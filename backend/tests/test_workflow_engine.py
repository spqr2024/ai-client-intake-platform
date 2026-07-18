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
        "I need an online store",   # branches to store_platform
        "Shopify",
        "Sell handmade jewelry across Europe with 200 products",
        "$5000",
        "1-3 months",
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
    assert collected["client_email"] == "alice@example.com"


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
    state = {"current_node": "email", "answers": {}, "clarify_count": 0}
    step = wf.advance(wf.DEFAULT_WORKFLOW, state, "my email is banana", "en")
    assert step.needs_clarification
    step = wf.advance(wf.DEFAULT_WORKFLOW, step.state, "ok it is alice@mail.co", "en")
    assert step.state["answers"]["client_email"] == "alice@mail.co"
