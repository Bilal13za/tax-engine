"""Test §16.17: the engine runs with no network access at all.

We disable the socket layer entirely; every engine operation (matching,
decision tables, calculations, reconciliation, search, CSV export) must
still succeed — proving there is no hidden cloud/AI dependency.
"""

import socket

import pytest

from taxengine import calc as calcmod
from taxengine import decision, export as exportmod, reconcile
from taxengine import search as searchmod


@pytest.fixture()
def no_network(monkeypatch):
    def _blocked(*a, **k):
        raise AssertionError("network access attempted — engine must be offline")
    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    return True


def test_full_analysis_offline(test_dbs, no_network, tmp_path):
    k = test_dbs["knowledge"]
    facts = {"tax_category": "withholding_tax", "jurisdiction": "federal",
             "taxpayer_type": "company", "transaction_type": "payment_for_goods",
             "transaction_date": "2025-02-01", "payment_category": "goods",
             "payment_amount": 100000, "payer_is_withholding_agent": True,
             "exemption_certificate_valid": False}
    steps = decision.analyze(
        k, {}, facts,
        calc_runner=lambda code, inputs, on_date=None:
            calcmod.run_calculation(k, code, inputs, on_date=on_date))
    assert len(steps) == 14
    s10 = next(s for s in steps if s["step_no"] == 10)
    calc_item = next(c for c in s10["detail"]["calculations"]
                     if c["calc_code"] == "CALC-TEST-WHT")
    assert calc_item["result"]["result"] == 7000.0
    assert calc_item["result"]["validation_status"] == "complete"


def test_search_calc_recon_export_offline(test_dbs, no_network, tmp_path):
    k, w = test_dbs["knowledge"], test_dbs["workdata"]
    hits = searchmod.search(k, "payment")
    assert any(h["entity_code"] == "RULE-TEST-WHT" for h in hits)
    res = calcmod.run_calculation(
        k, "CALC-TEST-SLAB", {"base": {"value": 1500, "source": "t"}},
        on_date="2023-01-01")
    assert res["result"] == 50.0
    rec = reconcile.compute([
        {"label": "x", "amount_a": 10, "amount_b": 10,
         "source_a": "a", "source_b": "b", "note": ""}])
    assert rec["total_difference"] == 0
    p = exportmod.export_rules_csv(k, tmp_path / "r.csv")
    assert p.exists()
