"""ESATTO robotic focuser driver."""

from __future__ import annotations

from .focuser import Focuser, _to_float


class Esatto(Focuser):
    """ESATTO 2"/2"LP/3"/3.5"LP/4" robotic focusers.

    Uses the shared :class:`Focuser` motion API (``MOVE_ABS``/``ABS_POS``).
    The only ESATTO-specific surface today is the USB bus voltage and an
    explicit getter for the model name.
    """

    def get_voltage_usb(self) -> float:
        """USB bus voltage (V)."""
        return _to_float(self.transport.get(None, "VIN_USB"))
