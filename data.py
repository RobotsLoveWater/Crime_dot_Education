"""Compatibility alias for the packaged data-analysis engine."""

import sys

from src.mn_sentencing_explorer.analysis import data as _implementation

sys.modules[__name__] = _implementation
