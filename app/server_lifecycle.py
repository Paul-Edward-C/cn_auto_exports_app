"""Bokeh server lifecycle hooks.

Importing shared_data here runs its (one-time) heavy load — parquet read + index build +
world geometry — when the Bokeh server boots, rather than lazily on the first browser
session. So even the first visitor after a dyno restart gets the fast (~tens of ms) page
build instead of waiting ~1.5s.
"""


def on_server_loaded(server_context):
    import shared_data  # noqa: F401  (side effect: warm the process-wide data cache at boot)
