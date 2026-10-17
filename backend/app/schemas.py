from datetime import date
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceRef(Contract):
    id: str
    source_id: str
    record_id: str | None = None
    path: str
    title: str
    excerpt: str
    start_line: int | None = None
    end_line: int | None = None


class Finding(Contract):
    label: str
    value: Any
    unit: str | None = None
    evidence_ids: list[str] = []


class VisualKind(str, Enum):
    text = "text"
    card = "card"
    table = "table"
    line = "line"
    bar = "bar"
    map = "map"
    heatmap = "heatmap"


class VisualSpec(Contract):
    kind: VisualKind
    title: str
    data: list[dict[str, Any]] = []
    x: str | None = None
    y: str | None = None
    series: str | None = None


class AnswerEnvelope(Contract):
    result_id: str
    question: str
    analysis_date: date
    date_window: dict[str, date] | None = None
    summary: str
    findings: list[Finding] = []
    evidence: list[EvidenceRef] = []
    conflicts: list[dict[str, Any]] = []
    visual: VisualSpec
    selected_well_ids: list[str] = []
    calculations: list[dict[str, Any]] = []
    revisions: dict[str, str] = {}
    warnings: list[str] = []
    previous_result_id: str | None = None
    comparison: dict[str, Any] | None = None
