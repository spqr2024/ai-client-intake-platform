from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ── Auth ─────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: str
    role: str


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    role: str = Field(default="manager", pattern="^(admin|manager)$")


# ── Chat ─────────────────────────────────────────────────────────────────
class ChatStartRequest(BaseModel):
    client_name: str = Field(default="", max_length=255)
    email: str = Field(default="", max_length=255)
    language: str = Field(default="", max_length=8)
    workflow_id: int | None = None


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
    created_at: datetime


class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    filename: str
    size: int
    content_type: str
    created_at: datetime


# ── Leads ────────────────────────────────────────────────────────────────
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
    status: str | None = Field(
        default=None,
        pattern="^(New|Qualified|In Progress|Rejected|Converted|Closed|Incomplete)$",
    )
    assigned_to_id: int | None = None
    project_name: str | None = None
    score: int | None = Field(default=None, ge=0, le=100)


class NoteCreate(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


# ── Workflows ────────────────────────────────────────────────────────────
class WorkflowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    is_default: int
    definition: dict
    updated_at: datetime


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    definition: dict
    is_default: bool = False


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


# ── Settings ─────────────────────────────────────────────────────────────
class SettingsOut(BaseModel):
    values: dict[str, str]


class SettingsUpdate(BaseModel):
    values: dict[str, str]


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
