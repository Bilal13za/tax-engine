"""Tests §16.1 (effective dates), §16.15 (legislation changes),
§16.18 (version preservation): date-scoped rule/calc selection and history."""

from taxengine import calc as calcmod
from taxengine import decision


def test_rule_not_in_effect_before_start(test_dbs):
    k = test_dbs["knowledge"]
    matched = decision.match_rules(k, {
        "tax_category": "withholding_tax", "jurisdiction": "federal",
        "taxpayer_type": "company", "transaction_type": "payment_for_goods",
        "transaction_date": "2019-06-30", "payment_category": "goods",
        "payer_is_withholding_agent": True})
    codes = [e["rule"]["code"] for e in matched["applicable"]]
    assert "RULE-TEST-WHT" not in codes


def test_rule_in_effect_on_start_date(test_dbs):
    k = test_dbs["knowledge"]
    matched = decision.match_rules(k, {
        "tax_category": "withholding_tax", "jurisdiction": "federal",
        "taxpayer_type": "company", "transaction_type": "payment_for_goods",
        "transaction_date": "2020-01-01", "payment_category": "goods",
        "payer_is_withholding_agent": True,
        "exemption_certificate_valid": False})
    assert "RULE-TEST-WHT" in [e["rule"]["code"] for e in matched["applicable"]]


def test_historical_calc_uses_old_rate(test_dbs):
    """§16.2: a 2023 payment must use v1 (5%), never the latest rate."""
    k = test_dbs["knowledge"]
    res = calcmod.run_calculation(
        k, "CALC-TEST-WHT",
        {"payment_amount": {"value": 100000, "source": "test"}},
        on_date="2023-05-01")
    assert res["validation_status"] == "complete"
    assert res["calc_version"] == 1
    assert res["result"] == 5000.0


def test_current_calc_uses_new_rate(test_dbs):
    k = test_dbs["knowledge"]
    res = calcmod.run_calculation(
        k, "CALC-TEST-WHT",
        {"payment_amount": {"value": 100000, "source": "test"}},
        on_date="2025-01-15")
    assert res["calc_version"] == 2
    assert res["result"] == 7000.0


def test_boundary_dates_pick_correct_version(test_dbs):
    k = test_dbs["knowledge"]
    old = calcmod.select_calc_table(k, "CALC-TEST-WHT", on_date="2024-06-30")
    new = calcmod.select_calc_table(k, "CALC-TEST-WHT", on_date="2024-07-01")
    assert old["version"] == 1
    assert new["version"] == 2


def test_old_version_preserved_not_overwritten(test_dbs):
    """§16.18: both versions coexist in the database."""
    k = test_dbs["knowledge"]
    rows = k.execute(
        "SELECT version, verification_status FROM calc_tables "
        "WHERE code='CALC-TEST-WHT' ORDER BY version").fetchall()
    assert [(r["version"], r["verification_status"]) for r in rows] == [
        (1, "verified"), (2, "verified")]
    legs = k.execute(
        "SELECT code FROM legislation WHERE provision='Section 1'").fetchall()
    assert {r["code"] for r in legs} == {"LEG-TEST-S1", "LEG-TEST-S1-AMENDED"}


def test_no_calc_table_for_unknown_date(test_dbs):
    k = test_dbs["knowledge"]
    res = calcmod.run_calculation(
        k, "CALC-TEST-WHT",
        {"payment_amount": {"value": 100, "source": "test"}},
        on_date="2010-01-01")
    assert res["result"] is None
    assert "No version" in res["steps"][0]
