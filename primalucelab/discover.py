"""Helpers for finding PrimaLuceLab devices among the system's USB serial ports.

Two layers are provided:

- :func:`find_port` and :func:`find_port_by_hwid` — pure pyserial-based
  enumeration, matching on USB VID/PID/iSerial or a free-form hwid substring.
- :func:`list_usb_ports` and :func:`discover` — higher level. ``discover``
  briefly opens each candidate port, asks the device for ``MODNAME`` and
  ``SN``, and returns the ones that answer like a PrimaLuceLab focuser.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from serial.tools import list_ports

from .exceptions import PrimaLuceError
from .transport import Transport


@dataclass(frozen=True)
class PortInfo:
    """Subset of pyserial ``ListPortInfo`` fields, in a stable, copyable form."""

    device: str
    vid: Optional[int]
    pid: Optional[int]
    serial_number: Optional[str]
    manufacturer: Optional[str]
    product: Optional[str]
    description: Optional[str]
    hwid: Optional[str]


@dataclass(frozen=True)
class DeviceInfo:
    """A PrimaLuceLab device that responded on a USB serial port."""

    device: str
    model: str
    serial_number: str
    port_info: PortInfo


def list_usb_ports() -> list[PortInfo]:
    """Return every USB serial port currently visible to the OS.

    Cross-platform: matches whatever pyserial sees (``/dev/ttyACM*``,
    ``/dev/cu.usbmodem*``, ``COM*``, ...).
    """
    return [
        PortInfo(
            device=p.device,
            vid=p.vid,
            pid=p.pid,
            serial_number=p.serial_number,
            manufacturer=p.manufacturer,
            product=p.product,
            description=p.description,
            hwid=p.hwid,
        )
        for p in list_ports.comports()
    ]


def find_port(
    *,
    vid: Optional[int] = None,
    pid: Optional[int] = None,
    serial_number: Optional[str] = None,
) -> Optional[str]:
    """Return the device path of the first USB serial port matching the criteria.

    Any combination of ``vid`` / ``pid`` / ``serial_number`` may be provided;
    criteria are AND-combined and ``None`` arguments are ignored. Returns
    ``None`` if no port matches.

    Example::

        path = find_port(vid=0x03EB, pid=0x2404)
        path = find_port(serial_number="ESATTO35-12345")
    """
    for port in list_usb_ports():
        if vid is not None and port.vid != vid:
            continue
        if pid is not None and port.pid != pid:
            continue
        if serial_number is not None and port.serial_number != serial_number:
            continue
        return port.device
    return None


def find_port_by_hwid(needle: str) -> Optional[str]:
    """Return the first port whose ``hwid`` contains ``needle`` (case-insensitive)."""
    needle = needle.lower()
    for port in list_usb_ports():
        if needle in (port.hwid or "").lower():
            return port.device
    return None


def _candidate_ports(ports: Iterable[PortInfo]) -> list[PortInfo]:
    """Filter to ports that look like USB CDC-ACM-style devices.

    Any port that pyserial reports a VID for is a USB device; that's enough
    to weed out e.g. legacy on-board UARTs without poking them.
    """
    return [p for p in ports if p.vid is not None]


def discover(*, timeout: float = 1.0, baudrate: int = 115200) -> list[DeviceInfo]:
    """Probe every USB serial port and return the PrimaLuceLab devices that answer.

    Each port is opened briefly with the given ``timeout`` and asked for
    ``MODNAME`` and ``SN``. Ports that don't respond within the timeout, or
    that reply with anything other than valid JSON, are silently skipped —
    so this is safe to run on systems with other USB serial peripherals.

    Returns one :class:`DeviceInfo` per matching port. Order matches the
    order pyserial enumerates ports.
    """
    found: list[DeviceInfo] = []
    for port in _candidate_ports(list_usb_ports()):
        try:
            with Transport(port.device, baudrate=baudrate, timeout=timeout) as t:
                model = str(t.get(None, "MODNAME"))
                serial = str(t.get(None, "SN")).strip()
        except (PrimaLuceError, OSError):
            continue
        found.append(
            DeviceInfo(
                device=port.device,
                model=model,
                serial_number=serial,
                port_info=port,
            )
        )
    return found
