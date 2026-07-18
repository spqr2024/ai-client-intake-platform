from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db import get_db
from app.models import User, Workflow
from app.schemas import WorkflowCreate, WorkflowOut
from app.services import audit, workflow_templates
from app.services import workflow as wf

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


def _validate_definition(definition: dict) -> None:
    nodes = definition.get("nodes")
    start = definition.get("start")
    if not isinstance(nodes, dict) or not nodes:
        raise HTTPException(status_code=422, detail="Definition must contain a non-empty 'nodes' map")
    if start not in nodes:
        raise HTTPException(status_code=422, detail="'start' must reference an existing node")
    for node_id, node in nodes.items():
        next_id = node.get("next", "")
        if next_id and next_id not in nodes:
            raise HTTPException(status_code=422, detail=f"Node '{node_id}' points to unknown node '{next_id}'")
        for branch in node.get("branches", []):
            goto = branch.get("goto", "")
            if goto and goto not in nodes:
                raise HTTPException(status_code=422, detail=f"Branch in '{node_id}' points to unknown node '{goto}'")


def _get_workflow(db: Session, workflow_id: int, user: User) -> Workflow:
    workflow = db.get(Workflow, workflow_id)
    if workflow is None or workflow.workspace_id != user.workspace_id:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


@router.get("/templates")
def list_templates(_: User = Depends(require_admin)):
    """Starter flows and reusable step blueprints for the visual builder."""
    return {
        "templates": [
            {"key": t["key"], "name": t["name"], "description": t["description"],
             "definition": t["definition"]}
            for t in workflow_templates.TEMPLATES
        ],
        "node_library": workflow_templates.NODE_LIBRARY,
        "field_types": ["text", "choice", "number", "email", "phone"],
    }


@router.post("/analyze")
def analyze_definition(body: dict, _: User = Depends(require_admin)):
    """Structural report (reachability, dead ends, loops) for the builder's
    live validation panel. Warnings never block saving."""
    return workflow_templates.analyze(body.get("definition", body))


@router.post("/simulate")
def simulate(body: dict, _: User = Depends(require_admin)):
    """Dry-run a flow against scripted answers so an admin can test a
    conversation before publishing it — no LLM or database involved."""
    definition = body.get("definition", {})
    answers = body.get("answers", [])
    language = body.get("language", "en")
    _validate_definition(definition)

    transcript: list[dict] = []
    step = wf.start(definition, {}, language)
    transcript.append({"sender": "bot", "text": step.reply,
                       "quick_replies": step.quick_replies, "node": step.state.get("current_node")})
    state = step.state
    for answer in answers[:50]:
        if step.done:
            break
        transcript.append({"sender": "user", "text": str(answer)})
        step = wf.advance(definition, state, str(answer), language)
        state = step.state
        if step.done:
            transcript.append({"sender": "bot", "text": "[flow complete — lead would be created]",
                               "quick_replies": [], "node": None})
        else:
            transcript.append({"sender": "bot", "text": step.reply,
                               "quick_replies": step.quick_replies,
                               "node": state.get("current_node"),
                               "clarification": step.needs_clarification})
    return {"transcript": transcript, "collected": state.get("answers", {}), "done": step.done}


@router.get("", response_model=list[WorkflowOut])
def list_workflows(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return db.scalars(
        select(Workflow).where(Workflow.workspace_id == admin.workspace_id).order_by(Workflow.id)
    ).all()


@router.post("", response_model=WorkflowOut, status_code=201)
def create_workflow(
    body: WorkflowCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    _validate_definition(body.definition)
    exists = db.scalars(
        select(Workflow).where(
            Workflow.workspace_id == admin.workspace_id, Workflow.name == body.name
        )
    ).first()
    if exists:
        raise HTTPException(status_code=409, detail="Workflow name already exists")
    workflow = Workflow(
        workspace_id=admin.workspace_id, name=body.name, definition=body.definition,
        is_default=1 if body.is_default else 0, prompt_name=body.prompt_name,
    )
    if body.is_default:
        for other in db.scalars(
            select(Workflow).where(Workflow.workspace_id == admin.workspace_id)
        ).all():
            other.is_default = 0
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    audit.record(db, admin.workspace_id, admin.email, "workflow_edited", "workflow", workflow.id,
                 detail=f"created: {workflow.name}", request=request)
    return workflow


@router.put("/{workflow_id}", response_model=WorkflowOut)
def update_workflow(
    workflow_id: int,
    body: WorkflowCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    workflow = _get_workflow(db, workflow_id, admin)
    _validate_definition(body.definition)
    workflow.name = body.name
    workflow.definition = body.definition
    workflow.prompt_name = body.prompt_name
    if body.is_default:
        for other in db.scalars(
            select(Workflow).where(Workflow.workspace_id == admin.workspace_id)
        ).all():
            other.is_default = 0
        workflow.is_default = 1
    db.commit()
    db.refresh(workflow)
    audit.record(db, admin.workspace_id, admin.email, "workflow_edited", "workflow", workflow.id,
                 detail=f"updated: {workflow.name}", request=request)
    return workflow


@router.delete("/{workflow_id}", status_code=204)
def delete_workflow(
    workflow_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    workflow = _get_workflow(db, workflow_id, admin)
    if workflow.is_default:
        raise HTTPException(status_code=400, detail="Cannot delete the default workflow")
    name = workflow.name
    db.delete(workflow)
    db.commit()
    audit.record(db, admin.workspace_id, admin.email, "workflow_edited", "workflow", workflow_id,
                 detail=f"deleted: {name}", request=request)
