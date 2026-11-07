-- Populate the repo's normalized CFB schema from the cfb_* staging tables.
--
-- Run scripts/load_cfb_filers.py first. This script reads only from
-- cfb_contributions / cfb_expenditures / cfb_intermediaries and rewrites
-- elections, recipients, employers, locations, contributors, intermediaries,
-- filings, contributions and expenditures. It is idempotent: it truncates those
-- tables and rebuilds them, so it can be re-run after fixing a mapping without
-- re-parsing 540 MB of CSV.
--
-- TWO UNIQUE CONSTRAINTS MUST GO. public.contributions shipped with
-- UNIQUE (refno) and public.expenditures with UNIQUE (reference_number). Neither
-- can be satisfied: REFNO is a filing PAGE reference, not a transaction id, and
-- it repeats heavily in both exports.
--
--   contributions: 2,123,892 rows -> 204,266 distinct REFNO ('P0001-01' x4,490)
--   expenditures :   669,276 rows ->  62,308 distinct REFNO ('P0001-01' x4,735)
--
-- Keeping them would silently discard ~90% of each file -- the likeliest reason
-- these tables have sat empty. Both are replaced by NON-unique indexes.
-- expenditures.reference_number is also NOT NULL, which is fine: REFNO is
-- populated on every row of both exports.
--
-- NAME NORMALIZATION: contributors.normalized_name and employers.normalized_name
-- are UNIQUE, so the dedup key is upper(trim(collapse whitespace)). That is the
-- repo's own design, and it has a real consequence worth knowing: every distinct
-- person sharing a name collapses into ONE contributor row. 'SMITH, JOHN' in
-- Brooklyn and in Buffalo become the same contributor. The staging tables keep
-- every row as filed, so per-transaction analysis should use cfb_contributions;
-- use contributors for name-level rollups only.
--
-- See data/cfb/README.md.

\set ON_ERROR_STOP on
SET datestyle TO 'ISO, MDY';

BEGIN;

-- ---------------------------------------------------------------- 0. constraint
ALTER TABLE contributions DROP CONSTRAINT IF EXISTS contributions_refno_key;
CREATE INDEX IF NOT EXISTS idx_contributions_refno ON contributions (refno);

ALTER TABLE expenditures DROP CONSTRAINT IF EXISTS expenditures_reference_number_key;
CREATE INDEX IF NOT EXISTS idx_expenditures_refno ON expenditures (reference_number);

-- ---------------------------------------------------------------- 1. clear out
TRUNCATE contributions, expenditures, filings, intermediaries,
         contributors, recipients, employers, locations, elections
         RESTART IDENTITY CASCADE;

-- ---------------------------------------------------------------- 2. elections
INSERT INTO elections (election_cycle, election_year, election_type)
SELECT e,
       nullif(substring(e from '^\d{4}'), '')::int,
       CASE right(e, 1)
            WHEN 'T' THEN 'Transition'
            WHEN 'A' THEN 'Special'
            WHEN 'U' THEN 'Unknown'
            ELSE 'Regular'
       END
FROM  (SELECT DISTINCT election AS e FROM cfb_contributions
       UNION
       SELECT DISTINCT election      FROM cfb_expenditures) s
WHERE e IS NOT NULL;

-- ---------------------------------------------------------------- 3. recipients
-- recipid and candid share one id space (1,961 of 1,966 expenditure candids also
-- appear as contribution recipids), so a single recipients table serves both.
-- Contributions carry only RECIPNAME ('Last, First'); expenditures carry the name
-- already split, so prefer those parts where a candidate appears in both.
WITH from_contrib AS (
    SELECT DISTINCT ON (recipid)
           recipid, recipname AS full_name, canclass, officecd, committee
    FROM   cfb_contributions
    ORDER  BY recipid, election DESC
), from_expend AS (
    SELECT DISTINCT ON (candid)
           candid, candlast, candfirst, candmi, canclass, officecd, committee
    FROM   cfb_expenditures
    ORDER  BY candid, election DESC
), ids AS (
    SELECT recipid AS id FROM from_contrib
    UNION
    SELECT candid        FROM from_expend
)
INSERT INTO recipients (recipid, full_name, last_name, first_name, middle_initial,
                        normalized_name, office_code, canclass,
                        canclass_description, committee_code)
SELECT i.id,
       coalesce(c.full_name,
                nullif(trim(coalesce(e.candlast,'') || ', ' ||
                            coalesce(e.candfirst,'')), ', ')),
       coalesce(e.candlast,  split_part(c.full_name, ',', 1)),
       coalesce(e.candfirst, nullif(trim(split_part(c.full_name, ',', 2)), '')),
       e.candmi,
       upper(trim(regexp_replace(
           coalesce(c.full_name,
                    coalesce(e.candlast,'') || ', ' || coalesce(e.candfirst,'')),
           '\s+', ' ', 'g'))),
       coalesce(c.officecd, e.officecd),
       coalesce(c.canclass, e.canclass),
       CASE coalesce(c.canclass, e.canclass)
            WHEN 'P'  THEN 'Participating (receives public matching funds)'
            WHEN 'NP' THEN 'Non-participating'
            WHEN 'UN' THEN 'Unknown/Unclassified'
       END,
       coalesce(c.committee, e.committee)
FROM   ids i
LEFT   JOIN from_contrib c ON c.recipid = i.id
LEFT   JOIN from_expend  e ON e.candid  = i.id;

-- ---------------------------------------------------------------- 4. employers
INSERT INTO employers (name, normalized_name, street_number, street_name, city, state)
SELECT DISTINCT ON (norm) nm, norm, strno, strnm, cty, st
FROM (
    SELECT upper(trim(regexp_replace(empname, '\s+', ' ', 'g'))) AS norm,
           empname AS nm, empstrno AS strno, empstrname AS strnm,
           empcity AS cty, empstate AS st
    FROM   cfb_contributions WHERE nullif(trim(empname), '') IS NOT NULL
    UNION ALL
    SELECT upper(trim(regexp_replace(intempname, '\s+', ' ', 'g'))),
           intempname, intempstno, intempstnm, intempcity, intempst
    FROM   cfb_contributions WHERE nullif(trim(intempname), '') IS NOT NULL
    UNION ALL
    SELECT upper(trim(regexp_replace(empname, '\s+', ' ', 'g'))),
           empname, empstrno, empstrname, empcity, empstate
    FROM   cfb_intermediaries WHERE nullif(trim(empname), '') IS NOT NULL
) s
WHERE norm <> ''
ORDER  BY norm, strno NULLS LAST;

-- ---------------------------------------------------------------- 5. locations
-- Street number/name/apartment are blank in every row of these exports, so a
-- location here is only as precise as city + state + zip + borough.
INSERT INTO locations (city, state, zip_code, borough_code, borough_name)
SELECT DISTINCT cty, st, zp, bc,
       CASE bc WHEN 'M' THEN 'Manhattan'  WHEN 'B' THEN 'Bronx'
               WHEN 'K' THEN 'Brooklyn'   WHEN 'Q' THEN 'Queens'
               WHEN 'S' THEN 'Staten Island' END
FROM (
    SELECT city AS cty, state AS st, zip AS zp, boroughcd AS bc
    FROM   cfb_contributions
    UNION
    SELECT intcity, intst, intzip, NULL FROM cfb_contributions
    UNION
    SELECT city, state, zip, boroughcd FROM cfb_intermediaries
    UNION
    SELECT city, state, zip, NULL FROM cfb_expenditures
) s
WHERE coalesce(cty, st, zp, bc) IS NOT NULL;

-- ---------------------------------------------------------------- 6. contributors
INSERT INTO contributors (full_name, normalized_name, c_code, contributor_type,
                          occupation, is_individual, city, state, zip_code,
                          employer_id, location_id,
                          total_contributions, contribution_count)
SELECT DISTINCT ON (g.norm)
       g.nm, g.norm, g.c_code,
       CASE g.c_code WHEN 'IND' THEN 'Individual' WHEN 'CORP' THEN 'Corporation'
                     WHEN 'PCOMP' THEN 'Political Committee'
                     WHEN 'FAM' THEN 'Family' WHEN 'PART' THEN 'Partnership'
                     WHEN 'EMPO' THEN 'Employee Organization'
                     ELSE g.c_code END,
       g.occupation,
       g.c_code IN ('IND', 'FAM'),
       g.city, g.state, g.zip,
       emp.id, loc.id,
       g.total, g.cnt
FROM (
    SELECT upper(trim(regexp_replace(name, '\s+', ' ', 'g'))) AS norm,
           min(name)                     AS nm,
           min(c_code)                   AS c_code,
           min(occupation)               AS occupation,
           min(city)                     AS city,
           min(state)                    AS state,
           min(zip)                       AS zip,
           min(upper(trim(regexp_replace(empname, '\s+', ' ', 'g')))) AS emp_norm,
           min(boroughcd)                AS bc,
           sum(amnt)                     AS total,
           count(*)                      AS cnt
    FROM   cfb_contributions
    WHERE  nullif(trim(name), '') IS NOT NULL
    GROUP  BY 1
) g
LEFT JOIN employers emp ON emp.normalized_name = g.emp_norm
LEFT JOIN locations loc ON loc.city = g.city AND loc.state = g.state
                       AND loc.zip_code = g.zip AND loc.borough_code IS NOT DISTINCT FROM g.bc
WHERE g.norm <> ''
ORDER BY g.norm;

-- ---------------------------------------------------------------- 7. intermediaries
INSERT INTO intermediaries (full_name, normalized_name, c_code, intermediary_type,
                            occupation, city, state, zip, employer_name,
                            employer_street_no, employer_street_name,
                            employer_city, employer_state, employer_id, location_id)
SELECT DISTINCT ON (s.norm)
       s.name, s.norm, s.c_code,
       CASE s.c_code WHEN 'IND' THEN 'Individual' WHEN 'PCOMP' THEN 'Political Committee'
                     ELSE s.c_code END,
       s.occupation, s.city, s.state, s.zip, s.empname,
       s.empstrno, s.empstrname, s.empcity, s.empstate,
       emp.id, loc.id
FROM (
    SELECT upper(trim(regexp_replace(name, '\s+', ' ', 'g'))) AS norm, *,
           upper(trim(regexp_replace(empname, '\s+', ' ', 'g'))) AS emp_norm
    FROM   cfb_intermediaries
) s
LEFT JOIN employers emp ON emp.normalized_name = s.emp_norm
LEFT JOIN locations loc ON loc.city = s.city AND loc.state = s.state
                       AND loc.zip_code = s.zip
                       AND loc.borough_code IS NOT DISTINCT FROM s.boroughcd
WHERE s.norm <> ''
ORDER BY s.norm, s.amnt DESC NULLS LAST;

-- ---------------------------------------------------------------- 8. filings
INSERT INTO filings (election_id, recipient_id, filing_number, schedule_type,
                     schedule_description)
SELECT DISTINCT ON (el.id, r.id, s.filing)
       el.id, r.id, s.filing, s.schedule,
       CASE s.schedule WHEN 'ABC' THEN 'Contributions'
                       WHEN 'M'   THEN 'Matchable contributions'
                       WHEN 'D'   THEN 'Expenditures'
                       WHEN 'F'   THEN 'Expenditures/Payments'
                       WHEN 'ICONT' THEN 'In-kind contributions' END
FROM  (SELECT election, recipid, filing, schedule FROM cfb_contributions
       UNION
       SELECT election, candid,  filing, schedule FROM cfb_expenditures) s
JOIN  elections  el ON el.election_cycle = s.election
JOIN  recipients r  ON r.recipid        = s.recipid
WHERE s.filing IS NOT NULL
ORDER BY el.id, r.id, s.filing, s.schedule;

-- ---------------------------------------------------------------- 9. contributions
INSERT INTO contributions (
    contributor_id, recipient_id, intermediary_id, election_id, filing_id,
    location_id, employer_id,
    reference_number, refno, recip_id, date, refund_date,
    amount, match_amount, previous_amount, payment_method,
    purpose_code, exemption_code, adjustment_type_code,
    registered_recipient, segregated_account,
    str_no, str_name, occupation,
    contributor_city, contributor_state, contributor_zip,
    schedule, election_cycle)
SELECT ctr.id, r.id, itm.id, el.id, fl.id, loc.id, emp.id,
       c.refno, c.refno, c.recipid, c.date, c.refunddate,
       c.amnt, c.matchamnt, c.prevamnt, c.pay_method,
       c.purposecd, c.exemptcd, c.adjtypecd,
       c.rr_ind = 'Y', c.seg_ind = 'Y',
       c.strno, c.strname, c.occupation,
       c.city, c.state, c.zip,
       c.schedule, c.election
FROM   cfb_contributions c
LEFT   JOIN elections    el  ON el.election_cycle = c.election
LEFT   JOIN recipients   r   ON r.recipid         = c.recipid
LEFT   JOIN contributors ctr ON ctr.normalized_name =
           upper(trim(regexp_replace(c.name, '\s+', ' ', 'g')))
LEFT   JOIN intermediaries itm ON itm.normalized_name =
           upper(trim(regexp_replace(c.intermname, '\s+', ' ', 'g')))
LEFT   JOIN employers    emp ON emp.normalized_name =
           upper(trim(regexp_replace(c.empname, '\s+', ' ', 'g')))
LEFT   JOIN locations    loc ON loc.city = c.city AND loc.state = c.state
                            AND loc.zip_code = c.zip
                            AND loc.borough_code IS NOT DISTINCT FROM c.boroughcd
LEFT   JOIN filings      fl  ON fl.election_id = el.id AND fl.recipient_id = r.id
                            AND fl.filing_number = c.filing;

-- ---------------------------------------------------------------- 10. expenditures
INSERT INTO expenditures (
    election_id, recipient_id, reference_number, filing_number, schedule,
    invoice_date, payment_date, payee_name, payee_type, organization_type,
    city, state, zip, payment_method, amount,
    purpose_code, purpose_description, explanation, exemption_code,
    is_reimbursement, is_segregated)
SELECT el.id, r.id, e.refno, e.filing, e.schedule,
       e.inv_date, e.date, e.name, e.c_code, e.org_ind,
       e.city, e.state, e.zip, e.pay_method, e.amnt,
       e.purposecd, e.purpose, e.explain, e.exemptcd,
       e.rr_ind = 'Y', e.seg_ind = 'Y'
FROM   cfb_expenditures e
LEFT   JOIN elections  el ON el.election_cycle = e.election
LEFT   JOIN recipients r  ON r.recipid         = e.candid;

COMMIT;

ANALYZE elections;
ANALYZE recipients;
ANALYZE employers;
ANALYZE locations;
ANALYZE contributors;
ANALYZE intermediaries;
ANALYZE filings;
ANALYZE contributions;
ANALYZE expenditures;
