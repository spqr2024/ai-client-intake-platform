"""Seed the database with demo data for portfolio/demo purposes.

Usage:  python -m app.seed
"""

import random
from datetime import timedelta

from sqlalchemy import select

from app.core.security import hash_password
from app.db import Base, SessionLocal, engine
from app.main import bootstrap
from app.models import (
    ActivityLog,
    Conversation,
    KnowledgeBaseArticle,
    Lead,
    Message,
    User,
    utcnow,
)

DEMO_LEADS = [
    {
        "project_name": "Online store — Alice Johnson",
        "client_name": "Alice Johnson",
        "client_email": "alice@example.com",
        "service": "Online store",
        "budget": 5000,
        "timeline": "1-3 months",
        "status": "Qualified",
        "score": 85,
        "days_ago": 1,
        "transcript": [
            ("bot", "Hello! I'm your intake assistant. May I have your name?"),
            ("user", "Alice Johnson"),
            ("bot", "Nice to meet you! What service are you interested in?"),
            ("user", "I need an online store"),
            ("bot", "Great, what's your approximate budget?"),
            ("user", "Around $5000"),
            ("bot", "Do you have a deadline?"),
            ("user", "Within 3 months would be perfect"),
            ("bot", "What email should we use to follow up?"),
            ("user", "alice@example.com"),
        ],
    },
    {
        "project_name": "Logo Design — Bob Martinez",
        "client_name": "Bob Martinez",
        "client_email": "bob@startup.io",
        "service": "Branding / Design",
        "budget": 1500,
        "timeline": "2 weeks",
        "status": "In Progress",
        "score": 62,
        "days_ago": 3,
        "transcript": [
            ("bot", "Hello! What service are you interested in?"),
            ("user", "Logo design for my startup"),
            ("bot", "What's your approximate budget?"),
            ("user", "$1500"),
        ],
    },
    {
        "project_name": "Website — Kateryna Shevchenko",
        "client_name": "Катерина Шевченко",
        "client_email": "kateryna@example.ua",
        "service": "Вебсайт",
        "budget": 2000,
        "timeline": "Якнайшвидше",
        "status": "New",
        "score": 70,
        "days_ago": 0,
        "language": "uk",
        "transcript": [
            ("bot", "Вітаю! Як вас звати?"),
            ("user", "Катерина Шевченко"),
            ("bot", "Яка послуга вас цікавить?"),
            ("user", "Потрібен вебсайт для салону краси"),
            ("bot", "Який ваш орієнтовний бюджет?"),
            ("user", "Близько $2000"),
        ],
    },
    {
        "project_name": "Mobile app — Dan Lee",
        "client_name": "Dan Lee",
        "client_email": "dan@fitness.app",
        "service": "Mobile app",
        "budget": 12000,
        "timeline": "ASAP",
        "status": "Converted",
        "score": 95,
        "days_ago": 12,
        "transcript": [
            ("bot", "Hello! What can we build for you?"),
            ("user", "A fitness tracking mobile app for iOS and Android"),
            ("bot", "What's your budget range?"),
            ("user", "$12k, could stretch if needed"),
        ],
    },
    {
        "project_name": "Website redesign — (anonymous)",
        "client_name": "",
        "client_email": "",
        "service": "Website",
        "budget": None,
        "timeline": "",
        "status": "Incomplete",
        "score": 15,
        "days_ago": 5,
        "transcript": [
            ("bot", "Hello! What service are you interested in?"),
            ("user", "Maybe a website redesign, just looking around"),
        ],
    },
    {
        "project_name": "SEO audit — Grace Kim",
        "client_name": "Grace Kim",
        "client_email": "grace@retailco.com",
        "service": "Other",
        "budget": 800,
        "timeline": "Flexible",
        "status": "Rejected",
        "score": 30,
        "days_ago": 8,
        "transcript": [
            ("bot", "Hello! What service are you interested in?"),
            ("user", "SEO audit"),
            ("bot", "What's your approximate budget?"),
            ("user", "$800 max"),
        ],
    },
]

KB_ARTICLES = [
    {
        "title": "How long does a typical website project take?",
        "content": "A typical marketing website takes 4-8 weeks from kickoff to launch: "
        "1 week of discovery, 2-3 weeks of design, 2-3 weeks of development and 1 week "
        "of QA and content loading. Online stores usually take 8-12 weeks.",
    },
    {
        "title": "What is included in the price?",
        "content": "Every quote includes design, development, basic SEO setup, mobile "
        "responsiveness, one round of revisions and 30 days of post-launch support. "
        "Hosting and domain registration are billed separately at cost.",
    },
    {
        "title": "Where are you located and do you work remotely?",
        "content": "Our team is fully remote with headquarters in Kyiv, Ukraine. We work "
        "with clients worldwide across all time zones and hold meetings over Zoom or "
        "Google Meet.",
    },
    {
        "title": "Payment terms and process",
        "content": "We work in milestones: 40% upfront to book the project, 40% at design "
        "approval and 20% at launch. We accept bank transfer, Wise and Payoneer.",
    },
]


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        bootstrap(db)

        if db.scalars(select(User).where(User.email == "manager@example.com")).first() is None:
            db.add(
                User(
                    name="John Manager",
                    email="manager@example.com",
                    password_hash=hash_password("manager123"),
                    role="manager",
                )
            )

        if db.scalars(select(KnowledgeBaseArticle)).first() is None:
            for article in KB_ARTICLES:
                db.add(KnowledgeBaseArticle(**article))

        if db.scalars(select(Lead)).first() is None:
            manager = db.scalars(select(User).where(User.role == "manager")).first()
            for item in DEMO_LEADS:
                created = utcnow() - timedelta(days=item["days_ago"], hours=random.randint(0, 8))
                score = item["score"]
                lead = Lead(
                    project_name=item["project_name"],
                    client_name=item["client_name"],
                    client_email=item["client_email"],
                    service=item["service"],
                    budget=item["budget"],
                    timeline=item["timeline"],
                    status=item["status"],
                    score=score,
                    priority="High" if score >= 80 else "Medium" if score >= 50 else "Low",
                    tags=(["vip"] if score >= 85 else []) + (["demo"]),
                    language=item.get("language", "en"),
                    summary=f"- **Project**: {item['project_name']}\n"
                    f"- **Budget**: {'$' + format(item['budget'], ',.0f') if item['budget'] else '—'}\n"
                    f"- **Timeline**: {item['timeline'] or '—'}",
                    created_at=created,
                    assigned_to_id=manager.id if manager and item["status"] == "In Progress" else None,
                )
                db.add(lead)
                db.flush()
                conversation = Conversation(
                    lead_id=lead.id,
                    status="Abandoned" if item["status"] == "Incomplete" else "Completed",
                    language=item.get("language", "en"),
                    client_name=item["client_name"],
                    client_email=item["client_email"],
                    started_at=created,
                    ended_at=created + timedelta(minutes=6),
                )
                db.add(conversation)
                db.flush()
                for offset, (sender, text) in enumerate(item["transcript"]):
                    db.add(
                        Message(
                            conversation_id=conversation.id,
                            sender=sender,
                            text=text,
                            created_at=created + timedelta(seconds=30 * offset),
                        )
                    )
                db.add(
                    ActivityLog(
                        lead_id=lead.id,
                        actor="system",
                        action="created",
                        detail="Lead created from chat (demo seed)",
                        created_at=created,
                    )
                )
        db.commit()
        print(
            "Seed complete. Admin: admin@example.com / admin12345 — Manager: manager@example.com / manager123"
        )
    finally:
        db.close()


if __name__ == "__main__":
    seed()
