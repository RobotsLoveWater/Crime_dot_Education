"""Interactive runtime-data build entry point.

The historical ``python cache.py`` command remains supported; this wrapper gives
operational scripts a dedicated home without duplicating cache-building behavior.
"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cache import main


if __name__ == "__main__":
    main()
