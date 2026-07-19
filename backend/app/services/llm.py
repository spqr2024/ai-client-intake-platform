"""Multi-provider LLM abstraction.

Providers: mock (offline, deterministic), openai, anthropic, gemini, openrouter.
The active provider/model is resolved from runtime AppSettings with .env
fallback, so admins can switch providers without a redeploy.
"""

import logging
from dataclasses import dataclass

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Verified reachable 2026-07-19. Gemini pins the rolling "-latest" alias
# because dated Gemini snapshots get closed to new API keys; the OpenRouter
# default is a currently-listed free-tier model (its catalogue rotates, so
# re-check with GET /api/v1/models if completions start 404-ing).
DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-5",
    "gemini": "gemini-flash-latest",
    "openrouter": "openai/gpt-oss-20b:free",
}


class LLMError(Exception):
    pass


@dataclass
class LLMConfig:
    provider: str = "mock"
    model: str = ""
    api_key: str = ""
    temperature: float = 0.4
    max_tokens: int = 1024


def resolve_config(overrides: dict[str, str] | None = None) -> LLMConfig:
    """Build the effective LLM config from env settings + runtime overrides."""
    s = get_settings()
    o = overrides or {}
    provider = (o.get("ai_provider") or s.ai_provider or "mock").lower()
    model = o.get("ai_model") or s.ai_model or DEFAULT_MODELS.get(provider, "")
    key_map = {
        "openai": s.openai_api_key,
        "anthropic": s.anthropic_api_key,
        "gemini": s.gemini_api_key,
        "openrouter": s.openrouter_api_key,
    }
    api_key = o.get("ai_api_key") or key_map.get(provider, "")
    try:
        temperature = float(o.get("ai_temperature") or s.ai_temperature)
    except ValueError:
        temperature = s.ai_temperature
    try:
        max_tokens = int(o.get("ai_max_tokens") or s.ai_max_tokens)
    except ValueError:
        max_tokens = s.ai_max_tokens
    if provider != "mock" and not api_key:
        logger.warning("Provider %s selected but no API key set; falling back to mock", provider)
        provider = "mock"
    return LLMConfig(provider, model, api_key, temperature, max_tokens)


async def complete(
    messages: list[dict[str, str]],
    config: LLMConfig | None = None,
    system: str = "",
) -> str:
    """Run a chat completion. `messages` is a list of {role, content}."""
    cfg = config or resolve_config()
    if cfg.provider == "mock":
        return ""
    try:
        if cfg.provider in ("openai", "openrouter"):
            return await _openai_compatible(messages, cfg, system)
        if cfg.provider == "anthropic":
            return await _anthropic(messages, cfg, system)
        if cfg.provider == "gemini":
            return await _gemini(messages, cfg, system)
    except (httpx.HTTPError, KeyError, IndexError) as exc:
        logger.error("LLM call failed (%s): %s", cfg.provider, exc)
        raise LLMError(str(exc)) from exc
    raise LLMError(f"Unknown provider: {cfg.provider}")


async def _openai_compatible(messages: list[dict], cfg: LLMConfig, system: str) -> str:
    base = "https://openrouter.ai/api/v1" if cfg.provider == "openrouter" else "https://api.openai.com/v1"
    payload_messages = ([{"role": "system", "content": system}] if system else []) + messages
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {cfg.api_key}"},
            json={
                "model": cfg.model,
                "messages": payload_messages,
                "temperature": cfg.temperature,
                "max_tokens": cfg.max_tokens,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()


async def _anthropic(messages: list[dict], cfg: LLMConfig, system: str) -> str:
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": cfg.api_key, "anthropic-version": "2023-06-01"},
            json={
                "model": cfg.model,
                "system": system or None,
                "messages": messages,
                "temperature": cfg.temperature,
                "max_tokens": cfg.max_tokens,
            },
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"].strip()


async def _gemini(messages: list[dict], cfg: LLMConfig, system: str) -> str:
    contents = [
        {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
        for m in messages
    ]
    body: dict = {
        "contents": contents,
        "generationConfig": {"temperature": cfg.temperature, "maxOutputTokens": cfg.max_tokens},
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{cfg.model}:generateContent",
            params={"key": cfg.api_key},
            json=body,
        )
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
