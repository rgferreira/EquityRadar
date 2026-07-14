from src.scoring.technology import technology_potential_evidence


def research(company, peers):
    return {"profile": company, "peer_profiles": peers}


def test_missing_technology_evidence_is_neutral():
    evidence = technology_potential_evidence(None)
    assert evidence["score"] == 50
    assert evidence["confidence"] == 0
    assert evidence["entry_modifier"] == 0


def test_strong_industry_relative_evidence_gets_bounded_positive_modifier():
    company = {
        "market_cap": 1000, "net_debt": -200, "r_and_d_intensity": .25,
        "revenue_growth": .30, "gross_margin": .80, "free_cash_flow_margin": .20,
    }
    peers = [
        {"market_cap": 1000, "net_debt": debt, "r_and_d_intensity": rd,
         "revenue_growth": growth, "gross_margin": margin, "free_cash_flow_margin": fcf}
        for debt, rd, growth, margin, fcf in (
            (100, .08, .05, .40, .05), (50, .10, .10, .50, .08),
            (0, .12, .15, .60, .10), (-50, .15, .20, .70, .12),
            (-100, .18, .25, .75, .15),
        )
    ]
    evidence = technology_potential_evidence(research(company, peers))
    assert evidence["score"] > 80
    assert evidence["confidence"] == 1
    assert 0 < evidence["entry_modifier"] <= 5


def test_missing_r_and_d_caps_confidence_and_never_invents_full_coverage():
    company = {"revenue_growth": .20, "gross_margin": .70, "free_cash_flow_margin": .15}
    peers = [
        {"revenue_growth": .10, "gross_margin": .50, "free_cash_flow_margin": .08}
        for _ in range(5)
    ]
    evidence = technology_potential_evidence(research(company, peers))
    assert evidence["confidence"] <= .5
    assert evidence["coverage"] == "limited"
