"""Tests §14 validation: incomplete/unverifiable seeds are rejected,
never silently stored. Also §16.12/16.13 (unsupported deductions, evidence)."""

import json

import pytest

from taxengine import decision, loader
from taxengine.validate import SeedError, validate_rule


def _rule(**over):
    base = {
        "code": "RULE-BAD", "title": "Bad", "tax_category": "withholding_tax",
        "jurisdiction": "federal", "taxpayer_types": ["company"],
        "triggering_transaction": "x", "transaction_types": ["payment_for_goods"],
        "applicability_conditions": {"all": []},
        "decision_logic": {"table": [{"when": {"all": []}, "then": "y",
                                      "treatment_code": "t"}],
                           "default": "d"},
        "expected_treatment": "y", "effective_from": "2020-01-01",
        "verification_status": "draft",
        "legislation_codes": ["LEG-TEST-S1"],
    }
    base.update(over)
    return base


def test_rule_without_legislation_rejected(test_dbs):
    k = test_dbs["knowledge"]
    known = {"legislation": {"LEG-TEST-S1"}, "rules": set(), "risks": set(),
             "evidence": {"EV-TEST-INV"}, "procedures": {"PROC-TEST"},
             "calc_tables": {"CALC-TEST-WHT"}, "sources": set()}
    with pytest.raises(SeedError, match="legislation_code"):
        validate_rule(_rule(legislation_codes=[]), known)


def test_rule_with_bad_dates_rejected(test_dbs):
    known = {"legislation": {"LEG-TEST-S1"}}
    with pytest.raises(SeedError, match="effective_from is after"):
        validate_rule(_rule(effective_from="2025-01-01",
                            effective_to="2024-01-01"), known)


def test_rule_with_unknown_calc_rejected(test_dbs):
    known = {"legislation": {"LEG-TEST-S1"}}
    with pytest.raises(SeedError, match="calc_code"):
        validate_rule(_rule(calc_codes=["CALC-NOPE"]), known)


def test_verified_rule_requires_reviewer(test_dbs):
    known = {"legislation": {"LEG-TEST-S1"}}
    with pytest.raises(SeedError, match="requires reviewer"):
        validate_rule(_rule(verification_status="verified"), known)


def test_loader_rejects_malformed_file(test_dbs, tmp_path):
    k = test_dbs["knowledge"]
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"meta": {}, "rules": [
        {"code": "RULE-X"}  # missing everything
    ]}), encoding="utf-8")
    with pytest.raises(SeedError):
        loader.load_seed_file(bad, conn=k)
    # nothing partially stored
    assert k.execute(
        "SELECT COUNT(*) c FROM tax_rules WHERE code='RULE-X'").fetchone()["c"] == 0


def test_unsupported_deduction_excluded_by_conditions(test_dbs):
    """§16.12: a rule whose conditions fail must not produce a treatment."""
    k = test_dbs["knowledge"]
    matched = decision.match_rules(k, {
        "tax_category": "withholding_tax", "jurisdiction": "federal",
        "taxpayer_type": "company", "transaction_type": "payment_for_goods",
        "transaction_date": "2025-01-01", "payment_category": "royalty",
        "payer_is_withholding_agent": True})
    assert "RULE-TEST-WHT" not in [e["rule"]["code"]
                                  for e in matched["applicable"]]


def test_evidence_tracker_lifecycle(test_dbs):
    """§16.13: evidence requested/received/verified tracked per assessment."""
    w = test_dbs["workdata"]
    aid = w.execute(
        "INSERT INTO assessments(title, facts) VALUES (?,?)",
        ("t", "{}")).lastrowid
    w.execute("INSERT INTO evidence_tracker(assessment_id, evidence_code)"
              " VALUES (?,?)", (aid, "EV-TEST-INV"))
    w.execute("UPDATE evidence_tracker SET requested=1, received=1,"
              " verification_done=1, result='discrepancy_found',"
              " exceptions='amount differs', status='in_progress'"
              " WHERE assessment_id=?", (aid,))
    w.commit()
    row = w.execute("SELECT * FROM evidence_tracker WHERE assessment_id=?",
                    (aid,)).fetchone()
    assert row["result"] == "discrepancy_found"
    assert row["exceptions"] == "amount differs"
