"""Deterministic decision engine — the 14-step tax analysis chain.

No AI, no heuristics: rules are matched by explicit condition trees,
treatments come from explicit decision tables, and every step records what
was evaluated. Missing facts produce "needs_input", never invented values.
Unverified rules are shown but flagged — never presented as authoritative.

The 14 steps:
  1 taxpayer_profile      2 transaction_condition   3 legislation
  4 applicability         5 tax_treatment           6 possible_error
  7 tax_risk              8 evidence_required       9 verification
 10 calculation          11 exceptions             12 adjustment
 13 return_impact        14 followup
"""

from __future__ import annotations

import json
from datetime import date

STEP_NAMES = [
    (1, "taxpayer_profile"),
    (2, "transaction_condition"),
    (3, "legislation"),
    (4, "applicability"),
    (5, "tax_treatment"),
    (6, "possible_error"),
    (7, "tax_risk"),
    (8, "evidence_required"),
    (9, "verification"),
    (10, "calculation"),
    (11, "exceptions"),
    (12, "adjustment"),
    (13, "return_impact"),
    (14, "followup"),
]

_MISSING = object()


def _as_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _coerce_number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def eval_leaf(leaf: dict, facts: dict):
    """Evaluate one condition leaf. Returns True / False / _MISSING."""
    field, op = leaf["field"], leaf["op"]
    actual = facts.get(field, _MISSING)
    if actual is _MISSING:
        # exists / not_exists can still be decided
        if op == "exists":
            return False
        if op == "not_exists":
            return True
        return _MISSING
    want = leaf.get("value")

    if op == "eq":
        return actual == want
    if op == "ne":
        return actual != want
    if op == "in":
        return actual in (want or [])
    if op == "not_in":
        return actual not in (want or [])
    if op == "exists":
        return True
    if op == "not_exists":
        return False
    if op == "contains":
        return str(want) in str(actual)
    if op in ("gt", "gte", "lt", "lte"):
        a, b = _coerce_number(actual), _coerce_number(want)
        if a is None or b is None:
            return _MISSING
        return {"gt": a > b, "gte": a >= b, "lt": a < b, "lte": a <= b}[op]
    if op in ("date_gte", "date_lte", "date_between"):
        a = _as_date(actual)
        if a is None:
            return _MISSING
        if op == "date_between":
            lo, hi = (_as_date(want[0]), _as_date(want[1])) if want else (None, None)
            if lo and a < lo:
                return False
            if hi and a > hi:
                return False
            return True
        b = _as_date(want)
        if b is None:
            return _MISSING
        return (a >= b) if op == "date_gte" else (a <= b)
    return _MISSING


def eval_tree(tree, facts: dict):
    """Evaluate a condition tree. Returns (True|False|None, missing_fields).

    None means "cannot decide — facts missing". missing_fields lists them.
    Empty tree ({} or []) evaluates True.
    """
    if not tree:
        return True, []
    if isinstance(tree, list):
        return (True, []) if not tree else (None, ["<malformed condition>"])
    if "all" in tree or "any" in tree:
        branches = list(tree.get("all", [])) + list(tree.get("any", []))
        results = [eval_tree(b, facts) for b in branches]
        if "all" in tree:
            missing = [m for r, ms in results for m in ms]
            if any(r is False for r, _ in results):
                return False, missing
            if any(r is None for r, _ in results):
                return None, missing
            return True, []
        else:  # any
            if any(r is True for r, _ in results):
                return True, []
            missing = [m for r, ms in results for m in ms]
            if all(r is False for r, _ in results):
                return False, missing
            return None, missing
    # leaf
    result = eval_leaf(tree, facts)
    if result is _MISSING:
        return None, [tree.get("field", "?")]
    return bool(result), []


def _row_dict(row):
    return dict(row)


def _json(value, default):
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return default
    return value


def _in_effect(row, on_date: date | None) -> bool:
    if on_date is None:
        return True
    eff_from = _as_date(row["effective_from"])
    eff_to = _as_date(row["effective_to"])
    if eff_from and on_date < eff_from:
        return False
    if eff_to and on_date > eff_to:
        return False
    return True


def match_rules(conn, facts: dict) -> dict:
    """Match facts against the rule library.

    Returns dict with keys:
      applicable  : rules whose conditions hold
      excluded    : rules whose conditions fail (with reason)
      needs_info  : rules that cannot be decided (with missing fields)
      out_of_scope: rules filtered out by category/jurisdiction/type/date
      unverified  : subset of applicable that are not 'verified'
    Each entry: {rule row dict, reasons}.
    """
    tx_date = _as_date(facts.get("transaction_date"))
    want_cat = facts.get("tax_category")
    want_jur = facts.get("jurisdiction")
    want_ttype = facts.get("transaction_type")
    want_tptype = facts.get("taxpayer_type")

    out = {"applicable": [], "excluded": [], "needs_info": [],
           "out_of_scope": [], "unverified": []}

    for r in conn.execute("SELECT * FROM tax_rules ORDER BY code, version"):
        row = _row_dict(r)
        reasons = []
        # --- scope filters (never "applicable", just not in scope) ---
        if want_cat and row["tax_category"] != want_cat:
            continue
        if want_jur and row["jurisdiction"] not in (want_jur, "federal") \
                and not (want_jur == "federal"):
            # federal rules can apply alongside provincial ones; provincial
            # rules only apply in their own jurisdiction
            if row["jurisdiction"] != want_jur:
                out["out_of_scope"].append(
                    {"rule": row, "reason": f"jurisdiction {row['jurisdiction']} != {want_jur}"})
                continue
        if want_tptype:
            tps = _json(row["taxpayer_types"], [])
            if tps and want_tptype not in tps:
                out["out_of_scope"].append(
                    {"rule": row, "reason": f"taxpayer type {want_tptype} not in {tps}"})
                continue
        if want_ttype:
            tts = _json(row["transaction_types"], [])
            if tts and want_ttype not in tts:
                out["out_of_scope"].append(
                    {"rule": row, "reason": f"transaction type {want_ttype} not in {tts}"})
                continue
        if not _in_effect(row, tx_date):
            out["out_of_scope"].append(
                {"rule": row,
                 "reason": f"not in effect on {tx_date} "
                           f"(effective {row['effective_from']} to {row['effective_to'] or 'present'})"})
            continue

        # --- applicability conditions ---
        cond = _json(row["applicability_conditions"], {})
        ok, missing = eval_tree(cond, facts)
        if ok is False:
            out["excluded"].append(
                {"rule": row, "reason": "applicability conditions not met"})
            continue
        # --- exclusion conditions (empty = no exclusions) ---
        excl = _json(row["exclusion_conditions"], [])
        if excl:
            eok, emissing = eval_tree(excl, facts)
        else:
            eok, emissing = False, []
        if eok is True:
            out["excluded"].append(
                {"rule": row, "reason": "an exclusion condition applies"})
            continue
        if ok is None or eok is None:
            out["needs_info"].append(
                {"rule": row,
                 "missing_fields": sorted(set(missing) | set(emissing))})
            continue
        entry = {"rule": row, "reason": "all applicability conditions met"}
        out["applicable"].append(entry)
        if row["verification_status"] != "verified":
            out["unverified"].append(
                {"rule": row,
                 "reason": f"rule status is '{row['verification_status']}' — not verified; "
                           "treat as indicative only"})
    return out


def run_decision_table(rule: dict, facts: dict) -> dict:
    """Run a rule's explicit decision table against facts.

    First branch whose condition is True wins. Branches that cannot be
    decided (missing facts) are skipped but reported; the default applies
    only when every branch is decidably False.
    """
    logic = _json(rule.get("decision_logic"), {})
    table = logic.get("table", []) if isinstance(logic, dict) else []
    undecided = []
    for i, branch in enumerate(table):
        ok, missing = eval_tree(branch.get("when", {}), facts)
        if ok is True:
            return {"matched": True, "branch_index": i,
                    "then": branch.get("then", ""),
                    "treatment_code": branch.get("treatment_code", ""),
                    "missing_fields": []}
        if ok is None:
            undecided.append((i, missing))
    if undecided:
        i, missing = undecided[0]
        return {"matched": False, "branch_index": i,
                "then": "",
                "treatment_code": "",
                "missing_fields": sorted(set(missing)),
                "note": f"branch {i} cannot be decided — missing facts; "
                        "no treatment determined"}
    return {"matched": False, "branch_index": None,
            "then": logic.get("default", "") if isinstance(logic, dict) else "",
            "treatment_code": "default",
            "missing_fields": [],
            "note": "no branch matched; default applies"}


def _linked(conn, link_table, id_col, rule_id, target_table):
    rows = conn.execute(
        f"""SELECT t.* FROM {target_table} t
            JOIN {link_table} l ON l.{id_col} = t.id
            WHERE l.rule_id = ?""", (rule_id,)).fetchall()
    return [_row_dict(r) for r in rows]


def analyze(conn, profile: dict, facts: dict, calc_runner=None) -> list:
    """Run the full 14-step chain. Returns a list of step dicts.

    profile: taxpayer profile dict (may be {} for a standalone lookup).
    facts:   transaction/tax-condition facts. Must include transaction_date
             (or tax_year) for date-scoped rules; missing facts are reported,
             never invented.
    calc_runner: optional callable(calc_code, inputs) -> calc result dict,
             used at step 10. If None, step 10 lists required inputs only.
    """
    facts = dict(facts)
    # fold profile context into facts where the fact is absent
    for key in ("taxpayer_type", "jurisdiction", "province", "tax_year",
                "resident_status"):
        if key not in facts and profile.get(key):
            facts[key] = profile[key]
    if "jurisdiction" not in facts and facts.get("province"):
        facts["jurisdiction"] = facts["province"]

    matched = match_rules(conn, facts)
    applicable = matched["applicable"]

    steps = []

    def add(no, name, finding, detail=None, confidence="info"):
        steps.append({"step_no": no, "step_name": name, "finding": finding,
                      "detail": detail or {}, "confidence": confidence})

    # 1 — taxpayer profile
    prof_summary = {k: profile.get(k) for k in
                    ("display_name", "taxpayer_type", "resident_status",
                     "tax_year", "province", "industry",
                     "federal_registered", "sales_tax_registered") if profile.get(k) is not None}
    add(1, "taxpayer_profile",
        (f"Profile '{profile.get('display_name', 'unspecified')}' "
         f"({profile.get('taxpayer_type', '?')}, {profile.get('province', '?')}, "
         f"TY {profile.get('tax_year', '?')})" if profile else
         "No taxpayer profile supplied — rules matched on transaction facts only."),
        {"profile": prof_summary},
        "info" if profile else "needs_input")

    # 2 — transaction / tax condition
    add(2, "transaction_condition",
        f"Transaction: {facts.get('transaction_type', 'unspecified')} "
        f"on {facts.get('transaction_date', 'date not given')} "
        f"({facts.get('tax_category', 'no tax category given')}).",
        {"facts": facts},
        "info" if facts.get("transaction_date") else "needs_input")

    # 3 — legislation
    leg_rows = []
    for entry in applicable:
        for leg in _linked(conn, "rule_legislation", "legislation_id",
                           entry["rule"]["id"], "legislation"):
            leg_rows.append(
                {"rule_code": entry["rule"]["code"],
                 "provision": f"{leg['name']} — {leg['provision']}"
                              f"{(' ' + leg['subsection']) if leg['subsection'] else ''}",
                 "effective": f"{leg['effective_from']} to {leg['effective_to'] or 'present'}",
                 "status": leg["review_status"]})
    add(3, "legislation",
        f"{len(leg_rows)} legislative provision(s) linked to applicable rules."
        if leg_rows else "No legislation linked to applicable rules.",
        {"provisions": leg_rows})

    # 4 — applicability
    app_detail = {
        "applicable": [e["rule"]["code"] for e in applicable],
        "excluded": [{"code": e["rule"]["code"], "reason": e["reason"]}
                     for e in matched["excluded"]],
        "needs_info": [{"code": e["rule"]["code"],
                        "missing_fields": e["missing_fields"]}
                       for e in matched["needs_info"]],
        "unverified": [e["rule"]["code"] for e in matched["unverified"]],
    }
    conf = "info"
    if matched["needs_info"]:
        conf = "needs_input"
    elif matched["unverified"]:
        conf = "unverified_rule"
    add(4, "applicability",
        (f"{len(applicable)} rule(s) applicable, {len(matched['excluded'])} excluded, "
         f"{len(matched['needs_info'])} need more information."),
        app_detail, conf)

    # 5 — tax treatment via decision tables
    treatments = []
    for entry in applicable:
        rule = entry["rule"]
        dt = run_decision_table(rule, facts)
        treatments.append({"rule_code": rule["code"],
                           "rule_version": rule["version"],
                           "treatment": dt["then"],
                           "treatment_code": dt["treatment_code"],
                           "verified": rule["verification_status"] == "verified",
                           "missing_fields": dt["missing_fields"]})
    add(5, "tax_treatment",
        ("; ".join(t["treatment"] for t in treatments if t["treatment"])
         or "No treatment determined — see missing information."),
        {"treatments": treatments},
        "needs_input" if any(t["missing_fields"] for t in treatments) else
        ("unverified_rule" if any(not t["verified"] for t in treatments) else "info"))

    # 6 — possible errors: decision-table branches NOT taken + scenario hints
    errors = []
    for entry in applicable:
        rule = entry["rule"]
        logic = _json(rule.get("decision_logic"), {})
        dt = run_decision_table(rule, facts)
        for i, branch in enumerate(logic.get("table", [])):
            if dt.get("branch_index") != i:
                errors.append(
                    {"rule_code": rule["code"],
                     "possible_error": f"Branch not taken: {branch.get('then', '')}",
                     "treatment_code": branch.get("treatment_code", "")})
    add(6, "possible_error",
        (f"{len(errors)} alternative outcome(s) identified — each is a "
         "candidate error if the facts were different or misreported."
         if errors else "No alternative branches identified."),
        {"possible_errors": errors})

    # 7 — tax risks
    risks = []
    for entry in applicable:
        for rk in _linked(conn, "rule_risks", "risk_id", entry["rule"]["id"], "tax_risks"):
            risks.append({"rule_code": entry["rule"]["code"],
                          "risk_code": rk["code"], "title": rk["title"],
                          "description": rk["description"],
                          "indicators": _json(rk["risk_indicators"], []),
                          "exposure_note": rk.get("exposure_note"),
                          "followup_action": rk.get("followup_action")})
    # de-duplicate by risk code
    seen, uniq = set(), []
    for r in risks:
        if r["risk_code"] not in seen:
            seen.add(r["risk_code"])
            uniq.append(r)
    add(7, "tax_risk",
        f"{len(uniq)} tax risk(s) linked to applicable rules." if uniq
        else "No risks linked to applicable rules.",
        {"risks": uniq})

    # 8 — evidence required
    ev_rows = []
    for entry in applicable:
        for ev in _linked(conn, "rule_evidence", "evidence_id",
                          entry["rule"]["id"], "evidence"):
            ev_rows.append({"rule_code": entry["rule"]["code"],
                            "evidence_code": ev["code"], "name": ev["name"],
                            "expected_information": _json(ev["expected_information"], []),
                            "common_discrepancies": _json(ev["common_discrepancies"], [])})
    seen, uniq_ev = set(), []
    for e in ev_rows:
        if e["evidence_code"] not in seen:
            seen.add(e["evidence_code"])
            uniq_ev.append(e)
    add(8, "evidence_required",
        f"{len(uniq_ev)} evidence type(s) required across applicable rules."
        if uniq_ev else "No evidence requirements linked.",
        {"evidence": uniq_ev},
        "info" if uniq_ev else "needs_input")

    # 9 — verification procedures
    procs = []
    for entry in applicable:
        for pr in _linked(conn, "rule_procedures", "procedure_id",
                          entry["rule"]["id"], "procedures"):
            procs.append({"rule_code": entry["rule"]["code"],
                          "procedure_code": pr["code"], "name": pr["name"],
                          "category": pr["category"], "objective": pr["objective"],
                          "steps": _json(pr["steps"], []),
                          "expected_result": pr.get("expected_result"),
                          "exception_conditions": _json(pr["exception_conditions"], [])})
    seen, uniq_pr = set(), []
    for p in procs:
        if p["procedure_code"] not in seen:
            seen.add(p["procedure_code"])
            uniq_pr.append(p)
    add(9, "verification",
        f"{len(uniq_pr)} verification procedure(s) to perform." if uniq_pr
        else "No verification procedures linked.",
        {"procedures": uniq_pr})

    # 10 — calculation
    calcs = []
    for entry in applicable:
        rule = entry["rule"]
        for cc in _linked(conn, "rule_calcs", "calc_id", entry["rule"]["id"], "calc_tables"):
            item = {"rule_code": rule["code"], "calc_code": cc["code"],
                    "calc_version": cc["version"],
                    "verified": cc["verification_status"] == "verified"}
            if calc_runner is not None:
                cparams = _json(cc.get("params"), {})
                want = set(cparams.get("required_inputs", [])) | {
                    i["name"] for i in _json(rule.get("required_inputs"), [])
                    if i.get("required")}
                inputs = {k: {"value": facts[k], "source": "assessment facts"}
                          for k in want
                          if k in facts and facts[k] not in (None, "")}
                try:
                    res = calc_runner(cc["code"], inputs,
                                      on_date=facts.get("transaction_date"))
                except Exception as exc:  # never crash the chain
                    res = {"validation_status": "error", "error": str(exc)}
                item["result"] = res
            else:
                item["required_inputs"] = [i["name"] for i in
                                           _json(rule.get("required_inputs"), [])]
            calcs.append(item)
    add(10, "calculation",
        (f"{len(calcs)} calculation(s) identified."
         if calcs else "No calculations linked to applicable rules."),
        {"calculations": calcs},
        "needs_input" if any(
            isinstance(c.get("result"), dict) and
            c["result"].get("validation_status") == "incomplete_missing_inputs"
            for c in calcs) else "info")

    # 11 — exceptions
    exceptions = []
    for entry in applicable:
        rule = entry["rule"]
        for exc in _json(rule.get("exceptions"), []):
            cond = exc.get("condition", {})
            ok, _ = eval_tree(cond, facts)
            if ok is True:
                exceptions.append({"rule_code": rule["code"],
                                   "exception": exc.get("description", ""),
                                   "action": exc.get("action", "")})
    add(11, "exceptions",
        (f"{len(exceptions)} exception(s) triggered by the facts."
         if exceptions else "No exceptions triggered by the facts."),
        {"exceptions": exceptions},
        "exception_flagged" if exceptions else "info")

    # 12 — potential adjustments
    adjustments = []
    for e in exceptions:
        adjustments.append({"rule_code": e["rule_code"],
                            "potential_adjustment": e["action"],
                            "basis": e["exception"]})
    for entry in applicable:
        rule = entry["rule"]
        if rule.get("consequences"):
            adjustments.append({"rule_code": rule["code"],
                                "potential_adjustment": rule["consequences"],
                                "basis": "rule consequences"})
    add(12, "adjustment",
        (f"{len(adjustments)} potential adjustment(s)/consequence(s) noted."
         if adjustments else "No adjustments indicated."),
        {"adjustments": adjustments})

    # 13 — return / compliance impact
    ret_fields = []
    for entry in applicable:
        for f in _json(entry["rule"].get("return_fields"), []):
            ret_fields.append({"rule_code": entry["rule"]["code"], "field": f})
    add(13, "return_impact",
        (f"{len(ret_fields)} return field(s)/statement(s) affected."
         if ret_fields else "No return impact mapped."),
        {"return_fields": ret_fields})

    # 14 — follow-up
    followups = []
    for r in uniq:
        if r.get("followup_action"):
            followups.append({"risk_code": r["risk_code"],
                              "action": r["followup_action"]})
    for p in uniq_pr:
        if p.get("followup_procedure"):
            followups.append({"procedure_code": p["procedure_code"],
                              "action": p.get("followup_procedure")})
    if matched["needs_info"]:
        followups.append({"action": "Provide the missing facts listed at step 4, then re-run the analysis."})
    if matched["unverified"]:
        followups.append({"action": "Unverified rules were used — confirm against the authoritative source before relying on the treatment."})
    add(14, "followup",
        f"{len(followups)} follow-up action(s)." if followups else "No follow-up actions.",
        {"followups": followups})

    return steps
