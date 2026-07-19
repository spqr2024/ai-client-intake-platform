"""Embedding provider abstraction for semantic retrieval.

No provider is hardcoded anywhere else in the codebase: consumers call
`get_provider()` and receive whichever implementation matches configuration.
Adding a provider = subclass EmbeddingProvider + one registry entry.

The `mock` provider is a deterministic feature-hashing embedder (character
n-grams → fixed-size normalized vector). It has no external dependencies,
which keeps semantic search functional (lexically approximated) offline and
in tests; real deployments configure openai/gemini/openrouter.
"""

import hashlib
import logging
import math
import re
from abc import ABC, abstractmethod

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

DEFAULT_MODELS = {
    "openai": "text-embedding-3-small",
    "gemini": "gemini-embedding-001",  # text-embedding-004 is retired (404s)
    "openrouter": "openai/text-embedding-3-small",
}


class EmbeddingError(Exception):
    pass


class EmbeddingProvider(ABC):
    name: str = ""
    model: str = ""

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text."""


class HashingEmbeddings(EmbeddingProvider):
    """Offline deterministic embedder: hashed character-trigram + word
    features, L2-normalized. Not semantic, but shape-compatible — the whole
    retrieval pipeline (index, cosine search, thresholds) behaves identically
    to a real provider."""

    name = "mock"
    model = "hashing-256"
    dimensions = 256

    _word_re = re.compile(r"[\w']+", re.UNICODE)

    def _features(self, text: str) -> list[str]:
        words = [w.lower() for w in self._word_re.findall(text)]
        features = list(words)
        for word in words:
            padded = f"^{word}$"
            features += [padded[i : i + 3] for i in range(len(padded) - 2)]
        return features

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            vec = [0.0] * self.dimensions
            for feature in self._features(text):
                digest = hashlib.md5(feature.encode()).digest()
                index = int.from_bytes(digest[:4], "little") % self.dimensions
                sign = 1.0 if digest[4] % 2 else -1.0
                vec[index] += sign
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            vectors.append([v / norm for v in vec])
        return vectors


class OpenAICompatibleEmbeddings(EmbeddingProvider):
    """OpenAI-style /embeddings endpoint. Also serves OpenRouter."""

    def __init__(self, name: str, api_key: str, model: str, base_url: str):
        self.name = name
        self.model = model
        self._api_key = api_key
        self._base_url = base_url

    async def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self._base_url}/embeddings",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={"model": self.model, "input": texts},
                )
                resp.raise_for_status()
                data = sorted(resp.json()["data"], key=lambda d: d["index"])
                return [d["embedding"] for d in data]
        except (httpx.HTTPError, KeyError) as exc:
            raise EmbeddingError(f"{self.name}: {exc}") from exc


class GeminiEmbeddings(EmbeddingProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str):
        self.model = model
        self._api_key = api_key

    async def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://generativelanguage.googleapis.com/v1beta/"
                    f"models/{self.model}:batchEmbedContents",
                    params={"key": self._api_key},
                    json={
                        "requests": [
                            {"model": f"models/{self.model}", "content": {"parts": [{"text": t}]}}
                            for t in texts
                        ]
                    },
                )
                resp.raise_for_status()
                return [e["values"] for e in resp.json()["embeddings"]]
        except (httpx.HTTPError, KeyError) as exc:
            raise EmbeddingError(f"gemini: {exc}") from exc


def get_provider() -> EmbeddingProvider:
    """Resolve the configured embedding provider, falling back to the offline
    hashing embedder when unconfigured or missing credentials."""
    settings = get_settings()
    name = (settings.embedding_provider or "mock").lower()
    model = settings.embedding_model or DEFAULT_MODELS.get(name, "")

    if name == "openai" and settings.openai_api_key:
        return OpenAICompatibleEmbeddings(
            "openai", settings.openai_api_key, model, "https://api.openai.com/v1"
        )
    if name == "openrouter" and settings.openrouter_api_key:
        return OpenAICompatibleEmbeddings(
            "openrouter", settings.openrouter_api_key, model, "https://openrouter.ai/api/v1"
        )
    if name == "gemini" and settings.gemini_api_key:
        return GeminiEmbeddings(settings.gemini_api_key, model)
    if name not in ("mock", ""):
        logger.warning("Embedding provider %s not usable (missing key?); using hashing fallback", name)
    return HashingEmbeddings()
