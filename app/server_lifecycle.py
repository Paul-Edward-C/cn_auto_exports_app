"""Bokeh server lifecycle hooks.

Importing the shared_data modules here runs their one-time heavy loads — parquet reads,
MultiIndex builds, world geometry — when the Bokeh server boots, rather than lazily on
the first browser session. So even the first visitor after a dyno restart gets the fast
page build instead of waiting for both parquets to load.
"""
import sys
from pathlib import Path


def on_server_loaded(server_context):
    # Lifecycle hooks run before the per-session script handler puts the app dir on
    # sys.path, so we add it here. Then warm all three process-wide data modules.
    app_dir = str(Path(__file__).parent)
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)
    import shared_data        # noqa: F401  (constants + world geometry)
    import shared_data_cn     # noqa: F401  (China parquet + MultiIndex)
    import shared_data_auto   # noqa: F401  (Auto parquet + MultiIndex)
