import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2.39.0";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Client-Info, Apikey",
};

// ── Types ─────────────────────────────────────────────────────────────────────

interface SpectrumBin {
  freq_mhz: number;
  power_dbm: number;
}

interface PeakInput {
  peak_freq_mhz: number;
  peak_power_dbm: number;
  bandwidth_khz?: number;
  peak_type?: string;
  harmonic_order?: number;
}

interface RecordingPayload {
  session_id?: string;           // attach to existing session, or omit to auto-create
  node_id?: number;
  frequency_mhz: number;
  bandwidth_mhz?: number;
  sample_rate_mhz?: number;
  fft_size?: number;
  power_dbm: number;
  noise_floor_dbm?: number;
  iq_data_hash?: string;
  spectrum_bins?: SpectrumBin[];
  peaks?: PeakInput[];
  access_tier?: string;
  metadata?: Record<string, unknown>;
}

interface IngestPayload {
  recording: RecordingPayload;
  device_type?: "hackrf" | "rtlsdr" | "airspy" | "mock";
  close_session?: boolean;        // if true, finalize session after this recording
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function blockchainHash(data: unknown): string {
  const text = JSON.stringify(data);
  let hash = 0;
  for (let i = 0; i < text.length; i++) {
    const char = text.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash;
  }
  return `0x${Math.abs(hash).toString(16).padStart(64, "0")}`;
}

function classifyPeak(freq_mhz: number): string {
  if (freq_mhz >= 10229 && freq_mhz <= 10271) return "dna_resonance";
  if (freq_mhz >= 6000 && freq_mhz <= 8500)   return "uwb_pulse";
  if (Math.abs(freq_mhz - 1935) <= 5)         return "lte_leakage";
  if (freq_mhz >= 30600 && freq_mhz <= 30900) return "harmonic";
  return "unknown";
}

// ── Handler ───────────────────────────────────────────────────────────────────

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { status: 200, headers: corsHeaders });
  }

  try {
    const supabase = createClient(
      Deno.env.get("SUPABASE_URL") || "",
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "",
    );

    if (req.method !== "POST") {
      return new Response(JSON.stringify({ error: "Only POST allowed" }), {
        status: 405,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    // Auth: extract user from JWT
    const authHeader = req.headers.get("Authorization");
    if (!authHeader?.startsWith("Bearer ")) {
      return new Response(JSON.stringify({ error: "Missing Authorization header" }), {
        status: 401,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const userClient = createClient(
      Deno.env.get("SUPABASE_URL") || "",
      Deno.env.get("SUPABASE_ANON_KEY") || "",
      { global: { headers: { Authorization: authHeader } } },
    );
    const { data: { user }, error: authError } = await userClient.auth.getUser();
    if (authError || !user) {
      return new Response(JSON.stringify({ error: "Unauthorized" }), {
        status: 401,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const payload: IngestPayload = await req.json();
    const { recording, device_type = "hackrf", close_session = false } = payload;

    if (!recording?.frequency_mhz || recording.power_dbm === undefined) {
      return new Response(
        JSON.stringify({ error: "Missing required fields: frequency_mhz, power_dbm" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    // ── 1. Resolve or create spectrum session ─────────────────────────────────
    let sessionId = recording.session_id ?? null;

    if (!sessionId) {
      const { data: newSession, error: sessionErr } = await supabase
        .from("spectrum_sessions")
        .insert({
          user_id: user.id,
          node_id: recording.node_id ?? null,
          device_type,
          center_freq_mhz: recording.frequency_mhz,
          sample_rate_mhz: recording.sample_rate_mhz ?? 10.0,
        })
        .select("id")
        .single();

      if (sessionErr) throw sessionErr;
      sessionId = newSession.id;
    }

    // ── 2. Insert spectrum recording ──────────────────────────────────────────
    const { data: rec, error: recErr } = await supabase
      .from("spectrum_recordings")
      .insert({
        user_id: user.id,
        session_id: sessionId,
        node_id: recording.node_id ?? null,
        frequency_mhz: recording.frequency_mhz,
        bandwidth_mhz: recording.bandwidth_mhz ?? 10.0,
        sample_rate_mhz: recording.sample_rate_mhz ?? 10.0,
        fft_size: recording.fft_size ?? 1024,
        power_dbm: recording.power_dbm,
        noise_floor_dbm: recording.noise_floor_dbm ?? null,
        peak_count: recording.peaks?.length ?? 0,
        iq_data_hash: recording.iq_data_hash ?? null,
        spectrum_bins: recording.spectrum_bins ?? null,
        access_tier: recording.access_tier ?? "LOW",
        metadata: recording.metadata ?? {},
      })
      .select("id, timestamp")
      .single();

    if (recErr) throw recErr;

    // ── 3. Stamp blockchain hash on recording ─────────────────────────────────
    const recHash = blockchainHash({
      id: rec.id,
      user_id: user.id,
      frequency_mhz: recording.frequency_mhz,
      power_dbm: recording.power_dbm,
      timestamp: rec.timestamp,
    });

    await supabase
      .from("spectrum_recordings")
      .update({ iq_data_hash: recording.iq_data_hash ?? recHash })
      .eq("id", rec.id);

    // ── 4. Insert frequency peaks ─────────────────────────────────────────────
    const insertedPeaks: string[] = [];

    if (recording.peaks && recording.peaks.length > 0) {
      const peakRows = recording.peaks.map((p) => ({
        recording_id: rec.id,
        user_id: user.id,
        peak_freq_mhz: p.peak_freq_mhz,
        peak_power_dbm: p.peak_power_dbm,
        bandwidth_khz: p.bandwidth_khz ?? null,
        snr_db: recording.noise_floor_dbm != null
          ? p.peak_power_dbm - recording.noise_floor_dbm
          : null,
        peak_type: p.peak_type ?? classifyPeak(p.peak_freq_mhz),
        harmonic_order: p.harmonic_order ?? null,
      }));

      const { error: peakErr } = await supabase
        .from("frequency_peaks")
        .insert(peakRows);

      if (peakErr) throw peakErr;

      peakRows.forEach((p) => {
        insertedPeaks.push(`${p.peak_freq_mhz} MHz (${p.peak_type})`);
      });
    }

    // ── 5. Increment session recording count ──────────────────────────────────
    await supabase.rpc("increment_session_count", { p_session_id: sessionId });

    // ── 6. Close session if requested ─────────────────────────────────────────
    let sessionHash: string | null = null;
    if (close_session) {
      const { data: hashResult } = await supabase
        .rpc("close_spectrum_session", { p_session_id: sessionId });
      sessionHash = hashResult;
    }

    return new Response(
      JSON.stringify({
        success: true,
        recording_id: rec.id,
        session_id: sessionId,
        blockchain_hash: recHash,
        peaks_stored: insertedPeaks.length,
        peaks: insertedPeaks,
        ...(sessionHash && { session_hash: sessionHash }),
      }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } },
    );
  } catch (error) {
    console.error("Error:", error);
    return new Response(
      JSON.stringify({
        error: error instanceof Error ? error.message : "Internal server error",
      }),
      {
        status: 500,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      },
    );
  }
});
