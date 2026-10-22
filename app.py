"""Pakistan Tax Risk, Rules and Evidence Engine — local Streamlit interface.

Modules:
  A  Taxpayer Profile        B  Transaction Assessment      C  Tax Rule Lookup
  D  Tax Risk Explorer       E  Tax Calculation Workbench   F  Tax Reconciliation
  G  Evidence Tracker        H  Export

Offline: everything runs on this computer (SQLite + local web server).
Deterministic: no AI/LLM at runtime — rules, decision tables and calculations
come from the versioned knowledge database.
"""

import io
import json
import sys
from datetime import date
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from taxengine import (  # noqa: E402
    calc as calcmod,
    db,
    decision,
    export as exportmod,
    reconcile,
    search as searchmod,
)

st.set_page_config(
    page_title="Pakistan Tax Rules & Evidence Engine",
    page_icon="⚖️",
    layout="wide",
)

kconn = db.get_knowledge_db()
wconn = db.get_workdata_db()


def _bootstrap_knowledge():
    """First-run: load the bundled seed library if the DB is empty."""
    n = kconn.execute("SELECT COUNT(*) c FROM tax_rules").fetchone()["c"]
    if n:
        return
    from pathlib import Path as _P
    from taxengine import loader as _loader
    seed_dir = _P(__file__).resolve().parent / "seed"
    for name in ("evidence_library.json", "procedures_library.json"):
        p = seed_dir / name
        if p.exists():
            _loader.load_seed_file(p, conn=kconn)
    incoming = seed_dir / "incoming"
    if incoming.is_dir():
        for p in sorted(incoming.glob("*.json")):
            _loader.load_seed_file(p, conn=kconn)


_bootstrap_knowledge()

TAX_CATEGORIES = [
    ("income_tax", "Income Tax (Federal)"),
    ("withholding_tax", "Withholding Tax (Federal)"),
    ("sales_tax_federal", "Sales Tax (Federal)"),
    ("customs", "Customs Duties (Federal)"),
    ("sales_tax_provincial", "Sales Tax on Services (Provincial)"),
    ("provincial_other", "Other Provincial Taxes/Duties"),
    ("other_levies", "Other Levies"),
]
JURISDICTIONS = ["federal", "punjab", "sindh", "kpk", "balochistan",
                 "ict", "gb", "ajk"]
TAXPAYER_TYPES = ["individual", "aop", "company", "other"]
STATUSES = ["draft", "under_review", "verified", "superseded", "retired"]


def _j(value, default):
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return default
    return value


def kb_counts():
    rules = kconn.execute(
        "SELECT verification_status, COUNT(*) c FROM tax_rules GROUP BY 1"
    ).fetchall()
    return {r["verification_status"]: r["c"] for r in rules}


# ---------------------------------------------------------------- sidebar ---
st.sidebar.title("⚖️ Tax Rules & Evidence Engine")
st.sidebar.caption("Pakistan · offline · deterministic (no AI at runtime)")
counts = kb_counts()
st.sidebar.caption(
    "Knowledge base: " +
    ", ".join(f"{v} {k}" for k, v in sorted(counts.items())) or "empty — load seed files"
)
module = st.sidebar.radio(
    "Module",
    ["A · Taxpayer Profile", "B · Transaction Assessment",
     "C · Tax Rule Lookup", "D · Tax Risk Explorer",
     "E · Calculation Workbench", "F · Reconciliation",
     "G · Evidence Tracker", "H · Export"],
)
st.sidebar.divider()
st.sidebar.caption(
    "Educational tool — not tax advice. Only rules marked **verified** were "
    "checked against an authoritative source; draft rules are indicative only."
)

if "profile_id" not in st.session_state:
    st.session_state.profile_id = None
if "assessment_id" not in st.session_state:
    st.session_state.assessment_id = None


def profile_options():
    return [(r["id"], f"{r['profile_code']} — {r['display_name']}")
            for r in wconn.execute(
                "SELECT id, profile_code, display_name FROM taxpayer_profiles "
                "ORDER BY profile_code")]


def assessment_options():
    return [(r["id"], f"#{r['id']} {r['title']}")
            for r in wconn.execute(
                "SELECT id, title FROM assessments ORDER BY id DESC LIMIT 100")]


def pick_profile_selector(key="profile_pick"):
    opts = profile_options()
    labels = ["— none —"] + [lbl for _, lbl in opts]
    ids = [None] + [i for i, _ in opts]
    cur = st.session_state.profile_id
    idx = ids.index(cur) if cur in ids else 0
    sel = st.selectbox("Active taxpayer profile", labels, index=idx, key=key)
    st.session_state.profile_id = ids[labels.index(sel)]
    return st.session_state.profile_id


def get_profile(pid):
    if not pid:
        return {}
    r = wconn.execute("SELECT * FROM taxpayer_profiles WHERE id=?", (pid,)).fetchone()
    return dict(r) if r else {}


# ============================================================ Module A ======
if module.startswith("A"):
    st.header("A · Taxpayer Profile")
    pick_profile_selector()
    st.subheader("Create profile")
    with st.form("new_profile"):
        c1, c2 = st.columns(2)
        with c1:
            pcode = st.text_input("Profile code *", placeholder="ABC-CO-2026")
            dname = st.text_input("Display name *", placeholder="ABC (Pvt) Ltd")
            ttype = st.selectbox("Taxpayer type *", TAXPAYER_TYPES)
            rstatus = st.selectbox("Resident status",
                                   ["", "resident", "non_resident"])
            tyear = st.text_input("Tax year *", value="2026")
            prov = st.selectbox("Province/territory",
                                [""] + JURISDICTIONS[1:])
        with c2:
            activity = st.text_input("Business activity")
            industry = st.text_input("Industry")
            ap_from = st.date_input("Accounting period from",
                                    value=date(2025, 7, 1))
            ap_to = st.date_input("Accounting period to", value=date(2026, 6, 30))
            fed_reg = st.checkbox("Federal (income tax) registered")
            stax_reg = st.checkbox("Sales tax registered")
            stax_jur = st.selectbox("Sales tax jurisdiction",
                                    [""] + ["federal"] + JURISDICTIONS[1:6])
        regimes = st.multiselect("Applicable tax regimes",
                                 [c for c, _ in TAX_CATEGORIES])
        wht_obl = st.text_input("Withholding obligations",
                                placeholder="e.g. prescribed person u/s 153")
        ev_codes = [r["code"] for r in kconn.execute(
            "SELECT code FROM evidence ORDER BY code")]
        avail = st.multiselect("Available records (evidence held)", ev_codes)
        notes = st.text_area("Notes")
        if st.form_submit_button("Save profile"):
            if not pcode or not dname or not tyear:
                st.error("Profile code, display name and tax year are required.")
            else:
                try:
                    wconn.execute(
                        """INSERT INTO taxpayer_profiles
                           (profile_code, display_name, taxpayer_type,
                            resident_status, tax_year, accounting_period_from,
                            accounting_period_to, business_activity, industry,
                            province, federal_registered, sales_tax_registered,
                            sales_tax_jurisdiction, applicable_regimes,
                            withholding_obligations, available_records, notes)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (pcode, dname, ttype, rstatus or None, tyear,
                         ap_from.isoformat(), ap_to.isoformat(), activity,
                         industry, prov or None, int(fed_reg), int(stax_reg),
                         stax_jur or None, json.dumps(regimes), wht_obl,
                         json.dumps(avail), notes))
                    wconn.commit()
                    st.success(f"Profile '{pcode}' saved.")
                except Exception as exc:
                    st.error(f"Could not save: {exc}")

    if st.session_state.profile_id:
        p = get_profile(st.session_state.profile_id)
        st.subheader("Active profile")
        st.json({k: v for k, v in p.items()
                 if k not in ("id", "created_at", "updated_at")})

# ============================================================ Module B ======
if module.startswith("B"):
    st.header("B · Transaction Assessment")
    st.caption("Enter a transaction or pick a predefined scenario — the engine "
               "runs the 14-step chain: profile → transaction → legislation → "
               "applicability → treatment → error → risk → evidence → "
               "verification → calculation → exceptions → adjustment → "
               "return impact → follow-up.")
    pid = pick_profile_selector(key="b_profile")
    profile = get_profile(pid)

    scenarios = [(r["code"], r["name"], r["category"], r["trigger_facts"])
                 for r in kconn.execute(
                     "SELECT code, name, category, trigger_facts FROM scenarios "
                     "ORDER BY code")]
    scn_labels = ["— manual entry —"] + [f"{c} · {n} [{cat}]"
                                         for c, n, cat, _ in scenarios]
    scn_choice = st.selectbox("Predefined scenario (optional)", scn_labels)
    preset_facts = {}
    scenario_code = None
    if not scn_choice.startswith("—"):
        idx = scn_labels.index(scn_choice) - 1
        scenario_code, _, _, tf = scenarios[idx]
        preset_facts = _j(tf, {})

    with st.form("assess_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            tax_cat = st.selectbox(
                "Tax category",
                [""] + [c for c, _ in TAX_CATEGORIES],
                index=([""] + [c for c, _ in TAX_CATEGORIES]).index(
                    preset_facts.get("tax_category", "")) if preset_facts.get("tax_category") else 0)
            juris = st.selectbox("Jurisdiction", [""] + JURISDICTIONS)
            ttype = st.selectbox("Taxpayer type", [""] + TAXPAYER_TYPES)
        with c2:
            txn_type = st.text_input(
                "Transaction type",
                value=str(preset_facts.get("transaction_type", "")),
                placeholder="e.g. payment_for_goods")
            txn_date = st.date_input("Transaction date", value=date.today())
            tax_year = st.text_input("Tax year",
                                     value=str(preset_facts.get("tax_year", "2026")))
        with c3:
            amount = st.text_input("Amount (PKR, optional)",
                                   value=str(preset_facts.get("payment_amount", "")))
            pay_cat = st.text_input("Payment category (WHT)",
                                    value=str(preset_facts.get("payment_category", "")),
                                    placeholder="goods / services / contracts")
            payee = st.text_input("Payee type",
                                  value=str(preset_facts.get("payee_type", "")),
                                  placeholder="company / non_company / individual")
        extra = st.text_area(
            "Additional facts (KEY=VALUE, one per line)",
            value="\n".join(f"{k}={v}" for k, v in preset_facts.items()
                            if k not in ("tax_category", "transaction_type",
                                         "tax_year", "payment_amount",
                                         "payment_category", "payee_type")),
            placeholder="payer_is_withholding_agent=true\nexemption_certificate_valid=false")
        title = st.text_input("Assessment title",
                              value=scn_choice if not scn_choice.startswith("—")
                              else "Manual assessment")
        run_btn = st.form_submit_button("Run analysis")

    def parse_extra(text):
        facts = {}
        for line in (text or "").splitlines():
            line = line.strip()
            if not line or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip()
            if v.lower() in ("true", "false"):
                facts[k] = v.lower() == "true"
            else:
                try:
                    facts[k] = int(v)
                except ValueError:
                    try:
                        facts[k] = float(v)
                    except ValueError:
                        facts[k] = v
        return facts

    if run_btn:
        facts = parse_extra(extra)
        if tax_cat:
            facts["tax_category"] = tax_cat
        if juris:
            facts["jurisdiction"] = juris
        if ttype:
            facts["taxpayer_type"] = ttype
        if txn_type:
            facts["transaction_type"] = txn_type
        facts["transaction_date"] = txn_date.isoformat()
        if tax_year:
            facts["tax_year"] = tax_year
        if amount:
            try:
                facts["payment_amount"] = float(amount)
            except ValueError:
                st.warning("Amount is not numeric — stored as text.")
                facts["payment_amount"] = amount
        if pay_cat:
            facts["payment_category"] = pay_cat
        if payee:
            facts["payee_type"] = payee

        def calc_runner(code, inputs, on_date=None):
            return calcmod.run_calculation(kconn, code, inputs, on_date=on_date)

        steps = decision.analyze(kconn, profile, facts, calc_runner=calc_runner)
        st.session_state["last_steps"] = steps
        st.session_state["last_facts"] = facts
        st.session_state["last_scenario"] = scenario_code
        st.session_state["last_title"] = title or "Manual assessment"

    steps = st.session_state.get("last_steps")
    if steps:
        st.divider()
        st.subheader("Analysis — 14-step chain")
        badge = {"info": "🔵", "needs_input": "🟡",
                 "unverified_rule": "🟠", "exception_flagged": "🔴"}
        for s in steps:
            with st.expander(
                    f"Step {s['step_no']} · {s['step_name']} "
                    f"{badge.get(s['confidence'], '')}"):
                st.write(s["finding"])
                d = s.get("detail") or {}
                if s["step_no"] == 4:
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.markdown("**Applicable**")
                        st.write(d.get("applicable") or "—")
                    with c2:
                        st.markdown("**Excluded**")
                        for e in d.get("excluded", []):
                            st.write(f"{e['code']}: {e['reason']}")
                        if not d.get("excluded"):
                            st.write("—")
                    with c3:
                        st.markdown("**Need more info**")
                        for e in d.get("needs_info", []):
                            st.write(f"{e['code']}: missing "
                                     f"{', '.join(e['missing_fields'])}")
                        if not d.get("needs_info"):
                            st.write("—")
                    if d.get("unverified"):
                        st.warning("Unverified rules in play: " +
                                   ", ".join(d["unverified"]))
                elif s["step_no"] == 5:
                    for t in d.get("treatments", []):
                        tag = "✅ verified" if t["verified"] else "⚠️ unverified"
                        st.write(f"**{t['rule_code']}** ({tag}): {t['treatment']}")
                        if t["missing_fields"]:
                            st.warning("Missing: " +
                                       ", ".join(t["missing_fields"]))
                elif s["step_no"] == 7:
                    for r in d.get("risks", []):
                        st.markdown(f"**{r['risk_code']} — {r['title']}**")
                        st.write(r["description"])
                        if r.get("indicators"):
                            st.caption("Indicators: " +
                                       "; ".join(r["indicators"]))
                elif s["step_no"] == 8:
                    for e in d.get("evidence", []):
                        st.write(f"**{e['evidence_code']}** — {e['name']}")
                elif s["step_no"] == 9:
                    for p in d.get("procedures", []):
                        st.markdown(f"**{p['procedure_code']} — {p['name']}**")
                        for i, step in enumerate(p["steps"], 1):
                            st.write(f"{i}. {step}")
                elif s["step_no"] == 10:
                    for c in d.get("calculations", []):
                        st.write(f"**{c['calc_code']}** v{c['calc_version']} "
                                 f"(rule {c['rule_code']})")
                        res = c.get("result")
                        if isinstance(res, dict):
                            if res.get("result") is not None:
                                st.success(f"Result: {res['result']:,.2f} "
                                           f"[{res['validation_status']}]")
                            else:
                                st.warning("Incomplete: " +
                                           "; ".join(res.get("steps", [])))
                            with st.expander("Working"):
                                for line in res.get("steps", []):
                                    st.write(line)
                elif s["step_no"] in (11, 12):
                    key = "exceptions" if s["step_no"] == 11 else "adjustments"
                    for e in d.get(key, []):
                        st.write(f"**{e.get('rule_code','')}** — "
                                 f"{e.get('exception', e.get('potential_adjustment',''))}")
                        if e.get("action"):
                            st.caption("Action: " + e["action"])
                elif s["step_no"] == 13:
                    st.write([f"{x['rule_code']}: {x['field']}"
                              for x in d.get("return_fields", [])] or "—")
                elif s["step_no"] == 14:
                    for f in d.get("followups", []):
                        st.write("• " + f["action"])
                else:
                    if d:
                        st.json(d)

        if st.button("💾 Save assessment"):
            facts = st.session_state["last_facts"]
            cur = wconn.execute(
                "INSERT INTO assessments(profile_id, title, scenario_code, facts)"
                " VALUES (?,?,?,?)",
                (pid, st.session_state["last_title"],
                 st.session_state.get("last_scenario"),
                 json.dumps(facts)))
            aid = cur.lastrowid
            for s in steps:
                rc = None
                d = s.get("detail") or {}
                if s["step_no"] == 5 and d.get("treatments"):
                    rc = d["treatments"][0]["rule_code"]
                wconn.execute(
                    "INSERT INTO assessment_steps(assessment_id, step_no, step_name,"
                    " rule_code, finding, detail, confidence)"
                    " VALUES (?,?,?,?,?,?,?)",
                    (aid, s["step_no"], s["step_name"], rc, s["finding"],
                     json.dumps(d), s["confidence"]))
            # seed evidence tracker from step 8
            s8 = next((x for x in steps if x["step_no"] == 8), None)
            if s8:
                for e in (s8.get("detail") or {}).get("evidence", []):
                    wconn.execute(
                        "INSERT INTO evidence_tracker(assessment_id, evidence_code)"
                        " VALUES (?,?)", (aid, e["evidence_code"]))
            wconn.commit()
            st.session_state.assessment_id = aid
            st.success(f"Assessment #{aid} saved — continue in G (Evidence) "
                       f"or H (Export).")

# ============================================================ Module C ======
if module.startswith("C"):
    st.header("C · Tax Rule Lookup")
    q = st.text_input("Full-text search", placeholder="e.g. withholding services 153")
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        f_cat = st.selectbox("Tax category", [""] + [c for c, _ in TAX_CATEGORIES],
                             key="c_cat")
        f_jur = st.selectbox("Jurisdiction", [""] + JURISDICTIONS, key="c_jur")
    with fc2:
        f_status = st.selectbox("Verification status", [""] + STATUSES, key="c_st")
        f_tptype = st.selectbox("Taxpayer type", [""] + TAXPAYER_TYPES, key="c_tp")
    with fc3:
        f_prov = st.text_input("Section / provision contains",
                               placeholder="e.g. 153", key="c_prov")
        f_txn = st.text_input("Transaction type contains", key="c_txn")

    results = []
    if q.strip():
        for hit in searchmod.search(kconn, q, limit=100):
            results.append(hit["entity_code"])
    sql = ("SELECT r.*, (SELECT GROUP_CONCAT(l.provision, '; ') FROM "
           "rule_legislation rl JOIN legislation l ON l.id=rl.legislation_id "
           "WHERE rl.rule_id=r.id) AS provisions FROM tax_rules r WHERE 1=1")
    params = []
    if f_cat:
        sql += " AND r.tax_category=?"; params.append(f_cat)
    if f_jur:
        sql += " AND r.jurisdiction=?"; params.append(f_jur)
    if f_status:
        sql += " AND r.verification_status=?"; params.append(f_status)
    if f_tptype:
        sql += " AND r.taxpayer_types LIKE ?"; params.append(f'%"{f_tptype}"%')
    if f_txn:
        sql += " AND r.transaction_types LIKE ?"; params.append(f"%{f_txn}%")
    sql += " ORDER BY r.code, r.version"
    rows = [dict(r) for r in kconn.execute(sql, params)]
    if f_prov:
        rows = [r for r in rows if f_prov.lower() in (r["provisions"] or "").lower()]
    if results:
        rows = [r for r in rows if r["code"] in results]

    st.write(f"**{len(rows)}** rule(s) found.")
    for r in rows:
        ver = "✅ verified" if r["verification_status"] == "verified" else \
            f"⚠️ {r['verification_status']}"
        with st.expander(f"{r['code']} v{r['version']} — {r['title']} [{ver}]"):
            st.caption(f"{r['tax_category']} · {r['jurisdiction']} · "
                       f"effective {r['effective_from']} → {r['effective_to'] or 'present'}")
            st.write("**Trigger:** " + r["triggering_transaction"])
            st.write("**Expected treatment:** " + r["expected_treatment"])
            if r["provisions"]:
                st.write("**Legislation:** " + r["provisions"])
            if r.get("interpretation_note"):
                st.info("Interpretation (not statute): " + r["interpretation_note"])
            logic = _j(r["decision_logic"], {})
            if logic.get("table"):
                st.markdown("**Decision table**")
                for i, br in enumerate(logic["table"]):
                    st.write(f"IF {json.dumps(br['when'])} → {br['then']}")
                st.write(f"DEFAULT → {logic.get('default','')}")
            for label, lt, ic in [
                    ("Risks", "rule_risks", "risk_id"),
                    ("Evidence", "rule_evidence", "evidence_id"),
                    ("Procedures", "rule_procedures", "procedure_id"),
                    ("Calculations", "rule_calcs", "calc_id")]:
                tmap = {"rule_risks": ("tax_risks", "code", "title"),
                        "rule_evidence": ("evidence", "code", "name"),
                        "rule_procedures": ("procedures", "code", "name"),
                        "rule_calcs": ("calc_tables", "code", "name")}[lt]
                linked = kconn.execute(
                    f"SELECT t.code, t.{tmap[2]} AS lbl FROM {tmap[0]} t "
                    f"JOIN {lt} l ON l.{ic}=t.id WHERE l.rule_id=?",
                    (r["id"],)).fetchall()
                if linked:
                    st.write(f"**{label}:** " +
                             ", ".join(f"{x['code']} — {x['lbl']}" for x in linked))
            if r.get("review_notes"):
                st.caption("Review notes: " + r["review_notes"])

# ============================================================ Module D ======
if module.startswith("D"):
    st.header("D · Tax Risk Explorer")
    risks = [(r["code"], r["title"], r["tax_category"])
             for r in kconn.execute(
                 "SELECT code, title, tax_category FROM tax_risks ORDER BY code")]
    if not risks:
        st.info("No risks in the knowledge base yet.")
    else:
        sel = st.selectbox("Risk", [f"{c} — {t} [{cat}]" for c, t, cat in risks])
        code = sel.split(" — ")[0]
        rk = dict(kconn.execute("SELECT * FROM tax_risks WHERE code=?",
                                (code,)).fetchone())
        ver = "✅ verified" if rk["review_status"] == "verified" else \
            f"⚠️ {rk['review_status']}"
        st.subheader(f"{rk['code']} — {rk['title']} [{ver}]")
        st.write(rk["description"])
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Triggering factors / indicators**")
            for i in _j(rk["risk_indicators"], []):
                st.write("• " + i)
            st.markdown("**Root cause**")
            st.write(rk.get("root_cause") or "—")
            st.markdown("**Required information**")
            for i in _j(rk["required_information"], []):
                st.write("• " + i)
        with c2:
            st.markdown("**Potential tax exposure**")
            st.write(rk.get("exposure_note") or "—")
            st.markdown("**Penalty / default surcharge implications**")
            st.write(rk.get("penalty_implications") or
                     "Not verified — no penalty computed.")
            st.markdown("**Follow-up action**")
            st.write(rk.get("followup_action") or "—")
        st.markdown("**Related tax rules**")
        for x in kconn.execute(
                "SELECT r.code, r.title FROM tax_rules r JOIN rule_risks rr "
                "ON rr.rule_id=r.id JOIN tax_risks k ON k.id=rr.risk_id "
                "WHERE k.code=?", (code,)):
            st.write(f"• {x['code']} — {x['title']}")
        st.markdown("**Evidence required**")
        for x in kconn.execute(
                "SELECT e.code, e.name FROM evidence e JOIN risk_evidence re "
                "ON re.evidence_id=e.id JOIN tax_risks k ON k.id=re.risk_id "
                "WHERE k.code=?", (code,)):
            st.write(f"• {x['code']} — {x['name']}")
        st.markdown("**Verification procedures**")
        for x in kconn.execute(
                "SELECT p.code, p.name FROM procedures p "
                "JOIN risk_procedures rp ON rp.procedure_id=p.id "
                "JOIN tax_risks k ON k.id=rp.risk_id WHERE k.code=?", (code,)):
            st.write(f"• {x['code']} — {x['name']}")
            steps = _j(kconn.execute(
                "SELECT steps FROM procedures WHERE code=?",
                (x["code"],)).fetchone()["steps"], [])
            for i, s in enumerate(steps, 1):
                st.caption(f"    {i}. {s}")

# ============================================================ Module E ======
if module.startswith("E"):
    st.header("E · Tax Calculation Workbench")
    st.caption("Every run records inputs + sources, rule/version, legal "
               "provision, effective date, steps, rounding, result and "
               "validation status. Missing inputs → incomplete, never invented.")
    tables = [(r["code"], r["version"], r["name"], r["kind"],
               r["verification_status"], r["effective_from"], r["effective_to"])
              for r in kconn.execute(
                  "SELECT code, version, name, kind, verification_status,"
                  " effective_from, effective_to FROM calc_tables "
                  "ORDER BY code, version")]
    if not tables:
        st.info("No calculation tables loaded yet.")
    else:
        sel = st.selectbox(
            "Calculation table",
            [f"{c} v{v} — {n} [{k}, {s}]" for c, v, n, k, s, _, _ in tables])
        code = sel.split(" v")[0]
        on_date = st.date_input("Effective date for the calculation",
                                value=date.today())
        tbl = calcmod.select_calc_table(kconn, code, on_date=on_date.isoformat())
        if tbl is None:
            st.error(f"No version of {code} is in effect on {on_date}.")
        else:
            params = _j(tbl["params"], {})
            st.write(f"Using **{tbl['code']} v{tbl['version']}** "
                     f"({'✅ verified' if tbl['verification_status'] == 'verified' else '⚠️ ' + tbl['verification_status']}) · "
                     f"provision: {tbl.get('legislation_ref') or '—'} · "
                     f"effective {tbl['effective_from']} → {tbl['effective_to'] or 'present'}")
            required = params.get("required_inputs", ["base"])
            st.caption(f"Base definition: {params.get('rate_basis', params.get('base_input', 'base'))} · "
                       f"rounding: {params.get('rounding')}")
            with st.form("calc_form"):
                vals, srcs = {}, {}
                for name in required:
                    c1, c2 = st.columns([1, 2])
                    with c1:
                        vals[name] = st.text_input(f"{name} *", key=f"cv_{name}")
                    with c2:
                        srcs[name] = st.text_input(f"Source of {name}",
                                                  key=f"cs_{name}",
                                                  placeholder="e.g. payment voucher PV-102")
                go = st.form_submit_button("Run calculation")
            if go:
                inputs = {n: {"value": vals[n], "source": srcs[n] or "user input"}
                          for n in required}
                try:
                    res = calcmod.run_calculation(kconn, code, inputs,
                                                  on_date=on_date.isoformat())
                except Exception as exc:
                    st.error(f"Calculation failed: {exc}")
                    res = None
                if res:
                    st.subheader("Working")
                    for line in res["steps"]:
                        st.write(line)
                    if res["result"] is not None:
                        if res["validation_status"] == "complete":
                            st.success(f"**Result: {res['result']:,.2f}** "
                                       f"(rounded: {res['rounding_method']})")
                        else:
                            st.warning(f"Result: {res['result']:,.2f} — "
                                       f"status: {res['validation_status']}")
                    else:
                        st.warning("Incomplete: " +
                                   "; ".join(res["steps"]))
                    aid = st.session_state.get("assessment_id")
                    if st.button("💾 Save calculation run"):
                        wconn.execute(
                            """INSERT INTO calculation_runs
                               (assessment_id, calc_code, calc_version, inputs,
                                legislation_ref, effective_date, steps,
                                rounding_method, result, validation_status)
                               VALUES (?,?,?,?,?,?,?,?,?,?)""",
                            (aid, res["calc_code"], res.get("calc_version", 1),
                             json.dumps(res["inputs"]), res.get("legislation_ref"),
                             res.get("effective_date"), json.dumps(res["steps"]),
                             res.get("rounding_method"), res.get("result"),
                             res["validation_status"]))
                        wconn.commit()
                        st.success("Calculation run saved.")

# ============================================================ Module F ======
if module.startswith("F"):
    st.header("F · Tax Reconciliation")
    tpl_code = st.selectbox("Template",
                            list(reconcile.TEMPLATES.keys()),
                            format_func=lambda c: reconcile.TEMPLATES[c]["title"])
    tpl = reconcile.new_reconciliation(tpl_code)
    st.caption(tpl["procedure_hint"])
    import pandas as pd
    init = pd.DataFrame(
        [{"label": lbl, "amount_a": None, "amount_b": None,
          "source_a": "", "source_b": "", "note": ""}
         for lbl in tpl["suggested_lines"]])
    edited = st.data_editor(init, num_rows="dynamic", use_container_width=True,
                            key=f"recon_{tpl_code}",
                            column_config={
                                "label": st.column_config.TextColumn("Line"),
                                f"amount_a": st.column_config.NumberColumn(tpl["column_a"]),
                                f"amount_b": st.column_config.NumberColumn(tpl["column_b"]),
                            })
    if st.button("Compute reconciliation"):
        lines = []
        for _, row in edited.iterrows():
            if not str(row["label"] or "").strip():
                continue
            lines.append({
                "label": row["label"],
                "amount_a": None if pd.isna(row["amount_a"]) else float(row["amount_a"]),
                "amount_b": None if pd.isna(row["amount_b"]) else float(row["amount_b"]),
                "source_a": row["source_a"] or "", "source_b": row["source_b"] or "",
                "note": row["note"] or ""})
        res = reconcile.compute(lines)
        st.session_state["last_recon"] = (tpl_code, tpl["title"], res)
        diff_df = pd.DataFrame(res["lines"])
        st.dataframe(diff_df[["label", "amount_a", "amount_b", "difference",
                              "status"]], use_container_width=True)
        if res["incomplete_lines"]:
            st.warning(res["conclusion"])
        elif res["total_difference"] == 0:
            st.success(res["conclusion"])
        else:
            st.error(res["conclusion"])

    if st.session_state.get("last_recon"):
        aid = st.selectbox("Attach to assessment (optional)",
                           ["— none —"] + [lbl for _, lbl in assessment_options()],
                           key="f_assess")
        if st.button("💾 Save reconciliation"):
            tpl_code, title, res = st.session_state["last_recon"]
            aid_val = None
            if not aid.startswith("—"):
                aid_val = [i for i, lbl in assessment_options() if lbl == aid][0]
            wconn.execute(
                "INSERT INTO reconciliations(assessment_id, template_code, title,"
                " lines, total_difference, conclusion)"
                " VALUES (?,?,?,?,?,?)",
                (aid_val, tpl_code, title, json.dumps(res["lines"]),
                 res["total_difference"], res["conclusion"]))
            wconn.commit()
            st.success("Reconciliation saved.")

# ============================================================ Module G ======
if module.startswith("G"):
    st.header("G · Evidence Tracker")
    opts = assessment_options()
    if not opts:
        st.info("No assessments yet — run one in Module B first.")
    else:
        labels = [lbl for _, lbl in opts]
        ids = [i for i, _ in opts]
        cur = st.session_state.assessment_id
        sel = st.selectbox("Assessment", labels,
                           index=ids.index(cur) if cur in ids else 0)
        aid = ids[labels.index(sel)]
        st.session_state.assessment_id = aid
        rows = [dict(r) for r in wconn.execute(
            "SELECT * FROM evidence_tracker WHERE assessment_id=? ORDER BY id",
            (aid,))]
        if not rows:
            st.info("No evidence items tracked for this assessment.")
        else:
            import pandas as pd
            df = pd.DataFrame([{
                "id": r["id"], "evidence": r["evidence_code"],
                "requested": bool(r["requested"]), "received": bool(r["received"]),
                "verified": bool(r["verification_done"]),
                "result": r["result"] or "",
                "exceptions": r["exceptions"] or "",
                "outstanding": r["outstanding_info"] or "",
                "reviewer_comments": r["reviewer_comments"] or "",
                "status": r["status"]} for r in rows])
            edited = st.data_editor(
                df, use_container_width=True, key=f"ev_{aid}",
                column_config={
                    "id": st.column_config.NumberColumn("ID", disabled=True),
                    "evidence": st.column_config.TextColumn("Evidence", disabled=True),
                    "result": st.column_config.SelectColumn(
                        "Result", options=["", "ok", "discrepancy_found",
                                           "incomplete", "not_applicable"]),
                    "status": st.column_config.SelectColumn(
                        "Status", options=["open", "in_progress", "completed",
                                           "archived"]),
                })
            if st.button("💾 Save evidence tracker"):
                for _, row in edited.iterrows():
                    wconn.execute(
                        """UPDATE evidence_tracker SET requested=?, received=?,
                           verification_done=?, result=?, exceptions=?,
                           outstanding_info=?, reviewer_comments=?, status=?,
                           updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
                           WHERE id=?""",
                        (int(row["requested"]), int(row["received"]),
                         int(row["verified"]), row["result"] or None,
                         row["exceptions"] or None, row["outstanding"] or None,
                         row["reviewer_comments"] or None, row["status"],
                         int(row["id"])))
                wconn.commit()
                st.success("Evidence tracker updated.")
        st.divider()
        st.subheader("Add evidence item")
        ev_codes = [r["code"] for r in kconn.execute(
            "SELECT code FROM evidence ORDER BY code")]
        new_ev = st.selectbox("Evidence type", ev_codes, key="g_new_ev")
        if st.button("➕ Add to tracker"):
            exists = wconn.execute(
                "SELECT 1 FROM evidence_tracker WHERE assessment_id=? "
                "AND evidence_code=?", (aid, new_ev)).fetchone()
            if exists:
                st.warning("Already tracked.")
            else:
                wconn.execute(
                    "INSERT INTO evidence_tracker(assessment_id, evidence_code)"
                    " VALUES (?,?)", (aid, new_ev))
                wconn.commit()
                st.success(f"{new_ev} added."); st.rerun()

# ============================================================ Module H ======
if module.startswith("H"):
    st.header("H · Export")
    st.caption("Export rules, calculations, risk assessments and "
               "reconciliations to CSV / Excel — all offline.")
    exp_dir = db.data_dir() / "exports"
    exp_dir.mkdir(parents=True, exist_ok=True)

    st.subheader("Rule library")
    ec1, ec2, ec3 = st.columns(3)
    with ec1:
        x_cat = st.selectbox("Category filter", ["(all)"] +
                             [c for c, _ in TAX_CATEGORIES], key="h_cat")
    with ec2:
        x_st = st.selectbox("Status filter", ["(all)"] + STATUSES, key="h_st")
    with ec3:
        x_jur = st.selectbox("Jurisdiction filter", ["(all)"] + JURISDICTIONS,
                             key="h_jur")
    if st.button("⬇️ Export rules to CSV"):
        p = exportmod.export_rules_csv(
            kconn, exp_dir / "tax_rules.csv",
            tax_category=None if x_cat == "(all)" else x_cat,
            jurisdiction=None if x_jur == "(all)" else x_jur,
            status=None if x_st == "(all)" else x_st)
        st.download_button("Download tax_rules.csv", p.read_bytes(),
                           file_name=p.name, mime="text/csv")

    st.divider()
    st.subheader("Assessment package")
    opts = assessment_options()
    if not opts:
        st.info("No assessments yet.")
    else:
        labels = [lbl for _, lbl in opts]
        ids = [i for i, _ in opts]
        cur = st.session_state.assessment_id
        sel = st.selectbox("Assessment", labels,
                           index=ids.index(cur) if cur in ids else 0,
                           key="h_assess")
        aid = ids[labels.index(sel)]
        c1, c2 = st.columns(2)
        with c1:
            if st.button("⬇️ Export calculations (CSV)"):
                p = exportmod.export_calculations_csv(
                    wconn, exp_dir / f"calculations_assessment_{aid}.csv",
                    assessment_id=aid)
                st.download_button("Download calculations CSV", p.read_bytes(),
                                   file_name=p.name, mime="text/csv")
        with c2:
            if st.button("⬇️ Export full assessment (Excel)"):
                p = exportmod.export_assessment_xlsx(
                    kconn, wconn, aid,
                    exp_dir / f"assessment_{aid}.xlsx")
                st.download_button("Download assessment workbook",
                                   p.read_bytes(), file_name=p.name,
                                   mime="application/vnd.openxmlformats-"
                                        "officedocument.spreadsheetml.sheet")

st.sidebar.divider()
st.sidebar.caption("Data: " + str(db.data_dir()))
