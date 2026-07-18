from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db import get_db
from app.models import Prompt, User
from app.schemas import PromptCreate, PromptOut, PromptTestRequest
from app.services import audit, llm, runtime_settings
from app.services import prompts as prompt_service

router = APIRouter(prefix="/api/prompts", tags=["prompts"])


def _get_prompt(db: Session, prompt_id: int, user: User) -> Prompt:
    prompt = db.get(Prompt, prompt_id)
    if prompt is None or prompt.workspace_id != user.workspace_id:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return prompt


@router.get("", response_model=list[PromptOut])
def list_prompts(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return db.scalars(
        select(Prompt)
        .where(Prompt.workspace_id == admin.workspace_id)
        .order_by(Prompt.name, Prompt.version.desc())
    ).all()


@router.post("", response_model=PromptOut, status_code=201)
def create_prompt_version(
    body: PromptCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    prompt = prompt_service.create_version(
        db, admin.workspace_id, body.name, body.kind, body.content,
        created_by=admin.email, activate=body.activate,
    )
    audit.record(db, admin.workspace_id, admin.email, "prompt_edited", "prompt", prompt.id,
                 detail=f"{prompt.name} v{prompt.version}"
                 + (" (activated)" if body.activate else ""), request=request)
    return prompt


@router.post("/{prompt_id}/activate", response_model=PromptOut)
def activate_prompt(
    prompt_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Activate any version — activating an older version IS the rollback."""
    prompt = prompt_service.activate(db, _get_prompt(db, prompt_id, admin))
    audit.record(db, admin.workspace_id, admin.email, "prompt_activated", "prompt", prompt.id,
                 detail=f"{prompt.name} v{prompt.version}", request=request)
    return prompt


@router.post("/{prompt_id}/deactivate", response_model=PromptOut)
def deactivate_prompt(
    prompt_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    prompt = prompt_service.deactivate(db, _get_prompt(db, prompt_id, admin))
    audit.record(db, admin.workspace_id, admin.email, "prompt_deactivated", "prompt", prompt.id,
                 detail=f"{prompt.name} v{prompt.version}", request=request)
    return prompt


@router.post("/test")
async def test_prompt(
    body: PromptTestRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Dry-run a prompt against the configured provider. In mock mode this
    echoes a deterministic preview so the button works offline."""
    config = llm.resolve_config(runtime_settings.llm_overrides(db, admin.workspace_id))
    if config.provider == "mock":
        return {
            "provider": "mock",
            "output": f"[mock preview] system prompt accepted ({len(body.content)} chars). "
                      f"Sample client message: {body.sample_input!r} → the assistant would "
                      "respond according to your prompt once a real provider is configured.",
        }
    try:
        output = await llm.complete(
            [{"role": "user", "content": body.sample_input}], config=config, system=body.content
        )
        return {"provider": config.provider, "output": output}
    except llm.LLMError as exc:
        raise HTTPException(status_code=502, detail=f"Provider error: {exc}") from exc
