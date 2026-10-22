# Pakistan Tax Risk, Rules and Evidence Engine

An **offline, deterministic** tax knowledge and compliance system for Pakistan.
No AI, no LLMs, no cloud, no paid APIs — at runtime or otherwise. Tax
analysis comes from structured rules, explicit decision tables, versioned
rate tables and predefined verification procedures stored in SQLite.

## What it does

Pick a transaction (or a predefined scenario) and get a traceable 14-step
analysis:

1. Taxpayer profile → 2. Transaction/condition → 3. Applicable legislation →
4. Applicability conditions → 5. Correct tax treatment → 6. Possible tax error →
7. Tax risk → 8. Documents & evidence required → 9. Verification procedure →
10. Calculation/reconciliation → 11. Exceptions → 12. Potential tax adjustment →
13. Return/compliance impact → 14. Follow-up action

Every conclusion is explainable through explicit rules and documented
sources. Unverified rules are shown but **flagged** — never presented as
authoritative.

## Modules (local web interface)

| Module | Purpose |
|---|---|
| A · Taxpayer Profile | Individual/business profiles: type, residence, tax year, province, registrations, regimes |
| B · Transaction Assessment | Enter facts or pick a scenario → full 14-step chain |
| C · Tax Rule Lookup | Full-text + filtered search (category, jurisdiction, section, transaction type, tax year, taxpayer type, status) |
| D · Tax Risk Explorer | Triggering factor, error, rule, exposure, evidence, procedures, follow-up |
| E · Calculation Workbench | Verified calculations with full working and legal references |
| F · Reconciliation | Profit→taxable income, turnover, WHT credits, payments, sales tax |
| G · Evidence Tracker | Requested/received/verified, results, exceptions, outstanding info |
| H · Export | Rules/calculations/assessments to CSV and formatted Excel |

## Quick start (Windows)

1. Extract the ZIP anywhere.
2. Double-click **`run_windows.bat`** — it installs Python itself if missing
   (via winget), sets up the environment, and opens the app in your browser.
3. First run needs internet (one-time dependency install). After that the
   app is **fully offline**.

See `docs/INSTALL_WINDOWS.md` and `docs/OFFLINE_OPS.md`.

## Project layout

```
tax-engine/
  app.py                 # Streamlit interface (Modules A–H)
  run_windows.bat        # Windows launcher (double-click)
  run_tests.bat          # pytest runner
  requirements.txt
  schema/                # schema_knowledge.sql, schema_workdata.sql
  src/taxengine/         # db, loader, validate, decision, calc,
                         # reconcile, export, search
  seed/                  # JSON rule definitions (see SEED_FORMAT.md)
    evidence_library.json, procedures_library.json
    incoming/            # research-agent output, reviewed before promotion
  data/                  # created on first run: tax_knowledge.db,
                         # tax_workdata.db, exports/
  tests/                 # pytest suite (42 tests)
  docs/                  # data dictionary, install/ops/maintenance guides,
                         # source register, verified-vs-unverified list
  sample_data/           # sample walkthrough inputs
```

## Two databases, strictly separated

- **`tax_knowledge.db`** — the tax library: legislation, rules (versioned),
  risks, evidence, procedures, calculation tables, scenarios, sources.
- **`tax_workdata.db`** — *your* working data: taxpayer profiles,
  assessments, evidence tracking, reconciliations, calculation runs.

## Tax content status

The software is complete; the **tax library is a starter set, not a
complete code**. Each rule carries a verification status:

- `verified` — provision and applicability checked against an authoritative
  source on the stated verification date.
- `draft` / `under_review` — indicative only; never used for definitive
  calculations.
- `superseded` / `retired` — preserved for historical tax years.

See `docs/VERIFIED_VS_UNVERIFIED.md` (generated from the database) and
`docs/SOURCE_REGISTER.md`. When a law changes, the old version is kept and
a new versioned row is added — historical computations always use the rule
in effect on the transaction date.

## Adding / updating rules

Rules are data, not code: edit JSON (see `seed/SEED_FORMAT.md`), validate,
and load — see `docs/MAINTENANCE.md`. The loader rejects incomplete or
unverifiable rules.

## Tests

42 pytest tests cover effective dates, historical vs current calculations,
slab accuracy, taxpayer classification, missing information, exemptions,
provincial jurisdictions, withholding rate selection, reconciliation,
evidence tracking, validation rejections, exports, offline operation
(sockets disabled), and a full end-to-end scenario. Run `run_tests.bat`.

## Disclaimer

Educational and research tool. It is not tax advice and does not replace
professional judgement or the authoritative legal text. Verify critical
positions against current legislation and FBR guidance.
