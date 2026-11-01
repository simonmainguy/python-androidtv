"""Run pure library and shell-replay tests without ADB transport dependencies.

Normal development environments can use pytest instead. This runner imports the
real production modules under a namespace package, bypassing only androidtv's
eager __init__ imports of unavailable ADB/network packages. It never connects
to a device and does not replace or modify any library source.
"""

import importlib
from pathlib import Path
import sys
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Pure modules can be tested without importing the sync transport at package root.
PACKAGE = types.ModuleType("androidtv")
PACKAGE.__path__ = [str(ROOT / "androidtv")]
sys.modules["androidtv"] = PACKAGE

SUITE = unittest.TestSuite()
for module_name in (
    "tests.test_constants",
    "tests.test_basetv",
    "tests.test_sony_android10",
    "tests.test_sony_audio_state",
):
    SUITE.addTests(unittest.defaultTestLoader.loadTestsFromModule(importlib.import_module(module_name)))

RESULT = unittest.TextTestRunner(verbosity=2).run(SUITE)
sys.exit(0 if RESULT.wasSuccessful() else 1)
