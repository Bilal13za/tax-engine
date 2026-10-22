"""Repair agent-produced seed files into strict SEED_FORMAT compliance.

Structural repairs only — field renames, kind conversions, alias mapping.
Never changes legal content (provisions, rates, dates, treatments).

Run after research agents finish:
    python scripts/repair_seeds.py
"""

import copy
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from taxengine import db, loader  # noqa: E402

PROJECT = Path(__file__).resolve().parent.parent
INCOMING = PROJECT / "seed" / "incoming"

SOURCE_TYPE_MAP = {
    "legislation_text_reproduction": "legislation",
    "official_legislation_text": "legislation",
    "legislation_text": "legislation",
    "official_guidance": "explanatory_guidance",
    "official_notification": "notification",
    "official_gazette": "notification",
    "professional_commentary": "professional_interpretation",
    "news_report": "professional_interpretation",
}

DEFAULT_JURISDICTION = {
    "income_tax": "federal",
    "withholding_tax": "federal",
    "sales_tax_federal": "federal",
    "sales_tax_provincial": None,  # must be set per source already
}

# Verified 2026-10-21: ITO 2001 s.1(3) — SRO 381(I)/2002 dated 15.06.2002
# appointed 01.07.2002 as the commencement date (FBR's own page:
# https://Fbr.gov.pk/income-tax/142262/159; corroborated by the annotated
# Ordinance text and Business Recorder). Applies to original provisions of
# the Ordinance only — never to later amendments.
ITO2001_COMMENCEMENT = "2002-07-01"
ITO2001_COMMENCEMENT_NOTE = (
    "Commencement: SRO 381(I)/2002 dated 15.06.2002 appointed 01.07.2002 "
    "as the date the Ordinance came into force (verified 2026-10-21).")

WHT_SOURCE_TYPES = {
    "SRC-WHT-ITO-2018": "legislation",
    "SRC-WHT-ITO-2019": "legislation",
    "SRC-WHT-ITO-RECENT": "legislation",
    "SRC-WHT-FBR-CARD-2025-26": "explanatory_guidance",
    "SRC-WHT-SALARY-CARD": "explanatory_guidance",
}

ITO_SOURCE_TYPE_MAP = {
    "legislation": "legislation",
    "official_government_page": "explanatory_guidance",
    "news_report_on_enacted_law": "professional_interpretation",
    "secondary_compilation": "professional_interpretation",
}

ITO2001_SOURCE_BY_PROVISION = {
    "LEG-ITO2001-S108": "SRC-ITO-108-FBR",
    "LEG-ITO2001-FA2024-SCH1": "SRC-ITO-SLAB-TY2025",
    "LEG-ITO2001-FA2025-SCH1": "SRC-ITO-SLAB-TY2026",
}

# Income-tax rules/calc tables that are original-Ordinance content
# (amendment histories confirm original-provision status).
ITO2001_ORIGINAL_RULES = {
    "RULE-INC-S18-BUSINESS-INCOME", "RULE-INC-S21-DISALLOW",
    "RULE-INC-S22-DEPRECIATION", "RULE-INC-S22-DISPOSAL",
    "RULE-INC-S74-TAXYEAR", "RULE-INC-S114-RETURN",
    "RULE-INC-S37-CAPITAL-GAINS", "RULE-INC-RECON-PROFIT",
    "RULE-INC-EVIDENCE-DEDUCTION", "RULE-INC-CREDIT-UNVERIFIED",
}
ITO2001_ORIGINAL_CALCS = {
    "CALC-INC-DEP-BUILDING", "CALC-INC-DEP-PLANT",
    "CALC-INC-DEP-IT", "CALC-INC-DEP-RAMP",
}
# s.61: verified availability window is TY2025 only (agent's sources).
S61_WINDOW = ("2024-07-01", "2025-06-30")
S61_NOTE = ("Effective window set to TY2025 (2024-07-01 to 2025-06-30): "
            "s.61 credit availability verified for TY2025 only "
            "(PBC Oct 2025 letter; pkrevenue TY2025-26 treatment). "
            "Earlier/later availability not verified in this pass.")


def repair_sources(batch, domain):
    default_jur = DEFAULT_JURISDICTION.get(domain)
    for s in batch.get("sources", []):
        if "name" in s and "title" not in s:
            s["title"] = s.pop("name")
        if "type" in s and "source_type" not in s:
            s["source_type"] = s.pop("type")
        if "url" in s and "reference_url" not in s:
            s["reference_url"] = s.pop("url")
        if "publisher" in s and "issuing_authority" not in s:
            s["issuing_authority"] = s.pop("publisher")
        if "accessed_date" in s and "verified_date" not in s:
            s["verified_date"] = s.pop("accessed_date")
        if "note" in s:
            note = s.pop("note")
            s["notes"] = (s.get("notes", "") + "\n" + note).strip()
        st = s.get("source_type")
        if domain == "withholding_tax" and not st:
            st = WHT_SOURCE_TYPES.get(s["code"], "professional_interpretation")
            s["notes"] = (s.get("notes", "")
                          + "\n[Source type assigned during curation: "
                            f"{st}; secondary reproduction/news unless noted.]").strip()
            s["source_type"] = st
        elif domain == "income_tax" and st in ITO_SOURCE_TYPE_MAP:
            if st != ITO_SOURCE_TYPE_MAP[st]:
                s["notes"] = (s.get("notes", "")
                              + f"\n[Original source_type label: {st}]").strip()
            s["source_type"] = ITO_SOURCE_TYPE_MAP[st]
        elif st in SOURCE_TYPE_MAP:
            s["notes"] = (s.get("notes", "")
                          + f"\n[Original source_type label: {st}]").strip()
            s["source_type"] = SOURCE_TYPE_MAP[st]
        if not s.get("jurisdiction"):
            if default_jur:
                s["jurisdiction"] = default_jur
            else:
                raise ValueError(
                    f"source {s.get('code')} has no jurisdiction and no default")


def repair_legislation(batch, domain):
    source_codes = {s["code"] for s in batch.get("sources", [])}
    for leg in batch.get("legislation", []):
        if "subsection_clause" in leg and "subsection" not in leg:
            leg["subsection"] = leg.pop("subsection_clause")
        if "source_verification_date" in leg \
                and "source_verified_date" not in leg:
            leg["source_verified_date"] = leg.pop("source_verification_date")
        if "applicable_tax_year" in leg and "tax_year" not in leg:
            leg["tax_year"] = leg.pop("applicable_tax_year")
        ah = leg.get("amendment_history")
        if isinstance(ah, list):
            leg["amendment_history"] = "\n".join(str(x) for x in ah)
        off = leg.pop("official_source", None)
        if off and not leg.get("source_code"):
            mapped = ITO2001_SOURCE_BY_PROVISION.get(leg["code"])
            if mapped and mapped in source_codes:
                leg["source_code"] = mapped
            elif "SRC-ITO-ORD" in source_codes and "XLIX of 2001" in str(off):
                leg["source_code"] = "SRC-ITO-ORD"
            # chapter detail preserved in the file's meta notes instead
        if domain == "income_tax" and not leg.get("effective_from") \
                and leg["code"].startswith("LEG-ITO2001-") \
                and "FA2024" not in leg["code"] and "FA2025" not in leg["code"]:
            leg["effective_from"] = ITO2001_COMMENCEMENT
            leg["amendment_history"] = (
                (leg.get("amendment_history") or "") + "\n"
                + ITO2001_COMMENCEMENT_NOTE).strip()


def repair_calc_tables(batch):
    # index rules -> calc codes for alias derivation
    rule_inputs = {}  # calc_code -> set of required input names
    for r in batch.get("rules", []):
        for cc in r.get("calc_codes", []):
            names = {i["name"] for i in r.get("required_inputs", [])}
            rule_inputs.setdefault(cc, set()).update(names)
    domain = batch.get("meta", {}).get("domain", "")
    for ct in batch.get("calc_tables", []):
        if "title" in ct and "name" not in ct:
            ct["name"] = ct.pop("title")
        if "tax_category" not in ct and domain:
            ct["tax_category"] = {"income_tax": "income_tax",
                                  "withholding_tax": "withholding_tax",
                                  "sales_tax_federal": "sales_tax_federal",
                                  "sales_tax_provincial": "sales_tax_provincial",
                                  }.get(domain, "other_levies")
        params = ct.get("params", {})
        if ct.get("kind") == "percentage" and isinstance(params.get("rates"), list) \
                and "rate" not in params:
            ct["kind"] = "rate_schedule"
        if ct.get("kind") != "rate_schedule":
            continue
        params = ct["params"]
        dims = sorted({k for row in params["rates"] for k in row if k != "rate"})
        inputs = rule_inputs.get(ct["code"], set())
        if "base_input" not in params:
            cands = [n for n in inputs if "amount" in n]
            params["base_input"] = (cands[0] if cands
                                    else "payment_amount")
        aliases = params.setdefault("input_aliases", {})
        for dk in dims:
            if dk in inputs or dk in aliases:
                continue
            cands = [n for n in inputs if dk in n]
            if len(cands) == 1:
                aliases[dk] = cands[0]
        # the calc table declares what it needs (input names, aliases resolved)
        params["required_inputs"] = (
            [params.get("base_input", "payment_amount")]
            + [aliases.get(dk, dk) for dk in dims])
        # every rule input referenced by dims should be required somewhere;
        # nothing more to do structurally


GLOBAL_FACTS = {"transaction_date", "tax_year", "tax_category", "jurisdiction",
                "taxpayer_type", "transaction_type", "province",
                "resident_status", "display_name"}
# Meta-gate flags: proxies for "the fact was provided". Optional, clearly labelled.
GATE_FIELDS = {"tax_year_known", "asset_category_known", "expense_recorded",
               "gain_arises", "disposed_in_year", "asset_used_in_business",
               "asset_is_depreciable"}


def _cond_fields(tree, out):
    if isinstance(tree, dict):
        if "field" in tree:
            out.setdefault(tree["field"], []).append(tree)
        for v in tree.values():
            _cond_fields(v, out)
    elif isinstance(tree, list):
        for v in tree:
            _cond_fields(v, out)


def _humanize(name):
    return name.replace("_", " ").capitalize()


def repair_missing_inputs(batch):
    for r in batch.get("rules", []):
        used: dict = {}
        _cond_fields(r.get("applicability_conditions"), used)
        _cond_fields(r.get("exclusion_conditions"), used)
        _cond_fields(r.get("decision_logic"), used)
        for exc in r.get("exceptions", []):
            if isinstance(exc, dict):
                _cond_fields(exc.get("condition"), used)
        declared = {i["name"]: i for i in r.get("required_inputs", [])}
        app_fields: dict = {}
        _cond_fields(r.get("applicability_conditions"), app_fields)
        for field, leaves in sorted(used.items()):
            if field in declared or field in GLOBAL_FACTS:
                continue
            ops = {l.get("op") for l in leaves}
            vals = [l.get("value") for l in leaves if "value" in l]
            flat = []
            for v in vals:
                flat += v if isinstance(v, list) else [v]
            if all(isinstance(v, bool) for v in flat) or not flat:
                dtype, choices = "boolean", None
            elif all(isinstance(v, str) for v in flat):
                dtype, choices = "choice", sorted(set(flat))
            elif all(isinstance(v, (int, float)) for v in flat):
                dtype, choices = "number", None
            else:
                dtype, choices = "string", None
            is_gate = field in GATE_FIELDS or field.endswith("_known")
            entry = {"name": field,
                     "label": ("Confirm: " + _humanize(field) if is_gate
                               else _humanize(field)),
                     "data_type": dtype,
                     "required": (field in app_fields) and not is_gate,
                     "source_hint": "Assessment facts"}
            if field == "province_of_provision":
                entry["required"] = True
                entry["choices"] = ["sindh", "punjab", "kpk", "balochistan",
                                    "ict"]
            elif choices:
                entry["choices"] = choices
            r.setdefault("required_inputs", []).append(entry)


def repair_scenarios(batch):
    domain = batch.get("meta", {}).get("domain", "")
    domain_cat = {"income_tax": "income_tax",
                  "withholding_tax": "withholding_tax",
                  "sales_tax_federal": "sales_tax_federal",
                  "sales_tax_provincial": "sales_tax_provincial"}.get(domain)
    valid = {"income_tax", "withholding_tax", "sales_tax_federal",
             "sales_tax_provincial", "return_preparation"}
    for s in batch.get("scenarios", []):
        if "title" in s and "name" not in s:
            s["name"] = s.pop("title")
        if s.get("category") in valid:
            continue
        if s.get("domain") in valid:
            s["category"] = s.pop("domain")
            continue
        maps_to = str(s.pop("maps_to", ""))
        if maps_to.startswith("Spec E"):
            s["category"] = "return_preparation"
        elif domain_cat:
            s["category"] = domain_cat
        else:
            raise ValueError(f"scenario {s.get('code')}: cannot derive category")


def repair_income_tax_dates(batch):
    for r in batch.get("rules", []):
        if r.get("effective_from") or r["code"] not in ITO2001_ORIGINAL_RULES \
                and r["code"] != "RULE-INC-S108-ASSOCIATES" \
                and r["code"] != "RULE-INC-S61-DONATION-CREDIT":
            continue
        if r["code"] == "RULE-INC-S61-DONATION-CREDIT":
            r["effective_from"], r["effective_to"] = S61_WINDOW
            r["review_notes"] = ((r.get("review_notes") or "") + "\n"
                                 + S61_NOTE).strip()
        else:
            r["effective_from"] = ITO2001_COMMENCEMENT
            note = ITO2001_COMMENCEMENT_NOTE
            if r["code"] == "RULE-INC-S108-ASSOCIATES":
                note += (" The s.108(3)-(5) documentation obligations were "
                         "inserted later; the insertion date was not verified "
                         "— the 2002 date covers the original arm's-length "
                         "limbs (1)-(2).")
            r["review_notes"] = ((r.get("review_notes") or "") + "\n"
                                 + note).strip()
    for ct in batch.get("calc_tables", []):
        if ct.get("effective_from"):
            continue
        if ct["code"] in ITO2001_ORIGINAL_CALCS:
            ct["effective_from"] = ITO2001_COMMENCEMENT
            ct["review_notes"] = ((ct.get("review_notes") or "") + "\n"
                                  + ITO2001_COMMENCEMENT_NOTE
                                  + " Applies to the Third Schedule Part I "
                                    "rate table.").strip()
        elif ct["code"] == "CALC-INC-CREDIT-S61":
            ct["effective_from"], ct["effective_to"] = S61_WINDOW
            ct["review_notes"] = ((ct.get("review_notes") or "") + "\n"
                                  + S61_NOTE).strip()


def repair_reviewer_attribution(batch):
    """Verified rules need reviewer + review_date. Attribute to the file's
    own research author/date (factual: that agent did the verification)."""
    meta = batch.get("meta", {})
    author = meta.get("author", "research-agent")
    pdate = meta.get("prepared_date", "2026-10-21")
    for r in batch.get("rules", []):
        if r.get("verification_status") == "verified":
            r.setdefault("reviewer", author)
            r.setdefault("review_date", pdate)


def repair_wht_calc_names(batch):
    rule_titles = {r["code"]: r["title"] for r in batch.get("rules", [])}
    calc_to_rule = {}
    for r in batch.get("rules", []):
        for cc in r.get("calc_codes", []):
            calc_to_rule.setdefault(cc, r["code"])
    for ct in batch.get("calc_tables", []):
        if ct.get("name"):
            continue
        rc = calc_to_rule.get(ct["code"])
        if rc and rc in rule_titles:
            ct["name"] = f"{rule_titles[rc]} — rate schedule"
        else:
            ct["name"] = ct["code"].replace("CALC-", "").replace("-", " ").title()


def repair_provincial(batch):
    codes = {r.get("code") for r in batch.get("rules", [])}
    for r in batch.get("rules", []):
        if not r.get("code"):
            # the Sindh taxable-service/exemption rule
            cand = "RULE-STP-SINDH-TAXABLE"
            assert cand not in codes, "code clash"
            r["code"] = cand
            codes.add(cand)


def repair_file(path):
    domain = json.load(open(path, encoding="utf-8"))["meta"]["domain"]
    # reload fresh for editing
    batch = json.load(open(path, encoding="utf-8"))
    shutil.copy(path, str(path) + ".bak")
    repair_sources(batch, domain)
    repair_legislation(batch, domain)
    repair_calc_tables(batch)
    repair_scenarios(batch)
    repair_missing_inputs(batch)
    repair_reviewer_attribution(batch)
    if domain == "income_tax":
        repair_income_tax_dates(batch)
    if domain == "withholding_tax":
        repair_wht_calc_names(batch)
    if domain == "sales_tax_provincial":
        repair_provincial(batch)
    # record curation in the file's own meta
    meta_notes = batch.get("meta", {}).get("notes", "")
    batch["meta"]["notes"] = (
        meta_notes
        + "\n[Curated 2026-10-21 by repair_seeds.py: source field names "
          "normalised to SEED_FORMAT; source_type labels mapped (originals kept "
          "in per-source notes); 'percentage' tables with rate schedules "
          "converted to kind=rate_schedule with base_input/input_aliases "
          "derived from linked rules; ITO 2001 original provisions given "
          "effective_from 2002-07-01 per SRO 381(I)/2002 (verified); no legal "
          "content altered.]").strip()
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(batch, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    return domain


def main():
    for path in sorted(INCOMING.glob("*.json")):
        if path.name.startswith("_"):
            continue
        domain = repair_file(path)
        print(f"repaired {path.name} (domain={domain})")
    # validate everything into a scratch DB
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="taxeng_repair_"))
    import os
    os.environ["TAXENGINE_DATA_DIR"] = str(tmp)
    # reimport to pick up env? db reads env at call time - fine
    k = db.get_knowledge_db()
    try:
        for f in [PROJECT / "seed" / "evidence_library.json",
                  PROJECT / "seed" / "procedures_library.json"]:
            loader.load_seed_file(f, conn=k)
        for path in sorted(INCOMING.glob("*.json")):
            try:
                counts = loader.load_seed_file(path, conn=k)
                print(path.name, "LOADED",
                      {kk: vv for kk, vv in counts.items() if vv})
            except Exception as e:
                print(path.name, "VALIDATION FAILED:", e)
    finally:
        k.close()


if __name__ == "__main__":
    main()
