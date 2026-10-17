"""Validated public tool contracts and current SQL projections of immutable records."""
from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models import JSONValue
from app.schemas import VisualKind


class Operation(str, Enum):
    status='status'; temperatures='temperatures'; spills='spills'; downtime='downtime'
    maintenance='maintenance'; compliance='compliance'; containment='containment'
    rca='rca'; notes='notes'; documents='documents'; guidance='guidance'
    gas_response='gas_response'; bypasses='bypasses'; regulator_letter='regulator_letter'
    status_conflicts='status_conflicts'; recall_pumps='recall_pumps'; cold_weather='cold_weather'
    waiting_reasons='waiting_reasons'; hot_regions='hot_regions'; operator_signals='operator_signals'
    pressure='pressure'; production_rank='production_rank'


class QuerySpec(BaseModel):
    model_config = ConfigDict(extra='forbid')
    operation: Operation
    well_ids: list[str] | None = None
    area: str | None = None
    start: date | None = None
    end: date | None = None
    equipment_kind: str | None = None
    limit: int | None = Field(default=None, ge=1, le=10000)
    producing: bool | None = None
    reportable_only: bool = False
    query: str | None = None
    areas: list[str] | None = None
    visual: VisualKind | None = None

    @model_validator(mode='after')
    def dates(self):
        if self.start and self.end and self.start > self.end:
            raise ValueError('start must be on or before end')
        return self


class FeedbackSpec(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: str
    target_id: str
    field: str = 'text'
    value: Any
    author_id: str
    reason: str = Field(min_length=1)
    unit: str | None = None
    equipment_kind: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    supersedes: str | None = None

    @model_validator(mode='after')
    def validate_scope(self):
        if self.kind not in {'correction','rule','note','claim'}:
            raise ValueError('unknown feedback kind')
        if self.valid_from and self.valid_to and self.valid_from > self.valid_to:
            raise ValueError('invalid validity interval')
        allowed = {'wellhead_temp_c','ambient_temp_c','spill_detected','spill_est_volume_bbl','spill_area_pct'}
        if self.kind == 'correction':
            if self.field not in allowed:
                raise ValueError('unsupported correction field')
            if self.field == 'spill_detected':
                if type(self.value) is not bool: raise ValueError('spill_detected requires boolean')
            else:
                if type(self.value) not in (int,float): raise ValueError('numeric correction required')
                import math
                if not math.isfinite(self.value): raise ValueError('finite numeric correction required')
                low, high = (-100,300) if self.field.endswith('temp_c') else (0,100 if self.field == 'spill_area_pct' else 1000000)
                if not low <= self.value <= high: raise ValueError('correction outside bounds')
                unit = 'C' if self.field.endswith('temp_c') else '%' if self.field == 'spill_area_pct' else 'bbl'
                if self.unit != unit: raise ValueError(f'unit must be {unit}')
        if self.kind == 'rule' and (self.field != 'rca_threshold' or not self.equipment_kind or type(self.value) is not int or not 1 <= self.value <= 100):
            raise ValueError('rule requires RCA integer threshold and equipment_kind')
        if self.kind in {'note','claim'} and (self.field != 'text' or not isinstance(self.value,str) or not self.value.strip()):
            raise ValueError('note/claim requires text')
        return self


class WellFact(Base):
    __tablename__='well_facts'
    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    version_id: Mapped[str] = mapped_column(ForeignKey('record_versions.id'), nullable=False)
    well_type: Mapped[str] = mapped_column(String(128), index=True)
    area_id: Mapped[str] = mapped_column(String(255), index=True)
    area_name: Mapped[str] = mapped_column(Text)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    recorded_status: Mapped[str] = mapped_column(String(64))


class InspectionFact(Base):
    __tablename__='inspection_facts'
    __table_args__=(Index('ix_inspection_well_date','well_id','inspected_at'),)
    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    version_id: Mapped[str] = mapped_column(ForeignKey('record_versions.id'), nullable=False)
    well_id: Mapped[str] = mapped_column(ForeignKey('well_facts.id'), index=True)
    inspected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    inspector_id: Mapped[str] = mapped_column(String(255))
    ambient_temp_c: Mapped[float] = mapped_column(Float)
    wellhead_temp_c: Mapped[float] = mapped_column(Float)
    spill_detected: Mapped[bool] = mapped_column(Boolean)
    spill_est_volume_bbl: Mapped[float | None] = mapped_column(Float)
    spill_area_pct: Mapped[float | None] = mapped_column(Float)


class MaintenanceFact(Base):
    __tablename__='maintenance_facts'
    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    version_id: Mapped[str] = mapped_column(ForeignKey('record_versions.id'), nullable=False)
    well_id: Mapped[str] = mapped_column(ForeignKey('well_facts.id'), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    maintenance_type: Mapped[str] = mapped_column(String(64))
    equipment_kind: Mapped[str] = mapped_column(String(128), index=True)
    inspection_id: Mapped[str | None] = mapped_column(String(255), index=True)
    cost_usd: Mapped[float] = mapped_column(Float)
    containment_hours: Mapped[float | None] = mapped_column(Float)
    report_version_id: Mapped[str | None] = mapped_column(ForeignKey('record_versions.id'))


class RegulatorFact(Base):
    __tablename__='regulator_facts'
    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    version_id: Mapped[str] = mapped_column(ForeignKey('record_versions.id'), nullable=False)
    well_id: Mapped[str] = mapped_column(ForeignKey('well_facts.id'), index=True)
    event_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    inspection_id: Mapped[str | None] = mapped_column(String(255), index=True)
    event_type: Mapped[str] = mapped_column(String(128))
    protocol_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(64))
    hours_to_report: Mapped[float | None] = mapped_column(Float)
    fine_usd: Mapped[float] = mapped_column(Float)


class FeedbackDetail(Base):
    __tablename__='feedback_details'
    correction_id: Mapped[str] = mapped_column(ForeignKey('corrections.id'), primary_key=True)
    equipment_kind: Mapped[str | None] = mapped_column(String(128))
    supersedes: Mapped[str | None] = mapped_column(ForeignKey('corrections.id'))


class CorrectionState(Base):
    """Durable last accepted truth; an unresolved competitor cannot reset it to raw."""
    __tablename__='correction_states'
    target_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    field: Mapped[str] = mapped_column(String(255), primary_key=True)
    correction_id: Mapped[str] = mapped_column(ForeignKey('corrections.id'))
    value: Mapped[Any] = mapped_column(JSONValue, nullable=False)


class ContextCorrectionIdentity(Base):
    """Logical context assertion identity, independent of a containing file hash."""
    __tablename__='context_correction_identities'
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    note_id: Mapped[str] = mapped_column(String(255), index=True)
    correction_id: Mapped[str] = mapped_column(ForeignKey('corrections.id'))
