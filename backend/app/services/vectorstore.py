"""Vector store abstraction.

The default implementation persists vectors as JSON rows in the relational
database and does brute-force cosine search — exactly right for FAQ-scale
corpora (hundreds of documents) with zero extra infrastructure. The
interface is the contract: a pgvector / Chroma / Redis implementation slots
in behind `VectorStore` without touching retrieval callers.
"""

import math
from abc import ABC, abstractmethod

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import KBEmbedding


class VectorStore(ABC):
    @abstractmethod
    def upsert(self, db: Session, workspace_id: int, article_id: int,
               vector: list[float], provider: str, model: str) -> None: ...

    @abstractmethod
    def remove(self, db: Session, article_id: int) -> None: ...

    @abstractmethod
    def search(self, db: Session, workspace_id: int, vector: list[float],
               limit: int, provider: str, model: str) -> list[tuple[int, float]]:
        """Return [(article_id, cosine_similarity)] sorted descending."""


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
    def upsert(self, db: Session, workspace_id: int, article_id: int,
               vector: list[float], provider: str, model: str) -> None:
        row = db.scalars(select(KBEmbedding).where(KBEmbedding.article_id == article_id)).first()
        if row is None:
            row = KBEmbedding(workspace_id=workspace_id, article_id=article_id)
            db.add(row)
        row.workspace_id = workspace_id
        row.vector = vector
        row.provider = provider
        row.model = model
        db.commit()

    def remove(self, db: Session, article_id: int) -> None:
        db.execute(delete(KBEmbedding).where(KBEmbedding.article_id == article_id))
        db.commit()

    def search(self, db: Session, workspace_id: int, vector: list[float],
               limit: int, provider: str, model: str) -> list[tuple[int, float]]:
        rows = db.scalars(
            select(KBEmbedding).where(
                KBEmbedding.workspace_id == workspace_id,
                KBEmbedding.provider == provider,
                KBEmbedding.model == model,
            )
        ).all()
        scored = [(row.article_id, cosine(vector, row.vector)) for row in rows]
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:limit]


_store: VectorStore | None = None


def get_store() -> VectorStore:
    global _store
    if _store is None:
        _store = DatabaseVectorStore()
    return _store
