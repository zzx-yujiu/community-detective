import { serve } from "https://deno.land/std@0.224.0/http/server.ts";
import { createClient } from "npm:@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

type Mode = "content" | "sentiment" | "both";

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}

function pickFirstString(value: unknown, preferredKeys: string[]): string | null {
  if (typeof value === "string") {
    const s = value.trim();
    if (!s) return null;
    if (s.length > 80) return s.slice(0, 80);
    return s;
  }
  if (!value || typeof value !== "object") return null;

  const obj = value as Record<string, unknown>;
  for (const k of preferredKeys) {
    if (k in obj) {
      const hit = pickFirstString(obj[k], preferredKeys);
      if (hit) return hit;
    }
  }

  for (const k of Object.keys(obj)) {
    const hit = pickFirstString(obj[k], preferredKeys);
    if (hit) return hit;
  }

  return null;
}

async function callAp(apUrl: string, token: string, content: string) {
  const res = await fetch(apUrl, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ input: { input_text_0: content } }),
  });
  const text = await res.text();
  let json: unknown = null;
  try {
    json = text ? JSON.parse(text) : null;
  } catch {
    json = { raw: text };
  }
  if (!res.ok) {
    return { ok: false, status: res.status, json };
  }
  return { ok: true, status: res.status, json };
}

serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  if (req.method !== "POST") return jsonResponse(405, { error: "method_not_allowed" });

  const supabaseUrl = Deno.env.get("SUPABASE_URL") ?? "";
  const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
  const apToken = Deno.env.get("AP_TOKEN") ?? "";
  const apContentUrl = Deno.env.get("AP_CONTENT_URL") ??
    "https://power-api.yingdao.com/oapi/power/v1/rest/flow/dd093840-4bac-4af8-afc0-23d8ac46f666/execute";
  const apSentimentUrl = Deno.env.get("AP_SENTIMENT_URL") ??
    "https://power-api.yingdao.com/oapi/power/v1/rest/flow/4aad96bc-b721-4475-90b4-46a7d6e6f6d8/execute";
  const tableName = Deno.env.get("POSTS_TABLE") ?? "影刀社区帖子";

  if (!supabaseUrl || !serviceKey) return jsonResponse(500, { error: "missing_supabase_env" });
  if (!apToken) return jsonResponse(500, { error: "missing_ap_token" });

  const authHeader = req.headers.get("Authorization") || "";
  const apiKeyHeader = req.headers.get("apikey") || "";
  if (!authHeader && !apiKeyHeader) return jsonResponse(401, { error: "missing_client_auth" });

  let body: any = null;
  try {
    body = await req.json();
  } catch {
    return jsonResponse(400, { error: "invalid_json" });
  }

  const postIds: string[] = Array.isArray(body?.post_ids) ? body.post_ids.map(String) : [];
  const mode: Mode = (body?.mode as Mode) || "both";
  const limit = Math.min(Number(body?.limit ?? 200), 500);
  const onlyMissing = Boolean(body?.only_missing ?? true);

  if (!postIds.length) return jsonResponse(400, { error: "post_ids_required" });

  const admin = createClient(supabaseUrl, serviceKey, { auth: { persistSession: false } });

  const { data: rows, error: selectError } = await admin
    .from(tableName)
    .select("post_id, content, content_type, sentiment")
    .in("post_id", postIds.slice(0, limit));

  if (selectError) return jsonResponse(500, { error: "db_select_failed", detail: selectError.message });

  const candidates = (rows ?? []).filter((r: any) => {
    if (!r?.post_id) return false;
    if (!r?.content) return false;
    if (!onlyMissing) return true;
    if (mode === "content") return !r.content_type;
    if (mode === "sentiment") return !r.sentiment;
    return !r.content_type || !r.sentiment;
  });

  const preferredContentKeys = ["content_type", "type", "label", "output_text_0", "result"];
  const preferredSentKeys = ["sentiment", "label", "output_text_0", "result"];

  let updated = 0;
  const failed: Array<{ post_id: string; error: string }> = [];

  for (const row of candidates) {
    const postId = String((row as any).post_id);
    const content = String((row as any).content);

    const patch: Record<string, unknown> = {};
    let ok = true;

    if (mode === "content" || mode === "both") {
      const r = await callAp(apContentUrl, apToken, content);
      if (r.ok) {
        const label = pickFirstString(r.json, preferredContentKeys);
        if (label) patch.content_type = label;
        else ok = false;
      } else {
        ok = false;
      }
    }

    if (mode === "sentiment" || mode === "both") {
      const r = await callAp(apSentimentUrl, apToken, content);
      if (r.ok) {
        const label = pickFirstString(r.json, preferredSentKeys);
        if (label) patch.sentiment = label;
        else ok = false;
      } else {
        ok = false;
      }
    }

    patch.ai_status = ok ? "done" : "failed";
    patch.ai_updated_at = new Date().toISOString();

    const { error: updateError } = await admin
      .from(tableName)
      .update(patch)
      .eq("post_id", postId);

    if (updateError) {
      failed.push({ post_id: postId, error: updateError.message });
      continue;
    }
    updated += 1;
  }

  return jsonResponse(200, {
    success: true,
    mode,
    requested: postIds.length,
    processed: candidates.length,
    updated,
    failed_count: failed.length,
    failed,
  });
});

