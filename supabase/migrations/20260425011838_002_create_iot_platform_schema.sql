/*
  # IoT Sensor Data Collection Platform

  1. New Tables
    - `sensors` - Registered IoT devices/sensors
      - `id` (uuid, primary key)
      - `device_id` (text, unique identifier for the sensor)
      - `name` (text)
      - `location` (text)
      - `sensor_type` (text) - e.g., "RF_ANALYZER", "TEMPERATURE", "HUMIDITY"
      - `status` (text) - "active", "inactive", "error"
      - `last_reading` (timestamp)
      - `api_key` (text, secret key for sensor authentication)
      - `created_at` (timestamp)
      - `metadata` (jsonb - custom sensor properties)
    
    - `sensor_readings` - Time-series data from sensors
      - `id` (uuid, primary key)
      - `sensor_id` (uuid, foreign key)
      - `timestamp` (timestamp)
      - `value` (numeric)
      - `unit` (text) - e.g., "dBm", "Hz", "celsius"
      - `signal_quality` (numeric 0-100)
      - `frequency` (numeric, optional)
      - `bandwidth` (numeric, optional)
      - `signal_type` (text, optional)
      - `raw_data` (jsonb - extended sensor-specific data)
    
    - `sensor_alerts` - Triggered when sensor data meets alert conditions
      - `id` (uuid, primary key)
      - `sensor_id` (uuid, foreign key)
      - `alert_type` (text) - "threshold_exceeded", "no_data", "connection_lost"
      - `message` (text)
      - `severity` (text) - "info", "warning", "critical"
      - `triggered_at` (timestamp)
      - `resolved_at` (timestamp, nullable)
    
    - `blockchain_events` - Audit trail of important events
      - `id` (uuid, primary key)
      - `sensor_id` (uuid, foreign key)
      - `event_type` (text) - "reading_received", "alert_triggered", "sensor_registered"
      - `event_data` (jsonb)
      - `blockchain_hash` (text, hash of event for verification)
      - `created_at` (timestamp)

  2. Security
    - Enable RLS on all tables
    - Sensors are user-owned; only users can see their sensors
    - Sensor readings are accessible to sensor owner and can be accessed via API key
    - Blockchain events are append-only audit logs

  3. Indexes
    - sensor_id on sensor_readings for fast queries
    - timestamp on sensor_readings for time-range queries
    - device_id on sensors for API lookups
*/

CREATE TABLE IF NOT EXISTS sensors (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  device_id text NOT NULL UNIQUE,
  name text NOT NULL,
  location text,
  sensor_type text NOT NULL DEFAULT 'RF_ANALYZER',
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'error')),
  last_reading timestamptz,
  api_key text NOT NULL UNIQUE DEFAULT encode(gen_random_bytes(32), 'hex'),
  created_at timestamptz DEFAULT now(),
  metadata jsonb DEFAULT '{}'::jsonb,
  updated_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sensor_readings (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  sensor_id uuid NOT NULL REFERENCES sensors(id) ON DELETE CASCADE,
  timestamp timestamptz DEFAULT now(),
  value numeric NOT NULL,
  unit text NOT NULL,
  signal_quality numeric CHECK (signal_quality >= 0 AND signal_quality <= 100),
  frequency numeric,
  bandwidth numeric,
  signal_type text,
  raw_data jsonb DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS sensor_alerts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  sensor_id uuid NOT NULL REFERENCES sensors(id) ON DELETE CASCADE,
  alert_type text NOT NULL,
  message text NOT NULL,
  severity text NOT NULL DEFAULT 'warning' CHECK (severity IN ('info', 'warning', 'critical')),
  triggered_at timestamptz DEFAULT now(),
  resolved_at timestamptz
);

CREATE TABLE IF NOT EXISTS blockchain_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  sensor_id uuid NOT NULL REFERENCES sensors(id) ON DELETE CASCADE,
  event_type text NOT NULL,
  event_data jsonb NOT NULL,
  blockchain_hash text NOT NULL UNIQUE,
  created_at timestamptz DEFAULT now()
);

CREATE INDEX idx_sensor_readings_sensor_id ON sensor_readings(sensor_id);
CREATE INDEX idx_sensor_readings_timestamp ON sensor_readings(timestamp DESC);
CREATE INDEX idx_sensors_device_id ON sensors(device_id);
CREATE INDEX idx_sensors_user_id ON sensors(user_id);
CREATE INDEX idx_sensor_alerts_sensor_id ON sensor_alerts(sensor_id);
CREATE INDEX idx_blockchain_events_sensor_id ON blockchain_events(sensor_id);

ALTER TABLE sensors ENABLE ROW LEVEL SECURITY;
ALTER TABLE sensor_readings ENABLE ROW LEVEL SECURITY;
ALTER TABLE sensor_alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE blockchain_events ENABLE ROW LEVEL SECURITY;

-- Sensors: Users can see only their own sensors
CREATE POLICY "Users can view own sensors"
  ON sensors FOR SELECT
  TO authenticated
  USING (auth.uid() = user_id);

CREATE POLICY "Users can create sensors"
  ON sensors FOR INSERT
  TO authenticated
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own sensors"
  ON sensors FOR UPDATE
  TO authenticated
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete own sensors"
  ON sensors FOR DELETE
  TO authenticated
  USING (auth.uid() = user_id);

-- Sensor readings: Only accessible by sensor owner
CREATE POLICY "Users can view readings from own sensors"
  ON sensor_readings FOR SELECT
  TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM sensors
      WHERE sensors.id = sensor_readings.sensor_id
      AND sensors.user_id = auth.uid()
    )
  );

CREATE POLICY "Service role can insert sensor readings"
  ON sensor_readings FOR INSERT
  TO service_role
  WITH CHECK (true);

-- Sensor alerts: Only accessible by sensor owner
CREATE POLICY "Users can view alerts from own sensors"
  ON sensor_alerts FOR SELECT
  TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM sensors
      WHERE sensors.id = sensor_alerts.sensor_id
      AND sensors.user_id = auth.uid()
    )
  );

CREATE POLICY "Service role can insert alerts"
  ON sensor_alerts FOR INSERT
  TO service_role
  WITH CHECK (true);

-- Blockchain events: Append-only audit log, accessible by sensor owner
CREATE POLICY "Users can view blockchain events from own sensors"
  ON blockchain_events FOR SELECT
  TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM sensors
      WHERE sensors.id = blockchain_events.sensor_id
      AND sensors.user_id = auth.uid()
    )
  );

CREATE POLICY "Service role can insert blockchain events"
  ON blockchain_events FOR INSERT
  TO service_role
  WITH CHECK (true);
