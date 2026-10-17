"""Task 3B: REST contract, privacy, idempotency and the validated feedback workflow.

Seams under test are the documented REST endpoints plus the orchestrator answer
envelope. Behaviour is asserted through the public API only.
"""
import os
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.db import Base
from app.domain import InspectionFact, WellFact
from app.ingestion import ingest_dataset
from app.main import create_app

ROOT = Path(__file__).resolve().parents[2] / 'assets/flytbase-dataset/sample-data'
USER_A = 'U-201'
USER_B = 'U-202'


@pytest.fixture(scope='module')
def client():
    if os.environ.get('KNOWLEDGE_TEST_POSTGRES') == '1':
        from sqlalchemy.engine import make_url

        engine = create_engine(make_url(get_settings().database_url).set(host='127.0.0.1'))
    else:
        engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as session:
        batch = ingest_dataset(session, ROOT)
        assert batch.status == 'published', batch.error
    settings = get_settings().model_copy(update={'ollama_api_key': '', 'dataset_root': str(ROOT)})
    app = create_app(engine, settings=settings)
    with TestClient(app) as test_client:
        test_client.factory = factory
        yield test_client


def headers(user=USER_A):
    return {'X-User-ID': user}


def test_users_are_dataset_users(client):
    response = client.get('/users')
    assert response.status_code == 200
    users = response.json()['users']
    assert users and all(u['id'] and u['name'] for u in users)
    assert any(u['id'] in {USER_A, USER_B} for u in users)


def test_private_endpoints_require_a_real_user(client):
    assert client.get('/conversations').status_code == 401
    assert client.get('/conversations', headers=headers('U-999')).status_code == 403


def test_conversations_and_results_are_private(client):
    created = client.post('/conversations', json={'title': 'A chat'}, headers=headers(USER_A))
    assert created.status_code == 201
    conversation_id = created.json()['id']
    # Another user cannot read it.
    assert client.get(f'/conversations/{conversation_id}', headers=headers(USER_B)).status_code == 404
    listed_b = client.get('/conversations', headers=headers(USER_B)).json()['conversations']
    assert all(c['id'] != conversation_id for c in listed_b)
    answer = client.post(f'/conversations/{conversation_id}/messages',
                         json={'content': 'Is WELL-0001 producing oil right now?', 'client_message_id': 'cm-priv'},
                         headers=headers(USER_A))
    assert answer.status_code == 200
    result_id = answer.json()['answer']['result_id']
    assert client.get(f'/results/{result_id}', headers=headers(USER_B)).status_code == 404
    assert client.get(f'/results/{result_id}', headers=headers(USER_A)).status_code == 200


def test_offline_answer_is_grounded_and_idempotent(client):
    conversation_id = client.post('/conversations', json={}, headers=headers(USER_A)).json()['id']
    body = {'content': 'How many oil spills has WELL-0001 had in the last 4 years, and how much oil in total? '
                       'List them in a table.', 'client_message_id': 'cm-spills'}
    first = client.post(f'/conversations/{conversation_id}/messages', json=body, headers=headers(USER_A)).json()
    assert first['status'] == 'complete'
    answer = first['answer']
    assert answer['selected_well_ids'] == ['WELL-0001']
    assert answer['visual']['kind'] == 'table'
    assert answer['evidence'], 'a grounded answer must cite source evidence'
    counts = [c for c in answer['calculations'] if 'spill_count' in c]
    assert counts and counts[0]['spill_count'] >= 1
    # Same client_message_id returns the same stored result without recomputation.
    second = client.post(f'/conversations/{conversation_id}/messages', json=body, headers=headers(USER_A)).json()
    assert second['answer']['result_id'] == answer['result_id']
    # A different payload under the same id is rejected.
    conflict = client.post(f'/conversations/{conversation_id}/messages',
                           json={'content': 'something else', 'client_message_id': 'cm-spills'},
                           headers=headers(USER_A))
    assert conflict.status_code == 409


def test_offline_downtime_scenario(client):
    conversation_id = client.post('/conversations', json={}, headers=headers(USER_A)).json()['id']
    answer = client.post(f'/conversations/{conversation_id}/messages',
                         json={'content': 'How many days was WELL-0001 down in 2025?',
                               'client_message_id': 'cm-down'}, headers=headers(USER_A)).json()['answer']
    assert answer['selected_well_ids'] == ['WELL-0001']
    rows = answer['visual']['data']
    assert rows and rows[0]['well_id'] == 'WELL-0001' and isinstance(rows[0]['downtime_days'], int)


def _latest_inspection(client, well_id='WELL-0001'):
    with client.factory() as session:
        fact = session.scalars(select(InspectionFact).where(InspectionFact.well_id == well_id)
                               .order_by(InspectionFact.inspected_at.desc())).first()
        value = session.get(__import__('app.models', fromlist=['RecordVersion']).RecordVersion, fact.version_id)
        return fact.id, fact.wellhead_temp_c, value.payload.get('wellhead_temp_c')


def test_vague_feedback_persists_unresolved_and_asks_for_details(client):
    response = client.post('/feedback', json={'kind': 'correction', 'well_id': 'WELL-0001',
                                              'reason': 'the sensor data is wrong'},
                           headers=headers(USER_A))
    assert response.status_code == 201
    draft = response.json()
    assert draft['status'] == 'needs_clarification'
    assert draft.get('clarification'), 'a vague claim must ask specific questions'
    # The draft is durable, not silently dropped.
    fetched = client.get(f"/feedback/{draft['id']}", headers=headers(USER_A))
    assert fetched.status_code == 200 and fetched.json()['status'] == 'needs_clarification'
    # Another user cannot see or confirm it.
    assert client.get(f"/feedback/{draft['id']}", headers=headers(USER_B)).status_code == 404
    assert client.post(f"/feedback/{draft['id']}/confirm", json={}, headers=headers(USER_B)).status_code == 404


def test_correction_prepare_confirm_marks_results_outdated(client):
    inspection_id, effective, _ = _latest_inspection(client)
    # Save a result citing this inspection first.
    conversation_id = client.post('/conversations', json={}, headers=headers(USER_A)).json()['id']
    saved = client.post(f'/conversations/{conversation_id}/messages',
                        json={'content': 'Show a line chart of WELL-0001 wellhead temperature for the last 13 weeks',
                              'client_message_id': 'cm-temps'}, headers=headers(USER_A)).json()['answer']
    prepared = client.post('/feedback', json={
        'kind': 'correction', 'well_id': 'WELL-0001', 'target_id': inspection_id,
        'field': 'wellhead_temp_c', 'value': round(effective + 1.5, 2), 'unit': 'C',
        'reason': 'The handheld thermal gun used in that inspection was faulty; re-measured by the field crew.'},
        headers=headers(USER_A))
    assert prepared.status_code == 201, prepared.text
    draft = prepared.json()
    assert draft['status'] == 'pending'
    assert draft['preview']['before'] == effective and draft['preview']['after'] == round(effective + 1.5, 2)
    assert draft['preview']['well_id'] == 'WELL-0001'
    confirmed = client.post(f"/feedback/{draft['id']}/confirm", json={}, headers=headers(USER_A))
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()['correction_id']
    assert saved['result_id'] in confirmed.json()['outdated_results']
    # Confirmation is idempotent.
    again = client.post(f"/feedback/{draft['id']}/confirm", json={}, headers=headers(USER_A))
    assert again.status_code == 200 and again.json()['idempotent'] is True
    # The saved result is now flagged outdated but its payload is unchanged.
    result = client.get(f"/results/{saved['result_id']}", headers=headers(USER_A)).json()
    assert result['validity']['outdated'] is True
    # History exposes the update without requiring a date.
    history = client.get('/wells/WELL-0001/history', headers=headers(USER_A)).json()
    assert any(item.get('correction_id') == confirmed.json()['correction_id'] for item in history['updates'])


def test_confirm_requires_supersede_of_prior_correction(client):
    inspection_id, effective, _ = _latest_inspection(client)
    first = client.post('/feedback', json={'kind': 'correction', 'well_id': 'WELL-0001',
                                           'target_id': inspection_id, 'field': 'wellhead_temp_c',
                                           'value': 40.0, 'unit': 'C', 'reason': 'first correction'},
                        headers=headers(USER_A)).json()
    client.post(f"/feedback/{first['id']}/confirm", json={}, headers=headers(USER_A))
    second = client.post('/feedback', json={'kind': 'correction', 'well_id': 'WELL-0001',
                                            'target_id': inspection_id, 'field': 'wellhead_temp_c',
                                            'value': 42.0, 'unit': 'C', 'reason': 'revised correction'},
                         headers=headers(USER_A)).json()
    assert second['preview'].get('prior_correction'), 'a replacement must surface the prior correction'
    blocked = client.post(f"/feedback/{second['id']}/confirm", json={}, headers=headers(USER_A))
    assert blocked.status_code == 409
    allowed = client.post(f"/feedback/{second['id']}/confirm",
                          json={'supersedes': second['preview']['prior_correction']['id']},
                          headers=headers(USER_A))
    assert allowed.status_code == 200


def test_refresh_preserves_original_and_records_comparison(client):
    conversation_id = client.post('/conversations', json={}, headers=headers(USER_A)).json()['id']
    original = client.post(f'/conversations/{conversation_id}/messages',
                           json={'content': 'How many days was WELL-0001 down in 2025?',
                                 'client_message_id': 'cm-refresh'}, headers=headers(USER_A)).json()['answer']
    refreshed = client.post(f"/results/{original['result_id']}/refresh", json={}, headers=headers(USER_A))
    assert refreshed.status_code == 200
    new = refreshed.json()
    assert new['result_id'] != original['result_id']
    assert new['previous_result_id'] == original['result_id']
    assert new['comparison']['original']['summary'] == original['summary']
    # Original payload is preserved unchanged.
    kept = client.get(f"/results/{original['result_id']}", headers=headers(USER_A)).json()
    assert kept['answer']['summary'] == original['summary']


def test_evidence_resolves_to_a_trusted_source_slice(client):
    conversation_id = client.post('/conversations', json={}, headers=headers(USER_A)).json()['id']
    answer = client.post(f'/conversations/{conversation_id}/messages',
                         json={'content': 'Is WELL-0001 producing oil right now?', 'client_message_id': 'cm-ev'},
                         headers=headers(USER_A)).json()['answer']
    evidence_id = answer['evidence'][0]['id']
    resolved = client.get(f"/evidence/{evidence_id}", headers=headers(USER_A))
    assert resolved.status_code == 200
    body = resolved.json()
    assert body['source_id'] and body['excerpt'] and body['path']


def test_capabilities_and_indexing_status(client):
    capabilities = client.get('/capabilities', headers=headers(USER_A))
    assert capabilities.status_code == 200
    body = capabilities.json()
    assert 'offline' in body and 'model' in body
    status = client.get('/indexing/status', headers=headers(USER_A))
    assert status.status_code == 200
    assert 'jobs' in status.json()
