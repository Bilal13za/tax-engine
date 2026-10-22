"""Generate docs/SOURCE_REGISTER.md and docs/VERIFIED_VS_UNVERIFIED.md
from the knowledge database. Run after every seed load:

    python scripts/generate_registers.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from taxengine import db  # noqa: E402

PROJECT = Path(__file__).resolve().parent.parent


def gen_source_register(conn) -> str:
    lines = ["# Tax Source Register",
             "",
             "Generated from `tax_knowledge.db`. Every legal or professional",
             "source cited by any rule, with its verification date.",
             ""]
    rows = conn.execute(
        "SELECT * FROM sources ORDER BY jurisdiction, code").fetchall()
    if not rows:
        lines.append("_No sources registered yet._")
    current_jur = None
    for r in rows:
        if r["jurisdiction"] != current_jur:
            current_jur = r["jurisdiction"]
            lines += ["", f"## {current_jur.title()}", ""]
        lines.append(f"### `{r['code']}` — {r['title']}")
        lines.append(f"- Type: {r['source_type']}")
        lines.append(f"- Issued by: {r['issuing_authority'] or '—'}")
        if r["reference_url"]:
            lines.append(f"- Reference: {r['reference_url']}")
        lines.append(f"- Verified: {r['verified_date'] or 'not yet verified'}")
        if r["notes"]:
            lines.append(f"- Notes: {r['notes']}")
        lines.append("")
    return "\n".join(lines)


def gen_verified_list(conn) -> str:
    lines = ["# Verified vs Unverified Rules",
             "",
             "Generated from `tax_knowledge.db`. Only `verified` rules were",
             "checked against an authoritative source; everything else is",
             "indicative and is excluded from definitive calculations.",
             ""]
    rows = conn.execute(
        """SELECT code, version, title, tax_category, jurisdiction,
                  verification_status, effective_from, effective_to,
                  reviewer, review_date, review_notes
           FROM tax_rules ORDER BY verification_status, code, version"""
    ).fetchall()
    by_status: dict[str, list] = {}
    for r in rows:
        by_status.setdefault(r["verification_status"], []).append(r)
    order = ["verified", "under_review", "draft", "superseded", "retired"]
    for status in order:
        items = by_status.get(status, [])
        lines += ["", f"## {status.replace('_', ' ').title()} ({len(items)})", ""]
        if not items:
            lines.append("_None._")
            continue
        for r in items:
            eff = f"{r['effective_from']} → {r['effective_to'] or 'present'}"
            lines.append(f"- `{r['code']}` v{r['version']} — {r['title']} "
                         f"[{r['tax_category']} · {r['jurisdiction']} · {eff}]")
            if status == "verified":
                lines.append(f"  Verified by {r['reviewer'] or '?'} on "
                             f"{r['review_date'] or '?'}")
            elif r["review_notes"]:
                lines.append(f"  Note: {r['review_notes']}")
    lines += ["", "## Calculation tables", ""]
    for r in conn.execute(
            "SELECT code, version, name, verification_status, effective_from,"
            " effective_to, legislation_ref FROM calc_tables "
            "ORDER BY code, version"):
        eff = f"{r['effective_from']} → {r['effective_to'] or 'present'}"
        lines.append(f"- `{r['code']}` v{r['version']} — {r['name']} "
                     f"[{r['verification_status']} · {eff}] "
                     f"({r['legislation_ref'] or 'no provision cited'})")
    lines += ["", "## Legislation", ""]
    for r in conn.execute(
            "SELECT code, name, provision, subsection, review_status,"
            " effective_from, effective_to FROM legislation "
            "ORDER BY name, provision"):
        eff = f"{r['effective_from']} → {r['effective_to'] or 'present'}"
        sub = f" {r['subsection']}" if r["subsection"] else ""
        lines.append(f"- `{r['code']}` — {r['name']}, {r['provision']}{sub} "
                     f"[{r['review_status']} · {eff}]")
    return "\n".join(lines)


def main():
    conn = db.get_knowledge_db()
    try:
        (PROJECT / "docs" / "SOURCE_REGISTER.md").write_text(
            gen_source_register(conn), encoding="utf-8")
        (PROJECT / "docs" / "VERIFIED_VS_UNVERIFIED.md").write_text(
            gen_verified_list(conn), encoding="utf-8")
        print("Wrote docs/SOURCE_REGISTER.md and docs/VERIFIED_VS_UNVERIFIED.md")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
