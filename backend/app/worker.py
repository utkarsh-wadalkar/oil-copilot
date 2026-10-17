"""Durable outbox projection worker.

Each outbox event fans out into independent per-target jobs (graph, mem0,
embeddings) so an unavailable target never starves the others. Jobs are claimed
with a reclaimable lease and processed without holding database locks across the
remote call. Failures are retained with exponential backoff, never dropped.
"""
from __future__ import annotations

import argparse
import time
from datetime import timedelta

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import SessionLocal, init_db
from app.embeddings import EmbeddingsUnavailable, LocalEmbedder
from app.graph import GraphMemory
from app.memory import MemoryUnavailable, SemanticMemory
from app.models import DocumentChunk, Outbox, ProjectionJob, ProjectionReceipt, SourceVersion, new_id, now_utc

# Outbox event type -> projection targets. Keep in sync with Task 2 publishers.
TARGETS: dict[str, list[str]] = {
    'knowledge.published': ['graph', 'mem0'],
    'embeddings.requested': ['embeddings'],
    'knowledge.feedback': ['graph', 'mem0'],
    'result.saved': ['graph', 'mem0'],
}


def enqueue_result(session: Session, result_id: str) -> Outbox:
    """Queue index work for a saved result in the caller's transaction."""
    event = Outbox(event_type='result.saved', payload={'result_id': result_id})
    session.add(event)
    return event


def enqueue_feedback(session: Session, correction_id: str) -> Outbox:
    event = Outbox(event_type='knowledge.feedback', payload={'correction_id': correction_id})
    session.add(event)
    return event


class ProjectionWorker:
    def __init__(self, settings: Settings | None = None, session_factory=SessionLocal,
                 graph=None, memory=None, embedder=None, worker_id: str | None = None):
        self.settings = settings or get_settings()
        self.session_factory = session_factory
        self.graph = graph if graph is not None else GraphMemory(self.settings)
        self.memory = memory if memory is not None else SemanticMemory(self.settings)
        self.embedder = embedder if embedder is not None else LocalEmbedder(self.settings)
        self.worker_id = worker_id or self.settings.worker_id or f'worker-{new_id()[:8]}'
        self.lease_seconds = int(self.settings.worker_lease_seconds)
        self.max_attempts = int(self.settings.worker_max_attempts)

    # -- dispatch ----------------------------------------------------------
    def dispatch(self, session: Session, limit: int) -> int:
        pending = list(session.scalars(
            select(Outbox).where(Outbox.status == 'pending').order_by(Outbox.created_at).limit(limit)))
        created = 0
        for event in pending:
            targets = TARGETS.get(event.event_type)
            if not targets:
                # Explicit failure diagnostic; an unknown event must not be silently acknowledged.
                event.status = 'failed'
                event.error = f'unknown outbox event type: {event.event_type}'
                continue
            existing = set(session.scalars(
                select(ProjectionJob.target).where(ProjectionJob.outbox_id == event.id)))
            for target in targets:
                if target in existing:
                    continue
                session.add(ProjectionJob(outbox_id=event.id, event_type=event.event_type,
                                          target=target, payload=event.payload or {}))
                created += 1
        session.commit()
        return created

    # -- lease management --------------------------------------------------
    def recover_expired(self, session: Session) -> int:
        now = now_utc()
        stuck = list(session.scalars(select(ProjectionJob).where(
            ProjectionJob.status == 'processing', ProjectionJob.lease_expires_at < now)))
        for job in stuck:
            job.status = 'pending'
            job.next_attempt_at = now
            job.lease_expires_at = None
            job.error = (job.error or '') + ' | lease expired; reclaimed'
        session.commit()
        return len(stuck)

    def claim(self, session: Session, limit: int) -> list[ProjectionJob]:
        now = now_utc()
        stmt = (select(ProjectionJob)
                .where(ProjectionJob.status == 'pending',
                       or_(ProjectionJob.next_attempt_at.is_(None), ProjectionJob.next_attempt_at <= now))
                .order_by(ProjectionJob.created_at)
                .limit(limit))
        if session.bind.dialect.name == 'postgresql':
            stmt = stmt.with_for_update(skip_locked=True)
        jobs = list(session.scalars(stmt))
        for job in jobs:
            job.status = 'processing'
            job.worker_id = self.worker_id
            job.lease_expires_at = now + timedelta(seconds=self.lease_seconds)
            job.attempts = (job.attempts or 0) + 1
            job.updated_at = now
        session.commit()
        return jobs

    # -- processing --------------------------------------------------------
    def run_once(self, limit: int | None = None) -> dict:
        limit = limit or int(self.settings.worker_batch_limit)
        with self.session_factory() as session:
            self.recover_expired(session)
            self.dispatch(session, limit)
            jobs = self.claim(session, limit)
        processed = 0
        for job in jobs:
            self.process_job(job.id)
            processed += 1
        return {'claimed': len(jobs), 'processed': processed}

    def process_job(self, job_id: str) -> str:
        """Run one job in its own session so no lock is held across the remote call."""
        with self.session_factory() as session:
            job = session.get(ProjectionJob, job_id)
            if job is None:
                return 'missing'
            try:
                count, external_id, receipt_key, receipt_payload = self._handle(session, job)
                if receipt_key:
                    self._record_receipt(session, job.target, receipt_key, external_id, receipt_payload)
                job.status = 'done'
                job.external_id = external_id
                job.indexed_count = (job.indexed_count or 0) + int(count)
                job.error = None
                job.lease_expires_at = None
                job.processed_at = now_utc()
            except Exception as exc:  # noqa: BLE001 - every failure is retained, never dropped
                self._schedule_retry(job, exc)
            session.flush()
            self._refresh_outbox(session, job.outbox_id)
            session.commit()
            return job.status

    def _handle(self, session: Session, job: ProjectionJob) -> tuple[int, str | None, str | None, dict]:
        payload = job.payload or {}
        if (job.event_type, job.target) == ('knowledge.published', 'graph'):
            return self.graph.project_import(session, payload['batch_id']), None, None, {}
        if (job.event_type, job.target) == ('knowledge.published', 'mem0'):
            return self.memory.index_batch(session, payload['batch_id']), None, None, {}
        if (job.event_type, job.target) == ('embeddings.requested', 'embeddings'):
            return self._embed_batch(session, payload['batch_id']), None, None, {}
        if (job.event_type, job.target) == ('knowledge.feedback', 'graph'):
            return self.graph.project_feedback(session, payload['correction_id']), None, None, {}
        if (job.event_type, job.target) == ('knowledge.feedback', 'mem0'):
            cid = payload['correction_id']
            count = self.memory.index_feedback(session, cid)
            return count, None, f'correction:{cid}', payload
        if (job.event_type, job.target) == ('result.saved', 'graph'):
            return self.graph.project_result(session, payload['result_id']), None, None, {}
        if (job.event_type, job.target) == ('result.saved', 'mem0'):
            rid = payload['result_id']
            count = self.memory.index_result(session, rid)
            return count, None, f'result:{rid}', payload
        raise ValueError(f'no handler for {job.event_type}/{job.target}')

    def _embed_batch(self, session: Session, batch_id: str) -> int:
        source_ids = list(session.scalars(select(SourceVersion.id).where(SourceVersion.batch_id == batch_id)))
        if not source_ids:
            return 0
        missing = self._missing_chunks(session, source_ids)
        total = 0
        for start in range(0, len(missing), 64):
            batch = missing[start:start + 64]
            vectors = self.embedder.embed([c.text for c in batch])
            if len(vectors) != len(batch):
                raise EmbeddingsUnavailable('embedding count mismatch')
            for chunk, vector in zip(batch, vectors):
                self._store_embedding(session, chunk, vector)
                total += 1
        return total

    def _missing_chunks(self, session: Session, source_ids: list[str]) -> list[DocumentChunk]:
        if session.bind.dialect.name == 'postgresql':
            rows = session.execute(text(
                'SELECT id FROM document_chunks WHERE source_id = ANY(:ids) AND embedding_vector IS NULL '
                'ORDER BY id'), {'ids': source_ids}).all()
            ids = [row[0] for row in rows]
            return list(session.scalars(select(DocumentChunk).where(DocumentChunk.id.in_(ids)))) if ids else []
        # JSON columns may persist a literal "null" string, so filter in Python.
        rows = session.scalars(select(DocumentChunk).where(DocumentChunk.source_id.in_(source_ids)))
        return [chunk for chunk in rows if chunk.embedding is None]

    @staticmethod
    def _store_embedding(session: Session, chunk: DocumentChunk, vector: list[float]) -> None:
        chunk.embedding = vector
        if session.bind.dialect.name == 'postgresql':
            import json as _json

            session.execute(text('UPDATE document_chunks SET embedding_vector = CAST(:vector AS vector) WHERE id = :id'),
                            {'vector': _json.dumps(vector), 'id': chunk.id})

    def _schedule_retry(self, job: ProjectionJob, exc: Exception) -> None:
        from app.models import now_utc as _now

        job.error = f'{type(exc).__name__}: {exc}'[:2000]
        job.lease_expires_at = None
        if (job.attempts or 0) >= self.max_attempts:
            job.status = 'dead'
            job.next_attempt_at = None
        else:
            job.status = 'pending'
            delay = min(self.settings.worker_backoff_base_seconds * (2 ** max(0, (job.attempts or 1) - 1)),
                        self.settings.worker_backoff_max_seconds)
            job.next_attempt_at = _now() + timedelta(seconds=delay)
        job.updated_at = _now()

    @staticmethod
    def _record_receipt(session: Session, target: str, key: str, external_id: str | None,
                        payload: dict) -> None:
        existing = session.scalar(select(ProjectionReceipt).where(
            ProjectionReceipt.target == target, ProjectionReceipt.external_key == key))
        if existing is not None:
            existing.external_id = external_id or existing.external_id
            return
        session.add(ProjectionReceipt(target=target, external_key=key, external_id=external_id, payload=payload or {}))

    def _refresh_outbox(self, session: Session, outbox_id: str) -> None:
        event = session.get(Outbox, outbox_id)
        if event is None:
            return
        statuses = list(session.scalars(select(ProjectionJob.status).where(ProjectionJob.outbox_id == outbox_id)))
        if statuses and all(status == 'done' for status in statuses):
            event.status = 'done'
            event.processed_at = now_utc()
            event.error = None
        elif any(status == 'dead' for status in statuses):
            event.status = 'failed'
            event.error = 'one or more projection targets exhausted retries'
        else:
            event.status = 'pending'

    # -- operations --------------------------------------------------------
    def reset_job(self, session: Session, job_id: str) -> bool:
        job = session.get(ProjectionJob, job_id)
        if job is None:
            return False
        job.status = 'pending'
        job.attempts = 0
        job.next_attempt_at = now_utc()
        job.lease_expires_at = None
        job.error = None
        session.commit()
        return True

    def status(self, session: Session) -> dict:
        counts = dict(session.execute(
            select(ProjectionJob.status, func.count()).group_by(ProjectionJob.status)).all())
        return {'worker_id': self.worker_id, 'jobs': counts,
                'graph': self.graph.health(), 'mem0': self.memory.status(),
                'embeddings': self.embedder.status()}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description='Asset Intelligence projection worker')
    parser.add_argument('--once', action='store_true', help='process one batch then exit')
    parser.add_argument('--limit', type=int, default=None)
    parser.add_argument('--interval', type=float, default=None)
    args = parser.parse_args(argv)
    settings = get_settings()
    init_db()
    worker = ProjectionWorker(settings)
    if args.once:
        result = worker.run_once(args.limit)
        with SessionLocal() as session:
            print({'result': result, 'status': worker.status(session)})
        return
    interval = args.interval or settings.worker_poll_seconds
    while True:
        try:
            worker.run_once(args.limit)
        except Exception as exc:  # keep the worker alive; failures are persisted per job
            print({'worker_error': f'{type(exc).__name__}: {exc}'})
        time.sleep(interval)


if __name__ == '__main__':
    main()
