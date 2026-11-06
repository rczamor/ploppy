-- Ploppy base schema (NYC Campaign Finance Board data).
-- Reconstructed from the queries in src/database/db_manager_v2.py, ploppy.py,
-- src/ai/* and the import scripts. Apply this before src/database/schema_update.sql.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ---------------------------------------------------------------- elections
CREATE TABLE IF NOT EXISTS elections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    election_cycle VARCHAR(50) UNIQUE,
    election_year INTEGER,
    election_type VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------- employers
CREATE TABLE IF NOT EXISTS employers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(500),
    normalized_name VARCHAR(500) UNIQUE,
    street_number VARCHAR(50),
    street_name VARCHAR(255),
    city VARCHAR(255),
    state VARCHAR(50),
    employer_type VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------- locations
CREATE TABLE IF NOT EXISTS locations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    street_number VARCHAR(50),
    street_name VARCHAR(255),
    apartment VARCHAR(50),
    city VARCHAR(255),
    state VARCHAR(50),
    zip_code VARCHAR(20),
    borough_code VARCHAR(1),
    borough_name VARCHAR(50),
    region VARCHAR(50),
    latitude DECIMAL(10, 8),
    longitude DECIMAL(11, 8),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------- contributors
CREATE TABLE IF NOT EXISTS contributors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name VARCHAR(500),
    last_name VARCHAR(255),
    first_name VARCHAR(255),
    middle_initial VARCHAR(10),
    middle_name VARCHAR(255),
    normalized_name VARCHAR(500) UNIQUE,
    contributor_type VARCHAR(100),
    c_code VARCHAR(50),
    occupation VARCHAR(255),
    employer_id UUID REFERENCES employers(id),
    location_id UUID REFERENCES locations(id),
    is_individual BOOLEAN,
    city VARCHAR(255),
    state VARCHAR(50),
    zip_code VARCHAR(20),
    total_contributions DECIMAL(14,2),
    contribution_count INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- --------------------------------------------------------------- recipients
CREATE TABLE IF NOT EXISTS recipients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recipid VARCHAR(50) UNIQUE,
    full_name VARCHAR(500),
    last_name VARCHAR(255),
    first_name VARCHAR(255),
    middle_initial VARCHAR(10),
    normalized_name VARCHAR(500),
    recipient_type VARCHAR(50),
    office_code VARCHAR(20),
    office_name VARCHAR(255),
    canclass VARCHAR(10),
    canclass_description VARCHAR(255),
    committee_code VARCHAR(50),
    party VARCHAR(100),
    borough VARCHAR(50),
    is_individual BOOLEAN,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ----------------------------------------------------------- intermediaries
-- Superset of the definition in schema_update.sql, which is a no-op once this
-- table exists.
CREATE TABLE IF NOT EXISTS intermediaries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    intermediary_number VARCHAR(50),
    full_name VARCHAR(500) NOT NULL,
    last_name VARCHAR(255),
    first_name VARCHAR(255),
    middle_initial VARCHAR(10),
    normalized_name VARCHAR(500),
    intermediary_type VARCHAR(50),
    c_code VARCHAR(50),
    occupation VARCHAR(255),
    employer_id UUID REFERENCES employers(id),
    location_id UUID REFERENCES locations(id),
    city VARCHAR(255),
    state VARCHAR(50),
    zip VARCHAR(20),
    employer_name VARCHAR(500),
    employer_street_no VARCHAR(50),
    employer_street_name VARCHAR(255),
    employer_city VARCHAR(255),
    employer_state VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (intermediary_number, full_name)
);

-- ------------------------------------------------------------------ filings
CREATE TABLE IF NOT EXISTS filings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    election_id UUID REFERENCES elections(id),
    recipient_id UUID REFERENCES recipients(id),
    filing_number INTEGER,
    schedule_type VARCHAR(20),
    schedule_description VARCHAR(255),
    page_number INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (election_id, recipient_id, filing_number)
);

-- ------------------------------------------------------------ contributions
-- Carries both the normalized foreign keys written by db_manager_v2 and the
-- denormalized columns the fast import scripts and ploppy.py use.
CREATE TABLE IF NOT EXISTS contributions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    contributor_id UUID REFERENCES contributors(id),
    recipient_id UUID REFERENCES recipients(id),
    intermediary_id UUID REFERENCES intermediaries(id),
    election_id UUID REFERENCES elections(id),
    filing_id UUID REFERENCES filings(id),
    location_id UUID REFERENCES locations(id),
    employer_id UUID REFERENCES employers(id),

    reference_number VARCHAR(255),
    refno VARCHAR(255) UNIQUE,
    sequence_number INTEGER,
    sequence_no INTEGER,
    recip_id VARCHAR(50),

    -- TIMESTAMP, not DATE: ploppy.py's create_timeline_chart uses the pandas
    -- .dt accessor on this column, which needs a datetime64 dtype.
    transaction_date TIMESTAMP,
    date TIMESTAMP,
    refund_date DATE,

    amount DECIMAL(12,2),
    match_amount DECIMAL(12,2) DEFAULT 0,
    previous_amount DECIMAL(12,2) DEFAULT 0,

    payment_method INTEGER,
    payment_method_desc VARCHAR(100),
    purpose_code VARCHAR(50),
    exemption_code VARCHAR(50),
    adjustment_type_code INTEGER,
    adjustment_type_desc VARCHAR(255),
    registered_recipient BOOLEAN DEFAULT FALSE,
    segregated_account BOOLEAN DEFAULT FALSE,
    amount_category VARCHAR(20),
    election_cycle VARCHAR(50),

    quarter INTEGER,
    month INTEGER,
    day_of_year INTEGER,
    weekday INTEGER,

    str_no VARCHAR(50),
    str_name VARCHAR(500),
    occupation VARCHAR(255),
    contributor_city VARCHAR(255),
    contributor_state VARCHAR(50),
    contributor_zip VARCHAR(20),
    schedule VARCHAR(10),
    page_no INTEGER,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------------ indexes
CREATE INDEX IF NOT EXISTS idx_contributions_contributor ON contributions(contributor_id);
CREATE INDEX IF NOT EXISTS idx_contributions_recipient ON contributions(recipient_id);
CREATE INDEX IF NOT EXISTS idx_contributions_election ON contributions(election_id);
CREATE INDEX IF NOT EXISTS idx_contributions_location ON contributions(location_id);
CREATE INDEX IF NOT EXISTS idx_contributions_date ON contributions(date DESC);
CREATE INDEX IF NOT EXISTS idx_contributions_transaction_date ON contributions(transaction_date DESC);
CREATE INDEX IF NOT EXISTS idx_contributions_amount ON contributions(amount);
CREATE INDEX IF NOT EXISTS idx_contributors_normalized ON contributors(normalized_name);
CREATE INDEX IF NOT EXISTS idx_contributors_employer ON contributors(employer_id);
CREATE INDEX IF NOT EXISTS idx_employers_normalized ON employers(normalized_name);
CREATE INDEX IF NOT EXISTS idx_recipients_recipid ON recipients(recipid);
CREATE INDEX IF NOT EXISTS idx_locations_city_state ON locations(city, state);

-- --------------------------------------------------------------- embeddings
-- Used by src/ai/pgvector_manager.py. 384 dims to match the embedding size
-- produced in src/ai/ai_phase3.py.
CREATE EXTENSION IF NOT EXISTS "vector";

CREATE TABLE IF NOT EXISTS embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type VARCHAR(50) NOT NULL,
    entity_id VARCHAR(100) NOT NULL,
    content TEXT,
    embedding vector(384),
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_embeddings_entity ON embeddings(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_vector ON embeddings
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- -------------------------------------------------- date column reconciliation
-- The app writes and reads two different date columns on contributions:
--   * db_manager_v2.import_contribution_row writes `transaction_date`, and
--     get_database_stats filters on it;
--   * the fast import scripts write `date`, and ploppy.py's search selects and
--     orders by `date`.
-- Keep them in step so either import path feeds both read paths. Drop this
-- trigger if the two columns are ever given distinct meanings.
CREATE OR REPLACE FUNCTION contributions_sync_dates() RETURNS trigger AS $$
BEGIN
    IF NEW.date IS NULL AND NEW.transaction_date IS NOT NULL THEN
        NEW.date := NEW.transaction_date;
    ELSIF NEW.transaction_date IS NULL AND NEW.date IS NOT NULL THEN
        NEW.transaction_date := NEW.date;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_contributions_sync_dates ON contributions;
CREATE TRIGGER trg_contributions_sync_dates
    BEFORE INSERT OR UPDATE ON contributions
    FOR EACH ROW EXECUTE FUNCTION contributions_sync_dates();
