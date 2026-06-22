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

## Automated weekly refresh

`.github/workflows/census-refresh.yml` runs Monday ~7:00 AM Eastern (and on
demand via the Actions tab). It seeds `census-history.csv` into the build, runs
the generator (with retries for FCC throttling), copies the page to
`census/index.html`, updates the history file, and commits + pushes — which
triggers the GitHub Pages redeploy. No local machine required.
