"""
auto_mode.py  –  Automatic test-mode detection for CHx2000 Realtime Flow Monitor.

Detection runs on a background thread every 2 seconds.
Modbus addresses and scaling are centralized in monitor_config.py.

Detection priority (first rule that matches wins):
  1. P31/P41 100% Pump Test: manual override enabled and one pump is at 100%, the other at 0%
  2. DP Test: manual override disabled and DP setpoint is 15, 20, 25, or 30
  3. Combine Pump Test: manual override enabled and both pumps have matching speeds
  –  else: None  (remain idle)
"""

from __future__ import annotations

import logging
import threading
from typing import Callable

if __package__:
    from .monitor_config import (
        AUTO_MODE_DETECTION_INTERVAL_S,
        AUTO_MODE_DP_SETPOINT_REGISTER,
        AUTO_MODE_DP_SETPOINT_SCALE,
        AUTO_MODE_MANUAL_OVERRIDE_COIL,
        AUTO_MODE_P31_REGISTER,
        AUTO_MODE_P41_REGISTER,
        AUTO_MODE_PUMP_SPEED_SCALE,
    )
else:
    from monitor_config import (
        AUTO_MODE_DETECTION_INTERVAL_S,
        AUTO_MODE_DP_SETPOINT_REGISTER,
        AUTO_MODE_DP_SETPOINT_SCALE,
        AUTO_MODE_MANUAL_OVERRIDE_COIL,
        AUTO_MODE_P31_REGISTER,
        AUTO_MODE_P41_REGISTER,
        AUTO_MODE_PUMP_SPEED_SCALE,
    )

_LOGGER = logging.getLogger(__name__)

DETECTION_INTERVAL_S = AUTO_MODE_DETECTION_INTERVAL_S


def detect_mode(
    manual_override: bool,
    p31_speed: float,
    p41_speed: float,
    dp_setpoint: float,
) -> str | None:
    """
    Return the matching TEST_MODE name for scaled Modbus values, or None if idle.
    """
    if manual_override:
        if p31_speed == 100 and p41_speed == 0:
            return "P31 100% Pump Test"
        if p41_speed == 100 and p31_speed == 0:
            return "P41 100% Pump Test"

        for target, name in (
            (25, "Combine 25% Pump Test"),
            (50, "Combine 50% Pump Test"),
            (75, "Combine 75% Pump Test"),
            (100, "Combine 100% Pump Test"),
        ):
            if p31_speed == target and p41_speed == target:
                return name
    else:
        for target, name in (
            (15, "15DP Test"),
            (20, "20DP Test"),
            (25, "25DP Test"),
            (30, "30DP Test"),
        ):
            if dp_setpoint == target:
                return name

    return None


class AutoModeDetector:
    """
    Background thread that polls Modbus every DETECTION_INTERVAL_S seconds and
    calls *on_mode_detected* whenever the resolved mode changes.

    Parameters
    ----------
    modbus_core :
        A :class:`ModbusCore` instance supporting ``read_registers_raw`` and
        ``read_coils_raw``.
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
            p31_raw = self._modbus.read_registers_raw(AUTO_MODE_P31_REGISTER, 1)
            p41_raw = self._modbus.read_registers_raw(AUTO_MODE_P41_REGISTER, 1)
            manual_override_raw = self._modbus.read_coils_raw(
                AUTO_MODE_MANUAL_OVERRIDE_COIL, 1
            )
            dp_setpoint_raw = self._modbus.read_registers_raw(
                AUTO_MODE_DP_SETPOINT_REGISTER, 1
            )
        except Exception:
            _LOGGER.exception("Auto-mode detection failed while reading Modbus")
            mode = None
        else:
            if (
                p31_raw is None
                or p41_raw is None
                or manual_override_raw is None
                or dp_setpoint_raw is None
            ):
                mode = None
            else:
                p31_speed = (
                    self._modbus.signed(p31_raw[0]) / AUTO_MODE_PUMP_SPEED_SCALE
                )
                p41_speed = (
                    self._modbus.signed(p41_raw[0]) / AUTO_MODE_PUMP_SPEED_SCALE
                )
                dp_setpoint = (
                    self._modbus.signed(dp_setpoint_raw[0])
                    / AUTO_MODE_DP_SETPOINT_SCALE
                )
                mode = detect_mode(
                    manual_override_raw[0],
                    p31_speed,
                    p41_speed,
                    dp_setpoint,
                )
        if mode != self._last_mode:
            self._last_mode = mode
            # Schedule callback safely on Tk main thread
            self._root.after(0, self._on_mode_detected, mode)
