/**
 * TavaOne Education API — Cloudflare Worker
 *
 * Public routes (no auth):
 *   GET  /api/classes              — list upcoming classes
 *   GET  /api/classes/:id          — single class detail
 *   POST /api/register             — submit registration (free or initiate paid)
 *   POST /api/stripe-webhook       — Stripe webhook (marks paid)
 *
 * Admin routes (Cloudflare Access JWT required):
 *   GET  /api/admin/classes        — list all classes (with counts)
 *   POST /api/admin/classes        — create a class
 *   GET  /api/admin/roster/:classId — full roster with PII
 *   PATCH /api/admin/registrations/:id — update registration (consent, paid, notes)
 *   DELETE /api/admin/registrations/:id — remove a registration
 */

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Cf-Access-Jwt-Assertion",
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { ...CORS, "Content-Type": "application/json" },
  });
}

function err(msg, status = 400) {
  return json({ error: msg }, status);
}

function id() {
  return crypto.randomUUID();
}

// ---- Cloudflare Access JWT verification ----------------------------------
// Verifies the Cf-Access-Jwt-Assertion header against the Access certs.
// CF_ACCESS_AUD must be set as a Worker secret (the Application Audience tag).
async function verifyAccessJwt(request, env) {
  const token = request.headers.get("Cf-Access-Jwt-Assertion");
  if (!token) return false;
  try {
    const certsUrl = `https://${env.CF_ACCESS_TEAM_DOMAIN}/cdn-cgi/access/certs`;
    const certsRes = await fetch(certsUrl);
    if (!certsRes.ok) return false;
    const { keys } = await certsRes.json();
    // Decode header to find kid
    const [headerB64] = token.split(".");
    const header = JSON.parse(atob(headerB64.replace(/-/g, "+").replace(/_/g, "/")));
    const jwk = keys.find((k) => k.kid === header.kid);
    if (!jwk) return false;
    const key = await crypto.subtle.importKey(
      "jwk", jwk, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"]
    );
    const [, payloadB64, sigB64] = token.split(".");
    const sig = Uint8Array.from(atob(sigB64.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));
    const data = new TextEncoder().encode(`${headerB64}.${payloadB64}`);
    const ok = await crypto.subtle.verify("RSASSA-PKCS1-v1_5", key, sig, data);
    if (!ok) return false;
    const payload = JSON.parse(atob(payloadB64.replace(/-/g, "+").replace(/_/g, "/")));
    if (payload.aud !== env.CF_ACCESS_AUD) return false;
    if (payload.exp < Math.floor(Date.now() / 1000)) return false;
    return true;
  } catch {
    return false;
  }
}

async function requireAdmin(request, env) {
  const ok = await verifyAccessJwt(request, env);
  if (!ok) return err("Unauthorized", 401);
  return null;
}

// ---- Route dispatcher ----------------------------------------------------
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;
    const method = request.method;

    if (method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });

    // ── Public: list upcoming classes ─────────────────────────────────────
    if (method === "GET" && path === "/api/classes") {
      const { results } = await env.DB.prepare(
        `SELECT id, title, starts_at, price_cents, capacity,
                (SELECT COUNT(*) FROM registrations r WHERE r.class_id = c.id AND r.paid = 1) AS enrolled
         FROM classes c WHERE starts_at >= datetime('now') ORDER BY starts_at ASC`
      ).all();
      return json(results);
    }

    // ── Public: single class ───────────────────────────────────────────────
    const classMatch = path.match(/^\/api\/classes\/([^/]+)$/);
    if (method === "GET" && classMatch) {
      const row = await env.DB.prepare(
        `SELECT id, title, starts_at, price_cents, capacity,
                (SELECT COUNT(*) FROM registrations r WHERE r.class_id = c.id AND r.paid = 1) AS enrolled
         FROM classes c WHERE id = ?`
      ).bind(classMatch[1]).first();
      if (!row) return err("Not found", 404);
      return json(row);
    }

    // ── Public: register ──────────────────────────────────────────────────
    if (method === "POST" && path === "/api/register") {
      let body;
      try { body = await request.json(); } catch { return err("Invalid JSON"); }

      const { class_id, name, email, guardian_name, consent, notes } = body;
      if (!class_id || !name || !email) return err("class_id, name, and email are required");
      if (!/^\S+@\S+\.\S+$/.test(email)) return err("Invalid email");

      const cls = await env.DB.prepare(
        `SELECT id, title, price_cents, capacity,
                (SELECT COUNT(*) FROM registrations r WHERE r.class_id = c.id AND r.paid = 1) AS enrolled
         FROM classes c WHERE id = ?`
      ).bind(class_id).first();
      if (!cls) return err("Class not found", 404);
      if (cls.capacity && cls.enrolled >= cls.capacity) return err("Class is full", 409);

      const regId = id();

      if (cls.price_cents === 0) {
        // Free class — insert as paid immediately
        await env.DB.prepare(
          `INSERT INTO registrations (id, class_id, name, email, guardian_name, consent, paid, notes)
           VALUES (?, ?, ?, ?, ?, ?, 1, ?)`
        ).bind(regId, class_id, name.trim(), email.trim().toLowerCase(),
               guardian_name?.trim() || null, consent ? 1 : 0, notes?.trim() || null).run();
        return json({ status: "registered", registration_id: regId });
      }

      // Paid class — create Stripe Checkout Session
      const stripe = new StripeClient(env.STRIPE_SECRET_KEY);
      const session = await stripe.createCheckoutSession({
        class_id, class_title: cls.title, name, email, registration_id: regId,
        price_cents: cls.price_cents,
        success_url: `${url.origin}/class/success?reg=${regId}`,
        cancel_url: `${url.origin}/class/?id=${class_id}`,
      });

      // Insert as unpaid; webhook will flip paid=1
      await env.DB.prepare(
        `INSERT INTO registrations (id, class_id, name, email, guardian_name, consent, paid, stripe_session_id, notes)
         VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)`
      ).bind(regId, class_id, name.trim(), email.trim().toLowerCase(),
             guardian_name?.trim() || null, consent ? 1 : 0, session.id, notes?.trim() || null).run();

      return json({ status: "pending_payment", checkout_url: session.url, registration_id: regId });
    }

    // ── Stripe webhook ────────────────────────────────────────────────────
    if (method === "POST" && path === "/api/stripe-webhook") {
      const sig = request.headers.get("stripe-signature");
      const rawBody = await request.text();
      const stripe = new StripeClient(env.STRIPE_SECRET_KEY);
      let event;
      try {
        event = await stripe.constructEvent(rawBody, sig, env.STRIPE_WEBHOOK_SECRET);
      } catch {
        return err("Webhook signature invalid", 400);
      }
      if (event.type === "checkout.session.completed") {
        const session = event.data.object;
        const regId = session.metadata?.registration_id;
        if (regId) {
          await env.DB.prepare(`UPDATE registrations SET paid = 1 WHERE id = ?`).bind(regId).run();
        }
      }
      return json({ received: true });
    }

    // ── Admin: list classes ────────────────────────────────────────────────
    if (method === "GET" && path === "/api/admin/classes") {
      const authErr = await requireAdmin(request, env);
      if (authErr) return authErr;
      const { results } = await env.DB.prepare(
        `SELECT c.*, (SELECT COUNT(*) FROM registrations r WHERE r.class_id = c.id) AS total_registrations,
                (SELECT COUNT(*) FROM registrations r WHERE r.class_id = c.id AND r.paid = 1) AS paid_registrations
         FROM classes c ORDER BY starts_at DESC`
      ).all();
      return json(results);
    }

    // ── Admin: create class ───────────────────────────────────────────────
    if (method === "POST" && path === "/api/admin/classes") {
      const authErr = await requireAdmin(request, env);
      if (authErr) return authErr;
      let body;
      try { body = await request.json(); } catch { return err("Invalid JSON"); }
      const { title, starts_at, price_cents = 0, capacity = null } = body;
      if (!title || !starts_at) return err("title and starts_at required");
      const classId = id();
      await env.DB.prepare(
        `INSERT INTO classes (id, title, starts_at, price_cents, capacity) VALUES (?, ?, ?, ?, ?)`
      ).bind(classId, title.trim(), starts_at, price_cents, capacity).run();
      return json({ id: classId }, 201);
    }

    // ── Admin: roster ─────────────────────────────────────────────────────
    const rosterMatch = path.match(/^\/api\/admin\/roster\/([^/]+)$/);
    if (method === "GET" && rosterMatch) {
      const authErr = await requireAdmin(request, env);
      if (authErr) return authErr;
      const cls = await env.DB.prepare(`SELECT * FROM classes WHERE id = ?`).bind(rosterMatch[1]).first();
      if (!cls) return err("Class not found", 404);
      const { results } = await env.DB.prepare(
        `SELECT * FROM registrations WHERE class_id = ? ORDER BY created_at ASC`
      ).bind(rosterMatch[1]).all();
      return json({ class: cls, registrations: results });
    }

    // ── Admin: update registration ────────────────────────────────────────
    const regMatch = path.match(/^\/api\/admin\/registrations\/([^/]+)$/);
    if (method === "PATCH" && regMatch) {
      const authErr = await requireAdmin(request, env);
      if (authErr) return authErr;
      let body;
      try { body = await request.json(); } catch { return err("Invalid JSON"); }
      const allowed = ["consent", "paid", "notes", "guardian_name"];
      const sets = Object.keys(body).filter((k) => allowed.includes(k));
      if (!sets.length) return err("Nothing to update");
      const stmt = `UPDATE registrations SET ${sets.map((k) => `${k} = ?`).join(", ")} WHERE id = ?`;
      await env.DB.prepare(stmt).bind(...sets.map((k) => body[k]), regMatch[1]).run();
      return json({ updated: true });
    }

    if (method === "DELETE" && regMatch) {
      const authErr = await requireAdmin(request, env);
      if (authErr) return authErr;
      await env.DB.prepare(`DELETE FROM registrations WHERE id = ?`).bind(regMatch[1]).run();
      return json({ deleted: true });
    }

    return err("Not found", 404);
  },
};

// ---- Minimal Stripe client -----------------------------------------------
// Uses the Stripe REST API directly — no npm dependency needed in a Worker.
class StripeClient {
  constructor(secretKey) {
    this.key = secretKey;
    this.base = "https://api.stripe.com/v1";
  }

  async _post(path, params) {
    const body = new URLSearchParams(params).toString();
    const res = await fetch(`${this.base}${path}`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${this.key}`,
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error?.message || "Stripe error");
    return data;
  }

  async createCheckoutSession({ class_id, class_title, name, email, registration_id, price_cents, success_url, cancel_url }) {
    return this._post("/checkout/sessions", {
      mode: "payment",
      customer_email: email,
      "line_items[0][price_data][currency]": "usd",
      "line_items[0][price_data][product_data][name]": class_title,
      "line_items[0][price_data][unit_amount]": price_cents,
      "line_items[0][quantity]": 1,
      "metadata[registration_id]": registration_id,
      "metadata[class_id]": class_id,
      "metadata[student_name]": name,
      success_url,
      cancel_url,
    });
  }

  async constructEvent(rawBody, sigHeader, secret) {
    // HMAC-SHA256 verification of Stripe webhook signature
    const sigParts = Object.fromEntries(
      sigHeader.split(",").map((p) => p.split("="))
    );
    const timestamp = sigParts.t;
    const payload = `${timestamp}.${rawBody}`;
    const key = await crypto.subtle.importKey(
      "raw", new TextEncoder().encode(secret),
      { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
    );
    const mac = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(payload));
    const expected = Array.from(new Uint8Array(mac)).map((b) => b.toString(16).padStart(2, "0")).join("");
    const received = sigParts.v1;
    if (!received || expected !== received) throw new Error("Signature mismatch");
    return JSON.parse(rawBody);
  }
}
