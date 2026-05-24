-- Tracks which sensor_readings batches have been archived to GCS
CREATE TABLE IF NOT EXISTS sensor_reading_archives (
  id          BIGSERIAL    PRIMARY KEY,
  sensor_type TEXT         NOT NULL,
  date        DATE         NOT NULL,
  gcs_path    TEXT         NOT NULL,
  row_count   INTEGER      NOT NULL,
  size_bytes  BIGINT,
  archived_at TIMESTAMPTZ  DEFAULT NOW(),
  UNIQUE (sensor_type, date)
);

CREATE INDEX IF NOT EXISTS archives_sensor_type_idx ON sensor_reading_archives (sensor_type);
CREATE INDEX IF NOT EXISTS archives_date_idx        ON sensor_reading_archives (date DESC);
