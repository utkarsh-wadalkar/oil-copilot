from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db import Base

JSONValue = JSON().with_variant(JSONB, "postgresql")


def new_id() -> str:
    return str(uuid4())


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class ImportBatch(Base):
    __tablename__ = "import_batches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    revision: Mapped[str] = mapped_column(String(128), nullable=False)
    root: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    counts: Mapped[dict[str, Any]] = mapped_column(JSONValue, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class SourceVersion(Base):
    __tablename__ = "source_versions"
    __table_args__ = (UniqueConstraint("path", "hash", name="uq_source_path_hash"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    hash: Mapped[str] = mapped_column(String(128), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    revision: Mapped[str] = mapped_column(String(128), nullable=False)
    batch_id: Mapped[str] = mapped_column(ForeignKey("import_batches.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class RecordVersion(Base):
    __tablename__ = "record_versions"
    __table_args__ = (UniqueConstraint("kind", "record_id", "source_id", name="uq_record_source_version"),
                      Index("ix_record_asset_kind", "asset_id", "kind"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    record_id: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_id: Mapped[str | None] = mapped_column(String(255), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONValue, nullable=False)
    source_id: Mapped[str] = mapped_column(ForeignKey("source_versions.id"), nullable=False)
    line_number: Mapped[int | None] = mapped_column(Integer)
    batch_id: Mapped[str] = mapped_column(ForeignKey("import_batches.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class ActiveRecord(Base):
    __tablename__ = "active_records"
    __table_args__ = (UniqueConstraint("kind", "record_id", name="uq_active_kind_record"),
                      Index("ix_active_lookup", "kind", "record_id"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    record_id: Mapped[str] = mapped_column(String(255), nullable=False)
    version_id: Mapped[str] = mapped_column(ForeignKey("record_versions.id"), unique=True, nullable=False)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("source_versions.id"), nullable=False, index=True)
    heading: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    start_line: Mapped[int | None] = mapped_column(Integer)
    end_line: Mapped[int | None] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(JSONValue)


class Rule(Base):
    __tablename__ = "rules"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    rule_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    well_type: Mapped[str | None] = mapped_column(String(128))
    value: Mapped[Any] = mapped_column(JSONValue, nullable=False)
    source_id: Mapped[str] = mapped_column(ForeignKey("source_versions.id"), nullable=False)
    start_line: Mapped[int | None] = mapped_column(Integer)
    end_line: Mapped[int | None] = mapped_column(Integer)
    batch_id: Mapped[str] = mapped_column(ForeignKey("import_batches.id"), nullable=False)


class Correction(Base):
    __tablename__ = "corrections"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    target_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    field: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[Any] = mapped_column(JSONValue, nullable=False)
    original_value: Mapped[Any] = mapped_column(JSONValue, nullable=False)
    scope_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(255), nullable=False)
    author_id: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("source_versions.id"))


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversation_owner", "user_id", "id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class SavedResult(Base):
    __tablename__ = "saved_results"
    __table_args__ = (Index("ix_saved_result_owner", "user_id", "conversation_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONValue, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class Outbox(Base):
    __tablename__ = "outbox"
    __table_args__ = (Index("ix_outbox_pending", "status", "next_attempt_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONValue, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProjectionJob(Base):
    """Per-target durable work item with a reclaimable processing lease.

    One outbox event fans out into one job per projection target (graph, mem0,
    embeddings) so an unavailable target never starves the others.
    """

    __tablename__ = "projection_jobs"
    __table_args__ = (UniqueConstraint("outbox_id", "target", name="uq_projection_outbox_target"),
                      Index("ix_projection_claim", "status", "next_attempt_at"),
                      Index("ix_projection_lease", "status", "lease_expires_at"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    outbox_id: Mapped[str] = mapped_column(ForeignKey("outbox.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    target: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONValue, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    worker_id: Mapped[str | None] = mapped_column(String(128))
    external_id: Mapped[str | None] = mapped_column(String(255))
    indexed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProjectionReceipt(Base):
    """Stable external-idempotency receipt written after a successful remote write.

    Survives a crash between the remote write and the job acknowledgement: the
    ``external_key`` (canonical target/version lineage) maps to the remote id, so a
    retried job re-reads the receipt instead of creating a duplicate.
    """

    __tablename__ = "projection_receipts"
    __table_args__ = (UniqueConstraint("target", "external_key", name="uq_receipt_target_key"),
                      Index("ix_receipt_lookup", "target", "external_key"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    target: Mapped[str] = mapped_column(String(32), nullable=False)
    external_key: Mapped[str] = mapped_column(String(512), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONValue, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class ConversationContext(Base):
    """Private app conversation metadata, including the nao chat mapping."""

    __tablename__ = "conversation_context"
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), primary_key=True)
    nao_chat_id: Mapped[str | None] = mapped_column(String(255))
    nao_user_id: Mapped[str | None] = mapped_column(String(255))
    analysis_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class NaoAccount(Base):
    """Private per-dataset-user mapping to a nao sidecar account.

    The nao account owns its own strong random credential (never a user password) and is
    provisioned intentionally, so it never requires a password reset. ``nao_user_id`` is the
    trusted subject minted into every actor capability the sidecar presents to ``/mcp``.
    """

    __tablename__ = "nao_accounts"
    __table_args__ = (UniqueConstraint("app_user_id", name="uq_nao_account_app_user"),
                      UniqueConstraint("nao_user_id", name="uq_nao_account_nao_user"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    app_user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    nao_user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    nao_email: Mapped[str] = mapped_column(String(255), nullable=False)
    nao_project_id: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)


class NaoToolResult(Base):
    """A trusted answer envelope produced by an Asset Knowledge MCP tool call.

    The tool stores the full, validated envelope server-side and returns only a reference to
    the reasoning loop. The app coordinator later loads owned envelopes by request correlation,
    so the model can never fabricate the payload the UI renders.
    """

    __tablename__ = "nao_tool_results"
    __table_args__ = (Index("ix_nao_result_owner", "app_user_id", "request_id"),
                      Index("ix_nao_result_conversation", "conversation_id", "created_at"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    app_user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    nao_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    project_id: Mapped[str | None] = mapped_column(String(255))
    request_id: Mapped[str | None] = mapped_column(String(255), index=True)
    conversation_id: Mapped[str | None] = mapped_column(String(255), index=True)
    tool: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="complete")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONValue, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class MessageRequest(Base):
    """Idempotency ledger for a client-submitted message."""

    __tablename__ = "message_requests"
    __table_args__ = (UniqueConstraint("conversation_id", "client_message_id", name="uq_request_client_message"),
                      Index("ix_request_status", "status"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    client_message_id: Mapped[str] = mapped_column(String(64), nullable=False)
    message_id: Mapped[str | None] = mapped_column(ForeignKey("messages.id"))
    result_id: Mapped[str | None] = mapped_column(ForeignKey("saved_results.id"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)


class ResultMeta(Base):
    """Additive saved-result metadata: typed query, dependencies and validity markers."""

    __tablename__ = "result_meta"
    result_id: Mapped[str] = mapped_column(ForeignKey("saved_results.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    query_spec: Mapped[dict[str, Any] | None] = mapped_column(JSONValue)
    query_specs: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONValue)
    dependencies: Mapped[list[dict[str, Any]]] = mapped_column(JSONValue, nullable=False, default=list)
    validity: Mapped[dict[str, Any]] = mapped_column(JSONValue, nullable=False, default=dict)
    previous_result_id: Mapped[str | None] = mapped_column(ForeignKey("saved_results.id"))
    analysis_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class FeedbackDraft(Base):
    """A durable, author-scoped prepare/confirm correction draft."""

    __tablename__ = "feedback_drafts"
    __table_args__ = (Index("ix_draft_author", "author_id", "status"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    author_id: Mapped[str] = mapped_column(String(255), nullable=False)
    conversation_id: Mapped[str | None] = mapped_column(ForeignKey("conversations.id"))
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(255), nullable=False)
    well_id: Mapped[str | None] = mapped_column(String(255))
    field: Mapped[str] = mapped_column(String(255), nullable=False, default="text")
    value: Mapped[Any] = mapped_column(JSONValue)
    unit: Mapped[str | None] = mapped_column(String(32))
    equipment_kind: Mapped[str | None] = mapped_column(String(128))
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    supersedes: Mapped[str | None] = mapped_column(String(36))
    before_value: Mapped[Any | None] = mapped_column(JSONValue, nullable=True)
    after_value: Mapped[Any | None] = mapped_column(JSONValue, nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    clarification: Mapped[list[str]] = mapped_column(JSONValue, nullable=False, default=list)
    preview: Mapped[dict[str, Any]] = mapped_column(JSONValue, nullable=False, default=dict)
    correction_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)
