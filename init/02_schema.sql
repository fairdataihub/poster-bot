-- posterbot schema — run as posterbot_owner against db "posters".
-- HNSW / GIN / btree indexes are deliberately deferred to after the bulk load.

CREATE TABLE IF NOT EXISTS posters (
  poster_key        text PRIMARY KEY,          -- DOI when present, else '<source>/<repo_id>'
  doi               text UNIQUE,
  repo_id           text NOT NULL,
  source            text NOT NULL CHECK (source IN ('zenodo','figshare')),
  batch             text NOT NULL CHECK (batch IN ('pre2025','data2025')),
  title             text,
  description       text,
  subjects          text[],
  creators          jsonb,
  creators_text     text,                      -- flattened names + affiliations, for FTS
  conference_name   text,
  conference_year   int,
  publication_year  int,
  research_field    text,
  rights            text,
  -- classify_license(rightsList) from repo/scripts/post_processing/license_policy.py:
  -- public full-text serving filters on license_class = 'allowed'
  license_class     text NOT NULL DEFAULT 'unknown'
                    CHECK (license_class IN ('allowed','blocked','unknown')),
  license_blocked   boolean NOT NULL DEFAULT false,  -- upstream _license_blocked flag (body stripped at source)
  n_sections        int,
  embed_tokens      int,
  full_text         text,                      -- exactly the sanitized text that was embedded
  url               text,
  tsv tsvector GENERATED ALWAYS AS (
    to_tsvector('english',
      left(coalesce(title,'') || ' ' || coalesce(description,'') || ' ' ||
           coalesce(creators_text,'') || ' ' || coalesce(full_text,''), 400000))
  ) STORED,
  embedding         vector(1024)
);

GRANT CONNECT ON DATABASE posters TO posterbot_ro;
GRANT USAGE ON SCHEMA public TO posterbot_ro;
GRANT SELECT ON posters TO posterbot_ro;
ALTER DEFAULT PRIVILEGES FOR ROLE posterbot_owner IN SCHEMA public
  GRANT SELECT ON TABLES TO posterbot_ro;
