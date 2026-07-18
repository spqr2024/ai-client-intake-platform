"""Knowledge-base retrieval and indexing: semantic-first, lexical fallback.

Retrieval pipeline
1. Embed the query via the configured EmbeddingProvider (provider-agnostic,
   see services.embeddings) and search the VectorStore by cosine similarity
   over *chunks*.
2. Blend in a lexical query-coverage score — cheap, language-agnostic, and a
   safety net for exact terms (prices, product names) that embeddings smear.
3. If no vectors exist yet (index not built, provider changed), lexical
   scoring alone keeps the KB functional.

Indexing is explicit and observable: every article carries an `index_status`
(pending → indexing → indexed/failed) so the admin UI can show what the bot
can actually answer from. Every search is logged for retrieval analytics.
"""

import logging
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.observability import Timer, metrics
from app.models import (
    DEFAULT_WORKSPACE_ID,
    KBChunk,
    KBSearchLog,
    KnowledgeBaseArticle,
    utcnow,
)
from app.services import documents, vectorstore
from app.services import embeddings as embedding_service

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[\w']+", re.UNICODE)

QUESTION_WORDS = {
    "what",
    "how",
    "where",
    "when",
    "why",
    "who",
    "which",
    "can",
    "do",
    "does",
    "is",
    "are",
    "що",
    "як",
    "де",
    "коли",
    "чому",
    "хто",
    "який",
    "яка",
    "чи",
    "скільки",
}

STOPWORDS = {
    "the",
    "a",
    "an",
    "is",
    "are",
    "was",
    "were",
    "do",
    "does",
    "did",
    "your",
    "you",
    "my",
    "our",
    "we",
    "it",
    "its",
    "of",
    "to",
    "in",
    "on",
    "for",
    "and",
    "or",
    "with",
    "how",
    "what",
    "where",
    "when",
    "why",
    "who",
    "which",
    "can",
    "could",
    "would",
    "i",
    "me",
    "at",
    "by",
    "be",
    "have",
    "has",
    "як",
    "що",
    "де",
    "коли",
    "чому",
    "хто",
    "який",
    "яка",
    "яке",
    "які",
    "чи",
    "ви",
    "ми",
    "ваш",
    "ваша",
    "ваші",
    "мій",
    "моя",
    "мої",
    "на",
    "в",
    "у",
    "з",
    "і",
    "та",
    "або",
    "до",
    "для",
    "це",
    "є",
}

SEMANTIC_WEIGHT = 0.7
LEXICAL_WEIGHT = 0.3
MIN_SCORE = 0.35


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "") if len(t) > 1]


def looks_like_question(text: str) -> bool:
    stripped = (text or "").strip().lower()
    if "?" in stripped:
        return True
    first = stripped.split(" ", 1)[0] if stripped else ""
    return first in QUESTION_WORDS and len(stripped.split()) >= 3


def _tokens_match(a: str, b: str) -> bool:
    if a == b:
        return True
    return len(a) >= 4 and len(b) >= 4 and a[:4] == b[:4]


def lexical_score(query: str, title: str, body: str) -> float:
    """Fraction of non-stopword query tokens covered, with a title bonus
    (FAQ titles are usually the question itself)."""
    query_tokens = [t for t in tokenize(query) if t not in STOPWORDS]
    if not query_tokens:
        return 0.0
    title_tokens = set(tokenize(title))
    body_tokens = set(tokenize(body))
    matched = 0.0
    for qt in query_tokens:
        in_title = any(_tokens_match(qt, t) for t in title_tokens)
        in_body = in_title or any(_tokens_match(qt, t) for t in body_tokens)
        if in_title:
            matched += 1.2
        elif in_body:
            matched += 1.0
    return min(matched / len(query_tokens), 1.0)


# ── Indexing ─────────────────────────────────────────────────────────────
def rebuild_chunks(db: Session, article: KnowledgeBaseArticle) -> list[KBChunk]:
    """Re-split an article into chunks, replacing the previous set."""
    for chunk in list(article.chunks):
        db.delete(chunk)
    db.flush()

    texts = documents.chunk_text(f"{article.title}\n\n{article.content}")
    chunks = [
        KBChunk(workspace_id=article.workspace_id, article_id=article.id, position=position, text=text)
        for position, text in enumerate(texts)
    ]
    for chunk in chunks:
        db.add(chunk)
    db.flush()
    article.chunk_count = len(chunks)
    return chunks


async def index_article(db: Session, article: KnowledgeBaseArticle) -> None:
    """(Re)build chunks and embeddings for one article, tracking status.

    Embedding failures are recorded on the article (status=failed) rather than
    raised: lexical retrieval keeps the KB usable, and the admin UI surfaces
    exactly which documents need attention.
    """
    article.index_status = "indexing"
    article.index_error = ""
    db.commit()

    provider = embedding_service.get_provider()
    store = vectorstore.get_store()
    try:
        with Timer("kb_index_seconds"):
            chunks = rebuild_chunks(db, article)
            store.remove_article(db, article.id)
            if chunks:
                vectors = await provider.embed([c.text for c in chunks])
                for chunk, vector in zip(chunks, vectors, strict=True):
                    store.upsert(
                        db, article.workspace_id, article.id, chunk.id, vector, provider.name, provider.model
                    )
        article.index_status = "indexed"
        article.indexed_at = utcnow()
        db.commit()
        metrics.counter(
            "kb_index_total", labels={"result": "success"}, help_text="KB article indexing operations"
        )
        logger.info("Indexed KB article", extra={"article_id": article.id, "chunks": article.chunk_count})
    except embedding_service.EmbeddingError as exc:
        article.index_status = "failed"
        article.index_error = str(exc)[:1000]
        db.commit()
        metrics.counter("kb_index_total", labels={"result": "failed"})
        logger.warning("Embedding failed for article %s: %s", article.id, exc)


def remove_article_index(db: Session, article_id: int) -> None:
    vectorstore.get_store().remove_article(db, article_id)
    db.commit()


async def reindex_workspace(db: Session, workspace_id: int) -> int:
    articles = db.scalars(
        select(KnowledgeBaseArticle).where(KnowledgeBaseArticle.workspace_id == workspace_id)
    ).all()
    for article in articles:
        await index_article(db, article)
    return len(articles)


# ── Retrieval ────────────────────────────────────────────────────────────
async def search(
    db: Session,
    query: str,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
    limit: int = 3,
    min_score: float = MIN_SCORE,
    log_source: str = "chat",
) -> list[tuple[KnowledgeBaseArticle, float]]:
    """Hybrid semantic + lexical retrieval, returning the best articles."""
    articles = db.scalars(
        select(KnowledgeBaseArticle).where(KnowledgeBaseArticle.workspace_id == workspace_id)
    ).all()
    if not articles:
        return []
    by_id = {article.id: article for article in articles}

    # Best semantic score per article (max over its chunks).
    semantic: dict[int, float] = {}
    provider = embedding_service.get_provider()
    try:
        with Timer("kb_search_seconds"):
            [query_vector] = await provider.embed([query])
            hits = vectorstore.get_store().search(
                db,
                workspace_id,
                query_vector,
                limit=50,
                provider=provider.name,
                model=provider.model,
            )
        for article_id, _chunk_id, score in hits:
            if score > semantic.get(article_id, 0.0):
                semantic[article_id] = max(score, 0.0)
    except embedding_service.EmbeddingError as exc:
        logger.warning("Semantic search unavailable (%s); lexical only", exc)

    scored: list[tuple[KnowledgeBaseArticle, float]] = []
    for article in articles:
        lex = lexical_score(query, article.title, article.content)
        score = SEMANTIC_WEIGHT * semantic.get(article.id, 0.0) + LEXICAL_WEIGHT * lex if semantic else lex
        if score >= min_score:
            scored.append((article, round(score, 3)))
    scored.sort(key=lambda item: item[1], reverse=True)
    results = scored[:limit]

    _log_search(db, workspace_id, query, results, log_source, by_id)
    return results


def _log_search(
    db: Session,
    workspace_id: int,
    query: str,
    results: list[tuple[KnowledgeBaseArticle, float]],
    source: str,
    by_id: dict[int, KnowledgeBaseArticle],
) -> None:
    top = results[0] if results else None
    db.add(
        KBSearchLog(
            workspace_id=workspace_id,
            query=query[:500],
            top_article_id=top[0].id if top else None,
            top_score=top[1] if top else 0.0,
            hit=1 if top else 0,
            source=source,
        )
    )
    if top:
        article = by_id.get(top[0].id)
        if article is not None:
            article.hit_count += 1
    db.commit()
    metrics.counter(
        "kb_search_total", labels={"result": "hit" if top else "miss"}, help_text="Knowledge-base searches"
    )


def statistics(db: Session, workspace_id: int) -> dict:
    """Retrieval analytics for the admin KB dashboard."""
    total_searches = (
        db.scalar(select(func.count(KBSearchLog.id)).where(KBSearchLog.workspace_id == workspace_id)) or 0
    )
    hits = (
        db.scalar(
            select(func.count(KBSearchLog.id)).where(
                KBSearchLog.workspace_id == workspace_id, KBSearchLog.hit == 1
            )
        )
        or 0
    )
    by_status = dict(
        db.execute(
            select(KnowledgeBaseArticle.index_status, func.count(KnowledgeBaseArticle.id))
            .where(KnowledgeBaseArticle.workspace_id == workspace_id)
            .group_by(KnowledgeBaseArticle.index_status)
        ).all()
    )
    top_articles = db.execute(
        select(KnowledgeBaseArticle.id, KnowledgeBaseArticle.title, KnowledgeBaseArticle.hit_count)
        .where(KnowledgeBaseArticle.workspace_id == workspace_id, KnowledgeBaseArticle.hit_count > 0)
        .order_by(KnowledgeBaseArticle.hit_count.desc())
        .limit(5)
    ).all()
    unanswered = db.execute(
        select(KBSearchLog.query, func.count(KBSearchLog.id).label("n"))
        .where(KBSearchLog.workspace_id == workspace_id, KBSearchLog.hit == 0)
        .group_by(KBSearchLog.query)
        .order_by(func.count(KBSearchLog.id).desc())
        .limit(10)
    ).all()

    return {
        "total_searches": total_searches,
        "hit_rate": round(hits / total_searches, 3) if total_searches else 0.0,
        "articles_by_status": by_status,
        "indexed_chunks": vectorstore.get_store().count(db, workspace_id),
        "top_articles": [{"id": row[0], "title": row[1], "hits": row[2]} for row in top_articles],
        "unanswered_queries": [{"query": row[0], "count": row[1]} for row in unanswered],
    }
