"""Compatibility entry point for the relocated base-data regression suite."""

import sys

from tests.regression.test_base_immutability import main


if __name__ == "__main__":
    sys.exit(main())
