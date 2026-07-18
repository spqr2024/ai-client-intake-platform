"""Demo provisioning: makes a fresh clone look alive immediately.

Runs once at startup when `DEMO_MODE=true` and the workspace has no leads.
Generates a realistic, time-distributed dataset — conversations with full
transcripts and replay metadata, leads across the whole pipeline with tags,
priorities and follow-ups, KB articles, activity history and notifications —
so the dashboard, analytics and kanban all have something meaningful to show.

Idempotent: safe to run on every boot; it no-ops once demo data exists.
"""

import logging
import random
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import (
    DEFAULT_WORKSPACE_ID,
    ActivityLog,
    Conversation,
    KnowledgeBaseArticle,
    Lead,
    Message,
    Notification,
    User,
    Workspace,
    utcnow,
)
from app.services import runtime_settings
from app.services.summary import rule_based_summary

logger = logging.getLogger(__name__)

DEMO_MARKER_TAG = "demo"

DEMO_KB = [
    ("How long does a typical website project take?",
     "A marketing website takes 4-8 weeks end to end: 1 week discovery, 2-3 weeks design, "
     "2-3 weeks development, 1 week QA and content loading. Online stores run 8-12 weeks "
     "depending on catalogue size and integrations."),
    ("What is included in the price?",
     "Every quote includes design, development, basic SEO setup, mobile responsiveness, one "
     "round of revisions and 30 days of post-launch support. Hosting and domain registration "
     "are billed separately at cost."),
    ("Do you offer support after launch?",
     "Yes. Every project includes 30 days of free post-launch support. After that we offer "
     "monthly maintenance retainers covering updates, backups, monitoring and small changes."),
    ("Where are you located and do you work remotely?",
     "Our team is fully remote with a hub in Kyiv, Ukraine. We work with clients worldwide "
     "across all time zones and run meetings over Zoom or Google Meet."),
    ("Payment terms and process",
     "We work in milestones: 40% upfront to book the project, 40% at design approval and 20% "
     "at launch. We accept bank transfer, Wise and Payoneer."),
]

# (project, client, email, service, budget, timeline, status, score, priority,
#  tags, days_ago, goals, language, follow_up_days)
DEMO_LEADS = [
    ("Online store — Alice Johnson", "Alice Johnson", "alice@brightcandle.com", "Online store",
     5000, "1-3 months", "Qualified", 85, "High", ["vip", "ecommerce"], 1,
     "Sell handmade candles across the EU, around 200 products, needs Stripe and TikTok integration",
     "en", 2),
    ("Mobile app — Dan Lee", "Dan Lee", "dan@fitpulse.app", "Mobile app",
     12000, "ASAP", "Converted", 95, "Urgent", ["vip", "mobile"], 12,
     "Fitness tracking app for iOS and Android with wearables sync and subscription billing",
     "en", None),
    ("Branding — Bob Martinez", "Bob Martinez", "bob@northstar.io", "Branding / Design",
     1500, "2 weeks", "In Progress", 62, "Medium", ["startup"], 3,
     "Full brand identity for a B2B SaaS startup: logo, palette, pitch deck template",
     "en", 1),
    ("Вебсайт — Катерина Шевченко", "Катерина Шевченко", "kateryna@salonlux.ua", "Вебсайт",
     2000, "Якнайшвидше", "Qualified", 74, "High", ["ukraine"], 0,
     "Сайт для салону краси з онлайн-записом та інтеграцією з Instagram",
     "uk", 3),
    ("Website redesign — Priya Raman", "Priya Raman", "priya@harborlaw.com", "Website",
     7500, "1-3 months", "In Progress", 80, "High", ["legal"], 5,
     "Redesign of a 40-page law firm site with case-study library and intake forms",
     "en", 4),
    ("Online store — Marco Rossi", "Marco Rossi", "marco@vinoteca.it", "Online store",
     3500, "Within 1 month", "New", 68, "Medium", [], 2,
     "Wine subscription store with age verification and monthly boxes",
     "en", None),
    ("SEO audit — Grace Kim", "Grace Kim", "grace@retailco.com", "Other",
     800, "Flexible", "Rejected", 30, "Low", ["small-budget"], 8,
     "SEO audit for an existing Shopify store",
     "en", None),
    ("Website — (anonymous)", "", "", "Website",
     None, "", "Incomplete", 15, "Low", [], 6,
     "", "en", None),
    ("Mobile app — Tomas Novak", "Tomas Novak", "tomas@logistix.cz", "Mobile app",
     18000, "1-3 months", "Qualified", 92, "Urgent", ["vip", "enterprise"], 4,
     "Driver-facing logistics app with offline mode, route optimisation and ERP integration",
     "en", 1),
    ("Branding — Sofia Almeida", "Sofia Almeida", "sofia@verdecafe.pt", "Branding / Design",
     2200, "Within 1 month", "Converted", 71, "Medium", ["hospitality"], 20,
     "Brand refresh for a coffee chain: packaging, signage and menu design",
     "en", None),
    ("Website — Ahmed Hassan", "Ahmed Hassan", "ahmed@medclinic.ae", "Website",
     6000, "1-3 months", "Closed", 66, "Medium", ["healthcare"], 26,
     "Clinic website with appointment booking and patient portal",
     "en", None),
    ("Online store — Lena Fischer", "Lena Fischer", "lena@bikeworks.de", "Online store",
     9500, "ASAP", "New", 88, "High", ["ecommerce"], 0,
     "Bicycle parts store, 5000 SKUs, needs ERP sync and B2B pricing tiers",
     "en", 1),
]

TRANSCRIPT_TEMPLATE = [
    ("bot", "Hello! I'm your intake assistant — I'll gather a few project details so our team "
            "can help you faster. May I have your name?", "greeting", "name"),
    ("user", "{client_name}", "answer", "name"),
    ("bot", "Nice to meet you! What service are you interested in?", "question", "service"),
    ("user", "{service}", "answer", "service"),
    ("bot", "Could you describe your project goals or needs in a sentence or two?",
     "question", "goals"),
    ("user", "{goals}", "answer", "goals"),
    ("bot", "What's your approximate budget for this project (in USD)?", "question", "budget"),
    ("user", "{budget_text}", "answer", "budget"),
    ("bot", "When would you like the project completed by?", "question", "timeline"),
    ("user", "{timeline}", "answer", "timeline"),
    ("bot", "Almost done! What email should we use to send you the summary and follow up?",
     "question", "email"),
    ("user", "{client_email}", "answer", "email"),
]


def _already_provisioned(db: Session, workspace_id: int) -> bool:
    return bool(
        db.scalar(select(func.count(Lead.id)).where(Lead.workspace_id == workspace_id))
    )


def provision_demo_workspace(db: Session, workspace_id: int = DEFAULT_WORKSPACE_ID) -> bool:
    """Populate the workspace with demo data. Returns True if it did work."""
    workspace = db.get(Workspace, workspace_id)
    if workspace is None or _already_provisioned(db, workspace_id):
        return False

    logger.info("DEMO_MODE: provisioning demo workspace")
    random.seed(20260718)  # stable output across restarts

    _ensure_users(db, workspace_id)
    _ensure_branding(db, workspace_id)
    _ensure_kb(db, workspace_id)
    manager = db.scalars(
        select(User).where(User.workspace_id == workspace_id, User.role == "manager")
    ).first()

    for entry in DEMO_LEADS:
        _create_demo_lead(db, workspace_id, entry, manager)

    _ensure_abandoned_conversations(db, workspace_id)
    db.commit()
    logger.info("DEMO_MODE: demo workspace ready", extra={"leads": len(DEMO_LEADS)})
    return True


def _ensure_users(db: Session, workspace_id: int) -> None:
    seed_users = [
        ("John Carter", "manager@example.com", "manager123", "manager"),
        ("Maria Lopez", "maria@example.com", "manager123", "manager"),
    ]
    for name, email, password, role in seed_users:
        if db.scalars(select(User).where(User.email == email)).first() is None:
            db.add(User(workspace_id=workspace_id, name=name, email=email,
                        password_hash=hash_password(password), role=role))
    db.commit()


def _ensure_branding(db: Session, workspace_id: int) -> None:
    runtime_settings.set_many(
        db,
        {
            "brand_company_name": "Northwind Studio",
            "brand_bot_name": "Nora — Intake Assistant",
            "brand_primary_color": "#4f46e5",
            "landing_hero_title": "Turn website visitors into qualified projects — automatically",
            "landing_hero_subtitle": (
                "Nora interviews every prospect 24/7, captures budget, timeline and scope, "
                "scores the lead and hands our team a ready-to-act brief."
            ),
            "staff_notification_email": "sales@example.com",
        },
        workspace_id,
    )


def _ensure_kb(db: Session, workspace_id: int) -> None:
    existing = db.scalar(
        select(func.count(KnowledgeBaseArticle.id)).where(
            KnowledgeBaseArticle.workspace_id == workspace_id
        )
    )
    if existing:
        return
    for title, content in DEMO_KB:
        db.add(
            KnowledgeBaseArticle(
                workspace_id=workspace_id, title=title, content=content,
                source_type="manual", index_status="pending",
                doc_metadata={"characters": len(content), "seeded": True},
            )
        )
    db.commit()


def _create_demo_lead(db: Session, workspace_id: int, entry: tuple, manager: User | None) -> None:
    (project, client, email, service, budget, timeline, status, score, priority,
     tags, days_ago, goals, language, follow_up_days) = entry

    created = utcnow() - timedelta(days=days_ago, hours=random.randint(1, 10),
                                   minutes=random.randint(0, 59))
    answers = {
        "client_name": client, "client_email": email, "service": service,
        "budget": budget, "timeline": timeline, "goals": goals,
    }
    lead = Lead(
        workspace_id=workspace_id,
        project_name=project,
        client_name=client,
        client_email=email,
        service=service,
        budget=budget,
        timeline=timeline,
        summary=rule_based_summary(answers, language),
        status=status,
        priority=priority,
        tags=[*tags, DEMO_MARKER_TAG],
        score=score,
        language=language,
        created_at=created,
        updated_at=created,
        assigned_to_id=manager.id if manager and status in ("In Progress", "Converted") else None,
        follow_up_at=utcnow() + timedelta(days=follow_up_days) if follow_up_days else None,
    )
    db.add(lead)
    db.flush()

    conversation = Conversation(
        workspace_id=workspace_id,
        lead_id=lead.id,
        status="Abandoned" if status == "Incomplete" else "Completed",
        language=language,
        client_name=client,
        client_email=email,
        state={"answers": answers, "current_node": "" if status != "Incomplete" else "budget"},
        last_node="" if status != "Incomplete" else "budget",
        started_at=created,
        ended_at=created + timedelta(minutes=random.randint(3, 11)),
    )
    db.add(conversation)
    db.flush()

    context = {
        "client_name": client or "there",
        "client_email": email or "—",
        "service": service,
        "goals": goals or "Just browsing for now",
        "budget_text": f"About ${budget:,.0f}" if budget else "Not sure yet",
        "timeline": timeline or "Not decided",
    }
    steps = TRANSCRIPT_TEMPLATE if status != "Incomplete" else TRANSCRIPT_TEMPLATE[:6]
    for offset, (sender, template, event, node) in enumerate(steps):
        db.add(
            Message(
                conversation_id=conversation.id,
                sender=sender,
                text=template.format(**context),
                meta={"node": node, "event": event, "demo": True},
                created_at=created + timedelta(seconds=25 * offset),
            )
        )
    if status != "Incomplete":
        db.add(
            Message(
                conversation_id=conversation.id, sender="bot",
                text=f"Thank you! I have everything I need. Here's a summary of your request:"
                     f"\n\n{lead.summary}\n\nOur team will get back to you shortly. 🙌",
                meta={"node": "", "event": "summary", "demo": True},
                created_at=created + timedelta(seconds=25 * len(steps)),
            )
        )

    db.add(ActivityLog(lead_id=lead.id, actor="system", action="created",
                       detail="Lead created from chat", created_at=created))
    if status in ("Qualified", "In Progress", "Converted", "Closed", "Rejected"):
        db.add(ActivityLog(lead_id=lead.id, actor="John Carter", action="status_change",
                           detail=f"status: New → {status}",
                           created_at=created + timedelta(hours=2)))
    if status == "In Progress":
        db.add(ActivityLog(lead_id=lead.id, actor="John Carter", action="comment",
                           detail="Called the client — very engaged, sending a proposal Monday.",
                           created_at=created + timedelta(hours=5)))
    if status == "Converted":
        db.add(ActivityLog(lead_id=lead.id, actor="Maria Lopez", action="comment",
                           detail="Contract signed. Kickoff scheduled.",
                           created_at=created + timedelta(days=1)))

    if days_ago <= 2:
        db.add(
            Notification(
                workspace_id=workspace_id, channel="inapp", event="lead.created",
                title=f"New lead: {project}",
                body=f"{client or 'Anonymous'} · {service} · "
                     f"{'$' + format(budget, ',.0f') if budget else '—'} · score {score}",
                link=f"/admin/leads/{lead.id}", status="sent", created_at=created,
            )
        )


def _ensure_abandoned_conversations(db: Session, workspace_id: int) -> None:
    """A few drop-offs with no lead, so funnel/drop-off analytics look real."""
    for index, node in enumerate(("service", "budget", "budget", "email")):
        started = utcnow() - timedelta(days=index + 1, hours=3)
        conversation = Conversation(
            workspace_id=workspace_id, status="Abandoned", language="en",
            state={"answers": {"service": "Website"}, "current_node": node},
            last_node=node, started_at=started, ended_at=started + timedelta(minutes=2),
        )
        db.add(conversation)
        db.flush()
        db.add(Message(conversation_id=conversation.id, sender="bot",
                       text="Hello! What service are you interested in?",
                       meta={"node": "service", "event": "greeting"}, created_at=started))
        db.add(Message(conversation_id=conversation.id, sender="user", text="Website",
                       meta={"node": "service", "event": "answer"},
                       created_at=started + timedelta(seconds=30)))
