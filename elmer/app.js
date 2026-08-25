/* ==========================================================================
   Elmer — Phase 1 static app.

   No backend, no API key, no network beyond fetching its own JSON. Everything
   it shows is read from site/elmer/data/*.json, which is generated from D1 by
   scripts/export-static.mjs and never hand-edited.

   Two rules shape this file:

   1. Nothing computes a regulatory number. Frequencies and power limits are
      rendered from the stored integers by dividing for display and nothing
      else — no rounding, no inference, no filling a gap with a plausible
      value. Where a dataset has not been built yet the panel says so and
      links out, rather than showing an empty result that reads like an answer.

   2. Nothing leaves the browser. Progress lives in localStorage; there is no
      analytics, no beacon, no account. Minors reach this through the karate
      programs and collecting nothing keeps COPPA out of scope entirely.
   ========================================================================== */

(function () {
  'use strict';

  var DATA = 'data/';
  var STORE = 'elmer.progress.v1';
  var cache = {};

  /* ── data loading ─────────────────────────────────────────────────────── */

  // meta.json is always revalidated; every other dataset is fetched with the
  // build stamp meta carries as a cache key.
  //
  // Without this, a data update never reaches anyone who has visited before.
  // The JSON files have stable names, so a browser or CDN that cached them
  // serves the old copy indefinitely — which for a page whose whole claim is
  // "these values come from a verified table" means quietly showing values
  // from a table that has since been corrected. One always-fresh file is
  // enough to version all the rest.
  var versionReady = fetch(DATA + 'meta.json', { cache: 'no-cache' })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (meta) {
      cache.meta = Promise.resolve(meta);
      return meta && meta._generated ? '?v=' + encodeURIComponent(meta._generated) : '';
    })
    .catch(function () { return ''; });

  // Datasets are fetched on first use, so opening the quiz does not pull the
  // park list. A missing file is an expected state, not an error: the table
  // behind it may simply not be seeded yet.
  function load(name) {
    if (cache[name]) return cache[name];
    cache[name] = versionReady.then(function (v) {
      return fetch(DATA + name + '.json' + v)
        .then(function (r) { return r.ok ? r.json() : null; })
        .catch(function () { return null; });
    });
    return cache[name];
  }

  function rowsOf(payload) {
    return payload && payload.rows ? payload.rows : [];
  }

  function el(id) { return document.getElementById(id); }

  /* ── figures ──────────────────────────────────────────────────────────── */

  // 44 questions across the three pools refer to a diagram, and a question that
  // says "in figure E5-1" is unanswerable without it. The Extra figures are
  // published as SVG and render inline. The Technician and General diagrams are
  // published only as PDF, so those link out to the file rather than being
  // converted — a redrawn diagram is a different diagram, and this is an exam.
  var FIGURE_PDF = {
    'T-1': 'technician-diagrams.pdf',
    'T-2': 'technician-diagrams.pdf',
    'T-3': 'technician-diagrams.pdf',
    'G7-1': 'G7-1.pdf',
  };

  function figureHtml(figure) {
    if (!figure) return '';
    if (FIGURE_PDF[figure]) {
      return '<p class="note"><a href="figures/' + esc(FIGURE_PDF[figure]) +
        '?v=1" target="_blank" rel="noopener">Open figure ' + esc(figure) +
        ' (PDF, published by NCVEC)</a></p>';
    }
    // Versioned like the site's own stylesheet. It also sidesteps a stale CDN
    // entry: probing a URL while GitHub Pages was still building cached the
    // 404, and a cached negative on an asset the page needs is indistinguishable
    // from a broken deploy. A version bump is a new URL and cannot inherit one.
    // No loading="lazy". Exactly one figure is on screen at a time and each is
    // a few kilobytes, so it buys nothing — and injecting a lazy image into the
    // panel left it permanently un-loaded: complete stayed false and the
    // element rendered at zero height while the file itself fetched fine.
    return '<div class="figure"><img src="figures/' + esc(figure) +
      '.svg?v=1" alt="Figure ' + esc(figure) + '" /></div>';
  }

  function esc(s) {
    return String(s === null || s === undefined ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function unavailable(what, link) {
    return '<div class="empty"><p>Elmer does not have ' + esc(what) +
      ' yet.</p>' + (link || '') + '</div>';
  }

  /* ── formatting ───────────────────────────────────────────────────────── */

  // Display only. The stored integer is the authority; this divides it and
  // trims trailing zeros so 14150000 Hz reads as 14.150 MHz.
  function fmtHz(hz) {
    if (hz >= 1e9) return trim(hz / 1e9, 6) + ' GHz';
    if (hz >= 1e6) return trim(hz / 1e6, 6) + ' MHz';
    return trim(hz / 1e3, 4) + ' kHz';
  }

  function fmtKhz(khz) {
    return khz >= 1000 ? trim(khz / 1000, 6) + ' MHz' : trim(khz, 3) + ' kHz';
  }

  function trim(n, places) {
    return String(parseFloat(n.toFixed(places)));
  }

  function fmtPower(mw, basis) {
    if (mw === null || mw === undefined) return '—';
    var w = mw / 1000;
    var shown = w >= 1000 ? trim(w / 1000, 3) + ' kW' : trim(w, 3) + ' W';
    return shown + (basis ? ' ' + basis : '');
  }

  /* ── progress ─────────────────────────────────────────────────────────── */

  function getProgress() {
    try { return JSON.parse(localStorage.getItem(STORE)) || {}; }
    catch (e) { return {}; }
  }

  function saveProgress(p) {
    try { localStorage.setItem(STORE, JSON.stringify(p)); } catch (e) { /* private mode */ }
  }

  function record(pool, id, correct) {
    var p = getProgress();
    p[pool] = p[pool] || {};
    var q = p[pool][id] || { seen: 0, right: 0 };
    q.seen += 1;
    if (correct) q.right += 1;
    p[pool][id] = q;
    saveProgress(p);
  }

  function renderStats() {
    var p = getProgress();
    var out = '';
    ['technician', 'general', 'extra'].forEach(function (pool) {
      var qs = p[pool] || {};
      var ids = Object.keys(qs);
      if (!ids.length) return;
      var seen = ids.length;
      var right = 0, attempts = 0;
      ids.forEach(function (id) { right += qs[id].right; attempts += qs[id].seen; });
      var pct = attempts ? Math.round((right / attempts) * 100) : 0;
      out += '<div><b>' + seen + '</b><span>' + pool + ' seen</span></div>' +
        '<div><b>' + pct + '%</b><span>' + pool + ' correct</span></div>';
    });
    el('quiz-stats-body').innerHTML = out ||
      '<span class="muted">Nothing answered yet. Your progress will appear here.</span>';
  }

  function weakIds(pool) {
    var qs = getProgress()[pool] || {};
    return Object.keys(qs).filter(function (id) {
      return qs[id].right < qs[id].seen;
    });
  }

  /* ── tabs ─────────────────────────────────────────────────────────────── */

  var initialised = {};

  el('tabs').addEventListener('click', function (e) {
    var btn = e.target.closest('button[data-panel]');
    if (!btn) return;
    show(btn.dataset.panel);
  });

  function show(name) {
    Array.prototype.forEach.call(document.querySelectorAll('.tabs button'), function (b) {
      b.setAttribute('aria-selected', String(b.dataset.panel === name));
    });
    Array.prototype.forEach.call(document.querySelectorAll('.panel'), function (p) {
      if (p.id === 'panel-' + name) p.setAttribute('data-active', '');
      else p.removeAttribute('data-active');
    });
    if (!initialised[name]) {
      initialised[name] = true;
      if (name === 'privileges') initPrivileges();
      if (name === 'bandplans') initBandPlans();
      if (name === 'parks') initParks();
      if (name === 'local') initLocal();
    }
  }

  /* ── practice quiz ────────────────────────────────────────────────────── */

  var quiz = { list: [], at: 0, pool: null, answered: false };

  function poolFile(name) { return 'pool-' + name; }

  el('quiz-pool').addEventListener('change', fillSubelements);

  function fillSubelements() {
    var pool = el('quiz-pool').value;
    load(poolFile(pool)).then(function (data) {
      var subs = {};
      rowsOf(data).forEach(function (q) { subs[q.subelement] = true; });
      var opts = '<option value="">All subelements</option>';
      Object.keys(subs).sort().forEach(function (s) {
        opts += '<option value="' + esc(s) + '">' + esc(s) + '</option>';
      });
      el('quiz-sub').innerHTML = opts;
    });
  }

  function startQuiz(onlyWeak) {
    var pool = el('quiz-pool').value;
    var sub = el('quiz-sub').value;
    load(poolFile(pool)).then(function (data) {
      var rows = rowsOf(data);
      if (!rows.length) {
        el('quiz-card').hidden = false;
        el('quiz-question').innerHTML = 'That pool has not been built yet.';
        return;
      }
      var list = rows.filter(function (q) { return !sub || q.subelement === sub; });
      if (onlyWeak) {
        var weak = weakIds(pool);
        var set = {};
        weak.forEach(function (id) { set[id] = true; });
        list = list.filter(function (q) { return set[q.id]; });
        if (!list.length) {
          el('quiz-hint').textContent =
            'No weak areas recorded yet for that pool — answer some questions first.';
          return;
        }
      }
      quiz = { list: shuffle(list), at: 0, pool: pool, answered: false };
      el('quiz-card').hidden = false;
      el('quiz-hint').textContent = 'Your progress is kept in this browser only.';
      renderQuestion();
    });
  }

  function shuffle(a) {
    var out = a.slice();
    for (var i = out.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1));
      var t = out[i]; out[i] = out[j]; out[j] = t;
    }
    return out;
  }

  function renderQuestion() {
    var q = quiz.list[quiz.at];
    if (!q) return finishQuiz();
    quiz.answered = false;
    el('quiz-id').textContent = q.id + (q.figure ? '  · figure ' + q.figure : '');
    el('quiz-count').textContent = (quiz.at + 1) + ' of ' + quiz.list.length;
    el('quiz-bar').style.width = ((quiz.at / quiz.list.length) * 100) + '%';
    el('quiz-question').textContent = q.question;
    el('quiz-figure').innerHTML = figureHtml(q.figure);
    el('quiz-feedback').textContent = '';
    el('quiz-next').hidden = true;

    var html = '';
    ['A', 'B', 'C', 'D'].forEach(function (L) {
      html += '<button data-letter="' + L + '"><span class="letter">' + L +
        '</span><span>' + esc(q['answer_' + L.toLowerCase()]) + '</span></button>';
    });
    el('quiz-answers').innerHTML = html;
  }

  el('quiz-answers').addEventListener('click', function (e) {
    var btn = e.target.closest('button[data-letter]');
    if (!btn || quiz.answered) return;
    quiz.answered = true;

    var q = quiz.list[quiz.at];
    var chosen = btn.dataset.letter;
    var right = chosen === q.correct_answer;

    Array.prototype.forEach.call(el('quiz-answers').children, function (b) {
      b.disabled = true;
      if (b.dataset.letter === q.correct_answer) b.classList.add('correct');
      else if (b.dataset.letter === chosen) b.classList.add('wrong');
    });

    record(quiz.pool, q.id, right);
    renderStats();

    // The explanation is hand-written curriculum content and is not written
    // yet for most questions. Where it is missing, say nothing rather than
    // generating filler.
    var msg = right ? 'Correct.' : 'The answer is ' + q.correct_answer + '.';
    if (q.explanation) msg += ' ' + q.explanation;
    else if (q.fcc_refs) msg += ' Rule reference: § ' + q.fcc_refs + '.';
    el('quiz-feedback').textContent = msg;
    el('quiz-next').hidden = false;
  });

  el('quiz-next').addEventListener('click', function () {
    quiz.at += 1;
    renderQuestion();
  });

  el('quiz-stop').addEventListener('click', finishQuiz);

  function finishQuiz() {
    el('quiz-card').hidden = true;
    renderStats();
  }

  el('quiz-start').addEventListener('click', function () { startQuiz(false); });
  el('quiz-weak').addEventListener('click', function () { startQuiz(true); });
  el('quiz-reset').addEventListener('click', function () {
    if (!confirm('Clear all recorded progress in this browser?')) return;
    saveProgress({});
    renderStats();
  });

  /* ── mock exam ────────────────────────────────────────────────────────── */

  var exam = { list: [], at: 0, answers: {}, pool: null };

  el('exam-start').addEventListener('click', function () {
    var pool = el('exam-pool').value;
    load(poolFile(pool)).then(function (data) {
      var rows = rowsOf(data);
      if (!rows.length) return;

      // A real exam takes one question from each group. Doing the same means
      // the length and coverage come from the pool itself rather than from a
      // number typed in here.
      var byGroup = {};
      rows.forEach(function (q) {
        (byGroup[q.group_code] = byGroup[q.group_code] || []).push(q);
      });
      var list = Object.keys(byGroup).sort().map(function (g) {
        var bucket = byGroup[g];
        return bucket[Math.floor(Math.random() * bucket.length)];
      });

      exam = { list: list, at: 0, answers: {}, pool: pool };
      el('exam-result').innerHTML = '';
      el('exam-card').hidden = false;
      renderExam();
    });
  });

  function renderExam() {
    var q = exam.list[exam.at];
    if (!q) return finishExam();
    el('exam-id').textContent = q.id;
    el('exam-count').textContent = (exam.at + 1) + ' of ' + exam.list.length;
    el('exam-bar').style.width = ((exam.at / exam.list.length) * 100) + '%';
    el('exam-question').textContent = q.question;
    el('exam-figure').innerHTML = figureHtml(q.figure);
    var html = '';
    ['A', 'B', 'C', 'D'].forEach(function (L) {
      html += '<button data-letter="' + L + '"><span class="letter">' + L +
        '</span><span>' + esc(q['answer_' + L.toLowerCase()]) + '</span></button>';
    });
    el('exam-answers').innerHTML = html;
  }

  el('exam-answers').addEventListener('click', function (e) {
    var btn = e.target.closest('button[data-letter]');
    if (!btn) return;
    exam.answers[exam.list[exam.at].id] = btn.dataset.letter;
    exam.at += 1;
    renderExam();
  });

  el('exam-abandon').addEventListener('click', function () {
    el('exam-card').hidden = true;
  });

  function finishExam() {
    el('exam-card').hidden = true;
    var right = 0;
    var missed = [];
    exam.list.forEach(function (q) {
      var given = exam.answers[q.id];
      if (given === q.correct_answer) { right += 1; record(exam.pool, q.id, true); }
      else { missed.push(q); record(exam.pool, q.id, false); }
    });

    var pct = Math.round((right / exam.list.length) * 100);
    var html = '<div class="card"><div class="kicker">Result</div>' +
      '<div class="stats"><div><b>' + right + ' / ' + exam.list.length +
      '</b><span>correct</span></div><div><b>' + pct + '%</b><span>score</span></div></div>' +
      // The pass mark is a number Elmer does not hold in a table, so it is not
      // stated. Saying "you passed" on a remembered threshold is exactly the
      // kind of confident guess this project refuses to make.
      '<p class="note">Elmer does not store the official pass mark, so it will not tell you ' +
      'whether this would have been a pass. Check with your VE team or the ARRL.</p></div>';

    if (missed.length) {
      html += '<div class="card"><div class="kicker">Questions you missed</div><div class="scroll"><table>' +
        '<tr><th>ID</th><th>Question</th><th>Correct</th></tr>';
      missed.forEach(function (q) {
        html += '<tr><td class="num">' + esc(q.id) + '</td><td>' + esc(q.question) +
          '</td><td class="num">' + esc(q.correct_answer) + '. ' +
          esc(q['answer_' + q.correct_answer.toLowerCase()]) + '</td></tr>';
      });
      html += '</table></div></div>';
    }
    el('exam-result').innerHTML = html;
    renderStats();
  }

  /* ── privileges ───────────────────────────────────────────────────────── */

  // Accepts "14.250", "14.250 MHz", "146.52", "7025 kHz". A bare number is
  // read as MHz unless it is large enough to only make sense as kHz or Hz.
  function parseFreq(text) {
    var s = String(text).trim().toLowerCase().replace(/,/g, '');
    if (!s) return null;
    var m = s.match(/^([\d.]+)\s*(ghz|mhz|khz|hz)?$/);
    if (!m) return null;
    var n = parseFloat(m[1]);
    if (isNaN(n)) return null;
    var unit = m[2];
    if (unit === 'ghz') return Math.round(n * 1e9);
    if (unit === 'mhz') return Math.round(n * 1e6);
    if (unit === 'khz') return Math.round(n * 1e3);
    if (unit === 'hz') return Math.round(n);
    if (n >= 1e6) return Math.round(n);          // already hertz
    if (n > 3000) return Math.round(n * 1e3);    // kilohertz
    return Math.round(n * 1e6);                  // megahertz
  }

  function initPrivileges() {
    el('priv-freq').addEventListener('input', runPrivilege);
    el('priv-class').addEventListener('change', runPrivilege);
    el('priv-browse').addEventListener('change', runBrowse);
  }

  function runPrivilege() {
    var hz = parseFreq(el('priv-freq').value);
    var cls = el('priv-class').value;
    if (!hz) {
      el('priv-parsed').textContent = '';
      el('priv-result').innerHTML = '';
      return;
    }
    el('priv-parsed').textContent = 'Reading that as ' + fmtHz(hz) + '.';

    load('privileges').then(function (data) {
      var rows = rowsOf(data).filter(function (r) {
        return hz >= r.freq_start_hz && hz <= r.freq_stop_hz && (!cls || r.class === cls);
      });

      if (!rows.length) {
        el('priv-result').innerHTML = '<div class="empty"><p>No US amateur privileges are ' +
          'recorded at ' + esc(fmtHz(hz)) + (cls ? ' for ' + esc(cls) : '') + '.</p>' +
          '<p class="muted">That may mean the frequency is outside the amateur bands, or ' +
          'outside what this table covers.</p></div>';
        return;
      }

      var html = '<div class="card"><div class="kicker">At ' + esc(fmtHz(hz)) + '</div><div class="scroll"><table>' +
        '<tr><th>Class</th><th>Band</th><th>Segment</th><th>Modes</th><th>Power</th><th>Citation</th></tr>';
      rows.forEach(function (r) {
        html += '<tr><td>' + esc(r.class) + '</td><td class="num">' + esc(r.band) + '</td>' +
          '<td class="num">' + esc(fmtHz(r.freq_start_hz)) + ' – ' + esc(fmtHz(r.freq_stop_hz)) +
          (r.channel_label ? '<br /><span class="cite">' + esc(r.channel_label) + '</span>' : '') + '</td>' +
          '<td>' + esc(r.modes) + '</td>' +
          '<td class="num">' + esc(fmtPower(r.max_power_mw, r.power_basis)) + '</td>' +
          '<td class="cite">§ ' + esc(r.cfr_cite) + '</td></tr>';
        if (r.notes) {
          html += '<tr><td></td><td colspan="5" class="note">' + esc(r.notes) + '</td></tr>';
        }
      });
      html += '</table></div><p class="note">Verified ' + esc(rows[0].verified_date) +
        ' against 47 CFR Part 97.</p></div>';
      el('priv-result').innerHTML = html;
    });
  }

  function runBrowse() {
    var cls = el('priv-browse').value;
    if (!cls) { el('priv-browse-result').innerHTML = ''; return; }
    load('privileges').then(function (data) {
      var rows = rowsOf(data).filter(function (r) { return r.class === cls; });
      var html = '<div class="card"><div class="kicker">' + esc(cls) + ' — every segment</div>' +
        '<div class="scroll"><table><tr><th>Band</th><th>Segment</th><th>Modes</th><th>Power</th><th>Citation</th></tr>';
      rows.forEach(function (r) {
        html += '<tr><td class="num">' + esc(r.band) + '</td><td class="num">' +
          esc(fmtHz(r.freq_start_hz)) + ' – ' + esc(fmtHz(r.freq_stop_hz)) + '</td><td>' +
          esc(r.modes) + '</td><td class="num">' + esc(fmtPower(r.max_power_mw, r.power_basis)) +
          '</td><td class="cite">§ ' + esc(r.cfr_cite) + '</td></tr>';
      });
      html += '</table></div></div>';
      el('priv-browse-result').innerHTML = html;
    });
  }

  /* ── band plans ───────────────────────────────────────────────────────── */

  var CLASS_ORDER = ['Technician', 'General', 'Extra'];
  var CLASS_SHORT = { Technician: 'T', General: 'G', Extra: 'E' };

  /**
   * The allocations chart: every band, every segment, and which licence classes
   * may use it.
   *
   * Built from `privileges`, which is transcribed from 47 CFR §§ 97.301, 97.305
   * and 97.313 — not from anybody's published band chart. Those charts are
   * copyrighted work; the underlying allocations are law.
   *
   * Segments identical in frequency, modes and power across classes are merged
   * into one row listing all of them, so 6 m 50.1-51.0 MHz reads as one line
   * for T/G/E rather than three near-identical ones. Where classes genuinely
   * differ — Extra from 14.000 MHz, General from 14.025 — they stay separate,
   * because that difference is the whole point of the chart.
   */
  function renderAllocations(rows) {
    var merged = {};
    var order = [];

    rows.forEach(function (r) {
      var key = [r.band, r.freq_start_hz, r.freq_stop_hz, r.modes,
        r.max_power_mw, r.power_basis, r.channel_label].join('|');
      if (!merged[key]) {
        merged[key] = { row: r, classes: [] };
        order.push(key);
      }
      if (merged[key].classes.indexOf(r.class) === -1) merged[key].classes.push(r.class);
    });

    var byBand = {};
    var bandOrder = [];
    order.forEach(function (key) {
      var m = merged[key];
      var band = m.row.band;
      if (!byBand[band]) { byBand[band] = []; bandOrder.push(band); }
      byBand[band].push(m);
    });

    // Ascending by frequency, which is how every band chart is read.
    bandOrder.sort(function (a, b) {
      return byBand[a][0].row.freq_start_hz - byBand[b][0].row.freq_start_hz;
    });

    var html = '';
    bandOrder.forEach(function (band) {
      var list = byBand[band].slice().sort(function (a, b) {
        return a.row.freq_start_hz - b.row.freq_start_hz;
      });

      html += '<div class="card"><div class="kicker">' + esc(band) + '</div>' +
        '<div class="scroll"><table><tr><th>Segment</th><th>Classes</th>' +
        '<th>Modes</th><th>Max power</th><th>Citation</th></tr>';

      list.forEach(function (m) {
        var r = m.row;
        var span = r.freq_start_hz === r.freq_stop_hz
          ? fmtHz(r.freq_start_hz)
          : fmtHz(r.freq_start_hz) + ' – ' + fmtHz(r.freq_stop_hz);

        var pills = CLASS_ORDER.map(function (c) {
          var has = m.classes.indexOf(c) !== -1;
          return '<span class="cls' + (has ? ' on' : '') + '" title="' + esc(c) + '">' +
            CLASS_SHORT[c] + '</span>';
        }).join('');

        html += '<tr><td class="num">' + esc(span) +
          (r.channel_label ? '<br /><span class="cite">' + esc(r.channel_label) + '</span>' : '') +
          '</td><td class="classes">' + pills + '</td><td>' + esc(r.modes) +
          '</td><td class="num">' + esc(fmtPower(r.max_power_mw, r.power_basis)) +
          '</td><td class="cite">§ ' + esc(r.cfr_cite) + '</td></tr>';
      });

      html += '</table></div></div>';
    });

    return html;
  }

  function initBandPlans() {
    load('privileges').then(function (data) {
      var rows = rowsOf(data);
      el('allocations-result').innerHTML = rows.length
        ? renderAllocations(rows)
        : unavailable('the allocations chart');
    });

    load('band-plans').then(function (data) {
      var rows = rowsOf(data);
      if (!rows.length) {
        el('bandplan-result').innerHTML = unavailable('band plan data');
        return;
      }
      var html = '<div class="card"><div class="scroll"><table>' +
        '<tr><th>Band</th><th>Frequency</th><th>Usage</th><th>Authority</th></tr>';
      rows.forEach(function (r) {
        html += '<tr><td class="num">' + esc(r.band) + '</td><td class="num">' +
          esc(fmtKhz(r.freq_khz)) + (r.freq_stop_khz ? ' – ' + esc(fmtKhz(r.freq_stop_khz)) : '') +
          '</td><td>' + esc(r.usage) + '</td><td><span class="pill conv">' +
          esc(r.authority) + '</span></td></tr>';
      });
      html += '</table></div>' +
        '<p class="note">Every row here is voluntary convention, not a rule. ' +
        'The allocations above are the law.</p></div>';
      el('bandplan-result').innerHTML = html;
    });
  }

  /* ── parks ────────────────────────────────────────────────────────────── */

  var parks = [];

  function initParks() {
    load('parks-fl').then(function (data) {
      parks = rowsOf(data);
      el('park-count').textContent = parks.length
        ? parks.length + ' Florida parks. National search needs the Worker, which is Phase 3.'
        : '';
      if (!parks.length) el('park-result').innerHTML = unavailable('the park list');
      el('park-q').addEventListener('input', runParks);
      runParks();
    });

    load('pota-rules').then(function (data) {
      var rows = rowsOf(data);
      if (!rows.length) {
        el('pota-rules').innerHTML = '<p class="muted">Program rules are not loaded. ' +
          '<a href="https://docs.pota.app/docs/rules.html" target="_blank" rel="noopener">' +
          'Read them at docs.pota.app</a>.</p>';
        return;
      }
      var html = '<dl style="margin:0">';
      rows.forEach(function (r) {
        html += '<dt class="mono" style="color:var(--accent);font-size:.78rem;margin-top:12px">' +
          esc(r.topic.replace(/_/g, ' ')) + '</dt><dd style="margin:4px 0 0">' +
          esc(r.rule_summary) + '</dd>';
      });
      html += '</dl><p class="note">Paraphrased. POTA rules are program policy and can change ' +
        'at any time — <a href="https://docs.pota.app/docs/rules.html" target="_blank" ' +
        'rel="noopener">the official rules</a> are what count.</p>';
      el('pota-rules').innerHTML = html;
    });
  }

  function runParks() {
    var q = el('park-q').value.trim().toLowerCase();
    var rows = !q ? parks.slice(0, 25) : parks.filter(function (p) {
      return (p.name && p.name.toLowerCase().indexOf(q) >= 0) ||
        (p.reference && p.reference.toLowerCase().indexOf(q) >= 0) ||
        (p.grid && p.grid.toLowerCase().indexOf(q) >= 0);
    }).slice(0, 60);

    if (!rows.length) {
      el('park-result').innerHTML = '<div class="empty">No Florida park matches that.</div>';
      return;
    }
    var html = '<div class="card"><div class="scroll"><table>' +
      '<tr><th>Reference</th><th>Name</th><th>Grid</th><th>Agency</th><th></th></tr>';
    rows.forEach(function (p) {
      html += '<tr><td class="num">' + esc(p.reference) + '</td><td>' + esc(p.name) +
        '</td><td class="num">' + esc(p.grid || '') + '</td><td class="muted">' +
        esc(p.managing_agency || '') + '</td><td>' +
        (p.guide_url ? '<a href="' + esc(p.guide_url) + '" target="_blank" rel="noopener">Guide</a>' : '') +
        '</td></tr>';
    });
    html += '</table></div>' + (!q ? '<p class="note">Showing the first 25. Type to search.</p>' : '') +
      '</div>';
    el('park-result').innerHTML = html;
  }

  /* ── local ────────────────────────────────────────────────────────────── */

  function initLocal() {
    load('clubs').then(function (data) {
      var rows = rowsOf(data);
      if (!rows.length) { el('clubs-result').innerHTML = unavailable('club listings'); return; }
      var html = '<div class="scroll"><table><tr><th>Club</th><th>Where</th><th>Meets</th></tr>';
      rows.forEach(function (c) {
        html += '<tr><td>' + (c.website
          ? '<a href="' + esc(c.website) + '" target="_blank" rel="noopener">' + esc(c.name) + '</a>'
          : esc(c.name)) +
          (c.notes ? '<div class="note">' + esc(c.notes) + '</div>' : '') +
          '</td><td class="muted">' + esc(c.city || '') +
          (c.county ? ', ' + esc(c.county) : '') + '</td><td class="muted">' +
          esc(c.meets || '') + '</td></tr>';
      });
      html += '</table></div>';
      el('clubs-result').innerHTML = html;
    });

    load('external-links').then(function (data) {
      var rows = rowsOf(data);
      if (!rows.length) {
        el('links-result').innerHTML = '<p class="muted">Repeater and exam session links ' +
          'are not loaded yet.</p>';
        return;
      }
      var html = '<ul style="margin:0;padding-left:18px">';
      rows.forEach(function (l) {
        html += '<li style="margin-bottom:10px"><a href="' + esc(l.url) + '" target="_blank" ' +
          'rel="noopener">' + esc(l.label) + '</a>' +
          (l.scope ? ' <span class="pill">' + esc(l.scope) + '</span>' : '') +
          (l.note ? '<div class="note">' + esc(l.note) + '</div>' : '') + '</li>';
      });
      html += '</ul>';
      el('links-result').innerHTML = html;
    });
  }

  /* ── verified dates banner ────────────────────────────────────────────── */

  load('meta').then(function (meta) {
    if (!meta) { el('verified-dates').textContent = ''; return; }
    var bits = [];
    (meta.pools || []).forEach(function (p) {
      bits.push(p.class + ' pool ' + p.pool_version + ' verified ' + p.verified_date);
    });
    (meta.cfr || []).forEach(function (c) {
      bits.push((c.label || ('Part ' + c.part)) + ' retrieved ' + c.retrieved);
    });
    (meta.freshness || []).forEach(function (f) {
      if (f.table_name === 'privileges') bits.push('Privileges verified ' + f.newest);
      if (f.table_name === 'band_plans') bits.push('Band plans verified ' + f.newest);
      if (f.table_name === 'pota_rules') bits.push('POTA rules verified ' + f.newest);
    });
    el('verified-dates').textContent = bits.join(' · ');
  });

  /* ── go ───────────────────────────────────────────────────────────────── */

  fillSubelements();
  renderStats();
})();
