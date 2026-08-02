"""Compatibility alias and CLI entry point for the packaged cache engine."""

import sys

from src.mn_sentencing_explorer.analysis import cache as _implementation


if __name__ == "__main__":
    _implementation.main()
else:
    sys.modules[__name__] = _implementation
