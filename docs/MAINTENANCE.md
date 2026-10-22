# Rule Update & Maintenance Guide

Rules are **data, not code**. You add or change tax law without touching the
application.

## The lifecycle

```
draft → under_review → verified
                            ├─ law changes → new version (old → superseded)
                            └─ withdrawn   → retired
```

- **Never edit a `verified` row in place** to reflect a law change. Create a
  new version row (`version` + 1, `supersedes_code` pointing at the old code),
  set the old row's status to `superseded` with the new `effective_from`
  recorded in the amendment history. Historical calculations keep working
  because selection is date-scoped.
- **Never mark `verified`** unless the provision text and applicability were
  checked against an authoritative source (FBR/official text) on the stated
  `source_verified_date`, with reviewer and review date recorded.
- **Never invent** provisions, section numbers, rates, thresholds, deadlines
  or references. Unverifiable content stays `draft` with the gap in
  `review_notes`.

## Adding rules: the workflow

1. Write or edit a seed JSON file following `seed/SEED_FORMAT.md`
   (a worked example is in `seed/incoming/` once research lands).
2. Validate it:
   ```
   set TAXENGINE_DATA_DIR=data
   python -m taxengine.loader  path\to\your_seed.json   (or use Module C later)
   ```
   The loader **rejects** files with missing required fields, bad dates,
   unknown categories, missing legal sources, dangling code references,
   empty decision tables, or `verified` status without reviewer + date.
3. Load it into the knowledge database (the loader is idempotent —
   re-loading the same file changes nothing).
4. Rebuild the search index if you edited the DB directly
   (`loader.rebuild_fts()`).
5. Run the test suite (`run_tests.bat`) — it guards date-scoping,
   version preservation and calculation accuracy.
6. Regenerate the registers:
   `python scripts\generate_registers.py` → updates
   `docs/SOURCE_REGISTER.md` and `docs/VERIFIED_VS_UNVERIFIED.md`.

## After a Finance Act / SRO / notification

1. Identify affected rules: search Module C by provision (e.g. `153`).
2. For each affected rule **and** calc table: add the new version with the
   new `effective_from` (usually 1 July), set the old version's
   `effective_to` and status `superseded`.
3. Record the amending instrument in `amendment_history` / `review_notes`.
4. Re-run the affected sample calculations for both the old and new
   periods (Module E) and confirm the date-scoping picks the right version.
5. Update the source register entry's `verified_date`.

## Validation checklist (§14, enforced by the loader)

- [ ] Required fields present
- [ ] Effective dates valid (`from` ≤ `to`, `YYYY-MM-DD`)
- [ ] Legal source cited (legislation code exists)
- [ ] Applicability/exclusion conditions parse
- [ ] Decision table has ≥1 branch + default
- [ ] Calculation method references an existing calc table (or is empty)
- [ ] Required evidence codes exist
- [ ] `verified` ⇒ reviewer + review date + source verification date
- [ ] Version history sane (new version supersedes the old)

## Who can edit

This is a single-user offline tool: anyone with the `data\` folder can
maintain rules. Keep a copy of each seed JSON you load (in `seed\`) so the
database can always be rebuilt from source.
