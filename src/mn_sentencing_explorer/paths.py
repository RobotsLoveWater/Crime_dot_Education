"""Canonical filesystem locations for the application.

All paths intentionally resolve to the repository's existing layout.  Centralizing
them makes commands independent of the caller's current working directory and gives
future instance-directory migrations one compatibility boundary without moving any
runtime data today.
"""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

CACHE_DIR = PROJECT_ROOT / "cache"
CACHE_DATA_DIR = CACHE_DIR / "data"
RAW_CSV_PATH = CACHE_DIR / "raw.csv"
RAW_PARQUET_PATH = CACHE_DIR / "raw.parquet"

USER_DIR = PROJECT_ROOT / "user"
CLASSES_DIR = PROJECT_ROOT / "classes"
LESSONS_DIR = PROJECT_ROOT / "content" / "lessons"

DATASET_PATH = PROJECT_ROOT / "dataset.sav"
RESOURCES_DIR = Path(__file__).resolve().parent / "resources"
CODEBOOK_PATH = RESOURCES_DIR / "codebook.xml"
SETTINGS_PATH = RESOURCES_DIR / "settings.xml"
STATIC_DIR = PROJECT_ROOT / "static"
TEMPLATES_DIR = PROJECT_ROOT / "templates"
