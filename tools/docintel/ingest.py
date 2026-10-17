"""Document Intelligence ingestion: unstructured ``.md`` + semi-structured ``.json`` -> Neo4j.

This implements the standard Document Intelligence output shape on the Aura graph:

    (:Document)-[:HAS_CHUNK]->(:Chunk)-[:NEXT_CHUNK]->(:Chunk)
    (:Chunk)-[:MENTIONS]->(:<typed entity>)
    (:<entity>)-[:<RELATION>]->(:<entity>)

* Markdown documents (fleet SOPs, well-type manuals, per-well maintenance reports) are
  chunked and passed through the Ollama Cloud chat model, which extracts a controlled
  vocabulary of entities and relations.
* JSON registries (``areas.json``, ``users.json``, per-well ``metadata.json``) are loaded
  deterministically, and each is also represented as a ``Document`` + ``Chunk`` for
  provenance so it shows up in the same lexical layer.

The pipeline is idempotent (documents are keyed by relative path and skipped when the
file hash is unchanged), concurrent on the LLM calls, and serialised on graph writes.

Run with the project virtualenv (it already has ``httpx`` + ``neo4j``):

    ..\\.venv\\Scripts\\python.exe tools\\docintel\\ingest.py --limit 3
    ..\\.venv\\Scripts\\python.exe tools\\docintel\\ingest.py
    ..\\.venv\\Scripts\\python.exe tools\\docintel\\ingest.py --embed
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'backend'))

import httpx  # noqa: E402
from neo4j import GraphDatabase  # noqa: E402
from neo4j.exceptions import (  # noqa: E402
    ServiceUnavailable,
    SessionExpired,
    TransientError,
)

from app.config import get_settings  # noqa: E402

DATASET = REPO / 'assets' / 'flytbase-dataset' / 'sample-data'

DEFAULT_WELLS = (
    'WELL-0001,WELL-0002,WELL-0003,WELL-0004,WELL-0005,'
    'WELL-0051,WELL-0052,WELL-0053,WELL-0054,WELL-0055,'
    'WELL-0101,WELL-0102,WELL-0103,WELL-0104,WELL-0105,'
    'WELL-0151,WELL-0152,WELL-0153,WELL-0154,WELL-0155'
)

# ---------------------------------------------------------------------------
# Controlled vocabulary. The model may only use these labels/types; anything
# else is normalised or dropped, which keeps the Bloom perspective tidy.
# ---------------------------------------------------------------------------
NODE_LABELS = [
    'Well', 'WellType', 'Area', 'Team', 'Person', 'Role', 'Equipment', 'Protocol',
    'Regulation', 'Spill', 'Hazard', 'Inspection', 'MaintenanceActivity', 'Measurement',
    'Organization', 'Material',
]
REL_TYPES = [
    'REQUIRES', 'GOVERNS', 'APPLIES_TO', 'LOCATED_IN', 'HAS_EQUIPMENT', 'OF_TYPE',
    'PERFORMED_BY', 'DETECTED_BY', 'REPORTS_TO', 'MITIGATES', 'REFERENCES', 'PART_OF',
    'ASSIGNED_TO', 'CAUSED', 'MEASURED_AS', 'COMPLIES_WITH', 'FOLLOWS', 'OWNS', 'USES',
    'MANAGED_BY',
]

LABEL_ALIASES = {
    'oil_well': 'Well', 'well': 'Well', 'wells': 'Well', 'asset': 'Well',
    'well_type': 'WellType', 'welltype': 'WellType',
    'area': 'Area', 'block': 'Area', 'field': 'Area', 'location': 'Area',
    'team': 'Team', 'crew': 'Team', 'department': 'Team',
    'person': 'Person', 'people': 'Person', 'employee': 'Person', 'user': 'Person',
    'individual': 'Person', 'operator': 'Person', 'inspector': 'Person', 'engineer': 'Person',
    'role': 'Role', 'job': 'Role', 'position': 'Role', 'title': 'Role',
    'equipment': 'Equipment', 'component': 'Equipment', 'device': 'Equipment',
    'tool': 'Equipment', 'part': 'Equipment', 'asset_component': 'Equipment',
    'protocol': 'Protocol', 'procedure': 'Protocol', 'sop': 'Protocol', 'step': 'Protocol',
    'standard': 'Protocol', 'rule': 'Protocol', 'requirement': 'Protocol',
    'regulation': 'Regulation', 'law': 'Regulation', 'code': 'Regulation',
    'regulatory_requirement': 'Regulation', 'cfr': 'Regulation',
    'spill': 'Spill', 'release': 'Spill', 'incident': 'Spill', 'leak': 'Spill',
    'hazard': 'Hazard', 'risk': 'Hazard', 'danger': 'Hazard',
    'inspection': 'Inspection', 'survey': 'Inspection', 'check': 'Inspection',
    'maintenance': 'MaintenanceActivity', 'maintenanceactivity': 'MaintenanceActivity',
    'work': 'MaintenanceActivity', 'repair': 'MaintenanceActivity', 'job': 'MaintenanceActivity',
    'activity': 'MaintenanceActivity', 'task': 'MaintenanceActivity',
    'measurement': 'Measurement', 'value': 'Measurement', 'metric': 'Measurement',
    'quantity': 'Measurement', 'threshold': 'Measurement', 'limit': 'Measurement',
    'organization': 'Organization', 'organisation': 'Organization', 'company': 'Organization',
    'agency': 'Organization', 'contractor': 'Organization', 'authority': 'Organization',
    'vendor': 'Organization',
    'material': 'Material', 'substance': 'Material', 'fluid': 'Material',
    'chemical': 'Material', 'waste': 'Material',
}

REL_ALIASES = {
    'requires': 'REQUIRES', 'require': 'REQUIRES', 'must': 'REQUIRES',
    'governs': 'GOVERNS', 'regulates': 'GOVERNS', 'mandates': 'GOVERNS',
    'applies_to': 'APPLIES_TO', 'applies': 'APPLIES_TO', 'pertains_to': 'APPLIES_TO',
    'affects': 'APPLIES_TO',
    'located_in': 'LOCATED_IN', 'in_area': 'LOCATED_IN', 'part_of_area': 'LOCATED_IN',
    'has_equipment': 'HAS_EQUIPMENT', 'uses_equipment': 'HAS_EQUIPMENT', 'equipped_with': 'HAS_EQUIPMENT',
    'of_type': 'OF_TYPE', 'is_type': 'OF_TYPE', 'type': 'OF_TYPE',
    'performed_by': 'PERFORMED_BY', 'done_by': 'PERFORMED_BY', 'carried_out_by': 'PERFORMED_BY',
    'detected_by': 'DETECTED_BY', 'found_by': 'DETECTED_BY', 'discovered_by': 'DETECTED_BY',
    'reports_to': 'REPORTS_TO', 'reported_to': 'REPORTS_TO', 'notifies': 'REPORTS_TO',
    'mitigates': 'MITIGATES', 'prevents': 'MITIGATES', 'controls': 'MITIGATES',
    'references': 'REFERENCES', 'mentions': 'REFERENCES', 'cites': 'REFERENCES', 'see': 'REFERENCES',
    'part_of': 'PART_OF', 'belongs_to': 'PART_OF', 'contains': 'PART_OF',
    'assigned_to': 'ASSIGNED_TO', 'in_charge_of': 'ASSIGNED_TO', 'owns': 'ASSIGNED_TO',
    'caused': 'CAUSED', 'cause': 'CAUSED', 'results_in': 'CAUSED', 'led_to': 'CAUSED',
    'measured_as': 'MEASURED_AS', 'has_value': 'MEASURED_AS', 'quantified_as': 'MEASURED_AS',
    'complies_with': 'COMPLIES_WITH', 'satisfies': 'COMPLIES_WITH', 'meets': 'COMPLIES_WITH',
    'follows': 'FOLLOWS', 'implements': 'FOLLOWS', 'according_to': 'FOLLOWS',
    'managed_by': 'MANAGED_BY', 'overseen_by': 'MANAGED_BY', 'lead_by': 'MANAGED_BY',
    'owns_asset': 'OWNS', 'operated_by': 'OWNS', 'uses': 'USES', 'utilises': 'USES',
}

DOC_LABELS = ['Document', 'Chunk']
UNIQUE_ID_LABELS = [label for label in NODE_LABELS if label != 'Well'] + DOC_LABELS + ['Entity']

PROMPT = """You extract a knowledge graph from one chunk of an oil & gas asset-management document.

Return ONLY a JSON object with this exact shape:
{{"entities": [{{"name": "...", "type": "LABEL"}}], "relations": [{{"source": "entity name", "target": "entity name", "type": "REL"}}]}}

Allowed entity LABEL values: {labels}

Allowed relation type values: {rels}

Rules:
- Use canonical identifiers that appear in the text: wells as WELL-0001, areas as SW-23, teams as TEAM-SW, well types as T200, protocols as SR-01 / WS-02 / RC-05.
- People use full names (e.g. "Daniel Foster"). Equipment uses concise nouns (e.g. "flowline", "pump jack"). Regulations keep their code (e.g. "40 CFR 112.9", "Statewide Rule 91").
- Keep every entity name to at most 6 words.
- Only output relations whose source and target are entities you listed, and only when the text states them.
- Never invent facts, numbers or names. Ignore boilerplate headers/footers.
- If the chunk has no useful entities, return {{"entities": [], "relations": []}}.

Document: {path}
---
{chunk}
---"""


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------
def slug(text: str) -> str:
    value = re.sub(r'[^a-z0-9]+', '-', (text or '').strip().lower())
    return value.strip('-') or 'unknown'


def lookup_name(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', (text or '').lower()).strip()


def normalize_label(raw) -> str | None:
    if not raw:
        return None
    key = slug(str(raw))
    if key in LABEL_ALIASES:
        return LABEL_ALIASES[key]
    for label in NODE_LABELS:
        if slug(label) == key:
            return label
    return None


def normalize_rel(raw) -> str:
    key = slug(str(raw or ''))
    if key in REL_ALIASES:
        return REL_ALIASES[key]
    upper = re.sub(r'[^A-Z0-9]+', '_', str(raw or '').strip().upper()).strip('_')
    if upper in REL_TYPES:
        return upper
    return 'RELATED_TO'


def canonical_id(label: str, name: str) -> str:
    text = (name or '').strip()
    if label == 'Well':
        match = re.search(r'WELL[-_ ]?(\d{1,4})', text, re.I)
        if match:
            return f'WELL-{int(match.group(1)):04d}'
    elif label == 'Area':
        match = re.search(r'\b((?:SW|NE)[-_ ]?\d{2})\b', text, re.I)
        if match:
            return re.sub(r'[ _]', '-', match.group(1).upper())
    elif label == 'Team':
        match = re.search(r'TEAM[-_ ]?([A-Za-z]+)', text, re.I)
        if match:
            return f'TEAM-{match.group(1).upper()}'
    elif label == 'WellType':
        match = re.search(r'\bT[-_ ]?(\d{3})\b', text, re.I)
        if match:
            return f'T{int(match.group(1)):03d}'
    elif label == 'Protocol':
        match = re.search(r'\b([A-Z]{2,3})[-_ ]?(\d{1,2})\b', text.upper())
        if match:
            return f'{match.group(1)}-{int(match.group(2)):02d}'
    return slug(text)


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    text = (text or '').replace('\r\n', '\n').strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    chunks, current = [], ''
    for para in re.split(r'\n\s*\n', text):
        para = para.strip()
        if not para:
            continue
        if current and len(current) + len(para) + 2 > size:
            chunks.append(current)
            tail = current[-overlap:].strip() if overlap > 0 else ''
            current = (tail + '\n\n' + para).strip() if tail else para
        else:
            current = (current + '\n\n' + para).strip() if current else para
    if current:
        chunks.append(current)
    return chunks


# ---------------------------------------------------------------------------
# LLM extraction
# ---------------------------------------------------------------------------
class Extractor:
    def __init__(self, settings, workers: int, timeout: float, retries: int = 4):
        self.settings = settings
        self.workers = workers
        self.retries = retries
        self._lock = threading.Lock()
        self.calls = 0
        self.failures = 0
        self._client = httpx.Client(base_url=settings.ollama_base_url.rstrip('/'),
                                    timeout=httpx.Timeout(timeout, connect=20.0))

    def close(self):
        self._client.close()

    def _chat(self, prompt: str) -> str:
        payload = {
            'model': self.settings.ollama_model,
            'messages': [{'role': 'user', 'content': prompt}],
            'stream': False,
            'format': 'json',
            'options': {'temperature': 0.1, 'num_predict': 1600},
        }
        headers = {'Authorization': f'Bearer {self.settings.ollama_api_key}'}
        last: Exception | None = None
        for attempt in range(self.retries):
            try:
                response = self._client.post('/api/chat', json=payload, headers=headers)
                if response.status_code == 429 or response.status_code >= 500:
                    wait = float(response.headers.get('retry-after') or 0) or (2 ** attempt) * 2
                    time.sleep(min(wait, 30))
                    last = RuntimeError(f'HTTP {response.status_code}')
                    continue
                response.raise_for_status()
                return (response.json().get('message') or {}).get('content') or ''
            except Exception as exc:  # noqa: BLE001
                last = exc
                time.sleep(min((2 ** attempt) * 1.5, 20))
        raise RuntimeError(f'chat failed after {self.retries} attempts: {last}')

    @staticmethod
    def parse(raw: str) -> dict:
        empty = {'entities': [], 'relations': []}
        if not raw:
            return empty
        text = raw.strip()
        text = re.sub(r'^```[a-zA-Z]*\s*', '', text)
        text = re.sub(r'\s*```$', '', text).strip()
        data = None
        try:
            data = json.loads(text)
        except Exception:  # noqa: BLE001
            match = re.search(r'[\[{]', text)
            if match:
                for end in range(len(text), match.start(), -1):
                    try:
                        data = json.loads(text[match.start():end])
                        break
                    except Exception:  # noqa: BLE001
                        continue
        if data is None:
            return empty
        if isinstance(data, list):
            return {'entities': data, 'relations': []}
        if not isinstance(data, dict):
            return empty
        return {
            'entities': data.get('entities') or data.get('nodes') or [],
            'relations': data.get('relations') or data.get('relationships')
            or data.get('edges') or [],
        }

    def extract_chunk(self, text: str, path: str) -> dict:
        prompt = PROMPT.format(labels=', '.join(NODE_LABELS), rels=', '.join(REL_TYPES),
                               path=path, chunk=text)
        with self._lock:
            self.calls += 1
        try:
            return self.parse(self._chat(prompt))
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self.failures += 1
            print(f'  ! extraction failed for {path}: {type(exc).__name__}: {exc}', flush=True)
            return {'entities': [], 'relations': []}

    def extract_document(self, path: str, chunks: list[str]) -> dict:
        entities: dict[tuple[str, str], dict] = {}
        relations: dict[tuple[str, str, str], dict] = {}
        mentions: set[tuple[int, str, str, str]] = set()
        for index, chunk in enumerate(chunks):
            result = self.extract_chunk(chunk, path)
            local: dict[str, tuple[str, str]] = {}
            for item in result.get('entities') or []:
                if isinstance(item, str):
                    name, raw_label = item, 'Entity'
                elif isinstance(item, dict):
                    name = item.get('name') or item.get('id') or item.get('text') or ''
                    raw_label = (item.get('type') or item.get('label')
                                 or item.get('category') or 'Entity')
                else:
                    continue
                name = str(name).strip()
                label = normalize_label(raw_label)
                if not name or label is None:
                    continue
                entity_id = canonical_id(label, name)
                entities[(label, entity_id)] = {'label': label, 'id': entity_id, 'name': name}
                local[lookup_name(name)] = (label, entity_id)
                mentions.add((index, label, entity_id, name))
            for item in result.get('relations') or []:
                if not isinstance(item, dict):
                    continue
                source = lookup_name(item.get('source') or item.get('from') or '')
                target = lookup_name(item.get('target') or item.get('to') or '')
                if source not in local or target not in local:
                    continue
                rel = normalize_rel(item.get('type') or item.get('label') or item.get('relation'))
                sl, sid = local[source]
                tl, tid = local[target]
                if (sl, sid) == (tl, tid):
                    continue
                relations[(sl, sid, tl, tid, rel)] = {
                    'source_label': sl, 'source_id': sid,
                    'target_label': tl, 'target_id': tid, 'rel': rel,
                }
        return {
            'entities': list(entities.values()),
            'relations': list(relations.values()),
            'mentions': [{'chunk_index': i, 'label': l, 'entity_id': eid, 'name': n}
                         for (i, l, eid, n) in sorted(mentions)],
        }


# ---------------------------------------------------------------------------
# Graph writer
# ---------------------------------------------------------------------------
class GraphWriter:
    def __init__(self, settings, run_id: str):
        self.settings = settings
        self.run_id = run_id
        self.user_names: dict[str, str] = {}
        self.driver = GraphDatabase.driver(settings.neo4j_uri,
                                           auth=(settings.neo4j_user, settings.neo4j_password))

    def close(self):
        self.driver.close()

    def run(self, query: str, **params) -> list:
        """Execute one statement, retrying transient Aura routing/connection blips."""
        last: Exception | None = None
        for attempt in range(5):
            try:
                with self.driver.session() as session:
                    return [record.data() for record in session.run(query, **params)]
            except (ServiceUnavailable, SessionExpired, TransientError) as exc:
                last = exc
                time.sleep(min(2 ** attempt, 20))
        raise last  # type: ignore[misc]

    def ensure_schema(self):
        for label in UNIQUE_ID_LABELS:
            name = f'docintel_{label.lower()}_id'
            self.run(f'CREATE CONSTRAINT {name} IF NOT EXISTS '
                     f'FOR (n:{label}) REQUIRE n.id IS UNIQUE')

    def existing_hashes(self, paths: list[str]) -> dict[str, str]:
        rows = self.run('UNWIND $paths AS p MATCH (d:Document {id: p}) '
                        'RETURN d.id AS id, d.sha256 AS sha256', paths=paths)
        return {r['id']: r['sha256'] for r in rows}

    def write_document(self, doc: dict, payload: dict, well_id: str | None = None,
                       well_type: str | None = None):
        chunks = payload.get('chunks') or []
        # sha256 is written last: a document only looks "done" once every part of it landed,
        # so an interrupted write is re-ingested instead of being skipped forever.
        props = dict(doc['props'])
        sha = props.pop('sha256', None)
        self.run(
            'MERGE (d:Document {id: $id}) SET d += $props',
            id=doc['id'], props={**props, 'run_id': self.run_id})
        if chunks:
            self.run(
                'MATCH (d:Document {id: $id}) UNWIND $chunks AS c '
                'MERGE (ch:Chunk {id: c.id}) '
                'SET ch.text = c.text, ch.index = c.index, ch.chars = c.chars, '
                'ch.document_id = c.document_id, ch.embedding = c.embedding '
                'MERGE (d)-[:HAS_CHUNK]->(ch)',
                id=doc['id'], chunks=chunks)
            self.run(
                'MATCH (d:Document {id: $id})-[:HAS_CHUNK]->(c:Chunk) WITH c ORDER BY c.index '
                'WITH collect(c) AS cs '
                'FOREACH (i IN range(0, size(cs) - 2) | '
                'FOREACH (a IN [cs[i]] | FOREACH (b IN [cs[i + 1]] | MERGE (a)-[:NEXT_CHUNK]->(b))))',
                id=doc['id'])

        mentions = payload.get('mentions') or []
        by_label: dict[str, list[dict]] = {}
        for row in mentions:
            by_label.setdefault(row['label'], []).append(row)
        for label, rows in by_label.items():
            label = self._safe(label)
            self.run(
                'UNWIND $rows AS row '
                f'MERGE (e:{label} {{id: row.entity_id}}) '
                'SET e.name = coalesce(e.name, row.name) '
                'WITH e, row MATCH (ch:Chunk {id: row.chunk_id}) '
                'MERGE (ch)-[:MENTIONS]->(e)',
                rows=[{'chunk_id': f"{doc['id']}#{r['chunk_index']}", 'entity_id': r['entity_id'],
                       'name': r['name']} for r in rows])

        grouped: dict[tuple[str, str, str], list[dict]] = {}
        for rel in payload.get('relations') or []:
            key = (rel['source_label'], rel['rel'], rel['target_label'])
            grouped.setdefault(key, []).append(rel)
        for (sl, rt, tl), rows in grouped.items():
            sl, rt, tl = self._safe(sl), self._safe(rt), self._safe(tl)
            self.run(
                'UNWIND $rows AS row '
                f'MATCH (a:{sl} {{id: row.source_id}}) '
                f'MATCH (b:{tl} {{id: row.target_id}}) '
                f'MERGE (a)-[:{rt}]->(b)',
                rows=[{'source_id': r['source_id'], 'target_id': r['target_id']} for r in rows])

        if well_id:
            self.run('MATCH (d:Document {id: $id}) MATCH (w:Well {id: $well}) '
                     'MERGE (w)-[:HAS_DOCUMENT]->(d)', id=doc['id'], well=well_id)
        if well_type:
            self.run('MATCH (d:Document {id: $id}) '
                     'MERGE (t:WellType {id: $t}) MERGE (d)-[:DESCRIBES]->(t)',
                     id=doc['id'], t=well_type)
        if sha is not None:
            self.run('MATCH (d:Document {id: $id}) SET d.sha256 = $sha, d.ingested_at = $ts',
                     id=doc['id'], sha=sha,
                     ts=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))

    @staticmethod
    def _safe(token: str) -> str:
        token = str(token)
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', token):
            raise ValueError(f'unsafe cypher token: {token!r}')
        return token

    # -- structural (JSON) loaders ----------------------------------------
    def load_fleet_registries(self, areas_path: Path, users_path: Path) -> dict[str, str]:
        areas = json.loads(areas_path.read_text(encoding='utf-8'))
        users = json.loads(users_path.read_text(encoding='utf-8'))
        self.user_names = {u['user_id']: u['name'] for u in users.get('users', [])}
        for area in areas.get('areas', []):
            self.run(
                'MERGE (a:Area {id: $id}) SET a.name = $name, a.lat = $lat, a.lon = $lon '
                'MERGE (t:Team {id: $team}) WITH a, t MERGE (t)-[:MANAGES]->(a)',
                id=area['area_id'], name=area.get('name'), team=area.get('team_id'),
                lat=(area.get('center') or {}).get('lat'), lon=(area.get('center') or {}).get('lon'))
            self.run(
                'MATCH (a:Area {id: $id}) UNWIND $wells AS w '
                'MERGE (well:Well {id: w}) MERGE (well)-[:LOCATED_IN]->(a)',
                id=area['area_id'], wells=area.get('asset_ids', []))
        for user in users.get('users', []):
            self.run(
                'MERGE (p:Person {id: $id}) SET p.name = $name, p.user_id = $user_id, '
                'p.role = $role '
                'MERGE (r:Role {id: $role_id}) SET r.name = $role_name '
                'WITH p, r MERGE (p)-[:HAS_ROLE]->(r) '
                'WITH p MERGE (t:Team {id: $team}) MERGE (p)-[:MEMBER_OF]->(t)',
                id=slug(user['name']), name=user['name'], user_id=user['user_id'],
                role=user.get('role'), role_id=slug(user.get('role', '')),
                role_name=(user.get('role') or '').replace('_', ' '), team=user.get('team_id'))
        for team in areas.get('teams', []):
            lead = team.get('lead_user_id')
            self.run('MERGE (t:Team {id: $id}) SET t.name = $name '
                     'MERGE (p:Person {id: $lead}) WITH t, p MERGE (t)-[:MANAGED_BY]->(p)',
                     id=team['team_id'], name=team.get('name'),
                     lead=slug(self.user_names.get(lead, lead or '')))
        return self.user_names

    def load_well_metadata(self, metadata_path: Path, well_id: str) -> dict:
        raw = metadata_path.read_text(encoding='utf-8')
        data = json.loads(raw)
        self.run(
            'MERGE (w:Well {id: $id}) SET w.name = $name, w.well_type = $type, '
            'w.area_id = $area, w.team_id = $team, w.lat = $lat, w.lon = $lon, '
            'w.installed_on = $installed, w.status = $status '
            'MERGE (wt:WellType {id: $type}) MERGE (w)-[:OF_TYPE]->(wt) '
            'MERGE (area:Area {id: $area}) MERGE (w)-[:LOCATED_IN]->(area) '
            'MERGE (team:Team {id: $team}) MERGE (w)-[:MANAGED_BY]->(team)',
            id=well_id, name=data.get('name'), type=data.get('well_type'),
            area=data.get('area_id'), team=data.get('team_id'),
            lat=(data.get('location') or {}).get('lat'), lon=(data.get('location') or {}).get('lon'),
            installed=data.get('installed_on'), status=data.get('recorded_status'))
        equipment = [{'id': e.get('equipment_id'), 'kind': e.get('kind'), 'model': e.get('model')}
                     for e in data.get('equipment', []) if e.get('equipment_id')]
        if equipment:
            self.run('MATCH (w:Well {id: $id}) UNWIND $rows AS row '
                     'MERGE (e:Equipment {id: row.id}) SET e.name = row.kind, e.model = row.model '
                     'MERGE (w)-[:HAS_EQUIPMENT]->(e)', id=well_id, rows=equipment)
        in_charge = data.get('in_charge_user_id')
        if in_charge:
            person = slug(self.user_names.get(in_charge, in_charge))
            self.run('MATCH (w:Well {id: $id}) MERGE (p:Person {id: $pid}) '
                     'SET p.user_id = coalesce(p.user_id, $uid) '
                     'MERGE (w)-[:ASSIGNED_TO]->(p)', id=well_id, pid=person, uid=in_charge)
        return data

    def summary(self) -> None:
        print('\n=== graph summary ===', flush=True)
        for row in self.run('MATCH (n) RETURN labels(n)[0] AS label, count(*) AS c '
                            'ORDER BY c DESC'):
            print(f'  {row["label"]:<22} {row["c"]}')
        print('  --- relationships ---')
        for row in self.run('MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS c ORDER BY c DESC'):
            print(f'  {row["t"]:<22} {row["c"]}')


# ---------------------------------------------------------------------------
# Discovery + orchestration
# ---------------------------------------------------------------------------
def discover(wells: list[str]) -> tuple[list[dict], list[dict]]:
    md_docs: list[dict] = []
    json_docs: list[dict] = []
    fleet = DATASET / 'fleet'
    for path in sorted((fleet / 'sops').glob('*.md')):
        md_docs.append({'path': path, 'kind': 'sop'})
    for path in sorted((fleet / 'well-types').glob('*.md')):
        md_docs.append({'path': path, 'kind': 'well_type_manual',
                        'well_type': path.stem.upper()})
    for name in ('areas.json', 'users.json'):
        path = fleet / name
        if path.exists():
            json_docs.append({'path': path, 'kind': 'fleet_registry'})
    for well in wells:
        base = DATASET / 'assets' / well
        reports = base / 'maintenance-reports'
        if reports.is_dir():
            for path in sorted(reports.glob('*.md')):
                md_docs.append({'path': path, 'kind': 'maintenance_report', 'well_id': well})
        metadata = base / 'metadata.json'
        if metadata.exists():
            json_docs.append({'path': metadata, 'kind': 'well_metadata', 'well_id': well})
    return md_docs, json_docs


def rel_path(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def title_for(path: Path, text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('#'):
            return line.lstrip('# ').strip()
    return path.stem


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wells', default=DEFAULT_WELLS)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--chunk-size', type=int, default=2500)
    parser.add_argument('--overlap', type=int, default=250)
    parser.add_argument('--timeout', type=float, default=180.0)
    parser.add_argument('--limit', type=int, default=0, help='only process N markdown documents')
    parser.add_argument('--force', action='store_true', help='re-ingest unchanged documents')
    parser.add_argument('--embed', action='store_true', help='compute MiniLM chunk embeddings')
    parser.add_argument('--skip-structural', action='store_true')
    parser.add_argument('--skip-md', action='store_true')
    args = parser.parse_args()

    wells = [w.strip().upper() for w in args.wells.split(',') if w.strip()]
    settings = get_settings()
    run_id = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
    print(f'target   = {settings.neo4j_uri}')
    print(f'model    = {settings.ollama_model}')
    print(f'run      = {run_id}', flush=True)

    md_docs, json_docs = discover(wells)
    if args.limit:
        md_docs = md_docs[:args.limit]
    print(f'discovered {len(md_docs)} markdown + {len(json_docs)} json documents', flush=True)

    writer = GraphWriter(settings, run_id)
    try:
        writer.ensure_schema()

        embedder = None
        if args.embed:
            try:
                from app.embeddings import LocalEmbedder
                embedder = LocalEmbedder(settings)
                print('embeddings: local MiniLM enabled', flush=True)
            except Exception as exc:  # noqa: BLE001
                print(f'embeddings disabled: {exc}', flush=True)

        # -- structural JSON ------------------------------------------------
        if not args.skip_structural:
            print('\n[1/2] structural JSON registries', flush=True)
            writer.load_fleet_registries(DATASET / 'fleet' / 'areas.json',
                                         DATASET / 'fleet' / 'users.json')
            for doc in json_docs:
                raw = doc['path'].read_text(encoding='utf-8')
                if doc['kind'] == 'well_metadata':
                    writer.load_well_metadata(doc['path'], doc['well_id'])
                chunk = {'id': f"{rel_path(doc['path'])}#0", 'index': 0, 'text': raw.strip(),
                         'chars': len(raw), 'document_id': rel_path(doc['path']), 'embedding': None}
                writer.write_document(
                    {'id': rel_path(doc['path']), 'props': {
                        'path': rel_path(doc['path']), 'title': doc['path'].name,
                        'kind': doc['kind'], 'well_id': doc.get('well_id'),
                        'bytes': len(raw.encode()),
                        'sha256': hashlib.sha256(raw.encode()).hexdigest(),
                        'chunk_count': 1, 'model': 'structural'}},
                    {'chunks': [chunk]}, well_id=doc.get('well_id'))
            print(f'  registered {len(json_docs)} json documents', flush=True)

        # -- markdown extraction -------------------------------------------
        if not args.skip_md and md_docs:
            print(f'\n[2/2] markdown extraction ({len(md_docs)} documents, '
                  f'{args.workers} workers)', flush=True)
            hashes = {} if args.force else writer.existing_hashes([rel_path(d['path']) for d in md_docs])
            extractor = Extractor(settings, args.workers, args.timeout)
            done = skipped = failed = 0
            started = time.time()
            try:
                with ThreadPoolExecutor(max_workers=args.workers) as pool:
                    futures = {}
                    for doc in md_docs:
                        doc_id = rel_path(doc['path'])
                        data = doc['path'].read_bytes()
                        doc['sha256'] = hashlib.sha256(data).hexdigest()
                        doc['text'] = data.decode('utf-8', errors='replace')
                        doc['id'] = doc_id
                        if hashes.get(doc_id) == doc['sha256']:
                            skipped += 1
                            continue
                        future = pool.submit(
                            _process, extractor, doc, args.chunk_size, args.overlap, embedder)
                        futures[future] = doc
                    for future in as_completed(futures):
                        doc = futures[future]
                        try:
                            payload = future.result()
                        except Exception as exc:  # noqa: BLE001
                            failed += 1
                            print(f'  x {doc["path"].name}: {type(exc).__name__}: {exc}', flush=True)
                            continue
                        payload['chunks'] = [dict(c, document_id=doc['id']) for c in payload['chunks']]
                        try:
                            writer.write_document(
                                {'id': doc['id'], 'props': {
                                    'path': doc['id'], 'title': title_for(doc['path'], doc['text']),
                                    'kind': doc['kind'], 'well_id': doc.get('well_id'),
                                    'bytes': len(doc['text'].encode()),
                                    'sha256': doc['sha256'],
                                    'chunk_count': len(payload['chunks']),
                                    'entity_count': len(payload['entities']),
                                    'model': settings.ollama_model}},
                                payload, well_id=doc.get('well_id'), well_type=doc.get('well_type'))
                        except Exception as exc:  # noqa: BLE001
                            failed += 1
                            print(f'  x write {doc["path"].name}: {type(exc).__name__}: {exc}',
                                  flush=True)
                            continue
                        done += 1
                        if done % 10 == 0 or done == 1:
                            rate = done / max(time.time() - started, 1e-6)
                            print(f'  {done}/{len(futures)} docs  ({rate:.2f} doc/s, '
                                  f'{extractor.calls} llm calls)', flush=True)
            finally:
                extractor.close()
            print(f'  wrote {done}, skipped {skipped}, failed {failed}', flush=True)

        writer.summary()
    finally:
        writer.close()
    return 0


def _process(extractor: Extractor, doc: dict, chunk_size: int, overlap: int, embedder) -> dict:
    chunks = chunk_text(doc['text'], chunk_size, overlap)
    extracted = extractor.extract_document(doc['id'], chunks)
    chunk_rows = []
    for index, text in enumerate(chunks):
        row = {'id': f"{doc['id']}#{index}", 'index': index, 'text': text,
               'chars': len(text), 'document_id': doc['id'], 'embedding': None}
        chunk_rows.append(row)
    if embedder is not None and embedder.status().get('available'):
        try:
            vectors = embedder.embed([c['text'] for c in chunk_rows])
            for row, vector in zip(chunk_rows, vectors):
                row['embedding'] = vector
        except Exception:  # noqa: BLE001
            pass
    extracted['chunks'] = chunk_rows
    return extracted


if __name__ == '__main__':
    raise SystemExit(main())
