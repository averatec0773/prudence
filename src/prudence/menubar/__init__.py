"""The menu-bar prototype: a thin `rumps` shell around the store.

`summary.py` computes the numbers shown and is plain Python, importable and testable on
any platform. `app.py` imports `rumps`, which only installs on macOS, so nothing else in
Prudence ever imports this package.
"""

from __future__ import annotations
