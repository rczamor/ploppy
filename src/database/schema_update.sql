-- SQL script to update database schema for new data types

-- Create expenditures table
CREATE TABLE IF NOT EXISTS expenditures (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reference_number VARCHAR(255) NOT NULL,
    election_id UUID REFERENCES elections(id),
    recipient_id UUID REFERENCES recipients(id),
    filing_number INTEGER,
    schedule VARCHAR(10),
    
    -- Expenditure details
    invoice_date DATE,
    payment_date DATE,
    payee_name VARCHAR(500),
    payee_type VARCHAR(50), -- from C_CODE
    organization_type VARCHAR(10), -- from ORG_IND
    
    -- Address
    city VARCHAR(255),
    state VARCHAR(50),
    zip VARCHAR(20),
    
    -- Payment details
    payment_method VARCHAR(50),
    amount DECIMAL(12,2),
    purpose_code VARCHAR(50),
    purpose_description TEXT,
    explanation TEXT,
    exemption_code VARCHAR(50),
    
    -- Flags
    is_reimbursement BOOLEAN DEFAULT FALSE,
    is_segregated BOOLEAN DEFAULT FALSE,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(reference_number)
);

-- Add intermediary columns to contributions table
ALTER TABLE contributions 
ADD COLUMN IF NOT EXISTS intermediary_id UUID REFERENCES intermediaries(id),
ADD COLUMN IF NOT EXISTS match_amount DECIMAL(12,2) DEFAULT 0,
ADD COLUMN IF NOT EXISTS previous_amount DECIMAL(12,2) DEFAULT 0,
ADD COLUMN IF NOT EXISTS purpose_code VARCHAR(50),
ADD COLUMN IF NOT EXISTS exemption_code VARCHAR(50),
ADD COLUMN IF NOT EXISTS adjustment_type_code INTEGER,
ADD COLUMN IF NOT EXISTS refund_date DATE;

-- Create intermediaries table
CREATE TABLE IF NOT EXISTS intermediaries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    intermediary_number VARCHAR(50),
    full_name VARCHAR(500) NOT NULL,
    normalized_name VARCHAR(500),
    intermediary_type VARCHAR(50),
    
    -- Address
    city VARCHAR(255),
    state VARCHAR(50),
    zip VARCHAR(20),
    
    -- Employment
    employer_name VARCHAR(500),
    employer_street_no VARCHAR(50),
    employer_street_name VARCHAR(255),
    employer_city VARCHAR(255),
    employer_state VARCHAR(50),
    occupation VARCHAR(255),
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(intermediary_number, full_name)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_expenditures_recipient ON expenditures(recipient_id);
CREATE INDEX IF NOT EXISTS idx_expenditures_date ON expenditures(payment_date);
CREATE INDEX IF NOT EXISTS idx_expenditures_purpose ON expenditures(purpose_code);
CREATE INDEX IF NOT EXISTS idx_contributions_intermediary ON contributions(intermediary_id);
CREATE INDEX IF NOT EXISTS idx_intermediaries_number ON intermediaries(intermediary_number);