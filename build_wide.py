#!/usr/bin/env python
"""Precompute the app's wide tables (wide.pkl) from the optimized long-format parquet.

The Heroku bokeh app (app/main.py) used to read data_normalized.parquet (~5M rows)
and pivot it per (flow, product, product_cat, unit) at boot. That reshape peaked at
~1.3 GB and OOM-killed the 512 MB dyno (R14/R15). This script does the reshape offline
and ships the result as a pickle the app loads in ~110 MB.

Run with an env whose pandas MINOR version matches the dyno pin
(requirements.txt: pandas==2.2.2). pandas DataFrame pickles are NOT guaranteed loadable
across pandas versions, so use the 'animation' conda env (pandas 2.2.3), e.g.:

    /Users/paul/opt/anaconda3/envs/animation/bin/python build_wide.py

This mirrors the rename -> dedup -> pivot -> YoY logic in app/main.py exactly.
"""
import pickle
from pathlib import Path

import pandas as pd

OPT = Path(__file__).resolve().parent / "app" / "data" / "optimized"

# Must stay identical to COUNTRY_RENAMES in app/main.py.
COUNTRY_RENAMES = {
    "Hong Kong S.A.R.": "Hong Kong",
    "World excluding Hong Kong S.A.R.": "World excluding Hong Kong",
    "Macao S.A.R": "Macao",
    "Democratic People's Republic of Korea": "North Korea",
    "DPRK": "North Korea",
}

KEY = ["flow", "product", "product_cat", "unit"]
DEDUP = ["flow", "country", "product", "product_cat", "unit", "date"]


def main() -> None:
    dates = pd.read_parquet(OPT / "dates.parquet")
    date_index = pd.DatetimeIndex(pd.to_datetime(dates["date"]))

    df = pd.read_parquet(OPT / "data_normalized.parquet")
    df["date"] = pd.to_datetime(df["date"])
    df["country"] = df["country"].replace(COUNTRY_RENAMES)
    # Collapse rows that became duplicate keys after the rename, keeping first non-null.
    df = df.sort_values("value", na_position="last").drop_duplicates(DEDUP, keep="first")

    wide = {}
    for key, g in df.groupby(KEY, sort=False):
        k = tuple(str(x) for x in key)  # plain str keys, matching metadata lookups
        w = (g.pivot_table(index="date", columns="country", values="value", aggfunc="first")
               .reindex(date_index)
               .astype("float32"))
        w.columns = pd.Index([str(c) for c in w.columns])
        w.index.name = "date"
        wide[k] = w

    # Ship only WIDE; the app recomputes YoY at boot. This keeps wide.pkl under GitHub's
    # 100 MB per-file hard limit (the full 3-dict bundle was ~101 MB).
    out = OPT / "wide.pkl"
    with open(out, "wb") as f:
        pickle.dump({"WIDE": wide}, f, protocol=5)
    print(f"wide.pkl written: pandas {pd.__version__}, {len(wide)} combos -> {out}")


if __name__ == "__main__":
    main()
