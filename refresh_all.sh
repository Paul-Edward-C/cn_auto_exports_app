#!/bin/bash
# Refresh BOTH tabs of the live app in one go.
#
# The only thing you have to do by hand is run the notebooks. Then:
#
#     bash refresh_all.sh
#
# and open GitHub Desktop -> Push origin. That's the whole process.
#
# This replaces having to remember refresh_auto.sh AND build_cn_long.py separately. Running
# only half of it is how the China tab ended up a month out of step in August 2026: the
# notebook had regenerated app/data/optimized/, but cn_long.parquet was never rebuilt from it,
# and nothing complained because git status showed optimized/ as modified either way.
#
# Safe to run at any time. Both builders read whatever the notebooks last wrote and are
# idempotent, so a run with no new data simply reports "nothing changed" and stops.
set -e

PY=/Users/paul/opt/anaconda3/bin/python      # base anaconda: build_wide.py needs numpy 1.x
DASH=/Users/paul/Documents/ghost/region_auto_dashboard
APP=/Users/paul/Documents/ghost/cn_auto_exports

cd "$APP"

# ---------------------------------------------------------------------------------------
echo "==> 1/5  Which notebooks have run recently"
"$PY" - <<'PYEOF'
import os, time
D = '/Users/paul/Documents/DATA/'
SRC = [
    ('Japan   jp_trade_recent',        D + 'jp/jp_input/jp_trade_autos_full_m.parquet'),
    ('Korea   kr_trade_recent',        D + 'kr/kr_input/kr_trade_autos_full_m.parquet'),
    ('EU      eu_imports_latest',      D + 'eu/eu_input/eu_autos_hist_m.parquet'),
    ('EM      comtrade notebook',      D + 'em/em_input/em_comtrade_auto_m.parquet'),
    ('China   cn_hs_8_digit_recent',   D + 'cn/cn_input/cn_hs_8_digit_recent.csv'),
    ('China   (optimized/, same nb)',
     '/Users/paul/Documents/ghost/cn_auto_exports/app/data/optimized/wide.pkl'),
]
now = time.time()
for label, path in SRC:
    if not os.path.exists(path):
        print(f'    {label:<32} MISSING  {path}')
        continue
    age = (now - os.path.getmtime(path)) / 86400
    flag = '  <-- stale, notebook not run?' if age > 40 else ''
    print(f'    {label:<32} {time.strftime("%Y-%m-%d", time.localtime(os.path.getmtime(path)))}'
          f'  ({age:4.0f}d){flag}')
PYEOF

# Content fingerprint of what the app currently ships, taken BEFORE anything is rebuilt.
# Parquet is not byte-reproducible -- rebuilding identical data still writes different bytes,
# so `git diff` always reports a change and a naive script commits noise on every run. Compare
# the DATA instead.
FP_BEFORE=$(mktemp)
"$PY" fingerprint_app_data.py > "$FP_BEFORE"

# ---------------------------------------------------------------------------------------
echo ""
echo "==> 2/5  Auto tab: rebuilding auto_long.parquet"
cd "$DASH"
"$PY" build_long_inputs.py > /dev/null    # EU + China auto -> long parquets
"$PY" build_data.py        > /dev/null    # all reporters   -> data/auto_long.parquet
cp "$DASH/data/auto_long.parquet" "$APP/app/data/auto_long.parquet"
echo "    built and copied into the app"

# ---------------------------------------------------------------------------------------
echo ""
echo "==> 3/5  China tab: rebuilding cn_long.parquet from app/data/optimized/"
cd "$APP"
"$PY" build_cn_long.py > /dev/null
echo "    built"

# ---------------------------------------------------------------------------------------
echo ""
echo "==> 4/5  How fresh the app's data now is"
"$PY" - <<'PYEOF'
import pandas as pd
a = pd.read_parquet('app/data/auto_long.parquet')
last = a.groupby('economy', observed=True)['Date'].max().sort_values(ascending=False)
print('    auto tab, latest month by reporter:')
for k, v in last.items():
    # Russia (reported) and UAE are dormant series that ended years ago, not failures
    note = '  (dormant)' if v.year < 2024 else ''
    print(f'        {k:<20} {v.date()}{note}')
c = pd.read_parquet('app/data/cn_long.parquet')
print(f"    china tab, latest month:  {c['Date'].max().date()}   ({len(c):,} rows)")
PYEOF

# ---------------------------------------------------------------------------------------
echo ""
echo "==> 5/5  Committing whatever changed (NOT pushing)"
FP_AFTER=$(mktemp)
"$PY" fingerprint_app_data.py > "$FP_AFTER"
if diff -q "$FP_BEFORE" "$FP_AFTER" > /dev/null; then
    # Same data, different bytes. Throw the rebuild away so the repo stays clean rather than
    # carrying a commit that changes nothing.
    git checkout -- app/data 2>/dev/null || true
    rm -f "$FP_BEFORE" "$FP_AFTER"
    echo "    Data is identical to what is already committed — nothing to deploy. Done."
    exit 0
fi
rm -f "$FP_BEFORE" "$FP_AFTER"
git status --short -- app/data | sed 's/^/        /'
git add app/data
git commit -q -m "Refresh app data ($(date '+%Y-%m-%d'))"
echo ""
echo "    Committed but NOT live yet."
echo "    -> GitHub Desktop -> Push origin to deploy."
