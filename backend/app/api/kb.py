from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.db import get_db
from app.models import KnowledgeBaseArticle, User
from app.schemas import KBArticleCreate, KBArticleOut
from app.services import audit
from app.services import kb as kb_service

router = APIRouter(prefix="/api/kb", tags=["knowledge-base"])


def _get_article(db: Session, article_id: int, user: User) -> KnowledgeBaseArticle:
    article = db.get(KnowledgeBaseArticle, article_id)
    if article is None or article.workspace_id != user.workspace_id:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


@router.get("", response_model=list[KBArticleOut])
def list_articles(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.scalars(
        select(KnowledgeBaseArticle)
        .where(KnowledgeBaseArticle.workspace_id == user.workspace_id)
        .order_by(KnowledgeBaseArticle.id)
    ).all()


@router.get("/search")
async def search_articles(
    q: str = Query(min_length=2, max_length=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    hits = await kb_service.search(db, q, workspace_id=user.workspace_id, limit=5)
    return [{"id": a.id, "title": a.title, "score": round(s, 3)} for a, s in hits]


@router.post("", response_model=KBArticleOut, status_code=201)
async def create_article(
    body: KBArticleCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    article = KnowledgeBaseArticle(
        workspace_id=admin.workspace_id, title=body.title, content=body.content,
        language=body.language,
    )
    db.add(article)
    db.commit()
    db.refresh(article)
    await kb_service.index_article(db, article)
    audit.record(db, admin.workspace_id, admin.email, "kb_updated", "kb", article.id,
                 detail=f"created: {article.title}", request=request)
    return article


@router.put("/{article_id}", response_model=KBArticleOut)
async def update_article(
    article_id: int,
    body: KBArticleCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    article = _get_article(db, article_id, admin)
    article.title = body.title
    article.content = body.content
    article.language = body.language
    db.commit()
    db.refresh(article)
    await kb_service.index_article(db, article)
    audit.record(db, admin.workspace_id, admin.email, "kb_updated", "kb", article.id,
                 detail=f"updated: {article.title}", request=request)
    return article


@router.delete("/{article_id}", status_code=204)
def delete_article(
    article_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    article = _get_article(db, article_id, admin)
    title = article.title
    kb_service.remove_article_index(db, article.id)
    db.delete(article)
    db.commit()
    audit.record(db, admin.workspace_id, admin.email, "kb_updated", "kb", article_id,
                 detail=f"deleted: {title}", request=request)


@router.post("/reindex")
async def reindex(
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Rebuild the semantic index (needed after switching embedding providers)."""
    count = await kb_service.reindex_workspace(db, admin.workspace_id)
    audit.record(db, admin.workspace_id, admin.email, "kb_updated", "kb", "",
                 detail=f"reindexed {count} articles", request=request)
    return {"indexed": count}
