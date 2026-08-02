"""Compatibility alias for the packaged Minnesota Offense Code data."""

import sys

from src.mn_sentencing_explorer.analysis import offense_codes as _implementation

sys.modules[__name__] = _implementation
