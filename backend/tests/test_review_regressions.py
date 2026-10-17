"""Small review regressions: publication, consistent filters, and durable corrections."""
import json
from datetime import date

from sqlalchemy import func, select

from app.domain import InspectionFact
from app.ingestion import ingest_dataset
from app.knowledge import AssetKnowledge
from app.models import ActiveRecord, Correction, Outbox, RecordVersion
from test_ingestion_lifecycle import dataset, session


def write(root,path,rows):
    target=root/path; target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text('\n'.join(json.dumps(r) for r in rows)+'\n',encoding='utf-8')


def feedback(k,value,**extra):
    return k.add_feedback({'kind':'correction','target_id':'READING-ASSET-A','field':'wellhead_temp_c','value':value,'unit':'C','author_id':'USER-A','reason':'Confirmed measurement',**extra})


def test_dispute_retains_last_accepted_and_survives_reimport(session,tmp_path):
    dataset(tmp_path); ingest_dataset(session,tmp_path,revision='one'); k=AssetKnowledge(session)
    accepted=feedback(k,55); feedback(k,60)
    assert session.get(InspectionFact,'READING-ASSET-A').wellhead_temp_c==55
    assert k.query({'operation':'status'}).conflicts
    ingest_dataset(session,tmp_path,revision='same')
    assert session.get(InspectionFact,'READING-ASSET-A').wellhead_temp_c==55
    feedback(k,58,supersedes=accepted['id'])
    assert session.get(InspectionFact,'READING-ASSET-A').wellhead_temp_c==58


def test_historical_source_reactivation_publishes_once(session,tmp_path):
    dataset(tmp_path,temp=40); ingest_dataset(session,tmp_path,revision='a')
    dataset(tmp_path,temp=21); ingest_dataset(session,tmp_path,revision='b')
    before=session.scalar(select(func.count()).select_from(Outbox).where(Outbox.event_type=='knowledge.published'))
    dataset(tmp_path,temp=40); ingest_dataset(session,tmp_path,revision='a-again')
    after=session.scalar(select(func.count()).select_from(Outbox).where(Outbox.event_type=='knowledge.published'))
    assert after==before+1
    ingest_dataset(session,tmp_path,revision='noop')
    assert session.scalar(select(func.count()).select_from(Outbox).where(Outbox.event_type=='knowledge.published'))==after


def test_normalization_repair_publishes_even_when_sources_unchanged(session,tmp_path):
    dataset(tmp_path); ingest_dataset(session,tmp_path,revision='one')
    session.get(InspectionFact,'READING-ASSET-A').wellhead_temp_c=21
    session.commit()
    before=session.scalar(select(func.count()).select_from(Outbox).where(Outbox.event_type=='knowledge.published'))
    ingest_dataset(session,tmp_path,revision='normalization-repair')
    assert session.get(InspectionFact,'READING-ASSET-A').wellhead_temp_c==40
    assert session.scalar(select(func.count()).select_from(Outbox).where(Outbox.event_type=='knowledge.published'))==before+1


def test_report_fact_tracks_changed_maintenance_inspection_link(session,tmp_path):
    spill_dataset(tmp_path)
    report=tmp_path/'assets/ASSET-A/maintenance-reports/custom-name.md'; report.parent.mkdir(parents=True); report.write_text('# Repair\nContained about 7 hours after inspection.\n',encoding='utf-8')
    maintenance={'maintenance_id':'M1','asset_id':'ASSET-A','completed_at':None,'maintenance_type':'corrective','equipment_kind':'flowline','started_at':'2026-10-15T13:00:00Z','technician_user_id':'USER-A','triggered_by_inspection_id':'READING-ASSET-A','issue':'Repair','report_file':'maintenance-reports/custom-name.md','cost_usd':{'total':100}}
    write(tmp_path,'assets/ASSET-A/maintenance.jsonl',[maintenance]); ingest_dataset(session,tmp_path,revision='one')
    maintenance['triggered_by_inspection_id']='READING-B'
    write(tmp_path,'assets/ASSET-A/maintenance.jsonl',[maintenance]); assert ingest_dataset(session,tmp_path,revision='two').status=='published'
    facts=list(session.scalars(select(RecordVersion).join(ActiveRecord,ActiveRecord.version_id==RecordVersion.id).where(RecordVersion.kind=='report_fact')))
    assert len(facts)==1 and facts[0].payload['inspection_id']=='READING-B'
    assert session.scalar(select(func.count()).select_from(RecordVersion).where(RecordVersion.kind=='report_fact'))==2


def test_inline_correction_cannot_target_another_well(session,tmp_path):
    dataset(tmp_path/'base'); ingest_dataset(session,tmp_path/'base',revision='base')
    dataset(tmp_path/'other',well='ASSET-B')
    path=tmp_path/'other/assets/ASSET-B/inspections.jsonl'
    path.write_text(path.read_text().replace('READING-ASSET-B','INS-B'),encoding='utf-8')
    meta=tmp_path/'other/assets/ASSET-B/metadata.json'; meta.write_text(meta.read_text().replace('READING-ASSET-B','INS-B'),encoding='utf-8')
    ingest_dataset(session,tmp_path/'other',revision='other')
    write(tmp_path/'base','assets/ASSET-A/context.jsonl',[{'note_id':'NOTE-A','asset_id':'ASSET-A','author_user_id':'USER-A','created_at':'2026-10-15T15:00:00Z','note_type':'correction','text':'Inspection INS-B was water, not crude.'}])
    failed=ingest_dataset(session,tmp_path/'base',revision='invalid')
    assert failed.status=='failed' and 'inspection' in failed.error.lower()
    assert session.scalar(select(func.count()).select_from(Correction))==0


def spill_dataset(root):
    dataset(root,temp=40)
    p=root/'assets/ASSET-A/inspections.jsonl'; row=json.loads(p.read_text())
    row.update(spill_detected=True,spill_est_volume_bbl=6,spill_area_pct=1)
    second={**row,'inspection_id':'READING-B','inspected_at':'2026-09-15T12:00:00Z','spill_est_volume_bbl':2,'wellhead_temp_c':21}
    write(root,'assets/ASSET-A/inspections.jsonl',[row,second])
    source=__import__('pathlib').Path(__file__).resolve().parents[2]/'assets/flytbase-dataset/sample-data/fleet/sops/spill-response-sop.md'
    (root/'fleet/sops').mkdir(parents=True,exist_ok=True)
    (root/'fleet/sops/spill-response-sop.md').write_text(source.read_text(encoding='utf-8'),encoding='utf-8')
    rc=source.with_name('regulatory-compliance-sop.md')
    (root/'fleet/sops/regulatory-compliance-sop.md').write_text(rc.read_text(encoding='utf-8'),encoding='utf-8')


def test_aggregate_filters_match_evidence_and_rows(session,tmp_path):
    spill_dataset(tmp_path)
    base={'asset_id':'ASSET-A','completed_at':None,'maintenance_type':'corrective','started_at':'2026-10-15T13:00:00Z','technician_user_id':'USER-A','triggered_by_inspection_id':None,'issue':'Repair','report_file':None}
    write(tmp_path,'assets/ASSET-A/maintenance.jsonl',[{**base,'maintenance_id':'M1','equipment_kind':'pump_jack','cost_usd':{'total':100}},{**base,'maintenance_id':'M2','equipment_kind':'flowline','cost_usd':{'total':200}}])
    assert ingest_dataset(session,tmp_path,revision='one').status=='published'
    k=AssetKnowledge(session)
    maintenance=k.query({'operation':'maintenance','equipment_kind':'pump_jack'})
    assert maintenance.calculations[0]['cost_usd']==100
    spills=k.query({'operation':'spills','producing':False})
    assert spills.calculations[-1]['spill_count']==len(spills.visual.data)==1
    heat=k.query({'operation':'spills','reportable_only':True,'producing':False,'visual':'heatmap','start':'2026-09-01','end':'2026-10-17'})
    assert sum(r['count'] for r in heat.visual.data)==0


def test_superseded_context_does_not_resurrect_after_unrelated_edit(session,tmp_path):
    spill_dataset(tmp_path)
    note={'note_id':'NOTE-A','asset_id':'ASSET-A','inspection_id':'READING-ASSET-A','author_user_id':'USER-A','created_at':'2026-10-15T15:00:00Z','note_type':'correction','text':'The observation is water, not crude.'}
    write(tmp_path,'assets/ASSET-A/context.jsonl',[note]); ingest_dataset(session,tmp_path,revision='one')
    original=session.scalar(select(Correction).where(Correction.field=='spill_detected'))
    AssetKnowledge(session).add_feedback({'kind':'correction','target_id':'READING-ASSET-A','field':'spill_detected','value':True,'author_id':'USER-A','reason':'Lab confirmed crude','supersedes':original.id})
    write(tmp_path,'assets/ASSET-A/context.jsonl',[note,{**note,'note_id':'NOTE-B','note_type':'operator_note','text':'Unrelated maintenance context'}])
    assert ingest_dataset(session,tmp_path,revision='two').status=='published'
    assert session.get(InspectionFact,'READING-ASSET-A').spill_detected is True
    assert session.scalar(select(func.count()).select_from(Correction))==2


def test_late_verification_and_well_level_nov_remain_breaches(session,tmp_path):
    spill_dataset(tmp_path)
    p=tmp_path/'assets/ASSET-A/inspections.jsonl'; records=[json.loads(l) for l in p.read_text().splitlines()]; records[0]['inspected_at']='2026-06-01T12:00:00Z'; write(tmp_path,'assets/ASSET-A/inspections.jsonl',records)
    base={'asset_id':'ASSET-A','agency':'Agency','fine_usd':0,'hours_to_report':None,'status':'closed'}
    write(tmp_path,'assets/ASSET-A/regulatory-events.jsonl',[
        {**base,'event_id':'E1','date':'2026-08-15','event_type':'site_inspection','protocol_id':'SR-03','related_inspection_id':'READING-ASSET-A','detail':'Remediation verified; site meets cleanup standard.'},
        {**base,'event_id':'E2','date':'2026-06-02','event_type':'notice_of_violation','protocol_id':'SR-01','related_inspection_id':None,'detail':'Well-level notice'},
        {**base,'event_id':'E3','date':'2026-08-20','event_type':'nov_response_filed','protocol_id':'RC-04','related_event_id':'E2','related_inspection_id':None,'detail':'Response filed'},
        {**base,'event_id':'E4','date':'2026-06-03','event_type':'notice_of_violation','protocol_id':'RC-02','related_inspection_id':None,'status':'open','detail':'Different well-level notice'},
    ])
    assert ingest_dataset(session,tmp_path,revision='one').status=='published'
    rows=AssetKnowledge(session).query({'operation':'compliance','well_ids':['ASSET-A'],'start':'2026-06-01'}).visual.data
    assert any(r['protocol']=='SR-03' and r['status']=='breach' and r.get('completion_status')=='completed late' for r in rows)
    assert any(r['protocol']=='RC-04' and r['status']=='breach' and r.get('completion_status')=='completed late' for r in rows)
    assert any(r['protocol']=='RC-04' and r.get('notice_id')=='E4' and r['status']=='possible breach' for r in rows)
