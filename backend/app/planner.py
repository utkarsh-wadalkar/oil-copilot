"""Transparent deterministic domain planner.

Used when no model is configured and as a grounded fallback. It maps common asset
questions to the strict :class:`~app.domain.QuerySpec` operations, resolves
relative business periods against the latest observed data day, and prepares
(non-publishing) feedback drafts. It never hardcodes scenario answers or specific
well result lists.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select

from app.domain import InspectionFact, WellFact
from app.knowledge import months_before

WELL_RE = re.compile(r'\bWELL-\d{4,}\b', re.I)
INSPECTION_RE = re.compile(r'\bINS-\d{4,}-\d{4,}\b', re.I)
NUMBER_WORDS = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6,
                'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10}
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
#: A question about downtime that has not happened yet. "Is any downtime planned for WELL-0007?"
#: asks about the near future, so answering it with a history of downtime days would be misleading.
PLANNED_RE = re.compile(
    r'\b(?:planned|planning|scheduled|scheduling|upcoming|forthcoming|future|'
    r'will\s+be|going\s+to\s+be|about\s+to|next\s+(?:week|month|quarter|year)|tomorrow)\b', re.I)


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
    """Resolve a relative business period.

    Calendar units (year, month, quarter, day) end *today* (the analysis date), because
    that is how people state them. A count of weeks is a count of weekly records, so it
    ends at the latest observation instead: "the last 13 weeks" means the last 13
    inspections, not 13 weeks of an empty future.
    """
    lowered = text.lower()
    if re.search(r'\bthis\s+year\b|\byear\s+to\s+date\b|\bytd\b', lowered):
        return date(analysis.year, 1, 1), analysis
    if re.search(r'\bthis\s+month\b', lowered):
        return analysis.replace(day=1), analysis
    if re.search(r'\bthis\s+quarter\b', lowered):
        first = (analysis.month - 1) // 3 * 3 + 1
        return date(analysis.year, first, 1), analysis
    match = re.search(r'(?:last|past|previous)\s+(\d+)\s+(year|month|week|day)s?', lowered)
    if match:
        count, unit = int(match.group(1)), match.group(2)
        if unit == 'year':
            return date(analysis.year - count, analysis.month, min(analysis.day, 28)), analysis
        if unit == 'month':
            return months_before(analysis, count), analysis
        if unit == 'week':
            return end - timedelta(days=(count - 1) * 7), end
        return analysis - timedelta(days=count - 1), analysis
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
    asks_procedure = re.search(r'what should we do|next step|guidance|procedure|what do we do|'
                               r'what does the .*sop|per the .*sop|sop say', lowered)
    asks_data = re.search(r'\bwhich\b|\bhow many\b|\blist\b|\bwere not\b|\bdid not\b', lowered)
    # "contained within the SOP time limit" is a data question; a bare mention of the SOP
    # must not route it to the procedure library.
    if asks_procedure and not asks_data:
        return 'guidance'
    if re.search(r'contain(?:ed|ment)', lowered):
        return 'containment'
    if re.search(r'root.?cause|rca', lowered):
        return 'rca'
    if re.search(r'contain(?:ed|ment)', lowered):
        return 'containment'
    if re.search(r'rule', lowered) and re.search(r'br(?:oke|eak)|violat|compliance|fine|open', lowered):
        return 'compliance'
    if re.search(r'cost|spent|repair', lowered):
        return 'maintenance'
    if re.search(r'down|downtime|shut.?in', lowered):
        # A planned/future outage is a state question, not a history question: read the well's
        # recorded state and any attributed plan instead of reporting historical downtime days.
        return 'status' if PLANNED_RE.search(lowered) else 'downtime'
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


def _parse_day(text: str, analysis: date):
    """The calendar day named in a correction, as a date in the analysis year."""
    dmy = DMY_RE.search(text)
    if dmy:
        return date(int(dmy.group(3)), MONTHS[dmy.group(2).lower()[:3]], int(dmy.group(1)))
    dm = DM_RE.search(text)
    if dm:
        try:
            return date(analysis.year, MONTHS[dm.group(2).lower()[:3]], int(dm.group(1)))
        except ValueError:
            return None
    return None


def _resolve_inspection(session, well: str, text: str, analysis: date) -> str | None:
    """The inspection a correction refers to: an explicit ID, a named day, or "latest"."""
    explicit = INSPECTION_RE.search(text)
    if explicit:
        return explicit.group(0).upper()
    stmt = select(InspectionFact).where(InspectionFact.well_id == well)
    day = _parse_day(text, analysis)
    if day is not None:
        stmt = stmt.where(InspectionFact.inspected_at >= datetime.combine(day, time.min),
                          InspectionFact.inspected_at < datetime.combine(day + timedelta(days=1), time.min))
        row = session.scalars(stmt.order_by(InspectionFact.inspected_at.desc())).first()
        return row.id if row else None
    if re.search(r'latest|last (?:reading|inspection)|most recent|that inspection|this inspection', text, re.I):
        row = session.scalars(stmt.order_by(InspectionFact.inspected_at.desc())).first()
        return row.id if row else None
    return None


def _measured_value(text: str):
    """The value the speaker is asserting, preferring an explicit re-measurement.

    "The AI estimated 4.5 bbl; the field crew measured 5.4 bbl" corrects to 5.4. The
    first number is the old estimate, kept only for reference.
    """
    pattern = re.compile(r'(\d+(?:\.\d+)?)\s*(°c|c\b|bbl|barrels?|%|percent)', re.I)
    matches = list(pattern.finditer(text))
    if not matches:
        return None, None
    measured = re.search(r're-?measur|measured|actual|field crew|correct(?:ed|ion)?\s+(?:value|to)', text, re.I)
    chosen = matches[-1] if measured and len(matches) > 1 else matches[0]
    unit = chosen.group(2).lower()
    unit = 'C' if unit.startswith('c') or unit.startswith('°') else '%' if unit.startswith('p') else 'bbl'
    return float(chosen.group(1)), unit


def parse_feedback(text: str, context):
    """Return a draft specification when the message is a feedback assertion."""
    lowered = text.lower()
    session = context.get('session')
    analysis = context.get('analysis') or date.today()
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
    numeric = _measured_value(text)
    wants_correction = re.search(r'\bwrong|incorrect|faulty|re-?measur|mismeasur|actually|should be|correct', lowered)
    restated = (re.search(r'\b(?:estimated|estimate|ai)\b', lowered)
                and re.search(r'\b(?:measured|field crew|actual)\b', lowered))
    wants_claim = re.search(r'running fine|is back online|back online|has been shut|shut in for|is operating', lowered)
    if (wants_correction or restated) and well:
        field, unit = None, None
        for token, (name, u) in FEEDBACK_FIELDS.items():
            if token in lowered:
                field, unit = name, u
                break
        if field is None and numeric[0] is not None:
            field, unit = 'wellhead_temp_c', numeric[1]
        value, parsed_unit = numeric
        target = _resolve_inspection(session, well, text, analysis) if session is not None else None
        return {'kind': 'correction', 'target_id': target, 'well_id': well, 'field': field,
                'value': value if value is not None else None, 'unit': unit or parsed_unit,
                'reason': text.strip(), 'excused_day': _extract_day(text),
                'missing': [] if (field and value is not None) else ['field' if not field else 'value']}
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
    context = {'analysis': analysis, 'data_end': end, 'areas': areas, 'session': session,
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
        counted = re.search(r'\b(?:the\s+)?(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+wells?\b', lowered)
        if counted:
            token = counted.group(1)
            recall['count'] = int(token) if token.isdigit() else NUMBER_WORDS[token]
        plan_out['recall'] = recall
        # The wells are named in an earlier conversation, not in this message: the caller must
        # resolve them before running any query, and must never widen to the whole fleet instead.
        plan_out['requires_recall'] = not wells and not area

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
