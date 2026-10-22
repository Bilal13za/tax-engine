"""Tests §16.3, §16.8, §16.9: current calculations, rate selection,
accuracy, missing inputs, unverified tables."""

from taxengine import calc as calcmod


def test_slab_calculation_accuracy(test_dbs):
    """Progressive slab: 2500 -> 0 on first 1000, 10% on next 1000, 20% on 500."""
    k = test_dbs["knowledge"]
    res = calcmod.run_calculation(
        k, "CALC-TEST-SLAB", {"base": {"value": 2500, "source": "test"}},
        on_date="2023-01-01")
    assert res["validation_status"] == "complete"
    assert res["result"] == 200.0  # 1000*0 + 1000*0.10 + 500*0.20
    assert any("Slab 3" in s for s in res["steps"])


def test_slab_at_boundary(test_dbs):
    k = test_dbs["knowledge"]
    res = calcmod.run_calculation(
        k, "CALC-TEST-SLAB", {"base": {"value": 1000, "source": "test"}},
        on_date="2023-01-01")
    assert res["result"] == 0.0


def test_missing_inputs_return_incomplete(test_dbs):
    """§16.5: missing required input -> incomplete, no invented values."""
    k = test_dbs["knowledge"]
    res = calcmod.run_calculation(k, "CALC-TEST-WHT", {}, on_date="2023-01-01")
    assert res["validation_status"] == "incomplete_missing_inputs"
    assert res["result"] is None
    assert any("Missing required inputs" in s for s in res["steps"])


def test_unverified_calc_table_flagged(test_dbs):
    """§16.14: unverified table computes but is flagged unverified_rule."""
    k = test_dbs["knowledge"]
    res = calcmod.run_calculation(
        k, "CALC-TEST-DRAFT",
        {"payment_amount": {"value": 1000, "source": "test"}},
        on_date="2023-01-01")
    assert res["validation_status"] == "unverified_rule"
    assert res["result"] == 990.0
    assert any("indicative only" in s for s in res["steps"])


def test_audit_trail_fields_present(test_dbs):
    """§11: every run records inputs, sources, rule, provision, dates,
    steps, rounding, result, validation status."""
    k = test_dbs["knowledge"]
    res = calcmod.run_calculation(
        k, "CALC-TEST-WHT",
        {"payment_amount": {"value": 200000, "source": "voucher PV-1"}},
        on_date="2025-03-01")
    for key in ("inputs", "applicable_rule", "legislation_ref",
                "effective_date", "steps", "rounding_method", "result",
                "validation_status"):
        assert key in res, f"missing trail field {key}"
    assert res["inputs"]["payment_amount"]["source"] == "voucher PV-1"
    assert res["legislation_ref"] == "Test Act s.1(1)(a) as amended"
    assert res["rounding_method"] == "nearest_rupee"
    assert len(res["steps"]) >= 3


def test_rounding_nearest_rupee(test_dbs):
    k = test_dbs["knowledge"]
    res = calcmod.run_calculation(
        k, "CALC-TEST-WHT",
        {"payment_amount": {"value": 33333, "source": "test"}},
        on_date="2025-01-01")
    # 33333 * 0.07 = 2333.31 -> 2333
    assert res["result"] == 2333.0


def _sched_inputs(**over):
    base = {"payment_amount": {"value": 100000, "source": "test"},
            "payee_type": {"value": "company", "source": "test"},
            "atl_status": {"value": "ATL", "source": "test"}}
    for k, v in over.items():
        base[k] = {"value": v, "source": "test"}
    return base


def test_rate_schedule_selects_matching_row(test_dbs):
    k = test_dbs["knowledge"]
    res = calcmod.run_calculation(k, "CALC-TEST-SCHEDULE",
                                  _sched_inputs(), on_date="2023-01-01")
    assert res["validation_status"] == "complete"
    assert res["result"] == 5000.0  # company + ATL -> 5%
    assert any("Rate row 1 selected" in s for s in res["steps"])


def test_rate_schedule_alias_and_wildcard(test_dbs):
    """Dimension alias atl->atl_status resolves; 'any' is a wildcard."""
    k = test_dbs["knowledge"]
    res = calcmod.run_calculation(
        k, "CALC-TEST-SCHEDULE",
        _sched_inputs(payee_type="non_company"), on_date="2023-01-01")
    assert res["result"] == 5500.0  # wildcard row, 5.5%


def test_rate_schedule_missing_dimension_incomplete(test_dbs):
    """Missing dimension -> incomplete, never a guessed rate."""
    k = test_dbs["knowledge"]
    res = calcmod.run_calculation(
        k, "CALC-TEST-SCHEDULE",
        {"payment_amount": {"value": 100000, "source": "test"}},
        on_date="2023-01-01")
    assert res["validation_status"] == "incomplete_missing_inputs"
    assert res["result"] is None
    assert any("Missing required inputs" in s for s in res["steps"])


def test_rate_schedule_no_matching_row_errors(test_dbs):
    import pytest
    from taxengine.calc import CalculationError
    k = test_dbs["knowledge"]
    with pytest.raises(CalculationError, match="no rate_schedule row matches"):
        calcmod.run_calculation(
            k, "CALC-TEST-SCHEDULE",
            _sched_inputs(payee_type="non_company", atl_status="non_ATL"),
            on_date="2023-01-01")
