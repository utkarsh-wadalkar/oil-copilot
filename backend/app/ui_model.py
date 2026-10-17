"""Generative UI composition over an already validated answer envelope.

Two models, two jobs, and the boundary between them is the point:

* the **copilot model** (``OLLAMA_MODEL``, gemma4:31b) talks to the engineer and owns the
  facts. Everything it says is recomputed and validated into an :class:`AnswerEnvelope`;
* the **UI model** (``OPENUI_MODEL``, ``thesysdev/OUI-1`` served through any
  OpenAI-compatible endpoint) only decides *presentation*: which parts of that envelope to
  lead with, in what order, and what short annotation to add.

The UI model therefore has no authority over a value. A program may call ``Layout``,
``Answer``, ``AnswerPart`` and ``Note`` and nothing else, every ``resultId`` in it must be
the envelope's own id, and any violation is rejected so the caller renders deterministically
instead. That is what makes it safe to let a generative model near a regulated answer.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.config import Settings

#: The only components the UI model may call. Mirrors frontend/components/uiLibrary.tsx.
ALLOWED_COMPONENTS = frozenset({'Layout', 'Answer', 'AnswerPart', 'Note'})

_CALL_RE = re.compile(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*\(')
_UUID_RE = re.compile(r'"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"')
_FENCE_RE = re.compile(r'^\s*```(?:openui|text)?\s*\n(?P<body>.*?)\n```\s*$', re.S)

_INSTRUCTIONS = (
    'You build the interface for one validated oil-well answer. '
    'Return only an OpenUI Lang program whose first line is `root = Layout([...])`. '
    'Use AnswerPart to show only the sections a reader needs, and Answer only when every section matters. '
    'Order the parts so the most important one comes first. '
    'NEVER write a number, date, well id, name or citation yourself: every value is already in the answer. '
    'Use Note only for a short sentence of your own that adds no new fact, and prefer omitting it. '
    'Never invent a component, and never reference a result id other than the one supplied.'
)


class UiUnavailable(RuntimeError):
    """No UI model is configured, so the caller renders deterministically."""


class UiRejected(RuntimeError):
    """The UI model returned a program outside the allowed surface."""


@dataclass
class UiProgram:
    enabled: bool
    model: str | None = None
    program: str | None = None
    reason: str | None = None


def spec_path(settings: Settings) -> Path:
    path = Path(settings.openui_spec_path)
    if path.is_absolute():
        return path
    return Path(__file__).resolve().parents[2] / path


def load_spec(settings: Settings) -> dict:
    path = spec_path(settings)
    if not path.is_file():
        raise UiUnavailable(f'OpenUI library spec is missing at {path}; run `npm run generate:ui-spec` in frontend/')
    return json.loads(path.read_text(encoding='utf-8'))


def system_message(spec: dict) -> str:
    """The Gateway config block plus trusted app instructions.

    Same payload as ``generateSystemPrompt({ cloud: true, library })`` from
    ``@openuidev/lang-core``, which is what the official FastAPI example builds: a config
    line carrying the library, so the model validates against the components the browser
    actually has.
    """
    chat_library = {key: spec[key] for key in ('schema', 'root', 'componentGroups', 'id')
                    if key in spec and spec[key] is not None}
    return ']]>openui:config\n' + json.dumps({'chatLibrary': chat_library}) + '\n\n' + _INSTRUCTIONS


def user_message(envelope: dict, result_id: str) -> str:
    """Describe the answer's shape, not its values, so the model can choose sections."""
    visual = envelope.get('visual') or {}
    parts = {
        'summary': bool(envelope.get('summary')),
        'findings': len(envelope.get('findings') or []),
        'warnings': len(envelope.get('warnings') or []),
        'conflicts': len(envelope.get('conflicts') or []),
        'visual': {'kind': visual.get('kind'), 'rows': len(visual.get('data') or [])},
        'evidence': len(envelope.get('evidence') or []),
        'calculations': len(envelope.get('calculations') or []),
    }
    brief = {
        'result_id': result_id,
        'question': envelope.get('question'),
        'available_parts': parts,
        'requested_visual': visual.get('kind'),
    }
    return ('Build the interface for this validated answer. Use only the parts listed and '
            'reference this result id exactly.\n' + json.dumps(brief, indent=2))


def guard(program: str, result_id: str) -> str:
    """Reject anything outside the declared surface before it reaches a renderer."""
    text = (program or '').strip()
    fenced = _FENCE_RE.match(text)
    if fenced:
        text = fenced.group('body').strip()
    if not re.match(r'^root\s*=', text):
        raise UiRejected('program does not start with a root assignment')
    if len(text) > 20_000:
        raise UiRejected('program is unreasonably large')
    calls = set(_CALL_RE.findall(text))
    unknown = calls - ALLOWED_COMPONENTS
    if unknown:
        raise UiRejected(f'program uses components outside the library: {", ".join(sorted(unknown))}')
    if 'Answer' not in calls and 'AnswerPart' not in calls:
        raise UiRejected('program renders no part of the answer')
    foreign = {match for match in _UUID_RE.findall(text) if match.lower() != result_id.lower()}
    if foreign:
        raise UiRejected('program references a different result id')
    return text


def _post(settings: Settings, payload: dict) -> str:
    """One Chat Completions call. Separated so tests never touch the network."""
    response = httpx.post(
        f'{settings.openui_base_url.rstrip("/")}/chat/completions',
        headers={'Authorization': f'Bearer {settings.openui_api_key}'} if settings.openui_api_key else {},
        json=payload,
        timeout=settings.openui_timeout_seconds,
    )
    response.raise_for_status()
    body = response.json()
    return (body['choices'][0]['message'].get('content') or '')


def compose(envelope: dict, result_id: str, settings: Settings) -> UiProgram:
    """Ask the UI model for a program. Never invents a fallback program of its own."""
    if not settings.openui_enabled:
        return UiProgram(enabled=False, reason=(
            'Generative UI is off. Set OPENUI_ENABLED=1 and point OPENUI_BASE_URL at a server that '
            'writes OpenUI Lang (vLLM serving thesysdev/OUI-1, or OpenUI Gateway).'))
    try:
        spec = load_spec(settings)
    except UiUnavailable as exc:
        return UiProgram(enabled=False, reason=str(exc))
    payload = {
        'model': settings.openui_model,
        'temperature': 0,
        'messages': [
            {'role': 'system', 'content': system_message(spec)},
            {'role': 'user', 'content': user_message(envelope, result_id)},
        ],
    }
    try:
        raw = _post(settings, payload)
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        return UiProgram(enabled=True, model=settings.openui_model,
                         reason=f'UI model unavailable: {type(exc).__name__}')
    try:
        program = guard(raw, result_id)
    except UiRejected as exc:
        return UiProgram(enabled=True, model=settings.openui_model, reason=f'rejected: {exc}')
    return UiProgram(enabled=True, model=settings.openui_model, program=program)
