import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2.39.0";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Client-Info, Apikey",
};

interface SensorPayload {
  device_id: string;
  name: string;
  location?: string;
  sensor_type?: string;
  metadata?: Record<string, unknown>;
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response(null, {
      status: 200,
      headers: corsHeaders,
    });
  }

  try {
    const supabase = createClient(
      Deno.env.get("SUPABASE_URL") || "",
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || ""
    );

    const authHeader = req.headers.get("Authorization");
    if (!authHeader) {
      return new Response(JSON.stringify({ error: "Unauthorized" }), {
        status: 401,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const token = authHeader.replace("Bearer ", "");
    const { data: userData, error: userError } = await supabase.auth.getUser(token);

    if (userError || !userData.user) {
      return new Response(JSON.stringify({ error: "Invalid token" }), {
        status: 401,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const userId = userData.user.id;

    if (req.method === "GET") {
      const { data: sensors, error: listError } = await supabase
        .from("sensors")
        .select("id, device_id, name, location, sensor_type, status, last_reading, created_at, metadata")
        .eq("user_id", userId)
        .order("created_at", { ascending: false });

      if (listError) throw listError;

      return new Response(JSON.stringify({ sensors }), {
        status: 200,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    if (req.method === "POST") {
      const payload: SensorPayload = await req.json();
      const { device_id, name, location, sensor_type, metadata } = payload;

      if (!device_id || !name) {
        return new Response(
          JSON.stringify({ error: "Missing required fields: device_id, name" }),
          { status: 400, headers: { ...corsHeaders, "Content-Type": "application/json" } }
        );
      }

      const { data: sensor, error: createError } = await supabase
        .from("sensors")
        .insert({
          user_id: userId,
          device_id,
          name,
          location: location || "",
          sensor_type: sensor_type || "RF_ANALYZER",
          metadata: metadata || {},
        })
        .select()
        .single();

      if (createError) throw createError;

      // Create blockchain event for sensor registration
      const registrationHash = `0x${Math.random().toString(16).slice(2)}`;
      await supabase.from("blockchain_events").insert({
        sensor_id: sensor.id,
        event_type: "sensor_registered",
        event_data: { device_id, name, location, sensor_type },
        blockchain_hash: registrationHash,
      });

      return new Response(JSON.stringify({ sensor }), {
        status: 201,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    if (req.method === "PUT") {
      const url = new URL(req.url);
      const sensorId = url.searchParams.get("id");
      const payload: Partial<SensorPayload> = await req.json();

      if (!sensorId) {
        return new Response(JSON.stringify({ error: "Missing sensor id" }), {
          status: 400,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        });
      }

      const { data: sensor, error: updateError } = await supabase
        .from("sensors")
        .update(payload)
        .eq("id", sensorId)
        .eq("user_id", userId)
        .select()
        .single();

      if (updateError) throw updateError;

      return new Response(JSON.stringify({ sensor }), {
        status: 200,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    if (req.method === "DELETE") {
      const url = new URL(req.url);
      const sensorId = url.searchParams.get("id");

      if (!sensorId) {
        return new Response(JSON.stringify({ error: "Missing sensor id" }), {
          status: 400,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        });
      }

      const { error: deleteError } = await supabase
        .from("sensors")
        .delete()
        .eq("id", sensorId)
        .eq("user_id", userId);

      if (deleteError) throw deleteError;

      return new Response(JSON.stringify({ success: true }), {
        status: 200,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    return new Response(JSON.stringify({ error: "Method not allowed" }), {
      status: 405,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  } catch (error) {
    console.error("Error:", error);
    return new Response(
      JSON.stringify({
        error: error instanceof Error ? error.message : "Internal server error",
      }),
      {
        status: 500,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      }
    );
  }
});
