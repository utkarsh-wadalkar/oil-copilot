"""Self-hosted Mem0 semantic recall with strict scope isolation.

Memory is a retryable projection, never an authority: recall returns candidate
identifiers that the caller re-validates against PostgreSQL. Scopes are explicit
(``private:<user>``, ``well:<well>``, ``type:<well_type>``); there is no implicit
anonymous or fallback scope.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import select

from app.config import Settings, get_settings
from app.domain import InspectionFact
from app.models import ActiveRecord, Correction, RecordVersion, Rule, SavedResult


class MemoryUnavailable(RuntimeError):
    pass


def private_scope(user_id: str) -> str:
    return f'private:{user_id}'


def well_scope(well_id: str) -> str:
    return f'well:{well_id}'


def type_scope(well_type: str) -> str:
    return f'type:{well_type}'


def valid_scope(scope: str) -> bool:
    return bool(scope) and scope.split(':', 1)[0] in {'private', 'well', 'type'} and len(scope.split(':', 1)) == 2


class SemanticMemory:
    def __init__(self, settings: Settings | None = None, client=None, client_factory=None):
        self.settings = settings or get_settings()
        self._client = client
        self._client_factory = client_factory
        self._error: str | None = None

    # -- lifecycle ---------------------------------------------------------
    def _ensure_client(self):
        if self._client is not None:
            return self._client
        if self._error is not None:
            raise MemoryUnavailable(self._error)
        if not self.settings.mem0_enabled:
            self._error = 'mem0 disabled by configuration'
            raise MemoryUnavailable(self._error)
        try:
            if self._client_factory is not None:
                self._client = self._client_factory(self.settings)
            else:
                self._client = self._build_real_client()
        except MemoryUnavailable:
            raise
        except Exception as exc:
            self._error = f'mem0 initialisation failed: {type(exc).__name__}: {exc}'
            raise MemoryUnavailable(self._error) from exc
        return self._client

    def _build_real_client(self):
        try:
            from mem0 import Memory
        except Exception as exc:  # pragma: no cover - optional dependency
            self._error = f'mem0ai unavailable: {type(exc).__name__}'
            raise MemoryUnavailable(self._error) from exc
        history = Path(self.settings.mem0_history_path)
        try:
            history.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            history = Path('./data/mem0/history.db')
            history.parent.mkdir(parents=True, exist_ok=True)
        return Memory.from_config(self._build_config(str(history)))

    def _build_config(self, history_path: str) -> dict:
        db = _parse_database_url(self.settings.database_url)
        config = {
            'vector_store': {
                'provider': 'pgvector',
                'config': {
                    'host': db['host'], 'port': db['port'], 'user': db['user'],
                    'password': db['password'], 'dbname': db['database'],
                    'collection_name': self.settings.mem0_collection,
                    'embedding_model_dims': self.settings.mem0_embedding_dims,
                    'diskann': False,
                },
            },
            'embedder': {
                'provider': 'huggingface',
                'config': {
                    'model': self.settings.mem0_embedding_model,
                    'embedding_dims': self.settings.mem0_embedding_dims,
                    'model_kwargs': {'device': 'cpu'},
                },
            },
            # Explicit OpenAI-compatible Ollama Cloud endpoint. infer=False means the
            # LLM is not invoked for curated indexing; the config only prevents an
            # implicit paid OpenAI default credential.
            'llm': {
                'provider': 'openai',
                'config': {
                    'model': self.settings.ollama_model,
                    'api_key': self.settings.ollama_api_key,
                    'openai_base_url': self.settings.ollama_base_url.rstrip('/') + '/v1',
                },
            },
            'history_db_path': history_path,
            'version': 'v1.1',
        }
        return config

    def status(self) -> dict:
        try:
            client = self._ensure_client()
        except MemoryUnavailable as exc:
            return {'available': False, 'reason': str(exc)}
        return {'available': True, 'provider': 'pgvector',
                'collection': self.settings.mem0_collection,
                'embedding_model': self.settings.mem0_embedding_model,
                'client': type(client).__name__}

    def health(self) -> dict:
        return self.status()

    # -- primitive add/recall ---------------------------------------------
    def add_event(self, event_id: str, scope: str, text: str, metadata: dict | None = None) -> dict:
        """Idempotently add one curated memory event under an explicit scope."""
        if not valid_scope(scope):
            raise ValueError(f'invalid memory scope: {scope!r}')
        if not text or not text.strip():
            raise ValueError('memory text is required')
        client = self._ensure_client()
        meta = dict(metadata or {})
        meta.update({'event_id': event_id, 'scope': scope})
        existing = self._find_by_event(client, scope, event_id)
        if existing is not None:
            return {'id': existing, 'created': False}
        memory_id = self._add(client, text, scope, meta)
        return {'id': memory_id, 'created': True}

    def _add(self, client, text: str, scope: str, metadata: dict) -> str | None:
        response = client.add(text, user_id=scope, metadata=metadata, infer=False)
        return _extract_add_id(response)

    def _find_by_event(self, client, scope: str, event_id: str) -> str | None:
        try:
            listing = client.get_all(filters={'user_id': scope}, top_k=200)
        except TypeError:
            try:
                listing = client.get_all(filters={'user_id': scope})
            except Exception:
                return None
        except Exception:
            return None
        for item in _as_items(listing):
            meta = item.get('metadata') or {}
            if meta.get('event_id') == event_id:
                return item.get('id')
        return None

    def recall(self, scope: str, query: str, limit: int = 10) -> list[dict]:
        if not valid_scope(scope):
            raise ValueError(f'invalid memory scope: {scope!r}')
        try:
            client = self._ensure_client()
        except MemoryUnavailable:
            return []
        results = client.search(query, filters={'user_id': scope}, top_k=int(limit))
        out = []
        for item in _as_items(results):
            meta = item.get('metadata') or {}
            if meta.get('scope') and meta.get('scope') != scope:
                continue
            out.append({'id': item.get('id'), 'text': item.get('memory') or item.get('text'),
                        'score': item.get('score'), 'metadata': meta})
        return out

    # -- projection helpers used by the worker -----------------------------
    def index_batch(self, session, batch_id: str) -> int:
        """Index explicit shared knowledge published by an import batch."""
        count = 0
        for rule in session.scalars(select(Rule)).all():
            version = session.get(RecordVersion, _source_of_rule(session, rule))
            if version is None or version.batch_id != batch_id:
                continue
            scope = type_scope(rule.well_type) if rule.well_type else 'type:fleet'
            text = f'Rule {rule.rule_key} for well type {rule.well_type or "fleet"}: {rule.value}'
            result = self.add_event(f'rule:{rule.id}', scope, text,
                                    {'kind': 'rule', 'rule_key': rule.rule_key, 'well_type': rule.well_type})
            count += 1 if result.get('created') else 0
        return count

    def index_result(self, session, result_id: str) -> int:
        result = session.get(SavedResult, result_id)
        if result is None:
            return 0
        scope = private_scope(result.user_id)
        payload = result.payload or {}
        wells = list(payload.get('selected_well_ids') or [])
        text = f'Question: {result.question}. Saved result for wells {", ".join(wells) or "unspecified"}.'
        outcome = self.add_event(f'result:{result.id}', scope, text,
                                 {'kind': 'result', 'result_id': result.id,
                                  'conversation_id': result.conversation_id,
                                  'selected_well_ids': wells,
                                  'created_at': result.created_at.isoformat() if result.created_at else None})
        return 1 if outcome.get('created') else 0

    def index_feedback(self, session, correction_id: str) -> int:
        correction = session.get(Correction, correction_id)
        if correction is None:
            return 0
        if correction.status not in {'accepted', 'superseded'}:
            # Unconfirmed claims/drafts never become accepted memory.
            return 0
        scope, well_id = self._correction_scope(session, correction)
        text = f'{correction.target_kind} {correction.target_id} {correction.field} corrected to {correction.value}: {correction.reason}'
        outcome = self.add_event(f'correction:{correction.id}', scope, text,
                                 {'kind': correction.target_kind, 'correction_id': correction.id,
                                  'field': correction.field, 'value': json.dumps(correction.value, default=str),
                                  'author_id': correction.author_id, 'well_id': well_id})
        return 1 if outcome.get('created') else 0

    @staticmethod
    def _correction_scope(session, correction: Correction):
        if correction.target_kind == 'well_type':
            return type_scope(correction.target_id), None
        if correction.target_kind == 'inspection':
            fact = session.get(InspectionFact, correction.target_id)
            well_id = fact.well_id if fact else None
            return (well_scope(well_id), well_id) if well_id else (None, None)
        if correction.target_kind == 'well':
            return well_scope(correction.target_id), correction.target_id
        return None, None


def _extract_add_id(response) -> str | None:
    if isinstance(response, dict):
        results = response.get('results')
        if isinstance(results, list) and results:
            first = results[0]
            if isinstance(first, dict):
                return first.get('id')
        return response.get('id')
    if isinstance(response, list) and response and isinstance(response[0], dict):
        return response[0].get('id')
    return None


def _as_items(response) -> list[dict]:
    if isinstance(response, dict):
        results = response.get('results', response.get('memories', []))
        return [item for item in results if isinstance(item, dict)]
    if isinstance(response, list):
        return [item for item in response if isinstance(item, dict)]
    return []


def _source_of_rule(session, rule: Rule):
    return rule.source_id


def _parse_database_url(url: str) -> dict:
    parts = urlsplit(url.replace('postgresql+psycopg', 'postgresql').replace('postgresql+psycopg2', 'postgresql'))
    return {
        'host': parts.hostname or 'localhost',
        'port': parts.port or 5432,
        'user': parts.username or 'copilot',
        'password': parts.password or '',
        'database': (parts.path or '/copilot').lstrip('/') or 'copilot',
    }
