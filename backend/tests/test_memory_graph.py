"""Task 3A: graph/Mem0 adapters and durable projection worker."""
import os
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.memory import MemoryUnavailable, SemanticMemory, private_scope, type_scope, well_scope
from app.models import (Base, DocumentChunk, Outbox, ProjectionJob, ProjectionReceipt, SourceVersion,
                        new_id, now_utc)
from app.worker import ProjectionWorker, enqueue_feedback, enqueue_result


# --------------------------------------------------------------------------
# fakes
# --------------------------------------------------------------------------
class FakeGraph:
    def __init__(self):
        self.imports = []
        self.results = []
        self.feedback = []

    def project_import(self, session, batch_id):
        self.imports.append(batch_id)
        return 3

    def project_result(self, session, result_id):
        self.results.append(result_id)
        return 2

    def project_feedback(self, session, correction_id):
        self.feedback.append(correction_id)
        return 1

    def health(self):
        return {'available': True}

    def recall(self, *a, **k):
        return []


class FakeMemory:
    def __init__(self, fail=False):
        self.fail = fail
        self.batches = []
        self.results = []
        self.feedback = []

    def index_batch(self, session, batch_id):
        if self.fail:
            raise MemoryUnavailable('mem0 down')
        self.batches.append(batch_id)
        return 1

    def index_result(self, session, result_id):
        if self.fail:
            raise MemoryUnavailable('mem0 down')
        self.results.append(result_id)
        return 1

    def index_feedback(self, session, correction_id):
        if self.fail:
            raise MemoryUnavailable('mem0 down')
        self.feedback.append(correction_id)
        return 1

    def status(self):
        return {'available': not self.fail}


class FakeEmbedder:
    def __init__(self):
        self.calls = []

    def embed(self, texts):
        self.calls.append(list(texts))
        return [[0.1] * 384 for _ in texts]

    def status(self):
        return {'available': True}


class FakeClient:
    """In-memory stand-in for mem0.Memory with per-scope isolation."""

    def __init__(self):
        self.store = {}
        self.counter = 0

    def add(self, text, user_id=None, metadata=None, infer=False):
        self.counter += 1
        mid = f'm{self.counter}'
        self.store.setdefault(user_id, []).append({'id': mid, 'memory': text, 'metadata': metadata or {}})
        return {'results': [{'id': mid}]}

    def get_all(self, user_id=None, filters=None, top_k=200):
        scope = (filters or {}).get('user_id', user_id)
        return {'results': list(self.store.get(scope, []))}

    def search(self, query, user_id=None, filters=None, limit=10, top_k=10, threshold=0.1):
        scope = (filters or {}).get('user_id', user_id)
        items = [i for i in self.store.get(scope, []) if query.lower() in (i['memory'] or '').lower()]
        return {'results': items[:top_k]}


@pytest.fixture
def session_factory():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


# --------------------------------------------------------------------------
# SemanticMemory scope isolation
# --------------------------------------------------------------------------
def test_memory_scope_isolation_and_dedupe():
    client = FakeClient()
    memory = SemanticMemory(client=client)
    first = memory.add_event('e1', private_scope('U-201'), 'Michael asked about WELL-0121 downtime',
                             {'kind': 'result', 'result_id': 'R1'})
    assert first == {'id': 'm1', 'created': True}
    # Idempotent: same event id never creates a second memory.
    assert memory.add_event('e1', private_scope('U-201'), 'Michael asked about WELL-0121 downtime')['created'] is False
    # Shared well knowledge lives in a different scope and cannot leak into private recall.
    memory.add_event('e2', well_scope('WELL-0121'), 'WELL-0121 T200 well', {'kind': 'well'})
    results = memory.recall(private_scope('U-201'), 'WELL-0121', limit=10)
    assert [r['id'] for r in results] == ['m1']
    assert results[0]['metadata']['scope'] == private_scope('U-201')
    # A different user sees nothing of Michael's private history.
    assert memory.recall(private_scope('U-999'), 'WELL-0121', limit=10) == []


def test_memory_rejects_anonymous_scope():
    memory = SemanticMemory(client=FakeClient())
    with pytest.raises(ValueError):
        memory.add_event('e', 'anonymous', 'text')
    with pytest.raises(ValueError):
        memory.recall('', 'query')


def test_memory_unavailable_status_truthful():
    memory = SemanticMemory(client_factory=lambda settings: (_ for _ in ()).throw(MemoryUnavailable('no deps')))
    status = memory.status()
    assert status['available'] is False and 'no deps' in status['reason']


# --------------------------------------------------------------------------
# worker dispatch / leases / independence
# --------------------------------------------------------------------------
def make_worker(session_factory, memory=None, graph=None, embedder=None):
    return ProjectionWorker(session_factory=session_factory, graph=graph or FakeGraph(),
                            memory=memory or FakeMemory(), embedder=embedder or FakeEmbedder(),
                            worker_id='test-worker')


def test_dispatch_unknown_event_fails_explicitly(session_factory):
    with session_factory() as session:
        session.add(Outbox(event_type='mystery.event', payload={}))
        session.commit()
    worker = make_worker(session_factory)
    worker.run_once(limit=10)
    with session_factory() as session:
        event = session.scalars(select(Outbox)).one()
        assert event.status == 'failed'
        assert 'unknown outbox event type' in (event.error or '')


def test_mem0_failure_does_not_starve_graph(session_factory):
    with session_factory() as session:
        session.add(Outbox(event_type='knowledge.published', payload={'batch_id': 'B1'}))
        session.commit()
    graph = FakeGraph()
    memory = FakeMemory(fail=True)
    worker = make_worker(session_factory, graph=graph, memory=memory)
    worker.run_once(limit=10)
    with session_factory() as session:
        jobs = {j.target: j for j in session.scalars(select(ProjectionJob))}
        assert jobs['graph'].status == 'done'
        assert jobs['mem0'].status == 'pending'
        assert memory_status_pending(jobs['mem0'])
        assert session.scalars(select(Outbox)).one().status == 'pending'
    # Recover mem0 and retry just that job -> whole event completes.
    memory.fail = False
    with session_factory() as session:
        mem_job = session.scalars(select(ProjectionJob).where(ProjectionJob.target == 'mem0')).one()
        worker.reset_job(session, mem_job.id)
    worker.run_once(limit=10)
    with session_factory() as session:
        jobs = {j.target: j for j in session.scalars(select(ProjectionJob))}
        assert jobs['mem0'].status == 'done'
        assert session.scalars(select(Outbox)).one().status == 'done'
    assert graph.imports == ['B1'] and memory.batches == ['B1']


def memory_status_pending(job):
    return job.status == 'pending' and job.next_attempt_at is not None and job.error


def test_dead_letter_after_max_attempts(session_factory):
    with session_factory() as session:
        session.add(Outbox(event_type='knowledge.published', payload={'batch_id': 'B2'}))
        session.commit()
    worker = make_worker(session_factory, memory=FakeMemory(fail=True))
    worker.max_attempts = 1
    worker.run_once(limit=10)
    with session_factory() as session:
        mem_job = session.scalars(select(ProjectionJob).where(ProjectionJob.target == 'mem0')).one()
        assert mem_job.status == 'dead'
        event = session.scalars(select(Outbox)).one()
        assert event.status == 'failed'


def test_expired_lease_is_reclaimed(session_factory):
    with session_factory() as session:
        event = Outbox(event_type='knowledge.published', payload={'batch_id': 'B3'}, status='pending')
        session.add(event)
        session.flush()
        session.add(ProjectionJob(outbox_id=event.id, event_type='knowledge.published', target='graph',
                                  payload={'batch_id': 'B3'}, status='processing',
                                  lease_expires_at=now_utc() - timedelta(seconds=5), attempts=1))
        session.commit()
    worker = make_worker(session_factory)
    with session_factory() as session:
        assert worker.recover_expired(session) == 1
    worker.run_once(limit=10)
    with session_factory() as session:
        job = session.scalars(select(ProjectionJob).where(ProjectionJob.target == 'graph')).one()
        assert job.status == 'done' and job.attempts == 2


def test_result_saved_writes_graph_mem0_and_receipt(session_factory):
    graph, memory = FakeGraph(), FakeMemory()
    with session_factory() as session:
        enqueue_result(session, 'R-1')
        session.commit()
    worker = make_worker(session_factory, graph=graph, memory=memory)
    worker.run_once(limit=10)
    with session_factory() as session:
        receipt = session.scalars(select(ProjectionReceipt).where(ProjectionReceipt.external_key == 'result:R-1')).one()
        assert receipt.target == 'mem0'
        assert session.scalars(select(Outbox)).one().status == 'done'
    assert graph.results == ['R-1'] and memory.results == ['R-1']


def test_feedback_enqueue_and_projection(session_factory):
    graph, memory = FakeGraph(), FakeMemory()
    with session_factory() as session:
        enqueue_feedback(session, 'C-1')
        session.commit()
    worker = make_worker(session_factory, graph=graph, memory=memory)
    worker.run_once(limit=10)
    assert graph.feedback == ['C-1'] and memory.feedback == ['C-1']


def test_embeddings_idempotent(session_factory):
    with session_factory() as session:
        source = SourceVersion(id=new_id(), path='a.md', hash='h', content='x', revision='r', batch_id='B4')
        session.add(source)
        session.flush()
        session.add_all([DocumentChunk(source_id=source.id, text='alpha', embedding=None),
                         DocumentChunk(source_id=source.id, text='beta', embedding=None)])
        session.add(Outbox(event_type='embeddings.requested', payload={'batch_id': 'B4'}))
        session.commit()
    embedder = FakeEmbedder()
    worker = make_worker(session_factory, embedder=embedder)
    worker.run_once(limit=10)
    with session_factory() as session:
        assert all(c.embedding is not None for c in session.scalars(select(DocumentChunk)))
    # Second run must not re-embed already-populated chunks.
    worker.run_once(limit=10)
    assert len(embedder.calls) == 1


# --------------------------------------------------------------------------
# opt-in live adapters
# --------------------------------------------------------------------------
@pytest.mark.skipif(os.environ.get('COPILOT_TEST_NEO4J') != '1', reason='set COPILOT_TEST_NEO4J=1 for live Neo4j')
def test_live_neo4j_import_and_result_path():
    from app.graph import GraphMemory

    graph = GraphMemory()
    health = graph.health()
    assert health['available'], health
    assert isinstance(graph.recall('nobody', 'anything'), list)
    graph.close()
