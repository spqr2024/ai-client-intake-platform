from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ── Auth ─────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str = ""
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=10, max_length=256)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: str
    role: str
    workspace_id: int


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    role: str = Field(default="manager", pattern="^(admin|manager)$")


class UserRoleUpdate(BaseModel):
    role: str = Field(pattern="^(admin|manager)$")


# ── Chat ─────────────────────────────────────────────────────────────────
class ChatStartRequest(BaseModel):
    client_name: str = Field(default="", max_length=255)
    email: str = Field(default="", max_length=255)
    language: str = Field(default="", max_length=8)
    workflow_id: int | None = None
    workspace: str = Field(default="default", max_length=64)  # workspace slug


class ChatStartResponse(BaseModel):
    conversation_id: str
    bot_message: str
    quick_replies: list[str] = []


class ChatMessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class ChatMessageResponse(BaseModel):
    bot_message: str
    quick_replies: list[str] = []
    done: bool = False
    lead_id: int | None = None
    summary: str | None = None


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    sender: str
    text: str
    meta: dict = {}
    created_at: datetime


class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    filename: str
    size: int
    content_type: str
    created_at: datetime


# ── Leads / CRM ──────────────────────────────────────────────────────────
class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    actor: str
    action: str
    detail: str
    created_at: datetime


class LeadListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_name: str
    client_name: str
    service: str
    budget: float | None
    timeline: str
    status: str
    priority: str
    tags: list = []
    follow_up_at: datetime | None = None
    score: int
    created_at: datetime


class LeadDetail(LeadListItem):
    client_email: str
    client_phone: str
    summary: str
    language: str
    assigned_to: UserOut | None = None
    updated_at: datetime
    messages: list[MessageOut] = []
    attachments: list[AttachmentOut] = []
    activities: list[ActivityOut] = []


class LeadUpdate(BaseModel):
    # Status validated dynamically against the workspace pipeline.
    status: str | None = Field(default=None, max_length=60)
    assigned_to_id: int | None = None
    project_name: str | None = None
    score: int | None = Field(default=None, ge=0, le=100)
    priority: str | None = Field(default=None, pattern="^(Low|Medium|High|Urgent)$")
    tags: list[str] | None = None
    follow_up_at: datetime | None = None
    clear_follow_up: bool = False


class NoteCreate(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    kind: str = Field(default="note", pattern="^(note|comment)$")


class ReplayEvent(BaseModel):
    at: datetime
    type: str  # message | activity | attachment
    sender: str = ""
    text: str = ""
    meta: dict = {}


class ReplayOut(BaseModel):
    conversation_id: str | None
    started_at: datetime | None
    ended_at: datetime | None
    language: str = "en"
    events: list[ReplayEvent] = []


# ── Workflows ────────────────────────────────────────────────────────────
class WorkflowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    is_default: int
    definition: dict
    prompt_name: str = ""
    updated_at: datetime


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    definition: dict
    is_default: bool = False
    prompt_name: str = Field(default="", max_length=120)


# ── Knowledge base ───────────────────────────────────────────────────────
class KBArticleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    content: str
    language: str
    updated_at: datetime


class KBArticleCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    language: str = Field(default="en", max_length=8)


# ── Prompts ──────────────────────────────────────────────────────────────
class PromptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    kind: str
    content: str
    version: int
    is_active: int
    created_by: str
    created_at: datetime


class PromptCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: str = Field(default="system", pattern="^(system|summary|custom)$")
    content: str = Field(min_length=1, max_length=20000)
    activate: bool = True


class PromptTestRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20000)
    sample_input: str = Field(default="Hi, I need a website for my bakery", max_length=2000)


# ── Notifications ────────────────────────────────────────────────────────
class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    channel: str
    event: str
    title: str
    body: str
    link: str
    recipient: str = ""
    status: str
    attempts: int
    error: str
    read: int
    created_at: datetime


# ── Audit ────────────────────────────────────────────────────────────────
class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    actor: str
    action: str
    entity: str
    entity_id: str
    detail: str
    ip: str
    created_at: datetime


# ── Settings / workspace ─────────────────────────────────────────────────
class SettingsOut(BaseModel):
    values: dict[str, str]


class SettingsUpdate(BaseModel):
    values: dict[str, str]


class WorkspaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    slug: str


class BrandingOut(BaseModel):
    company_name: str
    bot_name: str
    logo_url: str
    primary_color: str
    hero_title: str
    hero_subtitle: str


# ── Analytics ────────────────────────────────────────────────────────────
class AnalyticsSummary(BaseModel):
    total_conversations: int
    total_leads: int
    completion_rate: float
    conversion_rate: float
    average_budget: float
    average_score: float
    leads_by_status: dict[str, int]
    leads_by_service: dict[str, int]
    leads_per_day: list[dict]


class AIAnalytics(BaseModel):
    avg_messages_per_conversation: float
    avg_conversation_seconds: float
    abandonment_rate: float
    dropoff_by_node: dict[str, int]
    common_questions: list[dict]
    lead_quality: dict[str, int]
    avg_ai_confidence: float
    funnel: dict[str, int]
