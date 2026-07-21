# Updating the data on the live app

This app has **two tabs**, each driven by **one committed parquet file**. The app never reads
your notebooks' raw files directly — it only reads these two, and it reads whatever version was
in the **last push to GitHub**. Pushing to GitHub is what deploys (Heroku auto-deploys from
GitHub — that's why GitHub Desktop "updates the app").

| Tab | File the app reads | Where it comes from |
|-----|--------------------|---------------------|
| **China trade** | `app/data/cn_long.parquet` (+ `app/data/optimized/wide.pkl`) | you build it (see below) |
| **Auto trade** (Japan, Korea, EU, + EM reporters) | `app/data/auto_long.parquet` | built by a script from other people's country files |

So updating the live app is always the same shape:
**refresh the raw inputs → rebuild the app's parquet → commit → Push origin in GitHub Desktop.**

---

## Auto trade tab (Japan / Korea / EU / …)

`auto_long.parquet` is a *derived* file. You don't create it — a script combines the country
input files into it. Those inputs come from notebooks (some run by you, some not):

| Reporter | Raw input file | Produced by |
|----------|----------------|-------------|
| Japan | `DATA/jp/jp_input/jp_trade_autos_full_m.parquet` | `jp_trade_recent.ipynb` |
| Korea | `DATA/kr/kr_input/kr_trade_autos_full_m.parquet` | `kr_trade_recent.ipynb` |
| EU | `DATA/eu/eu_input/eu_autos_hist_m.parquet` | `eu_imports_latest.ipynb` |
| China (auto) | `DATA/cn/cn_input/cn_hs_8_digit_recent.csv` | `cn_hs_8_digit_recent.ipynb` |
| India, Saudi, UAE, South Africa, Russia | `DATA/em/em_input/em_comtrade_auto_m.parquet` | Comtrade notebook |

### Steps

1. **Run the country notebook(s)** you want to refresh (above). This updates the raw inputs.
2. **Run the refresh script** — it rebuilds `auto_long.parquet`, copies it into the app, and
   commits it (it does *not* push):
   ```bash
   bash refresh_auto.sh
   ```
   If the data didn't actually change, it says so and stops — no empty commit.
3. **Open GitHub Desktop → click "Push origin".** That deploys. The live app updates in a
   minute or two.

### What `refresh_auto.sh` actually does
- `region_auto_dashboard/build_long_inputs.py` — turns the EU + China raw files into long
  format (EUR→USD, powertrain buckets, unit prices).
- `region_auto_dashboard/build_data.py` — combines **all** reporters into one
  `region_auto_dashboard/data/auto_long.parquet`.
- copies that into `app/data/auto_long.parquet` (the app's own copy — this copy step is the
  one that's easy to forget by hand).
- commits it if it changed.

Japan and Korea are melted straight from their wide parquets inside `build_data.py`, so if you
only touched JP or KR, the script still works — `build_long_inputs.py` just rebuilds EU/China
harmlessly.

---

## China trade tab

Separate chain — this one you build from your own notebook:

1. Run **`cn_hs_8_digit_recent.ipynb`** top to bottom. Its final cells regenerate
   `app/data/optimized/` and (via `build_wide.py`) `optimized/wide.pkl`.
   > A guard in the restructure cell stops the run if it parses fewer than ~50k columns, so a
   > schema slip can't silently ship an empty dataset again.
2. Build the app's long file:
   ```bash
   /Users/paul/opt/anaconda3/bin/python build_cn_long.py   # -> app/data/cn_long.parquet
   ```
3. Commit `app/data/cn_long.parquet` + `app/data/optimized/`, then **Push origin** in GitHub
   Desktop.

Run these with **base anaconda** (`/Users/paul/opt/anaconda3/bin/python`): `build_wide.py`
needs numpy 1.x to match the Heroku dyno; the `animation` env's numpy 2.x produces a pickle the
dyno can't load.

---

## How to tell what's currently live

The live app shows whatever was last pushed. To see how fresh each reporter is in the file
you're about to push:

```bash
/Users/paul/opt/anaconda3/bin/python -c "
import pandas as pd
d = pd.read_parquet('app/data/auto_long.parquet')
print(d.groupby('economy', observed=True)['Date'].max())"
```

EU usually lags the others by a month or two (EU customs publishes later) — if the app looks
stale, EU is normally the reporter to refresh first.

---

## The one thing that trips people up

`build_data.py` writes to **`region_auto_dashboard/data/`**, not to this app. The app reads its
**own copy** in `app/data/`. `refresh_auto.sh` does the copy for you; if you ever build by hand,
don't forget it — otherwise you'll commit nothing and the live app stays stale. Quick check
before pushing: `git status` should list `app/data/auto_long.parquet` as modified.
