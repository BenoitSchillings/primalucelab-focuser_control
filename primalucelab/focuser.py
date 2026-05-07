"""Common Focuser base class.

Implements the functionality shared between SESTO SENSO 2/3 and the
ESATTO family. Device-specific subclasses live in ``sestosenso`` and
``esatto``.
"""

from __future__ import annotations

from typing import Optional

from .transport import Transport


def _to_float(value) -> float:
    """Coerce a device value (often a string-formatted float) to float."""
    if isinstance(value, (int, float)):
        return float(value)
    return float(str(value).strip())


class Focuser:
    """Base class for SESTO SENSO 2/3 and ESATTO focusers.

    Subclasses override calibration, motor settings, and any device-specific
    motion command (e.g. SestoSenso3 uses ``GOTO`` and ``ABS_POS_STEP``).
    """

    def __init__(self, transport: Transport) -> None:
        self.transport = transport

    # ---- position -----------------------------------------------------------

    def get_absolute_position(self) -> int:
        """Current position in motor steps."""
        return int(self.transport.get("MOT1", "ABS_POS"))

    def get_max_position(self) -> int:
        """Maximum calibrated travel in steps."""
        return int(self.transport.get("MOT1", "CAL_MAXPOS"))

    def is_hall_sensor_detected(self) -> bool:
        return int(self.transport.get("MOT1", "HSENDET")) == 1

    # ---- motion -------------------------------------------------------------

    def go_absolute_position(self, position: int) -> None:
        """Move to ``position`` in steps."""
        self.transport.cmd("MOT1", {"MOVE_ABS": {"STEP": int(position)}})

    def stop(self) -> None:
        self.transport.cmd("MOT1", {"MOT_STOP": ""})

    def fast_move_out(self) -> None:
        """Run the motor outward at full speed until stopped."""
        self.transport.cmd("MOT1", {"F_OUTW": ""})

    def fast_move_in(self) -> None:
        """Run the motor inward at full speed until stopped."""
        self.transport.cmd("MOT1", {"F_INW": ""})

    def get_current_speed(self) -> int:
        return int(self.transport.get("MOT1", "SPEED"))

    def get_status(self) -> dict:
        """Full STATUS dict (BUSY, MST, position, ...)."""
        result = self.transport.get("MOT1", "STATUS")
        if not isinstance(result, dict):
            raise TypeError(f"expected dict STATUS, got {type(result).__name__}")
        return result

    def is_busy(self) -> bool:
        # The underlying L6470/L6480 stepper driver clears BUSY as soon as a
        # RUN command (used by fast_move_in/out) reaches cruise speed, even
        # though the motor keeps turning. MST stays at 'acc' / 'CstSpeed' /
        # 'dec' until the motion actually stops, so combine both signals.
        status = self.get_status()
        if int(status.get("BUSY", 0)) == 1:
            return True
        mst = str(status.get("MST", "")).strip()
        return mst not in ("", "stop")

    # ---- sensors ------------------------------------------------------------

    def get_motor_temp(self) -> float:
        """Internal motor NTC temperature (°C)."""
        return _to_float(self.transport.get("MOT1", "NTC_T"))

    def get_external_temp(self) -> float:
        """External probe temperature (°C). Returns NaN-equivalent if absent."""
        return _to_float(self.transport.get(None, "EXT_T"))

    def get_voltage_12v(self) -> float:
        return _to_float(self.transport.get(None, "VIN_12V"))

    # ---- firmware -----------------------------------------------------------

    def get_serial_number(self) -> str:
        return str(self.transport.get(None, "SN"))

    def get_firmware_version(self) -> str:
        """Application firmware version (``SWAPP`` field)."""
        versions = self.transport.get(None, "SWVERS")
        if isinstance(versions, dict) and "SWAPP" in versions:
            return str(versions["SWAPP"])
        return str(versions)

    def get_model(self) -> str:
        return str(self.transport.get(None, "MODNAME"))

    # ---- backlash -----------------------------------------------------------

    def set_backlash(self, steps: int) -> None:
        self.transport.set("MOT1", {"BKLASH": int(steps)})

    def get_backlash(self) -> int:
        return int(self.transport.get("MOT1", "BKLASH"))

    # ---- convenience --------------------------------------------------------

    def wait_until_idle(self, *, poll_interval: float = 0.2, timeout: Optional[float] = None) -> None:
        """Block until ``is_busy()`` returns False or ``timeout`` elapses."""
        import time

        deadline = None if timeout is None else time.monotonic() + timeout
        while self.is_busy():
            if deadline is not None and time.monotonic() > deadline:
                raise TimeoutError("focuser still busy after timeout")
            time.sleep(poll_interval)
