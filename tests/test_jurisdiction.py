"""Test §16.7: provincial jurisdiction is never assumed — a Sindh rule
applies in Sindh only, and federal rules do not leak into provincial scope."""

from taxengine import decision


def test_sindh_rule_applies_in_sindh(test_dbs):
    k = test_dbs["knowledge"]
    matched = decision.match_rules(k, {
        "tax_category": "sales_tax_provincial", "jurisdiction": "sindh",
        "taxpayer_type": "company", "transaction_type": "service_provision",
        "transaction_date": "2025-01-01", "service_province": "sindh"})
    assert "RULE-TEST-STP-SINDH" in [e["rule"]["code"]
                                    for e in matched["applicable"]]


def test_sindh_rule_out_of_scope_in_punjab(test_dbs):
    k = test_dbs["knowledge"]
    matched = decision.match_rules(k, {
        "tax_category": "sales_tax_provincial", "jurisdiction": "punjab",
        "taxpayer_type": "company", "transaction_type": "service_provision",
        "transaction_date": "2025-01-01", "service_province": "punjab"})
    assert "RULE-TEST-STP-SINDH" not in [
        e["rule"]["code"] for e in matched["applicable"]]
    assert any(e["rule"]["code"] == "RULE-TEST-STP-SINDH"
               for e in matched["out_of_scope"])


def test_jurisdiction_missing_means_no_provincial_match(test_dbs):
    """Without a jurisdiction fact, the provincial rule cannot be confirmed."""
    k = test_dbs["knowledge"]
    matched = decision.match_rules(k, {
        "tax_category": "sales_tax_provincial",
        "taxpayer_type": "company", "transaction_type": "service_provision",
        "transaction_date": "2025-01-01"})
    # jurisdiction filter absent -> rule still candidate only if its own
    # applicability conditions hold; service_province missing -> needs_info
    codes = [e["rule"]["code"] for e in matched["applicable"]]
    assert "RULE-TEST-STP-SINDH" not in codes
