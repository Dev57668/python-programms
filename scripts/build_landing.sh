#!/usr/bin/env bash
# Builds the static site (landing page + read-only dashboard demo) into $1. Used by GitHub Pages and Vercel.
# There is no Python server there, so demo.js answers the dashboard's /api calls from recorded sample data.
set -euo pipefail
W=codevault/web/static
OUT=${1:?usage: build_landing.sh <outdir>}
mkdir -p "$OUT/dashboard" "$OUT/demo"
sed -e 's#href="/landing.css"#href="landing.css"#' \
    -e 's#<script src="/landing.js">#<script src="demo.js"></script><script src="landing.js">#' \
    -e 's#href="/dashboard"#href="dashboard/"#g' "$W/landing.html" > "$OUT/index.html"
sed -e 's#href="/style.css"#href="../style.css"#' -e 's#href="/"#href="../"#g' \
    -e 's#<script src="/app.js">#<script src="../demo.js"></script><script src="../app.js">#' "$W/index.html" > "$OUT/dashboard/index.html"
sed 's#location.href = "/dashboard\#files";#location.href = "dashboard/\#files";#' "$W/landing.js" > "$OUT/landing.js"
cp "$W/landing.css" "$W/style.css" "$W/app.js" "$W/demo.js" "$OUT/"
cp "$W/demo/api.json" "$OUT/demo/"
touch "$OUT/.nojekyll"
# Fail rather than publish a page with links that 404 when hosted under a sub-path.
! grep -n '"/dashboard\|"/landing\|"/app.js\|"/style.css\|href="/"' "$OUT/index.html" "$OUT/dashboard/index.html" "$OUT/landing.js"
