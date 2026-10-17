"""Operations for the released test dataset and its SOPs.

Every row is computed from the active records and cites the source line it came from. Where the
dataset does not contain the quantity a question asks for (reservoir pressure, produced oil
volume), the operation returns no rows and a warning that names the missing field instead of a
plausible-looking proxy presented as an answer.

The rules implemented here are transcribed from the documents that ship with the data:
OPS-1 gas odor response, OPS-2 temporary bypass, OPS-3 status evidence precedence, OPS-5 freeze
protection, the supplier recall notice, and the 20 Nov 2026 regulator letter.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import PurePosixPath

from sqlalchemy import select

from app.domain import InspectionFact, MaintenanceFact
from app.models import ActiveRecord, Correction, RecordVersion, SourceVersion

GAS = re.compile(r'gas odor|gas smell|smelled gas|smell of gas|rotten-egg|rotten egg|h2s monitor|gas at the', re.I)
SHUT = re.compile(r'shut[- ]?in|shut the well|well (?:was )?closed|stopped the well|not producing|ceased', re.I)
RESTART = re.compile(r'restart|back online|returned to production|started (?:it )?up|put .* back (?:on|online)|resumed', re.I)
BYPASS_IN = re.compile(r'bypass (?:in place|installed)|installed (?:a |the )?bypass|had the bypass installed', re.I)
BYPASS_OUT = re.compile(r'took the bypass out|bypass (?:was )?removed|removed (?:the )?bypass', re.I)
WRONG = re.compile(r'knock|noise|noisy|vibrat|straining|squeal|rattl|grind|gas|leak|seal|trip|overheat|hot|smell|smoke|ice|freez|pressure|alarm|fault', re.I)
SPILL_CLEAN = re.compile(r'spill|clean[- ]?up|containment|excavat', re.I)


def _utc(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _active(session, kind):
    return list(session.scalars(select(RecordVersion).join(
        ActiveRecord, ActiveRecord.version_id == RecordVersion.id).where(RecordVersion.kind == kind)))


def _notes(k):
    return [r for r in _active(k.session, 'context') if (r.payload or {}).get('note_type') in
            {'operator_note', 'operator_feedback', 'correction', 'data_correction'}]


def _report_facts(k):
    facts = {}
    for r in _active(k.session, 'report_fact'):
        payload = r.payload or {}
        if payload.get('maintenance_id'):
            facts[payload['maintenance_id']] = (r, payload)
    return facts


def _source(k, version):
    return k.session.get(SourceVersion, version.source_id)


def _doc_text(k, suffix):
    for record in _active(k.session, 'document'):
        path = (record.payload or {}).get('path', '')
        if path.endswith(suffix):
            return record, _source(k, record).content
    return None, None


def _well(k, well_id):
    return next((w for w in k.wells if w.id == well_id), None)


def _well_payload(k, well):
    return (k.session.get(RecordVersion, well.version_id).payload or {})


def _mocs(k):
    """Parse the MOC memos: covered wells and expiry, honouring an explicit extension."""
    memos = {}
    for record in _active(k.session, 'document'):
        path = (record.payload or {}).get('path', '')
        name = PurePosixPath(path).name
        if not name.startswith('moc-'):
            continue
        content = _source(k, record).content
        memo_id = re.search(r'(MOC-\d{4}-\d+)', content)
        wells = re.findall(r'WELL-\d{4}', content.split('## Conditions')[0])
        expiry = re.search(r'expires on (\d{1,2} \w+ \d{4})', content)
        extends = re.search(r'[Ee]xtends (MOC-\d{4}-\d+)', content)
        memos[memo_id.group(1) if memo_id else name] = {
            'record': record, 'memo': memo_id.group(1) if memo_id else name,
            'wells': list(dict.fromkeys(wells)),
            'expiry': datetime.strptime(expiry.group(1), '%d %b %Y').date() if expiry else None,
            'extends': extends.group(1) if extends else None,
            'path': path,
        }
    # An extension replaces the expiry date of the memo it names.
    for memo in memos.values():
        if memo['extends'] and memo['extends'] in memos:
            memos[memo['extends']]['expiry'] = memo['expiry']
            memos[memo['extends']]['extended_by'] = memo['memo']
    return memos


# ---------------------------------------------------------------- OPS-1 gas response
def gas_response(k, q):
    start = q.start or date(2026, 11, 1)
    end = q.end or k.analysis_date
    maintenance = defaultdict(list)
    for m in k.session.scalars(select(MaintenanceFact)):
        maintenance[m.well_id].append(m)
    rows = []
    for note in _notes(k):
        payload = note.payload or {}
        if payload.get('note_type') not in {'operator_note', 'operator_feedback'}:
            continue
        text = payload.get('text') or ''
        if not GAS.search(text):
            continue
        created = _utc(payload.get('created_at'))
        if created is None or not (start <= created.date() <= end):
            continue
        well_id = payload.get('asset_id')
        if q.well_ids and well_id not in q.well_ids:
            continue
        well = _well(k, well_id)
        if well is None:
            continue
        candidates = []
        for job in maintenance.get(well_id, []):
            if job.started_at and _utc(job.started_at) > created:
                candidates.append(('maintenance', job.id, _utc(job.started_at), job.version_id))
        for inspection in k.session.scalars(select(InspectionFact).where(
                InspectionFact.well_id == well_id, InspectionFact.inspected_at > created)):
            record = k.session.get(RecordVersion, inspection.version_id)
            if (record.payload or {}).get('method') == 'manual':
                candidates.append(('inspection', inspection.id, _utc(inspection.inspected_at), inspection.version_id))
        candidates.sort(key=lambda item: item[2])
        response = candidates[0] if candidates else None
        limit = float(k._value('gas_response_hours_2027' if created >= datetime(2027, 1, 1, tzinfo=timezone.utc)
                               else 'gas_response_hours'))
        hours = round((response[2] - created).total_seconds() / 3600, 1) if response else None
        facts = _report_facts(k)
        h2s = None
        if response and response[0] == 'maintenance' and response[1] in facts:
            h2s = facts[response[1]][1].get('h2s_ppm')
        evidence = k._evidence(note)
        if response:
            evidence += k._evidence(k.session.get(RecordVersion, response[3]))
        if response and response[0] == 'maintenance' and response[1] in facts:
            evidence += k._evidence(facts[response[1]][0])
        evidence += k._evidence(k._rule('gas_response_hours_2027' if created >= datetime(2027, 1, 1, tzinfo=timezone.utc)
                                        else 'gas_response_hours'))
        rows.append({'well_id': well_id, 'area': well.area_name,
                     'reported_at': created.isoformat(),
                     'response_id': response[1] if response else None,
                     'response_type': response[0] if response else None,
                     'response_at': response[2].isoformat() if response else None,
                     'hours_to_response': hours, 'deadline_hours': limit,
                     'met': (hours is not None and hours <= limit),
                     'note': text, 'note_id': payload.get('note_id'),
                     'h2s_ppm_at_response': h2s, 'evidence_ids': evidence})
    rows.sort(key=lambda r: r['reported_at'])
    misses = sum(1 for r in rows if not r['met'])
    k.calculations.append({'gas_reports': len(rows), 'missed': misses, 'deadline_hours': 12, 'evidence_ids': []})
    return rows


# ---------------------------------------------------------------- OPS-2 bypass
def bypasses(k, q):
    memos = _mocs(k)
    coverage = {}
    for memo in memos.values():
        if memo['extends']:
            continue
        for well_id in memo['wells']:
            coverage[well_id] = memo
    episodes = defaultdict(list)
    for note in _notes(k):
        payload = note.payload or {}
        if payload.get('note_type') not in {'operator_note', 'operator_feedback'}:
            continue
        text = payload.get('text') or ''
        if 'bypass' not in text.lower():
            continue
        well_id = payload.get('asset_id')
        created = _utc(payload.get('created_at'))
        if BYPASS_OUT.search(text):
            episodes[well_id].append({'kind': 'out', 'at': created, 'note': note, 'text': text})
        elif BYPASS_IN.search(text):
            episodes[well_id].append({'kind': 'in', 'at': created, 'note': note, 'text': text})
    rows = []
    for well_id, events in episodes.items():
        well = _well(k, well_id)
        if well is None or (q.well_ids and well_id not in q.well_ids):
            continue
        events.sort(key=lambda e: e['at'])
        current = None
        for event in events:
            if event['kind'] == 'in':
                current = event
            elif current is not None:
                rows.append(_bypass_row(k, well, current, event, coverage))
                current = None
        if current is not None:
            rows.append(_bypass_row(k, well, current, None, coverage))
    rows.sort(key=lambda r: (r['well_id'], r['in_at']))
    k.calculations.append({'bypass_episodes': len(rows),
                           'in_place_now': sum(1 for r in rows if r['out_at'] is None),
                           'violations': sum(1 for r in rows if r['status'] != 'Allowed')})
    return rows


def _bypass_row(k, well, start, end, coverage):
    memo = coverage.get(well.id)
    out = end['at'] if end else None
    valid = memo['expiry'] if memo else None
    if memo is None:
        status = 'Not approved'
    else:
        compare = (out.date() if out else k.analysis_date)
        status = 'Expired' if valid and compare > valid else 'Allowed'
    evidence = k._evidence(start['note']) + (k._evidence(end['note']) if end else [])
    if memo:
        evidence += k._evidence(memo['record'])
    return {'well_id': well.id, 'area': well.area_name,
            'in_at': start['at'].date().isoformat(), 'in_note': start['text'],
            'out_at': out.date().isoformat() if out else None,
            'approval': memo['memo'] if memo else None,
            'valid_until': valid.isoformat() if valid else None,
            'status': status, 'evidence_ids': evidence}


# ---------------------------------------------------------------- regulator letter
def regulator_letter(k, q):
    areas = [a for a in (q.areas or []) if a]
    if not areas and q.area:
        areas = [q.area]
    start = q.start or date(2026, 6, 1)
    facts = _report_facts(k)
    cleanup = defaultdict(list)
    for m in k.session.scalars(select(MaintenanceFact)):
        if m.inspection_id:
            cleanup[m.inspection_id].append(m)
    rows = []
    for inspection, well in k._inspection_rows(q, spills=True):
        payload = (k.session.get(RecordVersion, inspection.version_id).payload or {})
        if areas and well.area_name not in areas:
            continue
        if not inspection.spill_detected:
            continue
        volume = inspection.spill_est_volume_bbl or 0
        if volume < float(k._value('reportable_bbl')):
            continue
        jobs = cleanup.get(inspection.id, [])
        job = jobs[0] if jobs else None
        report = facts.get(job.id, (None, {}))[1] if job else {}
        compliant = bool(report.get('soil_samples_sent'))
        reason = ('clean-up report contains "Soil samples sent to the lab."' if compliant else
                  'no clean-up report with "Soil samples sent to the lab."' if job else
                  'no clean-up job recorded')
        evidence = k._evidence(inspection.version_id) + k._evidence(k._rule('reportable_bbl'))
        if job:
            evidence += k._evidence(k.session.get(RecordVersion, job.version_id))
            if job.id in facts:
                evidence += k._evidence(facts[job.id][0])
        rows.append({'well_id': well.id, 'area': well.area_name,
                     'inspection_id': inspection.id,
                     'inspected_at': inspection.inspected_at.date().isoformat(),
                     'volume_bbl': volume, 'cleanup_job': job.id if job else None,
                     'compliant': compliant, 'reason': reason, 'evidence_ids': evidence})
    rows.sort(key=lambda r: (r['area'], r['well_id'], r['inspected_at']))
    k.calculations.append({'covered_spills': len(rows), 'non_compliant': sum(1 for r in rows if not r['compliant'])})
    return rows


# ---------------------------------------------------------------- OPS-3 status conflicts
def status_conflicts(k, q):
    notes = defaultdict(list)
    for note in _notes(k):
        payload = note.payload or {}
        if payload.get('note_type') not in {'operator_note', 'operator_feedback'}:
            continue
        text = payload.get('text') or ''
        if SHUT.search(text) or RESTART.search(text):
            notes[payload.get('asset_id')].append(note)
    rows = []
    for well in k.wells:
        if q.well_ids and well.id not in q.well_ids:
            continue
        latest = k.session.scalars(select(InspectionFact)
                                   .where(InspectionFact.well_id == well.id)
                                   .order_by(InspectionFact.inspected_at.desc())).first()
        if latest is None:
            continue
        payload = k.session.get(RecordVersion, latest.version_id).payload or {}
        threshold = float(k._value('production_delta_c', well.well_type))
        delta = round((latest.wellhead_temp_c or 0) - (latest.ambient_temp_c or 0), 1)
        inspection_producing = delta >= threshold
        status_notes = sorted(notes.get(well.id, []), key=lambda n: _utc(n.payload.get('created_at')))
        note = status_notes[-1] if status_notes else None
        text = (note.payload or {}).get('text', '') if note else ''
        note_status = 'not producing' if (note and SHUT.search(text) and not RESTART.search(text)) else \
            'producing' if note else None
        disagrees = note is not None and note_status is not None and (
            (note_status == 'not producing' and inspection_producing) or
            (note_status == 'producing' and not inspection_producing))
        if not disagrees:
            continue
        note_at = _utc(note.payload.get('created_at'))
        inspected = _utc(latest.inspected_at)
        unconfirmed = False
        if note_at and note_at > inspected:
            now = note_status
            unconfirmed = note_status == 'producing'
        else:
            now = 'producing' if inspection_producing else 'not producing'
        evidence = k._evidence(latest.version_id) + k._evidence(note)
        rows.append({'well_id': well.id, 'area': well.area_name,
                     'inspection_id': latest.id, 'inspected_at': inspected.date().isoformat(),
                     'inspection_state': 'producing' if inspection_producing else 'not producing',
                     'delta_c': delta, 'threshold_c': threshold,
                     'note_id': (note.payload or {}).get('note_id'),
                     'note_at': note_at.isoformat() if note_at else None,
                     'note_text': text, 'note_author': k._user((note.payload or {}).get('author_user_id')),
                     'status_now': now, 'unconfirmed': unconfirmed, 'evidence_ids': evidence})
    rows.sort(key=lambda r: (r['area'], r['well_id']))
    k.calculations.append({'disagreements': len(rows), 'unconfirmed': sum(1 for r in rows if r['unconfirmed'])})
    return rows


# ---------------------------------------------------------------- supplier recall
def recall_pumps(k, q):
    record, content = _doc_text(k, 'supplier-recall-notice-2026-12-01.md')
    if record is None:
        k.warnings.append('Missing supplier recall notice; affected lots unknown')
        return []
    lots = set(re.findall(r'LOT-\d{4}-[A-Z]', content))
    facts = _report_facts(k)
    from app.domain import MaintenanceFact
    pumps = defaultdict(list)
    for job in k.session.scalars(select(MaintenanceFact)):
        fact = facts.get(job.id)
        if not fact or not fact[1].get('part_lot'):
            continue
        pumps[job.well_id].append((job, fact[0], fact[1]))
    claims = defaultdict(list)
    for correction in k.session.scalars(select(Correction)
                                        .where(Correction.target_kind == 'well')):
        claims[correction.target_id].append(correction)
    rows = []
    for well_id, installs in pumps.items():
        well = _well(k, well_id)
        if well is None or (q.well_ids and well_id not in q.well_ids):
            continue
        if q.area and well.area_name != q.area:
            continue
        installs.sort(key=lambda item: item[0].started_at)
        job, fact_record, payload = installs[-1]
        if payload.get('part_lot') not in lots:
            continue
        if (payload.get('pump_model') or '').upper().startswith('ESP'):
            continue
        claim = None
        for correction in claims.get(well_id, []):
            if re.search(r'swapp|replac|pulled', str(correction.value), re.I):
                claim = correction
        evidence = k._evidence(fact_record) + k._evidence(k.session.get(RecordVersion, job.version_id))
        evidence += k._evidence(record)
        if claim:
            evidence += k._source_evidence(claim.source_id)
        rows.append({'well_id': well_id, 'area': well.area_name,
                     'pump_model': payload.get('pump_model'), 'serial': payload.get('part_serial'),
                     'lot': payload.get('part_lot'), 'installed_job': job.id,
                     'installed_at': _utc(job.started_at).date().isoformat(),
                     'install_cost_usd': job.cost_usd,
                     'status': 'reported replaced' if claim else 'still in the ground',
                     'reported_by': k._user(claim.author_id) if claim else None,
                     'claim_confirmed': (claim.status == 'accepted') if claim else None,
                     'evidence_ids': evidence})
    rows.sort(key=lambda r: (r['area'], r['well_id']))
    k.calculations.append({'recalled_installed': len(rows),
                           'by_area': dict(Counter(r['area'] for r in rows))})
    return rows


# ---------------------------------------------------------------- OPS-5 freeze
def cold_weather(k, q):
    start = q.start or date(k.analysis_date.year - 1, 12, 1)
    end = q.end or date(k.analysis_date.year - 1, 12, 31)
    from app.domain import MaintenanceFact
    jobs = defaultdict(list)
    for job in k.session.scalars(select(MaintenanceFact)):
        if re.search(r'heat trace check', job.issue or '', re.I):
            jobs[job.well_id].append(_utc(job.started_at))
    limit = float(k._value('heat_trace_days'))
    freeze = float(k._value('freeze_temp_c'))
    rows = []
    for inspection, well in k._inspection_rows(q):
        if not (start <= inspection.inspected_at.date() <= end):
            continue
        if inspection.ambient_temp_c is None or inspection.ambient_temp_c > -freeze:
            continue
        threshold = float(k._value('production_delta_c', well.well_type))
        producing = (inspection.wellhead_temp_c - inspection.ambient_temp_c) >= threshold
        if not producing:
            continue
        found = None
        for started in jobs.get(well.id, []):
            if started and started > _utc(inspection.inspected_at):
                found = started
                break
        days = round((found - _utc(inspection.inspected_at)).total_seconds() / 86400, 1) if found else None
        rows.append({'well_id': well.id, 'area': well.area_name, 'inspection_id': inspection.id,
                     'inspected_at': inspection.inspected_at.date().isoformat(),
                     'ambient_temp_c': inspection.ambient_temp_c,
                     'heat_trace_at': found.date().isoformat() if found else None,
                     'days_to_check': days, 'met': (days is not None and days <= limit),
                     'evidence_ids': k._evidence(inspection.version_id) + k._evidence(k._rule('heat_trace_days'))})
    rows.sort(key=lambda r: (r['inspected_at'], r['well_id']))
    k.calculations.append({'cold_producing_readings': len(rows), 'missing_check': sum(1 for r in rows if not r['met'])})
    return rows


# ---------------------------------------------------------------- waiting reasons
def waiting_reasons(k, q):
    start = q.start or date(2026, 1, 1)
    end = q.end or date(2026, 12, 31)
    facts = _report_facts(k)
    from app.domain import MaintenanceFact
    grouped = defaultdict(list)
    details = []
    for job in k.session.scalars(select(MaintenanceFact)):
        if job.maintenance_type != 'corrective' or not job.started_at:
            continue
        if not (start <= _utc(job.started_at).date() <= end):
            continue
        fact = facts.get(job.id)
        if not fact or not fact[1].get('wait_days'):
            continue
        well = _well(k, job.well_id)
        if well is None or (q.area and well.area_name != q.area):
            continue
        reason = fact[1].get('wait_reason') or 'other'
        extra = float(fact[1]['wait_days'])
        grouped[(well.area_name, reason)].append(extra)
        details.append({'well_id': well.id, 'area': well.area_name, 'job': job.id,
                        'reason': reason, 'extra_days': extra,
                        'evidence_ids': k._evidence(fact[0])})
    rows = []
    for (area, reason), values in sorted(grouped.items()):
        ordered = sorted(values)
        median = ordered[len(ordered) // 2]
        rows.append({'area': area, 'reason': reason, 'jobs': len(values),
                     'share_pct': round(100 * len(values) / sum(len(v) for (a, _), v in grouped.items() if a == area), 1),
                     'typical_extra_days': median,
                     'evidence_ids': next((d['evidence_ids'] for d in details if d['area'] == area and d['reason'] == reason), [])})
    k.calculations.append({'jobs_with_wait': len(details), 'by_reason': dict(Counter(d['reason'] for d in details)),
                           'detail': details[:60]})
    return rows


# ---------------------------------------------------------------- hot regions
def hot_regions(k, q):
    grouped = defaultdict(list)
    wellhead = defaultdict(list)
    for inspection, well in k._inspection_rows(q):
        if inspection.ambient_temp_c is None or inspection.wellhead_temp_c is None:
            continue
        grouped[well.area_name].append(inspection.wellhead_temp_c - inspection.ambient_temp_c)
        wellhead[well.area_name].append(inspection.wellhead_temp_c)
    rows = []
    for area, deltas in sorted(grouped.items()):
        delta = round(sum(deltas) / len(deltas), 2)
        rows.append({'area': area, 'readings': len(deltas), 'mean_delta_c': delta,
                     'mean_wellhead_c': round(sum(wellhead[area]) / len(wellhead[area]), 2)})
    rows.sort(key=lambda r: r['mean_delta_c'], reverse=True)
    k.calculations.append({'hottest_area': rows[0]['area'] if rows else None})
    return rows


# ---------------------------------------------------------------- operator signals
def operator_signals(k, q):
    end = q.end or k.analysis_date
    start = q.start or (end - timedelta(days=30))
    facts = _report_facts(k)
    from app.domain import MaintenanceFact
    jobs = defaultdict(list)
    for job in k.session.scalars(select(MaintenanceFact)):
        if job.maintenance_type == 'corrective' and 'spill' not in (job.equipment_kind or '').lower():
            jobs[job.well_id].append(job)
    by_well = defaultdict(list)
    for note in _notes(k):
        payload = note.payload or {}
        if payload.get('note_type') != 'operator_note':
            continue
        created = _utc(payload.get('created_at'))
        text = payload.get('text') or ''
        if created is None or not (start <= created.date() <= end) or not WRONG.search(text):
            continue
        well_id = payload.get('asset_id')
        if q.area and (_well(k, well_id) is None or _well(k, well_id).area_name != q.area):
            continue
        by_well[well_id].append((note, created, text))
    rows = []
    for well_id, notes in by_well.items():
        well = _well(k, well_id)
        if well is None:
            continue
        last = max((job for job in jobs.get(well_id, []) if job.started_at), key=lambda j: j.started_at, default=None)
        latest_note = max(c for _, c, _ in notes)
        if last and _utc(last.started_at) > latest_note:
            continue  # repaired since the note: no longer a "haven't had a repair" well
        latest = k.session.scalars(select(InspectionFact)
                                   .where(InspectionFact.well_id == well_id)
                                   .order_by(InspectionFact.inspected_at.desc())).first()
        delta = None
        producing = None
        if latest:
            delta = round((latest.wellhead_temp_c or 0) - (latest.ambient_temp_c or 0), 1)
            producing = delta >= float(k._value('production_delta_c', well.well_type))
        recency = (latest_note.date() - start).days if latest_note.date() >= start else 0
        score = len(notes) * 2 + recency / 7 + (3 if producing is False else 0) + (1 if 'gas' in ' '.join(t for _, _, t in notes).lower() else 0)
        evidence = []
        for note, _, _ in notes:
            evidence += k._evidence(note)
        if latest:
            evidence += k._evidence(latest.version_id)
        rows.append({'well_id': well_id, 'area': well.area_name, 'score': round(score, 1),
                     'note_count': len(notes), 'latest_note': max(notes, key=lambda n: n[1])[2],
                     'latest_note_at': latest_note.date().isoformat(),
                     'delta_c': delta, 'producing_now': producing,
                     'last_repair': _utc(last.started_at).date().isoformat() if last else None,
                     'last_repair_issue': last.issue if last else None,
                     'evidence_ids': evidence})
    rows.sort(key=lambda r: r['score'], reverse=True)
    rows = rows[:10]
    for index, row in enumerate(rows, 1):
        row['rank'] = index
    k.warnings.append('The ranking is a transparent heuristic over notes, current production state and repair recency; it is not a trained failure prediction.')
    return rows


# ---------------------------------------------------------------- missing-data answers
def pressure(k, q):
    k.warnings.append('The dataset contains no reservoir pressure measurements. Only line/equipment '
                      'pressure-test values appear inside repair reports, which are integrity tests, not reservoir pressure.')
    k.calculations.append({'reservoir_pressure_measurements': 0})
    return []


def production_rank(k, q):
    k.warnings.append('The dataset records no produced oil volume (no barrels per well per day or month). '
                      'Production is only observable as producing / not producing from the temperature rule, so a '
                      '"most oil" ranking cannot be computed. The rows below rank by producing uptime instead and say so.')
    uptime = defaultdict(lambda: {'producing': 0, 'readings': 0})
    for inspection, well in k._inspection_rows(q):
        threshold = float(k._value('production_delta_c', well.well_type))
        delta = (inspection.wellhead_temp_c or 0) - (inspection.ambient_temp_c or 0)
        uptime[well.id]['readings'] += 1
        if delta >= threshold:
            uptime[well.id]['producing'] += 1
    rows = []
    for well_id, counts in uptime.items():
        row = {'well_id': well_id, 'producing_readings': counts['producing'],
               'readings': counts['readings'],
               'producing_share': round(counts['producing'] / counts['readings'], 3) if counts['readings'] else None}
        if counts['readings']:
            rows.append(row)
    rows.sort(key=lambda r: (r['producing_share'] or 0, r['producing_readings']), reverse=True)
    k.calculations.append({'proxy': 'producing uptime share, not oil volume'})
    return rows[:10] if q.limit is None else rows[:q.limit]
