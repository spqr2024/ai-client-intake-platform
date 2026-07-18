"""Prompt management: versioned, per-workspace prompts with activation.

Resolution order for the chat runtime:
1. Workflow-assigned prompt (workflow.prompt_name) — active version.
2. Active prompt named "system" / "summary".
3. Workspace runtime setting (legacy path, still editable).
4. Built-in default.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Prompt
from app.services import runtime_settings


def get_active(db: Session, workspace_id: int, name: str) -> Prompt | None:
    return db.scalars(
        select(Prompt).where(Prompt.workspace_id == workspace_id, Prompt.name == name, Prompt.is_active == 1)
    ).first()


def next_version(db: Session, workspace_id: int, name: str) -> int:
    current = db.scalar(
        select(func.max(Prompt.version)).where(Prompt.workspace_id == workspace_id, Prompt.name == name)
    )
    return int(current or 0) + 1


def create_version(
    db: Session,
    workspace_id: int,
    name: str,
    kind: str,
    content: str,
    created_by: str,
    activate: bool = True,
) -> Prompt:
    prompt = Prompt(
        workspace_id=workspace_id,
        name=name,
        kind=kind,
        content=content,
        version=next_version(db, workspace_id, name),
        created_by=created_by,
    )
    db.add(prompt)
    if activate:
        _deactivate_all(db, workspace_id, name)
        prompt.is_active = 1
    db.commit()
    db.refresh(prompt)
    return prompt


def activate(db: Session, prompt: Prompt) -> Prompt:
    _deactivate_all(db, prompt.workspace_id, prompt.name)
    prompt.is_active = 1
    db.commit()
    db.refresh(prompt)
    return prompt


def deactivate(db: Session, prompt: Prompt) -> Prompt:
    prompt.is_active = 0
    db.commit()
    db.refresh(prompt)
    return prompt


def _deactivate_all(db: Session, workspace_id: int, name: str) -> None:
    for row in db.scalars(
        select(Prompt).where(Prompt.workspace_id == workspace_id, Prompt.name == name)
    ).all():
        row.is_active = 0


def resolve(db: Session, workspace_id: int, kind: str, workflow_prompt_name: str = "") -> str:
    """Effective prompt text for `kind` ("system" | "summary")."""
    if workflow_prompt_name:
        assigned = get_active(db, workspace_id, workflow_prompt_name)
        if assigned is not None:
            return assigned.content
    named = get_active(db, workspace_id, kind)
    if named is not None:
        return named.content
    return runtime_settings.get(db, f"{kind}_prompt", workspace_id)
