const AP_CONTENT_DEFAULT = "https://power-api.yingdao.com/oapi/power/v1/rest/flow/dd093840-4bac-4af8-afc0-23d8ac46f666/execute";
const AP_SENTIMENT_DEFAULT = "https://power-api.yingdao.com/oapi/power/v1/rest/flow/4aad96bc-b721-4475-90b4-46a7d6e6f6d8/execute";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "Content-Type, Authorization, x-analyze-key",
  "Access-Control-Allow-Methods": "POST, OPTIONS"
};

const json = (statusCode, body) => ({
  statusCode,
  headers: { ...corsHeaders, "Content-Type": "application/json" },
  body: JSON.stringify(body)
});

function pickFirstString(value, preferredKeys) {
  if (typeof value === "string") {
    const s = value.trim();
    return s ? s.slice(0, 80) : null;
  }
  if (!value || typeof value !== "object") return null;
  for (const k of preferredKeys) {
    if (Object.prototype.hasOwnProperty.call(value, k)) {
      const hit = pickFirstString(value[k], preferredKeys);
      if (hit) return hit;
    }
  }
  for (const k of Object.keys(value)) {
    const hit = pickFirstString(value[k], preferredKeys);
    if (hit) return hit;
  }
  return null;
}

async function callAp(url, token, content) {
  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ input: { input_text_0: content } })
  });
  const text = await res.text();
  let payload = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    payload = { raw: text };
  }
  return { ok: res.ok, status: res.status, payload };
}

async function fetchRows({ supabaseUrl, serviceKey, tableName, postIds, limit }) {
  const encodedTable = encodeURIComponent(tableName);
  const safeIds = postIds.slice(0, limit).map(v => String(v).replace(/,/g, ""));
  const inValue = safeIds.join(",");
  const query = `select=post_id,content,content_type,sentiment&post_id=in.(${inValue})`;
  const url = `${supabaseUrl}/rest/v1/${encodedTable}?${query}`;
  const res = await fetch(url, {
    headers: {
      apikey: serviceKey,
      Authorization: `Bearer ${serviceKey}`
    }
  });
  const text = await res.text();
  let payload = [];
  try {
    payload = text ? JSON.parse(text) : [];
  } catch {
    payload = [];
  }
  if (!res.ok) throw new Error(`db_select_failed: ${text}`);
  return Array.isArray(payload) ? payload : [];
}

async function updateRow({ supabaseUrl, serviceKey, tableName, postId, patch }) {
  const encodedTable = encodeURIComponent(tableName);
  const filter = `post_id=eq.${encodeURIComponent(String(postId))}`;
  const url = `${supabaseUrl}/rest/v1/${encodedTable}?${filter}`;
  const res = await fetch(url, {
    method: "PATCH",
    headers: {
      apikey: serviceKey,
      Authorization: `Bearer ${serviceKey}`,
      "Content-Type": "application/json",
      Prefer: "return=minimal"
    },
    body: JSON.stringify(patch)
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`db_update_failed: ${text}`);
  }
}

exports.handler = async (event) => {
  if (event.httpMethod === "OPTIONS") return { statusCode: 200, headers: corsHeaders, body: "ok" };
  if (event.httpMethod !== "POST") return json(405, { error: "method_not_allowed" });

  const supabaseUrl = process.env.SUPABASE_URL || "";
  const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY || "";
  const apToken = process.env.AP_TOKEN || "";
  const apContentUrl = process.env.AP_CONTENT_URL || AP_CONTENT_DEFAULT;
  const apSentimentUrl = process.env.AP_SENTIMENT_URL || AP_SENTIMENT_DEFAULT;
  const tableName = process.env.POSTS_TABLE || "影刀社区帖子";
  const analyzeKey = process.env.NETLIFY_ANALYZE_KEY || "";

  if (!supabaseUrl || !serviceKey) return json(500, { error: "missing_supabase_env" });
  if (!apToken) return json(500, { error: "missing_ap_token" });

  const clientKey = event.headers["x-analyze-key"] || event.headers["X-Analyze-Key"] || "";
  if (analyzeKey && clientKey !== analyzeKey) return json(401, { error: "invalid_analyze_key" });

  let body = {};
  try {
    body = event.body ? JSON.parse(event.body) : {};
  } catch {
    return json(400, { error: "invalid_json" });
  }

  const mode = body.mode || "both";
  const postIds = Array.isArray(body.post_ids) ? body.post_ids.map(v => String(v)) : [];
  const limit = Math.min(Number(body.limit || 200), 500);
  const onlyMissing = body.only_missing !== false;

  if (!postIds.length) return json(400, { error: "post_ids_required" });

  let rows = [];
  try {
    rows = await fetchRows({ supabaseUrl, serviceKey, tableName, postIds, limit });
  } catch (e) {
    return json(500, { error: String(e.message || e) });
  }

  const candidates = rows.filter(r => {
    if (!r || !r.post_id || !r.content) return false;
    if (!onlyMissing) return true;
    if (mode === "content") return !r.content_type;
    if (mode === "sentiment") return !r.sentiment;
    return !r.content_type || !r.sentiment;
  });

  const preferredContentKeys = ["content_type", "type", "label", "output_text_0", "result"];
  const preferredSentKeys = ["sentiment", "label", "output_text_0", "result"];
  const failed = [];
  let updated = 0;

  for (const row of candidates) {
    const patch = {};
    let ok = true;

    if (mode === "content" || mode === "both") {
      const ap = await callAp(apContentUrl, apToken, String(row.content));
      if (ap.ok) {
        const label = pickFirstString(ap.payload, preferredContentKeys);
        if (label) patch.content_type = label;
        else ok = false;
      } else {
        ok = false;
      }
    }

    if (mode === "sentiment" || mode === "both") {
      const ap = await callAp(apSentimentUrl, apToken, String(row.content));
      if (ap.ok) {
        const label = pickFirstString(ap.payload, preferredSentKeys);
        if (label) patch.sentiment = label;
        else ok = false;
      } else {
        ok = false;
      }
    }

    patch.ai_status = ok ? "done" : "failed";
    patch.ai_updated_at = new Date().toISOString();

    try {
      await updateRow({ supabaseUrl, serviceKey, tableName, postId: row.post_id, patch });
      updated += 1;
    } catch (e) {
      failed.push({ post_id: String(row.post_id), error: String(e.message || e) });
    }
  }

  return json(200, {
    success: true,
    mode,
    requested: postIds.length,
    processed: candidates.length,
    updated,
    failed_count: failed.length,
    failed
  });
};

