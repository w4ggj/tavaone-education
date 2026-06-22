#!/usr/bin/env bash
# Weekly U.S. Amateur Radio License Census refresh — runs on the DigitalOcean
# VPS, where data.fcc.gov is reachable. (GitHub Actions' datacenter IPs are
# blocked/throttled by the FCC edge, so the refresh can't run there.)
#
# One-time setup on the VPS:
#   sudo mkdir -p /opt/hamstats && sudo chown "$USER" /opt/hamstats
#   cd /opt/hamstats
#   git clone git@github.com:w4ggj/tavaone-education.git
#   # Give it push access: add an SSH *deploy key with write access* to the repo
#   # (Settings -> Deploy keys), or use a PAT-authenticated https remote.
#   crontab -e
#   # Mondays ~7:00 AM Eastern (11:00 UTC; shifts +/-1h with daylight saving):
#   0 11 * * 1  /opt/hamstats/tavaone-education/tools/vps-refresh.sh >> /opt/hamstats/refresh.log 2>&1
#
# Requires: git, python3 (3.8+). No third-party Python packages.
set -euo pipefail

REPO="${REPO:-/opt/hamstats/tavaone-education}"
BRANCH="${BRANCH:-main}"
BUILD="$(mktemp -d)"
trap 'rm -rf "$BUILD"' EXIT

cd "$REPO"
git fetch --quiet origin "$BRANCH"
git checkout --quiet "$BRANCH"
git reset --quiet --hard "origin/$BRANCH"

# Carry the accumulated trend history into the build so the generator extends it
# (total-active-operators over time is the one stat that can't be backfilled).
[ -f tools/census-history.csv ] && cp tools/census-history.csv "$BUILD/history.csv"

# Run from the build dir so the temporary l_amat.zip never lands in the repo.
( cd "$BUILD" && python3 "$REPO/tools/fcc_ham_stats.py" --out "$BUILD" )

cp "$BUILD/ham_stats.html" census/index.html
cp "$BUILD/history.csv" tools/census-history.csv

if git diff --quiet -- census/index.html tools/census-history.csv; then
  echo "$(date -u +%FT%TZ) no changes"
  exit 0
fi
git add census/index.html tools/census-history.csv
git -c user.name="hamstats-bot" -c user.email="hamstats@tavaoneeducation.org" \
    commit --quiet -m "Weekly license census refresh ($(date -u +%Y-%m-%d))"
git push --quiet origin "$BRANCH"   # push to main triggers the GitHub Pages redeploy
echo "$(date -u +%FT%TZ) pushed refresh"
