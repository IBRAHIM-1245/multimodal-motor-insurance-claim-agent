-- Drop data tables so this script can be re-run safely (children first)
DROP TABLE IF EXISTS past_claims, policies, vehicles, customers, policy_rules, repair_prices CASCADE;

CREATE TABLE customers (
    customer_id  TEXT PRIMARY KEY,
    full_name    TEXT NOT NULL,
    email        TEXT,
    phone        TEXT,
    city         TEXT
);

CREATE TABLE vehicles (
    vehicle_id          TEXT PRIMARY KEY,
    customer_id         TEXT REFERENCES customers(customer_id),
    make                TEXT,
    model               TEXT,
    segment             TEXT,          -- hatchback / sedan / suv
    year                INTEGER,
    fuel                TEXT,
    registration_number TEXT
);

CREATE TABLE policies (
    policy_number TEXT PRIMARY KEY,
    customer_id   TEXT REFERENCES customers(customer_id),
    vehicle_id    TEXT REFERENCES vehicles(vehicle_id),
    policy_type   TEXT,                -- Comprehensive / Third Party Only
    start_date    DATE,
    end_date      DATE,
    status        TEXT,                -- active / expired
    idv           INTEGER,             -- Insured Declared Value (max payout for total loss)
    addons        TEXT,                -- e.g. zero_dep;engine_protect
    premium       INTEGER
);

CREATE TABLE past_claims (
    claim_id       TEXT PRIMARY KEY,
    policy_number  TEXT REFERENCES policies(policy_number),
    claim_date     DATE,
    claim_type     TEXT,
    claimed_amount INTEGER,
    settled_amount INTEGER,
    status         TEXT
);

CREATE TABLE policy_rules (
    claim_type         TEXT PRIMARY KEY,
    covered_under      TEXT,
    max_payout         INTEGER,
    deductible         INTEGER,
    required_documents TEXT,
    key_exclusions     TEXT,
    clause_ref         TEXT
);

CREATE TABLE repair_prices (
    part      TEXT,
    segment   TEXT,
    minor     INTEGER,
    moderate  INTEGER,
    severe    INTEGER,
    PRIMARY KEY (part, segment)
);

-- Audit log: one row per decided claim. NOT dropped on re-run, so history is kept.
CREATE TABLE IF NOT EXISTS claim_audit (
    id              SERIAL PRIMARY KEY,
    claim_id        TEXT,
    policy_number   TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    claim_type      TEXT,
    ai_decision     TEXT,          -- approve / reject / human_review / need_more_info
    final_decision  TEXT,          -- after the adjuster (or same as AI if auto)
    decided_by      TEXT,          -- "agent" or adjuster name
    confidence      NUMERIC,
    estimated_cost  INTEGER,
    payable_amount  INTEGER,
    reasons         TEXT,
    flags           TEXT,
    policy_clauses  TEXT,
    transcript      TEXT,
    damage_report   JSONB,
    trace_id        TEXT
);
