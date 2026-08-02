"""Compatibility alias for the packaged account service."""

import sys

from src.mn_sentencing_explorer.services import account as _implementation

sys.modules[__name__] = _implementation
