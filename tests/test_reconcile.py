"""Tests §16.10 (duplicate handling) and §16.11 (reconciliation)."""

import json
from pathlib import Path

from taxengine import loader, reconcile


def test_seed_loading_is_idempotent(test_dbs, tmp_path):
    """§16.10: loading the same seed twice must not duplicate rows."""
    k = test_dbs["knowledge"]
    before = k.execute("SELECT COUNT(*) c FROM tax_rules").fetchone()["c"]
    # re-run the loader over the same synthetic batch via a temp file
    from tests.conftest import _seed_batch
    p = tmp_path / "dup.json"
    p.write_text(json.dumps(_seed_batch()), encoding="utf-8")
    loader.load_seed_file(p, conn=k)
    after = k.execute("SELECT COUNT(*) c FROM tax_rules").fetchone()["c"]
    assert before == after


def test_reconciliation_balanced(test_dbs):
    res = reconcile.compute([
        {"label": "GL", "amount_a": 1000, "amount_b": 1000,
         "source_a": "ledger", "source_b": "return", "note": ""},
        {"label": "Adj", "amount_a": 200, "amount_b": 200,
         "source_a": "wp", "source_b": "return", "note": ""},
    ])
    assert res["total_difference"] == 0
    assert res["incomplete_lines"] == 0
    assert "no differences" in res["conclusion"]
    assert all(ln["status"] == "ok" for ln in res["lines"])


def test_reconciliation_difference_flagged(test_dbs):
    """§16.11: differences are quantified per line, never netted away."""
    res = reconcile.compute([
        {"label": "Revenue", "amount_a": 1000, "amount_b": 950,
         "source_a": "ledger", "source_b": "return", "note": ""},
        {"label": "Other", "amount_a": 50, "amount_b": 50,
         "source_a": "ledger", "source_b": "return", "note": ""},
    ])
    assert res["total_difference"] == 50
    rev = res["lines"][0]
    assert rev["difference"] == 50 and rev["status"] == "difference"
    assert "Unreconciled" in res["conclusion"]


def test_reconciliation_incomplete_not_zero_filled(test_dbs):
    res = reconcile.compute([
        {"label": "Missing B", "amount_a": 100, "amount_b": None,
         "source_a": "ledger", "source_b": "", "note": ""},
    ])
    assert res["lines"][0]["difference"] is None
    assert res["lines"][0]["status"] == "incomplete"
    assert res["incomplete_lines"] == 1
    assert "incomplete" in res["conclusion"]


def test_reconciliation_templates_configured(test_dbs):
    for code in ("RECON-PROFIT-TO-TAXABLE", "RECON-TURNOVER",
                 "RECON-WHT-CREDITS", "RECON-PAYMENTS", "RECON-SALESTAX"):
        tpl = reconcile.new_reconciliation(code)
        assert tpl["suggested_lines"], code
