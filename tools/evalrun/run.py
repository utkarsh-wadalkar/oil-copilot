"""Load a dataset, run the evaluation questions, record the answers, score them.

This is the submission harness, and it is also the QA oracle's driver. It runs the app
**in process**, so a result never depends on a server someone forgot to start.

Two rules shape it:

* the dataset and the question document are inputs, not code. A released test dataset in
  the same format is loaded with ``load``, and its released questions are parsed with
  ``ask``; nothing about the sample data is baked in.
* the recorded answers are the deliverable. ``ask`` writes the exact envelope the copilot
  returned next to the expected text from the question document, so a human can grade it
  and a machine can re-check it later.

Commands
--------
    python tools/evalrun/run.py load --source assets/flytbase-dataset/sample-data
    python tools/evalrun/run.py ask --questions assets/flytbase-dataset/03-evaluation-queries.md
    python tools/evalrun/run.py score --out eval-runs/<stamp>

``--live`` sends the questions to a running server instead of using the app in process.
Without ``OPENUI``/model credentials the deterministic offline planner answers, which is
the only reproducible mode; ``ask`` records which mode produced each answer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'backend'))

#: A scenario heading may carry a parenthetical after the bold title, for example
#: ``**Q15. A correction reaches other users** (follows Q12 and Q13)``. Requiring the
#: bold title to end the line silently dropped that scenario from every recorded run.
QUESTION_RE = re.compile(r'^\*\*Q(?P<id>\d+)[.\u2013-]?\s*(?P<text>.+?)\*\*(?P<tail>.*)$')
HEADING_RE = re.compile(r'^#{1,3}\s')
EXPECTED_RE = re.compile(r'^\s*[-*]\s*Expected\b', re.I)
NUMERAL_RE = re.compile(r'\d+(?:[.,]\d+)?')


# ---------------------------------------------------------------- questions
@dataclass
class Question:
    id: str
    text: str
    expected: str = ''
    line: int = 0
    meta: dict = field(default_factory=dict)


def parse_questions(path: Path) -> list[Question]:
    """Parse the dataset's question document.

    The format is the one the dataset ships: a bold ``**Q1. question**`` line, then an
    ``Expected`` block of bullets and tables until the next question or heading. A plain
    ``.json`` list of strings/objects and a one-question-per-line ``.txt`` are also
    accepted, so the released questions load whatever form they arrive in.
    """
    if path.suffix == '.json':
        raw = json.loads(path.read_text(encoding='utf-8'))
        items = raw.get('questions', raw) if isinstance(raw, dict) else raw
        out = []
        for index, item in enumerate(items, start=1):
            if isinstance(item, str):
                out.append(Question(id=str(index), text=item.strip()))
            else:
                out.append(Question(id=str(item.get('id', index)).lstrip('Qq'),
                                    text=str(item.get('question') or item.get('text') or '').strip(),
                                    expected=str(item.get('expected') or ''),
                                    meta={k: v for k, v in item.items()
                                          if k not in {'id', 'question', 'text', 'expected'}}))
        return out
    if path.suffix in {'.txt', '.text'}:
        text = path.read_text(encoding='utf-8')
        parts = [line.strip() for line in text.splitlines() if line.strip()]
        numbered = [(re.match(r'^Q?(\d+)[.)\]]\s*(.+)$', line), line) for line in parts]
        if parts and all(match for match, _ in numbered):
            return [Question(id=m.group(1), text=m.group(2).strip()) for m, _ in numbered]
        return [Question(id=str(i), text=line) for i, line in enumerate(parts, start=1)]

    lines = path.read_text(encoding='utf-8').splitlines()
    questions: list[Question] = []
    current: Question | None = None
    expected: list[str] = []

    def flush() -> None:
        nonlocal current, expected
        if current is not None:
            current.expected = '\n'.join(expected).strip()
            questions.append(current)
        current, expected = None, []

    for number, line in enumerate(lines, start=1):
        match = QUESTION_RE.match(line.strip())
        if match:
            flush()
            current = Question(id=match.group('id'), text=match.group('text').strip(), line=number)
            continue
        if current is None:
            continue
        if HEADING_RE.match(line):
            flush()
            continue
        if EXPECTED_RE.match(line) or (expected and (line.startswith('  ') or line.strip() == ''
                                                     or line.startswith('-') or line.startswith('|'))):
            expected.append(line.rstrip())
        elif expected and not line.strip():
            expected.append('')
        elif expected and line.startswith('**'):
            flush()
    flush()
    return [q for q in questions if q.text]


# ---------------------------------------------------------------- app
def make_app(source: Path, database: Path, live_model: bool, ingest: bool | None = None):
    from sqlalchemy import create_engine, func, select
    from sqlalchemy.orm import Session

    from app.config import get_settings
    from app.db import Base
    from app.domain import WellFact
    from app.ingestion import ingest_dataset
    from app.main import create_app

    engine = create_engine(f'sqlite:///{database.as_posix()}', connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    should_ingest = ingest
    if should_ingest is None:
        # Reuse an already loaded dataset so repeat runs answer the same stored records.
        with Session(engine) as session:
            should_ingest = not session.scalar(select(func.count()).select_from(WellFact))
    if should_ingest:
        with Session(engine, expire_on_commit=False) as session:
            batch = ingest_dataset(session, source)
            if batch.status != 'published':
                raise SystemExit(f'dataset did not publish: {batch.status}: {batch.error}')
    settings = get_settings().model_copy(update={
        'dataset_root': str(source),
        'ollama_api_key': get_settings().ollama_api_key if live_model else '',
    })
    return create_app(engine, settings=settings), engine, settings


def app_mode(settings) -> str:
    return 'configured-model' if (settings.ollama_api_key or '') else 'offline-deterministic'


# ---------------------------------------------------------------- ask
def ask_one(client, user: str, question: str, tag: str) -> dict:
    headers = {'X-User-ID': user}
    conversation = client.post('/conversations', json={}, headers=headers).json()['id']
    body = {'content': question, 'client_message_id': f'ev-{tag}'[:64]}
    response = client.post(f'/conversations/{conversation}/messages', json=body, headers=headers)
    if response.status_code != 200:
        return {'error': f'HTTP {response.status_code}', 'detail': response.text[:800]}
    return response.json()


def run_questions(args) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    questions = parse_questions(Path(args.questions))
    if args.limit:
        questions = questions[: args.limit]
    if not questions:
        raise SystemExit('no questions parsed; check the question document format')

    database = Path(args.database)
    started = time.time()
    if args.base_url:
        client = _LiveClient(args.base_url)
        settings = None
        mode = 'live-http'
    else:
        app, engine, settings = make_app(Path(args.source), database, live_model=args.live_model)
        from fastapi.testclient import TestClient

        client = TestClient(app)
        mode = app_mode(settings)

    records = []
    with client as active:
        for question in questions:
            tag = f'{question.id}-{hashlib.sha256(question.text.encode()).hexdigest()[:8]}'
            payload = ask_one(active, args.user, question.text, tag)
            records.append({'id': question.id, 'question': question.text,
                            'expected': question.expected, 'response': payload})

    manifest = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'dataset': args.source,
        'questions_file': args.questions,
        'questions_sha256': hashlib.sha256(Path(args.questions).read_bytes()).hexdigest(),
        'database': database.as_posix(),
        'mode': mode,
        'user': args.user,
        'count': len(records),
        'seconds': round(time.time() - started, 1),
        'git_head': _git_head(),
    }
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    (out / 'answers.jsonl').write_text(
        '\n'.join(json.dumps(record, ensure_ascii=False) for record in records) + '\n', encoding='utf-8')
    (out / 'answers.md').write_text(render_answers(records, manifest), encoding='utf-8')
    print(f'wrote {len(records)} answers to {out} ({mode or "in-process"})')
    return 0


class _LiveClient:
    """Minimal ``TestClient``-shaped wrapper over a running server."""

    def __init__(self, base_url: str):
        import httpx

        self._client = httpx.Client(base_url=base_url.rstrip('/'), timeout=120)

    def post(self, path, json=None, headers=None):  # noqa: A002 - mirrors TestClient
        return self._client.post(path, json=json, headers=headers)

    def get(self, path, headers=None):
        return self._client.get(path, headers=headers)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._client.close()
        return False


def render_answers(records: list[dict], manifest: dict) -> str:
    lines = ['# Recorded answers', '',
             f'- Dataset: `{manifest["dataset"]}`',
             f'- Questions: `{manifest["questions_file"]}` (sha256 `{manifest["questions_sha256"][:16]}`)',
             f'- Mode: **{manifest["mode"] or "in-process"}**, user `{manifest["user"]}`',
             f'- Generated: {manifest["generated_at"]}', '']
    for record in records:
        lines.append(f'## Q{record["id"]}. {record["question"]}')
        lines.append('')
        if record['expected']:
            lines.append('<details><summary>Expected (from the question document)</summary>')
            lines.append('')
            lines.append(record['expected'])
            lines.append('')
            lines.append('</details>')
            lines.append('')
        payload = record['response']
        if payload.get('error'):
            lines += [f'**ERROR** {payload["error"]}', '', f'```\n{payload.get("detail", "")}\n```', '']
            continue
        answer = payload.get('answer') or {}
        visual = answer.get('visual') or {}
        lines.append(f'**Status:** {payload.get("status")}')
        lines.append('')
        lines.append(f'**Summary:** {answer.get("summary") or "(none)"}')
        lines.append('')
        lines.append(f'**Visual:** `{visual.get("kind")}`, {len(visual.get("data") or [])} row(s)')
        lines.append('')
        rows = visual.get('data') or []
        if rows and isinstance(rows[0], dict) and len(rows) <= 20:
            columns = [key for key in rows[0] if key != 'evidence_ids'][:8]
            lines.append('| ' + ' | '.join(columns) + ' |')
            lines.append('|' + '---|' * len(columns))
            for row in rows:
                cells = [str(row.get(column, ''))[:60].replace('|', '\\|') for column in columns]
                lines.append('| ' + ' | '.join(cells) + ' |')
            lines.append('')
        elif rows:
            lines.append(f'({len(rows)} rows recorded in `answers.jsonl`)')
            lines.append('')
        if answer.get('selected_well_ids'):
            lines.append(f'**Wells:** {", ".join(answer["selected_well_ids"])}')
            lines.append('')
        if answer.get('evidence'):
            lines.append(f'**Evidence refs:** {len(answer["evidence"])}')
            lines.append('')
        for conflict in answer.get('conflicts') or []:
            lines.append(f'**Conflict:** {conflict.get("message") or conflict}')
        for warning in answer.get('warnings') or []:
            lines.append(f'**Warning:** {warning}')
        lines.append('')
        lines.append('---')
        lines.append('')
    return '\n'.join(lines)


def _git_head() -> str | None:
    head = REPO / '.git' / 'HEAD'
    try:
        text = head.read_text(encoding='utf-8').strip()
        if text.startswith('ref:'):
            ref = text.split(':', 1)[1].strip()
            return (REPO / '.git' / ref).read_text(encoding='utf-8').strip()
        return text
    except OSError:
        return None


# ---------------------------------------------------------------- score
def _numerals(value, sink: set[str]) -> None:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, (int, float)):
        sink.add(_canonical(value))
        sink.add(_canonical(round(float(value), 1)))
        sink.add(_canonical(round(float(value), 2)))
    elif isinstance(value, str):
        for token in NUMERAL_RE.findall(value):
            sink.add(token)
            sink.add(token.replace(',', ''))
    elif isinstance(value, dict):
        for item in value.values():
            _numerals(item, sink)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _numerals(item, sink)


def _canonical(value) -> str:
    text = f'{float(value):.6f}'.rstrip('0').rstrip('.')
    return text or '0'


def score_records(records: list[dict]) -> dict:
    """The mechanical half of the QA rules. No model, no opinion.

    Every finding names its check, so a human can audit the arithmetic instead of
    trusting the total. Checks that need judgement are reported as ``unverified`` rather
    than counted, and the coverage figure makes that visible.
    """
    checks = []
    for record in records:
        payload = record.get('response') or {}
        answer = payload.get('answer') or {}
        visual = answer.get('visual') or {}
        rows = visual.get('data') or []

        traceable: set[str] = set()
        _numerals(answer.get('calculations') or [], traceable)
        _numerals(rows, traceable)

        prose = [answer.get('summary') or '']
        prose += [str(finding.get('value')) for finding in answer.get('findings') or []]
        prose += [str(item.get('message') or item) for item in answer.get('conflicts') or []]
        prose += [str(item) for item in answer.get('warnings') or []]
        untraceable = sorted({token for text in prose for token in NUMERAL_RE.findall(text)
                              if token not in traceable and token.replace(',', '') not in traceable})

        checks.append({
            'id': record['id'],
            'answered': bool(answer) and not payload.get('error'),
            'rows': len(rows),
            'visual': visual.get('kind'),
            'grounded': not untraceable,
            'untraceable_numerals': untraceable,
            'evidence': len(answer.get('evidence') or []),
            'warnings': len(answer.get('warnings') or []),
            'conflicts': len(answer.get('conflicts') or []),
        })

    executed = [check for check in checks if check['answered']]
    return {
        'questions': len(checks),
        'answered': len(executed),
        'grounded': sum(1 for check in executed if check['grounded']),
        'with_evidence': sum(1 for check in executed if check['evidence'] > 0),
        'empty_answers': [check['id'] for check in executed if check['rows'] == 0],
        'untraceable': {check['id']: check['untraceable_numerals']
                        for check in executed if check['untraceable_numerals']},
        'per_question': checks,
        'note': ('Grounded means every numeral in the prose is traceable to calculations or '
                 'rows. It proves traceability, not truth: truth needs the expected values, '
                 'which this command deliberately does not encode.'),
    }


def score_command(args) -> int:
    out = Path(args.out)
    records = [json.loads(line) for line in (out / 'answers.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    summary = score_records(records)
    (out / 'score.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    lines = ['# Answer audit', '',
             f'- Questions: {summary["questions"]}, answered: {summary["answered"]}',
             f'- Grounded (no untraceable numeral): {summary["grounded"]}/{summary["answered"]}',
             f'- With evidence: {summary["with_evidence"]}/{summary["answered"]}',
             f'- Empty answers: {", ".join(summary["empty_answers"]) or "none"}', '']
    if summary['untraceable']:
        lines += ['## Untraceable numerals', '']
        for question_id, tokens in summary['untraceable'].items():
            lines.append(f'- Q{question_id}: {", ".join(tokens)}')
        lines.append('')
    lines += [f'> {summary["note"]}', '']
    (out / 'score.md').write_text('\n'.join(lines), encoding='utf-8')
    print(f'audited {summary["answered"]}/{summary["questions"]} questions; '
          f'grounded {summary["grounded"]}/{summary["answered"]}; wrote {out / "score.md"}')
    return 0


# ---------------------------------------------------------------- cli
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)

    load = sub.add_parser('load', help='ingest a dataset into the evaluation database')
    load.add_argument('--source', default='assets/flytbase-dataset/sample-data')
    load.add_argument('--database', default='eval-runs/eval.sqlite3')

    ask = sub.add_parser('ask', help='run the questions and record the answers')
    ask.add_argument('--questions', default='assets/flytbase-dataset/03-evaluation-queries.md')
    ask.add_argument('--source', default='assets/flytbase-dataset/sample-data')
    ask.add_argument('--database', default='eval-runs/eval.sqlite3')
    ask.add_argument('--out', default=None, help='defaults to eval-runs/<utc stamp>')
    ask.add_argument('--user', default='U-201')
    ask.add_argument('--limit', type=int, default=0)
    ask.add_argument('--live-model', action='store_true', help='use the configured model instead of the offline planner')
    ask.add_argument('--base-url', default=None, help='ask a running server instead of the app in process')

    score = sub.add_parser('score', help='audit a recorded run')
    score.add_argument('--out', default=None)

    args = parser.parse_args(argv)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    if getattr(args, 'out', None) is None:
        args.out = str(REPO / 'eval-runs' / stamp)

    if args.command == 'load':
        database = Path(args.database)
        database.parent.mkdir(parents=True, exist_ok=True)
        if database.exists():
            database.unlink()
        make_app(Path(args.source), database, live_model=False)
        print(f'loaded {args.source} into {database}')
        return 0
    if args.command == 'ask':
        return run_questions(args)
    if args.command == 'score':
        return score_command(args)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
