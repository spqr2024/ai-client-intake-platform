import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

DEFAULT_WORKSPACE_ID = 1


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_uuid() -> str:
    return uuid.uuid4().hex


class Workspace(Base):
    """Tenant root: every domain row belongs to exactly one workspace."""

    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), default="My Company")
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"), default=DEFAULT_WORKSPACE_ID, index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="manager")  # admin | manager
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    leads: Mapped[list["Lead"]] = relationship(back_populates="assigned_to")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Lead(Base):
    __tablename__ = "leads"
    # Every list/board query filters by workspace then sorts or filters on
    # status/created_at — composite indexes keep those index-only.
    __table_args__ = (
        Index("ix_lead_ws_status", "workspace_id", "status"),
        Index("ix_lead_ws_created", "workspace_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"), default=DEFAULT_WORKSPACE_ID, index=True
    )
    project_name: Mapped[str] = mapped_column(String(255), default="")
    client_name: Mapped[str] = mapped_column(String(255), default="")
    client_email: Mapped[str] = mapped_column(String(255), default="")
    client_phone: Mapped[str] = mapped_column(String(64), default="")
    # Preferred contact channel the client picked during intake, plus its value.
    # `contact_method` is "email" | "telegram" | "phone"; `contact_value` holds
    # the address / @handle / number for that channel. client_email and
    # client_phone stay populated for the email/phone cases (so email delivery
    # and CRM export keep working); a Telegram handle lives only here.
    contact_method: Mapped[str] = mapped_column(String(20), default="")
    contact_value: Mapped[str] = mapped_column(String(255), default="")
    service: Mapped[str] = mapped_column(String(255), default="")
    budget: Mapped[float | None] = mapped_column(Float, nullable=True)
    timeline: Mapped[str] = mapped_column(String(255), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    # Status values are workspace-configurable (pipeline_statuses setting);
    # these are the defaults: New | Qualified | In Progress | Rejected |
    # Converted | Closed | Incomplete
    status: Mapped[str] = mapped_column(String(60), default="New", index=True)
    priority: Mapped[str] = mapped_column(String(20), default="Medium")  # Low|Medium|High|Urgent
    tags: Mapped[list] = mapped_column(JSON, default=list)
    follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # When the follow-up reminder was actually delivered. Separate from
    # follow_up_at so the due date stays visible in the UI after reminding,
    # and so a restart cannot re-send a reminder that already went out.
    follow_up_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    score: Mapped[int] = mapped_column(Integer, default=0)
    language: Mapped[str] = mapped_column(String(8), default="en")
    assigned_to_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    assigned_to: Mapped[User | None] = relationship(back_populates="leads")
    conversation: Mapped["Conversation | None"] = relationship(back_populates="lead", uselist=False)
    activities: Mapped[list["ActivityLog"]] = relationship(
        back_populates="lead", cascade="all, delete-orphan", order_by="ActivityLog.created_at"
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"), default=DEFAULT_WORKSPACE_ID, index=True
    )
    lead_id: Mapped[int | None] = mapped_column(ForeignKey("leads.id"), nullable=True)
    workflow_id: Mapped[int | None] = mapped_column(ForeignKey("workflows.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="Active")  # Active | Completed | Abandoned
    language: Mapped[str] = mapped_column(String(8), default="en")
    client_name: Mapped[str] = mapped_column(String(255), default="")
    client_email: Mapped[str] = mapped_column(String(255), default="")
    # state: {current_node, answers, clarify_count, memory{summary,upto}, history[…]}
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    last_node: Mapped[str] = mapped_column(String(120), default="", index=True)
    # Identifies the conversation on a non-web channel, e.g. "telegram:123456".
    # Indexed because every inbound Telegram message looks the conversation up
    # by this value. Namespaced by channel so a second one cannot collide.
    external_ref: Mapped[str] = mapped_column(String(120), default="", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    lead: Mapped[Lead | None] = relationship(back_populates="conversation")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.id"
    )
    attachments: Mapped[list["Attachment"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    sender: Mapped[str] = mapped_column(String(10))  # user | bot
    text: Mapped[str] = mapped_column(Text)
    # Replay metadata: {node, event, kb_article_id, validation, …}
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(255))
    size: Mapped[int] = mapped_column(Integer, default=0)
    content_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="attachments")


class Workflow(Base):
    __tablename__ = "workflows"
    __table_args__ = (UniqueConstraint("workspace_id", "name", name="uq_workflow_ws_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"), default=DEFAULT_WORKSPACE_ID, index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    is_default: Mapped[int] = mapped_column(Integer, default=0)
    definition: Mapped[dict] = mapped_column(JSON, default=dict)
    prompt_name: Mapped[str] = mapped_column(String(120), default="")  # optional Prompt assignment
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class KnowledgeBaseArticle(Base):
    """A KB document. Content is either typed in the UI or extracted from an
    uploaded file (PDF/DOCX/MD/TXT). Long documents are split into
    `KBChunk` rows, which are what actually get embedded and retrieved."""

    __tablename__ = "kb_articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"), default=DEFAULT_WORKSPACE_ID, index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(8), default="en")

    # Document management
    source_type: Mapped[str] = mapped_column(String(20), default="manual")  # manual|pdf|docx|md|txt
    source_filename: Mapped[str] = mapped_column(String(255), default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    # pending | indexing | indexed | failed | stale
    index_status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    index_error: Mapped[str] = mapped_column(Text, default="")
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    doc_metadata: Mapped[dict] = mapped_column(JSON, default=dict)  # tags, author, size, pages…
    hit_count: Mapped[int] = mapped_column(Integer, default=0)  # retrieval statistics

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    chunks: Mapped[list["KBChunk"]] = relationship(
        back_populates="article", cascade="all, delete-orphan", order_by="KBChunk.position"
    )
    versions: Mapped[list["KBArticleVersion"]] = relationship(
        back_populates="article",
        cascade="all, delete-orphan",
        order_by="KBArticleVersion.version.desc()",
    )


class KBChunk(Base):
    """Retrieval unit: a passage of an article, embedded independently."""

    __tablename__ = "kb_chunks"
    __table_args__ = (Index("ix_chunk_ws_article", "workspace_id", "article_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("kb_articles.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)

    article: Mapped[KnowledgeBaseArticle] = relationship(back_populates="chunks")


class KBArticleVersion(Base):
    """Immutable snapshot of an article, written on every edit (rollback source)."""

    __tablename__ = "kb_article_versions"
    __table_args__ = (UniqueConstraint("article_id", "version", name="uq_kb_version_article_ver"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("kb_articles.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    article: Mapped[KnowledgeBaseArticle] = relationship(back_populates="versions")


class KBSearchLog(Base):
    """Retrieval analytics: what visitors ask and whether the KB answered."""

    __tablename__ = "kb_search_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    query: Mapped[str] = mapped_column(String(500))
    top_article_id: Mapped[int | None] = mapped_column(nullable=True)
    top_score: Mapped[float] = mapped_column(Float, default=0.0)
    hit: Mapped[int] = mapped_column(Integer, default=0)  # 1 when a result passed the threshold
    source: Mapped[str] = mapped_column(String(20), default="chat")  # chat | admin
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class CRMSyncLog(Base):
    """Outbound CRM export attempts (provider-agnostic delivery log)."""

    __tablename__ = "crm_sync_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|synced|failed|skipped
    external_id: Mapped[str] = mapped_column(String(120), default="")
    external_url: Mapped[str] = mapped_column(String(500), default="")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class KBEmbedding(Base):
    """Vector index entry for a KB chunk (JSON-stored, brute-force cosine).

    Swappable for pgvector/Chroma/etc. behind services.vectorstore.VectorStore.
    `chunk_id` is the retrieval unit; `article_id` is kept for cheap joins and
    cascade cleanup.
    """

    __tablename__ = "kb_embeddings"
    __table_args__ = (
        UniqueConstraint("chunk_id", name="uq_kb_embedding_chunk"),
        Index("ix_embedding_ws_provider", "workspace_id", "provider", "model"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("kb_articles.id", ondelete="CASCADE"), index=True)
    chunk_id: Mapped[int | None] = mapped_column(
        ForeignKey("kb_chunks.id", ondelete="CASCADE"), nullable=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(60), default="")
    model: Mapped[str] = mapped_column(String(120), default="")
    vector: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Prompt(Base):
    """Versioned prompt. Rows sharing (workspace_id, name) form a version
    chain; at most one row per name is active."""

    __tablename__ = "prompts"
    __table_args__ = (UniqueConstraint("workspace_id", "name", "version", name="uq_prompt_ws_name_ver"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    kind: Mapped[str] = mapped_column(String(30), default="system")  # system | summary | custom
    content: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AppSetting(Base):
    """Workspace-scoped key/value runtime settings (branding, prompts,
    pipeline, notification templates, AI overrides)."""

    __tablename__ = "app_settings"
    __table_args__ = (UniqueConstraint("workspace_id", "key", name="uq_setting_ws_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"), default=DEFAULT_WORKSPACE_ID, index=True
    )
    key: Mapped[str] = mapped_column(String(120), index=True)
    value: Mapped[str] = mapped_column(Text, default="")


class ActivityLog(Base):
    """Per-lead timeline (status changes, notes, comments, emails, telegram)."""

    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    actor: Mapped[str] = mapped_column(String(120), default="system")
    action: Mapped[str] = mapped_column(
        String(60)
    )  # created | status_change | note | comment | email_sent | telegram ...
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    lead: Mapped[Lead] = relationship(back_populates="activities")


class AuditLog(Base):
    """Workspace-wide security & configuration audit trail."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    actor: Mapped[str] = mapped_column(String(255), default="")  # email or "system"
    action: Mapped[str] = mapped_column(String(60), index=True)  # login | logout | role_change | ...
    entity: Mapped[str] = mapped_column(
        String(60), default=""
    )  # lead | user | prompt | workflow | kb | settings
    entity_id: Mapped[str] = mapped_column(String(60), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Notification(Base):
    """Notification-center entry. channel=inapp rows are what users see in the
    UI bell; email/telegram rows double as delivery logs (status/attempts)."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    channel: Mapped[str] = mapped_column(
        String(20), default="inapp"
    )  # inapp | email | telegram | slack | discord
    event: Mapped[str] = mapped_column(String(60), default="")  # lead.created | lead.status_changed | ...
    title: Mapped[str] = mapped_column(String(255), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str] = mapped_column(String(500), default="")
    recipient: Mapped[str] = mapped_column(String(255), default="")  # email addr / chat id
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | sent | failed | skipped
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    read: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
