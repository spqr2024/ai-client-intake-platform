from app.services import workflow as wf


def test_detect_language():
    assert wf.detect_language("Привіт, мені потрібен сайт") == "uk"
    assert wf.detect_language("Hello, I need a website") == "en"


def test_parse_number_variants():
    assert wf.parse_number("$2000") == 2000
    assert wf.parse_number("about 2,500 dollars") == 2500
    assert wf.parse_number("2k") == 2000
    assert wf.parse_number("no clue") is None


def test_start_skips_prefilled_name():
    step = wf.start(wf.DEFAULT_WORKFLOW, {"client_name": "Alice"}, "en")
    assert step.state["current_node"] == "service"
    assert "service" in step.reply.lower()


def test_full_happy_path():
    step = wf.start(wf.DEFAULT_WORKFLOW, {}, "en")
    assert step.state["current_node"] == "name"

    answers = [
        "Alice",
        "I need an online store",  # branches to store_platform
        "Shopify",
        "Sell handmade jewelry across Europe with 200 products",
        "$5000",
        "1-3 months",
        "Email",  # communication channel picker
        "alice@example.com",
        "no",
    ]
    state = step.state
    for answer in answers:
        step = wf.advance(wf.DEFAULT_WORKFLOW, state, answer, "en")
        state = step.state
    assert step.done
    collected = state["answers"]
    assert collected["client_name"] == "Alice"
    assert collected["platform"] == "Shopify"
    assert collected["budget"] == 5000
    assert collected["contact_method"] == "Email"
    assert collected["client_email"] == "alice@example.com"


def test_contact_picker_routes_to_telegram():
    """Choosing Telegram asks for a handle and stores it, not an email."""
    state = {"current_node": "contact_method", "answers": {}, "clarify_count": 0}
    step = wf.advance(wf.DEFAULT_WORKFLOW, state, "Telegram", "en")
    assert step.state["current_node"] == "contact_telegram"
    step = wf.advance(wf.DEFAULT_WORKFLOW, step.state, "@dana_dev", "en")
    # The `extra` node still follows; the channel detail is captured en route.
    assert step.state["current_node"] == "extra"
    assert step.state["answers"]["contact_telegram"] == "@dana_dev"
    assert not step.state["answers"].get("client_email")


def test_contact_picker_routes_to_phone():
    state = {"current_node": "contact_method", "answers": {}, "clarify_count": 0}
    step = wf.advance(wf.DEFAULT_WORKFLOW, state, "Phone", "en")
    assert step.state["current_node"] == "contact_phone"
    step = wf.advance(wf.DEFAULT_WORKFLOW, step.state, "+1 415 555 0198", "en")
    assert step.state["current_node"] == "extra"
    assert step.state["answers"]["client_phone"] == "+1 415 555 0198"


def test_branching_skips_platform_for_non_store():
    step = wf.start(wf.DEFAULT_WORKFLOW, {"client_name": "Bob"}, "en")
    step = wf.advance(wf.DEFAULT_WORKFLOW, step.state, "Mobile app", "en")
    assert step.state["current_node"] == "goals"


def test_invalid_budget_asks_clarification_then_accepts_empty():
    state = {"current_node": "budget", "answers": {}, "clarify_count": 0}
    step = wf.advance(wf.DEFAULT_WORKFLOW, state, "whatever fits", "en")
    assert step.needs_clarification
    step = wf.advance(wf.DEFAULT_WORKFLOW, step.state, "still no idea honestly", "en")
    assert not step.needs_clarification
    assert step.state["answers"]["budget"] == ""
    assert step.state["current_node"] == "timeline"


def test_vague_answer_triggers_clarification():
    state = {"current_node": "goals", "answers": {}, "clarify_count": 0}
    step = wf.advance(wf.DEFAULT_WORKFLOW, state, "not sure", "en")
    assert step.needs_clarification


def test_invalid_email_reprompts():
    state = {"current_node": "contact_email", "answers": {}, "clarify_count": 0}
    step = wf.advance(wf.DEFAULT_WORKFLOW, state, "my email is banana", "en")
    assert step.needs_clarification
    step = wf.advance(wf.DEFAULT_WORKFLOW, step.state, "ok it is alice@mail.co", "en")
    assert step.state["answers"]["client_email"] == "alice@mail.co"
