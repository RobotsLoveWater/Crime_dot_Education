"""Compatibility alias for the packaged geography helpers."""

import sys

from src.mn_sentencing_explorer.analysis import geo as _implementation

sys.modules[__name__] = _implementation
