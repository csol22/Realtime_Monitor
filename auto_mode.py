"""
auto_mode.py  –  Automatic test-mode detection for CHx2000 Realtime Flow Monitor.

Detection runs on a background thread every 3 seconds.
Registers polled (in a single batch):
    39  – P31 speed %   (SPEED_SCALE = 1)
    40  – P41 speed %   (SPEED_SCALE = 1)
    35  – Actual Secondary DP (raw / 10 → psi)
   201  – Secondary DP Setpoint (raw / 10 → psi)

Detection priority (first rule that matches wins):
  1. P31 100% Pump Test   : P31 > 70, P41 == 0
  2. P41 100% Pump Test   : P31 == 0, P41 > 70
  3. 15DP Test  : P31 = 58±2, P41 = 58±2, actual_dp > setpoint-1, setpoint == 15
  4. 20DP Test  : P31 = 68±2, P41 = 68±2, actual_dp > setpoint-1, setpoint == 20
  5. 25DP Test  : P31 = 76±2, P41 = 76±2, actual_dp > setpoint-1, setpoint == 25
  6. 30DP Test  : P31 = 83±2, P41 = 83±2, actual_dp > setpoint-1, setpoint == 30
  7. Combine 25%  Pump Test: P31 = 25±1, P41 = 25±1
  8. Combine 50%  Pump Test: P31 = 50±1, P41 = 50±1
  9. Combine 75%  Pump Test: P31 = 75±1, P41 = 75±1
 10. Combine 100% Pump Test: P31 = 90±1, P41 = 90±1
  –  else: None  (remain idle)
"""

from __future__ import annotations

import logging
import threading
from typing import Callable

# Raw scale for DP registers (same as FLOW_SCALE pattern, divide by 10)
_DP_SCALE = 100.0
_SPEED_SCALE = 1.0
_LOGGER = logging.getLogger(__name__)

# Detection interval in seconds
DETECTION_INTERVAL_S = 3.0


def _within(value: float, target: float, tolerance: float) -> bool:
    return abs(value - target) <= tolerance


def detect_mode(p31: float, p41: float, actual_dp: float, dp_setpoint: float) -> str | None:
    """
    Pure function: given the four measured values, return the matching TEST_MODE
    name string (matching monitor_config.TEST_MODES exactly), or None if no match.
    """
    # 1. P31 pump-only test
    if p31 > 70 and _within(p41, 0, 2):
        return "P31 100% Pump Test"

    # 2. P41 pump-only test
    if _within(p31, 0, 2) and p41 > 70:
        return "P41 100% Pump Test"

    # Check DP tests before Combine 75% because the 25DP speed range overlaps it.
    for sp_target, p_target, name in (
        (15, 58, "15DP Test"),
        (20, 68, "20DP Test"),
        (25, 76, "25DP Test"),
        (30, 83, "30DP Test"),
    ):
        if (
            _within(p31, p_target, 2)
            and _within(p41, p_target, 2)
            and _within(dp_setpoint, sp_target, 0.5)
            and actual_dp > (dp_setpoint - 1)
        ):
            return name

    # 3–6. Combine pump tests (both speeds equal within ±1)
    for target, name in (
        (25, "Combine 25% Pump Test"),
        (50, "Combine 50% Pump Test"),
        (75, "Combine 75% Pump Test"),
        (90, "Combine 100% Pump Test"),
    ):
        if _within(p31, target, 1) and _within(p41, target, 1):
            return name

    return None


class AutoModeDetector:
    """
    Background thread that polls Modbus every DETECTION_INTERVAL_S seconds and
    calls *on_mode_detected* whenever the resolved mode changes.

    Parameters
    ----------
    modbus_core :
        A :class:`ModbusCore` instance (must already support ``read_registers_raw``).
    on_mode_detected :
        Callback invoked on the *calling* thread's scheduler via ``root.after(0, ...)``.
        Signature: ``(mode_name: str | None) -> None``.
        ``mode_name`` is the new mode or ``None`` when no mode could be determined.
    root :
        The Tk root – used to safely schedule the callback on the main thread.
    """

    def __init__(
        self,
        modbus_core,
        on_mode_detected: Callable[[str | None], None],
        root,
    ) -> None:
        self._modbus = modbus_core
        self._on_mode_detected = on_mode_detected
        self._root = root
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_mode: str | None = "__unset__"   # sentinel so first result always fires

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._stop.clear()
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True, name="AutoModeDetector")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._last_mode = "__unset__"

    def reset(self) -> None:
        """Force the next detection to fire even if the mode is unchanged."""
        self._last_mode = "__unset__"

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run(self) -> None:
        while not self._stop.is_set():
            self._detect_once()
            self._stop.wait(DETECTION_INTERVAL_S)

    def _detect_once(self) -> None:
        try:
            # Read P31 (39), P41 (40) in one batch, then DP registers separately
            # because registers 35 and 201 are not contiguous with 39–40.
            speed_regs = self._modbus.read_registers_raw(39, 2)
            dp_actual_raw = self._modbus.read_registers_raw(35, 1)
            dp_setpoint_raw = self._modbus.read_registers_raw(201, 1)
        except Exception:
            _LOGGER.exception("Auto-mode detection failed while reading Modbus registers")
            mode = None
        else:
            if speed_regs is None or dp_actual_raw is None or dp_setpoint_raw is None:
                mode = None
            else:
                p31 = self._modbus.signed(speed_regs[0]) / _SPEED_SCALE
                p41 = self._modbus.signed(speed_regs[1]) / _SPEED_SCALE
                actual_dp = self._modbus.signed(dp_actual_raw[0]) / _DP_SCALE
                dp_setpoint = self._modbus.signed(dp_setpoint_raw[0]) / _DP_SCALE
                mode = detect_mode(p31, p41, actual_dp, dp_setpoint)
        if mode != self._last_mode:
            self._last_mode = mode
            # Schedule callback safely on Tk main thread
            self._root.after(0, self._on_mode_detected, mode)
