import asyncio
import json
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.public import resolve_workspace_id
from app.core.config import get_settings
from app.core.rate_limit import rate_limit
from app.db import get_db
from app.models import Attachment, Conversation
from app.schemas import (
    AttachmentOut,
    ChatMessageRequest,
    ChatMessageResponse,
    ChatStartRequest,
    ChatStartResponse,
)
from app.services import chat as chat_service

router = APIRouter(prefix="/api/chat", tags=["chat"])

_TAG_RE = re.compile(r"<[^>]+>")


def _sanitize(text: str) -> str:
    """Strip HTML tags from user input before it reaches storage or the LLM."""
    return _TAG_RE.sub("", text).strip()


def _get_active_conversation(db: Session, conversation_id: str) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conversation.status != "Active":
        raise HTTPException(status_code=409, detail="Conversation already finished")
    return conversation


@router.post("/start", response_model=ChatStartResponse)
def start_chat(body: ChatStartRequest, request: Request, db: Session = Depends(get_db)):
    rate_limit(request)
    conversation, reply = chat_service.start_conversation(
        db,
        client_name=_sanitize(body.client_name),
        client_email=_sanitize(body.email),
        language=body.language,
        workflow_id=body.workflow_id,
        workspace_id=resolve_workspace_id(db, body.workspace),
    )
    return ChatStartResponse(
        conversation_id=conversation.id,
        bot_message=reply.bot_message,
        quick_replies=reply.quick_replies,
    )


@router.post("/{conversation_id}/msg", response_model=ChatMessageResponse)
async def send_message(
    conversation_id: str,
    body: ChatMessageRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    rate_limit(request)
    conversation = _get_active_conversation(db, conversation_id)
    reply = await chat_service.process_message(db, conversation, _sanitize(body.text))
    return ChatMessageResponse(
        bot_message=reply.bot_message,
        quick_replies=reply.quick_replies,
        done=reply.done,
        lead_id=reply.lead_id,
        summary=reply.summary,
    )


@router.get("/{conversation_id}/stream")
async def stream_message(
    conversation_id: str,
    request: Request,
    text: str = Query(min_length=1, max_length=4000),
    db: Session = Depends(get_db),
):
    """Server-Sent Events: processes the user message, then streams the bot
    reply in small chunks followed by a final `meta` event."""
    rate_limit(request)
    conversation = _get_active_conversation(db, conversation_id)
    reply = await chat_service.process_message(db, conversation, _sanitize(text))

    async def event_stream():
        words = reply.bot_message.split(" ")
        chunk: list[str] = []
        for i, word in enumerate(words):
            chunk.append(word)
            if len(chunk) >= 4 or i == len(words) - 1:
                payload = json.dumps({"delta": " ".join(chunk) + ("" if i == len(words) - 1 else " ")})
                yield f"event: delta\ndata: {payload}\n\n"
                chunk = []
                await asyncio.sleep(0.04)
        meta = json.dumps(
            {
                "quick_replies": reply.quick_replies,
                "done": reply.done,
                "lead_id": reply.lead_id,
            }
        )
        yield f"event: meta\ndata: {meta}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


ALLOWED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".doc", ".docx",
    ".xls", ".xlsx", ".txt", ".md", ".zip", ".fig", ".sketch",
}


@router.post("/{conversation_id}/upload", response_model=AttachmentOut, status_code=201)
async def upload_file(
    conversation_id: str,
    file: UploadFile,
    request: Request,
    db: Session = Depends(get_db),
):
    rate_limit(request)
    conversation = _get_active_conversation(db, conversation_id)
    settings = get_settings()

    original = Path(file.filename or "upload").name
    suffix = Path(original).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail=f"File type {suffix or '(none)'} is not allowed")

    content = await file.read()
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File exceeds {settings.max_upload_mb} MB limit")

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    (settings.upload_dir / stored_name).write_bytes(content)

    attachment = Attachment(
        conversation_id=conversation.id,
        filename=original[:255],
        stored_name=stored_name,
        size=len(content),
        content_type=file.content_type or "application/octet-stream",
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return attachment
