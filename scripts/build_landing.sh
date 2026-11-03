#!/usr/bin/env bash
# Builds the static landing page (no server needed) into $1. Used by GitHub Pages and Vercel.
# The dashboard needs the local Python server, so its links point to the setup section instead.
set -euo pipefail
W=codevault/web/static
OUT=${1:?usage: build_landing.sh <outdir>}
mkdir -p "$OUT"
sed -e 's#href="/landing.css"#href="landing.css"#' -e 's#src="/landing.js"#src="landing.js"#' \
    -e 's#href="/dashboard">Open dashboard#href="\#start">Run the dashboard#g' \
    -e 's#href="/dashboard">Watch it happen in the dashboard#href="\#start">Run it to watch it happen#' \
    "$W/landing.html" > "$OUT/index.html"
cp "$W/landing.css" "$OUT/landing.css"
sed 's#location.href = "/dashboard\#files";#location.hash = "start";#' "$W/landing.js" > "$OUT/landing.js"
touch "$OUT/.nojekyll"
# Fail rather than publish a page with links that 404 when hosted statically.
! grep -n '"/dashboard\|"/landing' "$OUT/index.html" "$OUT/landing.js"
