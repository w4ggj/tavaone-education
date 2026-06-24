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
import argparse, csv, io, os, re, sys, json, zipfile, urllib.request, datetime
from collections import Counter

FCC_URL = "https://data.fcc.gov/download/pub/uls/complete/l_amat.zip"

# data.fcc.gov is behind Akamai, which stalls large-file GETs from non-browser
# clients. A full browser-like header set (real UA + Accept-Language + Referer)
# gets the body served. Used by both the urllib downloader here and curl in
# tools/vps-refresh.sh.
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.fcc.gov/",
}

# ---- ULS PUBACC column indices (0-based), verified against the layouts ----
HD_UI, HD_CALL, HD_STATUS, HD_SERVICE, HD_GRANT, HD_EXPIRED = 1, 4, 5, 6, 7, 8
EN_UI, EN_CALL, EN_NAME, EN_FIRST, EN_LAST, EN_CITY, EN_STATE, EN_ZIP, EN_FRN = 1, 4, 7, 8, 10, 16, 17, 18, 22
AM_UI, AM_CALL, AM_CLASS, AM_VANITY = 1, 4, 5, 13

# License ladder, entry -> advanced (order is meaningful: it's the progression)
CLASS_ORDER = ["N", "T", "P", "G", "A", "E"]
CLASS_LABELS = {
    "N": "Novice", "T": "Technician", "P": "Technician Plus",
    "G": "General", "A": "Advanced", "E": "Amateur Extra",
    "?": "Club / other",
}

# Pinellas County, FL is approximated by ZIP: the 337xx prefix is entirely
# Pinellas (St. Pete / Clearwater / Largo / Pinellas Park), plus these
# north-county 346xx ZIPs (Palm Harbor, Tarpon Springs, Dunedin, Oldsmar...).
PINELLAS_346 = {
    "34660", "34677", "34679", "34681", "34682", "34683", "34684",
    "34685", "34688", "34689", "34695", "34697", "34698",
}
def zip5(z):
    z = (z or "").strip()[:5]
    return z if len(z) == 5 and z.isdigit() else ""
def is_pinellas(z):
    z = zip5(z)
    return bool(z) and (z.startswith("337") or z in PINELLAS_346)

# Call-sign format, e.g. "1x3" for W4GGJ. The premium short formats (1x1, 1x2,
# 2x1) are no longer issued sequentially -- they're obtainable only through the
# vanity program -- so counting them is a conservative *lower bound* on vanity.
CALL_RE = re.compile(r"^([A-Z]{1,2})(\d)([A-Z]{1,3})$")
VANITY_FORMATS = {"1x1", "1x2", "2x1"}
FORMAT_ORDER = ["1x2", "2x1", "2x2", "1x3", "2x3"]
def call_format(call):
    m = CALL_RE.match((call or "").upper())
    return f"{len(m.group(1))}x{len(m.group(3))}" if m else "other"

def log(*a, **k): print(*a, file=sys.stderr, flush=True, **k)

# --------------------------------------------------------------------------- #
# Download + parse
# --------------------------------------------------------------------------- #
def download(url, dest):
    log(f"Downloading {url} ...")
    req = urllib.request.Request(url, headers=BROWSER_HEADERS)
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
        rec["city"] = row[EN_CITY].strip() if len(row) > EN_CITY else ""
        rec["zip"] = row[EN_ZIP].strip() if len(row) > EN_ZIP else ""
    return list(active.values()), today

# --------------------------------------------------------------------------- #
# Compute the stats object
# --------------------------------------------------------------------------- #
def class_breakdown(recs):
    """Class distribution (same shape as the national `classes` list) for any subset."""
    n = len(recs)
    p = lambda c: round(100 * c / n, 3) if n else 0.0
    cc = Counter(r.get("class", "") or "?" for r in recs)
    out = [{"code": c, "label": CLASS_LABELS.get(c, c), "count": cc[c], "pct": p(cc[c])}
           for c in CLASS_ORDER if c in cc]
    out += [{"code": c, "label": CLASS_LABELS.get(c, c), "count": cc[c], "pct": p(cc[c])}
            for c in cc if c not in CLASS_ORDER]
    return out

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

    # --- call-sign formats + conservative vanity estimate ---
    fmt = Counter(call_format(r.get("call", "")) for r in records)
    formats = [{"format": f, "count": fmt[f], "pct": pct(fmt[f])}
               for f in FORMAT_ORDER if f in fmt]
    formats += [{"format": f, "count": fmt[f], "pct": pct(fmt[f])}
                for f in sorted(fmt) if f not in FORMAT_ORDER]
    vest = sum(fmt.get(f, 0) for f in VANITY_FORMATS)
    vanity_estimate = {"count": vest, "pct": pct(vest), "formats": formats}

    # --- Florida (total + class breakdown) ---
    fl = [r for r in records if r.get("state") == "FL"]
    fl_rank = next((i + 1 for i, x in enumerate(states_all) if x["state"] == "FL"), None)
    florida = {"total": len(fl), "rank": fl_rank,
               "pct_of_us": pct(len(fl)), "classes": class_breakdown(fl)}

    # --- Pinellas County, approximated by ZIP (the area we support) ---
    pin = [r for r in records if is_pinellas(r.get("zip", ""))]
    pin_pct = lambda c: round(100 * c / len(pin), 3) if pin else 0.0
    cities = Counter(r["city"].title() for r in pin if r.get("city"))
    zips = Counter(zip5(r.get("zip", "")) for r in pin)
    pnames = Counter(r["first"].upper() for r in pin if r.get("first"))
    pin_fmt = Counter(call_format(r.get("call", "")) for r in pin)
    pin_vest = sum(pin_fmt.get(f, 0) for f in VANITY_FORMATS)
    pinellas = {
        "total": len(pin),
        "pct_of_fl": round(100 * len(pin) / len(fl), 3) if fl else 0.0,
        "pct_of_us": pct(len(pin)),
        "top_city": cities.most_common(1)[0][0] if cities else "-",
        "vanity_est": {"count": pin_vest, "pct": pin_pct(pin_vest)},
        "classes": class_breakdown(pin),
        "cities": [{"city": c, "count": v, "pct": pin_pct(v)} for c, v in cities.most_common()],
        "zips": [{"zip": z, "count": v, "pct": pin_pct(v)} for z, v in zips.most_common()],
        "names": [{"name": x, "count": v, "pct": pin_pct(v)} for x, v in pnames.most_common(10)],
    }

    # --- Program impact: licenses earned through our program (roster CSV) ---
    program = None
    rpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "program-licenses.csv")
    if os.path.exists(rpath):
        callset = {r["call"].upper() for r in records if r.get("call")}
        entries = []
        with open(rpath, newline="") as f:
            for row in csv.DictReader(f):
                cs = (row.get("callsign") or "").strip().upper()
                if cs:
                    entries.append(cs)
        if entries:
            program = {"total": len(entries),
                       "active": sum(1 for cs in entries if cs in callset)}

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
        "vanity_estimate": vanity_estimate,
        "expirations": expirations,
        "gender": gender,
        "florida": florida,
        "pinellas": pinellas,
        "program": program,
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
    header = ["snapshot_date", "total"] + [CLASS_LABELS[c] for c in CLASS_ORDER]
    cls = {c["code"]: c["count"] for c in s["classes"]}
    # Keep one row per snapshot date (a re-run on the same day overwrites it),
    # so the trend chart has one point per day rather than stacked duplicates.
    by_date = {}
    if os.path.exists(hist):
        with open(hist, newline="") as f:
            for r in csv.DictReader(f):
                if r.get("snapshot_date"):
                    by_date[r["snapshot_date"]] = r
    row = {"snapshot_date": s["snapshot_date"], "total": s["total"]}
    for c in CLASS_ORDER:
        row[CLASS_LABELS[c]] = cls.get(c, 0)
    by_date[s["snapshot_date"]] = row
    with open(hist, "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=header)
        wr.writeheader()
        for d in sorted(by_date):
            wr.writerow({k: by_date[d].get(k, "") for k in header})
    rows = [{"date": d, "total": int(by_date[d]["total"])} for d in sorted(by_date)]
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
  .live{display:inline-flex; align-items:center; gap:8px; margin-bottom:22px; flex-wrap:wrap}
  .live .updated{font-family:var(--mono); font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:var(--muted)}
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

  .mono{font-family:var(--mono)}

  /* program impact band */
  .impact{background:linear-gradient(180deg, rgba(16,185,129,.12), transparent); border-bottom:1px solid var(--border)}
  .impact-inner{display:flex; align-items:center; gap:24px; padding:36px 0; flex-wrap:wrap}
  .impact-num{font-family:var(--mono); font-weight:700; font-size:clamp(40px,8vw,72px); line-height:1; color:var(--green-l); text-shadow:0 0 28px rgba(16,185,129,.25)}
  .impact-txt{font-size:clamp(16px,2.4vw,20px); color:var(--text); max-width:36ch}
  .impact-txt b{color:var(--light); font-weight:700}
  .impact-txt .sub{display:block; color:var(--muted); font-size:13px; margin-top:6px}

  /* site chrome (matches the main page) */
  .site-bar{position:sticky; top:0; z-index:50; background:rgba(15,23,42,.82); backdrop-filter:blur(10px); -webkit-backdrop-filter:blur(10px); border-bottom:1px solid var(--border)}
  .site-bar-inner{display:flex; align-items:center; justify-content:space-between; height:64px; gap:20px}
  .mark{display:inline-flex; align-items:center; gap:10px; font-family:var(--mono); font-weight:700; font-size:17px; letter-spacing:-.01em; white-space:nowrap; color:var(--text); text-decoration:none}
  .mark-emblem{width:28px; height:28px; display:block; flex:none}
  .mark .one,.mark .edu{color:var(--green)}
  .mark .slash{color:var(--text); opacity:.7; margin:0 .15em}
  .site-links{display:flex; gap:22px; font-size:14px; font-weight:500}
  .site-links a{color:var(--muted); text-decoration:none; transition:color .15s}
  .site-links a:hover{color:var(--text)}
  .site-links a[aria-current="page"]{color:var(--green-l)}
  .site-foot .foot{display:flex; flex-wrap:wrap; justify-content:space-between; gap:18px; align-items:center}
  .site-foot .foot-nav{display:flex; flex-wrap:wrap; gap:18px; font-size:14px}
  .site-foot .foot-nav a{color:var(--muted); text-decoration:none}
  .site-foot .foot-nav a:hover{color:var(--text)}
  .site-foot .foot-nav a[aria-current="page"]{color:var(--green-l)}
  .site-foot .signoff{margin-top:8px; font-family:var(--mono); font-size:12px; color:var(--green-d)}
  @media (max-width:760px){ .site-links{display:none} }

  /* P1 restructure: section pill, "Your license" panel, lookup */
  .sec-head .pill{margin-left:auto; font-family:var(--mono); font-size:11px; letter-spacing:.1em; text-transform:uppercase; color:var(--green-l); background:rgba(16,185,129,.10); border:1px solid var(--green-d); border-radius:999px; padding:3px 11px}
  .yl-panel{background:rgba(16,185,129,.05); border:.5px solid rgba(16,185,129,.22); border-radius:16px; padding:26px 24px}
  .lookup{display:flex; gap:10px; flex-wrap:wrap; margin-top:18px}
  .lookup input{font-family:var(--mono); text-transform:uppercase; letter-spacing:.08em; font-size:18px; padding:12px 14px; width:200px; background:var(--bg2); border:1px solid var(--border); border-radius:10px; color:var(--light)}
  .lookup input:focus{outline:none; border-color:var(--green); box-shadow:0 0 0 3px rgba(16,185,129,.15)}
  .lookup button{font-family:var(--sans); font-weight:600; font-size:15px; padding:12px 22px; background:var(--green); color:#04221a; border:none; border-radius:10px; cursor:pointer}
  .lookup button:hover{background:var(--green-l)}
  .result{margin-top:20px}
  .result .note{color:var(--muted); font-size:14px; margin:0}
</style>
</head>
<body>
<script>const DATA = /*__DATA__*/;</script>

<header class="site-bar">
  <div class="wrap site-bar-inner">
    <a href="/" class="mark" aria-label="TavaOne Education home"><img src="/tavaone-education-emblem.svg" alt="" class="mark-emblem" width="28" height="28"/><span class="wordmark"><span>Tava</span><span class="one">One</span><span class="slash">//</span><span class="edu">Education</span></span></a>
    <nav class="site-links" aria-label="Primary">
      <a href="/#what">What's an Elmer</a>
      <a href="/#lab">STEM Lab</a>
      <a href="/#programs">Programs</a>
      <a href="/#tracks">Tracks</a>
      <a href="/#resources">Resources</a>
      <a href="/census/" aria-current="page">License Census</a>
    </nav>
  </div>
</header>

<header class="hero">
  <div class="wrap">
    <div class="live"><span class="dot"></span><span class="eyebrow" id="eyebrow"></span><span class="updated">&middot; updated Mondays 7&nbsp;AM ET</span></div>
    <div class="total" id="total">0</div>
    <div class="total-label">active <b>U.S. amateur radio operators</b> on the FCC roster &mdash; licensed, unexpired, ready to get on the air.</div>
    <div class="microbar" id="microbar"></div>
  </div>
</header>

<section class="impact" id="impactBand" style="display:none">
  <div class="wrap impact-inner">
    <div class="impact-num" id="impactNum">0</div>
    <div class="impact-txt">new <b>amateur licenses</b> earned with help from TavaOne Education<span class="sub" id="impactSub"></span></div>
  </div>
</section>

<main class="wrap">

  <!-- 1 -->
  <section id="us">
    <div class="sec-head"><span class="eyebrow">United States</span><h2>License classes</h2></div>
    <p class="sec-note">How today's active operators break down by license class. Each operator climbs from Technician to General to Amateur Extra; <b>Legacy</b> groups the discontinued Novice, Technician&nbsp;Plus, and Advanced classes.</p>
    <div class="panel"><div class="ladder" id="usBars"></div></div>
  </section>

  <!-- 2 -->
  <section id="your-license">
    <div class="sec-head"><span class="eyebrow">Your license</span><h2>Look up a call sign</h2></div>
    <div class="yl-panel">
      <p class="sec-note" style="margin:0">Check any U.S. call sign's license class and renewal date &mdash; from the public FCC ULS database, for educational use.</p>
      <div class="lookup">
        <input id="callInput" type="text" inputmode="text" autocomplete="off" spellcheck="false" maxlength="7" placeholder="W4GGJ" aria-label="Call sign">
        <button id="callBtn" type="button">Check</button>
      </div>
      <div id="callResult" class="result" hidden></div>
    </div>
  </section>

  <!-- 3 -->
  <section id="county">
    <div class="sec-head"><span class="eyebrow">Local county</span><h2 id="countyName">Pinellas County</h2><span class="pill" id="countyPill">Your county</span></div>
    <p class="sec-note" id="countyNote"></p>
    <div class="microbar" id="countyMicro" style="margin-top:0; margin-bottom:28px"></div>
    <div class="panel"><div class="ladder" id="countyBars"></div></div>
    <div class="grid2" style="margin-top:28px">
      <div class="panel" style="max-height:360px; overflow:auto"><table id="pinCityTable"></table></div>
      <div class="panel" style="max-height:360px; overflow:auto"><table id="pinZipTable"></table></div>
    </div>
    <div class="panel" style="max-height:360px; overflow:auto; margin-top:28px"><table id="pinNameTable"></table></div>
  </section>

  <!-- 4 -->
  <section id="florida">
    <div class="sec-head"><span class="eyebrow">Florida overview</span><h2>Statewide</h2></div>
    <p class="sec-note" id="flNote"></p>
    <div class="microbar" id="flMicro" style="margin-top:0; margin-bottom:28px"></div>
    <div class="panel"><div class="ladder" id="flBars"></div></div>
  </section>

  <!-- ===== national detail (kept from the original page) ===== -->
  <section>
    <div class="sec-head"><span class="eyebrow">Detail</span><h2>Where operators are</h2></div>
    <p class="sec-note">Active licenses by state of record. <span id="stateSummary"></span></p>
    <div class="grid2">
      <div class="panel"><div class="chart-box" style="height:360px"><canvas id="stateChart"></canvas></div></div>
      <div class="panel" style="max-height:404px; overflow:auto"><table id="stateTable"></table></div>
    </div>
  </section>

  <section>
    <div class="sec-head"><span class="eyebrow">Detail</span><h2>Call sign anatomy</h2></div>
    <p class="sec-note">U.S. call signs begin with A, K, N, or W, in formats like 1&times;3 (<span class="mono">W4GGJ</span>). The short 1&times;2 and 2&times;1 formats are no longer issued in sequence &mdash; they come only through the <b>vanity</b> program. <span id="vanityNote"></span></p>
    <div class="grid2">
      <div class="panel"><div class="chart-box"><canvas id="letterChart"></canvas></div></div>
      <div class="panel"><div class="chart-box"><canvas id="formatChart"></canvas></div></div>
    </div>
  </section>

  <section>
    <div class="sec-head"><span class="eyebrow">Detail</span><h2>Renewals on the horizon</h2></div>
    <p class="sec-note">Licenses run 10 years. This is when the current roster comes up for renewal &mdash; the current year is flagged in red.</p>
    <div class="panel"><div class="chart-box" style="height:320px"><canvas id="expChart"></canvas></div></div>
  </section>

  <section id="trendSec">
    <div class="sec-head"><span class="eyebrow">Detail</span><h2>The roster over time</h2></div>
    <p class="sec-note" id="trendNote"></p>
    <div class="panel"><div class="chart-box" style="height:320px"><canvas id="trendChart"></canvas></div></div>
  </section>

  <section style="border-bottom:none">
    <div class="sec-head"><span class="eyebrow">Detail</span><h2>Most common first names</h2></div>
    <p class="sec-note">The first names on the active roster, most common first.</p>
    <div class="panel" style="max-height:420px; overflow:auto"><table id="nameTable"></table></div>
  </section>

</main>

<footer class="wrap site-foot">
  <div class="foot">
    <a href="/" class="mark" aria-label="TavaOne Education home"><img src="/tavaone-education-emblem.svg" alt="" class="mark-emblem" width="28" height="28"/><span class="wordmark"><span>Tava</span><span class="one">One</span><span class="slash">//</span><span class="edu">Education</span></span></a>
    <nav class="foot-nav" aria-label="Footer">
      <a href="/">Home</a>
      <a href="/#programs">Programs</a>
      <a href="/#tracks">Tracks</a>
      <a href="/#resources">Resources</a>
      <a href="/census/" aria-current="page">License Census</a>
    </nav>
  </div>
  <div class="signoff">73 de the Elmers crew</div>
  <p style="max-width:62ch; margin:14px 0 18px">A public-interest snapshot of the amateur radio service, maintained to support STEM and licensing education.</p>
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
        BORDER=css('--border'), RED=css('--red');
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const fmtName = x => x.charAt(0)+x.slice(1).toLowerCase();
  const microHTML = items => items.map(m=>`<div class="micro"><div class="v">${m[1]}</div><div class="k">${m[0]}</div></div>`).join('');
  function rowsTable(el, head, rows){
    if(!el) return;
    el.innerHTML = '<thead><tr>'+head+'</tr></thead><tbody>'+rows+'</tbody>';
  }

  // Reusable horizontal bar list (national + county class breakdowns).
  function barsHTML(items){
    const total = items.reduce((a,b)=>a+b.count,0) || 1;
    const mx = Math.max(...items.map(i=>i.count), 1);
    return items.map(i=>{
      const pct = Math.round(i.count/total*100);
      const w = (i.count/mx*100).toFixed(1);
      return `<div class="rung"><div class="name">${i.label}</div>`+
        `<div class="track"><div class="fill" data-w="${w}" style="width:0;background:${i.color||GREEN}"></div></div>`+
        `<div class="val"><b>${num(i.count)}</b> &middot; ${pct}%</div></div>`;
    }).join('');
  }
  // Collapse FCC class codes into Technician / General / Amateur Extra / Legacy.
  function classBuckets(classes){
    const g = code => (classes.find(c=>c.code===code)||{count:0}).count;
    return [
      {label:'Technician',    count:g('T'),               color:'#34d399'},
      {label:'General',       count:g('G'),               color:'#10b981'},
      {label:'Amateur Extra', count:g('E'),               color:'#047857'},
      {label:'Legacy',        count:g('N')+g('P')+g('A'), color:'#64748b'},
    ];
  }

  document.getElementById('eyebrow').textContent = 'FCC ULS \u00B7 LIVE LICENSE CENSUS';
  document.getElementById('footDate').textContent = D.snapshot_date;

  // hero count-up (United States active total)
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
  document.getElementById('microbar').innerHTML = microHTML([
    ['Operators', num(D.total)],
    ['States & territories', num(D.states_represented)],
    ['Most common name', D.top_name],
  ]);

  // 1) United States \u2014 class bars
  document.getElementById('usBars').innerHTML = barsHTML(classBuckets(D.classes));

  // 2) Your license \u2014 interactive lookup (real data wiring lands in P3)
  const ci=document.getElementById('callInput'), cb=document.getElementById('callBtn'), cr=document.getElementById('callResult');
  function showSoon(){ cr.hidden=false; cr.innerHTML='<p class="note">Per-call lookup is coming soon &mdash; check back shortly.</p>'; }
  cb.addEventListener('click', showSoon);
  ci.addEventListener('keydown', e=>{ if(e.key==='Enter'){ e.preventDefault(); showSoon(); } });

  // 3) Local county \u2014 defaults to Pinellas (approximated by ZIP)
  const P = D.pinellas;
  document.getElementById('countyNote').innerHTML =
    `Our home county. <b>${num(P.total)}</b> active operators &mdash; ${P.pct_of_fl.toFixed(1)}% of Florida. ` +
    `<span style="color:var(--muted)">County isn't in the FCC data, so this is approximated from Pinellas ZIP codes (337xx plus north-county 346xx).</span>`;
  document.getElementById('countyMicro').innerHTML = microHTML([
    ['Active licenses', num(P.total)],
    ['Share of Florida', P.pct_of_fl.toFixed(1)+'%'],
    ['Top city', P.top_city],
  ]);
  document.getElementById('countyBars').innerHTML = barsHTML(classBuckets(P.classes));

  // 4) Florida overview
  const FL = D.florida;
  document.getElementById('flNote').innerHTML =
    `Florida has <b>${num(FL.total)}</b> active operators` +
    (FL.rank ? ` &mdash; #${FL.rank} nationally` : ``) +
    ` (${FL.pct_of_us.toFixed(1)}% of the U.S. total). Class breakdown below.`;
  document.getElementById('flMicro').innerHTML = microHTML(
    [['Active licenses', num(FL.total)], ['Share of U.S.', FL.pct_of_us.toFixed(1)+'%']]
    .concat(FL.rank ? [['Rank nationally', '#'+FL.rank]] : []));
  document.getElementById('flBars').innerHTML = barsHTML(classBuckets(FL.classes));

  // chart.js defaults (secondary detail charts below)
  Chart.defaults.color = MUTED; Chart.defaults.borderColor = BORDER;
  Chart.defaults.font.family = "'JetBrains Mono', monospace";
  const noLegend={plugins:{legend:{display:false}}};
  const grid={grid:{color:BORDER}, ticks:{color:MUTED}};

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
    D.names.map((x,i)=>`<tr><td class="num" style="color:var(--muted)">${i+1}</td><td>${fmtName(x.name)}</td><td class="num">${num(x.count)}</td><td class="num">${x.pct.toFixed(3)}</td></tr>`).join('')+'</tbody>';

  // estimated vanity + call-sign formats
  const ve = D.vanity_estimate;
  document.getElementById('vanityNote').innerHTML =
    `About <b>${num(ve.count)}</b> active calls (${ve.pct.toFixed(2)}%) use a premium 1&times;1/1&times;2/2&times;1 format &mdash; a conservative floor on vanity calls, since the FCC file can't flag standard-format vanity calls.`;
  const FMT = ve.formats.filter(f=>f.format!=='other').slice(0,6);
  new Chart(document.getElementById('formatChart'),{type:'bar',
    data:{labels:FMT.map(f=>f.format),
      datasets:[{data:FMT.map(f=>f.count),
        backgroundColor:FMT.map(f=>['1x1','1x2','2x1'].includes(f.format)?GREEN_L:MUTED)}]},
    options:{...noLegend, scales:{x:grid,y:grid}}});

  // local county detail tables (Pinellas)
  rowsTable(document.getElementById('pinCityTable'),
    '<th>City</th><th style="text-align:right">Operators</th><th style="text-align:right">%</th>',
    P.cities.map(c=>`<tr><td>${c.city}</td><td class="num">${num(c.count)}</td><td class="num">${c.pct.toFixed(1)}</td></tr>`).join(''));
  rowsTable(document.getElementById('pinZipTable'),
    '<th>ZIP</th><th style="text-align:right">Operators</th><th style="text-align:right">%</th>',
    P.zips.map(z=>`<tr><td>${z.zip}</td><td class="num">${num(z.count)}</td><td class="num">${z.pct.toFixed(1)}</td></tr>`).join(''));
  rowsTable(document.getElementById('pinNameTable'),
    '<th>Rank</th><th>First name</th><th style="text-align:right">Operators</th>',
    P.names.map((x,i)=>`<tr><td class="num" style="color:var(--muted)">${i+1}</td><td>${fmtName(x.name)}</td><td class="num">${num(x.count)}</td></tr>`).join(''));

  // program impact band (shown only when the roster CSV has entries)
  if(D.program && D.program.total>0){
    document.getElementById('impactBand').style.display='block';
    document.getElementById('impactSub').textContent =
      `${num(D.program.active)} currently active on the FCC roster · verified against today's file`;
    const pn=document.getElementById('impactNum'), target=D.program.total;
    if(reduce){ pn.textContent=num(target); }
    else{
      const t0=performance.now(), dur=900;
      (function st(now){const p=Math.min(1,(now-t0)/dur);pn.textContent=num(Math.round(target*(1-Math.pow(1-p,3))));if(p<1)requestAnimationFrame(st);})(t0);
    }
  }

  // animate every ladder fill once all ladders are rendered
  requestAnimationFrame(()=>document.querySelectorAll('.fill').forEach(f=>{ f.style.width=f.dataset.w+'%'; }));
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
    print(f"Vanity (AM flag): {s['vanity']['vanity']:,} ({s['vanity']['vanity_pct']:.2f}%)")
    print(f"Vanity est. (1x1/1x2/2x1): {s['vanity_estimate']['count']:,} ({s['vanity_estimate']['pct']:.2f}%)")
    print(f"Florida: {s['florida']['total']:,} (rank {s['florida']['rank']})")
    print(f"Pinellas (by ZIP): {s['pinellas']['total']:,}  top city: {s['pinellas']['top_city']}")
    if s.get("program"):
        print(f"Program licenses: {s['program']['total']} ({s['program']['active']} active on FCC roster)")
    print(f"Outputs in: {os.path.abspath(args.out)}/  (open ham_stats.html)")

    if tmp:
        try: os.remove(zip_path)
        except OSError: pass

if __name__ == "__main__":
    main()
