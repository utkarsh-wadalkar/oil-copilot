import json
import os
from uuid import uuid4
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from app.db import Base
from app.ingestion import ingest_dataset, chunks
from app.knowledge import AssetKnowledge
from app.models import SourceVersion, RecordVersion, ActiveRecord, Outbox


def dataset(root, well='ASSET-A', temp=40, duplicate=False):
    def write(path, value):
        target=root/path; target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(value if isinstance(value,str) else json.dumps(value),encoding='utf-8')
    write('fleet/users.json',{'users':[{'user_id':'USER-A','name':'Author','team_id':'TEAM-A'}]})
    write('fleet/areas.json',{'areas':[{'area_id':'AREA-A','name':'Area','team_id':'TEAM-A','asset_ids':[well]}],'teams':[{'team_id':'TEAM-A','name':'Team','lead_user_id':'USER-A'}]})
    write('fleet/well-types/TYPE-A.md','# TYPE-A\n## Production temperature rule\nProducing when at least **17 °C above\nambient**.\n## Maintenance escalation\nThree or more corrective maintenance events in 12 months require RCA.\n')
    write(f'assets/{well}/metadata.json',{'asset_id':well,'well_type':'TYPE-A','area_id':'AREA-A','team_id':'TEAM-A','in_charge_user_id':'USER-A','location':{'lat':10,'lon':20},'recorded_status':'active','last_inspection':{'inspection_id':f'READING-{well}'}})
    reading={'inspection_id':f'READING-{well}','asset_id':well,'inspected_at':'2026-10-15T12:00:00Z','inspector_user_id':'USER-A','wellhead_temp_c':temp,'ambient_temp_c':20,'spill_detected':False,'spill_est_volume_bbl':None,'spill_area_pct':None}
    line=json.dumps(reading)+'\n'
    write(f'assets/{well}/inspections.jsonl',line*(2 if duplicate else 1))


@pytest.fixture
def session():
    if os.environ.get('KNOWLEDGE_REVIEW_POSTGRES')=='1':
        from sqlalchemy import text
        from sqlalchemy.engine import make_url
        from app.config import get_settings
        engine=create_engine(make_url(get_settings().database_url).set(host='127.0.0.1'))
        schema='task2_review_'+uuid4().hex
        with engine.connect() as connection:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}", public')
            connection=connection.execution_options(schema_translate_map={None:schema})
            Base.metadata.create_all(connection)
            with Session(connection,expire_on_commit=False,join_transaction_mode='create_savepoint') as result: yield result
            connection.rollback()
        engine.dispose()
        return
    engine=create_engine('sqlite://'); Base.metadata.create_all(engine)
    with Session(engine,expire_on_commit=False) as result: yield result


def test_immutable_reimport_rollback_and_disjoint_merge(session,tmp_path):
    first=tmp_path/'first'; dataset(first)
    assert ingest_dataset(session,first,revision='one').status=='published'
    old=session.scalar(select(SourceVersion).where(SourceVersion.path=='assets/ASSET-A/inspections.jsonl'))
    old_content=old.content; old_id=old.id
    dataset(first,temp=21)
    assert ingest_dataset(session,first,revision='two').status=='published'
    assert session.get(SourceVersion,old_id).content==old_content
    assert session.scalar(select(func.count()).select_from(SourceVersion).where(SourceVersion.path=='assets/ASSET-A/inspections.jsonl'))==2
    status=AssetKnowledge(session).query({'operation':'status','well_ids':['ASSET-A']})
    assert status.visual.data[0]['producing'] is False
    dataset(first,temp='bad')
    count=session.scalar(select(func.count()).select_from(SourceVersion))
    failed=ingest_dataset(session,first,revision='bad')
    assert failed.status=='failed' and 'numeric' in failed.error
    assert session.scalar(select(func.count()).select_from(SourceVersion))==count
    assert AssetKnowledge(session).query({'operation':'status'}).visual.data[0]['wellhead_temp_c']==21
    second=tmp_path/'second'; dataset(second,well='ASSET-B')
    assert ingest_dataset(session,second,revision='three').status=='published'
    assert len(AssetKnowledge(session).query({'operation':'status'}).visual.data)==2
    assert session.scalar(select(func.count()).select_from(Outbox))>=3


def test_duplicate_and_bad_reference_rejected(session,tmp_path):
    dataset(tmp_path,duplicate=True)
    assert 'duplicate' in ingest_dataset(session,tmp_path,revision='bad').error
    assert session.scalar(select(func.count()).select_from(ActiveRecord))==0
    dataset(tmp_path)
    path=tmp_path/'assets/ASSET-A/inspections.jsonl'
    path.write_text(path.read_text().replace('USER-A','MISSING'),encoding='utf-8')
    assert 'reference' in ingest_dataset(session,tmp_path,revision='bad').error


def test_guidance_missing_sop_and_manual_applicability(session,tmp_path):
    dataset(tmp_path)
    assert ingest_dataset(session,tmp_path,revision='one').status=='published'
    answer=AssetKnowledge(session).query({'operation':'guidance','well_ids':['ASSET-A'],'query':'spill response'})
    assert any('Missing Spill Response SOP' in warning for warning in answer.warnings)
    assert not any(row.get('well_type')=='T200' for row in answer.visual.data)


def test_chunk_bounds_and_line_evidence():
    content='# Heading\n'+('wrapped sentence words '*300)+'\n## Next\nShort paragraph.'
    found=list(chunks(content))
    assert len(found)>2
    assert all(len(body.split())<=100 for _,_,_,body in found)
    assert all(1<=start<=end<=len(content.splitlines()) for _,start,end,_ in found)
