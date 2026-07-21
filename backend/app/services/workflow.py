"""Data-driven conversation workflow engine.

A workflow is a JSON document:

{
  "start": "name",
  "nodes": {
    "name": {
      "field": "client_name",          # answer is stored under this key
      "type": "text",                  # text | choice | number | email | phone
      "prompt": {"en": "...", "uk": "..."},
      "options": {"en": [...], "uk": [...]},   # quick replies (choice nodes)
      "branches": [{"if_contains": ["shop", "store"], "goto": "budget"}],
      "next": "service",               # default next node ("" / missing = end)
      "skip_if_known": true            # skip when the field was pre-filled
    },
    ...
  }
}

The engine is a pure state machine: `advance()` takes the current state and a
user message, validates/normalizes the answer for the node type, applies
branching and returns the next prompt. No LLM calls happen here, which keeps
intake logic deterministic and unit-testable; the LLM layer only rephrases
prompts and writes summaries.
"""

import copy
import re
from dataclasses import dataclass, field


@dataclass
class StepResult:
    reply: str = ""
    quick_replies: list[str] = field(default_factory=list)
    done: bool = False
    needs_clarification: bool = False
    state: dict = field(default_factory=dict)


VAGUE_ANSWERS = {
    "en": {"not sure", "no idea", "dont know", "don't know", "idk", "n/a", "na", "unsure", "maybe", "?"},
    "uk": {"не знаю", "не впевнений", "не впевнена", "хз", "можливо", "не певен"},
}

CLARIFY_TEXT = {
    "en": "No worries — even a rough idea helps. Could you give me your best guess?",
    "uk": "Нічого страшного — навіть приблизна відповідь допоможе. Можете припустити?",
}

INVALID_TEXT = {
    "number": {
        "en": "I couldn't catch a number there. Could you give an approximate figure, e.g. “$2000”?",
        "uk": "Не вдалося розпізнати число. Вкажіть, будь ласка, орієнтовну суму, наприклад «$2000».",
    },
    "email": {
        "en": "That doesn't look like a valid email. Could you re-check it?",
        "uk": "Це не схоже на коректний email. Перевірте, будь ласка.",
    },
    "phone": {
        "en": "That doesn't look like a phone number. Could you re-check it?",
        "uk": "Це не схоже на номер телефону. Перевірте, будь ласка.",
    },
}

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]{2,}")
_PHONE_RE = re.compile(r"\+?[\d\s()\-]{7,}")
_NUMBER_RE = re.compile(r"(\d[\d\s.,]*)\s*([kкKК])?")
_CYRILLIC_RE = re.compile(r"[а-щьюяїієґА-ЩЬЮЯЇІЄҐ]")


def detect_language(text: str) -> str:
    return "uk" if _CYRILLIC_RE.search(text or "") else "en"


def localized(value, lang: str, fallback: str = "en"):
    """Pick a language variant out of {"en": ..., "uk": ...} (or pass through)."""
    if isinstance(value, dict):
        return value.get(lang) or value.get(fallback) or next(iter(value.values()), "")
    return value


def parse_number(text: str) -> float | None:
    match = _NUMBER_RE.search(text.replace(",", ""))
    if not match:
        return None
    raw = re.sub(r"[\s,]", "", match.group(1)).rstrip(".")
    try:
        value = float(raw)
    except ValueError:
        return None
    if match.group(2):
        value *= 1000
    return value


def is_vague(text: str, lang: str) -> bool:
    normalized = text.strip().lower().rstrip(".!")
    return normalized in VAGUE_ANSWERS.get(lang, set()) | VAGUE_ANSWERS["en"]


def _validate(node: dict, text: str, lang: str) -> tuple[bool, str | float]:
    node_type = node.get("type", "text")
    if node_type == "number":
        value = parse_number(text)
        return (value is not None, value if value is not None else "")
    if node_type == "email":
        match = _EMAIL_RE.search(text)
        return (match is not None, match.group(0) if match else "")
    if node_type == "phone":
        match = _PHONE_RE.search(text)
        return (match is not None, match.group(0).strip() if match else "")
    return (bool(text.strip()), text.strip())


def _next_node_id(node: dict, answer: str) -> str:
    answer_lower = str(answer).lower()
    for branch in node.get("branches", []):
        keywords = [k.lower() for k in branch.get("if_contains", [])]
        if any(k in answer_lower for k in keywords):
            return branch.get("goto", "")
    return node.get("next", "")


def _prompt_for(definition: dict, node_id: str, lang: str) -> tuple[str, list[str]]:
    node = definition["nodes"][node_id]
    prompt = localized(node.get("prompt", ""), lang)
    options = localized(node.get("options", []), lang) or []
    return prompt, list(options)


def _skip_known(definition: dict, node_id: str, answers: dict) -> str:
    """Skip consecutive nodes whose field is already pre-filled."""
    while node_id:
        node = definition["nodes"].get(node_id)
        if not node:
            return ""
        if node.get("skip_if_known") and answers.get(node.get("field", "")):
            node_id = node.get("next", "")
            continue
        return node_id
    return ""


def start(definition: dict, prefilled: dict | None = None, lang: str = "en") -> StepResult:
    answers = dict(prefilled or {})
    node_id = _skip_known(definition, definition.get("start", ""), answers)
    state = {"current_node": node_id, "answers": answers, "clarify_count": 0}
    if not node_id:
        return StepResult(done=True, state=state)
    prompt, options = _prompt_for(definition, node_id, lang)
    return StepResult(reply=prompt, quick_replies=options, state=state)


def advance(definition: dict, state: dict, user_text: str, lang: str = "en") -> StepResult:
    node_id = state.get("current_node", "")
    answers = dict(state.get("answers", {}))
    clarify_count = int(state.get("clarify_count", 0))
    node = definition["nodes"].get(node_id)
    if node is None:
        return StepResult(done=True, state={**state, "answers": answers})

    valid, value = _validate(node, user_text, lang)
    vague = is_vague(user_text, lang)

    if (vague or not valid) and clarify_count < 1:
        text = CLARIFY_TEXT[lang if lang in CLARIFY_TEXT else "en"]
        if not valid and not vague:
            node_type = node.get("type", "text")
            text = INVALID_TEXT.get(node_type, {}).get(lang) or INVALID_TEXT.get(node_type, {}).get(
                "en", text
            )
        _, options = _prompt_for(definition, node_id, lang)
        new_state = {"current_node": node_id, "answers": answers, "clarify_count": clarify_count + 1}
        return StepResult(reply=text, quick_replies=options, needs_clarification=True, state=new_state)

    # Accept the answer (possibly empty after a failed clarification round).
    answers[node.get("field", node_id)] = value if valid and not vague else ""

    next_id = _skip_known(definition, _next_node_id(node, user_text), answers)
    new_state = {"current_node": next_id, "answers": answers, "clarify_count": 0}
    if not next_id:
        return StepResult(done=True, state=new_state)
    prompt, options = _prompt_for(definition, next_id, lang)
    return StepResult(reply=prompt, quick_replies=options, state=new_state)


# ── Default intake workflow (web agency flavour, EN + UK) ─────────────────
#
# `_DEFAULT_WORKFLOW_PRE_CONTACT` is the flow as shipped through v2.3.x: it
# always asked for an email at the end. The current default replaces that single
# email step with a communication-channel picker (Email / Telegram / Phone) via
# `_with_contact_step`. The pre-contact snapshot is kept *frozen* so the startup
# migration (chat.upgrade_default_workflows) can recognise an unmodified seeded
# workflow in an existing database and upgrade it in place, without clobbering a
# flow an admin has customised. Never edit the snapshot; when the default
# changes again, append the superseded DEFAULT_WORKFLOW to SUPERSEDED_DEFAULTS.
_DEFAULT_WORKFLOW_PRE_CONTACT: dict = {
    "start": "name",
    "nodes": {
        "name": {
            "field": "client_name",
            "type": "text",
            "skip_if_known": True,
            "prompt": {
                "en": "Hello! I'm your intake assistant — I'll gather a few project details so our team can help you faster. May I have your name?",
                "uk": "Вітаю! Я асистент з прийому заявок — поставлю кілька запитань, щоб наша команда допомогла вам швидше. Як вас звати?",
            },
            "next": "service",
        },
        "service": {
            "field": "service",
            "type": "choice",
            "prompt": {
                "en": "Nice to meet you! What service are you interested in?",
                "uk": "Приємно познайомитись! Яка послуга вас цікавить?",
            },
            "options": {
                "en": ["Website", "Online store", "Mobile app", "Branding / Design", "Other"],
                "uk": ["Вебсайт", "Інтернет-магазин", "Мобільний застосунок", "Брендинг / Дизайн", "Інше"],
            },
            "branches": [
                {
                    "if_contains": ["store", "shop", "ecommerce", "e-commerce", "магазин"],
                    "goto": "store_platform",
                }
            ],
            "next": "goals",
        },
        "store_platform": {
            "field": "platform",
            "type": "choice",
            "prompt": {
                "en": "Great choice! Do you have a platform in mind for the store?",
                "uk": "Чудовий вибір! Чи є платформа, якій ви надаєте перевагу?",
            },
            "options": {
                "en": ["Shopify", "WooCommerce", "Custom build", "Not sure yet"],
                "uk": ["Shopify", "WooCommerce", "Індивідуальна розробка", "Ще не знаю"],
            },
            "next": "goals",
        },
        "goals": {
            "field": "goals",
            "type": "text",
            "prompt": {
                "en": "Could you describe your project goals or needs in a sentence or two?",
                "uk": "Опишіть, будь ласка, цілі чи потреби вашого проєкту одним-двома реченнями.",
            },
            "next": "budget",
        },
        "budget": {
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
            "next": "timeline",
        },
        "timeline": {
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
            "next": "email",
        },
        "email": {
            "field": "client_email",
            "type": "email",
            "skip_if_known": True,
            "prompt": {
                "en": "Almost done! What email should we use to send you the summary and follow up?",
                "uk": "Майже готово! На який email надіслати підсумок і відповідь нашої команди?",
            },
            "next": "extra",
        },
        "extra": {
            "field": "extra_notes",
            "type": "text",
            "prompt": {
                "en": "Is there anything else important we should know? (Type 'no' if not.)",
                "uk": "Чи є ще щось важливе, що нам варто знати? (Напишіть «ні», якщо ні.)",
            },
            "options": {"en": ["No, that's all"], "uk": ["Ні, це все"]},
            "next": "",
        },
    },
}

# The channel picker + its three branch nodes. The picker replaces the single
# `email` step: the client chooses how they want to be reached, then supplies the
# matching detail. `contact_method` stores the raw choice; branching keys off the
# user's text (see `_next_node_id`). Each branch writes to the field the rest of
# the system already reads (client_email / client_phone), plus contact_telegram
# for the handle, which has no dedicated column and is resolved in _finalize.
_CONTACT_NODES: dict = {
    "contact_method": {
        "field": "contact_method",
        "type": "choice",
        "prompt": {
            "en": "Almost done! How would you prefer our team to reach you?",
            "uk": "Майже готово! Як вам зручніше, щоб наша команда з вами зв'язалася?",
        },
        "options": {
            "en": ["Email", "Telegram", "Phone"],
            "uk": ["Email", "Telegram", "Телефон"],
        },
        "branches": [
            {"if_contains": ["telegram", "телеграм"], "goto": "contact_telegram"},
            {
                "if_contains": ["phone", "mobile", "call", "телефон", "номер", "дзвін"],
                "goto": "contact_phone",
            },
        ],
        "next": "contact_email",
    },
    "contact_email": {
        "field": "client_email",
        "type": "email",
        "skip_if_known": True,
        "prompt": {
            "en": "Great — what email should we use to send the summary and follow up?",
            "uk": "Чудово — на який email надіслати підсумок і відповідь нашої команди?",
        },
        "next": "extra",
    },
    "contact_telegram": {
        "field": "contact_telegram",
        "type": "text",
        "prompt": {
            "en": "Great — what's your Telegram username so we can message you? (e.g. @username)",
            "uk": "Чудово — вкажіть ваш нікнейм у Telegram, щоб ми написали. (наприклад, @username)",
        },
        "next": "extra",
    },
    "contact_phone": {
        "field": "client_phone",
        "type": "phone",
        "prompt": {
            "en": "Great — what mobile number should we call or text?",
            "uk": "Чудово — на який номер телефону зателефонувати чи написати?",
        },
        "next": "extra",
    },
}


def _with_contact_step(base: dict) -> dict:
    """Derive the current default from the pre-contact snapshot by swapping the
    lone `email` step for the communication-channel picker."""
    definition = copy.deepcopy(base)
    nodes = definition["nodes"]
    nodes["timeline"]["next"] = "contact_method"
    del nodes["email"]
    nodes.update(copy.deepcopy(_CONTACT_NODES))
    return definition


DEFAULT_WORKFLOW: dict = _with_contact_step(_DEFAULT_WORKFLOW_PRE_CONTACT)

# Frozen prior built-in defaults. A stored default workflow that still deep-equals
# one of these has never been customised, so it is safe to upgrade in place.
SUPERSEDED_DEFAULTS: list[dict] = [_DEFAULT_WORKFLOW_PRE_CONTACT]
