from datetime import date
from pathlib import Path
import os

import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from app.db import Base
from app.ingestion import ingest_dataset
from app.knowledge import AssetKnowledge, QuerySpec
from app.models import SourceVersion, ImportBatch

ROOT = Path(__file__).resolve().parents[2] / 'assets/flytbase-dataset/sample-data'


@pytest.fixture(scope='module')
def seeded():
    if os.environ.get('KNOWLEDGE_TEST_POSTGRES') == '1':
        from sqlalchemy.engine import make_url
        from app.config import get_settings
        engine=create_engine(make_url(get_settings().database_url).set(host='127.0.0.1'))
    else:
        engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        batch = ingest_dataset(session, ROOT)
        assert batch.status == 'published', batch.error
        yield engine


@pytest.fixture
def imported(seeded):
    with seeded.connect() as connection:
        connection.exec_driver_sql('BEGIN')
        with Session(connection, expire_on_commit=False, join_transaction_mode='create_savepoint') as session:
            yield session
        connection.rollback()


def ask(session, operation, **kwargs):
    return AssetKnowledge(session).query({'operation': operation, **kwargs}).model_dump(mode='json')


def rows(answer):
    return answer['visual']['data']


def test_contract_and_idempotence(imported):
    with pytest.raises(ValueError):
        QuerySpec(operation='status', invented=True)
    with pytest.raises(ValueError):
        QuerySpec(operation='invented')
    before = imported.scalar(select(func.count()).select_from(SourceVersion))
    assert ingest_dataset(imported, ROOT).status == 'published'
    assert imported.scalar(select(func.count()).select_from(SourceVersion)) == before
    assert len(rows(ask(imported, 'status'))) == 200


def test_status_temperature_downtime(imported):
    status = ask(imported, 'status', well_ids=['WELL-0001'])
    row = rows(status)[0]
    assert row['producing'] is False
    assert row['inspector'] == 'Ryan Brooks'
    assert row['stale_recorded_status'] is True
    assert 'rod string' in row['reason'].lower()
    answer = ask(imported, 'status', area='Northeast Block 8', producing=False)
    assert answer['selected_well_ids'] == ['WELL-0164', 'WELL-0170', 'WELL-0172', 'WELL-0175']
    assert rows(answer)[0]['reason'] == 'No recorded reason'
    assert len(rows(ask(imported, 'temperatures', well_ids=['WELL-0001'], start='2026-07-23', end='2026-10-16'))) == 13
    down = ask(imported, 'downtime', well_ids=['WELL-0001'], start='2025-01-01', end='2025-12-31')
    assert rows(down)[0]['downtime_days'] == 21
    ranked = ask(imported, 'downtime', area='NE-07', start='2026-06-16', end='2026-10-16', limit=3)
    assert [(r['well_id'], r['downtime_days']) for r in rows(ranked)] == [('WELL-0121',49),('WELL-0138',42),('WELL-0107',42)]


def test_spills_containment_compliance(imported):
    spills = ask(imported, 'spills', well_ids=['WELL-0001'], start='2022-10-16', end='2026-10-16')
    assert len(rows(spills)) == 6
    assert round(sum(r['volume_bbl'] for r in rows(spills)), 1) == 15.1
    pins = ask(imported, 'spills', area='NE-08', start='2026-07-18', end='2026-10-16', visual='map')
    assert len(rows(pins)) == 4
    heat = ask(imported, 'spills', start='2026-01-01', end='2026-10-16', visual='heatmap')
    totals = {}
    for r in rows(heat): totals[r['area']] = totals.get(r['area'], 0) + r['count']
    assert totals == {'Southwest Block 23':35,'Southwest Block 24':43,'Northeast Block 7':37,'Northeast Block 8':26}
    late = ask(imported, 'containment', area='SW-24', start='2026-07-18', end='2026-10-16')
    assert [(r['well_id'], r['containment_hours']) for r in rows(late)] == [('WELL-0082',7.1),('WELL-0100',8.1)]
    comp = ask(imported, 'compliance', well_ids=['WELL-0001'], start='2025-10-17', end='2026-10-17')
    assert {r['protocol'] for r in rows(comp) if r['status'] in ('breach','possible breach')} == {'SR-01','SR-02','SR-03','RC-04'}
    assert sum(r.get('fine_usd',0) for r in rows(comp)) == 5000
    disagreement = ask(imported, 'spills', well_ids=['WELL-0101'], start='2026-08-20', end='2026-08-20')
    assert len(rows(disagreement)) == 1
    assert len(disagreement['conflicts']) >= 1


def test_feedback_guidance_and_rca(imported):
    knowledge = AssetKnowledge(imported)
    initial = ask(imported, 'rca', area='NE-07', equipment_kind='pump_jack', start='2025-10-17')
    assert initial['selected_well_ids'] == ['WELL-0108','WELL-0121','WELL-0138']
    knowledge.add_feedback({'kind':'rule','target_id':'T350','field':'rca_threshold','value':2,'equipment_kind':'pump_jack','author_id':'U-201','reason':'Team requirement'})
    changed = ask(imported, 'rca', area='NE-07', equipment_kind='pump_jack', start='2025-10-17')
    assert changed['selected_well_ids'] == ['WELL-0108','WELL-0120','WELL-0121','WELL-0138']
    correction = knowledge.add_feedback({'kind':'correction','target_id':'INS-0164-0205','field':'wellhead_temp_c','value':41.0,'author_id':'U-201','reason':'Faulty gun, crew remeasured','unit':'C'})
    changed = ask(imported, 'status', well_ids=['WELL-0164'])
    assert rows(changed)[0]['producing'] is True
    assert changed['conflicts']
    assert ask(imported,'status',area='NE-08',producing=False)['selected_well_ids']==['WELL-0170','WELL-0172','WELL-0175']
    before=ask(imported,'guidance',well_ids=['WELL-0151'],start='2026-09-24',end='2026-09-24',query='spill response')
    assert not any(r.get('well_id') and r.get('protocol')=='SR-01' for r in rows(before))
    knowledge.add_feedback({'kind':'correction','target_id':'INS-0151-0201','field':'spill_est_volume_bbl','value':5.4,'author_id':'U-201','reason':'Measured volume','unit':'bbl'})
    guide = ask(imported, 'guidance', well_ids=['WELL-0151'], start='2026-09-24', end='2026-09-24', query='spill repair')
    assert any(r.get('protocol') == 'SR-01' and r.get('due_at','').startswith('2026-09-25T15:30') for r in rows(guide))
    assert any(r.get('protocol') == 'SR-03' and r.get('due_at','').startswith('2026-11-23') for r in rows(guide))
    assert any(r.get('protocol') == 'WS-02' for r in rows(guide))
    assert all(r['evidence_ids'] for r in rows(guide))
    compliance=ask(imported,'compliance',well_ids=['WELL-0151'],start='2026-09-24',end='2026-10-17')
    assert any(r['protocol']=='SR-01' and r['status']=='possible breach' for r in rows(compliance))
    assert any(r['protocol']=='SR-03' and r['status']=='pending' for r in rows(compliance))
    knowledge.add_feedback({'kind':'correction','target_id':'INS-0164-0205','field':'wellhead_temp_c','value':20.0,'author_id':'U-202','reason':'Other measurement','unit':'C'})
    disputed = ask(imported, 'status', well_ids=['WELL-0164'])
    assert rows(disputed)[0]['wellhead_temp_c'] == 41.0
    assert disputed['conflicts']
    knowledge.add_feedback({'kind':'correction','target_id':'INS-0164-0205','field':'wellhead_temp_c','value':41.0,'author_id':'U-201','reason':'Confirmed calibration','unit':'C','supersedes':correction['id']})
    assert rows(ask(imported,'status',well_ids=['WELL-0164']))[0]['producing'] is True
    knowledge.add_feedback({'kind':'claim','target_id':'WELL-0175','value':'The well is running fine','author_id':'U-203','reason':'Operator claim'})
    claim=ask(imported,'status',well_ids=['WELL-0175'])
    assert rows(claim)[0]['producing'] is False and claim['conflicts']


def test_general_and_reportable_spill_guidance(imported):
    general=ask(imported,'guidance',query='spill response')
    assert rows(general) and not any(r.get('due_at') for r in rows(general))
    guide=ask(imported,'guidance',well_ids=['WELL-0001'],start='2026-06-11',end='2026-06-11',query='spill response')
    assert any(r.get('protocol')=='SR-01' and r.get('due_at','').startswith('2026-06-12') for r in rows(guide))
    assert any(r.get('protocol')=='SR-03' and r.get('due_at','').startswith('2026-08-10') for r in rows(guide))
    assert any('T200' in e['path'] for e in guide['evidence'])
    deeper=ask(imported,'guidance',well_ids=['WELL-0138'],query='repair shut-in')
    assert any('T350' in e['path'] for e in deeper['evidence'])
    assert any('T200' in e['path'] for e in deeper['evidence'])


def test_invalid_import_retains_diagnostic_without_publication(imported, tmp_path):
    (tmp_path/'fleet').mkdir()
    (tmp_path/'fleet/users.json').write_text('{bad', encoding='utf-8')
    count = imported.scalar(select(func.count()).select_from(SourceVersion))
    failed = ingest_dataset(imported, tmp_path)
    assert failed.status == 'failed' and failed.error
    assert imported.scalar(select(func.count()).select_from(SourceVersion)) == count
    assert len(rows(ask(imported, 'status'))) == 200

