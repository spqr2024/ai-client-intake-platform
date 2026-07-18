from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.db import get_db
from app.models import KnowledgeBaseArticle, User
from app.schemas import KBArticleCreate, KBArticleOut
from app.services import kb as kb_service

router = APIRouter(prefix="/api/kb", tags=["knowledge-base"])


@router.get("", response_model=list[KBArticleOut])
def list_articles(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(KnowledgeBaseArticle).order_by(KnowledgeBaseArticle.id)).all()


@router.get("/search")
def search_articles(
    q: str = Query(min_length=2, max_length=200),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    hits = kb_service.search(db, q, limit=5)
    return [
        {"id": a.id, "title": a.title, "score": round(s, 3)}
        for a, s in hits
    ]


@router.post("", response_model=KBArticleOut, status_code=201)
def create_article(body: KBArticleCreate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    article = KnowledgeBaseArticle(title=body.title, content=body.content, language=body.language)
    db.add(article)
    db.commit()
    db.refresh(article)
    return article


@router.put("/{article_id}", response_model=KBArticleOut)
def update_article(
    article_id: int, body: KBArticleCreate, db: Session = Depends(get_db), _: User = Depends(require_admin)
):
    article = db.get(KnowledgeBaseArticle, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    article.title = body.title
    article.content = body.content
    article.language = body.language
    db.commit()
    db.refresh(article)
    return article


@router.delete("/{article_id}", status_code=204)
def delete_article(article_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    article = db.get(KnowledgeBaseArticle, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    db.delete(article)
    db.commit()
