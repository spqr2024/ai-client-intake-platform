"""CRM integration layer.

A `CRMProvider` maps a Lead onto an external system. Providers are registered
in a registry keyed by name — adding Zoho or Airtable means writing one class
and one `register_provider` call; no existing code changes and no provider is
referenced anywhere else in the codebase.

Configuration is per workspace (`crm_provider`, `crm_api_key`, plus provider
options), export runs through the background queue with retry/backoff, and
every attempt is recorded in `CRMSyncLog` with the external id/url on success.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import queue
from app.db import SessionLocal
from app.models import CRMSyncLog, Lead
from app.services import runtime_settings

logger = logging.getLogger(__name__)


class CRMError(Exception):
    """Recoverable export failure — the queue will retry."""


@dataclass
class CRMResult:
    external_id: str = ""
    external_url: str = ""


@dataclass
class CRMConfig:
    provider: str = ""
    api_key: str = ""
    options: dict | None = None

    def option(self, key: str, default: str = "") -> str:
        return str((self.options or {}).get(key, default))


class CRMProvider(ABC):
    """Contract for exporting a qualified lead to an external CRM."""

    name: str = ""
    label: str = ""
    #: Extra per-workspace settings this provider needs (rendered in the UI).
    option_keys: tuple[str, ...] = ()

    @abstractmethod
    async def export_lead(self, lead: Lead, config: CRMConfig) -> CRMResult: ...

    @staticmethod
    def lead_payload(lead: Lead) -> dict:
        """Normalized, provider-independent view of a lead."""
        first, _, last = (lead.client_name or "").partition(" ")
        return {
            "id": lead.id,
            "project_name": lead.project_name,
            "first_name": first or lead.client_name,
            "last_name": last,
            "full_name": lead.client_name,
            "email": lead.client_email,
            "phone": lead.client_phone,
            "service": lead.service,
            "budget": lead.budget,
            "timeline": lead.timeline,
            "status": lead.status,
            "priority": lead.priority,
            "score": lead.score,
            "tags": list(lead.tags or []),
            "summary": lead.summary,
            "created_at": lead.created_at.isoformat() if lead.created_at else "",
        }


PROVIDERS: dict[str, CRMProvider] = {}


def register_provider(provider: CRMProvider) -> None:
    PROVIDERS[provider.name] = provider


def available_providers() -> list[dict]:
    return [
        {"name": p.name, "label": p.label, "option_keys": list(p.option_keys)}
        for p in sorted(PROVIDERS.values(), key=lambda p: p.label)
    ]


async def _post_json(url: str, payload: dict, headers: dict, provider: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json() if response.content else {}
    except httpx.HTTPStatusError as exc:
        raise CRMError(
            f"{provider}: HTTP {exc.response.status_code} — {exc.response.text[:200]}"
        ) from exc
    except httpx.HTTPError as exc:
        raise CRMError(f"{provider}: {exc}") from exc


# ── Adapters ─────────────────────────────────────────────────────────────
class HubSpotProvider(CRMProvider):
    name = "hubspot"
    label = "HubSpot"

    async def export_lead(self, lead: Lead, config: CRMConfig) -> CRMResult:
        data = self.lead_payload(lead)
        body = {
            "properties": {
                "email": data["email"],
                "firstname": data["first_name"],
                "lastname": data["last_name"],
                "phone": data["phone"],
                "company": data["project_name"],
                "hs_lead_status": data["status"].upper().replace(" ", "_"),
                "lifecyclestage": "lead",
                "message": data["summary"][:4000],
            }
        }
        result = await _post_json(
            "https://api.hubapi.com/crm/v3/objects/contacts",
            body, {"Authorization": f"Bearer {config.api_key}"}, self.label,
        )
        contact_id = str(result.get("id", ""))
        return CRMResult(
            external_id=contact_id,
            external_url=f"https://app.hubspot.com/contacts/objects/0-1/{contact_id}"
            if contact_id else "",
        )


class PipedriveProvider(CRMProvider):
    name = "pipedrive"
    label = "Pipedrive"
    option_keys = ("company_domain",)

    async def export_lead(self, lead: Lead, config: CRMConfig) -> CRMResult:
        data = self.lead_payload(lead)
        domain = config.option("company_domain", "api")
        base = f"https://{domain}.pipedrive.com/api/v1"
        person = await _post_json(
            f"{base}/persons?api_token={config.api_key}",
            {
                "name": data["full_name"] or f"Lead #{data['id']}",
                "email": [data["email"]] if data["email"] else [],
                "phone": [data["phone"]] if data["phone"] else [],
            },
            {}, self.label,
        )
        person_id = (person.get("data") or {}).get("id")
        deal = await _post_json(
            f"{base}/deals?api_token={config.api_key}",
            {
                "title": data["project_name"] or f"Lead #{data['id']}",
                "value": data["budget"] or 0,
                "currency": "USD",
                "person_id": person_id,
            },
            {}, self.label,
        )
        deal_id = str((deal.get("data") or {}).get("id", ""))
        return CRMResult(
            external_id=deal_id,
            external_url=f"https://{domain}.pipedrive.com/deal/{deal_id}" if deal_id else "",
        )


class NotionProvider(CRMProvider):
    name = "notion"
    label = "Notion"
    option_keys = ("database_id",)

    async def export_lead(self, lead: Lead, config: CRMConfig) -> CRMResult:
        data = self.lead_payload(lead)
        database_id = config.option("database_id")
        if not database_id:
            raise CRMError("Notion: 'database_id' option is required")
        properties = {
            "Name": {"title": [{"text": {"content": data["project_name"] or f"Lead #{data['id']}"}}]},
            "Status": {"select": {"name": data["status"]}},
            "Score": {"number": data["score"]},
        }
        if data["email"]:
            properties["Email"] = {"email": data["email"]}
        if data["budget"]:
            properties["Budget"] = {"number": data["budget"]}
        result = await _post_json(
            "https://api.notion.com/v1/pages",
            {
                "parent": {"database_id": database_id},
                "properties": properties,
                "children": [
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"type": "text", "text": {"content": data["summary"][:1900]}}]
                        },
                    }
                ],
            },
            {"Authorization": f"Bearer {config.api_key}", "Notion-Version": "2022-06-28"},
            self.label,
        )
        page_id = str(result.get("id", ""))
        return CRMResult(external_id=page_id, external_url=result.get("url", ""))


class SalesforceProvider(CRMProvider):
    name = "salesforce"
    label = "Salesforce"
    option_keys = ("instance_url",)

    async def export_lead(self, lead: Lead, config: CRMConfig) -> CRMResult:
        data = self.lead_payload(lead)
        instance = config.option("instance_url").rstrip("/")
        if not instance:
            raise CRMError("Salesforce: 'instance_url' option is required")
        result = await _post_json(
            f"{instance}/services/data/v60.0/sobjects/Lead",
            {
                "FirstName": data["first_name"] or "Unknown",
                "LastName": data["last_name"] or data["first_name"] or "Lead",
                "Company": data["project_name"] or "Website inquiry",
                "Email": data["email"],
                "Phone": data["phone"],
                "Status": "Open - Not Contacted",
                "Description": data["summary"][:32000],
            },
            {"Authorization": f"Bearer {config.api_key}"},
            self.label,
        )
        record_id = str(result.get("id", ""))
        return CRMResult(
            external_id=record_id,
            external_url=f"{instance}/lightning/r/Lead/{record_id}/view" if record_id else "",
        )


class WebhookProvider(CRMProvider):
    """Generic escape hatch: POSTs the normalized payload anywhere
    (Zapier, Make, n8n, an in-house endpoint)."""

    name = "webhook"
    label = "Generic webhook"
    option_keys = ("url",)

    async def export_lead(self, lead: Lead, config: CRMConfig) -> CRMResult:
        url = config.option("url")
        if not url:
            raise CRMError("Webhook: 'url' option is required")
        headers = {"Authorization": f"Bearer {config.api_key}"} if config.api_key else {}
        await _post_json(url, {"event": "lead.created", "lead": self.lead_payload(lead)},
                         headers, self.label)
        return CRMResult(external_id=str(lead.id))


for _provider in (HubSpotProvider(), PipedriveProvider(), NotionProvider(),
                  SalesforceProvider(), WebhookProvider()):
    register_provider(_provider)


# ── Orchestration ────────────────────────────────────────────────────────
def get_config(db: Session, workspace_id: int) -> CRMConfig:
    options = {}
    for provider in PROVIDERS.values():
        for key in provider.option_keys:
            value = runtime_settings.get(db, f"crm_option_{key}", workspace_id)
            if value:
                options[key] = value
    return CRMConfig(
        provider=runtime_settings.get(db, "crm_provider", workspace_id),
        api_key=runtime_settings.get(db, "crm_api_key", workspace_id),
        options=options,
    )


async def export_lead(db: Session, lead: Lead) -> CRMSyncLog | None:
    """Queue a lead export if a provider is configured for the workspace."""
    config = get_config(db, lead.workspace_id)
    if not config.provider or config.provider not in PROVIDERS:
        return None
    entry = CRMSyncLog(workspace_id=lead.workspace_id, lead_id=lead.id, provider=config.provider)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    await queue.enqueue("crm.export", {"sync_id": entry.id})
    return entry


async def _handle_export(payload: dict) -> None:
    db = SessionLocal()
    try:
        entry = db.get(CRMSyncLog, int(payload.get("sync_id", 0)))
        if entry is None or entry.status == "synced":
            return
        lead = db.get(Lead, entry.lead_id)
        provider = PROVIDERS.get(entry.provider)
        if lead is None or provider is None:
            entry.status = "skipped"
            entry.error = "Lead or provider unavailable"
            db.commit()
            return

        config = get_config(db, entry.workspace_id)
        entry.attempts += 1
        try:
            result = await provider.export_lead(lead, config)
            entry.status = "synced"
            entry.external_id = result.external_id[:120]
            entry.external_url = result.external_url[:500]
            entry.error = ""
            db.commit()
            logger.info("Exported lead to CRM",
                        extra={"lead_id": lead.id, "provider": entry.provider})
        except CRMError as exc:
            entry.error = str(exc)[:1000]
            if entry.attempts >= queue.MAX_ATTEMPTS:
                entry.status = "failed"
            db.commit()
            raise
    finally:
        db.close()


queue.register_handler("crm.export", _handle_export)


def recent_syncs(db: Session, workspace_id: int, limit: int = 50) -> list[CRMSyncLog]:
    return list(
        db.scalars(
            select(CRMSyncLog)
            .where(CRMSyncLog.workspace_id == workspace_id)
            .order_by(CRMSyncLog.created_at.desc(), CRMSyncLog.id.desc())
            .limit(limit)
        ).all()
    )
