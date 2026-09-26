"""Semantta application and user-data paths."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "Semantta"

# In source/development mode, application resources live in the repository
# while mutable user data always lives in a separate top-level ``data`` tree.
# In a packaged/frozen build, user data is placed in the platform's standard
# per-user application-data directory instead.
IS_FROZEN = getattr(sys, "frozen", False)

if IS_FROZEN:
    APP_DIR = Path(
        getattr(
            sys,
            "_MEIPASS",
            Path(sys.executable).resolve().parent,
        )
    )
else:
    APP_DIR = Path(__file__).resolve().parent

PROJECT_DIR = APP_DIR.parent


def _platform_user_data_dir() -> Path:
    """Return the platform-appropriate per-user Semantta data directory."""
    if os.name == "nt":
        base = os.getenv("APPDATA")
        if base:
            return Path(base) / APP_NAME
        return Path.home() / "AppData" / "Roaming" / APP_NAME

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME

    base = os.getenv("XDG_DATA_HOME")
    if base:
        return Path(base) / APP_NAME
    return Path.home() / ".local" / "share" / APP_NAME


# Development and packaged installations use the same conceptual separation:
# APP_DIR contains application files; DATA_DIR contains mutable user data.
DATA_DIR = (
    PROJECT_DIR / "data"
    if not IS_FROZEN
    else _platform_user_data_dir()
)

ONTOLOGY_DIR = DATA_DIR / "ontologies"
METADATA_DIR = DATA_DIR / "metadata"
CACHE_DIR = DATA_DIR / "cache"
PLUGINS_DIR = DATA_DIR / "plugins"
THEMES_DIR = DATA_DIR / "themes"

INDEX_CACHE_FILE = CACHE_DIR / "_indexes.json"

STARS_FILE = DATA_DIR / "stars.json"
PREFERENCES_FILE = DATA_DIR / "preferences.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
PLUGINS_CONFIG_FILE = DATA_DIR / "plugins.json"
THEMES_CONFIG_FILE = DATA_DIR / "themes.json"
ACTIVE_THEME_FILE = DATA_DIR / "active-theme.json"

# Application-owned immutable resource.
OWL_FILE = APP_DIR / "vocab" / "owl.ttl"


def ensure_data_dirs() -> None:
    """Create the mutable Semantta data directories when necessary."""
    for directory in (
        DATA_DIR,
        ONTOLOGY_DIR,
        METADATA_DIR,
        CACHE_DIR,
        PLUGINS_DIR,
        THEMES_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)