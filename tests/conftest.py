"""Shared fixtures: isolated temp databases seeded with synthetic test content.

All test content is synthetic (TEST- prefix) — no real tax law is asserted
here. Real-content verification is the job of the seed research, not tests.
"""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from taxengine import db, loader  # noqa: E402


def _seed_batch():
    return {
        "meta": {"domain": "test", "author": "pytest",
                 "prepared_date": "2026-10-21",
                 "notes": "Synthetic test content only."},
        "sources": [
            {"code": "SRC-TEST", "title": "Test Act", "source_type": "legislation",
             "issuing_authority": "Test Authority", "jurisdiction": "federal",
             "verified_date": "2026-10-21"},
        ],
        "legislation": [
            {"code": "LEG-TEST-S1", "name": "Test Act",
             "issuing_authority": "Test Authority", "jurisdiction": "federal",
             "provision": "Section 1", "subsection": "1(a)",
             "rule_description": "Test provision: deduct test tax on payments.",
             "effective_from": "2020-01-01", "review_status": "verified",
             "source_code": "SRC-TEST", "source_verified_date": "2026-10-21"},
            {"code": "LEG-TEST-S1-AMENDED", "name": "Test Act",
             "issuing_authority": "Test Authority", "jurisdiction": "federal",
             "provision": "Section 1", "subsection": "1(a)",
             "rule_description": "Test provision as amended: higher rate.",
             "effective_from": "2024-07-01", "review_status": "verified",
             "source_code": "SRC-TEST", "source_verified_date": "2026-10-21",
             "amendment_history": "Amended by Test Finance Act 2024"},
        ],
        "evidence": [
            {"code": "EV-TEST-INV", "name": "Test invoice",
             "description": "Test evidence document.", "review_status": "verified"},
        ],
        "procedures": [
            {"code": "PROC-TEST", "name": "Test procedure",
             "category": "calculation", "objective": "Test objective.",
             "steps": ["Step one.", "Step two."], "review_status": "verified"},
        ],
        "calc_tables": [
            {"code": "CALC-TEST-WHT", "version": 1, "name": "Test WHT 5%",
             "kind": "percentage", "tax_category": "withholding_tax",
             "params": {"rate": 0.05, "rate_basis": "gross payment",
                        "rounding": "nearest_rupee",
                        "required_inputs": ["payment_amount"]},
             "legislation_ref": "Test Act s.1(1)(a)",
             "effective_from": "2020-01-01", "effective_to": "2024-06-30",
             "verification_status": "verified"},
            {"code": "CALC-TEST-WHT", "version": 2, "name": "Test WHT 7%",
             "kind": "percentage", "tax_category": "withholding_tax",
             "params": {"rate": 0.07, "rate_basis": "gross payment",
                        "rounding": "nearest_rupee",
                        "required_inputs": ["payment_amount"]},
             "legislation_ref": "Test Act s.1(1)(a) as amended",
             "effective_from": "2024-07-01",
             "verification_status": "verified"},
            {"code": "CALC-TEST-SLAB", "name": "Test slab",
             "kind": "slab", "tax_category": "income_tax",
             "params": {"slabs": [{"upto": 1000, "rate": 0.0},
                                  {"upto": 2000, "rate": 0.10},
                                  {"upto": None, "rate": 0.20}],
                        "rounding": "nearest_rupee",
                        "required_inputs": ["base"]},
             "legislation_ref": "Test Act s.2",
             "effective_from": "2020-01-01", "verification_status": "verified"},
            {"code": "CALC-TEST-DRAFT", "name": "Draft calc",
             "kind": "percentage", "tax_category": "withholding_tax",
             "params": {"rate": 0.99, "rate_basis": "gross",
                        "rounding": "nearest_rupee",
                        "required_inputs": ["payment_amount"]},
             "legislation_ref": "unverified",
             "effective_from": "2020-01-01", "verification_status": "draft"},
            {"code": "CALC-TEST-SCHEDULE", "name": "Test rate schedule",
             "kind": "rate_schedule", "tax_category": "withholding_tax",
             "params": {"rate_basis": "gross payment", "rounding": "nearest_rupee",
                        "base_input": "payment_amount",
                        "input_aliases": {"atl": "atl_status"},
                        "required_inputs": ["payment_amount", "payee_type",
                                            "atl_status"],
                        "rates": [
                            {"payee_type": "company", "atl": "ATL",
                             "rate": 0.05},
                            {"payee_type": "company", "atl": "non_ATL",
                             "rate": 0.10},
                            {"payee_type": "any", "atl": "ATL",
                             "rate": 0.055}]},
             "legislation_ref": "Test Act s.1",
             "effective_from": "2020-01-01", "verification_status": "verified"},
        ],
        "risks": [
            {"code": "RISK-TEST", "title": "Test risk: deduction omitted",
             "description": "Test risk description.", "root_cause": "Test cause",
             "tax_category": "withholding_tax", "jurisdiction": "federal",
             "risk_indicators": ["payment without deduction"],
             "required_information": ["payment records"],
             "followup_action": "Test follow-up.",
             "review_status": "verified"},
        ],
        "rules": [
            {"code": "RULE-TEST-WHT", "title": "Test WHT on payments",
             "tax_category": "withholding_tax", "jurisdiction": "federal",
             "taxpayer_types": ["company", "aop"],
             "triggering_transaction": "A payment for goods or services is made.",
             "transaction_types": ["payment_for_goods", "payment_for_services"],
             "applicability_conditions": {
                 "all": [
                     {"field": "payment_category", "op": "in",
                      "value": ["goods", "services"]},
                     {"field": "payer_is_withholding_agent", "op": "eq",
                      "value": True}]},
             "exclusion_conditions": {
                 "all": [{"field": "exemption_certificate_valid", "op": "eq",
                           "value": True}]},
             "required_inputs": [
                 {"name": "payment_amount", "label": "Payment amount",
                  "data_type": "number", "required": True,
                  "source_hint": "payment voucher"},
                 {"name": "transaction_date", "label": "Payment date",
                  "data_type": "date", "required": True,
                  "source_hint": "payment record"}],
             "decision_logic": {
                 "table": [
                     {"when": {"all": [
                         {"field": "exemption_certificate_valid", "op": "eq",
                          "value": True}]},
                      "then": "No deduction: valid exemption certificate held.",
                      "treatment_code": "exempt"},
                     {"when": {"all": [
                         {"field": "payer_is_withholding_agent", "op": "eq",
                          "value": True}]},
                      "then": "Deduct per CALC-TEST-WHT for the payment date; deposit.",
                      "treatment_code": "deduct"}],
                 "default": "Cannot determine: confirm withholding-agent status."},
             "expected_treatment": "Deduct test WHT and deposit.",
             "calc_codes": ["CALC-TEST-WHT"],
             "evidence_codes": ["EV-TEST-INV"],
             "procedure_codes": ["PROC-TEST"],
             "risk_codes": ["RISK-TEST"],
             "legislation_codes": ["LEG-TEST-S1"],
             "return_fields": ["Test return field 1"],
             "effective_from": "2020-01-01",
             "verification_status": "verified",
             "reviewer": "pytest", "review_date": "2026-10-21"},
            {"code": "RULE-TEST-DRAFT", "title": "Draft rule (unverified)",
             "tax_category": "withholding_tax", "jurisdiction": "federal",
             "taxpayer_types": ["company"],
             "triggering_transaction": "Any payment.",
             "transaction_types": ["payment_for_goods"],
             "applicability_conditions": {
                 "all": [{"field": "payment_category", "op": "eq",
                           "value": "goods"}]},
             "decision_logic": {
                 "table": [{"when": {"all": []},
                            "then": "Draft treatment.",
                            "treatment_code": "draft"}],
                 "default": "n/a"},
             "expected_treatment": "Draft treatment (indicative only).",
             "calc_codes": ["CALC-TEST-DRAFT"],
             "legislation_codes": ["LEG-TEST-S1"],
             "effective_from": "2020-01-01",
             "verification_status": "draft",
             "review_notes": "Rate not verified against any source."},
            {"code": "RULE-TEST-STP-SINDH", "title": "Test Sindh services rule",
             "tax_category": "sales_tax_provincial", "jurisdiction": "sindh",
             "taxpayer_types": ["company"],
             "triggering_transaction": "A service is provided in Sindh.",
             "transaction_types": ["service_provision"],
             "applicability_conditions": {
                 "all": [{"field": "service_province", "op": "eq",
                           "value": "sindh"}]},
             "decision_logic": {
                 "table": [{"when": {"all": []},
                            "then": "Apply Sindh test treatment.",
                            "treatment_code": "sindh"}],
                 "default": "n/a"},
             "expected_treatment": "Sindh test treatment.",
             "legislation_codes": ["LEG-TEST-S1"],
             "effective_from": "2020-01-01",
             "verification_status": "verified",
             "reviewer": "pytest", "review_date": "2026-10-21"},
        ],
        "scenarios": [
            {"code": "SCN-TEST-001", "name": "Test WHT scenario",
             "category": "withholding_tax",
             "description": "Payment for goods by a withholding agent.",
             "trigger_facts": {
                 "all": [
                     {"field": "tax_category", "op": "eq",
                      "value": "withholding_tax"},
                     {"field": "transaction_type", "op": "eq",
                      "value": "payment_for_goods"}]},
             "expected_chain": {
                 "rule_codes": ["RULE-TEST-WHT"],
                 "risk_codes": ["RISK-TEST"],
                 "evidence_codes": ["EV-TEST-INV"],
                 "procedure_codes": ["PROC-TEST"],
                 "calc_codes": ["CALC-TEST-WHT"]},
             "review_status": "verified"},
        ],
    }


@pytest.fixture()
def test_dbs(tmp_path, monkeypatch):
    """Isolated knowledge + workdata DBs seeded with synthetic content."""
    data_dir = tmp_path / "data"
    monkeypatch.setenv("TAXENGINE_DATA_DIR", str(data_dir))
    k = db.get_knowledge_db()
    w = db.get_workdata_db()
    seed_file = tmp_path / "test_seed.json"
    seed_file.write_text(json.dumps(_seed_batch()), encoding="utf-8")
    loader.load_seed_file(seed_file, conn=k)
    yield {"knowledge": k, "workdata": w, "data_dir": data_dir}
    k.close()
    w.close()
