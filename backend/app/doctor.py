"""Integration preflight: `python -m app.doctor`.

Answers one question — "is what's in .env actually going to work in
production?" — without booting the app or touching the database. Every check
is read-only against the live provider unless `--send-test` is passed.

Exit code is 0 when nothing FAILed (SKIP and WARN are not failures), so this
doubles as a deploy gate:  python -m app.doctor || exit 1
"""

import argparse
import asyncio
import smtplib
import sys

import httpx

from app.core.config import get_settings
from app.services import embeddings, llm

OK, WARN, FAIL, SKIP = "OK", "WARN", "FAIL", "SKIP"


def _icons() -> dict[str, str]:
    """Legacy Windows consoles are cp1251/cp866 and raise on box-drawing
    glyphs, so fall back to ASCII when stdout cannot encode them."""
    fancy = {OK: "✓", WARN: "!", FAIL: "✗", SKIP: "-"}
    try:
        "".join(fancy.values()).encode(sys.stdout.encoding or "ascii")
    except (UnicodeEncodeError, LookupError):
        return {OK: "+", WARN: "!", FAIL: "x", SKIP: "-"}
    return fancy


ICONS = _icons()


def say(line: str = "") -> None:
    """print() that degrades instead of raising on a narrow console codepage."""
    encoding = sys.stdout.encoding or "utf-8"
    try:
        line.encode(encoding)
    except (UnicodeEncodeError, LookupError):
        line = line.translate(str.maketrans({"—": "-", "–": "-", "→": "->", "’": "'", "…": "..."}))
        line = line.encode(encoding, "replace").decode(encoding)
    print(line)


Result = tuple[str, str, str]  # (status, name, detail)


def _report(results: list[Result]) -> int:
    width = max(len(name) for _, name, _ in results)
    say()
    for status, name, detail in results:
        say(f"  {ICONS[status]} {status:<4} {name:<{width}}  {detail}")
    failed = sum(1 for status, _, _ in results if status == FAIL)
    warned = sum(1 for status, _, _ in results if status == WARN)
    say(f"\n  {len(results)} checks — {failed} failed, {warned} warnings\n")
    return 1 if failed else 0


# ── Checks ────────────────────────────────────────────────────────────────
def check_secrets() -> list[Result]:
    s = get_settings()
    out: list[Result] = []
    if s.jwt_secret == "change-me-in-production":
        out.append((FAIL, "JWT_SECRET", "still the placeholder — tokens are forgeable"))
    elif len(s.jwt_secret) < 32:
        out.append((WARN, "JWT_SECRET", f"only {len(s.jwt_secret)} chars; use 32+ random bytes"))
    else:
        out.append((OK, "JWT_SECRET", f"{len(s.jwt_secret)} chars"))

    if s.admin_password == "admin12345":
        out.append((WARN, "ADMIN_PASSWORD", "default demo password — change before exposing the app"))
    else:
        out.append((OK, "ADMIN_PASSWORD", "customised"))
    return out


async def check_llm() -> Result:
    s = get_settings()
    cfg = llm.resolve_config()
    if cfg.provider == "mock":
        detail = "provider=mock (deterministic engine, no API key needed)"
        if s.ai_provider not in ("", "mock"):
            return (WARN, "AI provider", f"{s.ai_provider} selected but no API key — fell back to mock")
        return (SKIP, "AI provider", detail)
    try:
        reply = await llm.complete([{"role": "user", "content": "Reply with exactly: OK"}], cfg, system="")
        return (OK, "AI provider", f"{cfg.provider}/{cfg.model} replied {reply[:20]!r}")
    except Exception as exc:  # surface any transport/auth error
        return (FAIL, "AI provider", f"{cfg.provider}/{cfg.model}: {str(exc)[:120]}")


async def check_embeddings() -> Result:
    provider = embeddings.get_provider()
    if provider.name == "mock":
        return (SKIP, "Embeddings", "offline hashing embedder (no key needed)")
    try:
        vectors = await provider.embed(["preflight"])
        return (OK, "Embeddings", f"{provider.name}/{provider.model} → dim {len(vectors[0])}")
    except Exception as exc:
        return (FAIL, "Embeddings", f"{provider.name}: {str(exc)[:120]}")


async def check_telegram(send_test: bool) -> list[Result]:
    s = get_settings()
    if not s.telegram_bot_token:
        return [(SKIP, "Telegram", "TELEGRAM_BOT_TOKEN empty — notifications disabled")]
    base = f"https://api.telegram.org/bot{s.telegram_bot_token}"
    out: list[Result] = []
    async with httpx.AsyncClient(timeout=20) as client:
        try:
            me = (await client.get(f"{base}/getMe")).json()
        except httpx.HTTPError as exc:
            return [(FAIL, "Telegram", f"getMe: {exc}")]
        if not me.get("ok"):
            return [(FAIL, "Telegram", f"getMe rejected the token: {me.get('description')}")]
        out.append((OK, "Telegram bot", f"@{me['result'].get('username')}"))

        bot_id = str(me["result"].get("id", ""))
        if s.telegram_chat_id == bot_id:
            # Easy mistake: the bot's own id is the prefix of the bot token, so
            # it looks like the obvious value. Telegram refuses self-sends.
            out.append(
                (
                    FAIL,
                    "Telegram chat",
                    f"TELEGRAM_CHAT_ID is the bot's own id ({bot_id}) — it must be the "
                    "recipient's chat id; message the bot and re-run to discover it",
                )
            )
            return out

        if s.telegram_chat_id:
            out.append((OK, "Telegram chat", f"TELEGRAM_CHAT_ID={s.telegram_chat_id}"))
            if send_test:
                sent = (
                    await client.post(
                        f"{base}/sendMessage",
                        json={"chat_id": s.telegram_chat_id, "text": "Preflight check from app.doctor"},
                    )
                ).json()
                status = OK if sent.get("ok") else FAIL
                out.append((status, "Telegram send", sent.get("description", "test message delivered")))
        else:
            # Not configured yet — surface any chat that has messaged the bot
            # so the operator can copy the id straight into .env.
            updates = (await client.get(f"{base}/getUpdates")).json().get("result", [])
            chats = {
                str(u[k]["chat"]["id"]): u[k]["chat"].get("title") or u[k]["chat"].get("first_name", "")
                for u in updates
                for k in ("message", "channel_post")
                if k in u
            }
            if chats:
                found = ", ".join(f"{cid} ({name})" for cid, name in chats.items())
                out.append((WARN, "Telegram chat", f"TELEGRAM_CHAT_ID unset — available: {found}"))
            else:
                out.append(
                    (WARN, "Telegram chat", "TELEGRAM_CHAT_ID unset — send /start to the bot, then re-run")
                )
    return out


def check_smtp(send_test: bool) -> list[Result]:
    s = get_settings()
    if not s.smtp_host:
        return [(SKIP, "Email/SMTP", "SMTP_HOST empty — emails are logged to console")]
    try:
        server = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=25)
        if s.smtp_tls:
            server.starttls()
        if s.smtp_user:
            server.login(s.smtp_user, s.smtp_password)
        out = [(OK, "Email/SMTP", f"authenticated as {s.smtp_user or 'anonymous'} on {s.smtp_host}")]
        if send_test:
            from email.message import EmailMessage

            msg = EmailMessage()
            msg["From"], msg["To"] = s.smtp_from, s.smtp_user or s.smtp_from
            msg["Subject"] = "Preflight check from app.doctor"
            msg.set_content("SMTP delivery works.")
            server.send_message(msg)
            out.append((OK, "Email send", f"test message sent to {msg['To']}"))
        server.quit()
        return out
    except Exception as exc:
        return [(FAIL, "Email/SMTP", f"{s.smtp_host}: {str(exc)[:120]}")]


async def check_crm() -> Result:
    """Token-validity probe only — never writes a contact into the CRM."""
    s = get_settings()
    if not s.crm_provider or not s.crm_api_key:
        return (SKIP, "CRM export", "CRM_PROVIDER/CRM_API_KEY unset (configurable in the admin UI)")
    probes = {
        "hubspot": ("https://api.hubapi.com/crm/v3/objects/contacts?limit=1", "bearer"),
        "notion": ("https://api.notion.com/v1/users/me", "bearer"),
    }
    if s.crm_provider not in probes:
        return (SKIP, "CRM export", f"{s.crm_provider}: no read-only probe available")
    url, _ = probes[s.crm_provider]
    headers = {"Authorization": f"Bearer {s.crm_api_key}"}
    if s.crm_provider == "notion":
        headers["Notion-Version"] = "2022-06-28"
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            resp = await client.get(url, headers=headers)
        if resp.status_code == 200:
            return (OK, "CRM export", f"{s.crm_provider} token accepted")
        return (FAIL, "CRM export", f"{s.crm_provider}: HTTP {resp.status_code} {resp.text[:80]}")
    except httpx.HTTPError as exc:
        return (FAIL, "CRM export", f"{s.crm_provider}: {exc}")


async def run(send_test: bool) -> int:
    say("\nIntegration preflight — checking .env against live providers")
    results: list[Result] = list(check_secrets())
    results.append(await check_llm())
    results.append(await check_embeddings())
    results.extend(await check_telegram(send_test))
    results.extend(check_smtp(send_test))
    results.append(await check_crm())
    return _report(results)


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify configured integrations.")
    parser.add_argument(
        "--send-test",
        action="store_true",
        help="also deliver a real test Telegram message and email (costs a send)",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(run(args.send_test)))


if __name__ == "__main__":
    main()
