"""Compatibility alias for the packaged security and formatting helpers."""

import sys

from src.mn_sentencing_explorer import security as _implementation

sys.modules[__name__] = _implementation
