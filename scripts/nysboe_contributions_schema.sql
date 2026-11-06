-- NY State Board of Elections itemized contribution records, 2016-present.
--
-- Native NYSBOE 63-column disclosure layout, kept as its own table rather than
-- merged into the NYC CFB `contributions` table: different filing authority,
-- different column set, and a disjoint transaction-id space. Join the two through
-- a view if you need unified reporting.
--
-- Source: data.ny.gov dataset e9ss-239a (NYSBOE). See data/nysboe/README.md.

DROP TABLE IF EXISTS nysboe_contributions;

CREATE TABLE nysboe_contributions (
    -- keys
    filing_trans_id         bigint PRIMARY KEY,
    filer_id                bigint NOT NULL,
    filer_previous_id       text,
    trans_number            text,
    trans_mapping           text,
    loan_lib_number         text,

    -- filer / committee
    cand_comm_name          text,
    election_year           integer,
    election_type           text,
    county_desc             text,

    -- the filing this record arrived in
    filing_abbrev           text,
    filing_desc             text,
    r_amend                 text,
    filing_cat_desc         text,
    filing_sched_abbrev     text NOT NULL,
    filing_sched_desc       text,

    -- transaction
    sched_date              date NOT NULL,
    org_date                date,
    org_amt                 numeric(16,2),
    owed_amt                numeric(16,2),
    cntrbr_type_desc        text,
    cntrbn_type_desc        text,
    transfer_type_desc      text,
    receipt_type_desc       text,
    receipt_code_desc       text,
    purpose_code_desc       text,
    payment_type_desc       text,
    pay_number              text,
    loan_other_desc         text,
    trans_explntn           text,
    r_subcontractor         text,

    -- contributor / filing entity
    flng_ent_name           text,
    flng_ent_first_name     text,
    flng_ent_middle_name    text,
    flng_ent_last_name      text,
    flng_ent_add1           text,
    flng_ent_city           text,
    flng_ent_state          text,
    flng_ent_zip            text,
    flng_ent_country        text,

    -- treasurer
    treas_occupation        text,
    treas_employer          text,
    treas_add1              text,
    treas_city              text,
    treas_state             text,
    treas_zip               text,

    -- independent expenditure contributor
    ie_cntrbr_occ           text,
    ie_cntrbr_emp           text,

    -- office sought
    election_year_r         integer,
    office_desc             text,
    district                text,
    dist_off_cand_bal_prop  text,

    -- flags, as filed (Y/N text, not boolean -- blanks are meaningful)
    r_itemized              text,
    r_liability             text,
    r_ie_supported          text,
    r_claim                 text,
    r_in_district           text,
    r_minor                 text,
    r_vendor                text,
    r_lobbyist              text,
    r_contributions         text,
    r_support_oppose        text,
    r_is_qualified_expense  text
);

COMMENT ON TABLE nysboe_contributions IS
    'NYSBOE itemized contributions (schedules A/B/C/D), sched_date >= 2016-01-01. Source: data.ny.gov e9ss-239a. Records are as-filed: amendments appear as separate rows (r_amend) and some sched_date values are filer typos in the future.';
