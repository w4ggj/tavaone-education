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

If `data.fcc.gov` returns 503/timeout (it throttles some datacenter IPs),
download <https://data.fcc.gov/download/pub/uls/complete/l_amat.zip> in a browser
and pass it with `--zip`.

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

## Automated weekly refresh

`.github/workflows/census-refresh.yml` runs Monday ~7:00 AM Eastern (and on
demand via the Actions tab). It seeds `census-history.csv` into the build, runs
the generator (with retries for FCC throttling), copies the page to
`census/index.html`, updates the history file, and commits + pushes — which
triggers the GitHub Pages redeploy. No local machine required.
