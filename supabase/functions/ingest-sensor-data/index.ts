import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2.39.0";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Client-Info, Apikey",
};

interface SensorReading {
  value: number;
  unit: string;
  signal_quality?: number;
  frequency?: number;
  bandwidth?: number;
  signal_type?: string;
  raw_data?: Record<string, unknown>;
}

interface IngestPayload {
  api_key: string;
  reading: SensorReading;
  alert?: {
    type: string;
    message: string;
    severity: "info" | "warning" | "critical";
  };
}

function generateBlockchainHash(data: unknown): string {
  const text = JSON.stringify(data);
  let hash = 0;
  for (let i = 0; i < text.length; i++) {
    const char = text.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash;
  }
  return `0x${Math.abs(hash).toString(16).padStart(64, "0")}`;
}

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

    const payload: IngestPayload = await req.json();
    const { api_key, reading, alert } = payload;

    if (!api_key || !reading) {
      return new Response(
        JSON.stringify({ error: "Missing api_key or reading" }),
        { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } },
      );
    }

    // Authenticate sensor by API key
    const { data: sensor, error: sensorError } = await supabase
      .from("sensors")
      .select("id, user_id")
      .eq("api_key", api_key)
      .maybeSingle();

    if (sensorError || !sensor) {
      return new Response(JSON.stringify({ error: "Invalid API key" }), {
        status: 401,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    // Insert sensor reading
    const { data: readingData, error: readingError } = await supabase
      .from("sensor_readings")
      .insert({
        sensor_id: sensor.id,
        value: reading.value,
        unit: reading.unit,
        signal_quality: reading.signal_quality,
        frequency: reading.frequency,
        bandwidth: reading.bandwidth,
        signal_type: reading.signal_type,
        raw_data: reading.raw_data || {},
      })
      .select()
      .single();

    if (readingError) throw readingError;

    // Stamp blockchain hash on reading
    const readingHash = generateBlockchainHash({
      reading_id: readingData.id,
      sensor_id: sensor.id,
      value: reading.value,
      unit: reading.unit,
      timestamp: readingData.created_at,
    });

    // Update blockchain_hash on the reading row
    await supabase
      .from("sensor_readings")
      .update({ blockchain_hash: readingHash })
      .eq("id", readingData.id);

    // Update sensor last_reading timestamp
    await supabase
      .from("sensors")
      .update({ last_reading: new Date().toISOString() })
      .eq("id", sensor.id);

    // Handle optional alert
    let alertHash: string | null = null;
    if (alert) {
      alertHash = generateBlockchainHash({
        reading_id: readingData.id,
        alert_type: alert.type,
        message: alert.message,
        severity: alert.severity,
        timestamp: new Date().toISOString(),
      });

      await supabase.from("sensor_alerts").insert({
        sensor_id: sensor.id,
        reading_id: readingData.id,
        alert_type: alert.type,
        message: alert.message,
        severity: alert.severity,
        blockchain_hash: alertHash,
      });
    }

    return new Response(
      JSON.stringify({
        success: true,
        reading_id: readingData.id,
        blockchain_hash: readingHash,
        ...(alertHash && { alert_hash: alertHash }),
      }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } },
    );
  } catch (error) {
    console.error("Error:", error);
    return new Response(
      JSON.stringify({
        error: error instanceof Error ? error.message : "Internal server error",
      }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } },
    );
  }
});
