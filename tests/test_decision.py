"""Tests §16.4 (taxpayer classification), §16.5 (missing info),
§16.6 (exemptions/exclusions), decision-table branching."""

from taxengine import decision


def base_facts(**over):
    f = {"tax_category": "withholding_tax", "jurisdiction": "federal",
         "taxpayer_type": "company", "transaction_type": "payment_for_goods",
         "transaction_date": "2025-02-01", "payment_category": "goods",
         "payer_is_withholding_agent": True,
         "exemption_certificate_valid": False}
    f.update(over)
    return f


def test_incorrect_taxpayer_classification_out_of_scope(test_dbs):
    """§16.4: an individual is not in the rule's taxpayer_types."""
    k = test_dbs["knowledge"]
    matched = decision.match_rules(k, base_facts(taxpayer_type="individual"))
    assert "RULE-TEST-WHT" not in [e["rule"]["code"] for e in matched["applicable"]]
    assert any(e["rule"]["code"] == "RULE-TEST-WHT"
               for e in matched["out_of_scope"])


def test_missing_fact_gives_needs_info(test_dbs):
    """§16.5: without payer_is_withholding_agent the rule cannot be decided."""
    k = test_dbs["knowledge"]
    facts = base_facts()
    del facts["payer_is_withholding_agent"]
    matched = decision.match_rules(k, facts)
    need = [e for e in matched["needs_info"]
            if e["rule"]["code"] == "RULE-TEST-WHT"]
    assert need and "payer_is_withholding_agent" in need[0]["missing_fields"]
    assert "RULE-TEST-WHT" not in [e["rule"]["code"] for e in matched["applicable"]]


def test_exemption_excludes_rule(test_dbs):
    """§16.6: a valid exemption certificate triggers the exclusion."""
    k = test_dbs["knowledge"]
    matched = decision.match_rules(
        k, base_facts(exemption_certificate_valid=True))
    assert "RULE-TEST-WHT" not in [e["rule"]["code"] for e in matched["applicable"]]
    assert any(e["rule"]["code"] == "RULE-TEST-WHT"
               for e in matched["excluded"])


def test_decision_table_picks_deduct_branch(test_dbs):
    k = test_dbs["knowledge"]
    row = k.execute(
        "SELECT * FROM tax_rules WHERE code='RULE-TEST-WHT'").fetchone()
    out = decision.run_decision_table(dict(row), base_facts())
    assert out["matched"] is True
    assert out["treatment_code"] == "deduct"
    assert "CALC-TEST-WHT" in out["then"]


def test_decision_table_default_when_no_branch_matches(test_dbs):
    """Default applies only when every branch is decidably False."""
    k = test_dbs["knowledge"]
    row = k.execute(
        "SELECT * FROM tax_rules WHERE code='RULE-TEST-WHT'").fetchone()
    out = decision.run_decision_table(
        dict(row), {"exemption_certificate_valid": False,
                    "payer_is_withholding_agent": False})
    assert out["matched"] is False
    assert out["treatment_code"] == "default"
    assert "withholding-agent status" in out["then"]


def test_decision_table_undecidable_branch_reported(test_dbs):
    """A branch that cannot be decided yields missing facts, not the default."""
    k = test_dbs["knowledge"]
    row = k.execute(
        "SELECT * FROM tax_rules WHERE code='RULE-TEST-WHT'").fetchone()
    out = decision.run_decision_table(dict(row), {})
    assert out["matched"] is False
    assert out["treatment_code"] == ""
    assert out["missing_fields"], "must name the missing facts"


def test_unverified_rule_flagged_in_analysis(test_dbs):
    """§16.14: draft rules appear in applicable but are flagged."""
    k = test_dbs["knowledge"]
    steps = decision.analyze(k, {}, base_facts())
    s4 = next(s for s in steps if s["step_no"] == 4)
    assert "RULE-TEST-DRAFT" in s4["detail"]["unverified"]
    assert s4["confidence"] in ("unverified_rule", "needs_input")
    s5 = next(s for s in steps if s["step_no"] == 5)
    draft_t = [t for t in s5["detail"]["treatments"]
               if t["rule_code"] == "RULE-TEST-DRAFT"][0]
    assert draft_t["verified"] is False


def test_full_chain_has_14_steps(test_dbs):
    k = test_dbs["knowledge"]
    steps = decision.analyze(k, {}, base_facts())
    assert [s["step_no"] for s in steps] == list(range(1, 15))
    names = [s["step_name"] for s in steps]
    assert names == ["taxpayer_profile", "transaction_condition", "legislation",
                     "applicability", "tax_treatment", "possible_error",
                     "tax_risk", "evidence_required", "verification",
                     "calculation", "exceptions", "adjustment",
                     "return_impact", "followup"]
