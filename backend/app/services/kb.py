"""Knowledge-base retrieval: semantic-first, lexical fallback.

Retrieval pipeline:
1. Embed the query via the configured EmbeddingProvider (provider-agnostic,
   see services.embeddings) and search the VectorStore by cosine similarity.
2. Blend in a lexical query-coverage score — cheap, language-agnostic, and a
   safety net for exact terms (prices, product names) that embeddings smear.
3. If no vectors exist yet (index not built, provider changed), lexical
   scoring alone keeps the KB functional.

Indexing is incremental: articles are (re)embedded on create/update through
`index_article`, and `reindex_workspace` rebuilds after a provider switch.
"""

import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DEFAULT_WORKSPACE_ID, KnowledgeBaseArticle
from app.services import embeddings as embedding_service
from app.services import vectorstore

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[\w']+", re.UNICODE)

QUESTION_WORDS = {
    "what", "how", "where", "when", "why", "who", "which", "can", "do", "does", "is", "are",
    "що", "як", "де", "коли", "чому", "хто", "який", "яка", "чи", "скільки",
}

STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "do", "does", "did", "your", "you",
    "my", "our", "we", "it", "its", "of", "to", "in", "on", "for", "and", "or", "with",
    "how", "what", "where", "when", "why", "who", "which", "can", "could", "would",
    "i", "me", "at", "by", "be", "have", "has",
    "як", "що", "де", "коли", "чому", "хто", "який", "яка", "яке", "які", "чи",
    "ви", "ми", "ваш", "ваша", "ваші", "мій", "моя", "мої", "на", "в", "у", "з", "і",
    "та", "або", "до", "для", "це", "є",
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


def lexical_score(query: str, article: KnowledgeBaseArticle) -> float:
    """Fraction of non-stopword query tokens covered by the article, with a
    bonus for title hits (FAQ titles are usually the question itself)."""
    query_tokens = [t for t in tokenize(query) if t not in STOPWORDS]
    if not query_tokens:
        return 0.0
    title_tokens = set(tokenize(article.title))
    content_tokens = set(tokenize(article.content))
    matched = 0.0
    for qt in query_tokens:
        in_title = any(_tokens_match(qt, t) for t in title_tokens)
        in_content = in_title or any(_tokens_match(qt, t) for t in content_tokens)
        if in_title:
            matched += 1.2
        elif in_content:
            matched += 1.0
    return min(matched / len(query_tokens), 1.0)


async def index_article(db: Session, article: KnowledgeBaseArticle) -> None:
    """(Re)build the vector for one article. Failures are logged, never raised:
    lexical fallback keeps retrieval working."""
    provider = embedding_service.get_provider()
    try:
        [vector] = await provider.embed([f"{article.title}\n{article.content}"])
        vectorstore.get_store().upsert(
            db, article.workspace_id, article.id, vector, provider.name, provider.model
        )
    except embedding_service.EmbeddingError as exc:
        logger.warning("Embedding failed for article %s: %s", article.id, exc)


def remove_article_index(db: Session, article_id: int) -> None:
    vectorstore.get_store().remove(db, article_id)


async def reindex_workspace(db: Session, workspace_id: int) -> int:
    articles = db.scalars(
        select(KnowledgeBaseArticle).where(KnowledgeBaseArticle.workspace_id == workspace_id)
    ).all()
    for article in articles:
        await index_article(db, article)
    return len(articles)


async def search(
    db: Session,
    query: str,
    workspace_id: int = DEFAULT_WORKSPACE_ID,
    limit: int = 3,
    min_score: float = MIN_SCORE,
) -> list[tuple[KnowledgeBaseArticle, float]]:
    articles = db.scalars(
        select(KnowledgeBaseArticle).where(KnowledgeBaseArticle.workspace_id == workspace_id)
    ).all()
    if not articles:
        return []

    semantic: dict[int, float] = {}
    provider = embedding_service.get_provider()
    try:
        [query_vector] = await provider.embed([query])
        hits = vectorstore.get_store().search(
            db, workspace_id, query_vector, limit=len(articles),
            provider=provider.name, model=provider.model,
        )
        semantic = {article_id: max(score, 0.0) for article_id, score in hits}
    except embedding_service.EmbeddingError as exc:
        logger.warning("Semantic search unavailable (%s); lexical only", exc)

    scored: list[tuple[KnowledgeBaseArticle, float]] = []
    for article in articles:
        lex = lexical_score(query, article)
        if semantic:
            score = SEMANTIC_WEIGHT * semantic.get(article.id, 0.0) + LEXICAL_WEIGHT * lex
        else:
            score = lex
        if score >= min_score:
            scored.append((article, round(score, 3)))
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:limit]
