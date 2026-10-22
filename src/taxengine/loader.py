"""Seed loader: validate JSON seed files and load them into tax_knowledge.db.

Idempotent: (code, version) pairs already present are skipped, never duplicated.
Cross-references may point at codes defined in the same file, earlier files,
or already in the database.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import db as dbmod
from .validate import (
    SeedError, validate_source, validate_legislation, validate_rule,
    validate_risk, validate_evidence, validate_procedure, validate_calc_table,
    validate_scenario,
)

JSON_FIELDS = {
    "tax_rules": ["taxpayer_types", "transaction_types", "applicability_conditions",
                  "exclusion_conditions", "required_inputs", "decision_logic",
                  "exceptions", "return_fields"],
    "legislation": [],
    "tax_risks": ["applicable_conditions", "risk_indicators", "required_information",
                  "source_codes"],
    "evidence": ["expected_information", "common_discrepancies"],
    "procedures": ["steps", "inputs_required", "documents_to_obtain",
                   "exception_conditions"],
    "calc_tables": ["taxpayer_types", "params"],
    "scenarios": ["trigger_facts", "expected_chain"],
    "sources": [],
}


def _t(value):
    """Textify: join lists into newline text, pass through the rest."""
    if isinstance(value, list):
        return "\n".join(str(x) for x in value)
    return value


def _j(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _known_codes(conn) -> dict:
    known = {}
    for table, code_col in [
        ("sources", "code"), ("legislation", "code"), ("tax_rules", "code"),
        ("tax_risks", "code"), ("evidence", "code"), ("procedures", "code"),
        ("calc_tables", "code"),
    ]:
        rows = conn.execute(f"SELECT {code_col} FROM {table}").fetchall()
        known[table] = {r[0] for r in rows}
    return known


def _batch_codes(batch: dict) -> dict:
    return {
        "sources": {s["code"] for s in batch.get("sources", [])},
        "legislation": {x["code"] for x in batch.get("legislation", [])},
        "rules": {x["code"] for x in batch.get("rules", [])},
        "risks": {x["code"] for x in batch.get("risks", [])},
        "evidence": {x["code"] for x in batch.get("evidence", [])},
        "procedures": {x["code"] for x in batch.get("procedures", [])},
        "calc_tables": {x["code"] for x in batch.get("calc_tables", [])},
    }


def _id_for(conn, table, code, version=None):
    if table == "tax_rules" or table == "calc_tables":
        row = conn.execute(
            f"SELECT id FROM {table} WHERE code=? AND version=?", (code, version or 1)
        ).fetchone()
    else:
        row = conn.execute(f"SELECT id FROM {table} WHERE code=?", (code,)).fetchone()
    return row["id"] if row else None


def load_seed_file(path: Path, conn=None) -> dict:
    """Validate and load one seed JSON file. Returns counts per entity."""
    path = Path(path)
    with open(path, "r", encoding="utf-8") as fh:
        batch = json.load(fh)
    if not isinstance(batch, dict) or "meta" not in batch:
        raise SeedError(f"{path.name}: top-level object with 'meta' is required")

    own_conn = conn is None
    conn = conn or dbmod.get_knowledge_db()
    try:
        db_known = _known_codes(conn)
        batch_known = _batch_codes(batch)
        # normalise: DB tables use tax_rules/tax_risks, validators use rules/risks
        known = {}
        for table_key in db_known:
            batch_key = {"tax_rules": "rules", "tax_risks": "risks"}.get(
                table_key, table_key)
            known[table_key] = (db_known.get(table_key, set())
                                | batch_known.get(batch_key, set()))
        known["rules"] = known.pop("tax_rules")
        known["risks"] = known.pop("tax_risks")

        counts = {k: 0 for k in
                  ["sources", "legislation", "rules", "risks", "evidence",
                   "procedures", "calc_tables", "scenarios"]}

        with conn:  # transaction
            for src in batch.get("sources", []):
                validate_source(src)
                if not _id_for(conn, "sources", src["code"]):
                    conn.execute(
                        """INSERT INTO sources(code,title,source_type,issuing_authority,
                           jurisdiction,reference_url,verified_date,notes)
                           VALUES (?,?,?,?,?,?,?,?)""",
                        (src["code"], src["title"], src["source_type"],
                         src.get("issuing_authority"), src["jurisdiction"],
                         src.get("reference_url"), src.get("verified_date"),
                         src.get("notes")))
                    counts["sources"] += 1

            for leg in batch.get("legislation", []):
                validate_legislation(leg, known)
                if not _id_for(conn, "legislation", leg["code"]):
                    conn.execute(
                        """INSERT INTO legislation(code,name,issuing_authority,jurisdiction,
                           provision,subsection,rule_description,effective_from,effective_to,
                           tax_year,amendment_history,source_code,source_verified_date,
                           review_status,version)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (leg["code"], leg["name"], leg["issuing_authority"],
                         leg["jurisdiction"], leg["provision"], leg.get("subsection"),
                         leg["rule_description"], leg["effective_from"],
                         leg.get("effective_to"), leg.get("tax_year"),
                         _t(leg.get("amendment_history")), leg.get("source_code"),
                         leg.get("source_verified_date"),
                         leg.get("review_status", "draft"), leg.get("version", 1)))
                    counts["legislation"] += 1
                    _index_fts(conn, "legislation", leg["code"],
                               f"{leg['name']} {leg['provision']} {leg.get('subsection','')}",
                               leg["rule_description"])

            for ev in batch.get("evidence", []):
                validate_evidence(ev, known)
                if not _id_for(conn, "evidence", ev["code"]):
                    conn.execute(
                        """INSERT INTO evidence(code,name,description,typical_source,
                           verification_procedure,reliability_notes,limitations,
                           expected_information,common_discrepancies,review_status)
                           VALUES (?,?,?,?,?,?,?,?,?,?)""",
                        (ev["code"], ev["name"], ev["description"],
                         ev.get("typical_source"), ev.get("verification_procedure"),
                         ev.get("reliability_notes"), ev.get("limitations"),
                         _j(ev.get("expected_information", [])),
                         _j(ev.get("common_discrepancies", [])),
                         ev.get("review_status", "draft")))
                    counts["evidence"] += 1
                    _index_fts(conn, "evidence", ev["code"], ev["name"], ev["description"])

            for pr in batch.get("procedures", []):
                validate_procedure(pr, known)
                if not _id_for(conn, "procedures", pr["code"]):
                    conn.execute(
                        """INSERT INTO procedures(code,name,category,objective,
                           triggering_condition,steps,inputs_required,documents_to_obtain,
                           calculation_method,expected_result,exception_conditions,
                           followup_procedure,legislation_ref,review_status)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (pr["code"], pr["name"], pr["category"], pr["objective"],
                         pr.get("triggering_condition"), _j(pr["steps"]),
                         _j(pr.get("inputs_required", [])),
                         _j(_merge_docs(pr)),
                         pr.get("calculation_method"), pr.get("expected_result"),
                         _j(pr.get("exception_conditions", [])),
                         pr.get("followup_procedure"), pr.get("legislation_ref"),
                         pr.get("review_status", "draft")))
                    counts["procedures"] += 1
                    _index_fts(conn, "procedure", pr["code"], pr["name"], pr["objective"])

            for ct in batch.get("calc_tables", []):
                validate_calc_table(ct, known)
                version = ct.get("version", 1)
                if _id_for(conn, "calc_tables", ct["code"], version) is None:
                    conn.execute(
                        """INSERT INTO calc_tables(code,version,name,kind,tax_category,
                           jurisdiction,taxpayer_types,params,legislation_ref,
                           effective_from,effective_to,tax_year,verification_status)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (ct["code"], version, ct["name"], ct["kind"],
                         ct["tax_category"], ct.get("jurisdiction", "federal"),
                         _j(ct.get("taxpayer_types", [])), _j(ct["params"]),
                         ct.get("legislation_ref"), ct["effective_from"],
                         ct.get("effective_to"), ct.get("tax_year"),
                         ct.get("verification_status", "draft")))
                    counts["calc_tables"] += 1

            for rk in batch.get("risks", []):
                validate_risk(rk, known)
                if not _id_for(conn, "tax_risks", rk["code"]):
                    conn.execute(
                        """INSERT INTO tax_risks(code,title,description,root_cause,
                           tax_category,jurisdiction,potential_financial_effect,
                           exposure_note,penalty_implications,applicable_conditions,
                           risk_indicators,required_information,followup_action,
                           source_codes,review_status)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (rk["code"], rk["title"], rk["description"],
                         rk.get("root_cause"), rk["tax_category"],
                         rk.get("jurisdiction", "federal"),
                         rk.get("potential_financial_effect"), rk.get("exposure_note"),
                         rk.get("penalty_implications"),
                         _j(rk.get("applicable_conditions", [])),
                         _j(rk.get("risk_indicators", [])),
                         _j(rk.get("required_information", [])),
                         rk.get("followup_action"),
                         _j(rk.get("source_codes", [])),
                         rk.get("review_status", "draft")))
                    counts["risks"] += 1
                    _index_fts(conn, "risk", rk["code"], rk["title"], rk["description"])

            for rule in batch.get("rules", []):
                validate_rule(rule, known)
                version = rule.get("version", 1)
                if _id_for(conn, "tax_rules", rule["code"], version) is None:
                    sup_id = None
                    if rule.get("supersedes_code"):
                        sup_id = _id_for(conn, "tax_rules",
                                         rule["supersedes_code"], version - 1)
                    cur = conn.execute(
                        """INSERT INTO tax_rules(code,version,title,tax_category,
                           jurisdiction,taxpayer_types,triggering_transaction,
                           transaction_types,applicability_conditions,
                           exclusion_conditions,required_inputs,decision_logic,
                           expected_treatment,calculation_method,exceptions,
                           consequences,return_fields,effective_from,effective_to,
                           verification_status,reviewer,review_date,review_notes,
                           interpretation_note,supersedes_id)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (rule["code"], version, rule["title"], rule["tax_category"],
                         rule["jurisdiction"], _j(rule["taxpayer_types"]),
                         rule["triggering_transaction"], _j(rule["transaction_types"]),
                         _j(rule["applicability_conditions"]),
                         _j(rule.get("exclusion_conditions", [])),
                         _j(rule.get("required_inputs", [])),
                         _j(rule["decision_logic"]), rule["expected_treatment"],
                         rule.get("calculation_method"), _j(rule.get("exceptions", [])),
                         rule.get("consequences"), _j(rule.get("return_fields", [])),
                         rule["effective_from"], rule.get("effective_to"),
                         rule.get("verification_status", "draft"),
                         rule.get("reviewer"), rule.get("review_date"),
                         rule.get("review_notes"), rule.get("interpretation_note"),
                         sup_id))
                    rule_id = cur.lastrowid
                    counts["rules"] += 1
                    for lc in rule.get("legislation_codes", []):
                        lid = _id_for(conn, "legislation", lc)
                        if lid:
                            conn.execute(
                                "INSERT OR IGNORE INTO rule_legislation(rule_id,legislation_id) VALUES (?,?)",
                                (rule_id, lid))
                    for rkc in rule.get("risk_codes", []):
                        rid = _id_for(conn, "tax_risks", rkc)
                        if rid:
                            conn.execute(
                                "INSERT OR IGNORE INTO rule_risks(rule_id,risk_id) VALUES (?,?)",
                                (rule_id, rid))
                    for ec in rule.get("evidence_codes", []):
                        eid = _id_for(conn, "evidence", ec)
                        if eid:
                            conn.execute(
                                "INSERT OR IGNORE INTO rule_evidence(rule_id,evidence_id) VALUES (?,?)",
                                (rule_id, eid))
                    for pc in rule.get("procedure_codes", []):
                        pid = _id_for(conn, "procedures", pc)
                        if pid:
                            conn.execute(
                                "INSERT OR IGNORE INTO rule_procedures(rule_id,procedure_id) VALUES (?,?)",
                                (rule_id, pid))
                    for cc in rule.get("calc_codes", []):
                        cid = _id_for(conn, "calc_tables", cc)
                        if cid:
                            conn.execute(
                                "INSERT OR IGNORE INTO rule_calcs(rule_id,calc_id) VALUES (?,?)",
                                (rule_id, cid))
                    _index_fts(conn, "rule", rule["code"], rule["title"],
                               f"{rule['code']}\n{rule['tax_category']}\n"
                               f"{rule['triggering_transaction']}\n"
                               f"{rule['expected_treatment']}")

            for scn in batch.get("scenarios", []):
                validate_scenario(scn, known)
                if not _id_for(conn, "scenarios", scn["code"]):
                    conn.execute(
                        """INSERT INTO scenarios(code,name,category,description,
                           trigger_facts,expected_chain,accounting_vs_tax,review_status)
                           VALUES (?,?,?,?,?,?,?,?)""",
                        (scn["code"], scn["name"], scn["category"], scn["description"],
                         _j(scn["trigger_facts"]), _j(scn["expected_chain"]),
                         scn.get("accounting_vs_tax"),
                         scn.get("review_status", "draft")))
                    counts["scenarios"] += 1
        return counts
    finally:
        if own_conn:
            conn.close()


def _merge_docs(pr: dict) -> list:
    """Combine explicit documents_to_obtain with evidence_codes (dedup, order kept)."""
    docs = list(pr.get("documents_to_obtain", []) or [])
    for ec in pr.get("evidence_codes", []) or []:
        if ec not in docs:
            docs.append(ec)
    return docs


def _index_fts(conn, entity_type, entity_code, title, body):    conn.execute(
        "INSERT INTO kb_fts(entity_type, entity_code, title, body) VALUES (?,?,?,?)",
        (entity_type, entity_code, title or "", body or ""))


def rebuild_fts(conn=None):
    """Rebuild the full-text index from all knowledge tables."""
    own = conn is None
    conn = conn or dbmod.get_knowledge_db()
    try:
        with conn:
            conn.execute("DELETE FROM kb_fts")
            for row in conn.execute("SELECT code, tax_category, title, triggering_transaction, expected_treatment FROM tax_rules"):
                _index_fts(conn, "rule", row["code"], row["title"],
                           f"{row['code']}\n{row['tax_category']}\n"
                           f"{row['triggering_transaction'] or ''}\n"
                           f"{row['expected_treatment'] or ''}")
            for row in conn.execute("SELECT code, title, description FROM tax_risks"):
                _index_fts(conn, "risk", row["code"], row["title"], row["description"] or "")
            for row in conn.execute("SELECT code, name, rule_description, provision FROM legislation"):
                _index_fts(conn, "legislation", row["code"], f"{row['name']} {row['provision']}",
                           row["rule_description"] or "")
            for row in conn.execute("SELECT code, name, description FROM evidence"):
                _index_fts(conn, "evidence", row["code"], row["name"], row["description"] or "")
            for row in conn.execute("SELECT code, name, objective FROM procedures"):
                _index_fts(conn, "procedure", row["code"], row["name"], row["objective"] or "")
    finally:
        if own:
            conn.close()


def load_seed_dir(seed_dir: Path, conn=None) -> dict:
    """Load every *.json in a directory (sorted). Returns merged counts."""
    seed_dir = Path(seed_dir)
    total = {}
    files = sorted(seed_dir.glob("*.json"))
    for f in files:
        counts = load_seed_file(f, conn=conn)
        for k, v in counts.items():
            total[k] = total.get(k, 0) + v
    return total
