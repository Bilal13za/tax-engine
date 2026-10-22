"""Deterministic tax calculation engine (§11).

Rates, slabs, thresholds and methods live in the calc_tables database table —
never in code. Every run records: inputs + their sources, the applicable
rule/version, legal provision, effective date, calculation steps, rounding
method, result and validation status.

Missing required inputs -> 'incomplete_missing_inputs' (never invented).
Unverified calc table   -> 'unverified_rule' (computed but flagged).
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation


def _as_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _dec(value) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise CalculationError(f"non-numeric input value: {value!r}")


class CalculationError(Exception):
    """Raised for deterministic calculation failures (bad params, bad inputs)."""


def _json(value, default):
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return default
    return value


def select_calc_table(conn, code: str, on_date=None, tax_year=None):
    """Select the calc-table version in effect for the given date/tax year.

    Never uses "the latest" for an earlier period: selection is strictly
    date-scoped. Returns the row dict or None.
    """
    d = _as_date(on_date)
    rows = conn.execute(
        "SELECT * FROM calc_tables WHERE code = ? ORDER BY version DESC", (code,)
    ).fetchall()
    candidates = []
    for r in rows:
        row = dict(r)
        eff_from = _as_date(row["effective_from"])
        eff_to = _as_date(row["effective_to"])
        if d is not None:
            if eff_from and d < eff_from:
                continue
            if eff_to and d > eff_to:
                continue
        if tax_year and row.get("tax_year") and row["tax_year"] != str(tax_year):
            continue
        candidates.append(row)
    if not candidates:
        return None
    # Prefer verified, then highest version (within the in-effect set only).
    candidates.sort(key=lambda r: (r["verification_status"] == "verified",
                                   r["version"]), reverse=True)
    return candidates[0]


def _round(value: Decimal, method: str) -> Decimal:
    if method == "nearest_rupee":
        return value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    if method == "exact":
        return value
    if method == "nearest_thousand":
        return (value / 1000).quantize(Decimal("1"),
                                       rounding=ROUND_HALF_UP) * 1000
    raise CalculationError(f"unknown rounding method: {method!r}")


def _base_name(params: dict, required: list) -> str:
    """Which input is the calculation base.

    Explicit params['base_input'] wins; otherwise, when there is exactly one
    required input it is the base. Ambiguity is an error, never a guess.
    """
    name = params.get("base_input")
    if name:
        if name not in required:
            raise CalculationError(
                f"base_input '{name}' not among required inputs {required}")
        return name
    if len(required) == 1:
        return required[0]
    raise CalculationError(
        f"ambiguous calculation base: required inputs are {required}; "
        "set params.base_input to name the base")


def run_calculation(conn, calc_code: str, inputs: dict, on_date=None,
                    tax_year=None) -> dict:
    """Run one calculation. `inputs`: {name: {'value':..., 'source':...}}.

    Returns a full audit-trail dict (see module docstring).
    """
    table = select_calc_table(conn, calc_code, on_date=on_date, tax_year=tax_year)
    trail = {
        "calc_code": calc_code,
        "inputs": inputs,
        "steps": [],
        "rounding_method": None,
        "result": None,
        "validation_status": "incomplete_missing_inputs",
    }
    if table is None:
        trail["steps"].append(
            f"No version of calc table '{calc_code}' is in effect for "
            f"{on_date or tax_year or 'the given period'}.")
        return trail

    params = _json(table["params"], {})
    trail.update({
        "calc_version": table["version"],
        "applicable_rule": f"{table['code']} v{table['version']}",
        "legislation_ref": table.get("legislation_ref"),
        "effective_date": table["effective_from"],
        "rounding_method": params.get("rounding", "exact"),
        "verification_status": table["verification_status"],
    })
    if table["verification_status"] != "verified":
        trail["validation_status"] = "unverified_rule"
        trail["steps"].append(
            f"NOTE: calc table status is '{table['verification_status']}' — "
            "result is indicative only, not a verified computation.")

    kind = table["kind"]
    required = params.get("required_inputs", ["base"])
    missing = [n for n in required
               if n not in inputs or inputs[n].get("value") in (None, "")]
    if missing:
        trail["steps"].append(
            f"Missing required inputs: {', '.join(missing)} — "
            "calculation left incomplete; no values invented.")
        if trail["validation_status"] != "unverified_rule":
            trail["validation_status"] = "incomplete_missing_inputs"
        return trail

    vals = {n: inputs[n]["value"] for n in required}
    rounding = params.get("rounding", "exact")
    steps = trail["steps"]

    if kind in ("percentage", "flat_rate"):
        base_name = _base_name(params, required)
        base = _dec(vals[base_name])
        rate = _dec(params["rate"])
        steps.append(f"Base ({params.get('rate_basis', base_name)}): {base:,}")
        steps.append(f"Rate: {rate} ({(rate * 100).normalize()}%)")
        raw = base * rate
        steps.append(f"Raw: {base:,} × {rate} = {raw:,}")
        result = _round(raw, rounding)
        steps.append(f"Rounded ({rounding}): {result:,}")

    elif kind == "slab":
        base = _dec(vals[_base_name(params, required)])
        steps.append(f"Taxable base: {base:,}")
        remaining = base
        lower = Decimal("0")
        total = Decimal("0")
        for i, slab in enumerate(params["slabs"]):
            upto = slab["upto"]
            rate = _dec(slab["rate"])
            upper = Decimal(str(upto)) if upto is not None else None
            if upper is None:
                portion = remaining
            else:
                width = upper - lower
                portion = min(remaining, width) if width > 0 else Decimal("0")
            if portion > 0:
                tax = portion * rate
                steps.append(
                    f"Slab {i + 1}: {lower:,}–{'∞' if upper is None else f'{upper:,}'} "
                    f"@ {(rate * 100).normalize()}% → {portion:,} × {rate} = {tax:,}")
                total += tax
                remaining -= portion
            lower = upper if upper is not None else lower
            if remaining <= 0:
                break
        steps.append(f"Total before rounding: {total:,}")
        result = _round(total, rounding)
        steps.append(f"Rounded ({rounding}): {result:,}")

    elif kind == "threshold":
        base = _dec(vals[_base_name(params, required)])
        threshold = _dec(params["threshold"])
        steps.append(f"Base: {base:,}; threshold: {threshold:,}")
        if base < threshold:
            action = params.get("action_below", "no_tax")
            steps.append(f"Base below threshold → {action}.")
            result = Decimal("0")
        else:
            rate = _dec(params.get("rate", 0))
            tax_base = params.get("tax_base", "full_amount")
            taxable = base if tax_base == "full_amount" else base - threshold
            steps.append(f"Base meets/exceeds threshold; taxable portion "
                         f"({tax_base}): {taxable:,}")
            steps.append(f"Rate: {(rate * 100).normalize()}%")
            raw = taxable * rate
            steps.append(f"Raw: {taxable:,} × {rate} = {raw:,}")
            result = _round(raw, rounding)
            steps.append(f"Rounded ({rounding}): {result:,}")

    elif kind == "fixed_amount":
        amount = _dec(params["amount"])
        steps.append(f"Fixed amount per {params.get('per', 'unit')}: {amount:,}")
        count = _dec(vals["count"]) if "count" in vals else Decimal("1")
        if "count" in vals:
            steps.append(f"Count: {count}")
        result = _round(amount * count, rounding)
        steps.append(f"Result ({rounding}): {result:,}")

    elif kind == "rate_schedule":
        # Conditional rate table: first row whose dimensions all match wins.
        # A dimension value of "any" is a wildcard. Missing dimension inputs
        # mean no row can be selected -> incomplete, never a guessed rate.
        base_name = params.get("base_input", "payment_amount")
        aliases = params.get("input_aliases", {})
        rows = params["rates"]
        dim_keys = sorted({k for r in rows for k in r.keys()
                           if k != "rate"})
        if base_name not in vals:
            raise CalculationError(
                f"rate_schedule needs base input '{base_name}'")
        base = _dec(vals[base_name])
        steps.append(f"Base ({params.get('rate_basis', base_name)}): {base:,}")
        steps.append(f"Rate dimensions: {', '.join(dim_keys) or 'none'}")
        chosen, missing_dims = None, set()
        for i, row in enumerate(rows):
            dims = {k: v for k, v in row.items() if k != "rate"}
            ok, lacking = True, []
            for dk, dv in dims.items():
                if dv == "any":
                    continue
                iname = aliases.get(dk, dk)
                if iname not in vals:
                    ok, lacking = False, lacking + [iname]
                elif str(vals[iname]) != str(dv):
                    ok = False
                    break
            if ok:
                chosen = (i, row)
                break
            missing_dims.update(lacking)
        if chosen is None:
            if missing_dims:
                trail["steps"].append(
                    "No rate row selectable: missing dimension inputs: "
                    + ", ".join(sorted(missing_dims))
                    + " — calculation left incomplete; no rate assumed.")
                if trail["validation_status"] != "unverified_rule":
                    trail["validation_status"] = "incomplete_missing_inputs"
                return trail
            raise CalculationError(
                "no rate_schedule row matches the given dimensions; "
                "check the category inputs")
        i, row = chosen
        rate = _dec(row["rate"])
        dim_desc = ", ".join(f"{k}={row[k]}" for k in dim_keys
                             if k in row)
        steps.append(f"Rate row {i + 1} selected ({dim_desc}): "
                     f"{(rate * 100).normalize()}%")
        raw = base * rate
        steps.append(f"Raw: {base:,} × {rate} = {raw:,}")
        result = _round(raw, rounding)
        steps.append(f"Rounded ({rounding}): {result:,}")

    else:
        raise CalculationError(f"unsupported calc kind: {kind!r}")

    trail["result"] = float(result)
    if trail["validation_status"] != "unverified_rule":
        trail["validation_status"] = "complete"
    elif trail["result"] is not None:
        # computed despite unverified status — keep the flag, note it
        steps.append("Result computed but flagged unverified (see note above).")
    return trail
