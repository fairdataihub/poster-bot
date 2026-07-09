-- Post-load index build. Run as posterbot_owner after load_posters.py.
-- maintenance_work_mem/parallel workers are already set container-wide (1GB / 2).
CREATE INDEX IF NOT EXISTS idx_posters_hnsw ON posters
  USING hnsw ((embedding::halfvec(1024)) halfvec_cosine_ops)
  WITH (m = 16, ef_construction = 128);
CREATE INDEX IF NOT EXISTS idx_posters_tsv        ON posters USING gin (tsv);
CREATE INDEX IF NOT EXISTS idx_posters_title_trgm ON posters USING gin (title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_posters_year       ON posters (publication_year);
CREATE INDEX IF NOT EXISTS idx_posters_source     ON posters (source);
CREATE INDEX IF NOT EXISTS idx_posters_license    ON posters (license_class);
ANALYZE posters;
