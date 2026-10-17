"""Validate a complete import before atomically publishing current SQL projections."""
import argparse
import hashlib
import json
import math
import re
import subprocess
from collections import Counter
from datetime import date, datetime
from pathlib import Path, PurePosixPath

from sqlalchemy import select, text

from app.db import SessionLocal, init_db
from app.domain import ContextCorrectionIdentity, InspectionFact, MaintenanceFact, RegulatorFact, WellFact
from app.models import (ActiveRecord, Correction, DocumentChunk, ImportBatch, Outbox,
                        RecordVersion, Rule, SourceVersion, new_id)


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def timestamp(value):
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    if 'T' not in value or result.tzinfo is None: raise ValueError('timestamp requires ISO time and timezone')
    return result


def plain(value):
    return re.sub(r'\s+', ' ', re.sub(r'[*`_]', '', value)).strip()


def sections(content):
    lines = content.splitlines()
    start, heading = 1, 'Document'
    for n, line in enumerate(lines, 1):
        if line.startswith('#'):
            if n > start: yield heading, start, n-1, '\n'.join(lines[start-1:n-1])
            start, heading = n, line.lstrip('# ').strip()
    if start <= len(lines): yield heading, start, len(lines), '\n'.join(lines[start-1:])


def chunks(content):
    """Conservative section-aware chunks; long physical lines split with exact refs."""
    for heading, start, end, body in sections(content):
        words, first, last = [], start, start
        for number, line in enumerate(body.splitlines(), start):
            for word in line.split():
                # 100 words and a conservative character bound also protect punctuation-heavy text.
                if words and (len(words) >= 100 or sum(len(w) for w in words)+len(word) > 650):
                    yield heading, first, last, ' '.join(words)
                    words, first = [], number
                if not words: first = number
                words.append(word); last = number
        if words: yield heading, first, last, ' '.join(words)


def extracted_rules(path, content):
    """Only promote text matching a known grammatical rule; retain source section spans."""
    well_type = Path(path).stem if '/well-types/' in path else None
    for heading, start, end, body in sections(content):
        # Manuals wrap prose across lines and bold their numbers, so a line-oriented regex
        # silently misses rules such as T500's "at least **25 °C above\nambient**".
        clean = re.sub(r'\s+', ' ', plain(body).replace('**', '')).strip()
        rules = []
        def number(key, pattern, flags=re.I, text=None):
            match = re.search(pattern, text if text is not None else clean, flags)
            if match: rules.append((key, float(match.group(1))))
        if well_type:
            if 'Production temperature rule' in heading:
                number('production_delta_c', r'at least (\d+(?:\.\d+)?) °C above ambient')
            if 'Maintenance escalation' in heading:
                m = re.search(r'(Two|Three|\d+) or more corrective.*?(\d+) months', clean, re.I)
                if m:
                    words = {'two': 2, 'three': 3}
                    rules.extend([('rca_threshold', words.get(m.group(1).lower(), None) or int(m.group(1))),
                                  ('rca_months', int(m.group(2)))])
                if 'Same as T200' in clean: rules.append(('inherits', 'T200'))
                if 'follow T200' in clean and not any(key == 'inherits' for key, _ in rules):
                    rules.append(('inherits', 'T200'))
            if 'Scope' in heading:
                m = re.search(r'Procedures not listed here follow the (\w+) manual', clean)
                if m: rules.append(('inherits', m.group(1)))
        if path.endswith('spill-response-sop.md'):
            if 'Spill classes' in heading:
                number('reportable_bbl', r'Reportable \| (\d+(?:\.\d+)?) bbl')
                number('major_bbl', r'Major \| (\d+(?:\.\d+)?) bbl')
                number('minor_bbl', r'Minor \| below (\d+(?:\.\d+)?) bbl')
                number('moderate_notice_hours', r'(\d+) h \|')
            if 'Protocols' in heading:
                number('report_hours', r'within (\d+) hours of discovery')
                number('major_report_hours', r'within (\d+) hours for a major spill')
                number('containment_hours', r'contained within (\d+) hours')
                number('verification_days', r'verified within (\d+) days')
        if path.endswith('regulatory-compliance-sop.md'):
            number('nov_response_days', r'answered within (\d+) days')
        if path.endswith('operations-sop-rev2.md'):
            if 'Gas odor response' in heading:
                number('gas_response_hours', r'(\d+) hours for reports noted before')
                number('gas_response_hours_2027', r'(\d+) hours for reports noted from 1 Jan 2027')
            if 'Freeze protection' in heading:
                number('heat_trace_days', r'within (\d+) days')
                number('freeze_temp_c', r'at or below .?(\d+)')
            if 'Repeat failure' in heading:
                number('repeat_failure_days', r'within (\d+) days after the previous')
        if path.endswith('02-dataset-guide.md'):
            number('downtime_days', r'counts as (\d+) days of downtime')
        for key, value in rules:
            if value is None:
                continue
            yield key, well_type, value, start, end


def prepare(root, session):
    root = root.resolve(strict=True)
    files = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink() and not path.resolve().is_relative_to(root): raise ValueError(f'unsafe symlink: {path.name}')
        if path.is_file() and path.suffix in {'.json','.jsonl','.md'}:
            if not path.resolve().is_relative_to(root): raise ValueError('file outside root')
            files[path.relative_to(root).as_posix()] = path.read_text(encoding='utf-8-sig')
    # This one documented guide is allowed outside ROOT; arbitrary source paths are never followed.
    guide = root.parent/'02-dataset-guide.md'
    if guide.exists() and not guide.is_symlink(): files['dataset-guide/02-dataset-guide.md'] = guide.read_text(encoding='utf-8-sig')
    records=[]; seen=set()
    def add(kind, ident, payload, path, line=1):
        if not isinstance(ident,str) or not ident: raise ValueError(f'missing {kind} ID in {path}:{line}')
        if (kind,ident) in seen: raise ValueError(f'duplicate {kind} ID {ident}')
        seen.add((kind,ident)); records.append((kind,ident,payload,path,line))
    for path,content in files.items():
        if path == 'fleet/users.json':
            for p in json.loads(content)['users']: add('user',p['user_id'],p,path, next((n for n,l in enumerate(content.splitlines(),1) if f'"{p["user_id"]}"' in l),1))
        elif path == 'fleet/areas.json':
            data=json.loads(content)
            for kind in ('area','team'):
                for p in data[kind+'s']: add(kind,p[kind+'_id'],p,path,next((n for n,l in enumerate(content.splitlines(),1) if f'"{p[kind+"_id"]}"' in l),1))
        elif path.startswith('assets/') and path.endswith('/metadata.json'):
            p=json.loads(content); add('well',p['asset_id'],p,path)
        elif path.endswith('.jsonl'):
            kind={'inspections':'inspection','maintenance':'maintenance','regulatory-events':'regulator','context':'context'}.get(Path(path).stem)
            if not kind: raise ValueError(f'unknown record file {path}')
            key={'inspection':'inspection_id','maintenance':'maintenance_id','regulator':'event_id','context':'note_id'}[kind]
            for n,line in enumerate(content.splitlines(),1):
                if line.strip():
                    p=json.loads(line); add(kind,p[key],p,path,n)
        elif path.endswith('.md'):
            add('document',path,{'path':path},path)
    if not any(k=='well' for k,*_ in records): raise ValueError('dataset has no wells')
    known={}
    for active,record in session.execute(select(ActiveRecord,RecordVersion).join(RecordVersion,ActiveRecord.version_id==RecordVersion.id)):
        known[(record.kind,record.record_id)] = record.payload
    known.update({(k,i):p for k,i,p,_,_ in records})
    types={Path(p).stem for p in files if '/well-types/' in p}
    types.update(p['well_type'] for (k,_),p in known.items() if k=='well')
    valid_types={Path(p).stem for p in files if '/well-types/' in p and any(k=='production_delta_c' for k,*_ in extracted_rules(p,files[p]))}
    valid_types.update(r.well_type for r in session.scalars(select(Rule).where(Rule.rule_key=='production_delta_c')))
    def ref(kind, ident, where):
        if ident is not None and (kind,ident) not in known: raise ValueError(f'bad {kind} reference {ident} at {where}')
    for kind,ident,p,path,line in records:
        where=f'{path}:{line}'
        for field,value in p.items():
            if field in {'inspected_at','started_at','completed_at','created_at'} and value is not None: timestamp(value)
            if field in {'date','installed_on','valid_from','valid_to'} and value is not None: date.fromisoformat(value)
            if field.endswith('_user_id'): ref('user',value,where)
            if field in {'inspection_id','triggered_by_inspection_id','related_inspection_id'} and kind!='inspection':
                ref('inspection',value,where)
                if value and known['inspection',value].get('asset_id') != p.get('asset_id'): raise ValueError(f'cross-well inspection reference at {where}')
            if field=='related_event_id': ref('regulator',value,where)
            if field=='team_id': ref('team',value,where)
            if field=='area_id': ref('area',value,where)
            if field in {'wellhead_temp_c','ambient_temp_c','spill_est_volume_bbl','spill_area_pct','downtime_hours','hours_to_report','fine_usd'} and value is not None:
                if type(value) not in (int,float) or not math.isfinite(value): raise ValueError(f'bad numeric {field} at {where}')
                if not field.endswith('temp_c') and value<0: raise ValueError(f'negative {field} at {where}')
                if field=='spill_area_pct' and value>100: raise ValueError(f'invalid area percent at {where}')
                if field.endswith('temp_c') and not -100<=value<=300: raise ValueError(f'invalid temperature at {where}')
        if kind in {'inspection','maintenance','regulator','context'}: ref('well',p.get('asset_id'),where)
        if kind=='context' and p.get('note_type')=='correction':
            target=context_target(p)
            if target is None: raise ValueError(f'context correction missing inspection target at {where}')
            ref('inspection',target,where)
            if known['inspection',target]['asset_id']!=p['asset_id']: raise ValueError(f'cross-well context inspection reference at {where}')
        if kind=='well':
            if path.split('/')[1]!=ident: raise ValueError('well ID/path mismatch')
            if p['well_type'] not in valid_types: raise ValueError(f'unknown well type {p["well_type"]}')
            for coord,lo,hi in [('lat',-90,90),('lon',-180,180)]:
                v=p['location'][coord]
                if type(v) not in (float,int) or not math.isfinite(v) or not lo<=v<=hi: raise ValueError('invalid coordinates')
            ref('inspection',p.get('last_inspection',{}).get('inspection_id'),where)
            last=p.get('last_inspection',{})
            if last.get('inspector_user_id'): ref('user',last['inspector_user_id'],where)
            if last.get('inspected_at'): timestamp(last['inspected_at'])
            if last.get('inspection_id') and known['inspection',last['inspection_id']]['asset_id']!=ident: raise ValueError('last inspection belongs to another well')
            # A well's own team_id/team_history takes priority over its area's team, so one area
            # can hold wells run by two teams (test dataset README). Only require a known team.
            if p.get('team_id') and ('team', p['team_id']) not in known: raise ValueError('unknown well team')
            for change in p.get('team_history') or []:
                ref('team', change.get('team_id'), where)
            for change in p.get('type_history') or []:
                if change.get('well_type') not in types: raise ValueError('unknown historical well type')
        if kind=='inspection':
            if type(p['spill_detected']) is not bool: raise ValueError('spill_detected must be boolean')
            for key in ('wellhead_temp_c','ambient_temp_c','inspected_at','inspector_user_id'): 
                if p.get(key) is None: raise ValueError(f'missing {key}')
            for image in p.get('evidence_images',[]): safe_relative(image)
        if kind=='area':
            for asset in p.get('asset_ids',[]): ref('well',asset,where)
        if kind=='maintenance':
            if p.get('completed_at') and timestamp(p['completed_at']) < timestamp(p['started_at']): raise ValueError('completion before start')
            cost=p['cost_usd']
            for v in cost.values():
                if type(v) not in (int,float) or not math.isfinite(v) or v<0: raise ValueError('invalid cost')
            if p.get('report_file'):
                safe_relative(p['report_file'])
                report=(PurePosixPath(path).parent/p['report_file']).as_posix()
                if report not in files: raise ValueError(f'missing report {report}')
        if kind in {'inspection','maintenance','context','regulator'} and path.split('/')[1]!=p['asset_id']: raise ValueError('record asset/path mismatch')
    return files,records


def safe_relative(path):
    p=PurePosixPath(path.replace('\\','/'))
    if p.is_absolute() or '..' in p.parts or ':' in path: raise ValueError(f'unsafe path {path}')


def context_target(payload):
    inline=set(re.findall(r'\bINS-[\w-]+\b',payload.get('text','')))
    inline.update(re.findall(r'\binspection\s+(?:ID\s+)?([A-Za-z0-9]+(?:-[A-Za-z0-9]+)+)\b',payload.get('text',''),re.I))
    explicit=payload.get('inspection_id')
    if explicit: inline.add(explicit)
    if len(inline)>1: raise ValueError('ambiguous context inspection targets')
    return next(iter(inline),None)


def install_search(session):
    if session.bind.dialect.name != 'postgresql': return
    session.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))
    session.execute(text('ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS embedding_vector vector(384)'))
    session.execute(text("ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS search_vector tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED"))
    session.execute(text('CREATE INDEX IF NOT EXISTS ix_chunks_fts ON document_chunks USING gin(search_vector)'))
    session.execute(text('CREATE INDEX IF NOT EXISTS ix_chunks_vector ON document_chunks USING hnsw (embedding_vector vector_cosine_ops)'))


def upsert_projections(session, model, rows):
    if not rows: return
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    insert=pg_insert if session.bind.dialect.name=='postgresql' else sqlite_insert
    # Keep each statement comfortably below both database parameter limits.
    for start in range(0,len(rows),100):
        statement=insert(model).values(rows[start:start+100])
        session.execute(statement.on_conflict_do_update(index_elements=['id'],set_={c.name:getattr(statement.excluded,c.name) for c in model.__table__.columns if c.name!='id'}))


def projection_hash(session):
    """Compare effective materialized truth when pointer identities alone do not change."""
    checksum=hashlib.sha256()
    for model in (WellFact,InspectionFact,MaintenanceFact,RegulatorFact):
        checksum.update(model.__tablename__.encode())
        for row in session.execute(select(*model.__table__.columns).order_by(model.id)):
            checksum.update(json.dumps(tuple(row),default=str,separators=(',',':')).encode())
    return checksum.hexdigest()


def ingest_dataset(session, root: Path, revision=None, no_embeddings=False):
    root=Path(root)
    batch=ImportBatch(revision=revision or 'pending',root=str(root),manifest_hash='pending',status='validating')
    session.add(batch); session.flush()
    try:
        files,records=prepare(root,session)
        manifest=digest('\n'.join(f'{p}:{digest(c)}' for p,c in sorted(files.items())))
        batch.manifest_hash=manifest
        if not revision:
            try: revision=subprocess.run(['git','-C',str(root),'rev-parse','HEAD'],capture_output=True,text=True,check=True,timeout=5).stdout.strip()
            except (subprocess.SubprocessError,OSError): revision=manifest
        batch.revision=revision
        # All writes are within a savepoint. A failure retains only the diagnostic batch.
        with session.begin_nested():
            install_search(session)
            existing={(s.path,s.hash):s for s in session.scalars(select(SourceVersion))}
            sources={}; added_sources=[]
            for path,content in files.items():
                key=(path,digest(content))
                source=existing.get(key)
                if source is None:
                    source=SourceVersion(id=new_id(),path=path,hash=key[1],content=content,revision=revision,batch_id=batch.id)
                    session.add(source); added_sources.append(source)
                sources[path]=source
            session.flush()
            old_records={(r.kind,r.record_id,r.source_id):r for r in session.scalars(select(RecordVersion))}
            active={(a.kind,a.record_id):a for a in session.scalars(select(ActiveRecord))}
            versions={}; changed_sources=set()
            for kind,ident,p,path,line in records:
                source=sources[path]; r=old_records.get((kind,ident,source.id))
                if r is None:
                    r=RecordVersion(id=new_id(),kind=kind,record_id=ident,asset_id=p.get('asset_id'),payload=p,source_id=source.id,line_number=line,batch_id=batch.id)
                    session.add(r)
                versions[kind,ident]=r
            session.flush()
            for (kind,ident),r in versions.items():
                pointer=active.get((kind,ident))
                if pointer:
                    if pointer.version_id!=r.id: changed_sources.add(r.source_id)
                    pointer.version_id=r.id
                else:
                    session.add(ActiveRecord(kind=kind,record_id=ident,version_id=r.id)); changed_sources.add(r.source_id)
            session.flush()
            before_normalized=projection_hash(session) if not changed_sources else None
            for source in added_sources:
                if source.path.endswith('.md'):
                    for heading,start,end,body in chunks(source.content): session.add(DocumentChunk(source_id=source.id,heading=heading,text=body,start_line=start,end_line=end))
                    for key,well_type,value,start,end in extracted_rules(source.path,source.content): session.add(Rule(rule_key=key,well_type=well_type,value=value,source_id=source.id,start_line=start,end_line=end,batch_id=batch.id))
            session.flush()
            # Build current projections. Shared metadata from prior disjoint batches remains available.
            current={(r.kind,r.record_id):r for r in session.scalars(select(RecordVersion).join(ActiveRecord,ActiveRecord.version_id==RecordVersion.id))}
            well_rows=[]
            for (kind,ident),r in current.items():
                if kind!='well': continue
                p=r.payload; area=current['area',p['area_id']].payload
                well_rows.append(dict(id=ident,version_id=r.id,well_type=p['well_type'],area_id=p['area_id'],area_name=area['name'],lat=p['location']['lat'],lon=p['location']['lon'],recorded_status=p['recorded_status']))
            upsert_projections(session,WellFact,well_rows)
            inspection_rows=[]; maintenance_rows=[]; regulator_rows=[]; facts_pending=[]; extraction_warnings=[]
            for kind,ident,p,path,line in records:
                r=versions[kind,ident]
                if kind=='inspection':
                    inspection_rows.append(dict(id=ident,version_id=r.id,well_id=p['asset_id'],inspected_at=timestamp(p['inspected_at']),inspector_id=p['inspector_user_id'],**{k:p.get(k) for k in ('ambient_temp_c','wellhead_temp_c','spill_detected','spill_est_volume_bbl','spill_area_pct')}))
                elif kind=='maintenance':
                    hours=None; report_version=None
                    if p.get('report_file'):
                        report_path=(PurePosixPath(path).parent/p['report_file']).as_posix()
                        report=versions['document',report_path]; report_version=report.id
                        match=re.search(r'(?:contained|containment).*?(?:about|after|within)\s+(\d+(?:\.\d+)?)\s*hours',plain(files[report_path]),re.I)
                        if match: hours=float(match.group(1))
                        elif p.get('triggered_by_inspection_id'): extraction_warnings.append(f'{report_path}: containment time not extracted; retained as unknown')
                        facts={'maintenance_id':ident,'asset_id':p['asset_id'],'inspection_id':p.get('triggered_by_inspection_id'),'containment_hours':hours,'compliance':[]}
                        for n,l in enumerate(files[report_path].splitlines(),1):
                            cells=[plain(c) for c in l.strip().strip('|').split('|')]
                            if len(cells)>=3 and re.fullmatch(r'(SR|WS|RC)-\d+',cells[0]): facts['compliance'].append({'protocol':cells[0],'result':cells[1],'detail':cells[2],'line':n})
                        # Derivations depend on both the report source and maintenance version/link.
                        factid=ident+':report:'+r.id
                        previous_fact=old_records.get(('report_fact',factid,report.source_id))
                        if previous_fact is None:
                            fact=RecordVersion(id=new_id(),kind='report_fact',record_id=factid,asset_id=p['asset_id'],payload=facts,source_id=report.source_id,line_number=1,batch_id=batch.id)
                            session.add(fact); facts_pending.append(fact)
                        else: facts_pending.append(previous_fact)
                    maintenance_rows.append(dict(id=ident,version_id=r.id,well_id=p['asset_id'],started_at=timestamp(p['started_at']),completed_at=timestamp(p['completed_at']) if p.get('completed_at') else None,maintenance_type=p['maintenance_type'],equipment_kind=p['equipment_kind'],inspection_id=p.get('triggered_by_inspection_id'),cost_usd=p['cost_usd']['total'],containment_hours=hours,report_version_id=report_version))
                elif kind=='regulator':
                    regulator_rows.append(dict(id=ident,version_id=r.id,well_id=p['asset_id'],event_date=datetime.combine(date.fromisoformat(p['date']),datetime.min.time()),inspection_id=p.get('related_inspection_id'),event_type=p['event_type'],protocol_id=p.get('protocol_id'),status=p['status'],hours_to_report=p.get('hours_to_report'),fine_usd=p.get('fine_usd',0)))
                elif kind=='context' and p.get('note_type')=='data_correction' and p.get('field') in {'wellhead_temp_c','ambient_temp_c','spill_est_volume_bbl','spill_area_pct','spill_detected'} and p.get('inspection_id'):
                    # A formal correction to one field of one inspection. It is source data, not a
                    # chat claim: promote it once, idempotently, so every later answer uses the
                    # corrected value and the original stays in its immutable record version.
                    inspection=p['inspection_id']; field=p['field']; value=p['corrected_value']
                    key=digest(json.dumps([ident,inspection,field,value],default=str))
                    if session.get(ContextCorrectionIdentity,key) is None:
                        correction=Correction(id=new_id(),target_kind='inspection',target_id=inspection,field=field,value=value,original_value=p.get('original_value'),scope_kind='inspection',scope_id=inspection,author_id=p['author_user_id'],reason=p.get('text') or 'data_correction note',status='accepted',source_id=r.source_id)
                        session.add(correction); session.flush(); changed_sources.add(r.source_id)
                        session.add(ContextCorrectionIdentity(key=key,note_id=ident,correction_id=correction.id))
                elif kind=='context' and p.get('note_type')=='correction' and re.search(r'not (?:a (?:crude |oil )?spill|crude|oil)|no (?:crude|oil|spill)',p['text'],re.I):
                    inspection=context_target(p)
                    key=digest(json.dumps([ident,inspection,'spill_detected',False]))
                    identity=session.get(ContextCorrectionIdentity,key)
                    if inspection and identity is None:
                        # Adopt existing pre-identity rows, including superseded rows, without resurrecting them.
                        historical_sources=select(RecordVersion.source_id).where(RecordVersion.kind=='context',RecordVersion.record_id==ident)
                        candidates=session.scalars(select(Correction).where(Correction.source_id.in_(historical_sources),Correction.target_id==inspection,Correction.field=='spill_detected').order_by(Correction.created_at,Correction.id))
                        correction=next((candidate for candidate in candidates if candidate.value is False),None)
                        if correction is None:
                            correction=Correction(id=new_id(),target_kind='inspection',target_id=inspection,field='spill_detected',value=False,original_value=current['inspection',inspection].payload['spill_detected'],scope_kind='inspection',scope_id=inspection,author_id=p['author_user_id'],reason=p['text'],status='accepted',source_id=r.source_id)
                            session.add(correction); session.flush(); changed_sources.add(r.source_id)
                        session.add(ContextCorrectionIdentity(key=key,note_id=ident,correction_id=correction.id))
            session.flush()
            for fact in facts_pending:
                # Keep one active derived report per maintenance; historical dependency versions persist.
                prefix=fact.payload['maintenance_id']+':report'
                for (old_kind,old_ident),old_pointer in list(active.items()):
                    if old_kind=='report_fact' and (old_ident==prefix or old_ident.startswith(prefix+':')) and old_ident!=fact.record_id:
                        session.delete(old_pointer); active.pop((old_kind,old_ident)); changed_sources.add(fact.source_id)
                pointer=active.get(('report_fact',fact.record_id))
                if pointer:
                    if pointer.version_id!=fact.id: changed_sources.add(fact.source_id)
                    pointer.version_id=fact.id
                else:
                    session.add(ActiveRecord(kind='report_fact',record_id=fact.record_id,version_id=fact.id)); changed_sources.add(fact.source_id)
            upsert_projections(session,InspectionFact,inspection_rows)
            upsert_projections(session,MaintenanceFact,maintenance_rows)
            upsert_projections(session,RegulatorFact,regulator_rows)
            session.expire_all()
            from app.knowledge import apply_corrections
            apply_corrections(session)
            if before_normalized is not None and before_normalized!=projection_hash(session):
                changed_sources.update(source.id for source in sources.values())
            batch.counts=dict(Counter(k for k,*_ in records)); batch.counts['embedding_status']='deferred_full_text'
            batch.counts['warnings']=extraction_warnings+[f'No structured extraction for {s.path}' for s in added_sources if '/well-types/' in s.path and not any(extracted_rules(s.path,s.content))]
            if changed_sources:
                session.add(Outbox(event_type='knowledge.published',payload={'batch_id':batch.id,'source_ids':sorted(changed_sources)}))
            if added_sources:
                if not no_embeddings: session.add(Outbox(event_type='embeddings.requested',payload={'batch_id':batch.id,'model':'all-MiniLM-L6-v2','dimensions':384,'status':'deferred'}))
            batch.status='published'
        session.commit()
    except Exception as exc:
        batch.status='failed'; batch.error=f'{type(exc).__name__}: {exc}'; session.commit()
    return batch


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('root',type=Path); parser.add_argument('--revision'); parser.add_argument('--no-embeddings',action='store_true')
    args=parser.parse_args(); init_db()
    with SessionLocal() as session:
        result=ingest_dataset(session,args.root,args.revision,args.no_embeddings)
        print(json.dumps({'id':result.id,'status':result.status,'counts':result.counts,'error':result.error}))
        if result.status=='failed': raise SystemExit(1)
