"""Compatibility entry point for the relocated map/filter regression suite."""

import sys

from tests.regression.test_map_filter_equivalence import main


if __name__ == "__main__":
    sys.exit(main())
