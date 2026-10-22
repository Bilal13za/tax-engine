# Windows Installation

## Requirements

- Windows 10/11 (64-bit)
- ~500 MB free disk space
- 8 GB RAM (the app is light: SQLite + a local web server)
- Internet **once**, for the first-run dependency install

## Install steps

1. Extract the ZIP to any folder, e.g. `C:\tax-engine\`.
   (Avoid syncing the `data\` folder to OneDrive while the app runs —
   SQLite does not like live-synced database files.)
2. Double-click **`run_windows.bat`**.
3. If Python is missing, the launcher installs it automatically via
   `winget` (Windows Package Manager) and continues.
4. First run creates an isolated `.venv`, installs dependencies
   (`streamlit`, `openpyxl`, `pytest`), initialises the databases, and
   opens the app in your browser at `http://127.0.0.1:8503`.
5. Keep the black window open while using the app; closing it stops the app.

If the app is already running, double-clicking the launcher just opens the
browser.

## What gets installed where

| Location | Contents |
|---|---|
| `data\tax_knowledge.db` | Tax library (rules, legislation, rates — versioned) |
| `data\tax_workdata.db` | Your taxpayer profiles, assessments, exports log |
| `data\exports\` | CSV/Excel files you export |
| `data\backups\` | Manual/automatic database backups |
| `.venv\` | Isolated Python environment (safe to delete; recreated on next run) |

## Troubleshooting

- **"winget not found"**: install Python 3.10+ manually from
  https://www.python.org (tick "Add python.exe to PATH"), then re-run.
- **Dependency install fails**: you need internet for this one step; check
  firewall/proxy, then re-run the launcher (it resumes, not restarts).
- **Port 8503 in use**: the launcher detects a running copy and opens the
  browser instead of starting a second server.
- **Browser shows "site can't be reached"**: wait a few seconds and refresh —
  the launcher opens the browser the moment the server accepts connections.
- **Antivirus flags the launcher**: it is a plain batch file; inspect it in
  Notepad if you like. Nothing is downloaded except Python (via winget) and
  the three Python packages above.

## Updating

Replace the application folder with the new version, keeping your `data\`
folder (or copy `data\` into the new folder). Tax-library updates arrive as
seed JSON files — see `docs/MAINTENANCE.md`.

## Uninstall

Delete the folder. To remove all traces including data, delete `data\` too.
