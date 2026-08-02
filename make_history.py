"""Compatibility alias for the packaged filter-history builders."""

import sys

from src.mn_sentencing_explorer.analysis import history as _implementation

sys.modules[__name__] = _implementation
