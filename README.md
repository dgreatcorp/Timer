# Keyboard Timer

A minimalist, fully offline Windows countdown timer controlled **entirely by the
keyboard** — no buttons, no menus, no mouse needed.

The countdown is shown as huge, **solid, extremely bold** white digits
(`MM:SS`) on a pure-black screen, using a heavy sans-serif (Arial Black, Impact,
…) — a clean high-end digital-clock look, **not** a seven-segment/LED style. An
optional real-time clock sits above or below the countdown.

## Features

- **Bold solid-digit countdown** in `MM:SS` on a `#000000` background.
  - The unit being adjusted (minutes / seconds) stays pure white while the other
    is a touch dimmer, so you can see what the arrows will change.
  - The `:` blinks while the timer runs.
- **TIMEUP alert** — when the countdown reaches zero the whole screen turns
  solid red with big bold white **TIMEUP** text. It
  stays until you press `Space` (restart) or `Delete`/`Enter` (reset). Resetting
  a finished timer returns it to the default **10:00**.
- **Real-time clock** (time + date only, no time-zone name) that can sit
  **above or below** the countdown. Press `F2` to flip Top ↔ Bottom; the choice
  is remembered.
- **Offline time zones** — `F1` opens a searchable picker with a curated list of
  major cities; you can also type any IANA id (e.g. `Europe/Berlin`).
- **Remembers everything** between sessions — countdown value, selected unit,
  time zone and clock position (stored in `%APPDATA%\KeyboardTimer\config.json`).
- **Double-click** anywhere on the window to toggle full screen.
- **Reliable start/pause** — `Space` starts and pauses the countdown, works
  after a reset, and restarts a finished timer. Auto-repeat is ignored so a held
  key can never double-toggle.
- Resizable window; fonts scale with the window. Fully offline, single exe.

## Keyboard controls

| Key | Action |
| --- | --- |
| `↑` / `↓` | Increase / decrease the selected unit (minutes or seconds) |
| `←` / `→` | Move the selection between minutes and seconds |
| `Space` | Start / pause (also restarts after TIMEUP) |
| `Delete` or `Enter` | Reset (after TIMEUP, resets to the default 10:00) |
| `F1` | Time zone picker — type to filter, `↑↓` select, `Enter` confirm, `Esc` cancel |
| `F2` | Move the real-time clock Top ↔ Bottom |
| `Esc` | Exit full screen (the app has no keyboard quit key) |

Seconds wrap `59 ↔ 0` (carrying into/out of minutes); minutes go up to `99`.

## Requirements

- Windows 10 or 11 (PyQt6 / Qt 6 requires Windows 10+).
- To **run from source**: Python 3.9 or newer.
- To **run the exe**: nothing at all — fully self-contained and offline.

## Run from source

```bat
python -m pip install -r requirements.txt
python main.py
```

## Build the single-file exe

Double-click **`build.bat`** (or run it from a terminal). It will:

1. install the build dependencies (`PyQt6`, `tzdata`, `PyInstaller`),
2. run the built-in self-test (`python main.py --smoke`),
3. produce **`dist\KeyboardTimer.exe`** — one file.

```bat
build.bat
```

Manual equivalent:

```bat
python -m pip install -r requirements-build.txt
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name KeyboardTimer --collect-data tzdata --collect-submodules tzdata ^
    --add-data "asset;asset" --icon "asset\timer.ico" main.py
```

The app icon comes from `asset\timer.ico` (generated from `asset\timer.png`).
Replace those files to change the icon, and it is embedded automatically when
you build.

**Install:** copy `dist\KeyboardTimer.exe` anywhere (Desktop, USB stick, another
PC) and double-click it. No admin rights, no internet, no installer.

## Project layout

```
Timer/
├── main.py                    # entry point
├── keyboard_timer/
│   ├── app.py                 # PyQt6 UI + all timer logic
│   ├── config.py              # JSON config load/save (%APPDATA%)
│   └── timezones.py           # offline zone list (zoneinfo + tzdata)
├── asset/
│   ├── timer.png              # source icon artwork
│   └── timer.ico              # app/exe icon
├── requirements.txt           # runtime deps
├── requirements-build.txt     # + PyInstaller
├── build.bat                  # one-click exe build
└── dist/KeyboardTimer.exe     # built application
```

## Self-test

```bat
python main.py --smoke
```

Runs the keyboard logic headlessly (offscreen) and exits with code `0` when all
checks pass — used by `build.bat` so a broken build never ships.

## Notes & troubleshooting

- **Config file:** `%APPDATA%\KeyboardTimer\config.json` — delete it to reset
  all settings.
- **Silent alert:** TIMEUP is visual only (the red screen); no sound is played.
- **"No match" in the zone picker:** type a valid IANA name instead, e.g.
  `Europe/Berlin` or `Asia/Kolkata`.
- Time zone data is embedded in the exe (`tzdata`), so offsets and DST are
  correct with no internet connection.
