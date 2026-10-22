# Sample Walkthrough — Withholding on a Supplier Payment

A complete worked example of the engine, from transaction entry to export.
(The automated version of this walkthrough is
`tests/test_end_to_end.py`, using synthetic TEST content.)

## 1. Taxpayer profile (Module A)

- **Test Company (Pvt) Ltd** — company, resident, Tax Year 2026
- Province: Punjab · Federal registered: yes
- Withholding obligations: prescribed person for payments u/s 153

## 2. Transaction (Module B)

| Fact | Value |
|---|---|
| tax_category | withholding_tax |
| transaction_type | payment_for_goods |
| transaction_date | 2025-02-10 |
| payment_category | goods |
| payment_amount | 500,000 |
| payer_is_withholding_agent | true |
| exemption_certificate_valid | false |

## 3–5. Legislation → applicability → treatment

- The engine matches the withholding rule for payments for goods, links the
  Income Tax Ordinance provision, and confirms all applicability conditions.
- The decision table selects the **deduct** branch (no valid exemption
  certificate): deduct per the calc table in effect on 2025-02-10 and deposit.

## 6–7. Possible error → risk

- Possible error: no tax deducted (the branch not taken).
- Risk: `RISK-…` — deduction omitted; indicators: payment without deduction;
  follow-up: verify deposit and reporting.

## 8–9. Evidence → verification

- Evidence required: supplier payment records, withholding certificate,
  tax challan.
- Procedure: recalculate withholding (confirm legal category → select the
  calc table for the payment date → correct tax base → recompute → compare
  with deducted amount → verify deposit/reporting).

## 10. Calculation (Module E)

Calc table v2 (in effect 2024-07-01, verified):

```
Base (gross payment): 500,000
Rate: 0.07 (7%)
Raw: 500,000 × 0.07 = 35,000.00
Rounded (nearest_rupee): 35,000
```

Full audit trail recorded: inputs + sources, rule version, provision,
effective date, steps, rounding, result, validation status = complete.

## 11–12. Exceptions → adjustment

- No rule exceptions trigger on these facts.
- If the evidence review finds the challan short (say 30,000 deposited),
  the reconciliation flags a −5,000 difference and the follow-up requires
  deposit of the shortfall.

## 13–14. Return impact → follow-up

- Return fields: withholding statement / credit schedules affected.
- Follow-up: obtain the missing facts (none here), confirm the unverified
  items (none here), and re-run after any law change.

## Export (Module H)

- `assessment_N.xlsx`: Summary (14 steps), Rules, Risks, Evidence,
  Calculations (with working), Reconciliations.
- `tax_rules.csv`, `calculations_assessment_N.csv`.

Try it live: Module B → pick scenario `SCN-TEST-001` (once research seeds
are loaded, the real Pakistan scenarios appear the same way).
