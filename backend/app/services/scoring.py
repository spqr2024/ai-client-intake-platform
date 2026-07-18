"""Rule-based lead scoring (0-100).

Deterministic on purpose: scoring drives prioritization and Telegram
notifications, so it must not depend on LLM availability or mood.
"""

URGENT_KEYWORDS = ("asap", "urgent", "immediately", "якнайшвидше", "терміново", "негайно")


def score_lead(answers: dict) -> int:
    score = 0

    budget = answers.get("budget")
    if isinstance(budget, (int, float)) and budget > 0:
        if budget >= 10000:
            score += 35
        elif budget >= 5000:
            score += 30
        elif budget >= 2000:
            score += 25
        elif budget >= 500:
            score += 15
        else:
            score += 5

    timeline = str(answers.get("timeline", "")).lower()
    if timeline:
        score += 15 if any(k in timeline for k in URGENT_KEYWORDS) else 10

    goals = str(answers.get("goals", ""))
    if len(goals) >= 80:
        score += 20
    elif len(goals) >= 20:
        score += 15
    elif goals:
        score += 5

    if answers.get("client_email"):
        score += 15
    if answers.get("client_name"):
        score += 5
    if answers.get("service"):
        score += 10

    return max(0, min(100, score))
