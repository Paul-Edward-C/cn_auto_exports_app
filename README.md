# cn_auto_exports

The China-trade and auto-trade dashboard behind East Asia Econ. Two tabs, each driven by one
committed parquet file, deployed to Heroku from GitHub.

| Tab | What it shows | File the app reads |
|-----|---------------|--------------------|
| **China trade** | China's exports and imports at HS-8, by partner and product group | `app/data/cn_long.parquet` + `app/data/optimized/` |
| **Auto trade** | Vehicle exports for Japan, Korea, EU, China and six EM reporters | `app/data/auto_long.parquet` |

---

## Updating the data

**Run the notebooks, then one command.**

```bash
cd /Users/paul/Documents/ghost/cn_auto_exports
bash refresh_all.sh
```

Then open GitHub Desktop and click **Push origin**. That deploys — Heroku builds from GitHub,
and the live app updates a minute or two later.

That is the whole process. Everything below is context for when it goes wrong.

### Which notebook feeds which reporter

Run only the ones with new data; `refresh_all.sh` rebuilds everything either way, harmlessly.

| Reporter | Notebook | Raw file it writes |
|----------|----------|--------------------|
| Japan | `jp_trade_recent` | `DATA/jp/jp_input/jp_trade_autos_full_m.parquet` |
| Korea | `kr_trade_recent` | `DATA/kr/kr_input/kr_trade_autos_full_m.parquet` |
| EU | `eu_imports_latest` | `DATA/eu/eu_input/eu_autos_hist_m.parquet` |
| India, Saudi, UAE, South Africa, Russia | Comtrade notebook | `DATA/em/em_input/em_comtrade_auto_m.parquet` |
| China — **both tabs** | `cn_hs_8_digit_recent` | `DATA/cn/cn_input/cn_hs_8_digit_recent.csv` and `app/data/optimized/` |

`cn_hs_8_digit_recent` is the only notebook feeding both tabs. Run it top to bottom: its final
cells regenerate `app/data/optimized/`, which `build_cn_long.py` then turns into the China tab's
long file.

### What `refresh_all.sh` reports

1. **When each notebook last ran**, flagged `<-- stale, notebook not run?` past 40 days — so
   something you forgot shows up before you deploy rather than after.
2. **The latest month for every reporter**, after rebuilding. EU normally lags a month or two
   because EU customs publishes late; if the app looks stale, EU is usually why. `Russia
   (reported)` and `UAE` end in 2021 and 2019 and are marked `(dormant)` — those are not
   failures, the series simply stopped.
3. **Whether anything actually changed**, and it commits only if so.

Safe to run as often as you like. A run with no new data reports
`Data is identical to what is already committed` and leaves the repo untouched.

---

## Two traps worth knowing about

**Half a refresh looks exactly like a whole one.** In August 2026 the China tab spent a month
out of step with itself: `cn_hs_8_digit_recent.ipynb` had regenerated `app/data/optimized/`, but
`build_cn_long.py` was never run, so the two files behind the same tab disagreed. Nothing
complained, because `git status` showed `optimized/` as modified either way. Running
`refresh_all.sh` rather than the individual scripts is what prevents a repeat.

**`git diff` cannot tell you whether the data changed.** Parquet embeds creation metadata, so a
rebuild of identical data always shows as modified. Worse, the builders are not bit-deterministic
in floating point — one rebuild of unchanged inputs moved a single `usd_per_unit` value by 1e-3
on a number around 1.6e4, out of 2.4m rows. `fingerprint_app_data.py` therefore hashes the values
at six significant figures, and `refresh_all.sh` discards a rebuild that produced identical data
instead of committing noise.

---

## Use base anaconda

```
/Users/paul/opt/anaconda3/bin/python
```

`build_wide.py` needs numpy 1.x to match the Heroku dyno. The `animation` environment's numpy 2.x
writes a pickle the dyno cannot load, and the failure only shows up in production.

---

## Files

| | |
|---|---|
| `refresh_all.sh` | both tabs, one command — **start here** |
| `refresh_auto.sh` | auto tab only, kept for when you want just that half |
| `build_cn_long.py` | `app/data/optimized/` → `app/data/cn_long.parquet` |
| `build_wide.py` | rebuilds `optimized/wide.pkl` (called by the China notebook) |
| `fingerprint_app_data.py` | content hash used to decide whether a rebuild is worth committing |
| `DATA_REFRESH.md` | the long-form runbook, including the manual per-tab steps |
| `DEPLOYMENT_GUIDE.md` | Heroku setup, dynos, environment |
| `main_latest.py` | the Flask app |
