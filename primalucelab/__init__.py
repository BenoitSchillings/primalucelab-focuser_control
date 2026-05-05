"""Python driver for PrimaLuceLab focusers.

Wraps the JSON-over-serial USB protocol (Rev. 3.3, 2022) used by the
SESTO SENSO 2/3 and ESATTO product lines.
"""

from .discover import (
    DeviceInfo,
    PortInfo,
    discover,
    find_port,
    find_port_by_hwid,
    list_usb_ports,
)
from .esatto import Esatto
from .exceptions import (
    PrimaLuceError,
    ProtocolError,
    DeviceError,
    TransportError,
)
from .focuser import Focuser
from .sestosenso import SestoSenso2, SestoSenso3
from .transport import Transport
from .types import MotorCurrents, MotorRates

__all__ = [
    "DeviceError",
    "DeviceInfo",
    "Esatto",
    "Focuser",
    "MotorCurrents",
    "MotorRates",
    "PortInfo",
    "PrimaLuceError",
    "ProtocolError",
    "SestoSenso2",
    "SestoSenso3",
    "Transport",
    "TransportError",
    "discover",
    "find_port",
    "find_port_by_hwid",
    "list_usb_ports",
]

__version__ = "0.1.0"
