-- Trigram indexes for fuzzy contributor / committee name matching on
-- nysboe_contributions. Requires pg_trgm.
--
-- pg_trgm folds case internally, so these index the raw columns -- no lower()
-- wrapper needed, and they serve ILIKE '%...%', similarity() and % as well.
--
-- Contributor identity splits by type in this dataset:
--   organizations  -> flng_ent_name            (715,688 rows populated)
--   individuals    -> flng_ent_first/last_name (~5.23M rows populated)
-- so both paths are indexed, plus a combined full-name expression that matches
-- the voter<->contributor matching this repo does elsewhere.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

SET maintenance_work_mem = '1GB';

-- organization / entity names
CREATE INDEX IF NOT EXISTS nysboe_contrib_ent_name_trgm
    ON nysboe_contributions USING gin (flng_ent_name gin_trgm_ops);

-- individual surnames
CREATE INDEX IF NOT EXISTS nysboe_contrib_ent_last_trgm
    ON nysboe_contributions USING gin (flng_ent_last_name gin_trgm_ops);

-- individual full name, as "First Last"
CREATE INDEX IF NOT EXISTS nysboe_contrib_ent_fullname_trgm
    ON nysboe_contributions USING gin (
        (coalesce(flng_ent_first_name,'') || ' ' || coalesce(flng_ent_last_name,''))
        gin_trgm_ops
    );

-- recipient committee names
CREATE INDEX IF NOT EXISTS nysboe_contrib_comm_name_trgm
    ON nysboe_contributions USING gin (cand_comm_name gin_trgm_ops);

ANALYZE nysboe_contributions;
