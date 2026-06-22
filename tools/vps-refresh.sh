#!/usr/bin/env bash
# Weekly U.S. Amateur Radio License Census refresh — runs on the DigitalOcean
# VPS, where data.fcc.gov is reachable. (GitHub Actions' Azure IPs are blocked.)
#
# The FCC edge (Akamai) stalls large-file GETs from non-browser clients, so we
# fetch the zip with curl using a full browser header set (resume + retries),
# then build from it with --zip.
#
# One-time setup on the VPS:
#   sudo apt-get update && sudo apt-get install -y git python3 curl
#   sudo mkdir -p /opt/hamstats && sudo chown "$USER" /opt/hamstats
#   cd /opt/hamstats
#   git clone git@github.com:w4ggj/tavaone-education.git   # add a write deploy key first
#   crontab -e
#   # Mondays ~7:00 AM Eastern (11:00 UTC; shifts +/-1h with daylight saving):
#   0 11 * * 1  /opt/hamstats/tavaone-education/tools/vps-refresh.sh >> /opt/hamstats/refresh.log 2>&1
#
# Requires: git, python3 (3.8+), curl. No third-party Python packages.
set -euo pipefail

REPO="${REPO:-/opt/hamstats/tavaone-education}"
BRANCH="${BRANCH:-main}"
FCC_URL="https://data.fcc.gov/download/pub/uls/complete/l_amat.zip"
BUILD="$(mktemp -d)"
ZIP="$BUILD/l_amat.zip"
trap 'rm -rf "$BUILD"' EXIT

cd "$REPO"
git fetch --quiet origin "$BRANCH"
git checkout --quiet "$BRANCH"
git reset --quiet --hard "origin/$BRANCH"

# Carry the accumulated trend history into the build so the generator extends it
# (total-active-operators over time is the one stat that can't be backfilled).
[ -f tools/census-history.csv ] && cp tools/census-history.csv "$BUILD/history.csv"

# Fetch the FCC zip with browser-like headers (Akamai stalls plain clients).
echo "$(date -u +%FT%TZ) downloading l_amat.zip ..."
curl --fail --location --http1.1 \
  --retry 5 --retry-delay 15 --retry-connrefused -C - \
  --connect-timeout 30 --max-time 1800 \
  -H 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36' \
  -H 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8' \
  -H 'Accept-Language: en-US,en;q=0.9' \
  -H 'Referer: https://www.fcc.gov/' \
  -o "$ZIP" "$FCC_URL"

python3 "$REPO/tools/fcc_ham_stats.py" --zip "$ZIP" --out "$BUILD"

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
