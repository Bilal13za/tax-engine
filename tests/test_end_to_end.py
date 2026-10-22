"""§16 end-to-end: one complete worked example —

transaction entry -> rule matching -> treatment -> calculation ->
evidence verification -> exception handling -> reconciliation -> export.

Uses the synthetic TEST content so the test asserts engine behaviour,
not tax law.
"""

import json

from taxengine import calc as calcmod
from taxengine import decision, export as exportmod, reconcile


def test_end_to_end_withholding_scenario(test_dbs, tmp_path):
    k, w = test_dbs["knowledge"], test_dbs["workdata"]

    # 1. taxpayer profile
    pid = w.execute(
        """INSERT INTO taxpayer_profiles(profile_code, display_name,
           taxpayer_type, tax_year, province, federal_registered)
           VALUES (?,?,?,?,?,?)""",
        ("TEST-CO-2026", "Test Company", "company", "2026", "punjab", 1)
    ).lastrowid
    profile = dict(w.execute("SELECT * FROM taxpayer_profiles WHERE id=?",
                             (pid,)).fetchone())

    # 2. transaction facts
    facts = {"tax_category": "withholding_tax",
             "transaction_type": "payment_for_goods",
             "transaction_date": "2025-02-10",
             "payment_category": "goods", "payment_amount": 500000,
             "payer_is_withholding_agent": True,
             "exemption_certificate_valid": False}

    # 3-14. run the chain
    steps = decision.analyze(
        k, profile, facts,
        calc_runner=lambda code, inputs, on_date=None:
            calcmod.run_calculation(k, code, inputs, on_date=on_date))
    by_no = {s["step_no"]: s for s in steps}

    # applicability: rule matched, treatment = deduct branch
    assert "RULE-TEST-WHT" in by_no[4]["detail"]["applicable"]
    t5 = [t for t in by_no[5]["detail"]["treatments"]
          if t["rule_code"] == "RULE-TEST-WHT"][0]
    assert t5["treatment_code"] == "deduct"

    # calculation: 500,000 x 7% (v2 in effect 2025) = 35,000
    calc_item = [c for c in by_no[10]["detail"]["calculations"]
                 if c["calc_code"] == "CALC-TEST-WHT"][0]
    assert calc_item["result"]["result"] == 35000.0
    assert calc_item["result"]["validation_status"] == "complete"

    # risk + evidence + procedure linked
    assert any(r["risk_code"] == "RISK-TEST"
               for r in by_no[7]["detail"]["risks"])
    assert any(e["evidence_code"] == "EV-TEST-INV"
               for e in by_no[8]["detail"]["evidence"])
    assert any(p["procedure_code"] == "PROC-TEST"
               for p in by_no[9]["detail"]["procedures"])

    # return impact mapped
    assert by_no[13]["detail"]["return_fields"]

    # persist assessment + steps
    aid = w.execute(
        "INSERT INTO assessments(profile_id, title, scenario_code, facts)"
        " VALUES (?,?,?,?)",
        (pid, "E2E WHT payment", "SCN-TEST-001", json.dumps(facts))).lastrowid
    for s in steps:
        w.execute(
            "INSERT INTO assessment_steps(assessment_id, step_no, step_name,"
            " rule_code, finding, detail, confidence) VALUES (?,?,?,?,?,?,?)",
            (aid, s["step_no"], s["step_name"], "RULE-TEST-WHT",
             s["finding"], json.dumps(s["detail"]), s["confidence"]))
    w.commit()

    # evidence verification: mark invoice received but discrepant
    w.execute("INSERT INTO evidence_tracker(assessment_id, evidence_code,"
              " requested, received, verification_done, result, exceptions)"
              " VALUES (?,?,?,?,?,?,?)",
              (aid, "EV-TEST-INV", 1, 1, 1, "discrepancy_found",
               "invoice amount differs from payment record"))

    # reconciliation: deducted vs deposited -> difference flagged
    rec = reconcile.compute([
        {"label": "WHT deducted per books", "amount_a": 35000,
         "amount_b": 35000, "source_a": "ledger", "source_b": "calc",
         "note": ""},
        {"label": "WHT deposited per challan", "amount_a": 30000,
         "amount_b": 35000, "source_a": "challan", "source_b": "calc",
         "note": "short deposit"},
    ])
    assert rec["total_difference"] == -5000
    w.execute("INSERT INTO reconciliations(assessment_id, template_code,"
              " title, lines, total_difference, conclusion)"
              " VALUES (?,?,?,?,?,?)",
              (aid, "RECON-PAYMENTS", "WHT deposited vs deducted",
               json.dumps(rec["lines"]), rec["total_difference"],
               rec["conclusion"]))
    w.commit()

    # exception handling: record the short deposit as an assessment-level note
    # (via evidence tracker exception already stored above)
    row = w.execute("SELECT exceptions FROM evidence_tracker WHERE "
                    "assessment_id=?", (aid,)).fetchone()
    assert "differs" in row["exceptions"]

    # export the full package
    xlsx = exportmod.export_assessment_xlsx(
        k, w, aid, tmp_path / "e2e.xlsx")
    assert xlsx.exists() and xlsx.stat().st_size > 0
    csvp = exportmod.export_rules_csv(k, tmp_path / "e2e_rules.csv")
    assert csvp.exists()
