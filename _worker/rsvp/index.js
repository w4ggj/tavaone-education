/**
 * TavaOne Education — RSVP Worker
 *
 * Deploy:
 *   1. npx wrangler d1 create tavaone-rsvp
 *      Copy the database_id into wrangler.toml
 *   2. npx wrangler d1 execute tavaone-rsvp --file=schema.sql
 *   3. Set your Resend API key:
 *      npx wrangler secret put RESEND_API_KEY
 *   4. Set the reply-from address:
 *      npx wrangler secret put FROM_EMAIL   (e.g. hello@tavaoneeducation.org)
 *   5. npx wrangler deploy
 *   6. Copy the deployed URL into get-on-the-air.html → RSVP_ENDPOINT
 *      e.g. "https://rsvp.tavaone.workers.dev/signup"
 */

const ALLOWED_ORIGIN = "https://tavaoneeducation.org";

const CORS = {
  "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // Preflight
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS });
    }

    if (request.method === "POST" && url.pathname === "/signup") {
      return handleSignup(request, env);
    }

    if (request.method === "POST" && url.pathname === "/course-signup") {
      return handleCourseSignup(request, env);
    }

    if (request.method === "POST" && url.pathname === "/contact") {
      return handleContact(request, env);
    }

    return new Response("Not found", { status: 404, headers: CORS });
  },
};

async function handleSignup(request, env) {
  let body;
  try {
    body = await request.json();
  } catch {
    return jsonError("Invalid JSON", 400);
  }

  const { name, email, phone = "", party = "Just me", minors = "No" } = body;

  if (!name || !String(name).trim()) return jsonError("Name required", 422);
  if (!email || !/^\S+@\S+\.\S+$/.test(email)) return jsonError("Valid email required", 422);

  // Store in D1
  try {
    await env.DB.prepare(
      `INSERT INTO rsvps (name, email, phone, party, minors, created_at)
       VALUES (?, ?, ?, ?, ?, datetime('now'))`
    ).bind(
      String(name).trim().slice(0, 200),
      String(email).trim().toLowerCase().slice(0, 200),
      String(phone).trim().slice(0, 50),
      String(party).slice(0, 50),
      String(minors).slice(0, 50)
    ).run();
  } catch (err) {
    console.error("D1 insert failed:", err);
    return jsonError("Storage error", 500);
  }

  // Send confirmation via Resend (non-fatal if it fails)
  try {
    await sendConfirmation(env, { name, email });
  } catch (err) {
    console.error("Resend failed:", err);
  }

  return new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: { "Content-Type": "application/json", ...CORS },
  });
}

async function sendConfirmation(env, { name, email }) {
  const firstName = String(name).split(" ")[0];
  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.RESEND_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from: env.FROM_EMAIL,
      to: email,
      reply_to: env.FROM_EMAIL,
      subject: "You're on the list — Get On The Air",
      html: `
<p>Hi ${firstName},</p>
<p>You're on the list. We don't have a date and time locked in yet, but when we do you'll be the first to know — I'll send you the full details as soon as they're set.</p>
<p>If your plans change in the meantime, just reply and I'll take you off the list. No problem at all.</p>
<p>The event is at Balance, 6701 49th St N, Pinellas Park, FL 33781.</p>
<p>73,<br>Joe · W4GGJ<br>TavaOne Education</p>
<hr style="border:none;border-top:1px solid #ddd;margin:24px 0">
<p style="font-size:12px;color:#888;">
TavaOne Education Inc. · 501(c)(3) nonprofit · FDACS Reg. CH84123<br>
You received this because you signed up at tavaoneeducation.org/get-on-the-air
</p>
      `.trim(),
      text: `Hi ${firstName},\n\nYou're on the list. We don't have a date and time locked in yet, but when we do you'll be the first to know — I'll send you the full details as soon as they're set.\n\nIf your plans change in the meantime, just reply and I'll take you off the list. No problem at all.\n\nThe event is at Balance, 6701 49th St N, Pinellas Park, FL 33781.\n\n73,\nJoe · W4GGJ\nTavaOne Education\n\n---\nTavaOne Education Inc. · 501(c)(3) nonprofit · FDACS Reg. CH84123`,
    }),
  });
  if (!res.ok) throw new Error(`Resend ${res.status}`);
}

async function handleCourseSignup(request, env) {
  let body;
  try {
    body = await request.json();
  } catch {
    return jsonError("Invalid JSON", 400);
  }

  const { name, email, phone = "", schedule = "", group_type = "Individual", notes = "" } = body;

  if (!name || !String(name).trim()) return jsonError("Name required", 422);
  if (!email || !/^\S+@\S+\.\S+$/.test(email)) return jsonError("Valid email required", 422);
  if (!schedule) return jsonError("Schedule required", 422);

  try {
    await env.DB.prepare(
      `INSERT INTO course_signups (name, email, phone, schedule, group_type, notes, created_at)
       VALUES (?, ?, ?, ?, ?, ?, datetime('now'))`
    ).bind(
      String(name).trim().slice(0, 200),
      String(email).trim().toLowerCase().slice(0, 200),
      String(phone).trim().slice(0, 50),
      String(schedule).slice(0, 100),
      String(group_type).slice(0, 100),
      String(notes).trim().slice(0, 1000)
    ).run();
  } catch (err) {
    console.error("D1 insert failed:", err);
    return jsonError("Storage error", 500);
  }

  try {
    await sendCourseConfirmation(env, { name, email, schedule });
  } catch (err) {
    console.error("Resend failed:", err);
  }

  return new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: { "Content-Type": "application/json", ...CORS },
  });
}

async function sendCourseConfirmation(env, { name, email, schedule }) {
  const firstName = String(name).split(" ")[0];
  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.RESEND_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from: env.FROM_EMAIL,
      to: email,
      reply_to: env.FROM_EMAIL,
      subject: "You're registered — Technician License Course",
      html: `
<p>Hi ${firstName},</p>
<p>You're on the list for the Technician License Course (${schedule}). We'll email you as soon as the next cohort date is confirmed — usually a week or two out.</p>
<p>In the meantime, feel free to get a head start on HamStudy.org — it's free and covers exactly what we use in class.</p>
<p>Questions? Just reply to this email.</p>
<p>73,<br>Joe · W4GGJ<br>TavaOne Education</p>
<hr style="border:none;border-top:1px solid #ddd;margin:24px 0">
<p style="font-size:12px;color:#888;">
TavaOne Education Inc. · 501(c)(3) nonprofit · FDACS Reg. CH84123<br>
Held at Balance Gaming · 6701 49th St N, Pinellas Park, FL 33781<br>
You received this because you registered at tavaoneeducation.org/courses
</p>
      `.trim(),
      text: `Hi ${firstName},\n\nYou're on the list for the Technician License Course (${schedule}). We'll email you as soon as the next cohort date is confirmed — usually a week or two out.\n\nIn the meantime, feel free to get a head start on HamStudy.org — it's free and covers exactly what we use in class.\n\nQuestions? Just reply to this email.\n\n73,\nJoe · W4GGJ\nTavaOne Education\n\n---\nTavaOne Education Inc. · 501(c)(3) nonprofit · FDACS Reg. CH84123\nHeld at Balance Gaming · 6701 49th St N, Pinellas Park, FL 33781`,
    }),
  });
  if (!res.ok) throw new Error(`Resend ${res.status}`);
}

async function handleContact(request, env) {
  let body;
  try {
    body = await request.json();
  } catch {
    return jsonError("Invalid JSON", 400);
  }

  const { name, email, topic = "Other", message = "" } = body;

  if (!name || !String(name).trim()) return jsonError("Name required", 422);
  if (!email || !/^\S+@\S+\.\S+$/.test(email)) return jsonError("Valid email required", 422);
  if (!message || !String(message).trim()) return jsonError("Message required", 422);

  try {
    await env.DB.prepare(
      `INSERT INTO contact_messages (name, email, topic, message, created_at)
       VALUES (?, ?, ?, ?, datetime('now'))`
    ).bind(
      String(name).trim().slice(0, 200),
      String(email).trim().toLowerCase().slice(0, 200),
      String(topic).slice(0, 100),
      String(message).trim().slice(0, 5000)
    ).run();
  } catch (err) {
    console.error("D1 insert failed:", err);
    return jsonError("Storage error", 500);
  }

  try {
    await forwardContact(env, { name, email, topic, message });
  } catch (err) {
    console.error("Resend failed:", err);
  }

  return new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: { "Content-Type": "application/json", ...CORS },
  });
}

async function forwardContact(env, { name, email, topic, message }) {
  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.RESEND_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from: env.FROM_EMAIL,
      to: env.FROM_EMAIL,
      reply_to: email,
      subject: `[Contact] ${topic} — ${name}`,
      html: `<p><strong>From:</strong> ${name} &lt;${email}&gt;<br><strong>Topic:</strong> ${topic}</p><p>${String(message).replace(/\n/g, '<br>')}</p>`,
      text: `From: ${name} <${email}>\nTopic: ${topic}\n\n${message}`,
    }),
  });
  if (!res.ok) throw new Error(`Resend ${res.status}`);
}

function jsonError(message, status) {
  return new Response(JSON.stringify({ error: message }), {
    status,
    headers: { "Content-Type": "application/json", ...CORS },
  });
}
