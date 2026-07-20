"""Telegram bot operations CLI.

Two delivery modes, because they suit different environments:

* **Webhook** - production. Telegram POSTs to `/api/webhook/telegram`, which is
  authenticated by a shared secret and needs a public HTTPS URL.
* **Polling** - local development. No public URL required, so a laptop can
  drive the same handlers. Never run both at once: registering a webhook makes
  `getUpdates` fail with 409, and polling while a webhook is live silently
  competes for the same updates.

Usage:
    python -m app.telegram_bot info
    python -m app.telegram_bot set-webhook https://api.example.com
    python -m app.telegram_bot delete-webhook
    python -m app.telegram_bot register-commands
    python -m app.telegram_bot poll
"""

import argparse
import asyncio
import logging
import sys

import httpx

from app.core.config import get_settings
from app.db import SessionLocal
from app.models import DEFAULT_WORKSPACE_ID
from app.services import telegram as telegram_service

logger = logging.getLogger(__name__)

WEBHOOK_PATH = "/api/webhook/telegram"


def _require_token() -> str:
    token = get_settings().telegram_bot_token
    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN is not set - nothing to do.", file=sys.stderr)
        raise SystemExit(2)
    return token


async def cmd_info() -> int:
    _require_token()
    me = await telegram_service._api("getMe", {})
    hook = await telegram_service._api("getWebhookInfo", {})
    if not me or not hook:
        print("ERROR: Could not reach the Bot API. Check the token and network.", file=sys.stderr)
        return 1

    bot = me["result"]
    info = hook["result"]
    print(f"Bot        : @{bot.get('username')} (id {bot.get('id')})")
    print(f"Webhook    : {info.get('url') or '(none - use polling or set-webhook)'}")
    print(f"Pending    : {info.get('pending_update_count', 0)} update(s) queued")
    if info.get("last_error_message"):
        print(f"Last error : {info['last_error_message']}")

    db = SessionLocal()
    try:
        allowed = telegram_service.authorized_chat_ids(db, DEFAULT_WORKSPACE_ID)
    finally:
        db.close()
    print(f"Authorized : {', '.join(sorted(allowed)) if allowed else '(none - bot will ignore everyone)'}")

    # The classic misconfiguration: the bot's own id used as the chat id.
    # Telegram rejects bot-to-self sends, so every notification fails.
    if str(bot.get("id")) in allowed:
        print(
            "\nERROR: TELEGRAM_CHAT_ID is the bot's OWN id. Telegram refuses bot-to-self\n"
            "  sends ('the bot can't send messages to the bot'), so no notification\n"
            "  will ever arrive. Set it to the manager or group chat id instead -\n"
            "  message the bot, then run this command again to see the id.",
            file=sys.stderr,
        )
        return 1
    return 0


async def cmd_set_webhook(base_url: str) -> int:
    _require_token()
    settings = get_settings()
    if not settings.telegram_webhook_secret:
        print(
            "ERROR: TELEGRAM_WEBHOOK_SECRET is empty. The endpoint fails closed and would\n"
            "  reject every update. Generate one:\n"
            '    python -c "import secrets; print(secrets.token_hex(32))"',
            file=sys.stderr,
        )
        return 2

    url = base_url.rstrip("/") + WEBHOOK_PATH
    if not url.startswith("https://"):
        print(f"ERROR: Telegram requires HTTPS for webhooks, got: {url}", file=sys.stderr)
        return 2

    result = await telegram_service._api(
        "setWebhook",
        {
            "url": url,
            "secret_token": settings.telegram_webhook_secret,
            # Without this the CRM action buttons silently do nothing.
            "allowed_updates": ["message", "callback_query"],
            "drop_pending_updates": True,
        },
    )
    if not result:
        print("ERROR: setWebhook failed - see the logged Telegram description above.", file=sys.stderr)
        return 1
    print(f"OK: Webhook registered: {url}")
    await telegram_service.register_commands()
    print("OK: Command menu published")
    return 0


async def cmd_delete_webhook() -> int:
    _require_token()
    result = await telegram_service._api("deleteWebhook", {"drop_pending_updates": False})
    if not result:
        return 1
    print("OK: Webhook removed - polling can now be used.")
    return 0


async def cmd_register_commands() -> int:
    _require_token()
    if not await telegram_service.register_commands():
        return 1
    print(
        "OK: Command menu published: " + ", ".join("/" + c["command"] for c in telegram_service.BOT_COMMANDS)
    )
    return 0


async def cmd_poll() -> int:
    """Long-poll getUpdates and route through the same handlers as the webhook.

    Development convenience only - single-process, no retry/backoff of its own.
    """
    token = _require_token()
    hook = await telegram_service._api("getWebhookInfo", {})
    if hook and hook["result"].get("url"):
        print(
            f"ERROR: A webhook is registered ({hook['result']['url']}). Telegram will not\n"
            "  serve getUpdates while it is active. Run `delete-webhook` first.",
            file=sys.stderr,
        )
        return 2

    await telegram_service.register_commands()
    print("Polling for updates - Ctrl+C to stop.")

    offset = 0
    url = f"{telegram_service.API_BASE}/bot{token}/getUpdates"
    async with httpx.AsyncClient(timeout=40) as client:
        while True:
            try:
                resp = await client.post(
                    url,
                    json={
                        "offset": offset,
                        "timeout": 30,
                        "allowed_updates": ["message", "callback_query"],
                    },
                )
                body = resp.json()
                if not body.get("ok"):
                    logger.error("getUpdates failed: %s", body.get("description"))
                    await asyncio.sleep(5)
                    continue
            except (httpx.HTTPError, ValueError) as exc:
                # Transient network trouble must not kill a long-running poller.
                logger.error("getUpdates transport error: %s", exc)
                await asyncio.sleep(5)
                continue

            for update in body.get("result", []):
                # Advance the offset even when handling raises, otherwise one
                # poisoned update is redelivered forever and blocks the queue.
                offset = update["update_id"] + 1
                db = SessionLocal()
                try:
                    await telegram_service.handle_update(db, update, DEFAULT_WORKSPACE_ID)
                except Exception:
                    logger.exception("Failed to handle update %s", update.get("update_id"))
                finally:
                    db.close()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    # httpx logs the request URL at INFO - and the Bot API puts the token in
    # the path, so this would print the token to the console on every call.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(description="Telegram bot operations")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("info", help="Show bot, webhook and authorization status")
    hook = sub.add_parser("set-webhook", help="Register the production webhook")
    hook.add_argument("base_url", help="Public HTTPS base URL, e.g. https://api.example.com")
    sub.add_parser("delete-webhook", help="Remove the webhook (required before polling)")
    sub.add_parser("register-commands", help="Publish the /command menu")
    sub.add_parser("poll", help="Long-poll for updates (local development)")
    args = parser.parse_args()

    if args.command == "info":
        return asyncio.run(cmd_info())
    if args.command == "set-webhook":
        return asyncio.run(cmd_set_webhook(args.base_url))
    if args.command == "delete-webhook":
        return asyncio.run(cmd_delete_webhook())
    if args.command == "register-commands":
        return asyncio.run(cmd_register_commands())
    if args.command == "poll":
        try:
            return asyncio.run(cmd_poll())
        except KeyboardInterrupt:
            print("\nStopped.")
            return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
