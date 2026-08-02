"""Compatibility alias for the packaged learning-attempt analytics service."""

import sys

from src.mn_sentencing_explorer.services import analytics as _implementation

sys.modules[__name__] = _implementation
