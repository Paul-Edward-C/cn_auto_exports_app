#!/bin/bash
# Refresh the Auto-trade tab (Japan / Korea / EU / China-auto / Comtrade EMs) on the live app.
#
# Run this AFTER you've run the country notebooks that update the raw input parquets
# (jp_trade_recent, kr_trade_recent, eu_imports_latest, ...). It rebuilds the combined
# auto_long.parquet, copies it into the app, and commits it. It does NOT push — open
# GitHub Desktop and click "Push origin" to deploy, the way you normally do.
#
#     bash refresh_auto.sh
#
set -e  # stop on the first error

PY=/Users/paul/opt/anaconda3/bin/python
DASH=/Users/paul/Documents/ghost/region_auto_dashboard
APP=/Users/paul/Documents/ghost/cn_auto_exports

echo "==> 1/4  Building combined auto_long.parquet from the latest country inputs"
cd "$DASH"
"$PY" build_long_inputs.py     # EU + China auto -> long parquets
"$PY" build_data.py            # all reporters   -> data/auto_long.parquet

echo "==> 2/4  Copying it into the app"
cp "$DASH/data/auto_long.parquet" "$APP/app/data/auto_long.parquet"

echo "==> 3/4  Checking whether the app data actually changed"
cd "$APP"
if git diff --quiet -- app/data/auto_long.parquet; then
    echo "    No change in auto_long.parquet — nothing to deploy. Done."
    exit 0
fi

echo "==> 4/4  Committing the change (NOT pushing)"
git add app/data/auto_long.parquet
git commit -m "Refresh auto data ($(date '+%Y-%m-%d'))"
echo ""
echo "    Done. The new auto_long.parquet is committed but NOT yet live."
echo "    -> Open GitHub Desktop and click 'Push origin' to deploy."
