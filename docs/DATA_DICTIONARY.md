# Data Dictionary

## Knowledge database (`tax_knowledge.db`)

### `sources` — source register
| Column | Meaning |
|---|---|
| code | Stable code, e.g. `SRC-FBR-ITO2001` |
| title | Full title of the source |
| source_type | `legislation` \| `rules` \| `notification` \| `sro` \| `circular` \| `explanatory_guidance` \| `professional_interpretation` \| `illustrative_example` \| `case_law` |
| issuing_authority | e.g. `Government of Pakistan`, `FBR` |
| jurisdiction | `federal` \| `punjab` \| `sindh` \| `kpk` \| `balochistan` \| `ict` \| `gb` \| `ajk` |
| reference_url | Official URL where verified (may be empty for print sources) |
| verified_date | `YYYY-MM-DD` the source was last checked |

### `legislation` — provisions, rules, notifications (one row per version)
`code`, `name`, `issuing_authority`, `jurisdiction`, `provision` (e.g. `Section 21`),
`subsection` (e.g. `21(1)(a)`), `rule_description`, `effective_from`/`effective_to`
(`YYYY-MM-DD`), `tax_year`, `amendment_history`, `source_code` → `sources.code`,
`source_verified_date`, `review_status`, `version`, `supersedes_id`.

### `tax_rules` — the rule library (one row per version)
| Column | Meaning |
|---|---|
| code / version | Stable rule code + version number (unique together) |
| title | Short rule title |
| tax_category | `income_tax` \| `withholding_tax` \| `sales_tax_federal` \| `customs` \| `sales_tax_provincial` \| `provincial_other` \| `other_levies` |
| jurisdiction | Federal or province/territory |
| taxpayer_types | JSON array: `individual`, `aop`, `company`, `other` |
| triggering_transaction | Human-readable trigger |
| transaction_types | JSON array of machine tags (e.g. `payment_for_goods`) |
| applicability_conditions | JSON condition tree (all/any + leaf ops) |
| exclusion_conditions | JSON condition tree; empty = no exclusions |
| required_inputs | JSON array of `{name,label,data_type,required,source_hint}` |
| decision_logic | JSON `{table:[{when,then,treatment_code}], default}` |
| expected_treatment | The correct tax treatment in words |
| calculation_method | Calc-table code or method description |
| exceptions | JSON array of `{condition, description, action}` |
| consequences | What follows from error/non-compliance (no invented penalties) |
| return_fields | JSON array of affected return fields/statements |
| effective_from / effective_to | `YYYY-MM-DD` applicability window |
| verification_status | `draft` \| `under_review` \| `verified` \| `superseded` \| `retired` |
| reviewer / review_date / review_notes | Review record |
| interpretation_note | The software's reading — kept separate from statute |
| supersedes_id | Previous version's row id |

### `tax_risks`
`code`, `title`, `description`, `root_cause`, `tax_category`, `jurisdiction`,
`potential_financial_effect`, `exposure_note`, `penalty_implications`
(only where legal conditions verified, else null + note), `applicable_conditions`
(JSON tree), `risk_indicators` (JSON), `required_information` (JSON),
`followup_action`, `source_codes` (JSON), `review_status`.

### `evidence`
`code`, `name`, `description`, `typical_source`, `verification_procedure`,
`reliability_notes`, `limitations`, `expected_information` (JSON),
`common_discrepancies` (JSON), `review_status`.

### `procedures`
`code`, `name`, `category` (`document_verification` \| `reconciliation` \|
`calculation` \| `completeness` \| `eligibility`), `objective`,
`triggering_condition`, `steps` (JSON array), `inputs_required` (JSON),
`documents_to_obtain` (JSON), `calculation_method`, `expected_result`,
`exception_conditions` (JSON), `followup_procedure`, `legislation_ref`,
`review_status`.

### `calc_tables` — rates, slabs, thresholds (never in code)
`code`/`version`, `name`, `kind` (`slab` \| `flat_rate` \| `percentage` \|
`fixed_amount` \| `threshold`), `tax_category`, `jurisdiction`,
`taxpayer_types` (JSON), `params` (JSON — see `seed/SEED_FORMAT.md`),
`legislation_ref`, `effective_from`/`effective_to`, `tax_year`,
`verification_status`, `supersedes_id`.

### Link tables
`rule_legislation`, `rule_risks`, `rule_evidence`, `rule_procedures`,
`rule_calcs`, `risk_evidence`, `risk_procedures` — structured many-to-many
relations between rules and library objects.

### `scenarios` — predefined §10 scenarios
`code`, `name`, `category`, `description`, `trigger_facts` (JSON condition
tree), `expected_chain` (JSON: rule/risk/evidence/procedure/calc codes),
`accounting_vs_tax` note, `review_status`.

### `kb_fts` — FTS5 full-text index over rules, risks, legislation, evidence,
procedures. Rebuilt by `loader.rebuild_fts()`.

## Working database (`tax_workdata.db`)

### `taxpayer_profiles`
`profile_code` (unique), `display_name`, `taxpayer_type`, `resident_status`,
`tax_year`, `accounting_period_from/to`, `business_activity`, `industry`,
`province`, `federal_registered`, `sales_tax_registered`,
`sales_tax_jurisdiction`, `applicable_regimes` (JSON), `withholding_obligations`
(JSON), `available_records` (JSON), `review_status`, `notes`.

### `assessments` + `assessment_steps`
One assessment per transaction/scenario analysis. `assessment_steps` stores
the 14-step chain (`step_no` 1–14, `step_name`, `rule_code`, `finding`,
`detail` JSON, `confidence`: `info` \| `needs_input` \| `unverified_rule` \|
`exception_flagged`).

### `evidence_tracker`
Per assessment: `evidence_code`, `requested`, `received`,
`verification_done`, `result` (`ok` \| `discrepancy_found` \| `incomplete` \|
`not_applicable`), `exceptions`, `outstanding_info`, `reviewer_comments`,
`status`.

### `reconciliations`
`template_code`, `title`, `lines` (JSON: label, amount_a/b, difference,
sources, note, status), `total_difference`, `conclusion`, `status`.

### `calculation_runs`
Full audit trail per §11: `calc_code`/`calc_version`, `inputs` (JSON with
per-input source), `legislation_ref`, `effective_date`, `steps` (JSON),
`rounding_method`, `result`, `validation_status` (`complete` \|
`incomplete_missing_inputs` \| `unverified_rule`).

### `export_log`
`assessment_id`, `export_kind`, `file_format`, `file_name`, timestamp.

## Condition-tree reference

Trees are JSON: `{"all": [...]}` / `{"any": [...]}` nesting, leaves
`{"field","op","value"}`. Operators: `eq, ne, in, not_in, gt, gte, lt, lte,
exists, not_exists, contains, date_between, date_gte, date_lte`. An empty
tree/list means "no conditions" (always true for applicability; no
exclusions for exclusion lists). Missing facts make a condition
*undecidable* — the engine reports `needs_input`, never guesses.
