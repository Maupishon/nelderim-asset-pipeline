#!/usr/bin/env python3
"""
uop_probe.py - compatibility shim.

uopatch.py and vd_inject.py both optionally import `read_uop_hashes` and
`uop_hash` from a module named `uop_probe` to check AnimationFrame*.uop
collisions before picking a target id. This file exists so that check is
never silently skipped just because a separately-authored uop_probe.py
isn't present.

It does not reimplement anything - it re-exports the exact same,
already-verified functions from nelderim_core.py (the ones used
everywhere else in this repo: uop_gump_patch.py, nelderim_search.py,
nelderim_patch.py). Keeping a single implementation avoids the two-
copies-quietly-drift problem.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nelderim_core import uop_hash, read_uop_hashes  # noqa: E402,F401
