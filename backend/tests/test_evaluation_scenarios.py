"""Task 5: the 18 evaluation scenarios at their deterministic seams.

Expected values are taken verbatim from
`assets/flytbase-dataset/03-evaluation-queries.md`. Scenarios already pinned by
`test_knowledge.py` (Q1, Q2, Q4-Q6, Q9, Q10, Q12-Q14, Q17, Q18) and by `test_api.py`
(the REST privacy/idempotency contract) are deliberately not repeated here; this file
covers the scenarios that had no assertion yet:

* Q3  - the line chart must mark the non-producing readings.
* Q7  - the spill map pins must carry the wells' real coordinates.
* Q8  - the heatmap must be the full area x month matrix, not just per-area totals.
* Q11 - recall of what the three earlier wells' repairs cost this year.
* Q15 - a correction made by one user reaches another user's answer.
* Q16 - a planned-downtime question reads the attributed plan (never the downtime history), and
  a reference to an earlier conversation that cannot be resolved is never widened to the fleet.

Ordering matters: the feedback scenarios commit real corrections into the shared module
engine, so they run last and use wells (WELL-0164, WELL-0007) that the read-only scenarios
never read.
"""
import os
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.db import Base
from app.ingestion import ingest_dataset
from app.knowledge import AssetKnowledge
from app.main import create_app
from app.models import SavedResult
from app.orchestrator import Orchestrator

ROOT = Path(__file__).resolve().parents[2] / 'assets/flytbase-dataset/sample-data'
USER_A = 'U-201'      # Michael Turner, production supervisor, northeast team
USER_B = 'U-202'      # Jessica Reed, field inspector, northeast team
USER_J = 'U-102'      # Jake Morales, field operator, southwest team
USER_FRESH = 'U-204'  # Tyler Hughes, field operator, with no earlier conversation
USER_HSE = 'U-401'    # Laura Simmons, HSE officer


@pytest.fixture(scope='module')
def engine():
    if os.environ.get('KNOWLEDGE_TEST_POSTGRES') == '1':
        from sqlalchemy.engine import make_url

        engine = create_engine(make_url(get_settings().database_url).set(host='127.0.0.1'))
    else:
        engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        batch = ingest_dataset(session, ROOT)
        assert batch.status == 'published', batch.error
    yield engine
    engine.dispose()


@pytest.fixture
def imported(engine):
    with engine.connect() as connection:
        connection.exec_driver_sql('BEGIN')
        with Session(connection, expire_on_commit=False, join_transaction_mode='create_savepoint') as session:
            yield session
        connection.rollback()


@pytest.fixture(scope='module')
def client(engine):
    settings = get_settings().model_copy(update={'ollama_api_key': '', 'dataset_root': str(ROOT)})
    app = create_app(engine, settings=settings)
    with TestClient(app) as test_client:
        yield test_client


def headers(user=USER_A):
    return {'X-User-ID': user}


def chat(client, user, text, tag, conversation=None, analysis_date='2026-10-16'):
    """One user turn through the REST contract, with the dataset's "today"."""
    conversation = conversation or client.post('/conversations', json={}, headers=headers(user)).json()['id']
    response = client.post(f'/conversations/{conversation}/messages',
                           json={'content': text, 'client_message_id': tag,
                                 'analysis_date': analysis_date}, headers=headers(user))
    assert response.status_code == 200, response.text
    return response.json()['answer']


def send(client, user, text, tag, conversation=None, analysis_date='2026-10-16'):
    conversation = conversation or client.post('/conversations', json={}, headers=headers(user)).json()['id']
    response = client.post(f'/conversations/{conversation}/messages',
                           json={'content': text, 'client_message_id': tag,
                                 'analysis_date': analysis_date}, headers=headers(user))
    assert response.status_code == 200, response.text
    return response.json()


def ask(session, operation, **kwargs):
    return AssetKnowledge(session).query({'operation': operation, **kwargs}).model_dump(mode='json')


def rows(answer):
    return answer['visual']['data']


def test_q3_line_chart_marks_the_non_producing_readings(imported):
    readings = rows(ask(imported, 'temperatures', well_ids=['WELL-0001'],
                        start='2026-07-23', end='2026-10-16'))
    assert len(readings) == 13, '23 Jul to 15 Oct 2026 is 13 weekly readings'
    # Q3: not producing oil on 8 Oct and 15 Oct.
    assert [r['date'] for r in readings if not r['producing']] == ['2026-10-08', '2026-10-15']
    assert all(r['threshold_c'] is not None for r in readings), 'the T200 limit must be carried for the plot'


def test_q7_spill_map_pins_use_the_real_well_locations(imported):
    pins = rows(ask(imported, 'spills', area='NE-08', start='2026-07-18', end='2026-10-16', visual='map'))
    assert len(pins) == 4
    located = {p['well_id']: (round(p['lat'], 5), round(p['lon'], 5)) for p in pins}
    assert located == {
        'WELL-0151': (32.12246, -102.18445),
        'WELL-0165': (32.15665, -102.14522),
        'WELL-0175': (32.18020, -102.14790),
        'WELL-0186': (32.17552, -102.17775),
    }


def test_q8_heatmap_is_the_full_area_by_month_matrix(imported):
    heat = rows(ask(imported, 'spills', start='2026-01-01', end='2026-10-16', visual='heatmap'))
    matrix = {(r['area'], r['month']): r['count'] for r in heat}
    expected = {
        'Southwest Block 23': [4, 3, 3, 6, 3, 4, 4, 3, 3, 2],
        'Southwest Block 24': [7, 4, 5, 6, 5, 5, 3, 1, 5, 2],
        'Northeast Block 7': [5, 3, 2, 4, 6, 6, 2, 4, 4, 1],
        'Northeast Block 8': [4, 4, 4, 3, 2, 4, 4, 0, 1, 0],
    }
    months = [f'2026-{month:02d}' for month in range(1, 11)]
    for area, counts in expected.items():
        assert [matrix[(area, month)] for month in months] == counts, area


def test_q8_heatmap_has_no_months_after_today(imported):
    """Q8: areas x Jan-Oct 2026. A window that names the year must not add future months."""
    heat = rows(ask(imported, 'spills', start='2026-01-01', end='2026-12-31', visual='heatmap'))
    assert len(heat) == 40, '4 areas x 10 observed months; Nov and Dec 2026 are in the future'
    assert {r['month'] for r in heat} == {f'2026-{month:02d}' for month in range(1, 11)}


def test_q6_window_is_the_four_calendar_months_ending_today(client):
    """Q6: "last 4 months" ends today (16 Oct 2026): window 16 Jun to 16 Oct."""
    answer = chat(client, USER_A, 'Which 3 wells in Northeast Block 7 had the most downtime in '
                                  'the last 4 months? Show a bar chart.', 'cm-q6-window')
    assert answer['date_window'] == {'start': '2026-06-16', 'end': '2026-10-16'}
    assert [(r['well_id'], r['downtime_days']) for r in answer['visual']['data']] == [
        ('WELL-0121', 49), ('WELL-0138', 42), ('WELL-0107', 42)]


def test_q9_rc04_past_deadline_with_no_response_is_a_breach(imported):
    """Q9: the notice response was due 30 Jul 2026 and none is recorded, so it is a breach.

    The SOP's 30-day obligation is RC-04 in fleet/sops/regulatory-compliance-sop.md:18.
    """
    comp = rows(ask(imported, 'compliance', well_ids=['WELL-0001'],
                    start='2025-10-17', end='2026-10-17'))
    rc04 = next(r for r in comp if r['protocol'] == 'RC-04')
    assert rc04['due_at'] == '2026-07-30'
    assert rc04['status'] == 'breach'
    assert sum(1 for r in comp if r['status'] == 'breach') == 4


def test_q10_containment_question_is_not_sop_guidance(client):
    """Q10: "contained within the SOP time limit" is a containment fact question."""
    answer = chat(client, USER_A, 'In Southwest Block 24, which spills in the last 90 days were '
                                  'not contained within the SOP time limit?', 'cm-q10')
    assert [(r['well_id'], r['containment_hours']) for r in answer['visual']['data']] == [
        ('WELL-0082', 7.1), ('WELL-0100', 8.1)]
    assert answer['visual']['data'][0]['limit_hours'] == 4


def test_q11_repair_cost_for_the_three_earlier_wells(imported):
    answer = ask(imported, 'maintenance', well_ids=['WELL-0121', 'WELL-0138', 'WELL-0107'],
                 start='2026-01-01', end='2026-10-16')
    costs = {c['well_id']: round(float(c['cost_usd'] or 0))
             for c in answer['calculations'] if 'cost_usd' in c}
    assert costs == {'WELL-0121': 25794, 'WELL-0138': 46942, 'WELL-0107': 5176}
    # The per-row evidence must still be present for a cost answer to be reviewable.
    assert all(r['evidence_ids'] for r in rows(answer))


def test_q11_chat_recalls_this_users_earlier_wells(client):
    """Q11: day 2, in a new chat, recalls the three wells of day 1 and their 2026 costs."""
    day_one = chat(client, USER_A, 'Which 3 wells in Northeast Block 7 had the most downtime in '
                                   'the last 4 months? Show a bar chart.', 'cm-q11-day1')
    assert day_one['selected_well_ids'] == ['WELL-0121', 'WELL-0138', 'WELL-0107']
    day_two = chat(client, USER_A, 'For the three wells we discussed yesterday, what have repairs '
                                   'cost this year?', 'cm-q11-day2')  # a new conversation
    assert sorted(day_two['selected_well_ids']) == ['WELL-0107', 'WELL-0121', 'WELL-0138']
    costs = {c['well_id']: round(float(c['cost_usd'])) for c in day_two['calculations']
             if 'cost_usd' in c}
    assert costs == {'WELL-0121': 25794, 'WELL-0138': 46942, 'WELL-0107': 5176}


def test_q12_chat_prepares_the_reading_correction_then_explains_q2(client):
    """Q12: the correction is a draft against INS-0164-0205, then Q2 shrinks to three wells."""
    turn = send(client, USER_A, 'The 15 Oct reading for WELL-0164 is wrong. The handheld thermal gun '
                                'used in that inspection was faulty; the field crew re-measured the '
                                'wellhead at 41.0 °C.', 'cm-q12')
    assert turn['status'] == 'pending_confirmation'
    draft = turn['draft']
    assert draft['status'] == 'pending'
    assert draft['preview']['inspection_id'] == 'INS-0164-0205'
    assert draft['preview']['before'] == 24.0
    assert draft['preview']['after'] == 41.0
    assert draft['author_id'] == USER_A
    # Provisional analysis: what the corrected reading would mean, without applying it.
    proposed = [c for c in turn['answer']['calculations'] if c.get('kind') == 'proposed_reading']
    assert proposed and proposed[0]['delta_c'] == 21.1 and proposed[0]['producing'] is True
    assert any('pump jack not moving' in (c.get('remark') or '').lower()
               for c in turn['answer']['conflicts'])
    assert 'confirm' in turn['answer']['summary'].lower()

    confirmed = client.post(f"/feedback/{draft['id']}/confirm", json={}, headers=headers(USER_A))
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()['correction']['original_value'] == 24.0
    assert confirmed.json()['correction']['value'] == 41.0

    status = chat(client, USER_A, 'Is WELL-0164 producing oil right now?', 'cm-q12-status')
    assert status['visual']['data'][0]['producing'] is True
    assert round(status['visual']['data'][0]['delta_c'], 1) == 21.1

    again = chat(client, USER_A, 'Which wells in Northeast Block 8 are not producing oil right now, '
                                 'and why? Show them in a table.', 'cm-q12-q2')
    assert [r['well_id'] for r in again['visual']['data']] == ['WELL-0170', 'WELL-0172', 'WELL-0175']
    assert 'WELL-0164' in again['summary'], 'the answer must say why WELL-0164 is no longer listed'
    assert 'corrected' in again['summary'].lower()


def test_q13_chat_prepares_the_volume_correction_and_flags_reporting(client):
    """Q13: 5.4 bbl against the 5 bbl SOP threshold, so SR-01 and SR-03 now apply."""
    turn = send(client, USER_A, 'The AI estimated the 24 Sep spill at WELL-0151 as 4.5 bbl. '
                                'The field crew measured 5.4 bbl.', 'cm-q13')
    assert turn['status'] == 'pending_confirmation'
    draft = turn['draft']
    assert draft['preview']['inspection_id'] == 'INS-0151-0201'
    assert draft['preview']['before'] == 4.5
    assert draft['preview']['after'] == 5.4
    assert draft['field'] == 'spill_est_volume_bbl'
    proposed = {c['protocol']: c for c in turn['answer']['calculations']
                if c.get('kind') == 'proposed_spill' and c.get('protocol')}
    assert proposed['SR-01']['status'] == 'possible breach'
    assert proposed['SR-01']['due_at'].startswith('2026-09-25T15:30')
    assert proposed['SR-03']['due_at'].startswith('2026-11-23')
    assert 'reportable' in turn['answer']['summary'].lower()
    confirmed = client.post(f"/feedback/{draft['id']}/confirm", json={}, headers=headers(USER_A))
    assert confirmed.status_code == 200, confirmed.text


def test_q14_rule_change_for_an_inheriting_well_type(client):
    """Q14: T350 inherits the T200 threshold, and a team rule of 2 replaces it for T350 only."""
    question = 'Which wells in Northeast Block 7 need a root-cause analysis on their pump jack?'
    before = chat(client, USER_A, question, 'cm-q14-before')
    assert before['selected_well_ids'] == ['WELL-0108', 'WELL-0121', 'WELL-0138']
    turn = send(client, USER_A, 'Note for all T350 wells: our team now wants a pump jack root-cause '
                                'analysis after 2 repairs, not 3.', 'cm-q14-rule')
    assert turn['status'] == 'pending_confirmation'
    draft = turn['draft']
    assert (draft['target_id'], draft['equipment_kind'], draft['after_value']) == ('T350', 'pump_jack', 2)
    confirmed = client.post(f"/feedback/{draft['id']}/confirm", json={}, headers=headers(USER_A))
    assert confirmed.status_code == 200, confirmed.text
    after = chat(client, USER_A, question, 'cm-q14-after')  # a new conversation
    assert after['selected_well_ids'] == ['WELL-0108', 'WELL-0120', 'WELL-0121', 'WELL-0138']
    assert 'WELL-0102' not in after['selected_well_ids'], 'a T200 well must not inherit the T350 rule'
    added = next(r for r in after['visual']['data'] if r['well_id'] == 'WELL-0120')
    assert added['corrective_count'] == 2 and added['authority'] == 'team override'
    assert added['author'] == 'Michael Turner'
    assert 'michael turner' in after['summary'].lower()


def test_q15_a_correction_reaches_another_user(client):
    prepared = client.post('/feedback', json={
        'kind': 'correction', 'well_id': 'WELL-0164', 'target_id': 'INS-0164-0205',
        'field': 'wellhead_temp_c', 'value': 41.0, 'unit': 'C',
        'reason': 'The handheld thermal gun used in that inspection was faulty; '
                  'the field crew re-measured the wellhead at 41.0 C.'}, headers=headers(USER_A))
    assert prepared.status_code == 201, prepared.text
    draft = prepared.json()
    assert draft['status'] == 'pending'
    assert draft['preview']['before'] == 24.0, 'the original reading must be preserved for review'
    confirmed = client.post(f"/feedback/{draft['id']}/confirm", json={}, headers=headers(USER_A))
    assert confirmed.status_code == 200, confirmed.text

    # Q15: a different user, in their own conversation, gets the corrected production state.
    conversation = client.post('/conversations', json={}, headers=headers(USER_B)).json()['id']
    answer = client.post(f'/conversations/{conversation}/messages',
                         json={'content': 'Is WELL-0164 producing oil right now?',
                               'client_message_id': 'cm-q15'}, headers=headers(USER_B)).json()['answer']
    assert answer['selected_well_ids'] == ['WELL-0164']
    row = answer['visual']['data'][0]
    assert row['producing'] is True, '41.0 C against 19.9 C air is 21.1 C warmer, above the T200 limit'
    assert answer['conflicts'], "the inspector's 'Pump jack not moving' note disagrees and must be shown"


def test_q15_a_corrected_volume_makes_the_spill_reportable(client):
    """Q15(b): with 5.4 bbl, WELL-0151 needs the regulator notice, and none is on record."""
    answer = chat(client, USER_HSE, 'Which spills in Northeast Block 8 in the last 90 days needed a '
                                    'report to the regulator?', 'cm-q15-report')
    data = answer['visual']['data']
    assert [(row['well_id'], row['volume_bbl']) for row in data] == [('WELL-0151', 5.4)]
    assert data[0]['reportable'] is True
    assert data[0]['notice_status'] == 'overdue', 'no written notice is recorded'
    assert data[0]['notice_due_at'].startswith('2026-09-25')


def test_a_resolved_reference_scopes_the_query_instead_of_widening(engine):
    """The positive half of the Q16 guardrail: when recall does resolve, it scopes the query."""
    settings = get_settings().model_copy(update={'ollama_api_key': '', 'dataset_root': str(ROOT)})
    with Session(engine, expire_on_commit=False) as session:
        prior = SavedResult(conversation_id='conv-prior', user_id=USER_FRESH,
                            question='Which wells in Northeast Block 7 had the most downtime this quarter?',
                            payload={'selected_well_ids': ['WELL-0121', 'WELL-0138', 'WELL-0107']})
        session.add(prior)
        session.flush()
        prior_id = prior.id

        class StubGraph:
            """Stands in for the projected memory graph, which the API process does not read."""

            def recall(self, user_id, query, well_ids, start, end, limit):
                return [prior_id]

        orchestrator = Orchestrator(session, provider=None, graph=StubGraph(), settings=settings)
        outcome = orchestrator.answer(USER_FRESH, 'conv-now',
                                      'For the three wells we discussed yesterday, what have repairs cost this year?',
                                      analysis_date=date(2026, 10, 17))

    answer = outcome['envelope']
    # The referenced wells scope the query; row order is the analytic layer's business, not the test's.
    assert sorted(answer['selected_well_ids']) == ['WELL-0107', 'WELL-0121', 'WELL-0138']
    assert {c['well_id'] for c in answer['calculations'] if 'cost_usd' in c} == {'WELL-0121', 'WELL-0138', 'WELL-0107'}


def test_q16_a_planned_outage_is_answered_from_the_attributed_plan(client):
    """Q16: a question about the future must not be answered with historical downtime days."""
    prepared = client.post('/feedback', json={
        'kind': 'claim', 'well_id': 'WELL-0007',
        'value': 'WELL-0007 will be shut in from 17 Oct for a 10-day planned workover.',
        'reason': 'Planned workover agreed with the field team.'}, headers=headers(USER_J))
    assert prepared.status_code == 201, prepared.text
    draft = prepared.json()
    if draft['status'] == 'pending':
        confirmed = client.post(f"/feedback/{draft['id']}/confirm", json={}, headers=headers(USER_J))
        assert confirmed.status_code == 200, confirmed.text

    conversation = client.post('/conversations', json={}, headers=headers(USER_A)).json()['id']
    answer = client.post(f'/conversations/{conversation}/messages',
                         json={'content': 'Is any downtime planned for WELL-0007?',
                               'client_message_id': 'cm-q16a'}, headers=headers(USER_A)).json()['answer']
    assert answer['selected_well_ids'] == ['WELL-0007']
    row = answer['visual']['data'][0]
    assert 'downtime_days' not in row, 'historical downtime days must not answer a planned-outage question'
    plans = [c for c in row.get('shared_notes') or [] if 'planned workover' in (c['text'] or '').lower()]
    assert plans, 'the attributed plan must be surfaced'
    assert plans[0]['author'] == 'Jake Morales'


def test_q16_an_unresolved_reference_never_widens_to_the_fleet(client):
    """Q16: with no such earlier conversation, say so rather than answering a fleet-wide question."""
    conversation = client.post('/conversations', json={}, headers=headers(USER_FRESH)).json()['id']
    answer = client.post(f'/conversations/{conversation}/messages',
                         json={'content': 'For the three wells we discussed yesterday, what have repairs cost this year?',
                               'client_message_id': 'cm-q16b'}, headers=headers(USER_FRESH)).json()['answer']
    assert answer['selected_well_ids'] == [], 'an unresolved reference must not select the whole fleet'
    assert answer['visual']['data'] == []
    assert 'no earlier conversation' in answer['summary'].lower()


def test_q17_claims_show_the_conflict_and_stay_unconfirmed(client):
    """Q17: a claim is kept on record, but the inspection wins and the conflict is shown."""
    plan = send(client, USER_A, 'WELL-0175 has been shut in for planned work since 14 Oct.', 'cm-q17-plan')
    assert plan['status'] == 'pending_confirmation'
    confirmed = client.post(f"/feedback/{plan['draft']['id']}/confirm", json={}, headers=headers(USER_A))
    assert confirmed.status_code == 200, confirmed.text

    tyler = send(client, USER_FRESH, 'WELL-0175 is running fine.', 'cm-q17-tyler')
    row = tyler['answer']['visual']['data'][0]
    assert row['producing'] is False and round(row['delta_c'], 1) == 0.4
    assert row['inspector'] == 'Jessica Reed'
    notes = {note['author']: note['status'] for note in row.get('shared_notes') or []}
    assert notes.get('Michael Turner'), 'the earlier plan is still on record'
    assert notes.get('Tyler Hughes') == 'unconfirmed'
    assert tyler['answer']['conflicts'], 'the disagreement must be shown, not resolved silently'
    assert 'confirm' in tyler['answer']['summary'].lower()
    confirmed = client.post(f"/feedback/{tyler['draft']['id']}/confirm", json={}, headers=headers(USER_FRESH))
    assert confirmed.status_code == 200, confirmed.text

    jake = send(client, USER_J, 'WELL-0001 is back online since 14 Oct.', 'cm-q17-jake')
    row = jake['answer']['visual']['data'][0]
    assert row['producing'] is False and row['date'] == '2026-10-15'
    assert '20 Oct' in row['reason'], 'CTX-0001-003 expects a return around 20 Oct'
    claim = next(note for note in row.get('shared_notes') or [] if note['author'] == 'Jake Morales')
    assert claim['status'] == 'unconfirmed'
    assert jake['answer']['conflicts']


def test_q18_a_single_disputed_spill_still_answers_yes(client):
    """Q18: two informal notes disagree; neither is a correction, so the detection stands."""
    answer = chat(client, USER_HSE, 'Was the 20 Aug spill at WELL-0101 real oil?', 'cm-q18')
    data = answer['visual']['data']
    assert len(data) == 1
    assert data[0]['inspection_id'] == 'INS-0101-0197'
    assert data[0]['volume_bbl'] == 1.0
    assert answer['summary'].lower().startswith('yes')
    authors = {note['author'] for conflict in answer['conflicts']
               for note in conflict.get('notes') or []}
    assert authors == {'Ryan Brooks', 'Chris Dalton'}
