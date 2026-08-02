"""Compatibility alias for the packaged classroom service."""

import sys

from src.mn_sentencing_explorer.services import classroom as _implementation

sys.modules[__name__] = _implementation
