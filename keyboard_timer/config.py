"""Tiny JSON config persistence.

The configuration file lives in ``%APPDATA%\\KeyboardTimer\\config.json`` so the
last countdown value (MM:SS), real-time clock position and time zone survive
between launches without admin rights or an installer.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict

APP_FOLDER = "KeyboardTimer"

DEFAULTS: Dict[str, Any] = {
    "minutes": 10,
    "seconds": 0,
    "timezone": "LOCAL",
    "selected_unit": 0,       # 0 = minutes, 1 = seconds
    "clock_position": "top",  # "top" or "bottom"
    "hint_shown": False,
}

CLOCK_POSITIONS = ("top", "bottom")


def config_dir() -> str:
    """Return the folder that holds the config file (creating nothing yet)."""
    base = os.environ.get("APPDATA")
    if not base:  # very unusual, but keep working
        base = os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, APP_FOLDER)


def config_path() -> str:
    return os.path.join(config_dir(), "config.json")


def _clamp_int(value: Any, low: int, high: int, default: int) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, value))


def sanitize(data: Dict[str, Any]) -> Dict[str, Any]:
    """Merge unknown/partial/legacy data into a valid configuration dict."""
    out = dict(DEFAULTS)
    if not isinstance(data, dict):
        return out

    minutes = _clamp_int(data.get("minutes"), 0, 99, DEFAULTS["minutes"])
    seconds = _clamp_int(data.get("seconds"), 0, 59, DEFAULTS["seconds"])

    # Older versions stored HH:MM:SS - fold hours into minutes (cap 99).
    hours = _clamp_int(data.get("hours", 0), 0, 99, 0)
    out["minutes"] = min(99, minutes + hours * 60)
    out["seconds"] = seconds

    tz_name = data.get("timezone")
    out["timezone"] = tz_name if isinstance(tz_name, str) and tz_name else "LOCAL"

    # Countdown has only two units now: minutes and seconds.
    out["selected_unit"] = _clamp_int(data.get("selected_unit"), 0, 1, 0)

    # The clock only supports top / bottom in this version.
    position = data.get("clock_position")
    out["clock_position"] = position if position in CLOCK_POSITIONS else "top"

    out["hint_shown"] = bool(data.get("hint_shown", False))
    return out


def load_config() -> Dict[str, Any]:
    """Read the config file; fall back to defaults if missing or corrupt."""
    try:
        with open(config_path(), "r", encoding="utf-8") as fh:
            return sanitize(json.load(fh))
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save_config(config: Dict[str, Any]) -> None:
    """Atomically write the config file (best effort, never raises)."""
    try:
        os.makedirs(config_dir(), exist_ok=True)
        path = config_path()
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(sanitize(config), fh, indent=2)
        os.replace(tmp, path)
    except OSError:
        pass
