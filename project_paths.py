"""Compatibility alias for :mod:`src.mn_sentencing_explorer.paths`."""

import sys

from src.mn_sentencing_explorer import paths as _implementation

sys.modules[__name__] = _implementation
