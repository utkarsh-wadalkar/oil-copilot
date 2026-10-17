"""Transparent deterministic domain planner.

Used when no model is configured and as a grounded fallback. It maps common asset
questions to the strict :class:`~app.domain.QuerySpec` operations, resolves
relative business periods against the latest observed data day, and prepares
(non-publishing) feedback drafts. It never hardcodes scenario answers or specific
well result lists.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from sqlalchemy import func, select

from app.domain import InspectionFact, WellFact
from app.knowledge import months_before

WELL_RE = re.compile(r'\bWELL-\d{4,}\b', re.I)
ISO_RE = re.compile(r'\b(\d{4})-(\d{2})-(\d{2})\b')
DMY_RE = re.compile(r'\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{4})\b', re.I)
DM_RE = re.compile(r'\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\b', re.I)
MONTHS = {m: i for i, m in enumerate(
    ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'], start=1)}
VISUALS = {'card': 'card', 'table': 'table', 'line chart': 'line', 'line graph': 'line', 'bar chart': 'bar',
           'bar graph': 'bar', 'map': 'map', 'heatmap': 'heatmap', 'heat map': 'heatmap'}
FEEDBACK_FIELDS = {
    'wellhead': ('wellhead_temp_c', 'C'), 'well head': ('wellhead_temp_c', 'C'),
    'ambient': ('ambient_temp_c', 'C'), 'spill volume': ('spill_est_volume_bbl', 'bbl'),
    'barrels': ('spill_est_volume_bbl', 'bbl'), 'bbl': ('spill_est_volume_bbl', 'bbl'),
    'spill area': ('spill_area_pct', '%'), 'area percent': ('spill_area_pct', '%'),
}


def data_end(session, fallback: date) -> date:
    latest = session.scalar(select(func.max(InspectionFact.inspected_at)))
    return latest.date() if latest else fallback


def known_areas(session) -> dict[str, str]:
    return {name.lower(): name for name in session.scalars(select(WellFact.area_name).distinct())}


def known_well_types(session) -> set[str]:
    return set(session.scalars(select(WellFact.well_type).distinct()))


def _find_area(text: str, areas: dict[str, str]) -> str | None:
    lowered = text.lower()
    for name, canonical in areas.items():
        if name in lowered:
            return canonical
    return None


def _relative_period(text: str, analysis: date, end: date):
    lowered = text.lower()
    match = re.search(r'(?:last|past|previous)\s+(\d+)\s+(year|month|week|day)s?', lowered)
    if match:
        count, unit = int(match.group(1)), match.group(2)
        if unit == 'year':
            return date(end.year - count, end.month, min(end.day, 28)), end
        if unit == 'month':
            return months_before(end, count), end
        if unit == 'week':
            return end - timedelta(days=(count - 1) * 7), end
        return end - timedelta(days=count - 1), end
    year = re.search(r'\b(20\d{2})\b', lowered)
    if year:
        y = int(year.group(1))
        return date(y, 1, 1), date(y, 12, 31)
    # A bare day-month such as "24 Sep" for the analysis year.
    dm = DM_RE.search(text)
    if dm and not re.search(r'20\d{2}', dm.group(0)):
        day, month = int(dm.group(1)), MONTHS[dm.group(2).lower()[:3]]
        try:
            value = date(analysis.year, month, day)
        except ValueError:
            return None, None
        return value, value
    return None, None


def _explicit_dates(text: str):
    iso = ISO_RE.findall(text)
    if iso:
        dates = [date(int(y), int(m), int(d)) for y, m, d in iso]
        return min(dates), max(dates)
    dmy = DMY_RE.search(text)
    if dmy:
        value = date(int(dmy.group(3)), MONTHS[dmy.group(2).lower()[:3]], int(dmy.group(1)))
        return value, value
    return None, None


def _visual(text: str):
    lowered = text.lower()
    for phrase in sorted(VISUALS, key=len, reverse=True):
        if phrase in lowered:
            return VISUALS[phrase]
    return None


def classify(text: str) -> str:
    lowered = text.lower()
    if re.search(r'what should we do|next step|guidance|procedure|sop|what do we do', lowered):
        return 'guidance'
    if re.search(r'root.?cause|rca', lowered):
        return 'rca'
    if re.search(r'contain(?:ed|ment)', lowered):
        return 'containment'
    if re.search(r'rule', lowered) and re.search(r'br(?:oke|eak)|violat|compliance|fine|open', lowered):
        return 'compliance'
    if re.search(r'cost|spent|repair', lowered):
        return 'maintenance'
    if re.search(r'down|downtime|shut.?in', lowered):
        return 'downtime'
    if re.search(r'spill|barrel|leak|oil sheen', lowered):
        return 'spills'
    if re.search(r'temperature|thermal|line chart', lowered):
        return 'temperatures'
    if re.search(r'produc|status|inspected|who inspected|running', lowered):
        return 'status'
    if re.search(r'note|fyi|planned', lowered):
        return 'notes'
    if re.search(r'compliance|breach|protocol|notice', lowered):
        return 'compliance'
    return 'status'


def parse_feedback(text: str, context):
    """Return a draft specification when the message is a feedback assertion."""
    lowered = text.lower()
    well = (WELL_RE.search(text).group(0).upper() if WELL_RE.search(text) else None)
    if re.search(r'\bfyi\b', lowered):
        return {'kind': 'note', 'target_id': well, 'field': 'text', 'value': text.strip(),
                'reason': 'Shared note from conversation', 'missing': [] if well else ['well_id']}
    if re.search(r'now wants|team now wants|we now want|should be changed', lowered):
        rule = re.search(r'after\s+(\d+)\s+repairs', lowered)
        well_type = next((t for t in context['well_types'] if t.lower() in lowered), None)
        equipment = next((e for e in ('pump_jack', 'flowline', 'prime_mover', 'stuffing_box') if e.replace('_', ' ') in lowered), None)
        missing = []
        if not well_type:
            missing.append('well_type')
        if not rule:
            missing.append('threshold')
        if not equipment:
            missing.append('equipment_kind')
        return {'kind': 'rule', 'target_id': well_type, 'field': 'rca_threshold',
                'value': int(rule.group(1)) if rule else None, 'equipment_kind': equipment,
                'reason': text.strip(), 'missing': missing, 'apply_to': 'well_type'}
    numeric = re.search(r'(\d+(?:\.\d+)?)\s*(°c|c\b|bbl|barrels?|%|percent)', lowered)
    wants_correction = re.search(r'\bwrong|incorrect|faulty|re-?measur|mismeasur|actually|should be|correct', lowered)
    wants_claim = re.search(r'running fine|is back online|back online|has been shut|shut in for|is operating', lowered)
    if wants_correction and well:
        field, unit = None, None
        for token, (name, u) in FEEDBACK_FIELDS.items():
            if token in lowered:
                field, unit = name, u
                break
        if field is None and numeric:
            field, unit = 'wellhead_temp_c', 'C' if numeric.group(2).startswith('c') else 'bbl'
        return {'kind': 'correction', 'target_id': None, 'well_id': well, 'field': field,
                'value': float(numeric.group(1)) if numeric else None, 'unit': unit,
                'reason': text.strip(), 'excused_day': _extract_day(text),
                'missing': [] if (field and numeric) else ['field' if not field else 'value']}
    if wants_claim and well:
        return {'kind': 'claim', 'target_id': well, 'well_id': well, 'field': 'text',
                'value': text.strip(), 'reason': 'Operator claim from conversation', 'missing': []}
    if well and re.search(r'sensor|data|reading|value', lowered) and re.search(r'wrong|bad|off|issue|problem', lowered):
        return {'kind': 'correction', 'target_id': None, 'well_id': well, 'field': None, 'value': None,
                'reason': text.strip(), 'missing': ['inspection_or_interval', 'field', 'value', 'unit', 'reason']}
    return None


def _extract_day(text: str):
    dmy = DMY_RE.search(text)
    if dmy:
        return date(int(dmy.group(3)), MONTHS[dmy.group(2).lower()[:3]], int(dmy.group(1)))
    dm = DM_RE.search(text)
    if dm:
        return (int(dm.group(1)), MONTHS[dm.group(2).lower()[:3]])
    return None


def plan(question: str, session, analysis: date) -> dict:
    """Return {queries, feedback, recall, visual, offline} for a question."""
    end = data_end(session, analysis)
    areas = known_areas(session)
    context = {'analysis': analysis, 'data_end': end, 'areas': areas,
               'well_types': known_well_types(session)}
    lowered = question.lower()
    visual = _visual(question)
    wells = [w.upper() for w in WELL_RE.findall(question)]
    area = _find_area(question, areas)
    plan_out = {'queries': [], 'feedback': None, 'recall': None, 'visual': visual, 'offline': True}

    recall = None
    if re.search(r'we discussed|discussed (?:yesterday|earlier|before|last)|previous|those wells|the three wells|the \w+ wells we|earlier conversation', lowered):
        when = None
        rel = re.search(r'(\d+)\s+days?\s+ago', lowered)
        if 'yesterday' in lowered:
            when = analysis - timedelta(days=1)
        elif rel:
            when = analysis - timedelta(days=int(rel.group(1)))
        recall = {'text': question, 'wells': wells or None, 'day': when}
        plan_out['recall'] = recall

    feedback = parse_feedback(question, context)
    if feedback:
        plan_out['feedback'] = feedback
        return plan_out

    has_question = bool(re.search(r'\?|how many|which|what|when|show|list|give|is |are |tell', lowered))
    if not has_question and recall:
        return plan_out

    operation = classify(question)
    start, end_period = _relative_period(question, analysis, end)
    explicit_start, explicit_end = _explicit_dates(question)
    if explicit_start:
        start, end_period = explicit_start, explicit_end
    if start is None and operation == 'temperatures':
        count = re.search(r'last\s+(\d+)\s+(?:week|reading)', lowered)
        start = end - timedelta(days=(int(count.group(1)) - 1) * 7) if count else None

    query = {'operation': operation}
    if wells:
        query['well_ids'] = wells
    if area:
        query['area'] = area
    if start:
        query['start'] = start.isoformat()
    if end_period:
        query['end'] = end_period.isoformat()
    if operation == 'status' and re.search(r'not producing|are not|which wells|who is not', lowered):
        query['producing'] = False
    if operation == 'spills' and re.search(r'reportable|report to', lowered):
        query['reportable_only'] = True
    if visual:
        query['visual'] = visual
    limit = re.search(r'top\s+(\d+)|which\s+(\d+)|the\s+(\d+)\s+wells', lowered)
    if limit:
        query['limit'] = int(next(g for g in limit.groups() if g))
    if operation in {'rca'}:
        equipment = next((e for e in ('pump_jack', 'flowline', 'prime_mover', 'stuffing_box')
                          if e.replace('_', ' ') in lowered), None)
        if equipment:
            query['equipment_kind'] = equipment
    if operation == 'guidance':
        query['query'] = question
    if operation == 'documents':
        query['query'] = question
    plan_out['queries'] = [query]
    return plan_out
