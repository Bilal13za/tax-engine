# Seed File Format — Tax Knowledge JSON

Seed files live in `seed/*.json` (authored) and `seed/incoming/*.json`
(research-agent output, reviewed before promotion). The loader
(`src/taxengine/loader.py`) validates every file against this contract and
**rejects** files that violate it.

## Top-level structure

```json
{
  "meta": {
    "domain": "withholding_tax",
    "author": "research-agent-wht",
    "prepared_date": "2026-10-21",
    "notes": "Rates verified against FBR website on 2026-10-21 unless marked draft."
  },
  "sources": [ ... ],
  "legislation": [ ... ],
  "rules": [ ... ],
  "risks": [ ... ],
  "evidence": [ ... ],
  "procedures": [ ... ],
  "calc_tables": [ ... ],
  "scenarios": [ ... ]
}
```

Any section may be omitted or an empty array. `meta` is required.

## Hard rules (loader-enforced)

1. **Never invent** a provision, section number, rate, threshold, deadline, or
   official reference. If you cannot verify it from an authoritative source
   (FBR/official gazette/legislation text), set
   `"verification_status": "draft"` and explain the gap in `review_notes`.
   Draft rules are stored but **never presented as authoritative** and are
   excluded from definitive calculations.
2. Every rule needs: `code`, `title`, `tax_category`, `jurisdiction`,
   `taxpayer_types`, `triggering_transaction`, `transaction_types`,
   `applicability_conditions`, `decision_logic`, `expected_treatment`,
   `effective_from`, `verification_status`.
3. `tax_category` ∈ `income_tax | withholding_tax | sales_tax_federal |
   customs | sales_tax_provincial | provincial_other | other_levies`.
4. `jurisdiction` ∈ `federal | punjab | sindh | kpk | balochistan | ict |
   gb | ajk`.
5. `verification_status` ∈ `draft | under_review | verified | superseded |
   retired`. Only `verified` rules feed definitive calculations and the
   "verified rules" list. Mark `verified` **only** when you checked the
   provision text against an authoritative source on the stated
   `source_verified_date`.
6. Dates are `YYYY-MM-DD`. `effective_to: null` means currently in force
   **to the best of your knowledge on `prepared_date`** — say so in notes.
7. Rates, slabs and thresholds go in `calc_tables[].params`, never only in
   prose. Each calc table needs `kind`, `params`, `legislation_ref`,
   `effective_from`.
8. Distinguish statute from interpretation: put the software's reading in
   `interpretation_note`, never inside `expected_treatment` as if it were law.
9. Do not label a discrepancy "evasion" or "fraud". Use neutral terms:
   `potential_error`, `discrepancy`, `exception_flagged`.
10. Do not compute penalties unless the legal conditions, dates, rates and
    method are verified — otherwise leave `penalty_implications` null and note
    why in the risk's description.

## Condition trees

`applicability_conditions`, `exclusion_conditions`, scenario `trigger_facts`
and risk `applicable_conditions` use this shape:

```json
{ "all": [
    {"field": "payment_category", "op": "in", "value": ["goods", "services"]},
    {"field": "payer_is_withholding_agent", "op": "eq", "value": true},
    {"any": [
        {"field": "payee_type", "op": "eq", "value": "company"},
        {"field": "payee_type", "op": "eq", "value": "non_company"}
    ]},
    {"field": "transaction_date", "op": "date_between", "value": ["2024-07-01", "2025-06-30"]}
]}
```

Operators: `eq | ne | in | not_in | gt | gte | lt | lte | exists |
not_exists | contains | date_between | date_gte | date_lte`.
`field` names must be documented in the rule's `required_inputs`.

## Decision logic (explicit IF/THEN tables)

```json
"decision_logic": {
  "table": [
    {"when": {"all": [{"field": "exemption_certificate_valid", "op": "eq", "value": true}]},
     "then": "No withholding required; retain certificate (see EV-WHT-CERT).",
     "treatment_code": "no_wht_exempt"},
    {"when": {"all": [{"field": "exemption_certificate_valid", "op": "eq", "value": false}]},
     "then": "Apply CALC-WHT-153-GOODS for the transaction date; deduct and deposit per rule.",
     "treatment_code": "deduct_deposit"}
  ],
  "default": "Insufficient information — request exemption status before determining treatment."
}
```

The example above must **not** hard-code any rate — rates come from the
referenced calc table for the transaction date.

## required_inputs

```json
"required_inputs": [
  {"name": "payment_amount", "label": "Gross payment amount (PKR)",
   "data_type": "number", "required": true, "source_hint": "Payment voucher / bank advice"},
  {"name": "transaction_date", "label": "Date of payment", "data_type": "date",
   "required": true, "source_hint": "Payment record"}
]
```

`data_type` ∈ `string | number | date | boolean | choice`. For `choice`,
add `"choices": [...]`.

## calc_tables params by kind

- `percentage`: `{"rate": 0.04, "rate_basis": "gross payment amount", "rounding": "nearest_rupee"}`
- `flat_rate`: `{"rate": 0.29, "base": "taxable income", "rounding": "nearest_rupee"}`
- `slab`: `{"slabs": [{"upto": 600000, "rate": 0.0}, {"upto": 1200000, "rate": 0.05}], "rounding": "nearest_rupee"}`
  (progressive: each portion taxed at its slab rate; final `upto: null` = infinity)
- `threshold`: `{"threshold": 100000, "action_below": "no_tax", "action_above": "apply_rate", "rate": 0.02}`
- `fixed_amount`: `{"amount": 5000, "per": "return", "rounding": "exact"}`
- `rate_schedule`: conditional rates, e.g. withholding by payee type / ATL status:
  `{"rate_basis": "gross payment amount", "rounding": "nearest_rupee",`
  `"base_input": "gross_payment_amount",`
  `"input_aliases": {"atl": "atl_status"},`
  `"rates": [{"supply_category": "other_goods", "payee_type": "company", "atl": "ATL", "rate": 0.05}, ...]}`
  The engine selects the first row whose dimensions all match the inputs
  (`"any"` is a wildcard). Missing dimension inputs → incomplete calculation;
  no row matching → error. Never a guessed rate.

Always include `rounding` and the `base`/`rate_basis` definition. If there is
exactly one required input it is the calculation base; with several required
inputs, name the base explicitly via `"base_input": "<input name>"`.

## Linking

Within one seed file, link by code strings:

- rule → legislation: `"legislation_codes": ["LEG-ITO2001-S153"]`
- rule → risks / evidence / procedures / calcs: `"risk_codes": [...]`,
  `"evidence_codes": [...]`, `"procedure_codes": [...]`, `"calc_codes": [...]`
- risk → evidence/procedures: `"evidence_codes"`, `"procedure_codes"`
- procedure → evidence: `"evidence_codes"` (documents_to_obtain)
- scenario `expected_chain`: `{"rule_codes": [...], "risk_codes": [...],
  "evidence_codes": [...], "procedure_codes": [...], "calc_codes": [...]}`

Codes must be unique across the whole knowledge base; prefix per domain
(e.g. `RULE-WHT-`, `RISK-INC-`, `EV-`, `PROC-`, `CALC-`, `LEG-`, `SCN-`, `SRC-`).

## review_status / verification_status lifecycle

`draft` → `under_review` → `verified`. When law changes: keep the old row,
set it `superseded`, add a new row (version+1) with `supersedes_code`
pointing at the old code, new `effective_from`, and note the amending
instrument in `amendment_history` (legislation) / `review_notes` (rules).
