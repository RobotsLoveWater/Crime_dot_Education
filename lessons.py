"""Compatibility alias for the packaged lesson service."""

import sys

from src.mn_sentencing_explorer.services import lessons as _implementation

sys.modules[__name__] = _implementation
