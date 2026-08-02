"""Stable Flask/WSGI entry point for the packaged application.

Existing commands such as ``flask --app app run`` and ``gunicorn app:app`` keep
working while the implementation lives under ``src/mn_sentencing_explorer``.
"""

import sys

from src.mn_sentencing_explorer import application as _implementation

sys.modules[__name__] = _implementation
