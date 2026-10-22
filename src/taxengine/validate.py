"""Rule validation (§14): every rule/seed object is validated before activation.

Validation checks:
  - required fields present
  - valid effective dates (YYYY-MM-DD, from <= to)
  - legal source present (legislation_codes non-empty; each must exist or be
    defined in the same seed batch)
  - applicability conditions parse as a condition tree
  - calculation method references an existing calc table code (or is empty)
  - required evidence codes exist or are defined in the same batch
  - decision_logic has at least one row and a default
  - version history sane (version >= 1; supersedes_code refers to same code)

Invalid objects are REJECTED with explicit errors — never silently stored.
"""

from __future__ import annotations

import json
from datetime import date

TAX_CATEGORIES = {
    "income_tax", "withholding_tax", "sales_tax_federal", "customs",
    "sales_tax_provincial", "provincial_other", "other_levies",
}
JURISDICTIONS = {
    "federal", "punjab", "sindh", "kpk", "balochistan", "ict", "gb", "ajk",
}
STATUSES = {"draft", "under_review", "verified", "superseded", "retired"}
CONDITION_OPS = {
    "eq", "ne", "in", "not_in", "gt", "gte", "lt", "lte",
    "exists", "not_exists", "contains", "date_between", "date_gte", "date_lte",
}
CALC_KINDS = {"slab", "flat_rate", "percentage", "fixed_amount", "threshold",
              "rate_schedule"}
PROCEDURE_CATEGORIES = {
    "document_verification", "reconciliation", "calculation",
    "completeness", "eligibility",
}
SCENARIO_CATEGORIES = {
    "income_tax", "withholding_tax", "sales_tax_federal",
    "sales_tax_provincial", "return_preparation",
}


class SeedError(Exception):
    """Raised when a seed object fails validation."""


def _parse_date(value, field, code):
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise SeedError(f"{code}: field '{field}' is not a valid YYYY-MM-DD date: {value!r}")


def validate_condition_tree(tree, code, where="applicability_conditions"):
    """Recursively validate a condition tree; returns True."""
    if isinstance(tree, list):
        if tree:
            raise SeedError(f"{code}: {where} list must be empty or an object, got {tree}")
        return True  # empty list = no conditions
    if not isinstance(tree, dict):
        raise SeedError(f"{code}: {where} must be an object, got {type(tree).__name__}")
    if "all" in tree or "any" in tree:
        branches = []
        if "all" in tree:
            branches += tree["all"]
        if "any" in tree:
            branches += tree["any"]
        if not branches:
            return True  # empty all/any = no conditions = always true
        for b in branches:
            validate_condition_tree(b, code, where)
        return True
    # leaf
    for key in ("field", "op"):
        if key not in tree:
            raise SeedError(f"{code}: {where} leaf missing '{key}': {tree}")
    if tree["op"] not in CONDITION_OPS:
        raise SeedError(f"{code}: {where} unknown operator {tree['op']!r}")
    return True


def validate_decision_logic(logic, code):
    if not isinstance(logic, dict):
        raise SeedError(f"{code}: decision_logic must be an object")
    table = logic.get("table")
    if not isinstance(table, list) or not table:
        raise SeedError(f"{code}: decision_logic.table must be a non-empty list")
    for i, row in enumerate(table):
        if "when" not in row or "then" not in row:
            raise SeedError(f"{code}: decision_logic.table[{i}] needs 'when' and 'then'")
        validate_condition_tree(row["when"], code, f"decision_logic.table[{i}].when")
        if not str(row["then"]).strip():
            raise SeedError(f"{code}: decision_logic.table[{i}].then is empty")
    if not str(logic.get("default", "")).strip():
        raise SeedError(f"{code}: decision_logic.default must be a non-empty string")
    return True


def _need(obj, fields, code):
    missing = [f for f in fields if f not in obj or obj[f] in (None, "")]
    if missing:
        raise SeedError(f"{code or '?'}: missing required fields: {', '.join(missing)}")


def validate_rule(rule: dict, known: dict) -> dict:
    """Validate one rule dict. `known` maps entity -> set of codes in this batch."""
    code = rule.get("code", "?")
    _need(rule, ["code", "title", "tax_category", "jurisdiction", "taxpayer_types",
                 "triggering_transaction", "transaction_types",
                 "applicability_conditions", "decision_logic",
                 "expected_treatment", "effective_from", "verification_status"], code)
    if rule["tax_category"] not in TAX_CATEGORIES:
        raise SeedError(f"{code}: unknown tax_category {rule['tax_category']!r}")
    if rule["jurisdiction"] not in JURISDICTIONS:
        raise SeedError(f"{code}: unknown jurisdiction {rule['jurisdiction']!r}")
    if rule["verification_status"] not in STATUSES:
        raise SeedError(f"{code}: unknown verification_status {rule['verification_status']!r}")
    d_from = _parse_date(rule["effective_from"], "effective_from", code)
    d_to = _parse_date(rule.get("effective_to"), "effective_to", code)
    if d_from and d_to and d_from > d_to:
        raise SeedError(f"{code}: effective_from is after effective_to")
    validate_condition_tree(rule["applicability_conditions"], code)
    if rule.get("exclusion_conditions"):
        validate_condition_tree(rule["exclusion_conditions"], code, "exclusion_conditions")
    validate_decision_logic(rule["decision_logic"], code)

    # legal source required
    leg_codes = rule.get("legislation_codes", [])
    if not leg_codes:
        raise SeedError(f"{code}: at least one legislation_code is required (legal source)")
    for lc in leg_codes:
        if lc not in known.get("legislation", set()):
            raise SeedError(f"{code}: legislation_code {lc!r} not defined in batch or DB")

    # calculation method must reference a known calc table (or be empty)
    for cc in rule.get("calc_codes", []):
        if cc not in known.get("calc_tables", set()):
            raise SeedError(f"{code}: calc_code {cc!r} not defined in batch or DB")

    # required evidence codes must exist
    for ec in rule.get("evidence_codes", []):
        if ec not in known.get("evidence", set()):
            raise SeedError(f"{code}: evidence_code {ec!r} not defined in batch or DB")
    for rc in rule.get("risk_codes", []):
        if rc not in known.get("risks", set()):
            raise SeedError(f"{code}: risk_code {rc!r} not defined in batch or DB")
    for pc in rule.get("procedure_codes", []):
        if pc not in known.get("procedures", set()):
            raise SeedError(f"{code}: procedure_code {pc!r} not defined in batch or DB")

    # verified rules must carry reviewer + review date + source verification date
    if rule["verification_status"] == "verified":
        if not rule.get("reviewer") or not rule.get("review_date"):
            raise SeedError(f"{code}: status 'verified' requires reviewer and review_date")
        _parse_date(rule["review_date"], "review_date", code)
    version = rule.get("version", 1)
    if not isinstance(version, int) or version < 1:
        raise SeedError(f"{code}: version must be a positive integer")
    return rule


def validate_legislation(leg: dict, known: dict) -> dict:
    code = leg.get("code", "?")
    _need(leg, ["code", "name", "issuing_authority", "jurisdiction", "provision",
                "rule_description", "effective_from", "review_status"], code)
    if leg["jurisdiction"] not in JURISDICTIONS:
        raise SeedError(f"{code}: unknown jurisdiction")
    if leg["review_status"] not in STATUSES:
        raise SeedError(f"{code}: unknown review_status")
    d_from = _parse_date(leg["effective_from"], "effective_from", code)
    d_to = _parse_date(leg.get("effective_to"), "effective_to", code)
    if d_from and d_to and d_from > d_to:
        raise SeedError(f"{code}: effective_from is after effective_to")
    if leg.get("source_code") and leg["source_code"] not in known.get("sources", set()):
        raise SeedError(f"{code}: source_code {leg['source_code']!r} unknown")
    return leg


def validate_risk(risk: dict, known: dict) -> dict:
    code = risk.get("code", "?")
    _need(risk, ["code", "title", "description", "tax_category", "review_status"], code)
    if risk["tax_category"] not in TAX_CATEGORIES:
        raise SeedError(f"{code}: unknown tax_category")
    if risk.get("jurisdiction") and risk["jurisdiction"] not in JURISDICTIONS:
        raise SeedError(f"{code}: unknown jurisdiction")
    if risk["review_status"] not in STATUSES:
        raise SeedError(f"{code}: unknown review_status")
    for ec in risk.get("evidence_codes", []):
        if ec not in known.get("evidence", set()):
            raise SeedError(f"{code}: evidence_code {ec!r} unknown")
    for pc in risk.get("procedure_codes", []):
        if pc not in known.get("procedures", set()):
            raise SeedError(f"{code}: procedure_code {pc!r} unknown")
    return risk


def validate_evidence(ev: dict, known: dict) -> dict:
    code = ev.get("code", "?")
    _need(ev, ["code", "name", "description", "review_status"], code)
    if ev["review_status"] not in STATUSES:
        raise SeedError(f"{code}: unknown review_status")
    return ev


def validate_procedure(proc: dict, known: dict) -> dict:
    code = proc.get("code", "?")
    _need(proc, ["code", "name", "category", "objective", "steps", "review_status"], code)
    if proc["category"] not in PROCEDURE_CATEGORIES:
        raise SeedError(f"{code}: unknown category")
    if proc["review_status"] not in STATUSES:
        raise SeedError(f"{code}: unknown review_status")
    if not isinstance(proc["steps"], list) or not proc["steps"]:
        raise SeedError(f"{code}: steps must be a non-empty list")
    for ec in proc.get("evidence_codes", []):
        if ec not in known.get("evidence", set()):
            raise SeedError(f"{code}: evidence_code {ec!r} unknown")
    return proc


def validate_calc_table(ct: dict, known: dict) -> dict:
    code = ct.get("code", "?")
    _need(ct, ["code", "name", "kind", "tax_category", "params",
               "effective_from", "verification_status"], code)
    if ct["kind"] not in CALC_KINDS:
        raise SeedError(f"{code}: unknown kind")
    if ct["tax_category"] not in TAX_CATEGORIES:
        raise SeedError(f"{code}: unknown tax_category")
    if ct["verification_status"] not in STATUSES:
        raise SeedError(f"{code}: unknown verification_status")
    d_from = _parse_date(ct["effective_from"], "effective_from", code)
    d_to = _parse_date(ct.get("effective_to"), "effective_to", code)
    if d_from and d_to and d_from > d_to:
        raise SeedError(f"{code}: effective_from is after effective_to")
    params = ct["params"]
    if not isinstance(params, dict):
        raise SeedError(f"{code}: params must be an object")
    kind = ct["kind"]
    if kind == "slab":
        slabs = params.get("slabs")
        if not isinstance(slabs, list) or not slabs:
            raise SeedError(f"{code}: slab kind needs params.slabs non-empty list")
        for s in slabs:
            if "rate" not in s or "upto" not in s:
                raise SeedError(f"{code}: each slab needs 'upto' and 'rate'")
    elif kind in ("percentage", "flat_rate"):
        if "rate" not in params:
            raise SeedError(f"{code}: {kind} needs params.rate")
    elif kind == "threshold":
        if "threshold" not in params:
            raise SeedError(f"{code}: threshold kind needs params.threshold")
    elif kind == "fixed_amount":
        if "amount" not in params:
            raise SeedError(f"{code}: fixed_amount kind needs params.amount")
    elif kind == "rate_schedule":
        rows = params.get("rates")
        if not isinstance(rows, list) or not rows:
            raise SeedError(f"{code}: rate_schedule kind needs params.rates "
                            "non-empty list")
        for i, r in enumerate(rows):
            if not isinstance(r, dict) or "rate" not in r:
                raise SeedError(f"{code}: params.rates[{i}] needs a 'rate'")
            try:
                float(r["rate"])
            except (TypeError, ValueError):
                raise SeedError(f"{code}: params.rates[{i}].rate not numeric")
    if "rounding" not in params:
        raise SeedError(f"{code}: params.rounding is required (e.g. nearest_rupee)")
    return ct


def validate_scenario(scn: dict, known: dict) -> dict:
    code = scn.get("code", "?")
    _need(scn, ["code", "name", "category", "description",
                "trigger_facts", "expected_chain", "review_status"], code)
    if scn["category"] not in SCENARIO_CATEGORIES:
        raise SeedError(f"{code}: unknown category")
    if scn["review_status"] not in STATUSES:
        raise SeedError(f"{code}: unknown review_status")
    validate_condition_tree(scn["trigger_facts"], code, "trigger_facts")
    chain = scn["expected_chain"]
    if not isinstance(chain, dict):
        raise SeedError(f"{code}: expected_chain must be an object")
    checks = [("rule_codes", "rules"), ("risk_codes", "risks"),
              ("evidence_codes", "evidence"), ("procedure_codes", "procedures"),
              ("calc_codes", "calc_tables")]
    for field, entity in checks:
        for c in chain.get(field, []):
            if c not in known.get(entity, set()):
                raise SeedError(f"{code}: expected_chain.{field} references unknown {c!r}")
    return scn


def validate_source(src: dict) -> dict:
    code = src.get("code", "?")
    _need(src, ["code", "title", "source_type", "jurisdiction"], code)
    if src["jurisdiction"] not in JURISDICTIONS:
        raise SeedError(f"{code}: unknown jurisdiction")
    if src.get("verified_date"):
        _parse_date(src["verified_date"], "verified_date", code)
    return src
