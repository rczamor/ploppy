-- Accent folding for nysboe_contributions.
--
-- WHY THERE IS NO INDEX HERE: unaccent() changes exactly 0 of the 6,182,834 rows
-- in this table. Every non-ASCII character in the source data (161 rows) is
-- U+FFFD REPLACEMENT CHARACTER -- upstream mojibake, verified against the live
-- Socrata API, not a download artifact. The accents were already destroyed
-- before NYSBOE published the data, so there is nothing left to fold and a
-- column-side index would be ~500 MB that can never change a result.
--
-- What unaccent IS for here: folding the QUERY INPUT. A name pasted from another
-- system ('Gutierrez' with an accent) will not equal the plain-ASCII spelling
-- NYSBOE stores, and folding the constant fixes that -- no index needed, because
-- the function runs once on the literal, not per row.
--
--     SELECT * FROM nysboe_contributions
--     WHERE lower(flng_ent_last_name) = lower(unaccent('Gutierrez'));  -- accented input
--
-- That reaches 1,021 rows; matching the accented form directly reaches 0.
-- The existing lower() btree indexes serve these queries unchanged.

CREATE EXTENSION IF NOT EXISTS unaccent;

-- Both unaccent() overloads are STABLE, not IMMUTABLE, because the dictionary is
-- loaded from a file on disk. So a direct index on unaccent(col) is rejected:
--     ERROR:  functions in index expression must be marked IMMUTABLE
-- This wrapper is the documented workaround. It is nothing but a promise: if
-- unaccent.rules ever changes on disk, any index built on it is silently stale
-- and must be REINDEXed. Pin the dictionary explicitly so a search_path change
-- cannot alter the result.
CREATE OR REPLACE FUNCTION immutable_unaccent(text)
    RETURNS text
    LANGUAGE sql
    IMMUTABLE STRICT PARALLEL SAFE
AS $$ SELECT public.unaccent('public.unaccent'::regdictionary, $1) $$;

COMMENT ON FUNCTION immutable_unaccent(text) IS
    'IMMUTABLE wrapper over unaccent() so it can be used in index expressions. Unused by default -- see scripts/nysboe_contributions_unaccent.sql for why this table needs no unaccent index. REINDEX anything built on it if unaccent.rules changes.';

-- If a future table DOES hold real accents, this is the shape to use:
--
--   CREATE INDEX <name> ON <table>
--       USING gin (immutable_unaccent(<col>) gin_trgm_ops);
