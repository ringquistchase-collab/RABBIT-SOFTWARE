/*
  # SDR Spectrum Analysis Schema

  1. New Tables
    - `spectrum_recordings`: Stores RF signal snapshots with frequency, power level, and metadata
      - `id` (uuid, primary key)
      - `frequency_mhz` (numeric) - Center frequency in MHz
      - `power_dbm` (numeric) - Signal power in dBm
      - `bandwidth_mhz` (numeric) - Bandwidth in MHz
      - `timestamp` (timestamp) - When the recording was taken
      - `signal_type` (text) - Classification (WiFi, LTE, etc.)
      - `user_id` (uuid, foreign key) - User who recorded
      - `created_at` (timestamp)

    - `spectrum_sessions`: Groups related recordings together
      - `id` (uuid, primary key)
      - `name` (text) - Session name
      - `description` (text) - Session notes
      - `start_time` (timestamp)
      - `end_time` (timestamp)
      - `user_id` (uuid, foreign key)
      - `created_at` (timestamp)

    - `frequency_peaks`: Identifies prominent signals in recordings
      - `id` (uuid, primary key)
      - `recording_id` (uuid, foreign key)
      - `frequency_mhz` (numeric)
      - `power_dbm` (numeric)
      - `peak_type` (text) - Type of peak detected
      - `created_at` (timestamp)

  2. Security
    - Enable RLS on all tables
    - Users can only view/edit their own data
*/

CREATE TABLE IF NOT EXISTS spectrum_recordings (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  frequency_mhz numeric NOT NULL,
  power_dbm numeric NOT NULL,
  bandwidth_mhz numeric,
  timestamp timestamptz NOT NULL,
  signal_type text DEFAULT 'unknown',
  user_id uuid REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
  created_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS spectrum_sessions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  description text,
  start_time timestamptz NOT NULL,
  end_time timestamptz,
  user_id uuid REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
  created_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS frequency_peaks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  recording_id uuid REFERENCES spectrum_recordings(id) ON DELETE CASCADE NOT NULL,
  frequency_mhz numeric NOT NULL,
  power_dbm numeric NOT NULL,
  peak_type text DEFAULT 'standard',
  created_at timestamptz DEFAULT now()
);

ALTER TABLE spectrum_recordings ENABLE ROW LEVEL SECURITY;
ALTER TABLE spectrum_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE frequency_peaks ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own recordings"
  ON spectrum_recordings FOR SELECT
  TO authenticated
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own recordings"
  ON spectrum_recordings FOR INSERT
  TO authenticated
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own recordings"
  ON spectrum_recordings FOR UPDATE
  TO authenticated
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete own recordings"
  ON spectrum_recordings FOR DELETE
  TO authenticated
  USING (auth.uid() = user_id);

CREATE POLICY "Users can view own sessions"
  ON spectrum_sessions FOR SELECT
  TO authenticated
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own sessions"
  ON spectrum_sessions FOR INSERT
  TO authenticated
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own sessions"
  ON spectrum_sessions FOR UPDATE
  TO authenticated
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete own sessions"
  ON spectrum_sessions FOR DELETE
  TO authenticated
  USING (auth.uid() = user_id);

CREATE POLICY "Users can view peaks from own recordings"
  ON frequency_peaks FOR SELECT
  TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM spectrum_recordings
      WHERE spectrum_recordings.id = frequency_peaks.recording_id
      AND spectrum_recordings.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can insert peaks to own recordings"
  ON frequency_peaks FOR INSERT
  TO authenticated
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM spectrum_recordings
      WHERE spectrum_recordings.id = recording_id
      AND spectrum_recordings.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can delete own peaks"
  ON frequency_peaks FOR DELETE
  TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM spectrum_recordings
      WHERE spectrum_recordings.id = frequency_peaks.recording_id
      AND spectrum_recordings.user_id = auth.uid()
    )
  );

CREATE INDEX IF NOT EXISTS idx_recordings_user_timestamp 
  ON spectrum_recordings(user_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_recordings_frequency 
  ON spectrum_recordings(frequency_mhz);

CREATE INDEX IF NOT EXISTS idx_sessions_user 
  ON spectrum_sessions(user_id);

CREATE INDEX IF NOT EXISTS idx_peaks_recording 
  ON frequency_peaks(recording_id);
