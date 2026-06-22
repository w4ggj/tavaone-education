#!/usr/bin/env python3
"""
fcc_ham_stats.py - Generate U.S. amateur-radio license statistics and a
                   publishable web page from the FCC ULS public database.

Source: https://data.fcc.gov/download/pub/uls/complete/l_amat.zip
The zip holds pipe-delimited .dat files. We use three, joined on the
Unique System Identifier (UI) - the stable key (call signs can change):
  HD.dat  license header  -> status + dates (who is ACTIVE & unexpired)
  EN.dat  entity          -> name, state, zip, FRN
  AM.dat  amateur record  -> operator class, vanity flag

Outputs (to --out, default ./out):
  *.csv                 one table per statistic (spreadsheet-friendly)
  ham_stats_data.json   all tables as one JSON object
  ham_stats.html        self-contained web page (Chart.js via CDN)
  charts/*.png          static charts (only if matplotlib is installed)
  history.csv           one snapshot row appended per run (builds the trend)

Usage:
  python3 fcc_ham_stats.py                    # download fresh -> ./out
  python3 fcc_ham_stats.py --zip l_amat.zip   # reuse a downloaded zip
  python3 fcc_ham_stats.py --keep             # keep the downloaded zip
  python3 fcc_ham_stats.py --top-names 100 --top-states 56

Optional gender table: drop names_gender.csv (header "name,gender",
lowercase first names) beside this script and the gender step turns on.

Python 3.8+. No third-party packages required for data/JSON/HTML;
matplotlib is used only for the optional static PNG charts.
"""
import argparse, csv, io, os, sys, json, zipfile, urllib.request, datetime
from collections import Counter

FCC_URL = "https://data.fcc.gov/download/pub/uls/complete/l_amat.zip"

# ---- ULS PUBACC column indices (0-based), verified against the layouts ----
HD_UI, HD_CALL, HD_STATUS, HD_SERVICE, HD_GRANT, HD_EXPIRED = 1, 4, 5, 6, 7, 8
EN_UI, EN_CALL, EN_NAME, EN_FIRST, EN_LAST, EN_STATE, EN_ZIP, EN_FRN = 1, 4, 7, 8, 10, 17, 18, 22
AM_UI, AM_CALL, AM_CLASS, AM_VANITY = 1, 4, 5, 13

# License ladder, entry -> advanced (order is meaningful: it's the progression)
CLASS_ORDER = ["N", "T", "P", "G", "A", "E"]
CLASS_LABELS = {
    "N": "Novice", "T": "Technician", "P": "Technician Plus",
    "G": "General", "A": "Advanced", "E": "Amateur Extra",
    "?": "Club / other",
}

def log(*a, **k): print(*a, file=sys.stderr, flush=True, **k)

# --------------------------------------------------------------------------- #
# Download + parse
# --------------------------------------------------------------------------- #
def download(url, dest):
    log(f"Downloading {url} ...")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=600) as r, open(dest, "wb") as f:
        total = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk: break
            f.write(chunk); total += len(chunk)
            log(f"  {total/1e6:6.1f} MB", end="\r")
    log(f"\nSaved {dest} ({os.path.getsize(dest)/1e6:.1f} MB)")

def read_dat(zf, member):
    with zf.open(member) as raw:
        text = io.TextIOWrapper(raw, encoding="latin-1", newline="")
        for line in text:
            line = line.rstrip("\r\n")
            if line:
                yield line.split("|")

def parse_date(s):
    s = s.strip()
    if not s: return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try: return datetime.datetime.strptime(s, fmt).date()
        except ValueError: pass
    return None

def build(zip_path):
    today = datetime.date.today()
    zf = zipfile.ZipFile(zip_path)
    members = {n.upper(): n for n in zf.namelist()}
    for need in ("HD.DAT", "EN.DAT", "AM.DAT"):
        if need not in members:
            sys.exit(f"ERROR: {need} not in {zip_path}. Members: {zf.namelist()}")

    active = {}
    hd_seen = 0
    for row in read_dat(zf, members["HD.DAT"]):
        if len(row) <= HD_EXPIRED: continue
        hd_seen += 1
        if row[HD_STATUS].strip() != "A": continue
        exp = parse_date(row[HD_EXPIRED])
        if exp is None or exp < today: continue
        active[row[HD_UI].strip()] = {"call": row[HD_CALL].strip(), "expired": exp}
    log(f"HD read: {hd_seen:,} | active & unexpired: {len(active):,}")

    for row in read_dat(zf, members["AM.DAT"]):
        if len(row) <= AM_CLASS: continue
        rec = active.get(row[AM_UI].strip())
        if rec is None: continue
        rec["class"] = row[AM_CLASS].strip().upper()
        rec["vanity"] = (len(row) > AM_VANITY and row[AM_VANITY].strip().upper() == "Y")

    for row in read_dat(zf, members["EN.DAT"]):
        if len(row) <= EN_STATE: continue
        rec = active.get(row[EN_UI].strip())
        if rec is None: continue
        rec["first"] = row[EN_FIRST].strip()
        rec["state"] = row[EN_STATE].strip().upper()
    return list(active.values()), today

# --------------------------------------------------------------------------- #
# Compute the stats object
# --------------------------------------------------------------------------- #
def compute(records, today, top_names, top_states):
    n = len(records)
    pct = lambda c, d=n: round(100 * c / d, 3) if d else 0.0

    cls = Counter(r.get("class", "") or "?" for r in records)
    classes = [{"code": c, "label": CLASS_LABELS.get(c, c),
                "count": cls[c], "pct": pct(cls[c])}
               for c in CLASS_ORDER if c in cls]
    classes += [{"code": c, "label": CLASS_LABELS.get(c, c),
                 "count": cls[c], "pct": pct(cls[c])}
                for c in cls if c not in CLASS_ORDER]

    st = Counter(r["state"] for r in records if r.get("state"))
    states_all = [{"state": s, "count": c, "pct": pct(c)} for s, c in st.most_common()]

    nm = Counter(r["first"].upper() for r in records if r.get("first"))
    names = [{"name": x, "count": c, "pct": pct(c)} for x, c in nm.most_common(top_names)]

    letters = Counter(r["call"][0].upper() for r in records if r.get("call"))
    lt_tot = sum(letters.values()) or 1
    akn = sum(letters.get(L, 0) for L in "AKNW")
    letter_rows = [{"letter": L, "count": letters.get(L, 0),
                    "pct": round(100*letters.get(L,0)/lt_tot, 3)} for L in "AKNW"]
    letter_rows.append({"letter": "other", "count": lt_tot-akn,
                        "pct": round(100*(lt_tot-akn)/lt_tot, 3)})

    vanity = sum(1 for r in records if r.get("vanity"))
    vanity_obj = {"vanity": vanity, "general": n-vanity, "vanity_pct": pct(vanity)}

    exp = Counter(r["expired"].year for r in records if r.get("expired"))
    expirations = [{"year": y, "count": exp[y]} for y in sorted(exp)]

    gender = None
    gpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "names_gender.csv")
    if os.path.exists(gpath):
        gmap = {}
        with open(gpath, newline="") as f:
            for row in csv.DictReader(f):
                gmap[row["name"].strip().lower()] = row["gender"].strip().upper()[:1]
        g = Counter(gmap.get(r.get("first","").lower(), "U") for r in records)
        gender = [{"gender": k, "count": g[k], "pct": pct(g[k])} for k in ("M","F","U")]

    return {
        "snapshot_date": today.isoformat(),
        "total": n,
        "states_represented": len(states_all),
        "top_name": names[0]["name"].title() if names else "-",
        "top_state": states_all[0]["state"] if states_all else "-",
        "classes": classes,
        "states": states_all[:top_states],
        "states_full": states_all,
        "names": names,
        "letters": letter_rows,
        "vanity": vanity_obj,
        "expirations": expirations,
        "gender": gender,
    }

# --------------------------------------------------------------------------- #
# Writers
# --------------------------------------------------------------------------- #
def write_csvs(s, out_dir):
    def w(name, header, rows):
        with open(os.path.join(out_dir, name), "w", newline="") as f:
            wr = csv.writer(f); wr.writerow(header); wr.writerows(rows)
    w("class_distribution.csv", ["code","class","count","pct"],
      [[c["code"],c["label"],c["count"],c["pct"]] for c in s["classes"]])
    w("state_distribution.csv", ["state","count","pct"],
      [[x["state"],x["count"],x["pct"]] for x in s["states_full"]])
    w("first_names.csv", ["first_name","count","pct"],
      [[x["name"],x["count"],x["pct"]] for x in s["names"]])
    w("callsign_first_letter.csv", ["letter","count","pct"],
      [[x["letter"],x["count"],x["pct"]] for x in s["letters"]])
    w("vanity_vs_general.csv", ["type","count","pct"],
      [["vanity",s["vanity"]["vanity"],s["vanity"]["vanity_pct"]],
       ["general_issue",s["vanity"]["general"],round(100-s["vanity"]["vanity_pct"],3)]])
    w("expirations_by_year.csv", ["year","count"],
      [[x["year"],x["count"]] for x in s["expirations"]])
    if s["gender"]:
        w("gender_estimate.csv", ["gender","count","pct"],
          [[x["gender"],x["count"],x["pct"]] for x in s["gender"]])

def write_json(s, out_dir):
    with open(os.path.join(out_dir, "ham_stats_data.json"), "w") as f:
        json.dump(s, f, indent=2)

def update_history(s, out_dir):
    hist = os.path.join(out_dir, "history.csv")
    new = not os.path.exists(hist)
    cls = {c["code"]: c["count"] for c in s["classes"]}
    with open(hist, "a", newline="") as f:
        wr = csv.writer(f)
        if new:
            wr.writerow(["snapshot_date","total"] + [CLASS_LABELS[c] for c in CLASS_ORDER])
        wr.writerow([s["snapshot_date"], s["total"]] + [cls.get(c,0) for c in CLASS_ORDER])
    rows = []
    with open(hist, newline="") as f:
        for r in csv.DictReader(f):
            rows.append({"date": r["snapshot_date"], "total": int(r["total"])})
    s["history"] = rows
    return rows

# ---- PNG charts (optional) ----
GREEN = "#10b981"; GREEN_L = "#34d399"; MUTED = "#94a3b8"; BG = "#0f172a"; CARD = "#1e293b"
TEXT = "#e2e8f0"; RED = "#ef4444"; GRID = "#334155"
CLASS_COLORS = {"N":"#64748b","T":"#34d399","P":"#5eead4","G":"#10b981","A":"#059669","E":"#047857"}

def write_pngs(s, out_dir):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        log("  (skip PNGs: matplotlib not installed)")
        return
    cdir = os.path.join(out_dir, "charts"); os.makedirs(cdir, exist_ok=True)
    def style(ax, fig):
        fig.patch.set_facecolor(BG); ax.set_facecolor(BG)
        for sp in ax.spines.values(): sp.set_color(GRID)
        ax.tick_params(colors=TEXT); ax.yaxis.label.set_color(TEXT); ax.xaxis.label.set_color(TEXT)
        ax.title.set_color(TEXT); ax.grid(axis="y", color=GRID, alpha=.4)
    def save(fig, name):
        fig.tight_layout(); fig.savefig(os.path.join(cdir,name), dpi=150, facecolor=BG); plt.close(fig)

    c = s["classes"]
    fig, ax = plt.subplots(figsize=(7,4))
    ax.barh([x["label"] for x in c][::-1], [x["count"] for x in c][::-1],
            color=[CLASS_COLORS.get(x["code"],GREEN) for x in c][::-1])
    ax.set_title("Active licenses by class"); style(ax, fig); save(fig,"class.png")

    top = s["states"][:15]
    fig, ax = plt.subplots(figsize=(7,4))
    ax.bar([x["state"] for x in top], [x["count"] for x in top], color=GREEN)
    ax.set_title("Top states by active operators"); style(ax, fig); save(fig,"states.png")

    L = s["letters"][:4]
    fig, ax = plt.subplots(figsize=(5,4))
    ax.bar([x["letter"] for x in L], [x["count"] for x in L],
           color=[GREEN_L,GREEN,"#059669","#047857"])
    ax.set_title("Call signs by first letter"); style(ax, fig); save(fig,"letters.png")

    e = s["expirations"]
    cur = datetime.date.today().year
    fig, ax = plt.subplots(figsize=(7,4))
    ax.bar([str(x["year"]) for x in e], [x["count"] for x in e],
           color=[RED if x["year"]==cur else GREEN for x in e])
    ax.set_title("Expirations by year"); style(ax, fig); save(fig,"expirations.png")

    if s.get("history") and len(s["history"]) > 1:
        h = s["history"]
        fig, ax = plt.subplots(figsize=(7,4))
        ax.plot([x["date"] for x in h], [x["total"] for x in h], color=GREEN, marker="o")
        ax.set_title("Total active operators over time"); style(ax, fig)
        plt.xticks(rotation=45, ha="right"); save(fig,"history.png")
    log(f"  wrote PNG charts -> {cdir}/")

# ---- Self-contained web page ----
def write_html(s, out_dir):
    data = json.dumps(s)
    html = HTML_TEMPLATE.replace("/*__DATA__*/", data)
    path = os.path.join(out_dir, "ham_stats.html")
    with open(path, "w") as f:
        f.write(html)
    log(f"  wrote {path}")

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>U.S. Amateur Radio License Census &middot; TavaOne Education</title>
<meta name="description" content="A living census of U.S. amateur radio licenses, built from the FCC ULS public database."/>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;800&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.min.js"></script>
<style>
  :root{
    --bg:#0f172a; --bg2:#0b1120; --card:#1e293b; --border:#334155;
    --green:#10b981; --green-l:#34d399; --green-d:#065f46;
    --text:#e2e8f0; --muted:#94a3b8; --light:#f8fafc; --red:#ef4444;
    --sans:'Plus Jakarta Sans',system-ui,sans-serif; --mono:'JetBrains Mono',monospace;
  }
  *{box-sizing:border-box}
  html,body{margin:0}
  body{background:var(--bg); color:var(--text); font-family:var(--sans); line-height:1.55; -webkit-font-smoothing:antialiased;}
  .wrap{max-width:1080px; margin:0 auto; padding:0 24px}
  .eyebrow{font-family:var(--mono); font-size:12px; letter-spacing:.18em; text-transform:uppercase; color:var(--green-l)}

  /* hero */
  .hero{position:relative; padding:88px 0 56px; border-bottom:1px solid var(--border);
        background:radial-gradient(120% 80% at 50% -10%, rgba(16,185,129,.10), transparent 60%), var(--bg2);}
  .live{display:inline-flex; align-items:center; gap:8px; margin-bottom:22px}
  .dot{width:8px; height:8px; border-radius:50%; background:var(--green); box-shadow:0 0 0 0 rgba(16,185,129,.6); animation:pulse 2.4s infinite}
  @keyframes pulse{0%{box-shadow:0 0 0 0 rgba(16,185,129,.5)}70%{box-shadow:0 0 0 9px rgba(16,185,129,0)}100%{box-shadow:0 0 0 0 rgba(16,185,129,0)}}
  .total{font-family:var(--mono); font-weight:700; font-size:clamp(56px,13vw,150px); line-height:.95;
         color:var(--light); text-shadow:0 0 32px rgba(16,185,129,.28); letter-spacing:-.02em; margin:6px 0 4px}
  .total-label{font-size:clamp(15px,2.4vw,20px); color:var(--muted); max-width:46ch}
  .total-label b{color:var(--green-l); font-weight:600}

  .microbar{display:grid; grid-template-columns:repeat(3,1fr); gap:16px; margin-top:40px}
  .micro{background:var(--card); border:1px solid var(--border); border-radius:12px; padding:18px}
  .micro .v{font-family:var(--mono); font-size:26px; font-weight:700; color:var(--light)}
  .micro .k{font-size:12px; color:var(--muted); margin-top:4px}

  /* sections */
  section{padding:64px 0; border-bottom:1px solid var(--border)}
  .sec-head{display:flex; align-items:baseline; gap:14px; margin-bottom:6px}
  h2{font-size:clamp(22px,3.4vw,30px); font-weight:800; margin:0; color:var(--light); letter-spacing:-.01em}
  .sec-note{color:var(--muted); font-size:15px; margin:8px 0 30px; max-width:64ch}

  .grid2{display:grid; grid-template-columns:1.15fr .85fr; gap:28px; align-items:start}
  .panel{background:var(--card); border:1px solid var(--border); border-radius:14px; padding:22px}
  .chart-box{position:relative; height:300px}

  /* class ladder */
  .ladder{display:flex; flex-direction:column; gap:10px}
  .rung{display:grid; grid-template-columns:128px 1fr 92px; align-items:center; gap:14px}
  .rung .name{font-size:14px; color:var(--text)}
  .rung .track{height:26px; background:var(--bg2); border:1px solid var(--border); border-radius:6px; overflow:hidden}
  .rung .fill{height:100%; border-radius:5px 0 0 5px; transition:width 1.1s cubic-bezier(.2,.8,.2,1)}
  .rung .val{font-family:var(--mono); font-size:14px; text-align:right; color:var(--muted)}
  .rung .val b{color:var(--light)}

  table{width:100%; border-collapse:collapse; font-size:14px}
  th,td{text-align:left; padding:9px 10px; border-bottom:1px solid var(--border)}
  th{font-family:var(--mono); font-size:11px; letter-spacing:.1em; text-transform:uppercase; color:var(--muted); font-weight:700}
  td.num{font-family:var(--mono); text-align:right; color:var(--light)}
  tbody tr:hover{background:rgba(16,185,129,.06)}

  footer{padding:48px 0 72px; color:var(--muted); font-size:13px}
  footer .src{font-family:var(--mono); font-size:12px; line-height:1.9}
  footer a{color:var(--green-l); text-decoration:none}
  footer a:hover{text-decoration:underline}
  .tag{font-family:var(--mono); color:var(--green-l); letter-spacing:.12em; text-transform:uppercase; font-size:12px}

  @media(max-width:760px){
    .microbar{grid-template-columns:repeat(2,1fr)}
    .grid2{grid-template-columns:1fr}
    .rung{grid-template-columns:96px 1fr 78px}
  }
  @media(prefers-reduced-motion:reduce){
    .dot{animation:none}
    .rung .fill{transition:none}
  }
</style>
</head>
<body>
<script>const DATA = /*__DATA__*/;</script>

<header class="hero">
  <div class="wrap">
    <div class="live"><span class="dot"></span><span class="eyebrow" id="eyebrow"></span></div>
    <div class="total" id="total">0</div>
    <div class="total-label">active <b>U.S. amateur radio operators</b> on the FCC roster &mdash; licensed, unexpired, ready to get on the air.</div>
    <div class="microbar" id="microbar"></div>
  </div>
</header>

<main class="wrap">

  <section>
    <div class="sec-head"><span class="eyebrow">01</span><h2>The licensing ladder</h2></div>
    <p class="sec-note">Every operator starts at Technician and can climb to General, then Amateur Extra &mdash; each step unlocking more bands and privileges. Here's where today's operators sit.</p>
    <div class="grid2">
      <div class="panel"><div class="ladder" id="ladder"></div></div>
      <div class="panel"><div class="chart-box"><canvas id="classChart"></canvas></div></div>
    </div>
  </section>

  <section>
    <div class="sec-head"><span class="eyebrow">02</span><h2>Where operators are</h2></div>
    <p class="sec-note">Active licenses by state of record. <span id="stateSummary"></span></p>
    <div class="grid2">
      <div class="panel"><div class="chart-box" style="height:360px"><canvas id="stateChart"></canvas></div></div>
      <div class="panel" style="max-height:404px; overflow:auto"><table id="stateTable"></table></div>
    </div>
  </section>

  <section>
    <div class="sec-head"><span class="eyebrow">03</span><h2>Call sign anatomy</h2></div>
    <p class="sec-note">U.S. call signs begin with A, K, N, or W. Operators can also apply for a personalized &ldquo;vanity&rdquo; call instead of taking the sequentially issued one.</p>
    <div class="panel"><div class="chart-box"><canvas id="letterChart"></canvas></div></div>
  </section>

  <section>
    <div class="sec-head"><span class="eyebrow">04</span><h2>Renewals on the horizon</h2></div>
    <p class="sec-note">Licenses run 10 years. This is when the current roster comes up for renewal &mdash; the current year is flagged in red.</p>
    <div class="panel"><div class="chart-box" style="height:320px"><canvas id="expChart"></canvas></div></div>
  </section>

  <section id="trendSec">
    <div class="sec-head"><span class="eyebrow">05</span><h2>The roster over time</h2></div>
    <p class="sec-note" id="trendNote"></p>
    <div class="panel"><div class="chart-box" style="height:320px"><canvas id="trendChart"></canvas></div></div>
  </section>

  <section style="border-bottom:none">
    <div class="sec-head"><span class="eyebrow">06</span><h2>Most common first names</h2></div>
    <p class="sec-note">The first names on the active roster, most common first.</p>
    <div class="panel" style="max-height:420px; overflow:auto"><table id="nameTable"></table></div>
  </section>

</main>

<footer class="wrap">
  <div class="tag">TavaOne Education</div>
  <p style="max-width:62ch; margin:10px 0 18px">A public-interest snapshot of the amateur radio service, maintained to support STEM and licensing education.</p>
  <div class="src">
    Source: FCC Universal Licensing System (ULS), <a href="https://data.fcc.gov/download/pub/uls/complete/l_amat.zip">l_amat complete database</a><br>
    Method: active status &ldquo;A&rdquo; with an expiration date after the snapshot date; records joined on Unique System Identifier.<br>
    Snapshot: <span id="footDate"></span> &middot; figures reflect that day's FCC file.
  </div>
</footer>

<script>
(function(){
  const D = DATA;
  const num = n => n.toLocaleString('en-US');
  const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const GREEN=css('--green'), GREEN_L=css('--green-l'), MUTED=css('--muted'),
        BORDER=css('--border'), TEXT=css('--text'), RED=css('--red'), CARD=css('--card');
  const CLASS_COLORS={N:'#64748b',T:'#34d399',P:'#5eead4',G:'#10b981',A:'#059669',E:'#047857'};
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  document.getElementById('eyebrow').textContent = 'FCC ULS \u00B7 LIVE LICENSE CENSUS';
  document.getElementById('footDate').textContent = D.snapshot_date;

  // hero count-up
  const tEl = document.getElementById('total');
  if(reduce){ tEl.textContent = num(D.total); }
  else{
    const dur=1100, t0=performance.now();
    (function step(now){
      const p=Math.min(1,(now-t0)/dur), e=1-Math.pow(1-p,3);
      tEl.textContent = num(Math.round(D.total*e));
      if(p<1) requestAnimationFrame(step);
    })(t0);
  }

  // microstats
  const micro=[
    ['Operators', num(D.total)],

    ['States & territories', num(D.states_represented)],
    ['Most common name', D.top_name],
  ];
  document.getElementById('microbar').innerHTML = micro.map(m=>
    `<div class="micro"><div class="v">${m[1]}</div><div class="k">${m[0]}</div></div>`).join('');

  // ladder
  const maxC = Math.max(...D.classes.map(c=>c.count));
  document.getElementById('ladder').innerHTML = D.classes.map(c=>
    `<div class="rung"><div class="name">${c.label}</div>
       <div class="track"><div class="fill" data-w="${(c.count/maxC*100).toFixed(1)}"
            style="width:0;background:${CLASS_COLORS[c.code]||GREEN}"></div></div>
       <div class="val"><b>${num(c.count)}</b> &middot; ${c.pct.toFixed(1)}%</div></div>`).join('');
  requestAnimationFrame(()=>document.querySelectorAll('.fill').forEach(f=>{
    f.style.width = reduce ? f.dataset.w+'%' : f.dataset.w+'%';}));

  // chart.js defaults
  Chart.defaults.color = MUTED; Chart.defaults.borderColor = BORDER;
  Chart.defaults.font.family = "'JetBrains Mono', monospace";
  const noLegend={plugins:{legend:{display:false}}};
  const grid={grid:{color:BORDER}, ticks:{color:MUTED}};

  new Chart(classChart,{type:'doughnut',
    data:{labels:D.classes.map(c=>c.label),
      datasets:[{data:D.classes.map(c=>c.count),
        backgroundColor:D.classes.map(c=>CLASS_COLORS[c.code]||GREEN), borderColor:CARD, borderWidth:2}]},
    options:{cutout:'62%', plugins:{legend:{position:'bottom',labels:{boxWidth:12,padding:12}}}}});

  new Chart(stateChart,{type:'bar',
    data:{labels:D.states.map(s=>s.state),
      datasets:[{data:D.states.map(s=>s.count), backgroundColor:GREEN}]},
    options:{...noLegend, scales:{x:grid,y:grid}}});
  document.getElementById('stateSummary').textContent =
    `${D.top_state} leads; ${D.states.length} shown.`;
  document.getElementById('stateTable').innerHTML =
    '<thead><tr><th>State</th><th style="text-align:right">Operators</th><th style="text-align:right">%</th></tr></thead><tbody>'+
    D.states_full.map(s=>`<tr><td>${s.state}</td><td class="num">${num(s.count)}</td><td class="num">${s.pct.toFixed(2)}</td></tr>`).join('')+'</tbody>';

  const L=D.letters.slice(0,4);
  new Chart(letterChart,{type:'bar',
    data:{labels:L.map(x=>x.letter),
      datasets:[{data:L.map(x=>x.count), backgroundColor:['#34d399','#10b981','#059669','#047857']}]},
    options:{...noLegend, scales:{x:grid,y:grid}}});

  const cur=new Date().getFullYear();
  new Chart(expChart,{type:'bar',
    data:{labels:D.expirations.map(e=>e.year),
      datasets:[{data:D.expirations.map(e=>e.count),
        backgroundColor:D.expirations.map(e=>e.year===cur?RED:GREEN)}]},
    options:{...noLegend, scales:{x:grid,y:grid}}});

  // trend
  const h=D.history||[];
  const tn=document.getElementById('trendNote');
  if(h.length>1){
    tn.textContent='Total active operators at each snapshot. Run the generator on a schedule to extend this line.';
    new Chart(trendChart,{type:'line',
      data:{labels:h.map(x=>x.date),
        datasets:[{data:h.map(x=>x.total), borderColor:GREEN, backgroundColor:'rgba(16,185,129,.12)',
          fill:true, tension:.25, pointBackgroundColor:GREEN_L}]},
      options:{...noLegend, scales:{x:grid,y:grid}}});
  } else {
    tn.textContent='Only one snapshot so far. Re-run the generator periodically (a weekly cron works well) and this chart fills in over time.';
    document.getElementById('trendChart').parentElement.parentElement.style.opacity=.5;
  }

  document.getElementById('nameTable').innerHTML =
    '<thead><tr><th>Rank</th><th>First name</th><th style="text-align:right">Count</th><th style="text-align:right">%</th></tr></thead><tbody>'+
    D.names.map((x,i)=>`<tr><td class="num" style="color:var(--muted)">${i+1}</td><td>${x.name.charAt(0)+x.name.slice(1).toLowerCase()}</td><td class="num">${num(x.count)}</td><td class="num">${x.pct.toFixed(3)}</td></tr>`).join('')+'</tbody>';
})();
</script>
</body>
</html>
"""

# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="FCC ULS amateur-radio statistics + web page")
    ap.add_argument("--zip", help="path to an already-downloaded l_amat.zip")
    ap.add_argument("--out", default="out", help="output directory (default: ./out)")
    ap.add_argument("--top-names", type=int, default=100)
    ap.add_argument("--top-states", type=int, default=56)
    ap.add_argument("--keep", action="store_true", help="keep the downloaded zip")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    zip_path, tmp = args.zip, False
    if not zip_path:
        zip_path = "l_amat.zip"; download(FCC_URL, zip_path); tmp = not args.keep

    records, today = build(zip_path)
    s = compute(records, today, args.top_names, args.top_states)
    update_history(s, args.out)     # sets s["history"]
    write_csvs(s, args.out)
    write_json(s, args.out)
    write_pngs(s, args.out)
    write_html(s, args.out)

    print(f"\n=== U.S. Amateur Radio snapshot {s['snapshot_date']} ===")
    print(f"Total active, unexpired: {s['total']:,}")
    for c in s["classes"]:
        print(f"  {c['label']:<16} {c['count']:>10,}  {c['pct']:5.2f}%")
    print(f"Vanity: {s['vanity']['vanity']:,} ({s['vanity']['vanity_pct']:.2f}%)")
    print(f"Outputs in: {os.path.abspath(args.out)}/  (open ham_stats.html)")

    if tmp:
        try: os.remove(zip_path)
        except OSError: pass

if __name__ == "__main__":
    main()
