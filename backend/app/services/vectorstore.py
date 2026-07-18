"""Vector store abstraction.

The default implementation persists vectors as JSON rows in the relational
database and does brute-force cosine search — right-sized for FAQ/handbook
corpora (thousands of chunks) with zero extra infrastructure. The interface
is the contract: a pgvector / Chroma / Redis implementation slots in behind
`VectorStore` without touching retrieval callers.

Retrieval operates on *chunks*, not whole articles, so long documents are
matched by the passage that actually answers the question.
"""

import math
from abc import ABC, abstractmethod

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import KBChunk, KBEmbedding


class VectorStore(ABC):
    @abstractmethod
    def upsert(self, db: Session, workspace_id: int, article_id: int, chunk_id: int,
               vector: list[float], provider: str, model: str) -> None: ...

    @abstractmethod
    def remove_article(self, db: Session, article_id: int) -> None: ...

    @abstractmethod
    def search(self, db: Session, workspace_id: int, vector: list[float],
               limit: int, provider: str, model: str) -> list[tuple[int, int, float]]:
        """Return [(article_id, chunk_id, cosine_similarity)] sorted descending."""

    @abstractmethod
    def count(self, db: Session, workspace_id: int) -> int: ...


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if not norm_a or not norm_b:
        return 0.0
    return dot / (norm_a * norm_b)


class DatabaseVectorStore(VectorStore):
    def upsert(self, db: Session, workspace_id: int, article_id: int, chunk_id: int,
               vector: list[float], provider: str, model: str) -> None:
        row = db.scalars(select(KBEmbedding).where(KBEmbedding.chunk_id == chunk_id)).first()
        if row is None:
            row = KBEmbedding(workspace_id=workspace_id, article_id=article_id, chunk_id=chunk_id)
            db.add(row)
        row.workspace_id = workspace_id
        row.article_id = article_id
        row.vector = vector
        row.provider = provider
        row.model = model

    def remove_article(self, db: Session, article_id: int) -> None:
        db.execute(delete(KBEmbedding).where(KBEmbedding.article_id == article_id))

    def search(self, db: Session, workspace_id: int, vector: list[float],
               limit: int, provider: str, model: str) -> list[tuple[int, int, float]]:
        rows = db.execute(
            select(KBEmbedding.article_id, KBEmbedding.chunk_id, KBEmbedding.vector).where(
                KBEmbedding.workspace_id == workspace_id,
                KBEmbedding.provider == provider,
                KBEmbedding.model == model,
            )
        ).all()
        scored = [
            (article_id, chunk_id, cosine(vector, stored))
            for article_id, chunk_id, stored in rows
        ]
        scored.sort(key=lambda item: item[2], reverse=True)
        return scored[:limit]

    def count(self, db: Session, workspace_id: int) -> int:
        return len(
            db.execute(
                select(KBEmbedding.id).where(KBEmbedding.workspace_id == workspace_id)
            ).all()
        )

    def prune_orphans(self, db: Session, article_id: int, keep_chunk_ids: set[int]) -> None:
        """Drop embeddings whose chunk disappeared after a re-chunk."""
        stale = db.scalars(
            select(KBEmbedding).where(KBEmbedding.article_id == article_id)
        ).all()
        for row in stale:
            if row.chunk_id not in keep_chunk_ids:
                db.delete(row)
        db.execute(
            delete(KBChunk).where(
                KBChunk.article_id == article_id, KBChunk.id.notin_(keep_chunk_ids or {0})
            )
        )


_store: VectorStore | None = None


def get_store() -> VectorStore:
    global _store
    if _store is None:
        _store = DatabaseVectorStore()
    return _store
