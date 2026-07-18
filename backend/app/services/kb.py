"""Knowledge-base retrieval.

Pure-Python lexical retrieval tuned for FAQ-sized corpora: the score is the
fraction of (non-stopword) query tokens covered by the article, with fuzzy
prefix matching ("located" ~ "locations") and a bonus for title hits. Zero
external services; the retriever can be swapped for a real vector store
(pgvector, Chroma, Redis) behind the same `search()` signature.
"""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import KnowledgeBaseArticle

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


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "") if len(t) > 1]


def looks_like_question(text: str) -> bool:
    stripped = (text or "").strip().lower()
    if "?" in stripped:
        return True
    first = stripped.split(" ", 1)[0] if stripped else ""
    return first in QUESTION_WORDS and len(stripped.split()) >= 3


def _tokens_match(a: str, b: str) -> bool:
    """Exact match, or shared 4-char prefix for longer words — a cheap stand-in
    for stemming that links 'located'/'locations', 'takes'/'take', etc."""
    if a == b:
        return True
    return len(a) >= 4 and len(b) >= 4 and a[:4] == b[:4]


def _score(query_tokens: list[str], title_tokens: set[str], content_tokens: set[str]) -> float:
    if not query_tokens:
        return 0.0
    matched = 0.0
    for qt in query_tokens:
        in_title = any(_tokens_match(qt, t) for t in title_tokens)
        in_content = in_title or any(_tokens_match(qt, t) for t in content_tokens)
        if in_title:
            matched += 1.2  # title hits count extra: FAQ titles are the question
        elif in_content:
            matched += 1.0
    return matched / len(query_tokens)


def search(
    db: Session, query: str, limit: int = 3, min_score: float = 0.45
) -> list[tuple[KnowledgeBaseArticle, float]]:
    articles = db.scalars(select(KnowledgeBaseArticle)).all()
    if not articles:
        return []
    query_tokens = [t for t in tokenize(query) if t not in STOPWORDS]
    if not query_tokens:
        return []

    scored = []
    for article in articles:
        title_tokens = set(tokenize(article.title))
        content_tokens = set(tokenize(article.content))
        score = _score(query_tokens, title_tokens, content_tokens)
        if score >= min_score:
            scored.append((article, round(score, 3)))
    scored.sort(key=lambda s: s[1], reverse=True)
    return scored[:limit]
