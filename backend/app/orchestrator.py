"""Conversation orchestration, grounded answer composition and feedback drafts.

The model (when configured) only chooses tools; the authoritative content is always
recomputed from PostgreSQL via :class:`~app.knowledge.AssetKnowledge`. Feedback is a
prepare/confirm workflow: chat and HTTP never publish a correction directly.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, or_, select

from app import planner
from app.config import Settings, get_settings
from app.domain import (FeedbackSpec, InspectionFact, MaintenanceFact, Operation, QuerySpec,
                        RegulatorFact, WellFact)
from app.knowledge import AssetKnowledge, utc
from app.models import (ActiveRecord, Conversation, Correction, FeedbackDraft, Message, MessageRequest,
                        RecordVersion, ResultMeta, Rule, SavedResult, SourceVersion, new_id, now_utc)
from app.provider import OllamaProvider, ProviderError, ProviderRateLimited, ProviderUnavailable
from app.schemas import AnswerEnvelope, EvidenceRef, Finding, VisualSpec

TOOL_SCHEMAS = [
    {'type': 'function', 'function': {
        'name': 'asset_query',
        'description': 'Run a validated analytics query over authoritative oil-well records and rules.',
        'parameters': {'type': 'object', 'properties': {
            'operation': {'type': 'string', 'enum': [op.value for op in Operation]},
            'well_ids': {'type': 'array', 'items': {'type': 'string'}},
            'area': {'type': 'string'},
            'start': {'type': 'string', 'description': 'ISO date'},
            'end': {'type': 'string', 'description': 'ISO date'},
            'equipment_kind': {'type': 'string'},
            'limit': {'type': 'integer'},
            'producing': {'type': 'boolean'},
            'reportable_only': {'type': 'boolean'},
            'query': {'type': 'string'},
            'visual': {'type': 'string', 'enum': ['text', 'card', 'table', 'line', 'bar', 'map', 'heatmap']},
        }, 'required': ['operation']}}},
    {'type': 'function', 'function': {
        'name': 'recall_results',
        'description': 'Recall this user\'s earlier saved results (private history) to resolve references.',
        'parameters': {'type': 'object', 'properties': {
            'query': {'type': 'string'}, 'well_ids': {'type': 'array', 'items': {'type': 'string'}},
            'start': {'type': 'string'}, 'end': {'type': 'string'}, 'limit': {'type': 'integer'}}}}},
    {'type': 'function', 'function': {
        'name': 'propose_feedback',
        'description': ('Prepare (never publish) a correction, rule change, note or claim for human confirmation. '
                        'Call asset_query first to resolve the exact record id; never guess one.'),
        'parameters': {'type': 'object', 'properties': {
            'kind': {'type': 'string', 'enum': ['correction', 'rule', 'note', 'claim']},
            'target_id': {'type': 'string',
                          'description': ('Exact record id the change applies to. For a correction this is an '
                                          'inspection id such as INS-0164-0205 (never a well id); for a repair it '
                                          'is a maintenance id such as MNT-0001-032.')},
            'well_id': {'type': 'string', 'description': 'Well id such as WELL-0164. Required for well-scoped notes, '
                                                         'claims and rule changes.'},
            'field': {'type': 'string',
                      'description': ('Field being corrected, e.g. wellhead_temp_c, ambient_temp_c, '
                                      'spill_est_volume_bbl, spill_detected. Required for kind=correction.')},
            'value': {'description': 'Replacement value with the unit the field uses.'},
            'unit': {'type': 'string'},
            'equipment_kind': {'type': 'string', 'description': 'Required for a rule change about one equipment kind.'},
            'reason': {'type': 'string', 'description': 'Why the stored value is wrong, in the user\'s words.'},
            'valid_from': {'type': 'string'}, 'valid_to': {'type': 'string'},
        }, 'required': ['kind']}}},
]

SYSTEM_PROMPT = (
    'You are the Asset Intelligence Copilot for an oil-well fleet. Use the provided tools to answer. '
    'Never invent facts, numbers, wells or citations: every figure must come from an asset_query result. '
    'Rules and thresholds live in well-type manuals and SOPs; asset_query already applies them. '
    'To refer to earlier discussion, call recall_results (private to the current user). '
    'To change any stored value you MUST call propose_feedback; a human confirms it later. '
    'Prefer precise, source-backed answers and choose the requested visualisation via the visual field.'
)


class ModelPending(RuntimeError):
    """Raised when the model is rate limited and the request should be retried."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


def _now_iso() -> str:
    return now_utc().isoformat()


class Orchestrator:
    def __init__(self, session, provider=None, memory=None, graph=None, settings: Settings | None = None,
                 clock=None):
        self.session = session
        self.settings = settings or get_settings()
        self.provider = provider if provider is not None else OllamaProvider(self.settings)
        self.memory = memory
        self.graph = graph
        self.clock = clock or (lambda: now_utc())

    # -- public entrypoint -------------------------------------------------
    def answer(self, user_id: str, conversation_id: str, content: str, analysis_date: date | None = None,
               client_message_id: str | None = None) -> dict:
        analysis_date = analysis_date or self._default_analysis_date()
        knowledge = AssetKnowledge(self.session, analysis_date)
        draft_payload = None
        warnings: list[str] = []
        recall_note = None
        envelopes: list[dict] = []
        tool_trace: list[dict] = []

        if self.provider and getattr(self.provider, 'configured', False):
            try:
                envelopes, draft_payload, recall_note, tool_trace, warnings = self._run_tool_loop(
                    user_id, conversation_id, content, analysis_date, knowledge)
            except ModelPending:
                raise
            except (ProviderUnavailable, ProviderError):
                warnings.append('Model unavailable; used the deterministic offline planner.')
                envelopes, draft_payload, recall_note = self._run_offline(
                    user_id, conversation_id, content, analysis_date, knowledge)
        else:
            warnings.append('No model credentials configured; using the deterministic offline planner.')
            envelopes, draft_payload, recall_note = self._run_offline(
                user_id, conversation_id, content, analysis_date, knowledge)

        envelope = self._compose(content, analysis_date, envelopes, draft_payload, recall_note, warnings,
                                 tool_trace)
        result = SavedResult(conversation_id=conversation_id, user_id=user_id, question=content,
                             payload={})
        self.session.add(result)
        self.session.flush()
        envelope['result_id'] = result.id
        # A fresh dict (not an in-place mutation) so the id is actually persisted.
        result.payload = dict(envelope)
        self.session.flush()
        self._save_meta(user_id, result, envelope, envelopes, analysis_date)
        if draft_payload is not None and draft_payload.get('id'):
            draft = self.session.get(FeedbackDraft, draft_payload['id'])
            if draft is not None and draft.conversation_id is None:
                draft.conversation_id = conversation_id
        from app.worker import enqueue_result

        enqueue_result(self.session, result.id)
        self.session.flush()
        status = 'pending_confirmation' if (draft_payload and draft_payload.get('status') == 'pending') else 'complete'
        return {'status': status, 'envelope': envelope, 'draft': _draft_summary(draft_payload),
                'analysis_date': analysis_date.isoformat(), 'warnings': warnings}

    # -- model tool loop ---------------------------------------------------
    def _run_tool_loop(self, user_id, conversation_id, content, analysis_date, knowledge):
        messages = self._messages(conversation_id, content, analysis_date)
        envelopes: list[dict] = []
        draft_payload = None
        recall_note = None
        tool_trace: list[dict] = []
        calls = 0
        for _ in range(6):
            try:
                message = self.provider.chat(messages, tools=TOOL_SCHEMAS)
            except ProviderRateLimited as exc:
                raise ModelPending('model rate limited', exc.retry_after) from exc
            calls += 1
            tool_calls = message.get('tool_calls') or []
            messages.append({'role': 'assistant', 'content': message.get('content') or '',
                             'tool_calls': tool_calls})
            if not tool_calls:
                break
            for call in tool_calls:
                if calls >= 8:
                    break
                calls += 1
                name = (call.get('function') or {}).get('name')
                arguments = _coerce_arguments((call.get('function') or {}).get('arguments'))
                payload, env, draft, note = self._execute_tool(user_id, conversation_id, name, arguments,
                                                               analysis_date, knowledge)
                tool_trace.append({'tool': name, 'arguments': arguments, 'result': payload})
                if env:
                    envelopes.append(env)
                if draft:
                    draft_payload = draft
                if note:
                    recall_note = note
                messages.append({'role': 'tool', 'content': json.dumps(payload, default=str)})
        if not envelopes and draft_payload is None and recall_note is None:
            # The model produced nothing usable: fall back to the grounded planner.
            envelopes, draft_payload, recall_note = self._run_offline(
                user_id, conversation_id, content, analysis_date, knowledge)
            tool_trace.append({'tool': 'offline_fallback', 'arguments': {}, 'result': {'reason': 'no tool calls'}})
        return envelopes, draft_payload, recall_note, tool_trace, []

    def _execute_tool(self, user_id, conversation_id, name, arguments, analysis_date, knowledge):
        if name == 'asset_query':
            spec = _spec_from_arguments(arguments)
            try:
                envelope = knowledge.query(spec).model_dump(mode='json')
            except Exception as exc:  # invalid/unsupported query must not break the turn
                return {'error': f'{type(exc).__name__}: {exc}'}, None, None, None
            envelope['_spec'] = spec.model_dump(mode='json')
            payload = {'summary': envelope['summary'], 'selected_well_ids': envelope['selected_well_ids'],
                       'rows': envelope['visual']['data'][:50], 'calculations': envelope['calculations'][:20],
                       'conflicts': envelope['conflicts'], 'warnings': envelope['warnings'],
                       'evidence_count': len(envelope['evidence']), 'visual': envelope['visual']['kind']}
            return payload, envelope, None, None
        if name == 'recall_results':
            note = self.recall_results(user_id, arguments.get('query'), arguments.get('well_ids'),
                                       _as_date(arguments.get('start')), _as_date(arguments.get('end')),
                                       int(arguments.get('limit') or 5))
            return note, None, None, note
        if name == 'propose_feedback':
            try:
                args = dict(arguments or {})
                if args.get('kind') == 'correction':
                    if args.get('field') in _NUMERIC_FIELDS:
                        args['value'] = _numeric(args.get('value'))
                    elif args.get('field') == 'spill_detected' and isinstance(args.get('value'), str):
                        args['value'] = args['value'].strip().lower() in {'true', 'yes', '1'}
                draft = FeedbackService(self.session, self.settings).prepare(
                    author_id=user_id, conversation_id=conversation_id, knowledge=knowledge, **args)
            except Exception as exc:  # a bad argument must come back as a tool error, not a failed turn
                return {'error': f'{type(exc).__name__}: {exc}',
                        'hint': 'Resolve the exact record id and field with asset_query, then retry.'}, None, None, None
            return _draft_summary(draft), None, draft, None
        return {'error': f'unknown tool {name}'}, None, None, None

    def _messages(self, conversation_id, content, analysis_date):
        history = list(self.session.scalars(
            select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at).limit(20)))
        messages = [{'role': 'system', 'content': SYSTEM_PROMPT},
                    {'role': 'system', 'content': f'Analysis date: {analysis_date.isoformat()}. '
                                                  f'Quick chat; ask for clarification if a request is ambiguous.'}]
        for item in history[-10:]:
            if item.role in {'user', 'assistant'}:
                messages.append({'role': item.role, 'content': item.content})
        messages.append({'role': 'user', 'content': content})
        return messages

    # -- offline planning --------------------------------------------------
    def _run_offline(self, user_id, conversation_id, content, analysis_date, knowledge):
        plan = planner.plan(content, self.session, analysis_date)
        requires_recall = bool(plan.get('requires_recall'))
        recall_note = None
        if plan.get('recall'):
            recall_note = self.recall_results(user_id, plan['recall'].get('text'), plan['recall'].get('wells'),
                                              plan['recall'].get('day'), plan['recall'].get('day'), 5,
                                              count=plan['recall'].get('count'))
        if requires_recall and not (recall_note or {}).get('selected_well_ids'):
            # "the wells we discussed" could not be resolved against this user's own saved results.
            # Running the query anyway would answer a different, fleet-wide question.
            recall_note = {**(recall_note or {}), 'unresolved_reference': True}
        draft_payload = None
        if plan.get('feedback'):
            payload = {k: v for k, v in plan['feedback'].items() if k != 'missing'}
            draft_payload = FeedbackService(self.session, self.settings).prepare(
                author_id=user_id, conversation_id=conversation_id, knowledge=knowledge, **payload)
            envelopes = []
            if payload.get('kind') == 'claim':
                # A claim about the present is graded on the inspected state it conflicts with,
                # so answer the state question too. The claim itself stays a pending draft.
                well = draft_payload.get('well_id') or draft_payload.get('target_id')
                if well:
                    try:
                        spec = QuerySpec(operation=Operation.status, well_ids=[well])
                        envelope = knowledge.query(spec).model_dump(mode='json')
                        envelope['_spec'] = spec.model_dump(mode='json')
                        envelopes.append(envelope)
                    except Exception:
                        envelopes = []
            return envelopes, draft_payload, recall_note
        envelopes = []
        for raw in plan.get('queries', []):
            spec_dict = dict(raw)
            if recall_note and recall_note.get('selected_well_ids') and not spec_dict.get('well_ids') and not spec_dict.get('area'):
                spec_dict['well_ids'] = recall_note['selected_well_ids']
            elif requires_recall and not spec_dict.get('well_ids') and not spec_dict.get('area'):
                continue  # an unresolved reference must never become a fleet-wide sweep
            try:
                spec = QuerySpec.model_validate(spec_dict)
            except Exception:
                continue
            if spec.operation in {Operation.notes, Operation.status} and recall_note and not spec_dict.get('well_ids') and not spec_dict.get('area'):
                spec = spec.model_copy(update={'well_ids': recall_note['selected_well_ids'] or None})
            envelope = knowledge.query(spec).model_dump(mode='json')
            envelope['_spec'] = spec.model_dump(mode='json')
            envelopes.append(envelope)
        return envelopes, None, recall_note

    # -- recall ------------------------------------------------------------
    def recall_results(self, user_id, query=None, well_ids=None, start=None, end=None, limit=5, count=None):
        candidates: list[str] = []
        if self.graph is not None:
            candidates += self.graph.recall(user_id, query, well_ids, _start_iso(start), _end_iso(end), limit)
        if self.memory is not None:
            try:
                for hit in self.memory.recall(f'private:{user_id}', query or 'recent question', limit):
                    rid = (hit.get('metadata') or {}).get('result_id')
                    if rid:
                        candidates.append(rid)
            except Exception:
                pass
        if not candidates:
            # The API process has no graph/memory projections wired, so private history also
            # has to resolve from this user's own durable saved results. Never another user's.
            candidates = self._private_history(user_id, well_ids, limit, count)
        seen = []
        for rid in candidates:
            if rid in seen:
                continue
            seen.append(rid)
        if count:
            # "the three wells we discussed" names a set of that size. If no earlier answer
            # selected three wells, the reference does not resolve: a differently sized
            # answer is a different question, and widening to it would be wrong (Q16b).
            sized = [rid for rid in seen
                     if len(((self.session.get(SavedResult, rid).payload or {}).get('selected_well_ids') or []))
                     == count and self.session.get(SavedResult, rid).user_id == user_id]
            seen = sized
        rows = []
        for rid in seen[: max(limit, 5)]:
            result = self.session.get(SavedResult, rid)
            if result is None or result.user_id != user_id:
                continue  # ownership is re-validated in the authoritative database
            meta = self.session.get(ResultMeta, rid)
            payload = result.payload or {}
            rows.append({'result_id': rid, 'question': result.question,
                         'selected_well_ids': payload.get('selected_well_ids') or [],
                         'outdated': bool((meta.validity if meta else {}).get('outdated')) if meta else False,
                         'created_at': result.created_at.isoformat() if result.created_at else None})
        return {'candidates': rows, 'selected_well_ids': rows[0]['selected_well_ids'] if rows else [],
                'question': rows[0]['question'] if rows else None}

    def _private_history(self, user_id, well_ids, limit, count):
        """Most recent saved answers of this user that selected wells.

        Ownership is enforced by the query, so a reference can never resolve into another
        person's conversation (Q16b). The most recent answer is the natural referent of
        "the wells we discussed"; an explicit count narrows it further.
        """
        rows = list(self.session.scalars(
            select(SavedResult).where(SavedResult.user_id == user_id)
            .order_by(SavedResult.created_at.desc()).limit(50)))
        picked = []
        sized = []
        for result in rows:
            selected = (result.payload or {}).get('selected_well_ids') or []
            if not selected:
                continue
            if well_ids and not set(well_ids) <= set(selected):
                continue
            picked.append(result.id)
            if count and len(selected) == count:
                sized.append(result.id)
        return (sized if count else picked)[:max(limit, 5)]

    def _user_name(self, ident):
        if not ident:
            return None
        row = self.session.scalar(
            select(RecordVersion).join(ActiveRecord, ActiveRecord.version_id == RecordVersion.id)
            .where(RecordVersion.kind == 'user', RecordVersion.record_id == ident))
        return ((row.payload or {}).get('name') if row else None) or ident

    # -- composition -------------------------------------------------------
    def _compose(self, content, analysis_date, envelopes, draft_payload, recall_note, warnings, tool_trace):
        evidence: dict[str, dict] = {}
        conflicts: list[dict] = []
        calculations: list[dict] = []
        revisions: dict[str, str] = {}
        selected: list[str] = []
        findings: list[dict] = []
        visuals: list[dict] = []
        all_warnings = list(warnings)
        for env in envelopes:
            for ref in env.get('evidence') or []:
                evidence[ref['id']] = ref
            conflicts += env.get('conflicts') or []
            calculations += env.get('calculations') or []
            revisions.update(env.get('revisions') or {})
            selected += env.get('selected_well_ids') or []
            for key in env.get('warnings') or []:
                if key not in all_warnings:
                    all_warnings.append(key)
            for finding in env.get('findings') or []:
                findings.append(finding)
            visuals.append(env.get('visual') or {})
        selected = list(dict.fromkeys(selected))
        if tool_trace:
            calculations.append({'kind': 'tool_trace', 'calls': tool_trace})
        if recall_note and recall_note.get('candidates'):
            calculations.append({'kind': 'recall', 'candidates': recall_note['candidates'],
                                 'selected_well_ids': recall_note.get('selected_well_ids') or []})
        primary = visuals[0] if visuals else {'kind': 'text', 'title': 'answer', 'data': []}
        effect_sentences, effect_calculations, effect_conflicts = self._draft_effect(draft_payload, analysis_date)
        calculations += effect_calculations
        conflicts += effect_conflicts
        pending = self._pending_claim(draft_payload)
        if pending and primary.get('data'):
            row = primary['data'][0]
            if row.get('well_id') == pending['well_id']:
                row.setdefault('shared_notes', []).append(
                    {'text': pending['text'], 'author': pending['author'],
                     'status': 'unconfirmed', 'evidence_ids': []})
                positive = bool(re.search(r'running|back online|producing|operating', pending['text'] or '', re.I))
                negative = bool(re.search(r'shut.?in|stopped|not producing', pending['text'] or '', re.I))
                if (positive and not row.get('producing')) or (negative and row.get('producing')):
                    conflicts.append({'target_id': pending['well_id'],
                                      'message': 'Unconfirmed shared claim disagrees with inspected production. Please confirm.',
                                      'claim': pending['text'], 'author': pending['author'],
                                      'evidence_ids': row.get('evidence_ids') or []})
        summary = self._summary(envelopes, draft_payload, recall_note, primary,
                                conflicts=conflicts, effect_sentences=effect_sentences)
        envelope = AnswerEnvelope(
            result_id=new_id(), question=content, analysis_date=analysis_date,
            date_window=_window(envelopes, analysis_date),
            summary=summary, findings=[Finding.model_validate(f) for f in findings],
            evidence=[EvidenceRef.model_validate(v) for v in evidence.values()],
            conflicts=conflicts, visual=VisualSpec.model_validate(primary),
            selected_well_ids=selected, calculations=calculations, revisions=revisions,
            warnings=all_warnings)
        return envelope.model_dump(mode='json')

    def _draft_effect(self, draft_payload, analysis_date):
        """What the proposed change would do, computed from the rules — not guessed.

        A correction is provisional, so the copilot may not answer as if it were applied.
        It can still say, truthfully, what the records and the SOP imply if it is
        confirmed: a corrected thermal reading flips the production state, and a corrected
        spill volume can cross the reportable threshold.
        """
        if not draft_payload:
            return [], [], []
        preview = draft_payload.get('preview') or {}
        inspection_id = preview.get('inspection_id')
        field = draft_payload.get('field') or preview.get('field')
        value = draft_payload.get('after_value')
        if not inspection_id or value is None:
            return [], [], []
        fact = self.session.get(InspectionFact, inspection_id)
        if fact is None or not isinstance(value, (int, float)):
            return [], [], []
        well = self.session.get(WellFact, fact.well_id)
        knowledge = AssetKnowledge(self.session, analysis_date)
        calculations, conflicts, sentences = [], [], []
        if field in {'wellhead_temp_c', 'ambient_temp_c'}:
            wellhead = float(value) if field == 'wellhead_temp_c' else float(fact.wellhead_temp_c)
            ambient = float(value) if field == 'ambient_temp_c' else float(fact.ambient_temp_c)
            threshold = float(knowledge._value('production_delta_c', well.well_type))
            delta = round(wellhead - ambient, 1)
            producing = delta >= threshold
            calculations.append({'kind': 'proposed_reading', 'well_id': well.id,
                                 'inspection_id': inspection_id, 'wellhead_temp_c': wellhead,
                                 'ambient_temp_c': ambient, 'delta_c': delta,
                                 'threshold_c': threshold, 'producing': producing})
            sentences.append(
                f'If confirmed, {well.id} would be {"producing" if producing else "not producing"} '
                f'({delta:g} °C above ambient, against the {threshold:g} °C {well.well_type} limit).')
            record = self.session.get(RecordVersion, fact.version_id)
            remark = (record.payload or {}).get('notes') or ''
            if producing and re.search(r'not moving|stopped|not running|shut.?in|\bdown\b', remark, re.I):
                conflicts.append({'target_id': inspection_id,
                                  'message': f"The inspector's remark {remark!r} disagrees with the corrected reading. Please confirm.",
                                  'remark': remark, 'evidence_ids': []})
                sentences.append(f"The same inspection notes {remark!r}, which disagrees with the correction. Please confirm.")
        elif field == 'spill_est_volume_bbl':
            volume = float(value)
            reportable = volume >= float(knowledge._value('reportable_bbl'))
            major = volume >= float(knowledge._value('major_bbl'))
            calculations.append({'kind': 'proposed_spill', 'well_id': well.id,
                                 'inspection_id': inspection_id, 'volume_bbl': volume,
                                 'reportable': reportable})
            if reportable:
                limit = float(knowledge._value('major_report_hours') if major else knowledge._value('report_hours'))
                due = utc(fact.inspected_at) + timedelta(hours=limit)
                verification_due = utc(fact.inspected_at) + timedelta(days=int(knowledge._value('verification_days')))
                filed = list(self.session.scalars(select(RegulatorFact).where(
                    RegulatorFact.inspection_id == inspection_id,
                    RegulatorFact.event_type == 'spill_report_filed')))
                calculations.append({'kind': 'proposed_spill', 'well_id': well.id,
                                     'inspection_id': inspection_id, 'protocol': 'SR-01',
                                     'reportable': True, 'due_at': due.isoformat(),
                                     'status': 'breach' if filed else 'possible breach',
                                     'hours_to_report': filed[0].hours_to_report if filed else None,
                                     'detail': 'Written notice recorded' if filed else 'No written notice recorded'})
                calculations.append({'kind': 'proposed_spill', 'well_id': well.id,
                                     'inspection_id': inspection_id, 'protocol': 'SR-03',
                                     'due_at': verification_due.isoformat(), 'status': 'pending',
                                     'detail': 'Agency verification due for a reportable spill'})
                sentences.append(
                    f'At {volume:g} bbl the spill is reportable: a written notice was due by '
                    f'{due:%Y-%m-%d %H:%M} ({limit:g} h) and '
                    f'{"one is recorded" if filed else "none is recorded, a possible SR-01 breach"}. '
                    f'Agency verification is due by {verification_due:%Y-%m-%d}.')
                # The repair report was written under the old estimate. If its class and
                # reporting conclusion no longer hold, say so instead of leaving a stale
                # "no reporting duty" on the record.
                report = self.session.scalar(select(MaintenanceFact).where(
                    MaintenanceFact.inspection_id == inspection_id,
                    MaintenanceFact.report_version_id.is_not(None)))
                if report is not None:
                    record = self.session.get(RecordVersion, report.report_version_id)
                    source = self.session.get(SourceVersion, record.source_id) if record else None
                    text = source.content if source else ''
                    stated = re.search(r'\((minor|moderate|reportable|major)\s+class\)|'
                                       r'for\s+(minor|moderate|reportable|major)\s+spills', text, re.I)
                    old_class = (stated.group(1) or stated.group(2)).lower() if stated else None
                    new_class = 'major' if major else 'reportable'
                    if old_class and old_class != new_class:
                        sentences.append(
                            f'Repair report {report.id} classified it as {old_class} on the old '
                            f'{_display(draft_payload.get("before_value"))} bbl estimate and listed no '
                            f'reporting duty; that no longer holds.')
                    limit_hours = float(knowledge._value('containment_hours'))
                    if report.containment_hours is not None and report.containment_hours > limit_hours:
                        sentences.append(
                            f'The same report shows containment took about {report.containment_hours:g} h, '
                            f'over the {limit_hours:g} h limit (SR-02).')
        return sentences, calculations, conflicts

    def _pending_claim(self, draft_payload):
        if not draft_payload or draft_payload.get('kind') != 'claim':
            return None
        well = draft_payload.get('well_id') or draft_payload.get('target_id')
        text = draft_payload.get('value') or draft_payload.get('after_value')
        if not well or not text:
            return None
        return {'well_id': well, 'text': text,
                'author': self._user_name(draft_payload.get('author_id'))}

    def _summary(self, envelopes, draft_payload, recall_note, primary, conflicts=None, effect_sentences=None):
        conflicts = conflicts or []
        if draft_payload is not None:
            if draft_payload.get('status') == 'needs_clarification':
                questions = '; '.join(draft_payload.get('clarification') or ['more detail'])
                return f'I can record that once you confirm the details. Please provide: {questions}.'
            base = (f'Prepared a {draft_payload.get("kind")} change for {draft_payload.get("target_id") or draft_payload.get("well_id")} '
                    f'({_display(draft_payload.get("before_value"))} -> {_display(draft_payload.get("after_value"))}). '
                    f'Confirm to publish it; nothing has changed yet.')
            if envelopes and draft_payload.get('field') in {'wellhead_temp_c', 'ambient_temp_c'}:
                row = (envelopes[0].get('visual') or {}).get('data') or []
                if row:
                    first = row[0]
                    base += (f" The latest inspection on {first.get('date')} shows {first.get('well_id')} "
                             f"{'producing' if first.get('producing') else 'not producing'} "
                             f"({first.get('delta_c'):g} °C above ambient).")
            for sentence in effect_sentences or []:
                base += ' ' + sentence
            for conflict in conflicts:
                message = conflict.get('message') or ''
                if 'confirm' in message.lower() and message not in base:
                    base += ' ' + message
            return base
        if not envelopes:
            if recall_note and recall_note.get('unresolved_reference'):
                return ('I have no earlier conversation of yours that names those wells. '
                        'Name the wells, an area, or a date range and I will answer from the records.')
            if recall_note and recall_note.get('candidates'):
                return f'Recalled {len(recall_note["candidates"])} earlier result(s); nothing further was requested.'
            return 'I could not map that request to a supported asset query. Please rephrase with a well, area or operation.'
        if primary.get('kind') == 'heatmap':
            return f'Combined {len(envelopes)} source-backed analyses; see the findings and evidence.'
        base = envelopes[0].get('summary') or 'See findings.'
        # Say why a well the user might expect is absent because its reading was corrected.
        for calculation in envelopes[0].get('calculations') or []:
            if calculation.get('kind') == 'corrected_exclusion':
                base += (f" {calculation['well_id']} is not listed: its reading of "
                         f"{calculation.get('original_value')} was corrected to {calculation.get('corrected_value')} "
                         f"by {calculation.get('author')}, which makes it producing.")
        # A team rule that replaces the manual must not look like the manual's threshold.
        if any(row.get('authority') == 'team override' for row in primary.get('data') or []):
            overrides = [row for row in primary.get('data') or [] if row.get('authority') == 'team override']
            who = overrides[0].get('author') or 'the team'
            types = sorted({row.get('well_type') for row in overrides if row.get('well_type')})
            base += (f" This threshold follows {who}'s team rule for {'/'.join(types)}, "
                     f'not the official manual.')
        # A single spill whose notes disagree: answer the yes/no explicitly.
        if primary.get('kind') == 'table' and len(primary.get('data') or []) == 1:
            if any('do not replace detection' in (conflict.get('message') or '') for conflict in conflicts):
                base = 'Yes. The detection stands; the attributed notes disagree and both are shown. ' + base
        return base

    def _save_meta(self, user_id, result, envelope, envelopes, analysis_date):
        specs = [env.get('_spec') for env in envelopes if env.get('_spec')]
        meta = ResultMeta(result_id=result.id, user_id=user_id,
                          query_spec=specs[0] if specs else None,
                          query_specs=specs or None,
                          dependencies=self._dependencies(envelope),
                          validity={'outdated': False}, analysis_date=analysis_date)
        self.session.merge(meta)

    def _dependencies(self, envelope):
        deps: dict[str, dict] = {}
        for ref in envelope.get('evidence') or []:
            record_id = ref.get('record_id')
            if not record_id:
                title = (ref.get('title') or '')
                if title and _looks_like_rule(title):
                    deps.setdefault(f'rule:{title}', {'kind': 'rule', 'record_id': title,
                                                      'source_id': ref.get('source_id')})
                continue
            version = self.session.scalar(
                select(RecordVersion).where(RecordVersion.record_id == record_id).limit(1))
            kind = version.kind if version else 'record'
            deps.setdefault(f'{kind}:{record_id}', {'kind': kind, 'record_id': record_id,
                                                    'source_id': ref.get('source_id')})
        return list(deps.values())

    def _default_analysis_date(self) -> date:
        try:
            return date.fromisoformat(self.settings.analysis_date)
        except Exception:
            return date.today()

    def compose(self, question, analysis_date, envelopes, warnings=None, draft_payload=None, recall_note=None):
        return self._compose(question, analysis_date, envelopes, draft_payload, recall_note, warnings or [], [])


class FeedbackService:
    """Durable prepare/confirm workflow for corrections, rules, notes and claims."""

    def __init__(self, session, settings: Settings | None = None):
        self.session = session
        self.settings = settings or get_settings()

    def prepare(self, *, author_id, kind, conversation_id=None, knowledge=None, target_id=None, well_id=None,
                field=None, value=None, unit=None, equipment_kind=None, reason=None, valid_from=None,
                valid_to=None, supersedes=None, **_ignored) -> dict:
        knowledge = knowledge or AssetKnowledge(self.session)
        draft = FeedbackDraft(author_id=author_id, conversation_id=conversation_id, kind=kind,
                              field=field or 'text', value=value, unit=unit, equipment_kind=equipment_kind,
                              reason=reason or '', valid_from=_as_date(valid_from), valid_to=_as_date(valid_to),
                              supersedes=supersedes, target_id=target_id or '', well_id=well_id)
        clarification = self._clarify(kind, well_id, target_id, field, value, reason, equipment_kind)
        draft.clarification = clarification
        if clarification:
            draft.status = 'needs_clarification'
            draft.fingerprint = ''
            draft.preview = {'missing': clarification}
            self.session.add(draft)
            self.session.commit()
            return _draft_dict(draft)
        # Resolve the concrete target for corrections that came in as a well + date.
        target_kind, resolved = self._resolve_target(kind, well_id, target_id)
        draft.target_id = resolved
        before, after, fingerprint, preview = self._preview(kind, resolved, well_id, field, value, unit,
                                                            equipment_kind, knowledge, author_id)
        if preview.get('error'):
            self.session.rollback()
            raise ValueError(preview['error'])
        draft.before_value = before
        draft.after_value = after
        draft.fingerprint = fingerprint
        draft.status = 'pending'
        draft.preview = preview
        self.session.add(draft)
        self.session.commit()
        return _draft_dict(draft)

    def confirm(self, draft_id: str, author_id: str, supersedes: str | None = None) -> dict:
        draft = self.session.get(FeedbackDraft, draft_id)
        if draft is None:
            raise KeyError('draft not found')
        if draft.author_id != author_id:
            raise PermissionError('draft belongs to another author')
        if draft.status == 'confirmed':
            return {'id': draft.id, 'status': 'confirmed', 'correction_id': draft.correction_id,
                    'idempotent': True, 'outdated_results': []}
        if draft.status == 'needs_clarification':
            raise ValueError('draft still needs clarification')
        target = self._lock_target(draft.kind, draft.target_id)
        fingerprint, preview = self._recheck(draft, target)
        if preview.get('error'):
            raise ValueError(preview['error'])
        if fingerprint != draft.fingerprint:
            draft.preview = preview
            draft.clarification = []
            draft.status = 'pending'
            self.session.commit()
            raise StaleDraftError('target changed since preview', _draft_dict(draft))
        prior = (draft.preview or {}).get('prior_correction')
        chosen = supersedes or draft.supersedes
        if prior and not chosen:
            raise ValueError('must identify the prior correction being superseded')
        if prior and chosen and chosen != prior.get('id'):
            raise ValueError('supersedes does not match the current prior correction')
        spec = FeedbackSpec(kind=draft.kind, target_id=draft.target_id, field=draft.field,
                            value=draft.value, author_id=draft.author_id, reason=draft.reason,
                            unit=draft.unit, equipment_kind=draft.equipment_kind,
                            valid_from=draft.valid_from, valid_to=draft.valid_to, supersedes=chosen)
        knowledge = AssetKnowledge(self.session, draft_analysis_date(self.session))
        outcome = knowledge.add_feedback(spec)
        draft.status = 'confirmed'
        draft.correction_id = outcome['id']
        outdated = self._mark_outdated(draft)
        self.session.commit()
        return {'id': draft.id, 'status': 'confirmed', 'correction_id': outcome['id'],
                'correction': outcome, 'idempotent': False, 'outdated_results': outdated}

    # -- helpers -----------------------------------------------------------
    def _clarify(self, kind, well_id, target_id, field, value, reason, equipment_kind):
        missing = []
        if kind in {'correction', 'rule', 'note', 'claim'} and not reason:
            missing.append('reason')
        if kind in {'correction', 'rule'}:
            if not field and kind == 'correction':
                missing.append('field')
            if value is None:
                missing.append('value')
        if kind == 'correction' and not target_id and not well_id:
            missing.append('well_id or inspection id')
        if kind == 'rule':
            if not target_id and not well_id:
                missing.append('well_type')
            if not equipment_kind:
                missing.append('equipment_kind')
        if kind in {'note', 'claim'} and not (target_id or well_id):
            missing.append('well_id')
        if kind == 'claim' and value is None:
            missing.append('statement')
        return missing

    def _resolve_target(self, kind, well_id, target_id):
        if kind == 'rule':
            return 'well_type', target_id or well_id
        if target_id:
            return ('inspection' if kind == 'correction' else 'well'), target_id
        return 'well', well_id

    def _preview(self, kind, resolved, well_id, field, value, unit, equipment_kind, knowledge, author_id=None):
        target_kind, target_id = self._resolve_target(kind, well_id, resolved)
        preview: dict = {}
        before = after = None
        if kind == 'correction':
            fact = self.session.get(InspectionFact, target_id)
            if fact is None:
                return None, None, '', {'error': f'unknown inspection {target_id}'}
            if well_id and fact.well_id != well_id:
                return None, None, '', {'error': 'inspection does not belong to the intended well'}
            version = self.session.get(RecordVersion, fact.version_id)
            before = (version.payload or {}).get(field)
            after = value
            preview['well_id'] = fact.well_id
            preview['inspection_id'] = fact.id
            preview['inspected_at'] = fact.inspected_at.date().isoformat()
            preview['field'] = field
            preview['unit'] = unit
            preview['before'] = before
            preview['after'] = after
            preview['plausible'] = self._plausible(field, value)
            prior_list = list(self.session.scalars(select(Correction).where(
                Correction.target_kind == 'inspection', Correction.target_id == target_id,
                Correction.field == field, Correction.status.in_(['accepted', 'disputed'])).order_by(
                Correction.created_at.desc())))
            if prior_list and prior_list[0].value != value:
                preview['prior_correction'] = {'id': prior_list[0].id, 'value': prior_list[0].value,
                                               'author': prior_list[0].author_id, 'status': prior_list[0].status}
            competitors = [c for c in self.session.scalars(select(FeedbackDraft).where(
                FeedbackDraft.kind == 'correction', FeedbackDraft.target_id == target_id,
                FeedbackDraft.field == field, FeedbackDraft.status == 'pending'))
                if c.author_id != author_id and c.value != value]
            if competitors:
                preview['conflicting_drafts'] = [{'id': c.id, 'author': c.author_id, 'value': c.value}
                                                 for c in competitors]
            fingerprint = _fingerprint(['correction', target_id, field, fact.version_id, before])
            return before, after, fingerprint, preview
        if kind == 'rule':
            # T350 has no rca_threshold of its own; it inherits T200's. The preview must read
            # the effective rule, or a legitimate rule change for an inheriting type is
            # rejected as "unknown well type".
            rule = knowledge._rule('rca_threshold', target_id)
            if rule is None:
                return None, None, '', {'error': f'unknown well type {target_id}'}
            before, after = rule.value, value
            preview.update({'well_type': target_id, 'equipment_kind': equipment_kind, 'field': field,
                            'before': before, 'after': after, 'inherited_from': rule.well_type})
            fingerprint = _fingerprint(['rule', target_id, field, equipment_kind, before])
            return before, after, fingerprint, preview
        preview.update({'well_id': target_id, 'field': 'text', 'before': None, 'after': value})
        fingerprint = _fingerprint(['note', target_id])
        return None, value, fingerprint, preview

    @staticmethod
    def _plausible(field, value):
        if field == 'spill_detected':
            return isinstance(value, bool)
        if not isinstance(value, (int, float)):
            return False
        if field == 'spill_area_pct':
            return 0 <= value <= 100
        if field == 'spill_est_volume_bbl':
            return 0 <= value <= 1_000_000
        return -100 <= value <= 300

    def _lock_target(self, kind, target_id):
        if kind == 'correction':
            return self.session.scalars(select(InspectionFact).where(InspectionFact.id == target_id)
                                        .with_for_update()).first()
        return None

    def _recheck(self, draft, target):
        knowledge = AssetKnowledge(self.session, draft_analysis_date(self.session))
        before, after, fingerprint, preview = self._preview(draft.kind, draft.target_id, draft.well_id,
                                                            draft.field, draft.value, draft.unit,
                                                            draft.equipment_kind, knowledge, draft.author_id)
        return fingerprint, preview

    def _mark_outdated(self, draft):
        target_kind, target_id = self._resolve_target(draft.kind, draft.well_id, draft.target_id)
        outdated = []
        for meta in self.session.scalars(select(ResultMeta)):
            for dep in meta.dependencies or []:
                if dep.get('record_id') == target_id and dep.get('kind') in {'inspection', 'record', 'inspection_fact'}:
                    validity = dict(meta.validity or {})
                    validity.update({'outdated': True, 'reason': 'underlying reading corrected',
                                     'correction_id': draft.correction_id, 'marked_at': _now_iso()})
                    meta.validity = validity
                    outdated.append(meta.result_id)
                    break
        return outdated


class StaleDraftError(RuntimeError):
    def __init__(self, message, draft):
        super().__init__(message)
        self.draft = draft


def draft_analysis_date(session) -> date:
    latest = session.scalar(select(func.max(InspectionFact.inspected_at)))
    return latest.date() if latest else date.today()


def _spec_from_arguments(arguments: dict) -> QuerySpec:
    clean = {k: v for k, v in (arguments or {}).items() if v is not None}
    return QuerySpec.model_validate(clean)


# Fields whose stored value is numeric. A model sometimes sends "5.4 bbl" instead of 5.4;
# normalising here keeps the preview and the plausibility check honest instead of silently
# storing a string that no later query would compare correctly.
_NUMERIC_FIELDS = {'wellhead_temp_c', 'ambient_temp_c', 'spill_est_volume_bbl', 'spill_area_pct'}


def _numeric(value):
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    match = re.search(r'-?\d+(?:\.\d+)?', str(value))
    if not match:
        return value
    number = float(match.group())
    return int(number) if number.is_integer() and '.' not in match.group() else number


def _coerce_arguments(arguments):
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        try:
            return json.loads(arguments)
        except Exception:
            return {}
    return {}


def _as_date(value):
    if value is None or isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:
        return None


def _start_iso(value):
    if value is None:
        return None
    moment = datetime.combine(value, time.min, tzinfo=timezone.utc) if isinstance(value, date) else value
    return moment.isoformat()


def _end_iso(value):
    if value is None:
        return None
    moment = datetime.combine(value, time.max, tzinfo=timezone.utc) if isinstance(value, date) else value
    return moment.isoformat()


def _window(envelopes, analysis_date):
    for env in envelopes:
        if env.get('date_window'):
            return env['date_window']
    return None


def _fingerprint(parts) -> str:
    return hashlib.sha256(json.dumps(parts, default=str).encode('utf-8')).hexdigest()[:32]


def _looks_like_rule(title: str) -> bool:
    return bool(title) and ' ' not in title and ('_' in title or title.islower())


def _display(value):
    return 'none' if value is None else str(value)


def _draft_summary(draft_payload):
    if not draft_payload:
        return None
    return draft_payload


def _draft_dict(draft: FeedbackDraft) -> dict:
    return {'id': draft.id, 'kind': draft.kind, 'target_id': draft.target_id, 'well_id': draft.well_id,
            'field': draft.field, 'value': draft.value, 'unit': draft.unit,
            'equipment_kind': draft.equipment_kind, 'reason': draft.reason, 'author_id': draft.author_id,
            'before_value': draft.before_value, 'after_value': draft.after_value,
            'status': draft.status, 'clarification': draft.clarification, 'preview': draft.preview,
            'fingerprint': draft.fingerprint, 'correction_id': draft.correction_id,
            'conversation_id': draft.conversation_id}
