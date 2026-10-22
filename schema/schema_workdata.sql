-- ============================================================================
-- Pakistan Tax Risk, Rules and Evidence Engine — Working-data database schema
-- tax_workdata.db : taxpayer profiles, assessments, evidence tracking,
--                   reconciliations, calculation runs, export log.
-- This database holds TAXPAYER-SPECIFIC WORKING DATA, kept strictly separate
-- from the tax knowledge database (tax_knowledge.db).
-- ============================================================================

PRAGMA journal_mode = WAL;

-- ----------------------------------------------------------------------------
-- Taxpayer profiles (Module A). One row per taxpayer / tax year if needed.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS taxpayer_profiles (
    id                      INTEGER PRIMARY KEY,
    profile_code            TEXT NOT NULL UNIQUE,  -- user-chosen, e.g. "ABC-CO-2026"
    display_name            TEXT NOT NULL,
    taxpayer_type           TEXT NOT NULL          -- individual | aop | company | other
                            CHECK (taxpayer_type IN ('individual','aop','company','other')),
    resident_status         TEXT,                  -- resident | non_resident (where relevant)
    tax_year                TEXT NOT NULL,         -- e.g. "2026"
    accounting_period_from  TEXT,
    accounting_period_to    TEXT,
    business_activity       TEXT,
    industry                TEXT,
    province                TEXT,                  -- punjab | sindh | kpk | balochistan | ict | gb | ajk
    federal_registered      INTEGER NOT NULL DEFAULT 0,  -- income tax registration (0/1)
    sales_tax_registered    INTEGER NOT NULL DEFAULT 0,  -- 0/1
    sales_tax_jurisdiction  TEXT,                  -- federal | punjab | sindh | kpk | balochistan | ict
    applicable_regimes      TEXT NOT NULL DEFAULT '[]', -- JSON array of tax_category codes
    withholding_obligations TEXT NOT NULL DEFAULT '[]', -- JSON array, e.g. ["prescribed_person"]
    available_records       TEXT NOT NULL DEFAULT '[]', -- JSON array of evidence codes held
    review_status           TEXT NOT NULL DEFAULT 'draft'
                            CHECK (review_status IN ('draft','under_review','verified','superseded','retired')),
    notes                   TEXT,
    created_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- ----------------------------------------------------------------------------
-- Assessments: one row per transaction/scenario analysis (Module B).
-- The 14-step chain is stored row-by-row in assessment_steps.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS assessments (
    id              INTEGER PRIMARY KEY,
    profile_id      INTEGER REFERENCES taxpayer_profiles(id),
    title           TEXT NOT NULL,
    scenario_code   TEXT,                           -- scenarios.code when launched from a scenario
    facts           TEXT NOT NULL,                 -- JSON: all facts entered by the user
    status          TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','in_progress','completed','archived')),
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- The 14-step chain, in order:
--  1 taxpayer_profile  2 transaction_condition  3 legislation  4 applicability
--  5 tax_treatment     6 possible_error         7 tax_risk       8 evidence_required
--  9 verification      10 calculation           11 exceptions    12 adjustment
-- 13 return_impact     14 followup
CREATE TABLE IF NOT EXISTS assessment_steps (
    id              INTEGER PRIMARY KEY,
    assessment_id   INTEGER NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
    step_no         INTEGER NOT NULL,              -- 1..14
    step_name       TEXT NOT NULL,
    rule_code       TEXT,                          -- tax_rules.code when relevant
    rule_version    INTEGER,
    finding         TEXT NOT NULL,                 -- what the engine determined at this step
    detail          TEXT,                          -- JSON: structured detail (amounts, refs, flags)
    confidence      TEXT NOT NULL DEFAULT 'info'   -- info | needs_input | unverified_rule | exception_flagged
                    CHECK (confidence IN ('info','needs_input','unverified_rule','exception_flagged')),
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE (assessment_id, step_no)
);

-- ----------------------------------------------------------------------------
-- Evidence tracker (Module G).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS evidence_tracker (
    id                  INTEGER PRIMARY KEY,
    assessment_id       INTEGER NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
    evidence_code       TEXT NOT NULL,             -- evidence.code
    requested           INTEGER NOT NULL DEFAULT 0,
    received            INTEGER NOT NULL DEFAULT 0,
    verification_done   INTEGER NOT NULL DEFAULT 0,
    result              TEXT,                      -- ok | discrepancy_found | incomplete | not_applicable
    exceptions          TEXT,
    outstanding_info    TEXT,
    reviewer_comments   TEXT,
    status              TEXT NOT NULL DEFAULT 'open'
                        CHECK (status IN ('open','in_progress','completed','archived')),
    updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- ----------------------------------------------------------------------------
-- Reconciliations (Module F).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reconciliations (
    id              INTEGER PRIMARY KEY,
    assessment_id   INTEGER REFERENCES assessments(id) ON DELETE CASCADE,
    template_code   TEXT NOT NULL,                 -- e.g. RECON-PROFIT-TO-TAXABLE
    title           TEXT NOT NULL,
    lines           TEXT NOT NULL,                 -- JSON array of {label, amount_a, amount_b, difference, note}
    total_difference REAL,
    conclusion      TEXT,
    status          TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','completed','archived')),
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- ----------------------------------------------------------------------------
-- Calculation runs (Module E): full audit trail per §11.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS calculation_runs (
    id                  INTEGER PRIMARY KEY,
    assessment_id       INTEGER REFERENCES assessments(id) ON DELETE SET NULL,
    calc_code           TEXT NOT NULL,             -- calc_tables.code
    calc_version        INTEGER NOT NULL,
    inputs              TEXT NOT NULL,             -- JSON: {name: {value, source}}
    legislation_ref     TEXT,
    effective_date      TEXT,
    steps               TEXT NOT NULL,             -- JSON array of human-readable step strings
    rounding_method     TEXT,
    result              REAL,
    validation_status   TEXT NOT NULL              -- complete | incomplete_missing_inputs | unverified_rule
                        CHECK (validation_status IN ('complete','incomplete_missing_inputs','unverified_rule')),
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- ----------------------------------------------------------------------------
-- Export log (Module H).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS export_log (
    id              INTEGER PRIMARY KEY,
    assessment_id   INTEGER REFERENCES assessments(id) ON DELETE SET NULL,
    export_kind     TEXT NOT NULL,                 -- rules | calculations | risks | reconciliations | full_assessment
    file_format     TEXT NOT NULL,                 -- csv | xlsx
    file_name       TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
