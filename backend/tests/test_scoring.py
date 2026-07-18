from app.services.scoring import score_lead


def test_rich_lead_scores_high():
    score = score_lead(
        {
            "budget": 12000,
            "timeline": "ASAP",
            "goals": "Build a complete fitness tracking app for iOS and Android with payments "
            "and social features for our gym chain",
            "client_email": "dan@fitness.app",
            "client_name": "Dan",
            "service": "Mobile app",
        }
    )
    assert score >= 90


def test_empty_lead_scores_zero():
    assert score_lead({}) == 0


def test_budget_tiers_monotonic():
    scores = [score_lead({"budget": b}) for b in (100, 600, 2500, 6000, 15000)]
    assert scores == sorted(scores)


def test_score_capped_at_100():
    score = score_lead(
        {
            "budget": 50000,
            "timeline": "urgent, ASAP",
            "goals": "x" * 200,
            "client_email": "a@b.co",
            "client_name": "A",
            "service": "Everything",
        }
    )
    assert score == 100
