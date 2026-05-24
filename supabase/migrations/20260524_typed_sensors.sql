-- Extend sensor_readings to support typed multi-sensor payloads
ALTER TABLE sensor_readings
  ADD COLUMN IF NOT EXISTS sensor_type  TEXT             DEFAULT 'rf',
  ADD COLUMN IF NOT EXISTS metadata     JSONB,
  ADD COLUMN IF NOT EXISTS temperature_c  DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS humidity_pct   DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS pressure_hpa   DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS kp_index       DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS solar_flux     DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS channel        TEXT,
  ADD COLUMN IF NOT EXISTS amplitude_uv   DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS band           TEXT;

-- Backfill existing RF rows
UPDATE sensor_readings SET sensor_type = 'rf' WHERE sensor_type IS NULL;

CREATE INDEX IF NOT EXISTS sensor_readings_type_idx ON sensor_readings (sensor_type);
CREATE INDEX IF NOT EXISTS sensor_readings_ts_idx   ON sensor_readings (timestamp DESC);
