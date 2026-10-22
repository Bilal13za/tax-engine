# Offline Operating Instructions

The engine is designed to run with **no internet connection** after the
one-time first-run install.

## What works offline

Everything in normal operation:

- All 8 modules (profiles, assessments, rule lookup, risk explorer,
  calculations, reconciliations, evidence tracker, export)
- Full-text search (SQLite FTS5, on-device)
- All calculations (rates/slabs live in the local database)
- CSV and Excel export (openpyxl, local)
- Rule maintenance (JSON seeds validated and loaded locally)

The automated test suite includes an offline proof: with the network layer
disabled entirely, analysis, search, calculation, reconciliation and export
all succeed (`tests/test_offline.py`).

## What needs internet (and when)

| Task | Internet needed? |
|---|---|
| First-run dependency install | Yes, once |
| Daily use | No |
| Loading new seed JSON files | No (files are local) |
| **Verifying a tax rule against its authoritative source** | Yes — source verification is a research task done in a browser, not by the app |

## Verifying sources

"Verified" in this system means a human checked the provision text against
an authoritative source (FBR website, official gazette/Act text) and
recorded the `source_verified_date`. The app never fetches sources itself.
Re-verify rules after each Finance Act: see `docs/MAINTENANCE.md`.

## Backups

Your working data (`data\tax_workdata.db`) is yours — back it up:

1. Close the app (or just make sure no assessment is being saved).
2. Copy `data\tax_workdata.db` (and `data\tax_knowledge.db` if you
   customised rules) to `data\backups\` or an external drive.

Recommended: back up before loading any seed update. A restore is copying
the files back.

## Data privacy

All data stays on your computer:

- No accounts, no telemetry, no network calls at runtime.
- Taxpayer profiles and assessments live in `data\tax_workdata.db` only.
- Exported files go to `data\exports\` — share them deliberately.
