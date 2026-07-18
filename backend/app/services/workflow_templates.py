"""Reusable workflow building blocks and starter templates.

The visual builder composes flows from these instead of asking administrators
to write JSON. Templates are data, not code: adding an industry flow is a new
dict entry, never a code change in the engine.
"""

from app.services.workflow import DEFAULT_WORKFLOW

# Reusable node blueprints the builder offers as "add a step" options.
NODE_LIBRARY: list[dict] = [
    {
        "key": "contact_name",
        "label": "Client name",
        "field": "client_name",
        "type": "text",
        "skip_if_known": True,
        "prompt": {"en": "May I have your name?", "uk": "Як вас звати?"},
    },
    {
        "key": "contact_email",
        "label": "Email address",
        "field": "client_email",
        "type": "email",
        "skip_if_known": True,
        "prompt": {
            "en": "What email should we use to follow up?",
            "uk": "На який email надіслати відповідь?",
        },
    },
    {
        "key": "contact_phone",
        "label": "Phone number",
        "field": "client_phone",
        "type": "phone",
        "prompt": {
            "en": "What's the best phone number to reach you?",
            "uk": "За яким номером телефону з вами зв'язатися?",
        },
    },
    {
        "key": "service_choice",
        "label": "Service selection",
        "field": "service",
        "type": "choice",
        "prompt": {"en": "What service are you interested in?", "uk": "Яка послуга вас цікавить?"},
        "options": {
            "en": ["Website", "Online store", "Mobile app", "Branding / Design", "Other"],
            "uk": ["Вебсайт", "Інтернет-магазин", "Мобільний застосунок", "Брендинг / Дизайн", "Інше"],
        },
    },
    {
        "key": "budget",
        "label": "Budget",
        "field": "budget",
        "type": "number",
        "prompt": {
            "en": "What's your approximate budget for this project (in USD)?",
            "uk": "Який ваш орієнтовний бюджет на цей проєкт (у доларах США)?",
        },
        "options": {
            "en": ["$1000", "$2000", "$5000", "$10000+"],
            "uk": ["$1000", "$2000", "$5000", "$10000+"],
        },
    },
    {
        "key": "timeline",
        "label": "Timeline",
        "field": "timeline",
        "type": "text",
        "prompt": {
            "en": "When would you like the project completed by?",
            "uk": "До якого терміну ви хотіли б завершити проєкт?",
        },
        "options": {
            "en": ["ASAP", "Within 1 month", "1-3 months", "Flexible"],
            "uk": ["Якнайшвидше", "Протягом місяця", "1-3 місяці", "Гнучко"],
        },
    },
    {
        "key": "goals",
        "label": "Project goals (free text)",
        "field": "goals",
        "type": "text",
        "prompt": {
            "en": "Could you describe your project goals in a sentence or two?",
            "uk": "Опишіть, будь ласка, цілі проєкту одним-двома реченнями.",
        },
    },
    {
        "key": "extra_notes",
        "label": "Anything else",
        "field": "extra_notes",
        "type": "text",
        "prompt": {
            "en": "Is there anything else important we should know?",
            "uk": "Чи є ще щось важливе, що нам варто знати?",
        },
        "options": {"en": ["No, that's all"], "uk": ["Ні, це все"]},
    },
]

# Complete starter flows, selectable when creating a workflow.
TEMPLATES: list[dict] = [
    {
        "key": "agency",
        "name": "Web agency intake",
        "description": "Service selection with an online-store branch, budget, timeline and contact.",
        "definition": DEFAULT_WORKFLOW,
    },
    {
        "key": "law",
        "name": "Law firm case intake",
        "description": "Case type, incident date, injury details and urgency scoring.",
        "definition": {
            "start": "name",
            "nodes": {
                "name": {
                    "field": "client_name",
                    "type": "text",
                    "skip_if_known": True,
                    "prompt": {"en": "Hello — I can help start your case review. May I have your name?"},
                    "next": "case_type",
                },
                "case_type": {
                    "field": "service",
                    "type": "choice",
                    "prompt": {"en": "What kind of case do you need help with?"},
                    "options": {
                        "en": ["Personal injury", "Family law", "Employment", "Business dispute", "Other"]
                    },
                    "branches": [{"if_contains": ["injury", "accident"], "goto": "incident_date"}],
                    "next": "case_details",
                },
                "incident_date": {
                    "field": "incident_date",
                    "type": "text",
                    "prompt": {"en": "When did the incident happen?"},
                    "next": "case_details",
                },
                "case_details": {
                    "field": "goals",
                    "type": "text",
                    "prompt": {"en": "Please describe what happened in a few sentences."},
                    "next": "urgency",
                },
                "urgency": {
                    "field": "timeline",
                    "type": "text",
                    "prompt": {"en": "How urgent is this? Are there any upcoming deadlines?"},
                    "options": {"en": ["Very urgent", "Within a month", "Just exploring"]},
                    "next": "email",
                },
                "email": {
                    "field": "client_email",
                    "type": "email",
                    "skip_if_known": True,
                    "prompt": {"en": "What email should our attorney use to reach you?"},
                    "next": "",
                },
            },
        },
    },
    {
        "key": "clinic",
        "name": "Healthcare patient intake",
        "description": "Symptoms, insurance and appointment preference.",
        "definition": {
            "start": "name",
            "nodes": {
                "name": {
                    "field": "client_name",
                    "type": "text",
                    "skip_if_known": True,
                    "prompt": {"en": "Hello! I'll collect a few details before your visit. Your name?"},
                    "next": "reason",
                },
                "reason": {
                    "field": "service",
                    "type": "choice",
                    "prompt": {"en": "What brings you in today?"},
                    "options": {
                        "en": ["New symptoms", "Follow-up visit", "Routine check-up", "Prescription refill"]
                    },
                    "next": "symptoms",
                },
                "symptoms": {
                    "field": "goals",
                    "type": "text",
                    "prompt": {"en": "Please describe your symptoms and when they started."},
                    "next": "insurance",
                },
                "insurance": {
                    "field": "insurance",
                    "type": "text",
                    "prompt": {"en": "Which insurance provider do you use? (Type 'none' if self-paying.)"},
                    "next": "preferred_time",
                },
                "preferred_time": {
                    "field": "timeline",
                    "type": "text",
                    "prompt": {"en": "When would you prefer your appointment?"},
                    "options": {"en": ["As soon as possible", "This week", "Next week"]},
                    "next": "phone",
                },
                "phone": {
                    "field": "client_phone",
                    "type": "phone",
                    "prompt": {"en": "What phone number should the clinic call to confirm?"},
                    "next": "",
                },
            },
        },
    },
    {
        "key": "saas_demo",
        "name": "SaaS demo booking",
        "description": "Company size, use case, timeline and work email.",
        "definition": {
            "start": "name",
            "nodes": {
                "name": {
                    "field": "client_name",
                    "type": "text",
                    "skip_if_known": True,
                    "prompt": {"en": "Hi! Let's get your demo booked. What's your name?"},
                    "next": "company_size",
                },
                "company_size": {
                    "field": "company_size",
                    "type": "choice",
                    "prompt": {"en": "How big is your team?"},
                    "options": {"en": ["1-10", "11-50", "51-200", "200+"]},
                    "next": "use_case",
                },
                "use_case": {
                    "field": "goals",
                    "type": "text",
                    "prompt": {"en": "What problem are you hoping to solve with our product?"},
                    "next": "budget",
                },
                "budget": {
                    "field": "budget",
                    "type": "number",
                    "prompt": {"en": "Do you have a monthly budget in mind (USD)?"},
                    "options": {"en": ["$100", "$500", "$2000", "Not sure yet"]},
                    "next": "timeline",
                },
                "timeline": {
                    "field": "timeline",
                    "type": "text",
                    "prompt": {"en": "When are you looking to get started?"},
                    "options": {"en": ["Immediately", "This quarter", "Just researching"]},
                    "next": "email",
                },
                "email": {
                    "field": "client_email",
                    "type": "email",
                    "skip_if_known": True,
                    "prompt": {"en": "What work email should we send the demo invite to?"},
                    "next": "",
                },
            },
        },
    },
    {
        "key": "blank",
        "name": "Blank flow",
        "description": "A single question to build on from scratch.",
        "definition": {
            "start": "q1",
            "nodes": {
                "q1": {
                    "field": "goals",
                    "type": "text",
                    "prompt": {"en": "How can we help you today?"},
                    "next": "",
                }
            },
        },
    },
]


def analyze(definition: dict) -> dict:
    """Structural report used by the builder: reachability, dead ends, cycles.

    These are *warnings*, not validation errors — an unreachable node is a
    work-in-progress, not a broken flow — so the builder can surface them
    without blocking a save.
    """
    nodes: dict = definition.get("nodes", {}) or {}
    start = definition.get("start", "")
    warnings: list[str] = []

    if not nodes:
        return {
            "reachable": [],
            "unreachable": [],
            "warnings": ["Flow has no steps"],
            "terminal_nodes": [],
            "has_cycle": False,
        }

    # Reachability from start.
    reachable: set[str] = set()
    stack = [start] if start in nodes else []
    while stack:
        current = stack.pop()
        if current in reachable or current not in nodes:
            continue
        reachable.add(current)
        node = nodes[current]
        targets = [node.get("next", "")] + [b.get("goto", "") for b in node.get("branches", [])]
        stack.extend(t for t in targets if t and t not in reachable)

    unreachable = sorted(set(nodes) - reachable)
    if unreachable:
        warnings.append(f"{len(unreachable)} step(s) can never be reached: {', '.join(unreachable)}")

    # Terminal nodes (empty `next` and no branches) end the flow and create the lead.
    terminal = sorted(
        node_id for node_id, node in nodes.items() if not node.get("next") and not node.get("branches")
    )
    if not terminal:
        warnings.append("No step ends the flow — at least one step needs an empty 'next'")

    # Cycle detection over the reachable subgraph.
    has_cycle = False
    visiting: set[str] = set()
    visited: set[str] = set()

    def _visit(node_id: str) -> bool:
        if node_id in visiting:
            return True
        if node_id in visited or node_id not in nodes:
            return False
        visiting.add(node_id)
        node = nodes[node_id]
        targets = [node.get("next", "")] + [b.get("goto", "") for b in node.get("branches", [])]
        found = any(_visit(t) for t in targets if t)
        visiting.discard(node_id)
        visited.add(node_id)
        return found

    if start in nodes:
        has_cycle = _visit(start)
    if has_cycle:
        warnings.append("The flow contains a loop — a client could be asked the same step twice")

    for node_id, node in nodes.items():
        prompt = node.get("prompt")
        text = prompt.get("en") if isinstance(prompt, dict) else prompt
        if not text:
            warnings.append(f"Step '{node_id}' has no question text")
        if not node.get("field"):
            warnings.append(f"Step '{node_id}' does not store its answer in a field")

    return {
        "reachable": sorted(reachable),
        "unreachable": unreachable,
        "terminal_nodes": terminal,
        "has_cycle": has_cycle,
        "warnings": warnings,
    }
