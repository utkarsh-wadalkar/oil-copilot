"""Durable REST contract: conversations, grounded results, feedback prepare/confirm."""
from __future__ import annotations

import hashlib
from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, Body, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import ui_model
from app.config import Settings, get_settings
from app.db import get_session
from app.domain import InspectionFact, Operation, QuerySpec, WellFact
from app.ingestion import ingest_dataset
from app.knowledge import AssetKnowledge
from app.models import (ActiveRecord, Conversation, ConversationContext, Correction, FeedbackDraft, ImportBatch,
                        Message, MessageRequest, Outbox, ProjectionJob, RecordVersion, ResultMeta, SavedResult,
                        SourceVersion)
from app.orchestrator import FeedbackService, ModelPending, Orchestrator, StaleDraftError
from app.provider import OllamaProvider
from app.schemas import EvidenceRef


class MessageIn(BaseModel):
    content: str
    client_message_id: str
    analysis_date: date | None = None


class ConversationIn(BaseModel):
    title: str | None = None


class FeedbackIn(BaseModel):
    kind: str
    target_id: str | None = None
    well_id: str | None = None
    field: str | None = None
    value: object | None = None
    unit: str | None = None
    equipment_kind: str | None = None
    reason: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    supersedes: str | None = None
    message: str | None = None


class ConfirmIn(BaseModel):
    supersedes: str | None = None


class ImportIn(BaseModel):
    root: str | None = None


def create_router(settings: Settings | None = None, provider=None, memory=None, graph=None) -> APIRouter:
    settings = settings or get_settings()
    router = APIRouter()

    # -- identity ----------------------------------------------------------
    def current_user(x_user_id: str | None = Header(default=None, alias='X-User-ID'),
                     session: Session = Depends(get_session)) -> str:
        if not x_user_id:
            raise HTTPException(status_code=401, detail='X-User-ID header is required')
        exists = session.scalar(
            select(RecordVersion.record_id).join(ActiveRecord, ActiveRecord.version_id == RecordVersion.id)
            .where(RecordVersion.kind == 'user', RecordVersion.record_id == x_user_id))
        if not exists:
            raise HTTPException(status_code=403, detail='unknown dataset user')
        return x_user_id

    def owned_conversation(session: Session, conversation_id: str, user_id: str) -> Conversation:
        conversation = session.get(Conversation, conversation_id)
        if conversation is None or conversation.user_id != user_id:
            raise HTTPException(status_code=404, detail='conversation not found')
        return conversation

    def build_orchestrator(session: Session) -> Orchestrator:
        return Orchestrator(session, provider=provider, memory=memory, graph=graph, settings=settings)

    # -- identity and discovery -------------------------------------------
    @router.get('/users')
    def list_users(session: Session = Depends(get_session)):
        rows = session.scalars(
            select(RecordVersion).join(ActiveRecord, ActiveRecord.version_id == RecordVersion.id)
            .where(RecordVersion.kind == 'user').order_by(RecordVersion.record_id))
        return {'users': [{'id': r.record_id, 'name': (r.payload or {}).get('name'),
                           'role': (r.payload or {}).get('role'),
                           'team': (r.payload or {}).get('team')} for r in rows]}

    @router.get('/capabilities')
    def capabilities(user: str = Depends(current_user)):
        model = provider.status() if provider is not None else OllamaProvider(settings).status()
        return {'offline': not model.get('configured'), 'model': model,
                'memory': {'provider': 'pgvector', 'enabled': settings.mem0_enabled,
                           'embedding_model': settings.mem0_embedding_model},
                'graph': {'uri': settings.neo4j_uri, 'configured': True},
                'embeddings': {'model': settings.embeddings_model, 'enabled': settings.embeddings_enabled},
                'analysis_date': settings.analysis_date}

    # -- conversations -----------------------------------------------------
    @router.post('/conversations', status_code=201)
    def create_conversation(body: ConversationIn, user: str = Depends(current_user),
                            session: Session = Depends(get_session)):
        conversation = Conversation(user_id=user, title=body.title)
        session.add(conversation)
        session.flush()
        session.add(ConversationContext(conversation_id=conversation.id, nao_user_id=user))
        session.commit()
        return {'id': conversation.id, 'title': conversation.title,
                'created_at': conversation.created_at.isoformat()}

    @router.get('/conversations')
    def list_conversations(user: str = Depends(current_user), session: Session = Depends(get_session)):
        rows = session.scalars(select(Conversation).where(Conversation.user_id == user)
                               .order_by(Conversation.created_at.desc()))
        return {'conversations': [{'id': c.id, 'title': c.title, 'created_at': c.created_at.isoformat()}
                                  for c in rows]}

    @router.get('/conversations/{conversation_id}')
    def get_conversation(conversation_id: str, user: str = Depends(current_user),
                         session: Session = Depends(get_session)):
        conversation = owned_conversation(session, conversation_id, user)
        messages = session.scalars(select(Message).where(Message.conversation_id == conversation_id)
                                   .order_by(Message.created_at))
        results = session.scalars(select(SavedResult).where(SavedResult.conversation_id == conversation_id,
                                                            SavedResult.user_id == user)
                                  .order_by(SavedResult.created_at))
        return {'id': conversation.id, 'title': conversation.title,
                'messages': [{'id': m.id, 'role': m.role, 'content': m.content,
                              'created_at': m.created_at.isoformat()} for m in messages],
                'results': [{'result_id': r.id, 'question': r.question,
                             'created_at': r.created_at.isoformat()} for r in results]}

    @router.post('/conversations/{conversation_id}/messages')
    def post_message(conversation_id: str, body: MessageIn, user: str = Depends(current_user),
                     session: Session = Depends(get_session)):
        conversation = owned_conversation(session, conversation_id, user)
        if not body.content.strip():
            raise HTTPException(status_code=422, detail='content is required')
        fingerprint = _fingerprint(body.content, body.analysis_date)
        request_row = session.scalar(select(MessageRequest).where(
            MessageRequest.conversation_id == conversation_id,
            MessageRequest.client_message_id == body.client_message_id))
        if request_row is not None:
            if request_row.fingerprint != fingerprint:
                raise HTTPException(status_code=409, detail='client_message_id reused with different content')
            if request_row.status == 'complete' and request_row.result_id:
                return _stored_response(session, request_row)
        else:
            user_message = Message(conversation_id=conversation_id, role='user', content=body.content)
            session.add(user_message)
            session.flush()
            request_row = MessageRequest(conversation_id=conversation_id, user_id=user,
                                         client_message_id=body.client_message_id, fingerprint=fingerprint,
                                         status='pending', message_id=user_message.id)
            session.add(request_row)
            session.commit()
        if conversation.title is None:
            conversation.title = body.content[:60]
        try:
            outcome = build_orchestrator(session).answer(user, conversation_id, body.content,
                                                         body.analysis_date, body.client_message_id)
        except ModelPending as exc:
            request_row.status = 'pending'
            request_row.error = 'model rate limited'
            session.commit()
            return {'status': 'pending', 'conversation_id': conversation_id, 'retry_after': exc.retry_after,
                    'answer': None, 'draft': None}
        except Exception as exc:  # noqa: BLE001 - a failed turn is recorded, never fabricated
            session.rollback()
            request_row = session.scalar(select(MessageRequest).where(
                MessageRequest.conversation_id == conversation_id,
                MessageRequest.client_message_id == body.client_message_id))
            if request_row is not None:
                request_row.status = 'failed'
                request_row.error = f'{type(exc).__name__}: {exc}'[:2000]
                session.commit()
            raise HTTPException(status_code=500, detail='answer generation failed')
        session.add(Message(conversation_id=conversation_id, role='assistant',
                            content=outcome['envelope']['summary']))
        request_row.status = 'complete'
        request_row.result_id = outcome['envelope']['result_id']
        request_row.error = None
        session.commit()
        return {'status': outcome['status'], 'conversation_id': conversation_id,
                'message_id': request_row.message_id, 'result_id': outcome['envelope']['result_id'],
                'answer': outcome['envelope'], 'draft': outcome['draft'],
                'warnings': outcome['warnings']}

    # -- results -----------------------------------------------------------
    @router.get('/results/{result_id}')
    def get_result(result_id: str, user: str = Depends(current_user), session: Session = Depends(get_session)):
        result = session.get(SavedResult, result_id)
        if result is None or result.user_id != user:
            raise HTTPException(status_code=404, detail='result not found')
        meta = session.get(ResultMeta, result_id)
        return {'result_id': result.id, 'question': result.question, 'answer': result.payload,
                'validity': (meta.validity if meta else {'outdated': False}),
                'previous_result_id': meta.previous_result_id if meta else None,
                'analysis_date': meta.analysis_date.isoformat() if meta and meta.analysis_date else None}

    @router.post('/results/{result_id}/ui')
    def result_ui(result_id: str, user: str = Depends(current_user), session: Session = Depends(get_session)):
        """Compose a generative layout for an already validated answer.

        Presentation only: the program selects and orders parts of the stored envelope, and
        the UI model never supplies a value. Unconfigured or rejected returns 200 with
        ``enabled`` false and a reason, so the client falls back without an error banner.
        """
        result = session.get(SavedResult, result_id)
        if result is None or result.user_id != user:
            raise HTTPException(status_code=404, detail='result not found')
        program = ui_model.compose(result.payload or {}, result.id, settings)
        return {'result_id': result.id, 'enabled': program.enabled, 'model': program.model,
                'program': program.program, 'reason': program.reason}

    @router.post('/results/{result_id}/refresh')
    def refresh_result(result_id: str, user: str = Depends(current_user), session: Session = Depends(get_session)):
        result = session.get(SavedResult, result_id)
        if result is None or result.user_id != user:
            raise HTTPException(status_code=404, detail='result not found')
        meta = session.get(ResultMeta, result_id)
        specs = (meta.query_specs if meta else None) or ([meta.query_spec] if meta and meta.query_spec else [])
        specs = [s for s in specs if s]
        if not specs:
            raise HTTPException(status_code=400, detail='result has no typed query to refresh')
        analysis_date = (meta.analysis_date if meta and meta.analysis_date else date.fromisoformat(settings.analysis_date))
        knowledge = AssetKnowledge(session, analysis_date)
        envelopes = []
        for spec in specs:
            try:
                envelope = knowledge.query(QuerySpec.model_validate(spec)).model_dump(mode='json')
                envelope['_spec'] = spec
                envelopes.append(envelope)
            except Exception:
                continue
        if not envelopes:
            raise HTTPException(status_code=422, detail='the original query no longer runs against current facts')
        orchestrator = build_orchestrator(session)
        envelope = orchestrator.compose(result.question, analysis_date, envelopes)
        envelope['previous_result_id'] = result.id
        envelope['comparison'] = {'original': {'result_id': result.id, 'summary': (result.payload or {}).get('summary'),
                                               'findings': (result.payload or {}).get('findings')},
                                  'current': {'summary': envelope['summary'], 'findings': envelope['findings']}}
        new_result = SavedResult(conversation_id=result.conversation_id, user_id=user,
                                 question=result.question, payload={})
        session.add(new_result)
        session.flush()
        envelope['result_id'] = new_result.id
        new_result.payload = dict(envelope)
        session.flush()
        session.merge(ResultMeta(result_id=new_result.id, user_id=user, query_spec=specs[0],
                                 query_specs=specs, dependencies=orchestrator._dependencies(envelope),
                                 validity={'outdated': False}, previous_result_id=result.id,
                                 analysis_date=analysis_date))
        from app.worker import enqueue_result

        enqueue_result(session, new_result.id)
        session.commit()
        return envelope

    # -- evidence ----------------------------------------------------------
    @router.get('/evidence/{evidence_id:path}')
    def get_evidence(evidence_id: str, user: str = Depends(current_user), session: Session = Depends(get_session)):
        parts = evidence_id.rsplit(':', 2)
        if len(parts) != 3:
            raise HTTPException(status_code=404, detail='unknown evidence reference')
        source_id, start, end = parts
        try:
            start_n, end_n = int(start), int(end)
        except ValueError:
            raise HTTPException(status_code=404, detail='unknown evidence reference') from None
        source = session.get(SourceVersion, source_id)
        if source is None:
            raise HTTPException(status_code=404, detail='unknown evidence source')
        lines = source.content.splitlines()
        excerpt = '\n'.join(lines[start_n - 1:end_n])
        return EvidenceRef(id=evidence_id, source_id=source_id, path=source.path, title=source.path,
                           excerpt=excerpt, start_line=start_n, end_line=end_n).model_dump(mode='json')

    # -- feedback workflow -------------------------------------------------
    @router.post('/feedback', status_code=201)
    def prepare_feedback(body: FeedbackIn, user: str = Depends(current_user),
                         session: Session = Depends(get_session)):
        service = FeedbackService(session, settings)
        try:
            draft = service.prepare(author_id=user, kind=body.kind, target_id=body.target_id,
                                    well_id=body.well_id, field=body.field, value=body.value, unit=body.unit,
                                    equipment_kind=body.equipment_kind, reason=body.reason,
                                    valid_from=body.valid_from, valid_to=body.valid_to,
                                    supersedes=body.supersedes)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return draft

    @router.get('/feedback/{draft_id}')
    def get_feedback(draft_id: str, user: str = Depends(current_user), session: Session = Depends(get_session)):
        draft = session.get(FeedbackDraft, draft_id)
        if draft is None or draft.author_id != user:
            raise HTTPException(status_code=404, detail='draft not found')
        from app.orchestrator import _draft_dict

        return _draft_dict(draft)

    @router.post('/feedback/{draft_id}/confirm')
    def confirm_feedback(draft_id: str, body: ConfirmIn | None = Body(default=None),
                         user: str = Depends(current_user), session: Session = Depends(get_session)):
        supersedes = body.supersedes if body else None
        service = FeedbackService(session, settings)
        try:
            return service.confirm(draft_id, user, supersedes)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            # Never reveal the existence of another author's private draft.
            raise HTTPException(status_code=404, detail='draft not found') from exc
        except StaleDraftError as exc:
            raise HTTPException(status_code=409, detail={'message': str(exc), 'draft': exc.draft}) from exc
        except ValueError as exc:
            code = 409 if 'supersede' in str(exc) or 'clarification' in str(exc) else 422
            raise HTTPException(status_code=code, detail=str(exc)) from exc

    @router.get('/wells/{well_id}/history')
    def well_history(well_id: str, user: str = Depends(current_user), session: Session = Depends(get_session)):
        if session.get(WellFact, well_id) is None:
            raise HTTPException(status_code=404, detail='unknown well')
        inspection_ids = list(session.scalars(select(InspectionFact.id).where(InspectionFact.well_id == well_id)))
        updates = []
        corrections = session.scalars(select(Correction).where(or_(
            (Correction.target_kind == 'well') & (Correction.target_id == well_id),
            (Correction.target_kind == 'inspection') & (Correction.target_id.in_(inspection_ids or ['-'])))))
        for c in corrections:
            updates.append({'correction_id': c.id, 'kind': c.target_kind, 'target_id': c.target_id,
                            'field': c.field, 'before': c.original_value, 'after': c.value,
                            'author': c.author_id, 'reason': c.reason, 'status': c.status,
                            'valid_from': c.valid_from.isoformat() if c.valid_from else None,
                            'valid_to': c.valid_to.isoformat() if c.valid_to else None,
                            'created_at': c.created_at.isoformat()})
        notes = session.scalars(select(RecordVersion).join(ActiveRecord, ActiveRecord.version_id == RecordVersion.id)
                                .where(RecordVersion.kind == 'context', RecordVersion.asset_id == well_id))
        for note in notes:
            updates.append({'correction_id': None, 'kind': 'note', 'target_id': note.record_id,
                            'field': 'text', 'before': None, 'after': (note.payload or {}).get('text'),
                            'author': (note.payload or {}).get('author_user_id'),
                            'reason': (note.payload or {}).get('note_type'), 'status': 'recorded',
                            'valid_from': (note.payload or {}).get('valid_from'),
                            'valid_to': (note.payload or {}).get('valid_to'),
                            'created_at': note.created_at.isoformat()})
        updates.sort(key=lambda u: u['created_at'] or '')
        return {'well_id': well_id, 'updates': updates}

    # -- imports and indexing ---------------------------------------------
    @router.post('/imports', status_code=202)
    def start_import(body: ImportIn, user: str = Depends(current_user), session: Session = Depends(get_session)):
        base = Path(settings.dataset_root).resolve()
        target = Path(body.root).resolve() if body.root else base
        if target != base and base not in target.parents:
            raise HTTPException(status_code=400, detail='import root must be within the configured dataset root')
        batch = ingest_dataset(session, target)
        return {'id': batch.id, 'status': batch.status, 'counts': batch.counts, 'error': batch.error}

    @router.get('/imports/status')
    def import_status(user: str = Depends(current_user), session: Session = Depends(get_session)):
        batch = session.scalars(select(ImportBatch).order_by(ImportBatch.created_at.desc())).first()
        if batch is None:
            return {'status': 'none'}
        return {'id': batch.id, 'status': batch.status, 'counts': batch.counts, 'error': batch.error,
                'created_at': batch.created_at.isoformat()}

    @router.get('/indexing/status')
    def indexing_status(user: str = Depends(current_user), session: Session = Depends(get_session)):
        jobs = dict(session.execute(select(ProjectionJob.status, func.count()).group_by(ProjectionJob.status)).all())
        outbox = dict(session.execute(select(Outbox.status, func.count()).group_by(Outbox.status)).all())
        model = provider.status() if provider is not None else OllamaProvider(settings).status()
        return {'jobs': jobs, 'outbox': outbox,
                'targets': {'graph': settings.neo4j_uri, 'mem0': settings.mem0_collection,
                            'embeddings': settings.embeddings_model},
                'model_configured': bool(model.get('configured'))}

    @router.post('/indexing/retry')
    def indexing_retry(user: str = Depends(current_user), session: Session = Depends(get_session)):
        dead = list(session.scalars(select(ProjectionJob).where(ProjectionJob.status == 'dead')))
        for job in dead:
            job.status = 'pending'
            job.attempts = 0
            job.error = None
            job.lease_expires_at = None
        failed = list(session.scalars(select(Outbox).where(Outbox.status == 'failed')))
        for event in failed:
            event.status = 'pending'
            event.error = None
        session.commit()
        return {'requeued_jobs': len(dead), 'requeued_events': len(failed)}

    return router


def _fingerprint(content: str, analysis_date) -> str:
    return hashlib.sha256(f'{content}|{analysis_date or ""}'.encode('utf-8')).hexdigest()


def _stored_response(session: Session, request_row: MessageRequest) -> dict:
    result = session.get(SavedResult, request_row.result_id)
    draft = session.scalars(select(FeedbackDraft).where(FeedbackDraft.conversation_id == request_row.conversation_id)
                            .order_by(FeedbackDraft.created_at.desc())).first()
    from app.orchestrator import _draft_dict

    return {'status': 'complete', 'conversation_id': request_row.conversation_id,
            'message_id': request_row.message_id, 'result_id': request_row.result_id,
            'answer': result.payload if result else None,
            'draft': _draft_dict(draft) if draft else None, 'warnings': ['idempotent replay']}
