"""Content fingerprint of the two parquets the app ships.

Two things make a naive comparison useless here. Parquet embeds creation metadata, so
rebuilding identical DATA still writes different bytes and `git diff` always reports a change.
And the builders are not bit-deterministic in floating point: a rebuild of unchanged inputs
moved exactly one of 2.4m `usd_per_unit` values by 1e-3 on a ~1.6e4 number, i.e. float32
rounding noise. An exact hash therefore never matches either.

So floats are rounded to six significant figures before hashing -- far more precision than
trade values carry, and enough to make the fingerprint stable across rebuilds while still
catching any real revision. Identical output means the app would ship identical data.
"""
import numpy as np
import pandas as pd

SIGFIG = 6


def stable(df):
    """Copy with float columns rounded to SIGFIG significant figures."""
    out = df.copy()
    for c in out.columns:
        if out[c].dtype.kind != 'f':
            continue
        finite = np.abs(out[c].to_numpy(dtype='float64'))
        finite = finite[np.isfinite(finite) & (finite > 0)]
        mag = int(np.floor(np.log10(finite.max()))) if finite.size else 0
        out[c] = out[c].round(max(0, SIGFIG - 1 - mag))
    return out


for path in ('app/data/auto_long.parquet', 'app/data/cn_long.parquet'):
    try:
        d = pd.read_parquet(path)
    except Exception as exc:                      # a missing file counts as "different"
        print(f'{path}\tMISSING\t{exc}')
        continue
    h = int(pd.util.hash_pandas_object(stable(d), index=True).sum() % (2 ** 63))
    print(f'{path}\t{len(d)}\t{d.shape[1]}\t{h}')
