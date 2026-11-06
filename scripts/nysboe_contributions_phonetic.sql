-- Phonetic blocking indexes for nysboe_contributions. Requires fuzzystrmatch.
--
-- WHY THESE AND NOT A levenshtein INDEX: levenshtein() has no operator class, so it
-- can never be index-driven -- it must run against an already-narrowed candidate
-- set. These expression indexes supply that narrowing ("blocking") step cheaply,
-- after which levenshtein ranks the survivors. See data/nysboe/README.md.
--
-- Scope: individual surnames only. dmetaphone/soundex encode a single word, so
-- they are not meaningful on multi-word organization or committee names -- use the
-- GIN trigram indexes (nysboe_contributions_trgm.sql) for those.

CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;

SET maintenance_work_mem = '1GB';

-- double metaphone: finer-grained than soundex (keeps Smith/Smyth together as SM0
-- while separating Schmidt as XMT), so prefer this for blocking.
CREATE INDEX IF NOT EXISTS nysboe_contrib_last_dmetaphone_idx
    ON nysboe_contributions (dmetaphone(flng_ent_last_name));

-- soundex: coarser (Smith, Smyth AND Schmidt all collapse to S530). Higher recall,
-- lower precision -- useful as a fallback block when dmetaphone finds nothing.
CREATE INDEX IF NOT EXISTS nysboe_contrib_last_soundex_idx
    ON nysboe_contributions (soundex(flng_ent_last_name));

ANALYZE nysboe_contributions;
