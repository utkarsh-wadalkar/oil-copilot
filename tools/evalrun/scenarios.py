"""Replay the 18 evaluation scenarios faithfully, including their multi-turn setup.

``run.py ask`` sends one standalone turn per question. Five scenarios (Q12-Q17) are
multi-turn by design: they post a correction, confirm a rule change, or share an FYI
before the question that is graded. Running those standalone measures the harness, not
the copilot.

This driver uses the same in-process app and REST contract as ``ask``, but walks each
scenario turn by turn:

* corrections, rule changes, notes and claims go through ``POST /feedback`` (prepared by
  the copilot's own planner when the user states them in chat) and are then confirmed by
  the same user, exactly as a person would;
* "a new chat" really is a new conversation, so private history is exercised;
* every check quotes the expected fact from
  ``assets/flytbase-dataset/03-evaluation-queries.md`` and prints the observed value.

Nothing here changes the product. It is an oracle, so the expected values live in this
file and never in production code.

    python tools/evalrun/scenarios.py --database eval-runs/scenarios.sqlite3 \
        --out eval-runs/scenarios
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / 'backend'))

import run as evalrun  # noqa: E402  (the sibling harness module)

# Users from fleet/users.json. Names matter to the spec; IDs are the REST identity.
MICHAEL = 'U-201'   # Production supervisor, Northeast Production
JESSICA = 'U-202'   # Field inspector, Northeast Production
TYLER = 'U-204'     # Field operator, Northeast Production
JAKE = 'U-102'      # Field operator, Southwest Production
LAURA = 'U-401'     # HSE officer


# The dataset says "today" is 16 Oct 2026; the question document grades relative periods
# against that day, so the replay states it explicitly.
ANALYSIS_DATE = '2026-10-16'


# ---------------------------------------------------------------- runner
class Recorder:
    def __init__(self, client):
        self.client = client
        self.steps: list[dict] = []
        self.checks: list[dict] = []

    # -- REST helpers ------------------------------------------------------
    def new_chat(self, user):
        response = self.client.post('/conversations', json={}, headers={'X-User-ID': user})
        assert response.status_code == 201, response.text
        return response.json()['id']

    def say(self, user, text, tag, conversation=None):
        conversation = conversation or self.new_chat(user)
        response = self.client.post(
            f'/conversations/{conversation}/messages',
            json={'content': text, 'client_message_id': f'sc-{tag}'[:64],
                  'analysis_date': ANALYSIS_DATE},
            headers={'X-User-ID': user})
        payload = response.json() if response.status_code == 200 else {
            'error': f'HTTP {response.status_code}', 'detail': response.text[:2000]}
        self.steps.append({'user': user, 'text': text, 'conversation': conversation,
                           'response': payload})
        return payload

    def confirm(self, user, draft_id):
        response = self.client.post(f'/feedback/{draft_id}/confirm', json={},
                                    headers={'X-User-ID': user})
        body = (response.json() if response.status_code == 200
                else {'error': response.text[:1000]})
        return response.status_code, body

    def feedback(self, user, body):
        response = self.client.post('/feedback', json=body, headers={'X-User-ID': user})
        return response.status_code, (response.json() if response.status_code < 300
                                      else response.text[:1000])

    # -- checks ------------------------------------------------------------
    def check(self, scenario, label, expected, actual, ok):
        self.checks.append({'scenario': scenario, 'label': label,
                            'expected': expected, 'actual': actual, 'ok': bool(ok)})

    def eq(self, scenario, label, expected, actual):
        self.check(scenario, label, expected, actual, expected == actual)

    def contains(self, scenario, label, needle, text):
        text = str(text or '')
        self.check(scenario, label, f'contains {needle!r}', text[:300],
                   needle.lower() in text.lower())


def answer(response):
    return (response or {}).get('answer') or {}


def rows(response):
    return (answer(response).get('visual') or {}).get('data') or []


def draft(response):
    return (response or {}).get('draft') or {}


def summary(response):
    return answer(response).get('summary') or ''


def protocols(response):
    return {row.get('protocol'): row for row in rows(response)}


# ---------------------------------------------------------------- scenarios
def q1(r):
    q = 'Is WELL-0001 producing oil right now? When was it last inspected, and by whom? Show me its status card.'
    response = r.say(MICHAEL, q, 'q1')
    row = (rows(response) or [{}])[0]
    r.eq('Q1', 'visual', 'card', answer(response).get('visual', {}).get('kind'))
    r.eq('Q1', 'producing', False, row.get('producing'))
    r.eq('Q1', 'inspection id', 'INS-0001-0203', row.get('inspection_id'))
    r.eq('Q1', 'date', '2026-10-15', row.get('date'))
    r.eq('Q1', 'inspector', 'Ryan Brooks', row.get('inspector'))
    r.eq('Q1', 'delta above air', 3.2, round(row.get('delta_c') or 0, 1))
    r.eq('Q1', 'T200 limit', 15, round(row.get('threshold_c') or 0, 1))
    r.contains('Q1', 'reason names the planned rod string work', 'rod string', row.get('reason'))
    r.contains('Q1', 'reason expects a return around 20 Oct', '20 Oct', row.get('reason'))
    r.eq('Q1', 'recorded status', 'active', row.get('recorded_status'))
    r.eq('Q1', 'recorded status is stale', True, row.get('stale_recorded_status'))
    r.check('Q1', 'evidence cited', 'status card carries evidence', len(answer(response).get('evidence') or []),
            len(answer(response).get('evidence') or []) > 0)


def q2(r):
    q = 'Which wells in Northeast Block 8 are not producing oil right now, and why? Show them in a table.'
    response = r.say(MICHAEL, q, 'q2')
    data = rows(response)
    r.eq('Q2', 'visual', 'table', answer(response).get('visual', {}).get('kind'))
    r.eq('Q2', 'wells', ['WELL-0164', 'WELL-0170', 'WELL-0172', 'WELL-0175'],
         [row['well_id'] for row in data])
    r.eq('Q2', 'deltas', [4.1, 2.9, 5.7, 0.4], [round(row['delta_c'], 1) for row in data])
    r.eq('Q2', 'all last inspected 15 Oct', ['2026-10-15'] * 4, [row['date'] for row in data])
    located = {row['well_id']: row for row in data}
    r.eq('Q2', '0164 reason is absent', 'No recorded reason', located.get('WELL-0164', {}).get('reason'))
    r.contains('Q2', '0164 keeps the inspector remark', 'Pump jack not moving',
               located.get('WELL-0164', {}).get('inspection_remark'))
    r.contains('Q2', '0170 reason is the open pump jack repair', 'bearing wear',
               located.get('WELL-0170', {}).get('reason'))
    r.eq('Q2', '0170 recorded status', 'down', located.get('WELL-0170', {}).get('recorded_status'))
    r.contains('Q2', '0172 reason is the open flowline leak', 'pinhole',
               located.get('WELL-0172', {}).get('reason'))
    r.eq('Q2', '0175 reason is absent', 'No recorded reason', located.get('WELL-0175', {}).get('reason'))


def q3(r):
    q = ("Show a line chart of WELL-0001's wellhead temperature against air temperature for the "
         "last 13 weeks, and mark when it was not producing oil.")
    response = r.say(MICHAEL, q, 'q3')
    data = rows(response)
    r.eq('Q3', 'visual', 'line', answer(response).get('visual', {}).get('kind'))
    r.eq('Q3', 'reading count', 13, len(data))
    r.eq('Q3', 'first reading', '2026-07-23', data[0]['date'] if data else None)
    r.eq('Q3', 'last reading', '2026-10-15', data[-1]['date'] if data else None)
    r.eq('Q3', 'non-producing dates', ['2026-10-08', '2026-10-15'],
         [row['date'] for row in data if not row['producing']])
    r.check('Q3', 'every reading carries the production limit',
            'threshold_c on all rows', [row['threshold_c'] for row in data],
            all(row['threshold_c'] is not None for row in data))


def q4(r):
    q = ('How many oil spills has WELL-0001 had in the last 4 years, and how much oil in total? '
         'List them in a table.')
    response = r.say(MICHAEL, q, 'q4')
    data = rows(response)
    r.eq('Q4', 'visual', 'table', answer(response).get('visual', {}).get('kind'))
    r.eq('Q4', 'spill count', 6, len(data))
    r.eq('Q4', 'total barrels', 15.1, round(sum(row['volume_bbl'] for row in data), 1))
    r.eq('Q4', 'spill dates', ['2023-03-16', '2023-04-27', '2023-09-28', '2023-10-19',
                               '2026-06-11', '2026-10-01'], [row['date'] for row in data])
    r.eq('Q4', 'rainwater detection INS-0001-0070 excluded', False,
         any(row['inspection_id'] == 'INS-0001-0070' for row in data))


def q5(r):
    response = r.say(MICHAEL, 'How many days was WELL-0001 down in 2025?', 'q5')
    data = rows(response)
    r.eq('Q5', 'downtime days', 21, data[0].get('downtime_days') if data else None)
    r.eq('Q5', 'latest non-producing reading', '2025-10-23',
         str(data[0].get('latest_nonproducing') or '')[:10] if data else None)
    r.check('Q5', 'evidence cited', 'evidence for the three readings',
            len(answer(response).get('evidence') or []), len(answer(response).get('evidence') or []) >= 3)


def q6(r):
    q = 'Which 3 wells in Northeast Block 7 had the most downtime in the last 4 months? Show a bar chart.'
    response = r.say(MICHAEL, q, 'q6')
    data = rows(response)
    r.eq('Q6', 'visual', 'bar', answer(response).get('visual', {}).get('kind'))
    r.eq('Q6', 'ranked wells', [('WELL-0121', 49), ('WELL-0138', 42), ('WELL-0107', 42)],
         [(row['well_id'], row['downtime_days']) for row in data])
    r.eq('Q6', 'window', {'start': '2026-06-16', 'end': '2026-10-16'},
         answer(response).get('date_window'))


def q7(r):
    q = 'Show on a map every well in Northeast Block 8 with a real spill in the last 90 days.'
    response = r.say(MICHAEL, q, 'q7')
    data = rows(response)
    r.eq('Q7', 'visual', 'map', answer(response).get('visual', {}).get('kind'))
    r.eq('Q7', 'pin count', 4, len(data))
    located = {row['well_id']: (round(row['lat'], 5), round(row['lon'], 5), row['date'],
                                round(row['volume_bbl'], 1)) for row in data}
    r.eq('Q7', 'pins', {
        'WELL-0151': (32.12246, -102.18445, '2026-09-24', 4.5),
        'WELL-0165': (32.15665, -102.14522, '2026-07-30', 1.2),
        'WELL-0175': (32.18020, -102.14790, '2026-07-30', 3.9),
        'WELL-0186': (32.17552, -102.17775, '2026-07-23', 0.6),
    }, located)


def q8(r):
    response = r.say(MICHAEL, 'Show a heatmap of 2026 spills by geographic area and month.', 'q8')
    data = rows(response)
    r.eq('Q8', 'visual', 'heatmap', answer(response).get('visual', {}).get('kind'))
    months = [f'2026-{month:02d}' for month in range(1, 11)]
    r.eq('Q8', 'cells (4 areas x Jan-Oct)', 40, len(data))
    r.eq('Q8', 'months', months, sorted({row['month'] for row in data}))
    matrix = {(row['area'], row['month']): row['count'] for row in data}
    expected = {
        'Southwest Block 23': [4, 3, 3, 6, 3, 4, 4, 3, 3, 2],
        'Southwest Block 24': [7, 4, 5, 6, 5, 5, 3, 1, 5, 2],
        'Northeast Block 7': [5, 3, 2, 4, 6, 6, 2, 4, 4, 1],
        'Northeast Block 8': [4, 4, 4, 3, 2, 4, 4, 0, 1, 0],
    }
    for area, counts in expected.items():
        r.eq(f'Q8', f'{area} row', counts, [matrix.get((area, month)) for month in months])


def q9(r):
    q = 'Which rules has WELL-0001 broken in the last 12 months, and what is still open?'
    response = r.say(MICHAEL, q, 'q9')
    found = protocols(response)
    for protocol in ('SR-01', 'SR-02', 'SR-03', 'RC-04'):
        r.eq(f'Q9', f'{protocol} present and adverse', True,
             protocol in found and found[protocol].get('status') in {'breach', 'possible breach'})
    r.eq('Q9', 'breaches come from the June spill', 'INS-0001-0185',
         found.get('SR-01', {}).get('inspection_id'))
    r.eq('Q9', 'hours to report', 41.0, found.get('SR-01', {}).get('hours_to_report'))
    r.eq('Q9', 'containment took about 7 hours', 7.0, found.get('SR-02', {}).get('containment_hours'))
    r.eq('Q9', 'containment limit', 4, found.get('SR-02', {}).get('limit_hours'))
    r.eq('Q9', 'SR-03 verification due', '2026-08-10',
         str(found.get('SR-03', {}).get('due_at') or '')[:10])
    r.eq('Q9', 'SR-03 still open', 'open', found.get('SR-03', {}).get('completion_status'))
    r.eq('Q9', 'RC-04 response due', '2026-07-30',
         str(found.get('RC-04', {}).get('due_at') or '')[:10])
    r.eq('Q9', 'RC-04 no response recorded', 'open', found.get('RC-04', {}).get('completion_status'))
    r.eq('Q9', 'fine total', 5000, sum(row.get('fine_usd') or 0 for row in rows(response)))
    r.eq('Q9', 'RC-02 annual flowline test met', 'met', found.get('RC-02', {}).get('status'))
    r.contains('Q9', 'pending RCA on the flowline', 'flowline',
               str(found.get('RCA', {}).get('equipment_kind')))
    r.contains('Q9', 'planned shut-in missing from maintenance system', 'maintenance system',
               str(found.get('manual records', {}).get('detail')))
    r.eq('Q9', 'breach count', 4, sum(1 for row in rows(response)
                                     if row.get('status') == 'breach'))


def q10(r):
    q = ('In Southwest Block 24, which spills in the last 90 days were not contained '
         'within the SOP time limit?')
    response = r.say(MICHAEL, q, 'q10')
    data = rows(response)
    r.eq('Q10', 'visual', 'table', answer(response).get('visual', {}).get('kind'))
    r.eq('Q10', 'late spills', [('WELL-0082', 7.1), ('WELL-0100', 8.1)],
         [(row.get('well_id'), row.get('containment_hours')) for row in data])
    r.eq('Q10', 'SOP containment limit', 4, data[0].get('limit_hours') if data else None)


def q11(r):
    q6 = 'Which 3 wells in Northeast Block 7 had the most downtime in the last 4 months? Show a bar chart.'
    first = r.say(MICHAEL, q6, 'q11a')
    r.eq('Q11', 'day 1 resolved three wells', ['WELL-0121', 'WELL-0138', 'WELL-0107'],
         answer(first).get('selected_well_ids'))
    second = r.say(MICHAEL, 'For the three wells we discussed yesterday, what have repairs cost this year?',
                   'q11b')  # a new conversation: private memory must resolve it
    costs = {item.get('well_id'): round(float(item.get('cost_usd') or 0))
             for item in answer(second).get('calculations') or [] if 'cost_usd' in item}
    r.eq('Q11', 'recalled the earlier wells', ['WELL-0107', 'WELL-0121', 'WELL-0138'],
         sorted(answer(second).get('selected_well_ids') or []))
    r.eq('Q11', '2026 repair cost per well',
         {'WELL-0121': 25794, 'WELL-0138': 46942, 'WELL-0107': 5176}, costs)
    r.eq('Q11', 'cost rows are evidenced', True,
         all(row.get('evidence_ids') for row in rows(second)))


def q12(r):
    correction = ('The 15 Oct reading for WELL-0164 is wrong. The handheld thermal gun used in '
                  'that inspection was faulty; the field crew re-measured the wellhead at 41.0 °C.')
    first = r.say(MICHAEL, correction, 'q12a')
    d = draft(first)
    r.eq('Q12', 'turn asks for confirmation', 'pending_confirmation', first.get('status'))
    r.eq('Q12', 'correction targets the 15 Oct inspection', 'INS-0164-0205',
         (d.get('preview') or {}).get('inspection_id'))
    r.eq('Q12', 'original reading preserved', 24.0, d.get('before_value'))
    r.eq('Q12', 'corrected reading', 41.0, d.get('after_value'))
    r.eq('Q12', 'author', MICHAEL, d.get('author_id'))
    r.contains('Q12', 'reason recorded', 'faulty', d.get('reason'))
    r.eq('Q12', 'still provisional', 'pending', d.get('status'))
    code, confirmed = r.confirm(MICHAEL, d.get('id'))
    r.eq('Q12', 'confirm succeeds', 200, code)
    r.eq('Q12', 'correction keeps the original', 24.0,
         (confirmed.get('correction') or {}).get('original_value'))
    r.eq('Q12', 'correction stores the new value', 41.0,
         (confirmed.get('correction') or {}).get('value'))
    history = r.client.get('/wells/WELL-0164/history', headers={'X-User-ID': MICHAEL}).json()
    recorded = [u for u in history['updates'] if u['kind'] == 'inspection'
                and u['target_id'] == 'INS-0164-0205']
    r.eq('Q12', 'history keeps before/after/author', (24.0, 41.0, MICHAEL),
         ((recorded[-1]['before'], recorded[-1]['after'], recorded[-1]['author'])
          if recorded else None))
    r.contains('Q12', 'copilot flags the disagreeing inspector note', 'pump jack not moving',
               json.dumps(answer(first).get('conflicts') or []) + ' ' + summary(first))
    r.contains('Q12', 'copilot asks to confirm', 'confirm', summary(first))
    status = r.say(MICHAEL, 'Is WELL-0164 producing oil right now?', 'q12b')
    r.eq('Q12', 'with 41.0 C the well produces', True,
         (rows(status) or [{}])[0].get('producing'))
    r.eq('Q12', 'delta is 21.1 C above air', 21.1, round((rows(status) or [{}])[0].get('delta_c') or 0, 1))
    again = r.say(MICHAEL, 'Which wells in Northeast Block 8 are not producing oil right now, and why? '
                           'Show them in a table.', 'q12c')
    r.eq('Q12', 'Q2 afterwards lists three wells', ['WELL-0170', 'WELL-0172', 'WELL-0175'],
         [row['well_id'] for row in rows(again)])
    r.contains('Q12', 'answer says why 0164 is gone', '0164',
               summary(again) + ' ' + json.dumps(answer(again).get('calculations') or []))


def q13(r):
    correction = ('The AI estimated the 24 Sep spill at WELL-0151 as 4.5 bbl. '
                  'The field crew measured 5.4 bbl.')
    first = r.say(MICHAEL, correction, 'q13a')
    d = draft(first)
    r.eq('Q13', 'turn asks for confirmation', 'pending_confirmation', first.get('status'))
    r.eq('Q13', 'correction targets the 24 Sep inspection', 'INS-0151-0201',
         (d.get('preview') or {}).get('inspection_id'))
    r.eq('Q13', 'AI estimate preserved', 4.5, d.get('before_value'))
    r.eq('Q13', 'measured volume', 5.4, d.get('after_value'))
    r.eq('Q13', 'field', 'spill_est_volume_bbl', d.get('field'))
    code, _ = r.confirm(MICHAEL, d.get('id'))
    r.eq('Q13', 'confirm succeeds', 200, code)
    r.contains('Q13', 'now reportable at 5.4 bbl', 'reportable', summary(first) + ' ' +
               json.dumps(answer(first).get('calculations') or []))
    r.contains('Q13', 'SR-01 possible breach due 25 Sep', '2026-09-25',
               json.dumps(answer(first).get('calculations') or []) + ' ' + summary(first))
    r.contains('Q13', 'SR-03 verification due 23 Nov 2026', '2026-11-23',
               json.dumps(answer(first).get('calculations') or []) + ' ' + summary(first))
    compliance = r.say(MICHAEL, 'Which rules has WELL-0151 broken in the last 12 months?', 'q13b')
    found = protocols(compliance)
    r.eq('Q13', 'SR-01 flagged for no written notice', 'possible breach',
         found.get('SR-01', {}).get('status'))
    r.eq('Q13', 'SR-03 due 23 Nov 2026', '2026-11-23',
         str(found.get('SR-03', {}).get('due_at') or '')[:10])


def q14(r):
    question = 'Which wells in Northeast Block 7 need a root-cause analysis on their pump jack?'
    first = r.say(MICHAEL, question, 'q14a')
    r.eq('Q14', 'manual threshold finds three wells', ['WELL-0108', 'WELL-0121', 'WELL-0138'],
         answer(first).get('selected_well_ids'))
    r.eq('Q14', 'each has three corrective pump jack repairs', [3, 3, 3],
         [row.get('corrective_count') for row in rows(first)])
    r.eq('Q14', 'authority is the manual', {'official manual'},
         {row.get('authority') for row in rows(first)})
    rule = ('Note for all T350 wells: our team now wants a pump jack root-cause analysis '
            'after 2 repairs, not 3.')
    stated = r.say(MICHAEL, rule, 'q14b')
    d = draft(stated)
    r.eq('Q14', 'rule change is prepared', 'pending_confirmation', stated.get('status'))
    r.eq('Q14', 'rule scope', 'T350', d.get('target_id'))
    r.eq('Q14', 'rule threshold', 2, d.get('after_value'))
    r.eq('Q14', 'rule equipment', 'pump_jack', d.get('equipment_kind'))
    code, _ = r.confirm(MICHAEL, d.get('id'))
    r.eq('Q14', 'rule confirm succeeds', 200, code)
    second = r.say(MICHAEL, question, 'q14c')  # new chat
    r.eq('Q14', 'rule adds WELL-0120 and keeps the three',
         ['WELL-0108', 'WELL-0120', 'WELL-0121', 'WELL-0138'],
         answer(second).get('selected_well_ids'))
    r.eq('Q14', 'T200 WELL-0102 is not added', False,
         'WELL-0102' in (answer(second).get('selected_well_ids') or []))
    r.eq('Q14', 'the added well is T350 with two repairs',
         ('T350', 2),
         next(((row.get('well_type'), row.get('corrective_count')) for row in rows(second)
               if row.get('well_id') == 'WELL-0120'), None))
    r.eq('Q14', 'answer attributes the rule to Michael Turner',
         ('team override', 'Michael Turner'),
         next(((row.get('authority'), row.get('author')) for row in rows(second)
               if row.get('well_id') == 'WELL-0120'), None))
    r.contains('Q14', 'summary distinguishes the rule from the manual', 'michael turner',
               summary(second))


def q15(r):
    # Q15 follows Q12 and Q13, which the caller ran first.
    status = r.say(JESSICA, 'Is WELL-0164 producing oil right now?', 'q15a')
    row = (rows(status) or [{}])[0]
    r.eq('Q15', 'another user sees the correction', True, row.get('producing'))
    r.eq('Q15', 'the corrected value is 41.0 C', 41.0, row.get('wellhead_temp_c'))
    r.eq('Q15', 'the delta is 21.1 C above air', 21.1, round(row.get('delta_c') or 0, 1))
    r.contains('Q15', 'answer says who corrected it', 'michael turner',
               json.dumps(answer(status).get('calculations') or []) + ' ' + summary(status))
    r.contains('Q15', 'answer mentions the disagreeing inspector note', 'pump jack not moving',
               json.dumps(answer(status).get('conflicts') or []) + ' ' +
               str(row.get('inspection_remark')))
    reportable = r.say(LAURA, 'Which spills in Northeast Block 8 in the last 90 days needed a '
                              'report to the regulator?', 'q15b')
    data = rows(reportable)
    r.eq('Q15', 'only the corrected WELL-0151 spill is reportable',
         [('WELL-0151', 5.4)], [(row.get('well_id'), row.get('volume_bbl')) for row in data])
    row = (data or [{}])[0]
    r.eq('Q15', 'the corrected spill is reportable', True, row.get('reportable'))
    r.eq('Q15', 'no written notice is on record, so it is overdue', 'overdue',
         row.get('notice_status'))
    r.eq('Q15', 'the 24-hour notice deadline', '2026-09-25',
         str(row.get('notice_due_at') or '')[:10])


def q16(r):
    fyi = 'FYI for everyone: WELL-0007 will be shut in from 17 Oct for a 10-day planned workover.'
    shared = r.say(JAKE, fyi, 'q16a')
    d = draft(shared)
    r.eq('Q16', 'FYI is prepared for the shared store', 'pending_confirmation', shared.get('status'))
    r.eq('Q16', 'FYI is scoped to WELL-0007', 'WELL-0007', d.get('target_id'))
    code, _ = r.confirm(JAKE, d.get('id'))
    r.eq('Q16', 'FYI confirm succeeds', 200, code)
    planned = r.say(MICHAEL, 'Is any downtime planned for WELL-0007?', 'q16b')
    row = (rows(planned) or [{}])[0]
    r.eq('Q16', 'answers about WELL-0007', ['WELL-0007'], answer(planned).get('selected_well_ids'))
    r.eq('Q16', 'does not answer with historical downtime days', False, 'downtime_days' in row)
    notes = row.get('shared_notes') or []
    r.eq('Q16', 'the attributed plan is surfaced',
         [('Jake Morales', True)],
         [(note.get('author'), 'planned workover' in (note.get('text') or '').lower())
          for note in notes])
    r.contains('Q16', 'plan starts 17 Oct', '17 Oct', ' '.join(note.get('text') or '' for note in notes))
    r.contains('Q16', 'plan lasts about 10 days', '10-day',
               ' '.join(note.get('text') or '' for note in notes))
    private = r.say(JESSICA, 'For the three wells we discussed yesterday, what have repairs cost this year?',
                    'q16c')
    r.eq('Q16', 'does not reuse Michael Turner history', [], answer(private).get('selected_well_ids'))
    r.eq('Q16', 'no fleet-wide rows', [], rows(private))
    r.contains('Q16', 'says there is no such earlier conversation', 'no earlier conversation',
               summary(private))


def q17(r):
    claim = r.say(MICHAEL, 'WELL-0175 has been shut in for planned work since 14 Oct.', 'q17a')
    d = draft(claim)
    r.eq('Q17', 'shared plan claim is prepared', 'pending_confirmation', claim.get('status'))
    r.eq('Q17', 'claim is scoped to WELL-0175', 'WELL-0175', d.get('well_id') or d.get('target_id'))
    code, _ = r.confirm(MICHAEL, d.get('id'))
    r.eq('Q17', 'claim confirm succeeds', 200, code)

    tyler = r.say(TYLER, 'WELL-0175 is running fine.', 'q17b')
    row = (rows(tyler) or [{}])[0]
    r.eq('Q17', 'inspection contradicts the claim', False, row.get('producing'))
    r.eq('Q17', 'delta is 0.4 C above air', 0.4, round(row.get('delta_c') or 0, 1))
    r.eq('Q17', 'inspection was by Jessica Reed', 'Jessica Reed', row.get('inspector'))
    r.eq('Q17', 'both statements on record', {'Michael Turner', 'Tyler Hughes'},
         {note.get('author') for note in row.get('shared_notes') or []})
    r.eq('Q17', "Tyler's claim is unconfirmed",
         {'Tyler Hughes': 'unconfirmed'},
         {note.get('author'): note.get('status') for note in row.get('shared_notes') or []
          if note.get('author') == 'Tyler Hughes'})
    r.contains('Q17', 'asks for confirmation', 'confirm', summary(tyler))
    code, _ = r.confirm(TYLER, draft(tyler).get('id'))
    r.eq('Q17', 'Tyler draft confirmed as an unconfirmed claim', 200, code)

    jake = r.say(JAKE, 'WELL-0001 is back online since 14 Oct.', 'q17c')
    row = (rows(jake) or [{}])[0]
    r.eq('Q17', 'inspection contradicts the claim', False, row.get('producing'))
    r.eq('Q17', 'latest inspection is 15 Oct', '2026-10-15', row.get('date'))
    r.contains('Q17', 'note expects a return around 20 Oct', '20 Oct', row.get('reason'))
    claim_row = next((note for note in row.get('shared_notes') or []
                      if note.get('author') == 'Jake Morales'), None)
    r.eq('Q17', 'claim recorded as unconfirmed', 'unconfirmed', (claim_row or {}).get('status'))
    r.contains('Q17', 'conflict shown', 'confirm', json.dumps(answer(jake).get('conflicts') or []))
    r.confirm(JAKE, draft(jake).get('id'))


def q18(r):
    response = r.say(LAURA, 'Was the 20 Aug spill at WELL-0101 real oil?', 'q18')
    data = rows(response)
    r.eq('Q18', 'one detection', 1, len(data))
    r.eq('Q18', 'the AI flagged INS-0101-0197', 'INS-0101-0197',
         data[0].get('inspection_id') if data else None)
    r.eq('Q18', 'estimated volume', 1.0, data[0].get('volume_bbl') if data else None)
    conflict = json.dumps(answer(response).get('conflicts') or [])
    r.contains('Q18', 'shows Ryan Brooks produced-water note', 'produced water', conflict)
    r.contains('Q18', 'shows Chris Dalton confirmed crude', 'crude', conflict)
    r.eq('Q18', 'both notes retained',
         {'Ryan Brooks', 'Chris Dalton'},
         {note.get('author') for block in answer(response).get('conflicts') or []
          for note in block.get('notes') or []})
    r.eq('Q18', 'detection stands', True, any(
        'detection' in (note.get('text') or '').lower()
        for block in answer(response).get('conflicts') or []
        for note in block.get('notes') or []))
    r.contains('Q18', 'answer says yes', 'yes', summary(response))


SCENARIOS = [
    ('Q1', q1), ('Q2', q2), ('Q3', q3), ('Q4', q4), ('Q5', q5), ('Q6', q6),
    ('Q7', q7), ('Q8', q8), ('Q9', q9), ('Q10', q10), ('Q11', q11), ('Q12', q12),
    ('Q13', q13), ('Q14', q14), ('Q15', q15), ('Q16', q16), ('Q17', q17), ('Q18', q18),
]


def run_scenarios(r):
    for _, scenario in SCENARIOS:
        try:
            scenario(r)
        except Exception as exc:  # a broken scenario must not hide the others
            r.check('?', 'scenario raised', 'no exception', f'{type(exc).__name__}: {exc}', False)


def render(result) -> str:
    lines = ['# Scenario replay', '',
             f'- Dataset: `{result["dataset"]}`',
             f'- Database: `{result["database"]}` (fresh ingest per run)',
             f'- Mode: **{result["mode"]}**',
             f'- Generated: {result["generated_at"]}', '']
    by_scenario: dict[str, list[dict]] = {}
    for check in result['checks']:
        by_scenario.setdefault(check['scenario'], []).append(check)
    lines += ['| Scenario | Checks | Failing |', '|---|---|---|']
    for name, _ in SCENARIOS:
        checks = by_scenario.get(name, [])
        failing = [check for check in checks if not check['ok']]
        lines.append(f'| {name} | {len(checks)} | {len(failing)} |')
    lines.append('')
    for name, _ in SCENARIOS:
        checks = by_scenario.get(name, [])
        failing = [check for check in checks if not check['ok']]
        lines.append(f'## {name} — {"PASS" if not failing else "MISMATCH"}')
        lines.append('')
        lines.append('| Check | Expected | Actual | OK |')
        lines.append('|---|---|---|---|')
        for check in checks:
            actual = str(check['actual']).replace('|', '\\|')[:240]
            expected = str(check['expected']).replace('|', '\\|')[:240]
            lines.append(f'| {check["label"]} | {expected} | {actual} | {"yes" if check["ok"] else "**NO**"} |')
        lines.append('')
    return '\n'.join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', default='assets/flytbase-dataset/sample-data')
    parser.add_argument('--database', default='eval-runs/scenarios.sqlite3')
    parser.add_argument('--out', default='eval-runs/scenarios')
    parser.add_argument('--live-model', action='store_true')
    args = parser.parse_args(argv)

    database = Path(args.database)
    if not database.is_absolute():
        database = REPO / database
    database.parent.mkdir(parents=True, exist_ok=True)
    if database.exists():
        database.unlink()
    source = Path(args.source) if Path(args.source).is_absolute() else REPO / args.source
    started = time.time()
    app, engine, settings = evalrun.make_app(source, database, live_model=args.live_model, ingest=True)
    from fastapi.testclient import TestClient

    recorder = Recorder(None)
    with TestClient(app) as client:
        recorder.client = client
        run_scenarios(recorder)
    engine.dispose()

    result = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'dataset': str(source), 'database': str(database),
        'mode': evalrun.app_mode(settings), 'seconds': round(time.time() - started, 1),
        'checks': recorder.checks, 'steps': recorder.steps,
    }
    out = Path(args.out) if Path(args.out).is_absolute() else REPO / args.out
    out.mkdir(parents=True, exist_ok=True)
    (out / 'scenario-report.json').write_text(json.dumps(result, indent=2, default=str), encoding='utf-8')
    (out / 'scenario-report.md').write_text(render(result), encoding='utf-8')
    failing = [check for check in recorder.checks if not check['ok']]
    print(f'replayed {len(SCENARIOS)} scenarios: {len(recorder.checks)} checks, '
          f'{len(failing)} failing; wrote {out / "scenario-report.md"}')
    for check in failing:
        print(f'  FAIL {check["scenario"]}: {check["label"]} | expected {check["expected"]!r} | '
              f'actual {str(check["actual"])[:160]!r}')
    return 0 if not failing else 1


if __name__ == '__main__':
    raise SystemExit(main())
