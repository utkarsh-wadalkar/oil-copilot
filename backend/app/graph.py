"""Independent Neo4j evidence graph projection and user-anchored recall.

The graph is a retryable projection of authoritative PostgreSQL facts; it is never
the source of truth. Private recall is always anchored at the owning ``User`` and
re-validated against PostgreSQL ownership by the caller, so a bare well traversal
can never surface another user's saved result.
"""
from __future__ import annotations

from app.config import Settings, get_settings
from app.domain import InspectionFact, WellFact
from app.models import ActiveRecord, Correction, RecordVersion, Rule, SavedResult, SourceVersion
from sqlalchemy import select

CONSTRAINTS = [
    ('copilot_well_id', 'Well', 'id'),
    ('copilot_source_id', 'SourceVersion', 'id'),
    ('copilot_evidence_id', 'Evidence', 'id'),
    ('copilot_rule_id', 'Rule', 'id'),
    ('copilot_correction_id', 'Correction', 'id'),
    ('copilot_user_id', 'User', 'id'),
    ('copilot_conversation_id', 'Conversation', 'id'),
    ('copilot_result_id', 'Result', 'id'),
]


class GraphMemory:
    def __init__(self, settings: Settings | None = None, driver=None):
        self.settings = settings or get_settings()
        self._driver = driver
        self._owns_driver = driver is None
        self._error: str | None = None
        self._constraints_ready = False

    # -- lifecycle ---------------------------------------------------------
    def driver(self):
        if self._driver is not None:
            return self._driver
        try:
            from neo4j import GraphDatabase
        except Exception as exc:  # pragma: no cover - optional dependency
            self._error = f'neo4j driver unavailable: {type(exc).__name__}'
            raise RuntimeError(self._error) from exc
        self._driver = GraphDatabase.driver(self.settings.neo4j_uri,
                                            auth=(self.settings.neo4j_user, self.settings.neo4j_password))
        return self._driver

    def close(self) -> None:
        if self._driver is not None and self._owns_driver:
            try:
                self._driver.close()
            finally:
                self._driver = None

    def _run(self, query, **params):
        with self.driver().session() as graph_session:
            result = graph_session.run(query, **params)
            return [record.data() for record in result]

    def _ensure_constraints(self) -> None:
        if self._constraints_ready:
            return
        for name, label, prop in CONSTRAINTS:
            self._run(f'CREATE CONSTRAINT {name} IF NOT EXISTS FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE')
        self._constraints_ready = True

    def health(self) -> dict:
        try:
            self.driver().verify_connectivity()
            return {'available': True, 'uri': self.settings.neo4j_uri}
        except Exception as exc:
            self._error = f'{type(exc).__name__}: {exc}'
            return {'available': False, 'uri': self.settings.neo4j_uri, 'reason': self._error}

    # -- projection --------------------------------------------------------
    def project_import(self, session, batch_id: str) -> int:
        """Project the structured shared records published by an import batch."""
        self._ensure_constraints()
        sources = list(session.scalars(select(SourceVersion).where(SourceVersion.batch_id == batch_id)))
        source_ids = [s.id for s in sources]
        count = 0
        self._run(
            'UNWIND $rows AS row MERGE (sv:SourceVersion {id: row.id}) '
            'SET sv.path = row.path, sv.revision = row.revision, sv.hash = row.hash',
            rows=[{'id': s.id, 'path': s.path, 'revision': s.revision, 'hash': s.hash} for s in sources])
        count += len(sources)

        current = {(r.kind, r.record_id): r for r in _active_records(session)}
        wells = []
        for well in session.scalars(select(WellFact)).all():
            version = current.get(('well', well.id))
            if version is None or version.source_id not in source_ids:
                continue
            wells.append({'id': well.id, 'well_type': well.well_type, 'area_id': well.area_id,
                          'area_name': well.area_name, 'lat': well.lat, 'lon': well.lon,
                          'source_id': version.source_id})
        if wells:
            self._run(
                'UNWIND $rows AS row MERGE (w:Well {id: row.id}) '
                'SET w.well_type = row.well_type, w.area_id = row.area_id, w.area_name = row.area_name, '
                'w.lat = row.lat, w.lon = row.lon '
                'WITH w, row MERGE (sv:SourceVersion {id: row.source_id}) WITH w, sv '
                'MERGE (w)-[:FROM_SOURCE]->(sv)', rows=wells)
        count += len(wells)

        rules = [{'id': r.id, 'rule_key': r.rule_key, 'well_type': r.well_type,
                  'value': _scalar(r.value) if isinstance(r.value, (int, float, str, bool)) or r.value is None else str(r.value),
                  'source_id': r.source_id}
                 for r in session.scalars(select(Rule).where(Rule.source_id.in_(source_ids))).all()]
        if rules:
            self._run(
                'UNWIND $rows AS row MERGE (rule:Rule {id: row.id}) '
                'SET rule.rule_key = row.rule_key, rule.well_type = row.well_type, rule.value = row.value '
                'WITH rule, row MERGE (sv:SourceVersion {id: row.source_id}) WITH rule, sv '
                'MERGE (rule)-[:FROM_SOURCE]->(sv)', rows=rules)
        count += len(rules)

        # Context-derived formal corrections published by the import batch.
        corrections = [c for c in session.scalars(select(Correction).where(Correction.source_id.in_(source_ids)))]
        for correction in corrections:
            count += self._project_correction(session, correction)
        return count

    def project_result(self, session, result_id: str) -> int:
        """Project a saved result snapshot and its cited evidence for one owner."""
        result = session.get(SavedResult, result_id)
        if result is None:
            return 0
        self._ensure_constraints()
        payload = result.payload or {}
        user = _user_record(session, result.user_id)
        user_name = user.payload.get('name') if user else result.user_id
        self._run(
            'MERGE (u:User {id: $user_id}) SET u.name = $name '
            'MERGE (c:Conversation {id: $conversation_id}) SET c.user_id = $user_id '
            'MERGE (u)-[:OWNS]->(c) '
            'MERGE (r:Result {id: $result_id}) '
            'SET r.user_id = $user_id, r.conversation_id = $conversation_id, r.question = $question, '
            'r.created_at = $created_at, r.selected_well_ids = $well_ids '
            'MERGE (c)-[:YIELDED]->(r) MERGE (u)-[:OWNS]->(r)',
            user_id=result.user_id, name=user_name, conversation_id=result.conversation_id,
            result_id=result.id, question=result.question,
            created_at=result.created_at.isoformat() if result.created_at else None,
            well_ids=list(payload.get('selected_well_ids') or []))
        count = 1
        for well_id in payload.get('selected_well_ids') or []:
            self._run('MERGE (w:Well {id: $id}) WITH w MATCH (r:Result {id: $result_id}) MERGE (r)-[:DISCUSSED]->(w)',
                      id=well_id, result_id=result.id)
        evidence_rows = []
        for ref in payload.get('evidence') or []:
            if not ref.get('source_id'):
                continue
            evidence_rows.append({'id': ref['id'], 'source_id': ref['source_id'],
                                  'record_id': ref.get('record_id'), 'path': ref.get('path'),
                                  'start_line': ref.get('start_line'), 'end_line': ref.get('end_line')})
        if evidence_rows:
            self._run(
                'UNWIND $rows AS row MERGE (e:Evidence {id: row.id}) '
                'SET e.source_id = row.source_id, e.record_id = row.record_id, e.path = row.path, '
                'e.start_line = row.start_line, e.end_line = row.end_line '
                'MERGE (sv:SourceVersion {id: row.source_id}) '
                'ON CREATE SET sv.path = row.path '
                'MERGE (e)-[:FROM_SOURCE]->(sv) '
                'WITH e, row MATCH (r:Result {id: $result_id}) MERGE (r)-[:CITES]->(e)',
                rows=evidence_rows, result_id=result.id)
        count += len(evidence_rows)
        # Link to the governing rules by matching active rule keys in the evidence titles.
        rule_keys = {r.rule_key for r in session.scalars(select(Rule)).all()}
        for ref in payload.get('evidence') or []:
            title = (ref.get('title') or '').strip()
            if title in rule_keys:
                self._run('MATCH (r:Result {id: $result_id}) MERGE (rule:Rule {rule_key: $rule_key}) '
                          'ON CREATE SET rule.id = $rule_key WITH r, rule MERGE (r)-[:USES_RULE]->(rule)',
                          result_id=result.id, rule_key=title)
        return count

    def project_feedback(self, session, correction_id: str) -> int:
        correction = session.get(Correction, correction_id)
        if correction is None:
            return 0
        self._ensure_constraints()
        return self._project_correction(session, correction)

    def _project_correction(self, session, correction: Correction) -> int:
        well_id = self._target_well(session, correction)
        supersedes = _supersedes(session, correction.id)
        self._run(
            'MERGE (cor:Correction {id: $id}) '
            'SET cor.target_kind = $target_kind, cor.target_id = $target_id, cor.field = $field, '
            'cor.status = $status, cor.author_id = $author_id, cor.value = $value, '
            'cor.original_value = $original_value, cor.reason = $reason, cor.well_id = $well_id '
            'MERGE (u:User {id: $author_id}) MERGE (u)-[:AUTHORED]->(cor)',
            id=correction.id, target_kind=correction.target_kind, target_id=correction.target_id,
            field=correction.field, status=correction.status, author_id=correction.author_id,
            value=_scalar(correction.value), original_value=_scalar(correction.original_value),
            reason=correction.reason, well_id=well_id)
        count = 1
        if correction.source_id:
            self._run('MATCH (cor:Correction {id: $id}) MERGE (sv:SourceVersion {id: $source_id}) '
                      'MERGE (cor)-[:FROM_SOURCE]->(sv)', id=correction.id, source_id=correction.source_id)
        if well_id:
            self._run('MATCH (cor:Correction {id: $id}) MERGE (w:Well {id: $well_id}) '
                      'MERGE (cor)-[:AMENDS]->(w)', id=correction.id, well_id=well_id)
        if supersedes:
            self._run('MATCH (cor:Correction {id: $id}) MERGE (old:Correction {id: $old}) '
                      'MERGE (cor)-[:SUPERSEDES]->(old)', id=correction.id, old=supersedes)
        return count

    @staticmethod
    def _target_well(session, correction: Correction) -> str | None:
        if correction.target_kind == 'well':
            return correction.target_id
        if correction.target_kind == 'inspection':
            fact = session.get(InspectionFact, correction.target_id)
            return fact.well_id if fact else None
        return None

    # -- recall ------------------------------------------------------------
    def recall(self, user_id: str, query: str | None = None, well_ids: list[str] | None = None,
               start=None, end=None, limit: int = 10) -> list[str]:
        """Return candidate saved-result IDs owned by ``user_id``; [] when unavailable."""
        tokens = [t.lower() for t in (query or '').split() if len(t) > 2] or None
        cypher = (
            'MATCH (u:User {id: $user_id})-[:OWNS]->(:Conversation)-[:YIELDED]->(res:Result) '
            'WHERE ($tokens IS NULL OR any(t IN $tokens WHERE toLower(res.question) CONTAINS t)) '
            'AND ($wells IS NULL OR any(w IN $wells WHERE (res)-[:DISCUSSED]->(:Well {id: w}))) '
            'AND ($start IS NULL OR res.created_at >= $start) '
            'AND ($end IS NULL OR res.created_at <= $end) '
            'RETURN DISTINCT res.id AS id, res.created_at AS created ORDER BY created DESC LIMIT $limit')
        try:
            rows = self._run(cypher, user_id=user_id, tokens=tokens, wells=well_ids or None,
                             start=start, end=end, limit=int(limit))
        except Exception as exc:
            self._error = f'{type(exc).__name__}: {exc}'
            return []
        return [row['id'] for row in rows]


def _active_records(session):
    return session.scalars(select(RecordVersion).join(ActiveRecord, ActiveRecord.version_id == RecordVersion.id)).all()


def _user_record(session, user_id):
    return session.scalars(select(RecordVersion).join(ActiveRecord, ActiveRecord.version_id == RecordVersion.id).where(
        RecordVersion.kind == 'user', RecordVersion.record_id == user_id)).first()


def _supersedes(session, correction_id):
    from app.domain import FeedbackDetail

    detail = session.get(FeedbackDetail, correction_id)
    return detail.supersedes if detail else None


def _scalar(value):
    if value is None or isinstance(value, (int, float, str, bool)):
        return value
    return str(value)
