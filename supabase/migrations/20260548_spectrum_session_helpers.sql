-- Spectrum session helper functions for ingest-spectrum-data Edge Function

CREATE OR REPLACE FUNCTION increment_session_count(p_session_id UUID)
RETURNS VOID LANGUAGE sql SECURITY DEFINER AS $$
    UPDATE spectrum_sessions
    SET recording_count = recording_count + 1
    WHERE id = p_session_id;
$$;
