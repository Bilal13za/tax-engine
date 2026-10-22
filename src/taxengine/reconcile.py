"""Reconciliation templates (Module F).

Configurable templates for the standard tax reconciliations. The caller
supplies the lines (label, amount_a, amount_b, note); this module computes
differences, totals and a draft conclusion. Nothing is invented: every line
must carry its source.
"""

from __future__ import annotations

TEMPLATES = {
    "RECON-PROFIT-TO-TAXABLE": {
        "title": "Accounting profit to taxable income",
        "column_a": "Accounting (PKR)",
        "column_b": "Tax computation (PKR)",
        "suggested_lines": [
            "Profit before tax per financial statements",
            "Add: accounting depreciation",
            "Less: tax depreciation claimed",
            "Add: inadmissible expenses (e.g. per s.21 ITO 2001)",
            "Less: exempt income / allowable deductions",
            "Taxable income",
        ],
        "procedure_hint": "Reconcile accounting profit to taxable income; "
                          "every add-back/deduction must cite its provision.",
    },
    "RECON-TURNOVER": {
        "title": "Accounting turnover to reported turnover",
        "column_a": "General ledger (PKR)",
        "column_b": "Tax return (PKR)",
        "suggested_lines": [
            "Revenue per general ledger",
            "Less: exempt / zero-rated supplies (if any)",
            "Add: unrecorded revenue identified",
            "Turnover per tax return",
        ],
        "procedure_hint": "Trace revenue from the ledger to the return; "
                          "investigate cut-off and classification differences.",
    },
    "RECON-WHT-CREDITS": {
        "title": "Withholding tax deducted to tax credits claimed",
        "column_a": "Certificates / statements (PKR)",
        "column_b": "Return claim (PKR)",
        "suggested_lines": [
            "WHT per deduction certificates",
            "WHT per party ledgers / challans",
            "WHT claimed as credit in return",
        ],
        "procedure_hint": "Reconcile deducted tax to certificates, challans "
                          "and the credit claimed; unmatched credits are exceptions.",
    },
    "RECON-PAYMENTS": {
        "title": "Tax payments to amounts payable",
        "column_a": "Challans / bank (PKR)",
        "column_b": "Liability per computation (PKR)",
        "suggested_lines": [
            "Tax liability per computation",
            "Less: advance tax paid",
            "Less: withholding credits",
            "Balance payable / (refundable)",
            "Amount actually deposited",
        ],
        "procedure_hint": "Agree each payment to a challan/bank credit; "
                          "short payments accrue exposure.",
    },
    "RECON-SALESTAX": {
        "title": "Sales tax records to accounting records",
        "column_a": "Sales tax records (PKR)",
        "column_b": "Accounting records (PKR)",
        "suggested_lines": [
            "Taxable supplies per sales tax return",
            "Revenue per general ledger (taxable portion)",
            "Output tax per return",
            "Output tax per accounting records",
            "Input tax claimed per return",
            "Input tax per purchase register",
        ],
        "procedure_hint": "Reconcile output tax and input tax between the "
                          "return, registers and the ledger, period by period.",
    },
}


def new_reconciliation(template_code: str) -> dict:
    """Return template metadata + suggested line labels for the UI."""
    tpl = TEMPLATES.get(template_code)
    if tpl is None:
        raise KeyError(f"unknown reconciliation template: {template_code!r}")
    return {"template_code": template_code, **tpl}


def compute(lines: list) -> dict:
    """Compute differences for user-supplied lines.

    Each line: {'label': str, 'amount_a': number|None, 'amount_b': number|None,
                'source_a': str, 'source_b': str, 'note': str}
    Lines without both amounts are reported as incomplete, not zero-filled.
    """
    out_lines = []
    total_diff = 0.0
    incomplete = 0
    for ln in lines:
        a, b = ln.get("amount_a"), ln.get("amount_b")
        if a is None or b is None or a == "" or b == "":
            diff = None
            incomplete += 1
        else:
            diff = float(a) - float(b)
            total_diff += diff
        out_lines.append({
            "label": ln.get("label", ""),
            "amount_a": a, "amount_b": b,
            "difference": diff,
            "source_a": ln.get("source_a", ""),
            "source_b": ln.get("source_b", ""),
            "note": ln.get("note", ""),
            "status": "ok" if diff == 0 else ("difference" if diff is not None else "incomplete"),
        })
    if incomplete:
        conclusion = (f"{incomplete} line(s) incomplete — provide both amounts "
                      "before concluding.")
    elif total_diff == 0:
        conclusion = "Reconciled: no differences."
    else:
        conclusion = (f"Unreconciled difference of {total_diff:,.2f}. "
                      "Investigate each non-zero line before concluding.")
    return {"lines": out_lines, "total_difference": total_diff,
            "incomplete_lines": incomplete, "conclusion": conclusion}
