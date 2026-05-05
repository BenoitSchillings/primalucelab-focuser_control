"""Tests for primalucelab.discover.

We patch ``serial.tools.list_ports.comports`` with a fake list so the tests
work on machines with no real USB serial ports attached.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from primalucelab import discover as _discover_mod
from primalucelab import find_port, find_port_by_hwid, list_usb_ports


def _fake_port(**kwargs) -> SimpleNamespace:
    """Build a stand-in for pyserial's ListPortInfo."""
    defaults = dict(
        device="/dev/ttyACM0",
        vid=None,
        pid=None,
        serial_number=None,
        manufacturer=None,
        product=None,
        description=None,
        hwid=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


PORTS = [
    _fake_port(
        device="/dev/ttyACM0",
        vid=0x1A86,
        pid=0x7523,
        serial_number=None,
        product="USB Serial",
        hwid="USB VID:PID=1A86:7523",
    ),
    _fake_port(
        device="/dev/ttyACM1",
        vid=0x03EB,
        pid=0x2404,
        serial_number="ESATTO35-A",
        product="ESATTO 3.5",
        hwid="USB VID:PID=03EB:2404 SER=ESATTO35-A",
    ),
    _fake_port(
        device="/dev/ttyACM2",
        vid=0x03EB,
        pid=0x2404,
        serial_number="ESATTO35-B",
        product="ESATTO 3.5",
        hwid="USB VID:PID=03EB:2404 SER=ESATTO35-B",
    ),
]


class FindPortTests(unittest.TestCase):
    def test_match_vid_pid(self) -> None:
        with patch("primalucelab.discover.list_ports.comports", return_value=PORTS):
            self.assertEqual(find_port(vid=0x03EB, pid=0x2404), "/dev/ttyACM1")

    def test_match_serial_disambiguates(self) -> None:
        with patch("primalucelab.discover.list_ports.comports", return_value=PORTS):
            self.assertEqual(
                find_port(vid=0x03EB, pid=0x2404, serial_number="ESATTO35-B"),
                "/dev/ttyACM2",
            )

    def test_no_match_returns_none(self) -> None:
        with patch("primalucelab.discover.list_ports.comports", return_value=PORTS):
            self.assertIsNone(find_port(vid=0xDEAD, pid=0xBEEF))

    def test_serial_only(self) -> None:
        with patch("primalucelab.discover.list_ports.comports", return_value=PORTS):
            self.assertEqual(find_port(serial_number="ESATTO35-A"), "/dev/ttyACM1")

    def test_no_criteria_returns_first(self) -> None:
        with patch("primalucelab.discover.list_ports.comports", return_value=PORTS):
            self.assertEqual(find_port(), "/dev/ttyACM0")


class FindByHwidTests(unittest.TestCase):
    def test_substring_match_case_insensitive(self) -> None:
        with patch("primalucelab.discover.list_ports.comports", return_value=PORTS):
            self.assertEqual(find_port_by_hwid("esatto35-b"), "/dev/ttyACM2")

    def test_vid_pid_substring(self) -> None:
        with patch("primalucelab.discover.list_ports.comports", return_value=PORTS):
            self.assertEqual(find_port_by_hwid("03EB:2404"), "/dev/ttyACM1")

    def test_no_match(self) -> None:
        with patch("primalucelab.discover.list_ports.comports", return_value=PORTS):
            self.assertIsNone(find_port_by_hwid("nothing-here"))


class ListUsbPortsTests(unittest.TestCase):
    def test_returns_portinfo_dataclass(self) -> None:
        with patch("primalucelab.discover.list_ports.comports", return_value=PORTS):
            result = list_usb_ports()
        self.assertEqual(len(result), 3)
        self.assertEqual(result[1].device, "/dev/ttyACM1")
        self.assertEqual(result[1].vid, 0x03EB)
        self.assertEqual(result[1].serial_number, "ESATTO35-A")
        # Should be a frozen dataclass — hashable.
        self.assertIsInstance(hash(result[1]), int)


if __name__ == "__main__":
    unittest.main()
