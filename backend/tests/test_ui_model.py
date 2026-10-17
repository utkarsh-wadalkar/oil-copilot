"""The generative-UI boundary: composition without data authority.

The copilot model (gemma4:31b) owns facts; the UI model may only choose which parts of a
validated envelope to show. These tests pin the boundary, because it is the only thing
standing between "a model arranges the answer" and "a model invents the answer".
"""
from pathlib import Path

import pytest

from app import ui_model
from app.config import get_settings

SPEC = Path(__file__).resolve().parents[2] / 'frontend/lib/generated/ui-spec.json'
RESULT = '11111111-2222-3333-4444-555555555555'


def settings(**overrides):
    return get_settings().model_copy(update={'openui_enabled': True,
                                             'openui_spec_path': str(SPEC), **overrides})


ENVELOPE = {
    'question': 'Is WELL-0001 producing oil right now?',
    'summary': '1 status result(s).',
    'findings': [{'label': 'status', 'value': [{'well_id': 'WELL-0001'}]}],
    'warnings': ['No model credentials configured.'],
    'conflicts': [],
    'visual': {'kind': 'card', 'title': 'status', 'data': [{'well_id': 'WELL-0001'}]},
    'evidence': [{'id': 'src:1:2'}],
    'calculations': [],
}


def test_the_spec_is_the_browser_library():
    """The prompt and the renderer must be built from the same library, or nothing parses."""
    spec = ui_model.load_spec(settings())
    assert spec['root'] == 'Layout'
    assert set(spec['components']) == set(ui_model.ALLOWED_COMPONENTS)


def test_system_message_carries_the_library_and_the_no_fabrication_rule():
    message = ui_model.system_message(ui_model.load_spec(settings()))
    assert message.startswith(']]>openui:config')
    assert 'Layout' in message and 'AnswerPart' in message
    assert 'NEVER write a number' in message


def test_guard_accepts_a_composed_program():
    program = ('root = Layout([\n'
               f'  AnswerPart("{RESULT}", "summary"),\n'
               f'  AnswerPart("{RESULT}", "visual"),\n'
               '  Note("Two records disagree; both are shown.")\n'
               '])')
    assert ui_model.guard(program, RESULT) == program


def test_guard_strips_a_markdown_fence():
    program = f'```openui\nroot = Answer("{RESULT}")\n```'
    assert ui_model.guard(program, RESULT) == f'root = Answer("{RESULT}")'


def test_guard_rejects_an_invented_component():
    with pytest.raises(ui_model.UiRejected, match='outside the library'):
        ui_model.guard(f'root = Chart("{RESULT}", 999)', RESULT)


def test_guard_rejects_another_result_id():
    other = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
    with pytest.raises(ui_model.UiRejected, match='different result id'):
        ui_model.guard(f'root = Answer("{other}")', RESULT)


def test_guard_rejects_a_program_that_renders_nothing():
    with pytest.raises(ui_model.UiRejected, match='renders no part'):
        ui_model.guard('root = Layout([])', RESULT)


def test_compose_is_honest_when_generative_ui_is_off():
    off = get_settings().model_copy(update={'openui_enabled': False})
    result = ui_model.compose(ENVELOPE, RESULT, off)
    assert result.enabled is False
    assert result.program is None
    assert 'vLLM' in result.reason and 'OUI-1' in result.reason


def test_compose_returns_the_guarded_program(monkeypatch):
    monkeypatch.setattr(ui_model, '_post', lambda settings, payload: f'root = Answer("{RESULT}")')
    result = ui_model.compose(ENVELOPE, RESULT, settings())
    assert result.enabled is True
    assert result.program == f'root = Answer("{RESULT}")'
    assert result.reason is None


def test_compose_falls_back_when_the_model_is_unreachable(monkeypatch):
    import httpx

    def boom(settings, payload):
        raise httpx.ConnectError('no server')

    monkeypatch.setattr(ui_model, '_post', boom)
    result = ui_model.compose(ENVELOPE, RESULT, settings())
    assert result.enabled is True
    assert result.program is None
    assert 'unavailable' in result.reason


def test_compose_falls_back_when_the_model_breaks_the_boundary(monkeypatch):
    monkeypatch.setattr(ui_model, '_post', lambda settings, payload: f'root = Table("{RESULT}")')
    result = ui_model.compose(ENVELOPE, RESULT, settings())
    assert result.program is None
    assert result.reason.startswith('rejected:')
