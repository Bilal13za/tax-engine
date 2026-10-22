-- ============================================================================
-- Pakistan Tax Risk, Rules and Evidence Engine — Knowledge database schema
-- tax_knowledge.db : versioned tax law, rules, risks, evidence, procedures,
--                    calculation tables, scenarios, source register.
-- This database holds TAX KNOWLEDGE (legislation, rules, library content).
-- Taxpayer-specific working data lives in tax_workdata.db (see schema_workdata.sql).
-- ============================================================================

PRAGMA journal_mode = WAL;

-- ----------------------------------------------------------------------------
-- Source register: every legal/professional source used by any rule.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sources (
    id              INTEGER PRIMARY KEY,
    code            TEXT NOT NULL UNIQUE,          -- e.g. SRC-FBR-ITO2001
    title           TEXT NOT NULL,                 -- "Income Tax Ordinance, 2001"
    source_type     TEXT NOT NULL,                 -- legislation | rules | notification | sro | circular | explanatory_guidance | professional_interpretation | illustrative_example | case_law
    issuing_authority TEXT,                        -- e.g. "Government of Pakistan", "FBR"
    jurisdiction    TEXT NOT NULL,                 -- federal | punjab | sindh | kpk | balochistan | ict | gb | ajk
    reference_url   TEXT,                          -- official URL where verified (may be empty if verified from print)
    verified_date   TEXT,                          -- YYYY-MM-DD when the source was last checked
    notes           TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- ----------------------------------------------------------------------------
-- Legislation: one row per provision/rule/notification instrument.
-- Historical versions are preserved as separate rows (never overwritten).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS legislation (
    id                  INTEGER PRIMARY KEY,
    code                TEXT NOT NULL UNIQUE,      -- e.g. LEG-ITO2001-S21
    name                TEXT NOT NULL,             -- "Income Tax Ordinance, 2001"
    issuing_authority   TEXT NOT NULL,
    jurisdiction        TEXT NOT NULL,
    provision           TEXT NOT NULL,             -- "Section 21"
    subsection          TEXT,                      -- "21(1)(a)"
    rule_description    TEXT NOT NULL,
    effective_from      TEXT NOT NULL,             -- YYYY-MM-DD
    effective_to        TEXT,                      -- YYYY-MM-DD or NULL if current
    tax_year            TEXT,                      -- e.g. "2026" where the provision is TY-specific
    amendment_history   TEXT,                      -- free text: which Finance Act changed it and when
    source_code         TEXT REFERENCES sources(code),
    source_verified_date TEXT,
    review_status       TEXT NOT NULL DEFAULT 'draft'
                        CHECK (review_status IN ('draft','under_review','verified','superseded','retired')),
    version             INTEGER NOT NULL DEFAULT 1,
    supersedes_id       INTEGER REFERENCES legislation(id),
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_legislation_provision ON legislation(provision, jurisdiction);
CREATE INDEX IF NOT EXISTS idx_legislation_dates ON legislation(effective_from, effective_to);

-- ----------------------------------------------------------------------------
-- Tax rule library. One row = one version of one rule.
-- NEVER invent provisions, rates, dates: unverified content stays 'draft'.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tax_rules (
    id                      INTEGER PRIMARY KEY,
    code                    TEXT NOT NULL,         -- stable rule code, e.g. RULE-WHT-153-GOODS
    version                 INTEGER NOT NULL DEFAULT 1,
    title                   TEXT NOT NULL,
    tax_category            TEXT NOT NULL          -- income_tax | withholding_tax | sales_tax_federal | customs
                        CHECK (tax_category IN ('income_tax','withholding_tax','sales_tax_federal',
                                                'customs','sales_tax_provincial','provincial_other','other_levies')),
    jurisdiction            TEXT NOT NULL,         -- federal | punjab | sindh | kpk | balochistan | ict | gb | ajk
    taxpayer_types          TEXT NOT NULL,         -- JSON array, e.g. ["company","aop","individual"]
    triggering_transaction  TEXT NOT NULL,         -- human-readable trigger description
    transaction_types       TEXT NOT NULL,         -- JSON array of machine tags, e.g. ["payment_for_goods"]
    applicability_conditions TEXT NOT NULL,        -- JSON: condition tree (see SEED_FORMAT.md)
    exclusion_conditions    TEXT NOT NULL DEFAULT '[]',  -- JSON: condition tree
    required_inputs         TEXT NOT NULL DEFAULT '[]',  -- JSON array of {name,label,data_type,source_hint,required}
    decision_logic          TEXT NOT NULL,         -- JSON: explicit IF/THEN decision table
    expected_treatment      TEXT NOT NULL,
    calculation_method      TEXT,                  -- references a calc_tables.code or describes manual method
    exceptions              TEXT NOT NULL DEFAULT '[]',  -- JSON array of {condition, action}
    consequences            TEXT,                  -- what follows from error/non-compliance (no invented penalties)
    return_fields           TEXT NOT NULL DEFAULT '[]',  -- JSON array of affected return fields/statements
    effective_from          TEXT NOT NULL,
    effective_to            TEXT,
    verification_status     TEXT NOT NULL DEFAULT 'draft'
                            CHECK (verification_status IN ('draft','under_review','verified','superseded','retired')),
    reviewer                TEXT,
    review_date             TEXT,
    review_notes            TEXT,
    interpretation_note     TEXT,                  -- software's interpretation, separated from statute
    supersedes_id           INTEGER REFERENCES tax_rules(id),
    created_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE (code, version)
);
CREATE INDEX IF NOT EXISTS idx_rules_code ON tax_rules(code);
CREATE INDEX IF NOT EXISTS idx_rules_cat_jur ON tax_rules(tax_category, jurisdiction);
CREATE INDEX IF NOT EXISTS idx_rules_dates ON tax_rules(effective_from, effective_to);
CREATE INDEX IF NOT EXISTS idx_rules_status ON tax_rules(verification_status);

-- ----------------------------------------------------------------------------
-- Tax risk library.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tax_risks (
    id                  INTEGER PRIMARY KEY,
    code                TEXT NOT NULL UNIQUE,      -- e.g. RISK-WHT-001
    title               TEXT NOT NULL,
    description         TEXT NOT NULL,
    root_cause          TEXT,
    tax_category        TEXT NOT NULL,
    jurisdiction        TEXT NOT NULL DEFAULT 'federal',
    potential_financial_effect TEXT,
    exposure_note       TEXT,                      -- possible underpayment exposure (no invented penalty maths)
    penalty_implications TEXT,                     -- only where legal conditions verified; else NULL + note
    applicable_conditions TEXT NOT NULL DEFAULT '[]', -- JSON condition tree
    risk_indicators     TEXT NOT NULL DEFAULT '[]',-- JSON array of red-flag descriptions
    required_information TEXT NOT NULL DEFAULT '[]', -- JSON array
    followup_action     TEXT,
    source_codes        TEXT NOT NULL DEFAULT '[]',-- JSON array of sources.code
    review_status       TEXT NOT NULL DEFAULT 'draft'
                        CHECK (review_status IN ('draft','under_review','verified','superseded','retired')),
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- ----------------------------------------------------------------------------
-- Evidence library.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS evidence (
    id                  INTEGER PRIMARY KEY,
    code                TEXT NOT NULL UNIQUE,      -- e.g. EV-SALES-INVOICE
    name                TEXT NOT NULL,
    description         TEXT NOT NULL,
    typical_source      TEXT,
    verification_procedure TEXT,                   -- how to verify this evidence type
    reliability_notes   TEXT,
    limitations         TEXT,
    expected_information TEXT NOT NULL DEFAULT '[]', -- JSON array of fields expected on the document
    common_discrepancies TEXT NOT NULL DEFAULT '[]',-- JSON array
    review_status       TEXT NOT NULL DEFAULT 'draft'
                        CHECK (review_status IN ('draft','under_review','verified','superseded','retired')),
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- ----------------------------------------------------------------------------
-- Verification procedure library.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS procedures (
    id                  INTEGER PRIMARY KEY,
    code                TEXT NOT NULL UNIQUE,      -- e.g. PROC-DOC-VERIFY
    name                TEXT NOT NULL,
    category            TEXT NOT NULL              -- document_verification | reconciliation | calculation | completeness | eligibility
                        CHECK (category IN ('document_verification','reconciliation','calculation','completeness','eligibility')),
    objective           TEXT NOT NULL,
    triggering_condition TEXT,
    steps               TEXT NOT NULL,             -- JSON array of step descriptions
    inputs_required     TEXT NOT NULL DEFAULT '[]',-- JSON array
    documents_to_obtain TEXT NOT NULL DEFAULT '[]',-- JSON array of evidence codes
    calculation_method  TEXT,
    expected_result     TEXT,
    exception_conditions TEXT NOT NULL DEFAULT '[]', -- JSON array
    followup_procedure  TEXT,
    legislation_ref     TEXT,                      -- free-text provision reference (linked formally via rule links)
    review_status       TEXT NOT NULL DEFAULT 'draft'
                        CHECK (review_status IN ('draft','under_review','verified','superseded','retired')),
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- ----------------------------------------------------------------------------
-- Calculation tables: rates, slabs, thresholds live HERE, never in code.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS calc_tables (
    id                  INTEGER PRIMARY KEY,
    code                TEXT NOT NULL,             -- e.g. CALC-WHT-153-GOODS
    version             INTEGER NOT NULL DEFAULT 1,
    name                TEXT NOT NULL,
    kind                TEXT NOT NULL              -- slab | flat_rate | percentage | fixed_amount | threshold | rate_schedule
                        CHECK (kind IN ('slab','flat_rate','percentage','fixed_amount','threshold',
                                        'rate_schedule')),
    tax_category        TEXT NOT NULL,
    jurisdiction        TEXT NOT NULL DEFAULT 'federal',
    taxpayer_types      TEXT NOT NULL DEFAULT '[]',-- JSON array; [] = all
    params              TEXT NOT NULL,             -- JSON: slabs/thresholds/rates + rounding + base definition
    legislation_ref     TEXT,                      -- provision, e.g. "ITO 2001 s.153(1)(a)"
    effective_from      TEXT NOT NULL,
    effective_to        TEXT,
    tax_year            TEXT,
    verification_status TEXT NOT NULL DEFAULT 'draft'
                        CHECK (verification_status IN ('draft','under_review','verified','superseded','retired')),
    supersedes_id       INTEGER REFERENCES calc_tables(id),
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE (code, version)
);
CREATE INDEX IF NOT EXISTS idx_calc_code ON calc_tables(code);
CREATE INDEX IF NOT EXISTS idx_calc_dates ON calc_tables(effective_from, effective_to);

-- ----------------------------------------------------------------------------
-- Many-to-many links between rules and library objects (structured relations).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rule_legislation (
    rule_id INTEGER NOT NULL REFERENCES tax_rules(id),
    legislation_id INTEGER NOT NULL REFERENCES legislation(id),
    link_note TEXT,
    PRIMARY KEY (rule_id, legislation_id)
);
CREATE TABLE IF NOT EXISTS rule_risks (
    rule_id INTEGER NOT NULL REFERENCES tax_rules(id),
    risk_id INTEGER NOT NULL REFERENCES tax_risks(id),
    PRIMARY KEY (rule_id, risk_id)
);
CREATE TABLE IF NOT EXISTS rule_evidence (
    rule_id INTEGER NOT NULL REFERENCES tax_rules(id),
    evidence_id INTEGER NOT NULL REFERENCES evidence(id),
    purpose TEXT,                                   -- e.g. "supports deduction claim"
    PRIMARY KEY (rule_id, evidence_id)
);
CREATE TABLE IF NOT EXISTS rule_procedures (
    rule_id INTEGER NOT NULL REFERENCES tax_rules(id),
    procedure_id INTEGER NOT NULL REFERENCES procedures(id),
    PRIMARY KEY (rule_id, procedure_id)
);
CREATE TABLE IF NOT EXISTS rule_calcs (
    rule_id INTEGER NOT NULL REFERENCES tax_rules(id),
    calc_id INTEGER NOT NULL REFERENCES calc_tables(id),
    PRIMARY KEY (rule_id, calc_id)
);
CREATE TABLE IF NOT EXISTS risk_evidence (
    risk_id INTEGER NOT NULL REFERENCES tax_risks(id),
    evidence_id INTEGER NOT NULL REFERENCES evidence(id),
    PRIMARY KEY (risk_id, evidence_id)
);
CREATE TABLE IF NOT EXISTS risk_procedures (
    risk_id INTEGER NOT NULL REFERENCES tax_risks(id),
    procedure_id INTEGER NOT NULL REFERENCES procedures(id),
    PRIMARY KEY (risk_id, procedure_id)
);

-- ----------------------------------------------------------------------------
-- Predefined scenarios (§10): trigger -> full chain mapping, for Module B.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scenarios (
    id                  INTEGER PRIMARY KEY,
    code                TEXT NOT NULL UNIQUE,      -- e.g. SCN-INC-001
    name                TEXT NOT NULL,
    category            TEXT NOT NULL              -- income_tax | withholding_tax | sales_tax_federal | sales_tax_provincial | return_preparation
                        CHECK (category IN ('income_tax','withholding_tax','sales_tax_federal','sales_tax_provincial','return_preparation')),
    description         TEXT NOT NULL,
    trigger_facts       TEXT NOT NULL,             -- JSON: facts that select this scenario
    expected_chain      TEXT NOT NULL,             -- JSON: the 14-step mapping (rule codes, risk codes, evidence codes, procedure codes, calc codes)
    accounting_vs_tax   TEXT,                      -- note distinguishing accounting treatment from tax treatment
    review_status       TEXT NOT NULL DEFAULT 'draft'
                        CHECK (review_status IN ('draft','under_review','verified','superseded','retired')),
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- ----------------------------------------------------------------------------
-- Full-text search over the knowledge base (offline, no external service).
-- ----------------------------------------------------------------------------
CREATE VIRTUAL TABLE IF NOT EXISTS kb_fts USING fts5(
    entity_type, entity_code, title, body,
    tokenize = 'unicode61'
);
