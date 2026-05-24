-- pgvector: telemetry semantic search and memory retrieval
-- 768 dims = nomic-embed-text (Ollama, no key) or text-embedding-3-small truncated (OpenAI)
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS telemetry_embeddings (
  id          BIGSERIAL    PRIMARY KEY,
  sensor_id   TEXT         NOT NULL,
  sensor_type TEXT         NOT NULL,
  event_type  TEXT         NOT NULL,  -- bio_fusion | eeg_process | sensor_ingest | ai_router
  state       TEXT,                   -- STRESS_CONFIRMED | BASELINE | etc.
  content     TEXT         NOT NULL,  -- human-readable text that was embedded
  embedding   vector(768)  NOT NULL,
  metadata    JSONB,
  created_at  TIMESTAMPTZ  DEFAULT NOW()
);

-- IVFFlat index for fast approximate cosine similarity
CREATE INDEX IF NOT EXISTS telemetry_embeddings_vec_idx
  ON telemetry_embeddings
  USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

CREATE INDEX IF NOT EXISTS telemetry_embeddings_sensor_idx  ON telemetry_embeddings (sensor_id);
CREATE INDEX IF NOT EXISTS telemetry_embeddings_type_idx    ON telemetry_embeddings (event_type);
CREATE INDEX IF NOT EXISTS telemetry_embeddings_state_idx   ON telemetry_embeddings (state);
CREATE INDEX IF NOT EXISTS telemetry_embeddings_ts_idx      ON telemetry_embeddings (created_at DESC);

-- RPC used by semantic-search edge function
CREATE OR REPLACE FUNCTION match_telemetry(
  query_embedding    vector(768),
  match_threshold    float   DEFAULT 0.70,
  match_count        int     DEFAULT 10,
  filter_sensor_type text    DEFAULT NULL,
  filter_event_type  text    DEFAULT NULL,
  filter_state       text    DEFAULT NULL
)
RETURNS TABLE (
  id          bigint,
  sensor_id   text,
  sensor_type text,
  event_type  text,
  state       text,
  content     text,
  metadata    jsonb,
  created_at  timestamptz,
  similarity  float
)
LANGUAGE plpgsql AS $$
BEGIN
  RETURN QUERY
  SELECT
    t.id, t.sensor_id, t.sensor_type, t.event_type, t.state, t.content, t.metadata, t.created_at,
    (1 - (t.embedding <=> query_embedding))::float AS similarity
  FROM telemetry_embeddings t
  WHERE (1 - (t.embedding <=> query_embedding)) > match_threshold
    AND (filter_sensor_type IS NULL OR t.sensor_type = filter_sensor_type)
    AND (filter_event_type  IS NULL OR t.event_type  = filter_event_type)
    AND (filter_state       IS NULL OR t.state       = filter_state)
  ORDER BY t.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
