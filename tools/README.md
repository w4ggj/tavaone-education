# tools/

Utilities behind the **License Census** page (`/census/`). These files are not
part of the published site UI — `fcc_ham_stats.py` is served by GitHub Pages as
an inert text file but is never executed server-side.

## `fcc_ham_stats.py`

Generates `census/index.html` (and CSV/JSON tables) from the FCC ULS public
amateur-radio database. Pure standard library; `matplotlib` is optional and only
used for static PNG charts (skipped if not installed).

```bash
python3 tools/fcc_ham_stats.py --out ./_build        # download fresh -> ./_build
python3 tools/fcc_ham_stats.py --zip l_amat.zip --out ./_build   # reuse a local zip
```

Output of interest: `_build/ham_stats.html` → copy to `census/index.html`.

`data.fcc.gov` is behind Akamai, which **stalls large-file GETs from non-browser
clients** (plain `urllib`/`curl` hang on the body even though a HEAD returns 200).
The downloader sends a full browser header set (real UA + `Accept-Language` +
`Referer`) to get the body served; `vps-refresh.sh` does the same with curl. If a
fetch still fails, download the zip in a browser and pass it with `--zip`.

## `census-history.csv`

One snapshot row per run (`snapshot_date,total,<class counts...>`). This is the
data behind the "roster over time" trend chart — the **one statistic that can't
be backfilled**, since the FCC dump is only a current snapshot. Keep this file in
the repo so it accumulates; the generator appends to it when it's present in the
output directory.

## `program-licenses.csv`

The roster of operators **licensed through our program**, driving the "new
licenses earned with help from TavaOne Education" count on the census page.
Header: `callsign,name,licensed_date` (only `callsign` is required). Add one row
per student, e.g.:

```csv
callsign,name,licensed_date
KO4ABC,Jane Doe,2025-09-14
```

The generator counts the entries and cross-checks each call against the current
FCC roster, so the page can show both the total earned and how many are still
active. The impact band is hidden until the file has at least one entry.

## Florida & Pinellas sections

The generator also emits a Florida class breakdown and a full Pinellas County
section (class breakdown, top cities, top ZIP areas, common names, estimated
vanity). Pinellas has **no county field in FCC data**, so it's approximated from
ZIP codes — the `337xx` prefix plus a curated set of north-county `346xx` ZIPs
(see `PINELLAS_346` in the script).

## Automated weekly refresh (`vps-refresh.sh`)

Runs on the **DigitalOcean VPS**, not GitHub Actions: the FCC edge
(`data.fcc.gov`) blocks/throttles Actions' Azure datacenter IPs, so a scheduled
Action just hangs on the download. The VPS has a normal IP FCC serves.

`vps-refresh.sh` pulls the repo, seeds `census-history.csv` into the build, runs
the generator, copies the page to `census/index.html`, updates the history file,
and commits + pushes `main` — which triggers the GitHub Pages redeploy.

One-time VPS setup (see the header of `vps-refresh.sh` for exact commands):

1. Clone the repo to `/opt/hamstats/tavaone-education`.
2. Give it push access — an SSH **deploy key with write access**, or a
   PAT-authenticated HTTPS remote.
3. Add the weekly cron (Mondays ~7:00 AM Eastern):
   ```
   0 11 * * 1  /opt/hamstats/tavaone-education/tools/vps-refresh.sh >> /opt/hamstats/refresh.log 2>&1
   ```

Run it once by hand first to confirm it fetches, builds, and pushes cleanly.
