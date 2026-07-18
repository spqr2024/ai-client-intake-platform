from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, require_admin
from app.core.config import get_settings
from app.db import get_db
from app.models import KBArticleVersion, KnowledgeBaseArticle, User
from app.schemas import KBArticleCreate, KBArticleOut, KBStats, KBVersionOut
from app.services import audit, documents
from app.services import kb as kb_service

router = APIRouter(prefix="/api/kb", tags=["knowledge-base"])


def _get_article(db: Session, article_id: int, user: User) -> KnowledgeBaseArticle:
    article = db.get(KnowledgeBaseArticle, article_id)
    if article is None or article.workspace_id != user.workspace_id:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


def _snapshot(db: Session, article: KnowledgeBaseArticle, actor: str) -> None:
    """Persist the current state before it is overwritten."""
    db.add(
        KBArticleVersion(
            article_id=article.id, version=article.version, title=article.title,
            content=article.content, created_by=actor,
        )
    )


@router.get("", response_model=list[KBArticleOut])
def list_articles(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.scalars(
        select(KnowledgeBaseArticle)
        .where(KnowledgeBaseArticle.workspace_id == user.workspace_id)
        .order_by(KnowledgeBaseArticle.id)
    ).all()


@router.get("/stats", response_model=KBStats)
def stats(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Indexing state + retrieval analytics for the KB dashboard."""
    return kb_service.statistics(db, user.workspace_id)


@router.get("/formats")
def supported_formats(_: User = Depends(get_current_user)):
    """Which upload formats this deployment can actually extract (optional
    dependencies may be missing), so the UI can disable what won't work."""
    available = {}
    for extension, source_type in documents.SUPPORTED_EXTENSIONS.items():
        if source_type == "pdf":
            try:
                import pypdf  # noqa: F401

                available[extension] = True
            except ImportError:
                available[extension] = False
        elif source_type == "docx":
            try:
                import docx  # noqa: F401

                available[extension] = True
            except ImportError:
                available[extension] = False
        else:
            available[extension] = True
    return {"formats": available, "max_mb": get_settings().max_upload_mb}


@router.get("/search")
async def search_articles(
    q: str = Query(min_length=2, max_length=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    hits = await kb_service.search(db, q, workspace_id=user.workspace_id, limit=5,
                                   log_source="admin")
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
        language=body.language, source_type="manual",
        doc_metadata={"characters": len(body.content)},
    )
    db.add(article)
    db.commit()
    db.refresh(article)
    await kb_service.index_article(db, article)
    audit.record(db, admin.workspace_id, admin.email, "kb_updated", "kb", article.id,
                 detail=f"created: {article.title}", request=request)
    return article


@router.post("/upload", response_model=KBArticleOut, status_code=201)
async def upload_document(
    file: UploadFile,
    request: Request,
    title: str = Query(default="", max_length=255),
    language: str = Query(default="en", max_length=8),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Ingest a PDF / DOCX / Markdown / TXT document into the knowledge base."""
    settings = get_settings()
    data = await file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File exceeds {settings.max_upload_mb} MB limit")

    filename = (file.filename or "document").split("/")[-1].split("\\")[-1]
    try:
        source_type, text, metadata = documents.extract(filename, data)
    except documents.UnsupportedDocument as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    article = KnowledgeBaseArticle(
        workspace_id=admin.workspace_id,
        title=(title or filename.rsplit(".", 1)[0])[:255],
        content=text,
        language=language,
        source_type=source_type,
        source_filename=filename[:255],
        doc_metadata={**metadata, "content_type": file.content_type or ""},
    )
    db.add(article)
    db.commit()
    db.refresh(article)
    await kb_service.index_article(db, article)
    audit.record(db, admin.workspace_id, admin.email, "kb_updated", "kb", article.id,
                 detail=f"uploaded {source_type}: {filename}", request=request)
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
    _snapshot(db, article, admin.email)
    article.version += 1
    article.title = body.title
    article.content = body.content
    article.language = body.language
    article.doc_metadata = {**(article.doc_metadata or {}), "characters": len(body.content)}
    db.commit()
    db.refresh(article)
    await kb_service.index_article(db, article)
    audit.record(db, admin.workspace_id, admin.email, "kb_updated", "kb", article.id,
                 detail=f"updated to v{article.version}: {article.title}", request=request)
    return article


@router.get("/{article_id}/versions", response_model=list[KBVersionOut])
def list_versions(article_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    article = db.scalars(
        select(KnowledgeBaseArticle)
        .options(selectinload(KnowledgeBaseArticle.versions))
        .where(KnowledgeBaseArticle.id == article_id,
               KnowledgeBaseArticle.workspace_id == user.workspace_id)
    ).first()
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return article.versions


@router.post("/{article_id}/versions/{version}/restore", response_model=KBArticleOut)
async def restore_version(
    article_id: int,
    version: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Roll an article back to a previous version (recorded as a new version)."""
    article = _get_article(db, article_id, admin)
    snapshot = db.scalars(
        select(KBArticleVersion).where(
            KBArticleVersion.article_id == article.id, KBArticleVersion.version == version
        )
    ).first()
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Version not found")

    _snapshot(db, article, admin.email)
    article.version += 1
    article.title = snapshot.title
    article.content = snapshot.content
    db.commit()
    db.refresh(article)
    await kb_service.index_article(db, article)
    audit.record(db, admin.workspace_id, admin.email, "kb_updated", "kb", article.id,
                 detail=f"restored v{version} as v{article.version}", request=request)
    return article


@router.post("/{article_id}/reindex", response_model=KBArticleOut)
async def reindex_article(
    article_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    article = _get_article(db, article_id, admin)
    await kb_service.index_article(db, article)
    db.refresh(article)
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
    """Rebuild the semantic index for every article (after a provider switch)."""
    count = await kb_service.reindex_workspace(db, admin.workspace_id)
    audit.record(db, admin.workspace_id, admin.email, "kb_updated", "kb", "",
                 detail=f"reindexed {count} articles", request=request)
    return {"indexed": count}
