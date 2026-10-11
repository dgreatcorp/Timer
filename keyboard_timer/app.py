"""Keyboard Timer - PyQt6 user interface and application logic.

Visual design
-------------
Pure black (#000000) screen with huge, SOLID, extremely bold white digits in an
MM:SS countdown.  The digits use a heavy sans-serif ("Arial Black", "Impact",
...), *not* a seven-segment / LED style.  The real-time clock (time + date) sits
above or below the countdown and can be flipped with F2.  There are no buttons,
menus or toolbars - everything is keyboard driven.

The countdown is started and paused with the Space bar, which is handled manually
in ``keyPressEvent`` (never through an accelerator) and ignores the operating
system's key auto-repeat, so the first press always starts and the second always
pauses - reliably, every time, even right after a reset or at 00:00.
"""

from __future__ import annotations

import os
import sys
import time
import traceback

from PyQt6.QtCore import QEvent, QSize, Qt, QTimer
from PyQt6.QtGui import QFont, QFontDatabase, QIcon, QKeyEvent
from PyQt6.QtWidgets import (
    QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QVBoxLayout, QWidget,
)

from . import APP_NAME, timezones as tz
from .config import DEFAULTS, load_config, save_config

# --- Theme -----------------------------------------------------------------
BG = "#000000"          # pure black background
FG = "#FFFFFF"          # pure white digits
FG_OFF = "#B4B4B4"      # the non-selected unit (slightly dimmed, still white-ish)
RED_BG = "#FF0000"      # TIMEUP background
RED_FG = "#FFFFFF"      # TIMEUP text
MUTED = "#8A8A8A"       # date / hints

UI_FONT = "Segoe UI"
PICKER_MAX_ROWS = 8

# Heavy, solid fonts in order of preference.  All are non-segmented; whichever
# is installed first is used for the digits.
DIGIT_FONTS = (
    "Arial Black",
    "Impact",
    "Segoe UI Black",
    "Roboto Black",
    "Montserrat Black",
    "Segoe UI",
    "Arial",
)

# Keyboard controls mapped once and shared by keyPressEvent and the application
# wide event filter, so keys work no matter which child widget has focus.
KEY_MAP = {
    Qt.Key.Key_Up: "Up", Qt.Key.Key_Down: "Down",
    Qt.Key.Key_Left: "Left", Qt.Key.Key_Right: "Right",
    Qt.Key.Key_Space: "space", Qt.Key.Key_Delete: "Delete",
    Qt.Key.Key_Return: "Return", Qt.Key.Key_Enter: "Return",
    Qt.Key.Key_Escape: "Escape",
    Qt.Key.Key_F1: "F1", Qt.Key.Key_F2: "F2",
}


def mmss_to_ms(minutes: int, seconds: int) -> float:
    """Convert minutes/seconds to milliseconds."""
    return float((minutes * 60 + seconds) * 1000)


def ms_to_mmss(total_seconds: int):
    """Split whole seconds into (minutes, seconds)."""
    return total_seconds // 60, total_seconds % 60


# The default countdown, shown on first run and when a finished (TIMEUP) timer
# is reset.  Derived from the config defaults so the two stay in sync.
DEFAULT_MS = mmss_to_ms(DEFAULTS["minutes"], DEFAULTS["seconds"])


def pick_digit_family() -> str:
    """Return the first installed heavy font from ``DIGIT_FONTS``."""
    try:
        available = set(QFontDatabase.families())
    except Exception:
        available = set()
    for name in DIGIT_FONTS:
        if name in available:
            return name
    return "Arial"


class ScaledLabel(QLabel):
    """A QLabel whose font is scaled by the parent.

    Its *minimum* size is reported as zero so the big fonts can never inflate
    the window's minimum size, while its *preferred* size still follows the
    text so the layout can centre it normally.
    """

    def minimumSizeHint(self):  # noqa: N802
        return QSize(0, 0)


class TimerApp(QWidget):
    """The whole user interface and application logic."""

    def __init__(self, config, smoke=False):
        super().__init__()
        self.config = config
        self.smoke = smoke

        self.unit = int(config.get("selected_unit", 0)) % 2
        self.set_ms = mmss_to_ms(config.get("minutes", 5), config.get("seconds", 0))
        self.remaining_ms = self.set_ms
        self.running = False
        self.timeup = False
        self.deadline = 0.0
        self.clock_pos = config.get("clock_position", "top")
        self.tz_key = config.get("timezone", "LOCAL")
        self.last_clock = ""
        self.colon_on = True
        self.hint_shown = bool(config.get("hint_shown", False))
        self._picker_results = []
        self._status_token = 0

        self.setObjectName("root")
        self.setWindowTitle(APP_NAME)
        self.setStyleSheet(f"#root {{ background-color: {BG}; }}")
        # A top-level QWidget defaults to NoFocus, which means it would never
        # receive keyPressEvent and Space would appear to do nothing.  Force
        # keyboard focus so the whole window reacts to the keyboard.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Build the font objects.  The digit font is the important one.
        self.digit_family = pick_digit_family()
        self.f_digit = QFont(self.digit_family)
        self.f_digit.setWeight(QFont.Weight.Black)
        self.f_digit.setBold(True)
        self.f_time = QFont(UI_FONT)
        self.f_time.setWeight(QFont.Weight.Bold)
        self.f_date = QFont(UI_FONT)
        self.f_timeup = QFont(self.digit_family)
        self.f_timeup.setWeight(QFont.Weight.Black)
        self.f_timeup.setBold(True)

        self._build_ui()
        self._build_picker()
        self._apply_sizes()
        self._apply_theme()
        self._render_countdown()
        self._place_clock()

        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start(100)

        if not smoke and not self.hint_shown:
            self._set_status(
                "Space start / pause     Delete reset     F1 timezone     F2 clock",
                8000,
            )
            self.hint_shown = True

    # --- construction ------------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Holders for the clock, so it can be moved above/below the countdown.
        self.top_holder = QWidget(self)
        top = QVBoxLayout(self.top_holder)
        top.setContentsMargins(0, 0, 0, 0)
        self.bottom_holder = QWidget(self)
        bottom = QVBoxLayout(self.bottom_holder)
        bottom.setContentsMargins(0, 0, 0, 0)

        # The clock bar (time + date only - no time-zone name).
        self.clock_bar = QFrame(self)
        self.clock_bar.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        bar = QVBoxLayout(self.clock_bar)
        bar.setContentsMargins(18, 6, 18, 2)
        bar.setSpacing(0)
        self.time_lbl = ScaledLabel("", self.clock_bar)
        self.time_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.date_lbl = ScaledLabel("", self.clock_bar)
        self.date_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.date_lbl.setStyleSheet(f"color: {MUTED};")
        bar.addWidget(self.time_lbl)
        bar.addWidget(self.date_lbl)

        # Middle: the big countdown digits, with the TIMEUP overlay in the same
        # cell so it appears centred over the whole area.
        self.middle = QWidget(self)
        mg = QGridLayout(self.middle)
        mg.setContentsMargins(0, 0, 0, 0)
        mg.setSpacing(0)

        digits = QWidget(self.middle)
        row = QHBoxLayout(digits)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.min_lbl = ScaledLabel("00", digits)
        self.colon_lbl = ScaledLabel(":", digits)
        self.sec_lbl = ScaledLabel("00", digits)
        for label in (self.min_lbl, self.colon_lbl, self.sec_lbl):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addStretch(1)
        row.addWidget(self.min_lbl)
        row.addWidget(self.colon_lbl)
        row.addWidget(self.sec_lbl)
        row.addStretch(1)
        self.digits = digits
        self.digits.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self.timeup_lbl = ScaledLabel("TIMEUP", self.middle)
        self.timeup_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.timeup_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.timeup_lbl.hide()

        mg.addWidget(self.digits, 0, 0)
        mg.addWidget(self.timeup_lbl, 0, 0)
        mg.setRowStretch(0, 1)
        mg.setColumnStretch(0, 1)

        self.status_lbl = QLabel("", self)
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_lbl.setStyleSheet(f"color: {MUTED};")

        root.addWidget(self.top_holder, 0)
        root.addWidget(self.middle, 1)
        root.addWidget(self.bottom_holder, 0)
        root.addWidget(self.status_lbl, 0)

    def _build_picker(self):
        self.picker = QFrame(self)
        self.picker.setObjectName("pickerCard")
        self.picker.setStyleSheet(
            "#pickerCard { background-color: #1E1E1E; border: 1px solid #3A3A3A;"
            " border-radius: 10px; }"
            "#pickerCard QLabel { color: #FFFFFF; }"
        )
        self.picker.setFixedWidth(520)
        card = QVBoxLayout(self.picker)
        card.setContentsMargins(20, 14, 20, 14)
        card.setSpacing(10)

        self.tz_edit = QLineEdit(self.picker)
        self.tz_edit.setPlaceholderText("Type a city or time zone")
        self.tz_edit.setStyleSheet(
            "QLineEdit { background:#141414; color:#FFFFFF; border:1px solid #3A3A3A;"
            " border-radius:6px; padding:8px 10px; font-size:14pt; }"
        )
        self.tz_edit.textChanged.connect(self._refresh_results)
        card.addWidget(self.tz_edit)

        self.tz_list = QListWidget(self.picker)
        self.tz_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.tz_list.setStyleSheet(
            "QListWidget { background:transparent; border:none; }"
            "QListWidget::item { min-height:30px; border-radius:6px; }"
            "QListWidget::item:selected { background:#4FC3F7; color:#000000; }"
        )
        card.addWidget(self.tz_list)

        hint = QLabel("Up/Down select      Enter confirm      Esc cancel", self.picker)
        hint.setFont(QFont(UI_FONT, 9))
        hint.setStyleSheet(f"color: {MUTED};")
        card.addWidget(hint)

        self.picker.hide()

    # --- layout / theme ----------------------------------------------------
    def _place_clock(self):
        self.clock_bar.setParent(None)
        holder = self.top_holder if self.clock_pos == "top" else self.bottom_holder
        holder.layout().addWidget(self.clock_bar)
        self.clock_bar.show()

    def _apply_theme(self):
        alarm = self.timeup
        self.setStyleSheet(f"#root {{ background-color: {RED_BG if alarm else BG}; }}")
        self.time_lbl.setStyleSheet(f"color: {RED_FG if alarm else FG};")
        self.date_lbl.setStyleSheet(f"color: {'#FFD9D9' if alarm else MUTED};")
        self.status_lbl.setStyleSheet(f"color: {'#FFD9D9' if alarm else MUTED};")
        self.digits.setVisible(not alarm)
        self.timeup_lbl.setVisible(alarm)
        self.timeup_lbl.setStyleSheet("color: #FFFFFF;")

    def _apply_sizes(self):
        """Scale every font to the current window size."""
        mw = max(self.middle.width(), 1)
        mh = max(self.middle.height(), 1)
        # Digits must fit both the height and the width of the middle area.
        digit_px = max(40, int(min(mh * 0.80, mw / 3.2)))
        self.f_digit.setPixelSize(digit_px)
        # "TIMEUP" is a long word, so it is sized to fit across the width too.
        self.f_timeup.setPixelSize(max(40, int(min(mh * 0.72, mw / 4.6))))
        self.f_time.setPixelSize(max(32, int(self.height() * 0.14)))
        self.f_date.setPixelSize(max(16, int(self.height() * 0.05)))
        for label in (self.min_lbl, self.colon_lbl, self.sec_lbl):
            label.setFont(self.f_digit)
        self.time_lbl.setFont(self.f_time)
        self.date_lbl.setFont(self.f_date)
        self.timeup_lbl.setFont(self.f_timeup)
        self.time_lbl.setFont(self.f_time)
        self.date_lbl.setFont(self.f_date)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._apply_sizes()
        if self.picker.isVisible():
            self._center_picker()

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        self.raise_()
        self.activateWindow()
        self.setFocus()

    def mousePressEvent(self, event):  # noqa: N802
        self.setFocus()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):  # noqa: N802
        # Double-click toggles full screen; the fonts rescale via resizeEvent.
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()
        self.setFocus()
        super().mouseDoubleClickEvent(event)

    def closeEvent(self, event):  # noqa: N802
        self._save()
        super().closeEvent(event)

    # --- ticking / rendering ----------------------------------------------
    def _tick(self):
        try:
            self._update_clock()
            if self.timeup:
                return
            if self.running:
                self.remaining_ms = max(
                    0.0, (self.deadline - time.monotonic()) * 1000.0
                )
                if self.remaining_ms <= 0:
                    self._trigger_timeup()
                    return
                self._render_countdown()
                self._set_colon(int(time.monotonic() * 2) % 2 == 0)
            else:
                self._set_colon(True)
        except Exception:  # pragma: no cover - never let the UI die
            traceback.print_exc()

    def _update_clock(self):
        dt = tz.now_for(self.tz_key)
        text = dt.strftime("%H:%M:%S")
        if text != self.last_clock:
            self.last_clock = text
            self.time_lbl.setText(text)
            self.date_lbl.setText(tz.format_date(dt))

    def _render_countdown(self):
        m, s = ms_to_mmss(int(round(self.remaining_ms / 1000)))
        self.min_lbl.setText(f"{m:02d}")
        self.sec_lbl.setText(f"{s:02d}")
        # While paused, the selected unit stays pure white and the other is a
        # touch dimmer, so the user can see what the arrows will change.
        editing = not self.running and not self.timeup
        self.min_lbl.setStyleSheet(
            f"color: {FG if (not editing or self.unit == 0) else FG_OFF};"
        )
        self.sec_lbl.setStyleSheet(
            f"color: {FG if (not editing or self.unit == 1) else FG_OFF};"
        )

    def _set_colon(self, on: bool):
        self.colon_on = on
        self.colon_lbl.setStyleSheet(f"color: {FG if on else FG_OFF};")

    # --- status line -------------------------------------------------------
    def _set_status(self, text: str, timeout_ms: int = 0):
        self.status_lbl.setText(text)
        self._status_token += 1
        token = self._status_token
        if timeout_ms:
            QTimer.singleShot(timeout_ms, lambda: self._clear_status(token))

    def _clear_status(self, token: int):
        if token == self._status_token:
            self.status_lbl.setText("")

    # --- key handling ------------------------------------------------------
    def handle_key(self, name: str):
        if name == "Escape":
            # Esc only leaves full screen - no key ever exits the app.
            if self.isFullScreen():
                self.showNormal()
        elif name == "F1":
            self._toggle_picker()
        elif name == "F2":
            self.clock_pos = "bottom" if self.clock_pos == "top" else "top"
            self._place_clock()
            self._set_status("Clock moved to the " + self.clock_pos, 1500)
            self._save()
        elif name == "space":
            self._toggle()
        elif name in ("Delete", "Return"):
            self._reset()
        elif self.timeup or self.running:
            return
        elif name == "Up":
            self._adjust(+1)
        elif name == "Down":
            self._adjust(-1)
        elif name in ("Left", "Right"):
            self.unit = (self.unit + (1 if name == "Right" else -1)) % 2
            self._render_countdown()
            self._save()

    def _adjust(self, delta: int):
        m, s = ms_to_mmss(int(round(self.set_ms / 1000)))
        if self.unit == 0:
            m = max(0, min(99, m + delta))
        else:
            s += delta
            if s > 59:
                s, m = 0, min(99, m + 1)
            elif s < 0:
                s, m = 59, max(0, m - 1)
        self.set_ms = mmss_to_ms(m, s)
        self.remaining_ms = self.set_ms
        self._render_countdown()
        self._save()

    def _toggle(self):
        """Space action: start, pause, or restart after TIMEUP."""
        if self.timeup:
            self.timeup = False
            self._apply_theme()
            self.remaining_ms = self.set_ms
            self.running = True
            self.deadline = time.monotonic() + self.remaining_ms / 1000.0
            self._render_countdown()
        elif self.running:
            self.running = False
            self._set_colon(True)
        elif self.remaining_ms > 0:
            self.running = True
            self.deadline = time.monotonic() + self.remaining_ms / 1000.0
            self._render_countdown()

    def _reset(self):
        self.running = False
        if self.timeup:
            # Resetting a finished timer returns to the default countdown
            # (10:00) rather than the value it just finished from.
            self.set_ms = DEFAULT_MS
            self.timeup = False
        self.remaining_ms = self.set_ms
        self._apply_theme()
        self._render_countdown()
        self._set_colon(True)
        self._save()

    def _trigger_timeup(self):
        self.running = False
        self.timeup = True
        self.remaining_ms = 0.0
        self._apply_theme()
        self._play_beep()

    def _play_beep(self):
        """Short system beep (Windows only; silently skipped elsewhere)."""
        if self.smoke:
            return
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONHAND)
        except Exception:
            pass

    def _save(self):
        if self.smoke:
            return
        m, s = ms_to_mmss(int(round(self.set_ms / 1000)))
        save_config({
            "minutes": m,
            "seconds": s,
            "timezone": self.tz_key,
            "selected_unit": self.unit,
            "clock_position": self.clock_pos,
            "hint_shown": self.hint_shown,
        })

    # --- time zone picker --------------------------------------------------
    def _refresh_results(self):
        self._picker_results = tz.search(self.tz_edit.text())[:PICKER_MAX_ROWS]
        self.tz_list.clear()
        if not self._picker_results:
            item = QListWidgetItem("No match - try another spelling")
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.tz_list.addItem(item)
        for zone in self._picker_results:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, zone)
            item.setSizeHint(QSize(0, 30))
            self.tz_list.addItem(item)
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(10, 0, 10, 0)
            layout.addWidget(QLabel(zone.name, row))
            layout.addStretch(1)
            offset = QLabel(tz.offset_label(zone.key), row)
            offset.setStyleSheet(f"color: {MUTED};")
            layout.addWidget(offset)
            self.tz_list.setItemWidget(item, row)
        if self._picker_results:
            self.tz_list.setCurrentRow(0)
        if self.picker.isVisible():
            self._center_picker()

    def _toggle_picker(self):
        if self.picker.isVisible():
            self._close_picker()
        else:
            self.tz_edit.clear()
            self.picker.show()
            self.picker.raise_()
            self._center_picker()
            self.tz_edit.setFocus()

    def _close_picker(self):
        self.picker.hide()
        self.setFocus()

    def _center_picker(self):
        self.picker.adjustSize()
        x = max(0, (self.width() - self.picker.width()) // 2)
        y = max(0, (self.height() - self.picker.height()) // 2)
        self.picker.move(x, y)

    def _move_list(self, delta: int):
        count = self.tz_list.count()
        if not count:
            return
        self.tz_list.setCurrentRow((self.tz_list.currentRow() + delta) % count)

    def _apply_current(self):
        item = self.tz_list.currentItem()
        zone = item.data(Qt.ItemDataRole.UserRole) if item else None
        if zone is None:
            return
        self.tz_key = zone.key
        self.last_clock = ""
        self._update_clock()
        self._close_picker()
        self._save()

    # --- Qt event overrides ------------------------------------------------
    def _dispatch_key_event(self, event) -> bool:
        """Route a key press to handle_key.  Returns True if it was consumed."""
        name = KEY_MAP.get(event.key())
        if name is None:
            return False
        # Ignore OS key auto-repeat for the action keys.  This is what makes
        # Space reliable: holding it can never toggle start/pause twice.
        if event.isAutoRepeat() and name not in ("Up", "Down"):
            return True
        try:
            self.handle_key(name)
        except Exception:  # pragma: no cover
            traceback.print_exc()
        return True

    def keyPressEvent(self, event):  # noqa: N802
        if not self._dispatch_key_event(event):
            super().keyPressEvent(event)
        else:
            event.accept()

    def eventFilter(self, obj, event):  # noqa: N802
        # This filter is installed on the QApplication (see run()), so it sees
        # every key press.  That guarantees the shortcuts work even if some
        # child widget happens to hold focus.
        if event.type() == QEvent.Type.KeyPress:
            if obj is self.tz_edit:
                key = event.key()
                try:
                    if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                        self._apply_current()
                        return True
                    if key in (Qt.Key.Key_Escape, Qt.Key.Key_F1):
                        self._close_picker()
                        return True
                    if key == Qt.Key.Key_Up:
                        self._move_list(-1)
                        return True
                    if key == Qt.Key.Key_Down:
                        self._move_list(+1)
                        return True
                except Exception:  # pragma: no cover
                    traceback.print_exc()
                return False  # let the line edit handle typing normally
            if not self.picker.isVisible() and self._dispatch_key_event(event):
                return True
        return super().eventFilter(obj, event)

    # --- smoke test --------------------------------------------------------
    def start_smoke(self):
        self._checks = []
        steps = [
            (0, self._smoke_defaults),
            (0, self._smoke_editing),
            (0, self._smoke_countdown),
            (1400, self._smoke_timeup),
            (0, self._smoke_restart_reset),
            (0, self._smoke_toggle_repeat),
            (0, self._smoke_picker),
            (0, self._smoke_positions),
            (0, self._smoke_escape),
            (0, self._smoke_resize),
            (0, self._finish_smoke),
        ]

        def run_from(index):
            if index >= len(steps):
                return
            delay, step = steps[index]
            QTimer.singleShot(delay, lambda: (step(), run_from(index + 1)))

        run_from(0)

    def _check(self, name: str, ok: bool):
        self._checks.append((name, bool(ok)))

    def _smoke_defaults(self):
        QApplication.processEvents()
        self._check("Window accepts keyboard focus",
                    self.focusPolicy() == Qt.FocusPolicy.StrongFocus)
        self._check("Default time is 10:00",
                    self.set_ms == mmss_to_ms(10, 0)
                    and self.remaining_ms == mmss_to_ms(10, 0))
        self._check("Countdown digits are laid out",
                    self.min_lbl.isVisible() and self.min_lbl.width() > 0
                    and self.sec_lbl.width() > 0)

    def _smoke_editing(self):
        self.remaining_ms = self.set_ms = mmss_to_ms(5, 0)
        self.unit = 0
        self._render_countdown()
        self.handle_key("Up")
        self._check("Up adds a minute", self.set_ms == mmss_to_ms(6, 0))
        self.handle_key("Down")
        self.handle_key("Down")
        self._check("Down subtracts a minute", self.set_ms == mmss_to_ms(4, 0))
        self.remaining_ms = self.set_ms = mmss_to_ms(0, 1)
        self.handle_key("Right")
        self._check("Right selects seconds", self.unit == 1)
        self.handle_key("Up")
        self._check("Up adds a second", self.set_ms == mmss_to_ms(0, 2))

    def _smoke_countdown(self):
        self.set_ms = self.remaining_ms = mmss_to_ms(0, 1)
        self.handle_key("space")
        self._check("Space starts", self.running)

    def _smoke_timeup(self):
        self._check("Reaches TIMEUP", self.timeup)
        self._check("Digits hidden at TIMEUP", not self.digits.isVisible())
        self._check("TIMEUP label shown", self.timeup_lbl.isVisible())

    def _smoke_restart_reset(self):
        # The timer reached TIMEUP in the previous step with a 1 second value.
        self.handle_key("Delete")
        self._check("Reset after TIMEUP restores default 10:00",
                    not self.timeup and self.set_ms == DEFAULT_MS
                    and self.remaining_ms == DEFAULT_MS)
        # Space restarts a finished timer.
        self.remaining_ms = 0.0
        self._trigger_timeup()
        self.handle_key("space")
        self._check("Space restarts after TIMEUP",
                    self.running and not self.timeup)
        # Space toggles start / pause reliably.
        self.handle_key("space")
        self._check("Space pauses", not self.running)
        self.handle_key("space")
        self._check("Space starts again", self.running)
        # Delete resets to the last set value.
        self.handle_key("Delete")
        self._check("Delete resets",
                    not self.running and self.remaining_ms == self.set_ms)

    def _smoke_toggle_repeat(self):
        # A held key produces auto-repeat events, which must be ignored so the
        # start/pause toggle fires exactly once per physical press.
        self.running = False
        self.timeup = False
        self.set_ms = self.remaining_ms = mmss_to_ms(0, 5)
        self._render_countdown()
        repeat = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space,
                           Qt.KeyboardModifier.NoModifier, "", True)
        self.keyPressEvent(repeat)
        self._check("Auto-repeat is ignored", not self.running)
        normal = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space,
                           Qt.KeyboardModifier.NoModifier, "", False)
        self.keyPressEvent(normal)
        self._check("Real Space starts", self.running)
        self.keyPressEvent(normal)
        self._check("Real Space pauses", not self.running)
        self.handle_key("Return")

    def _smoke_picker(self):
        self.handle_key("F1")
        self._check("F1 opens picker", self.picker.isVisible())
        self.tz_edit.setText("tokyo")
        self._apply_current()
        self._check("Picker applies zone", self.tz_key == "Asia/Tokyo")

    def _smoke_positions(self):
        self.handle_key("F2")
        self._check("F2 moves clock down", self.clock_pos == "bottom")
        self.handle_key("F2")
        self._check("F2 moves clock up", self.clock_pos == "top")

    def _smoke_escape(self):
        self.handle_key("Escape")
        self._check("Esc does not exit the app", self.isVisible() and not self.isFullScreen())

    def _smoke_resize(self):
        before = self.f_time.pixelSize()
        self.resize(self.width() + 240, self.height() + 240)
        QApplication.processEvents()
        self._check("Fonts scale on resize", self.f_time.pixelSize() != before)

    def _finish_smoke(self):
        passed = sum(1 for _, ok in self._checks if ok)
        total = len(self._checks)
        print(f"Smoke test: {passed}/{total} passed")
        for name, ok in self._checks:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
        self.smoke_code = 0 if passed == total else 1
        QApplication.instance().quit()


def _resource_path(*parts):
    """Locate a bundled asset both when running from source and from the exe."""
    base = getattr(sys, "_MEIPASS",
                   os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, *parts)


def app_icon():
    """Return the application icon from the bundled asset (or an empty icon)."""
    for name in ("timer.ico", "timer.png"):
        path = _resource_path("asset", name)
        if os.path.exists(path):
            return QIcon(path)
    return QIcon()


def run(argv=None) -> int:
    """Application entry point.  Returns a process exit code."""
    args = sys.argv[1:] if argv is None else list(argv)
    smoke = "--smoke" in args
    if smoke:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(app_icon())

    config = dict(DEFAULTS) if smoke else load_config()
    window = TimerApp(config, smoke=smoke)
    window.resize(1100, 640)
    # Capture every key at the application level so the shortcuts always work,
    # regardless of which (if any) child widget has focus.
    app.installEventFilter(window)
    window.show()

    if smoke:
        window.smoke_code = 1
        QTimer.singleShot(200, window.start_smoke)
    else:
        window.raise_()
        window.activateWindow()
        window.setFocus()
        QTimer.singleShot(0, window.raise_)
        QTimer.singleShot(0, window.activateWindow)
        QTimer.singleShot(0, window.setFocus)

    app.exec()
    return getattr(window, "smoke_code", 0) if smoke else 0
