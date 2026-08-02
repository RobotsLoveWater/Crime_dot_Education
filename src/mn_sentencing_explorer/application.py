"""Compatibility alias for the web application implementation."""

import sys

from .web import application as _implementation

sys.modules[__name__] = _implementation
