"""User-independent, deterministic SQL analytics and audited shared feedback."""
import calendar
import json
import re
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import and_, case, func, or_, select, text

from app.domain import (CorrectionState, FeedbackDetail, FeedbackSpec, InspectionFact, MaintenanceFact,
                        Operation, QuerySpec, RegulatorFact, WellFact)
from app.ingestion import digest, plain, sections
from app.models import (ActiveRecord, Correction, DocumentChunk, ImportBatch, Outbox,
                        RecordVersion, Rule, SourceVersion, new_id)
from app.schemas import AnswerEnvelope, EvidenceRef, Finding, VisualSpec


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def months_before(value, months):
    total=value.year*12+value.month-1-months
    year,month=divmod(total,12); month+=1
    return date(year,month,min(value.day,calendar.monthrange(year,month)[1]))


def correction_groups(session, target=None):
    stmt=select(Correction).where(Correction.target_kind=='inspection',Correction.status.in_(['accepted','disputed']))
    if target: stmt=stmt.where(Correction.target_id==target)
    groups={}
    for c in session.scalars(stmt): groups.setdefault((c.target_id,c.field),[]).append(c)
    return groups


def apply_corrections(session):
    """Apply agreed truth, retaining its durable acceptance pointer during disputes."""
    for (target,field),corrections in correction_groups(session).items():
        fact=session.get(InspectionFact,target)
        if not fact: continue
        values={json.dumps(c.value,sort_keys=True) for c in corrections}
        state=session.get(CorrectionState,(target,field))
        ordered=sorted(corrections,key=lambda c:(utc(c.created_at),c.id))
        if len(values)==1:
            accepted=ordered[-1]
            if state: state.value=accepted.value; state.correction_id=accepted.id
            else:
                state=CorrectionState(target_id=target,field=field,correction_id=accepted.id,value=accepted.value)
                session.add(state)
        elif state is None:
            # Bootstrap old databases without a state row from the first accepted assertion.
            accepted=next((c for c in ordered if c.status=='accepted'),ordered[0])
            state=CorrectionState(target_id=target,field=field,correction_id=accepted.id,value=accepted.value)
            session.add(state)
        value=state.value
        setattr(fact,field,value)
        for correction in corrections: correction.status='accepted' if len(values)==1 else 'disputed'
    session.flush()


class AssetKnowledge:
    def __init__(self, session, analysis_date=date(2026,10,17)):
        self.session=session; self.analysis_date=analysis_date

    def _records(self, kind, well_ids=None):
        stmt=select(RecordVersion).join(ActiveRecord,ActiveRecord.version_id==RecordVersion.id).where(RecordVersion.kind==kind)
        if well_ids is not None: stmt=stmt.where(RecordVersion.asset_id.in_(well_ids))
        return list(self.session.scalars(stmt))

    def _rules(self):
        # Rules are immutable; only the versions belonging to active documents govern current answers.
        if hasattr(self,'_rule_cache'): return self._rule_cache
        return list(self.session.scalars(select(Rule).join(RecordVersion,RecordVersion.source_id==Rule.source_id).join(ActiveRecord,ActiveRecord.version_id==RecordVersion.id).where(RecordVersion.kind=='document')))

    def _rule(self,key,well_type=None):
        rules=self._rules()
        found=next((r for r in rules if r.rule_key==key and r.well_type==well_type),None)
        if not found and well_type:
            parent=next((r for r in rules if r.rule_key=='inherits' and r.well_type==well_type),None)
            if parent: found=next((r for r in rules if r.rule_key==key and r.well_type==parent.value),None)
        return found

    def _value(self,key,well_type=None):
        rule=self._rule(key,well_type)
        if rule is None: raise ValueError(f'Missing source rule: {key} for {well_type or "fleet"}')
        return rule.value

    def _evidence(self, item):
        if isinstance(item,str): item=self.session.get(RecordVersion,item)
        if item is None: return []
        source=self.session.get(SourceVersion,item.source_id)
        start=getattr(item,'line_number',None) or getattr(item,'start_line',None) or 1
        end=getattr(item,'end_line',None) or start
        if isinstance(item,RecordVersion) and item.kind in {'well','document'}: end=len(source.content.splitlines())
        elif isinstance(item,RecordVersion) and item.kind in {'user','area','team'}:
            end=next((n for n,l in enumerate(source.content.splitlines(),1) if n>=start and l.strip().startswith('}')),start)
        excerpt='\n'.join(source.content.splitlines()[start-1:end])
        # Evidence excerpts are exact, immutable source slices. IDs remain server-resolvable.
        ident=f'{source.id}:{start}:{end}'
        ref=EvidenceRef(id=ident,source_id=source.id,record_id=getattr(item,'record_id',None),path=source.path,title=getattr(item,'rule_key',None) or getattr(item,'record_id',None) or source.path,excerpt=excerpt,start_line=start,end_line=end)
        self.evidence[ident]=ref
        return [ident]

    def _source_evidence(self,source_id,start=1,end=None,title=None):
        source=self.session.get(SourceVersion,source_id)
        end=end or len(source.content.splitlines())
        ident=f'{source.id}:{start}:{end}'
        self.evidence[ident]=EvidenceRef(id=ident,source_id=source.id,path=source.path,title=title or source.path,excerpt='\n'.join(source.content.splitlines()[start-1:end]),start_line=start,end_line=end)
        return [ident]

    def _correction_evidence(self,inspection_id):
        refs=[]
        for group in correction_groups(self.session,inspection_id).values():
            for c in group:
                refs+=self._source_evidence(c.source_id)
                author=self._user(c.author_id)
                if c.status=='disputed': self.conflicts.append({'target_id':inspection_id,'field':c.field,'value':c.value,'author':author,'status':'unresolved','message':'Incompatible formal corrections; last accepted effective value retained. Confirm with supersedes.','evidence_ids':refs[:]})
                else: self.calculations.append({'correction_id':c.id,'target_id':inspection_id,'field':c.field,'value':c.value,'original_value':c.original_value,'author':author,'evidence_ids':self._source_evidence(c.source_id)})
        return list(dict.fromkeys(refs))

    def _user(self,ident):
        if hasattr(self,'_user_records'):
            record=self._user_records.get(ident)
            if record: self._evidence(record)
            return record.payload['name'] if record else ident
        r=self.session.scalar(select(RecordVersion).join(ActiveRecord,ActiveRecord.version_id==RecordVersion.id).where(RecordVersion.kind=='user',RecordVersion.record_id==ident))
        return r.payload['name'] if r else ident

    def _well_stmt(self,q):
        stmt=select(WellFact)
        if q.well_ids is not None: stmt=stmt.where(WellFact.id.in_(q.well_ids))
        if q.area: stmt=stmt.where(or_(WellFact.area_id==q.area,WellFact.area_name==q.area))
        return stmt.order_by(WellFact.id)

    def _window(self,q,column,default_start=None):
        start=q.start or default_start
        end=min(q.end or self.analysis_date,self.analysis_date)
        clauses=[column < datetime.combine(end+timedelta(days=1),time.min)]
        if start: clauses.append(column >= datetime.combine(start,time.min))
        return clauses

    def _production_expression(self):
        # The numeric constants in SQL are bound parameters extracted from active manuals.
        types=list(self.session.scalars(select(WellFact.well_type).distinct()))
        threshold=case(*[(WellFact.well_type==kind,float(self._value('production_delta_c',kind))) for kind in types],else_=None)
        return InspectionFact.wellhead_temp_c-InspectionFact.ambient_temp_c >= threshold

    def _inspection_rows(self,q,latest=False,spills=False):
        stmt=select(InspectionFact,WellFact).join(WellFact,InspectionFact.well_id==WellFact.id).where(InspectionFact.well_id.in_(self.well_ids),*self._window(q,InspectionFact.inspected_at))
        if q.well_ids is not None: stmt=stmt.where(InspectionFact.well_id.in_(q.well_ids))
        if latest:
            rank=select(InspectionFact.id.label('id'),func.row_number().over(partition_by=InspectionFact.well_id,order_by=(InspectionFact.inspected_at.desc(),InspectionFact.id.desc())).label('rank')).where(*self._window(q,InspectionFact.inspected_at)).subquery()
            stmt=stmt.join(rank,rank.c.id==InspectionFact.id).where(rank.c.rank==1)
        if spills:
            stmt=stmt.where(InspectionFact.spill_detected.is_(True))
            if q.reportable_only: stmt=stmt.where(InspectionFact.spill_est_volume_bbl>=self._value('reportable_bbl'))
        if q.producing is not None: stmt=stmt.where(self._production_expression().is_(q.producing))
        return self.session.execute(stmt.order_by(WellFact.id,InspectionFact.inspected_at)).all()

    def _notes(self,well_id,inspection_id=None):
        notes=self._records('context',[well_id])
        if inspection_id:
            notes=[n for n in notes if n.payload.get('inspection_id')==inspection_id or inspection_id in n.payload.get('text','')]
        return notes

    def _reading(self,i,w):
        rule=self._rule('production_delta_c',w.well_type)
        record=self.session.get(RecordVersion,i.version_id)
        refs=self._evidence(record)+self._evidence(rule)+self._evidence(w.version_id)+self._correction_evidence(i.id)
        delta=round(i.wellhead_temp_c-i.ambient_temp_c,4)
        row={'well_id':w.id,'inspection_id':i.id,'date':i.inspected_at.date().isoformat(),'inspected_at':utc(i.inspected_at).isoformat(),'well_type':w.well_type,'wellhead_temp_c':i.wellhead_temp_c,'ambient_temp_c':i.ambient_temp_c,'delta_c':delta,'threshold_c':rule.value,'producing':delta>=rule.value,'inspector':self._user(i.inspector_id),'inspection_remark':record.payload.get('notes',''),'evidence_ids':refs}
        if 'not moving' in row['inspection_remark'].lower() and row['producing'] and self.session.scalar(select(Correction).where(Correction.target_id==i.id)):
            self.conflicts.append({'target_id':i.id,'message':'Corrected thermal reading disagrees with inspector remark. Please confirm.','remark':row['inspection_remark'],'evidence_ids':refs})
        return row

    def query(self,request):
        q=request if isinstance(request,QuerySpec) else QuerySpec.model_validate(request)
        self.evidence={}; self.conflicts=[]; self.calculations=[]; self.warnings=[]
        if hasattr(self,'_rule_cache'): del self._rule_cache
        self._rule_cache=self._rules()
        self._user_records={r.record_id:r for r in self._records('user')}
        self.wells=list(self.session.scalars(self._well_stmt(q))); self.well_ids=[w.id for w in self.wells]
        if q.well_ids and set(q.well_ids)-set(self.well_ids): self.warnings.append('Some requested wells are unknown or outside the requested area')
        handlers={'status':self._status,'temperatures':self._temperatures,'spills':self._spills,'downtime':self._downtime,'maintenance':self._maintenance,'rca':self._rca,'containment':self._containment,'compliance':self._compliance,'notes':self._note_rows,'documents':self._documents,'guidance':self._guidance}
        rows=handlers[q.operation.value](q)
        if q.limit: rows=rows[:q.limit]
        selected=list(dict.fromkeys(r['well_id'] for r in rows if r.get('well_id')))
        if not selected and q.operation in {Operation.documents,Operation.guidance}: selected=self.well_ids if q.well_ids else []
        default='card' if q.operation==Operation.status and len(rows)==1 else 'line' if q.operation==Operation.temperatures else 'bar' if q.operation==Operation.downtime and len(rows)>1 else 'text' if q.operation==Operation.downtime else 'table'
        visual=VisualSpec(kind=q.visual or default,title=q.operation.value,data=rows,x='date' if q.operation==Operation.temperatures else None,y='wellhead_temp_c' if q.operation==Operation.temperatures else None)
        summary=f'{len(rows)} {q.operation.value} result(s).'
        if not rows: summary='No matching records or applicable source evidence.'
        return AnswerEnvelope(result_id=new_id(),question=q.query or q.operation.value,analysis_date=self.analysis_date,date_window={'start':q.start,'end':q.end or self.analysis_date} if q.start else None,summary=summary,findings=[Finding(label=q.operation.value,value=rows,evidence_ids=list(self.evidence))],evidence=list(self.evidence.values()),conflicts=self.conflicts,visual=visual,selected_well_ids=selected,calculations=self.calculations,revisions={s.id:s.revision for s in self.session.scalars(select(SourceVersion).where(SourceVersion.id.in_({r.source_id for r in self.evidence.values()})))},warnings=self.warnings)

    def _corrected_reading(self,w,q):
        """A well excluded from a "not producing" answer because its reading was corrected."""
        inspections={i.id for i,w2 in self._inspection_rows(q.model_copy(update={'well_ids':[w.id],'producing':None}))}
        if not inspections: return None
        for c in self.session.scalars(select(Correction).where(Correction.target_kind=='inspection',Correction.target_id.in_(inspections),Correction.field.in_(['wellhead_temp_c','ambient_temp_c']),Correction.status.in_(['accepted','disputed']))):
            fact=self.session.get(InspectionFact,c.target_id); record=self.session.get(RecordVersion,fact.version_id)
            original=record.payload
            threshold=float(self._value('production_delta_c',w.well_type))
            raw=(original.get('wellhead_temp_c'),original.get('ambient_temp_c'))
            if None in raw: continue
            raw_producing=raw[0]-raw[1]>=threshold
            now_producing=fact.wellhead_temp_c-fact.ambient_temp_c>=threshold
            if now_producing and not raw_producing:
                return {'kind':'corrected_exclusion','well_id':w.id,'inspection_id':fact.id,
                        'original_value':raw[0] if c.field=='wellhead_temp_c' else raw[1],
                        'corrected_value':c.value,'author':self._user(c.author_id),
                        'reason':c.reason,'evidence_ids':self._source_evidence(c.source_id)}
        return None

    def _status(self,q):
        rows=[]
        for i,w in self._inspection_rows(q,latest=True):
            r=self._reading(i,w); r['recorded_status']=w.recorded_status
            r['stale_recorded_status']=(w.recorded_status=='active')!=r['producing']
            r['reason']='No recorded reason'
            if not r['producing']:
                maintenance=self.session.scalar(select(MaintenanceFact).where(MaintenanceFact.well_id==w.id,MaintenanceFact.started_at<=i.inspected_at,or_(MaintenanceFact.completed_at.is_(None),MaintenanceFact.completed_at>=i.inspected_at)).order_by(MaintenanceFact.started_at.desc()))
                if maintenance:
                    record=self.session.get(RecordVersion,maintenance.version_id)
                    r['reason']=record.payload['issue']; r['maintenance_id']=maintenance.id; r['evidence_ids']+=self._evidence(record)
                else:
                    for note in self._notes(w.id):
                        p=note.payload; day=i.inspected_at.date()
                        if p.get('valid_from') and date.fromisoformat(p['valid_from'])<=day and (not p.get('valid_to') or day<=date.fromisoformat(p['valid_to'])) and re.search(r'shut.?in|workover|stopp|down|replacement',p['text'],re.I):
                            r['reason']=p['text']; r['reason_author']=self._user(p['author_user_id']); r['evidence_ids']+=self._evidence(note)
            for shared in self.session.scalars(select(Correction).where(Correction.target_kind=='well',Correction.target_id==w.id)):
                if shared.valid_from and shared.valid_from>self.analysis_date: continue
                if shared.valid_to and shared.valid_to<self.analysis_date: continue
                refs=self._source_evidence(shared.source_id)
                r.setdefault('shared_notes',[]).append({'text':shared.value,'author':self._user(shared.author_id),'status':shared.status,'evidence_ids':refs})
                r['evidence_ids']+=refs
                positive=bool(re.search(r'running|back online|producing|operating',str(shared.value),re.I))
                negative=bool(re.search(r'shut.?in|stopped|not producing',str(shared.value),re.I))
                if (positive and not r['producing']) or (negative and r['producing']):
                    self.conflicts.append({'target_id':w.id,'message':'Unconfirmed shared claim disagrees with inspected production. Please confirm.','claim':shared.value,'author':self._user(shared.author_id),'evidence_ids':refs+r['evidence_ids']})
            rows.append(r)
        if q.producing is False:
            # A corrected reading can make a well producing again. Say so, rather than
            # silently dropping it from the list the user asked about.
            for w in self.wells:
                if w.id in {r['well_id'] for r in rows}: continue
                corrected=self._corrected_reading(w,q)
                if corrected: self.calculations.append(corrected)
        return rows

    def _temperatures(self,q):
        return [self._reading(i,w) for i,w in self._inspection_rows(q)]

    def _spills(self,q):
        rows=[]
        for i,w in self._inspection_rows(q,spills=True):
            r=self._reading(i,w); r.update(volume_bbl=i.spill_est_volume_bbl,spill_area_pct=i.spill_area_pct,lat=w.lat,lon=w.lon,area=w.area_name,reportable=(i.spill_est_volume_bbl or 0)>=self._value('reportable_bbl'))
            r['evidence_ids']+=self._evidence(self._rule('reportable_bbl'))
            if r['reportable']:
                # Q15/Q13: a reportable spill without a written notice is overdue, not silent.
                # The deadline is the SOP's own report_hours rule, never a constant.
                limit=self._value('major_report_hours') if i.spill_est_volume_bbl>=self._value('major_bbl') else self._value('report_hours')
                due=utc(i.inspected_at)+timedelta(hours=limit)
                filed=[e for e in self.session.scalars(select(RegulatorFact).where(RegulatorFact.inspection_id==i.id,RegulatorFact.event_type=='spill_report_filed'))]
                r['notice_due_at']=due.isoformat(); r['notice_status']='filed' if filed else 'overdue'
                r['notice_hours_to_report']=filed[0].hours_to_report if filed else None
                r['evidence_ids']+=self._evidence(self._rule('report_hours'))
            notes=self._notes(w.id,i.id)
            if len(notes)>1:
                refs=[]
                for note in notes: refs+=self._evidence(note)
                self.conflicts.append({'target_id':i.id,'message':'Attributed notes disagree; informal claims do not replace detection.','notes':[{'text':n.payload['text'],'author':self._user(n.payload['author_user_id'])} for n in notes],'evidence_ids':refs})
                r['evidence_ids']+=refs
            rows.append(r)
        # Excluded false positives still contribute correction lineage to aggregate answers.
        for (target,_),cs in correction_groups(self.session).items():
            fact=self.session.get(InspectionFact,target)
            if fact and fact.well_id in self.well_ids and not fact.spill_detected and (not q.start or fact.inspected_at.date()>=q.start) and fact.inspected_at.date() <= (q.end or self.analysis_date):
                self._evidence(fact.version_id); self._correction_evidence(target)
        if q.visual and q.visual.value=='heatmap':
            # Counts are SQL aggregates over effective corrections, never vector retrieval.
            month=func.substr(func.cast(InspectionFact.inspected_at,__import__('sqlalchemy').String),1,7)
            counts={(a,m):count for a,m,count in self.session.execute(select(WellFact.area_name,month,func.count()).join(InspectionFact,InspectionFact.well_id==WellFact.id).where(*self._spill_filters(q)).group_by(WellFact.area_name,month))}
            start=q.start or date(self.analysis_date.year,1,1); end=min(q.end or self.analysis_date,self.analysis_date); current=start.replace(day=1); months=[]
            while current<=end:
                months.append(current.strftime('%Y-%m')); current=(current.replace(day=28)+timedelta(days=4)).replace(day=1)
            refs=[e for r in rows for e in r['evidence_ids']]
            return [{'area':area,'month':m,'count':counts.get((area,m),0),'evidence_ids':refs} for area in sorted({w.area_name for w in self.wells}) for m in months]
        count,total=self.session.execute(select(func.count(),func.coalesce(func.sum(InspectionFact.spill_est_volume_bbl),0)).join(WellFact,WellFact.id==InspectionFact.well_id).where(*self._spill_filters(q))).one()
        self.calculations.append({'spill_count':count,'volume_bbl':round(total,6),'evidence_ids':list(self.evidence)})
        return rows

    def _spill_filters(self,q):
        filters=[WellFact.id.in_(self.well_ids),InspectionFact.spill_detected.is_(True),*self._window(q,InspectionFact.inspected_at)]
        if q.reportable_only: filters.append(InspectionFact.spill_est_volume_bbl>=self._value('reportable_bbl'))
        if q.producing is not None: filters.append(self._production_expression().is_(q.producing))
        return filters

    def _downtime(self,q):
        days=float(self._value('downtime_days')); rule=self._rule('downtime_days')
        producing=self._production_expression()
        stmt=select(WellFact.id,func.sum(case((producing.is_(False),days),else_=0)).label('days'),func.max(case((producing.is_(False),InspectionFact.inspected_at),else_=None)).label('latest')).outerjoin(InspectionFact,and_(InspectionFact.well_id==WellFact.id,*self._window(q,InspectionFact.inspected_at))).where(WellFact.id.in_(self.well_ids)).group_by(WellFact.id).order_by(text('days DESC'),text('latest DESC'),WellFact.id)
        rows=[]
        for well_id,total,latest in self.session.execute(stmt):
            refs=self._evidence(rule)
            detail=q.model_copy(update={'well_ids':[well_id]})
            for i,w in self._inspection_rows(detail.model_copy(update={'producing':False})):
                refs+=self._evidence(i.version_id)+self._correction_evidence(i.id)+self._evidence(self._rule('production_delta_c',w.well_type))
            rows.append({'well_id':well_id,'downtime_days':int(total or 0),'latest_nonproducing':latest,'evidence_ids':list(dict.fromkeys(refs))})
        return rows

    def _maintenance(self,q):
        stmt=select(MaintenanceFact).where(MaintenanceFact.well_id.in_(self.well_ids),*self._window(q,MaintenanceFact.started_at))
        if q.equipment_kind: stmt=stmt.where(MaintenanceFact.equipment_kind==q.equipment_kind)
        rows=[]
        for m in self.session.scalars(stmt.order_by(MaintenanceFact.well_id,MaintenanceFact.started_at)):
            rows.append({'well_id':m.well_id,'maintenance_id':m.id,'started_at':m.started_at.isoformat(),'completed_at':m.completed_at.isoformat() if m.completed_at else None,'equipment_kind':m.equipment_kind,'cost_usd':m.cost_usd,'issue':self.session.get(RecordVersion,m.version_id).payload['issue'],'evidence_ids':self._evidence(m.version_id)})
        filters=[MaintenanceFact.well_id.in_(self.well_ids),*self._window(q,MaintenanceFact.started_at)]
        if q.equipment_kind: filters.append(MaintenanceFact.equipment_kind==q.equipment_kind)
        totals=self.session.execute(select(MaintenanceFact.well_id,func.sum(MaintenanceFact.cost_usd)).where(*filters).group_by(MaintenanceFact.well_id))
        self.calculations.extend({'well_id':well,'cost_usd':total,'basis':'maintenance started_at','evidence_ids':[e for r in rows if r['well_id']==well for e in r['evidence_ids']]} for well,total in totals)
        return rows

    def _rca(self,q):
        rows=[]
        for w in self.wells:
            rule=self._rule('rca_threshold',w.well_type); months=int(self._value('rca_months',w.well_type))
            start=q.start or months_before(q.end or self.analysis_date,months)
            stmt=select(MaintenanceFact.equipment_kind,func.count()).where(MaintenanceFact.well_id==w.id,MaintenanceFact.maintenance_type=='corrective',*self._window(q,MaintenanceFact.started_at,start)).group_by(MaintenanceFact.equipment_kind)
            if q.equipment_kind: stmt=stmt.where(MaintenanceFact.equipment_kind==q.equipment_kind)
            for equipment,count in self.session.execute(stmt):
                threshold=rule.value; refs=self._evidence(rule)+self._evidence(self._rule('rca_months',w.well_type)); author=None
                overrides=list(self.session.scalars(select(Correction).join(FeedbackDetail,FeedbackDetail.correction_id==Correction.id).where(Correction.target_kind=='well_type',Correction.target_id==w.well_type,Correction.field=='rca_threshold',Correction.status=='accepted',FeedbackDetail.equipment_kind==equipment)))
                overrides=[c for c in overrides if (not c.valid_from or c.valid_from<=self.analysis_date) and (not c.valid_to or c.valid_to>=self.analysis_date)]
                if overrides:
                    values={c.value for c in overrides}
                    if len(values)==1:
                        c=overrides[0]; threshold=c.value; author=self._user(c.author_id); refs+=self._source_evidence(c.source_id)
                    else:
                        disputed_refs=[]
                        for override in overrides: disputed_refs+=self._source_evidence(override.source_id)
                        self.conflicts.append({'well_type':w.well_type,'equipment_kind':equipment,'message':'Conflicting team rules; official manual retained','evidence_ids':disputed_refs})
                if count>=threshold:
                    repairs=list(self.session.scalars(select(MaintenanceFact).where(MaintenanceFact.well_id==w.id,MaintenanceFact.equipment_kind==equipment,MaintenanceFact.maintenance_type=='corrective',*self._window(q,MaintenanceFact.started_at,start))))
                    for m in repairs: refs+=self._evidence(m.version_id)
                    parent=self._rule('inherits',w.well_type)
                    if parent: refs+=self._evidence(parent)
                    rows.append({'well_id':w.id,'well_type':w.well_type,'equipment_kind':equipment,'corrective_count':count,'threshold':threshold,'authority':'team override' if author else 'official manual','author':author,'maintenance_ids':[m.id for m in repairs],'evidence_ids':refs})
        return rows

    def _containment(self,q):
        limit=float(self._value('containment_hours')); rule=self._rule('containment_hours')
        stmt=select(MaintenanceFact,InspectionFact).join(InspectionFact,InspectionFact.id==MaintenanceFact.inspection_id).where(MaintenanceFact.well_id.in_(self.well_ids),InspectionFact.spill_detected.is_(True),MaintenanceFact.containment_hours>limit,*self._window(q,InspectionFact.inspected_at)).order_by(MaintenanceFact.well_id,InspectionFact.inspected_at)
        return [{'well_id':m.well_id,'inspection_id':i.id,'maintenance_id':m.id,'containment_hours':m.containment_hours,'limit_hours':limit,'evidence_ids':self._evidence(m.version_id)+self._evidence(m.report_version_id)+self._evidence(i.version_id)+self._evidence(rule)+self._correction_evidence(i.id)} for m,i in self.session.execute(stmt)]

    def _compliance(self,q):
        rows=[]; now=datetime.combine(min(q.end or self.analysis_date,self.analysis_date),time.max,tzinfo=timezone.utc)
        for i,w in self._inspection_rows(q,spills=True):
            refs=self._evidence(i.version_id)+self._correction_evidence(i.id)
            events=list(self.session.scalars(select(RegulatorFact).where(RegulatorFact.inspection_id==i.id,RegulatorFact.event_date<=now)))
            reportable=(i.spill_est_volume_bbl or 0)>=self._value('reportable_bbl')
            if reportable:
                limit=self._value('major_report_hours') if i.spill_est_volume_bbl>=self._value('major_bbl') else self._value('report_hours')
                due=utc(i.inspected_at)+timedelta(hours=limit)
                reports=[e for e in events if e.event_type=='spill_report_filed']
                late=reports and any((e.hours_to_report is not None and e.hours_to_report>limit) for e in reports)
                if late or not reports:
                    evidence=refs+self._evidence(self._rule('report_hours'))+self._evidence(self._rule('reportable_bbl'))
                    for event in reports: evidence+=self._evidence(event.version_id)
                    rows.append({'well_id':w.id,'inspection_id':i.id,'protocol':'SR-01','status':'breach' if late else 'possible breach' if now>due else 'pending','due_at':due.isoformat(),'hours_to_report':reports[0].hours_to_report if reports else None,'detail':'Late written notice' if late else 'No written notice recorded','evidence_ids':evidence})
                days=self._value('verification_days'); due=utc(i.inspected_at)+timedelta(days=days)
                verification=[e for e in events if e.event_type in {'site_inspection','remediation_verified','remediation_verification'} and e.protocol_id=='SR-03']
                passed=[e for e in verification if e.status=='closed' and not re.search(r'fail|pending|residual',self.session.get(RecordVersion,e.version_id).payload.get('detail',''),re.I)]
                first_pass=min(passed,key=lambda e:utc(e.event_date)) if passed else None
                completed_late=first_pass is not None and utc(first_pass.event_date)>due
                if not passed or completed_late:
                    evidence=refs+self._evidence(self._rule('verification_days'))
                    for event in verification: evidence+=self._evidence(event.version_id)
                    rows.append({'well_id':w.id,'inspection_id':i.id,'protocol':'SR-03','status':'breach' if completed_late else ('breach' if verification else 'possible breach') if now>due else 'pending','due_at':due.isoformat(),'completion_status':'completed late' if completed_late else 'open','completed_at':first_pass.event_date.isoformat() if first_pass else None,'detail':'Agency verification completed after deadline' if completed_late else 'Agency verification remains open' if verification else 'No passing agency verification recorded','evidence_ids':evidence})
        # Notices are well-level obligations and need not originate from a recorded spill.
        notices=self.session.scalars(select(RegulatorFact).where(RegulatorFact.well_id.in_(self.well_ids),RegulatorFact.event_type=='notice_of_violation',*self._window(q,RegulatorFact.event_date)).order_by(RegulatorFact.well_id,RegulatorFact.event_date,RegulatorFact.id))
        for event in notices:
            due=utc(event.event_date)+timedelta(days=self._value('nov_response_days'))
            responses=list(self.session.scalars(select(RegulatorFact).where(RegulatorFact.well_id==event.well_id,RegulatorFact.event_type=='nov_response_filed',RegulatorFact.event_date>=event.event_date,RegulatorFact.event_date<=now)))
            matching=[]
            for response in responses:
                explicit=self.session.get(RecordVersion,response.version_id).payload.get('related_event_id')
                if explicit==event.id or (not explicit and event.inspection_id is not None and response.inspection_id==event.inspection_id): matching.append(response)
            first_response=min(matching,key=lambda e:utc(e.event_date)) if matching else None
            completed_late=first_response is not None and utc(first_response.event_date)>due
            evidence=self._evidence(event.version_id)+self._evidence(self._rule('nov_response_days'))
            for response in matching: evidence+=self._evidence(response.version_id)
            if not matching or completed_late:
                # A passed response deadline with nothing on record is a breach when the
                # notice is tied to a recorded inspection: the obligation is fully
                # evidenced. An unattributed well-level notice stays "possible" because
                # the missing discovery record cannot be ruled out.
                attributable = event.inspection_id is not None
                status=('breach' if completed_late else
                        'breach' if (not matching and attributable and utc(due)<=utc(now)) else
                        'possible breach' if utc(now)>utc(due) else 'pending')
                rows.append({'well_id':event.well_id,'inspection_id':event.inspection_id,'notice_id':event.id,'protocol':'RC-04','status':status,'due_at':due.date().isoformat(),'completion_status':'completed late' if completed_late else 'open','completed_at':first_response.event_date.isoformat() if first_response else None,'fine_usd':event.fine_usd,'notice_status':event.status,'detail':'Notice response completed after deadline' if completed_late else 'No notice response recorded','evidence_ids':evidence})
            elif event.fine_usd:
                rows.append({'well_id':event.well_id,'notice_id':event.id,'protocol':event.protocol_id,'status':event.status,'fine_usd':event.fine_usd,'detail':'Notice of violation','evidence_ids':evidence})
        for late in self._containment(q): rows.append({**late,'protocol':'SR-02','status':'breach','detail':'Containment exceeded extracted SOP deadline'})
        for action in self._rca(q): rows.append({**action,'protocol':'RCA','status':'pending','detail':'RCA required before next repair closes'})
        for m in self.session.scalars(select(MaintenanceFact).where(MaintenanceFact.well_id.in_(self.well_ids),MaintenanceFact.started_at>=datetime(self.analysis_date.year,1,1),MaintenanceFact.started_at<=now)):
            record=self.session.get(RecordVersion,m.version_id)
            if 'annual flowline integrity test' in record.payload.get('issue','').lower() and m.completed_at:
                rows.append({'well_id':m.well_id,'protocol':'RC-02','status':'met','maintenance_id':m.id,'detail':'Yearly flowline integrity test completed','evidence_ids':self._evidence(record)})
        for n in self._records('context',self.well_ids):
            if 'not yet' in n.payload['text'].lower() and 'maintenance system' in n.payload['text'].lower() and n.payload.get('valid_to','9999') and n.payload.get('valid_to','9999') >= self.analysis_date.isoformat():
                rows.append({'well_id':n.asset_id,'protocol':'manual records','status':'pending','detail':n.payload['text'],'evidence_ids':self._evidence(n)})
        return rows

    def _note_rows(self,q):
        rows=[{'well_id':n.asset_id,'note_id':n.record_id,'text':n.payload['text'],'author':self._user(n.payload['author_user_id']),'note_type':n.payload.get('note_type'),'evidence_ids':self._evidence(n)} for n in self._records('context',self.well_ids)]
        for c in self.session.scalars(select(Correction).where(Correction.target_kind=='well',Correction.target_id.in_(self.well_ids))):
            rows.append({'well_id':c.target_id,'note_id':c.id,'text':c.value,'author':self._user(c.author_id),'status':c.status,'valid_from':str(c.valid_from) if c.valid_from else None,'valid_to':str(c.valid_to) if c.valid_to else None,'evidence_ids':self._source_evidence(c.source_id)})
        return rows

    def search_documents(self, query, limit=20, embedding=None):
        active_sources=select(RecordVersion.source_id).join(ActiveRecord,ActiveRecord.version_id==RecordVersion.id).where(RecordVersion.kind=='document')
        stmt=select(DocumentChunk).where(DocumentChunk.source_id.in_(active_sources))
        if self.session.bind.dialect.name=='postgresql':
            if embedding is not None:
                if len(embedding)!=384: raise ValueError('MiniLM embedding requires 384 dimensions')
                stmt=stmt.order_by(text('embedding_vector <=> CAST(:vector AS vector)')).params(vector=json.dumps(embedding))
            elif query: stmt=stmt.where(text("search_vector @@ plainto_tsquery('english', :query)")).params(query=query)
        elif query:
            tokens=re.findall(r'\w+',query)
            if tokens: stmt=stmt.where(or_(*(DocumentChunk.text.ilike('%'+token+'%') for token in tokens)))
        return list(self.session.scalars(stmt.limit(limit)))

    def _documents(self,q):
        self.warnings.append('Embedding indexing deferred; full-text search available')
        return [{'heading':c.heading,'text':c.text,'evidence_ids':self._source_evidence(c.source_id,c.start_line,c.end_line,c.heading)} for c in self.search_documents(q.query,q.limit or 20)]

    def _guidance(self,q):
        rows=[]
        documents=self._records('document')
        types={w.well_type for w in self.wells} if q.well_ids or q.area else set()
        spill=not q.query or bool(re.search(r'spill|contain|remediat|report',q.query,re.I))
        repair=bool(q.query and re.search(r'repair|shut.?in|work|safety',q.query,re.I))
        applicable=[]
        for document in documents:
            path=document.record_id
            if '/well-types/' in path and PathStem(path) in types:
                applicable.append(document)
                parent=self._rule('inherits',PathStem(path))
                if parent:
                    applicable.extend(d for d in documents if '/well-types/' in d.record_id and PathStem(d.record_id)==parent.value)
            elif spill and path.endswith('spill-response-sop.md'): applicable.append(document)
            elif repair and path.endswith('field-work-sop.md'): applicable.append(document)
        seen=set()
        for document in applicable:
            if document.id in seen: continue
            seen.add(document.id); source=self.session.get(SourceVersion,document.source_id)
            for heading,start,end,body in sections(source.content):
                if '/well-types/' in source.path and not any(x in heading.lower() for x in ('start-up','spill','maintenance escalation','failure modes')): continue
                if '/sops/' in source.path and not any(x in heading.lower() for x in ('protocols','response steps','spill classes','close-out','typical work')): continue
                for number,line in enumerate(body.splitlines(),start):
                    clean=plain(line)
                    if not clean or line.startswith('#') or clean.startswith('|---'): continue
                    protocol=re.search(r'\b(?:SR|WS|RC)-\d+\b',clean)
                    rows.append({'protocol':protocol.group() if protocol else None,'procedure':clean,'condition':heading,'well_type':PathStem(source.path) if '/well-types/' in source.path else None,'authority':'official manual/SOP','evidence_ids':self._source_evidence(source.id,number,number,heading)})
        if spill:
            if not any(d.record_id.endswith('spill-response-sop.md') for d in applicable):
                self.warnings.append('Missing Spill Response SOP evidence; clarify required procedure'); return rows
            needed=('reportable_bbl','major_bbl','minor_bbl','containment_hours','report_hours','major_report_hours','verification_days')
            missing=[key for key in needed if self._rule(key) is None]
            if missing:
                self.warnings.append('Missing extracted procedure rules; clarify: '+', '.join(missing)); return rows
            for i,w in (self._inspection_rows(q,spills=True) if q.well_ids or q.area else []):
                volume=i.spill_est_volume_bbl
                if volume is None:
                    self.warnings.append(f'{i.id}: spill volume unknown; classification requires clarification'); continue
                major=volume>=self._value('major_bbl'); reportable=volume>=self._value('reportable_bbl')
                cls='major' if major else 'reportable' if reportable else 'moderate' if volume>=self._value('minor_bbl') else 'minor'
                refs=self._evidence(i.version_id)+self._correction_evidence(i.id)+self._evidence(self._rule('reportable_bbl'))+self._evidence(self._rule('major_bbl'))
                deadlines=[('SR-02','containment_hours','hours')]
                if reportable: deadlines += [('SR-01','major_report_hours' if major else 'report_hours','hours'),('SR-03','verification_days','days')]
                elif cls=='moderate': deadlines += [('HSE notice','moderate_notice_hours','hours')]
                for protocol,key,unit in deadlines:
                    rule=self._rule(key)
                    if not rule:
                        self.warnings.append(f'Missing rule evidence for {protocol}'); continue
                    due=utc(i.inspected_at)+timedelta(**{unit:rule.value})
                    rows.append({'well_id':w.id,'inspection_id':i.id,'protocol':protocol,'spill_class':cls,'volume_bbl':volume,'discovered_at':utc(i.inspected_at).isoformat(),'due_at':due.isoformat(),'authority':'official SOP','evidence_ids':refs+self._evidence(rule)})
                rows.append({'well_id':w.id,'inspection_id':i.id,'protocol':'SR-04','spill_class':cls,'procedure':'Record estimated volume and affected area against asset','authority':'official SOP','evidence_ids':refs+self._evidence(self._rule('containment_hours'))})
        if not rows: self.warnings.append('Missing applicable procedure evidence; clarification required')
        return rows

    def add_feedback(self,request):
        f=request if isinstance(request,FeedbackSpec) else FeedbackSpec.model_validate(request)
        if not self.session.scalar(select(RecordVersion).join(ActiveRecord,ActiveRecord.version_id==RecordVersion.id).where(RecordVersion.kind=='user',RecordVersion.record_id==f.author_id)): raise ValueError('unknown author')
        kind='inspection' if f.kind=='correction' else 'well_type' if f.kind=='rule' else 'well'
        if kind=='inspection':
            fact=self.session.get(InspectionFact,f.target_id)
            if not fact: raise ValueError('unknown inspection')
            original=self.session.get(RecordVersion,fact.version_id).payload.get(f.field)
            if (f.valid_from and fact.inspected_at.date()<f.valid_from) or (f.valid_to and fact.inspected_at.date()>f.valid_to): raise ValueError('correction validity excludes target inspection')
        elif kind=='well_type':
            if not self._rule('production_delta_c',f.target_id): raise ValueError('unknown well type')
            equipment_exists=any(r.payload.get('well_type')==f.target_id and any(e.get('kind')==f.equipment_kind for e in r.payload.get('equipment',[])) for r in self._records('well'))
            if not equipment_exists: raise ValueError('unknown equipment scope')
            original=self._value('rca_threshold',f.target_id)
        else:
            if not self.session.get(WellFact,f.target_id): raise ValueError('unknown well')
            original=None
        previous=None
        if f.supersedes:
            previous=self.session.get(Correction,f.supersedes)
            if not previous or (previous.target_kind,previous.target_id,previous.field)!=(kind,f.target_id,f.field): raise ValueError('supersedes must match target and field')
            detail=self.session.get(FeedbackDetail,previous.id)
            if kind=='well_type' and (not detail or detail.equipment_kind!=f.equipment_kind): raise ValueError('supersedes must match equipment scope')
        ident=new_id(); content=json.dumps(f.model_dump(mode='json'),indent=2)
        with self.session.begin_nested():
            batch=ImportBatch(root='feedback',revision='feedback',manifest_hash=digest(content),status='published'); self.session.add(batch); self.session.flush()
            source=SourceVersion(path=f'feedback/{ident}',hash=digest(content),content=content,revision='feedback',batch_id=batch.id); self.session.add(source); self.session.flush()
            c=Correction(id=ident,target_kind=kind,target_id=f.target_id,field=f.field,value=f.value,original_value=original,scope_kind=kind,scope_id=f.target_id,author_id=f.author_id,reason=f.reason,status='unconfirmed' if f.kind in {'claim','note'} else 'accepted',valid_from=f.valid_from,valid_to=f.valid_to,source_id=source.id)
            self.session.add(c); self.session.flush()
            self.session.add(FeedbackDetail(correction_id=c.id,equipment_kind=f.equipment_kind,supersedes=f.supersedes))
            if previous:
                # A deliberate resolution closes all currently disputed alternatives in this exact scope.
                prior=select(Correction).where(Correction.target_kind==kind,Correction.target_id==f.target_id,Correction.field==f.field,Correction.id!=ident,Correction.status.in_(['accepted','disputed']))
                if kind=='well_type': prior=prior.join(FeedbackDetail,FeedbackDetail.correction_id==Correction.id).where(FeedbackDetail.equipment_kind==f.equipment_kind)
                for old in self.session.scalars(prior): old.status='superseded'
            self.session.flush(); apply_corrections(self.session)
            self.session.add(Outbox(event_type='knowledge.feedback',payload={'correction_id':c.id,'source_id':source.id,'target_kind':kind,'target_id':f.target_id,'author_id':f.author_id}))
        self.session.commit()
        return {'id':c.id,'status':c.status,'source_id':source.id,'original_value':original,'value':c.value}


def PathStem(path):
    return path.rsplit('/',1)[-1].rsplit('.',1)[0]
