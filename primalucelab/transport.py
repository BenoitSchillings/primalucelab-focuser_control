"""Serial JSON transport for PrimaLuceLab devices.

The wire protocol is line-oriented JSON terminated by ``\\r`` (0x0D):

    {"req":{"<verb>":<payload>}}\\r          -> host to device
    {"res":{"<verb>":<payload>}}\\r          -> device to host

Verbs are one of ``get`` / ``set`` / ``cmd`` / ``srv``.

The device may emit ``ERR:...\\r`` warning lines before the actual JSON
response; we drain those and keep reading until a valid frame appears.
A successful ``set``/``cmd`` echoes the payload key with the value
``"done"``. An ``ERROR`` key inside the response signals a device-side
failure.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any, Optional

try:
    import serial  # type: ignore
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "primalucelab requires pyserial — install it with `pip install pyserial`"
    ) from exc

from .exceptions import DeviceError, ProtocolError, TransportError

logger = logging.getLogger("primalucelab")

_TERMINATOR = b"\r"
_DEFAULT_BAUD = 115200
_DEFAULT_TIMEOUT = 5.0
_MAX_FRAME = 4096


class Transport:
    """Owns the serial port and serializes JSON request/response frames.

    A single Transport can be shared between multiple device classes when
    several PrimaLuceLab products are chained on one bus (e.g. ESATTO with
    an ARCO attached): the protocol routes via the ``MOT1``/``MOT2``/generic
    nodes, not via separate connections.

    Thread-safe: every request/response pair is serialized through a lock.
    """

    def __init__(
        self,
        port: str,
        *,
        baudrate: int = _DEFAULT_BAUD,
        timeout: float = _DEFAULT_TIMEOUT,
        name: str = "primalucelab",
    ) -> None:
        self.name = name
        self._lock = threading.Lock()
        self._serial = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=timeout,
            write_timeout=timeout,
        )

    @classmethod
    def from_serial(cls, ser: "serial.Serial", name: str = "primalucelab") -> "Transport":
        """Build a Transport around a pre-opened pyserial-compatible object.

        Useful for tests with `serial.serial_for_url('loop://')` or fakes.
        """
        obj = cls.__new__(cls)
        obj.name = name
        obj._lock = threading.Lock()
        obj._serial = ser
        return obj

    def close(self) -> None:
        try:
            self._serial.close()
        except Exception:
            pass

    def __enter__(self) -> "Transport":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ---- low-level frame I/O -------------------------------------------------

    def send_request(self, request: dict, *, expect_response: bool = True) -> Optional[dict]:
        """Send a fully-formed ``{"req": ...}`` frame and return the ``res`` body.

        If ``expect_response`` is False the caller is responsible for any
        follow-up reads (rare; the firmware always responds).
        """
        if "req" not in request:
            raise ProtocolError(f"frame missing 'req' wrapper: {request!r}")

        payload = json.dumps(request, separators=(",", ":")).encode("ascii")
        with self._lock:
            try:
                self._serial.reset_input_buffer()
                self._serial.reset_output_buffer()
            except Exception:
                # Some fake/loopback ports don't implement these.
                pass

            logger.debug("<REQ> %s", payload.decode("ascii", errors="replace"))
            try:
                self._serial.write(payload)
                self._serial.flush()
            except Exception as exc:
                raise TransportError(f"serial write failed: {exc}") from exc

            if not expect_response:
                return None

            line = self._read_frame()

        try:
            decoded = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ProtocolError(f"invalid JSON response: {line!r}") from exc

        if "res" not in decoded:
            raise ProtocolError(f"response missing 'res' wrapper: {decoded!r}")
        return decoded["res"]

    def _read_frame(self) -> str:
        """Read a single CR-terminated frame, skipping ``ERR:`` warnings."""
        while True:
            buf = bytearray()
            while True:
                ch = self._serial.read(1)
                if not ch:
                    raise TransportError("timeout waiting for response")
                if ch == _TERMINATOR:
                    break
                buf.extend(ch)
                if len(buf) > _MAX_FRAME:
                    raise TransportError(f"response exceeded {_MAX_FRAME} bytes")

            line = buf.decode("ascii", errors="replace").strip()
            logger.debug("<RES> %s", line)
            if not line:
                continue
            if line.startswith("ERR:"):
                logger.warning("device warning: %s", line)
                continue
            if line.startswith("Error:"):
                raise DeviceError(line)
            return line

    # ---- verb helpers --------------------------------------------------------

    def get(self, node: Optional[str], key: str) -> Any:
        """Issue a ``get`` for a single key on the given node (or generic).

        Returns the raw value (int, str, dict, ...) extracted from
        ``res.get[node][key]`` or ``res.get[key]``.
        """
        return self._verb_single("get", node, {key: ""}, key)

    def set(self, node: Optional[str], payload: dict) -> None:
        """Issue a ``set`` and validate that the device replied ``"done"``.

        Multi-key payloads are accepted (the device replies ``"done"`` for
        the whole node).
        """
        # Pick any key to inspect for the "done" / "ERROR" response.
        probe = next(iter(payload))
        result = self._verb_single("set", node, payload, probe)
        if isinstance(result, str) and result.lower() != "done":
            raise DeviceError(f"set returned {result!r}")

    def cmd(self, node: Optional[str], payload: dict) -> None:
        """Issue a ``cmd`` and validate ``"done"`` echo."""
        probe = next(iter(payload))
        result = self._verb_single("cmd", node, payload, probe)
        if isinstance(result, str) and result.lower() != "done":
            raise DeviceError(f"cmd returned {result!r}")

    def srv(self, key: str, value: Any = "") -> Any:
        """Issue a ``srv`` request (e.g. ``GET_MODEL_SUBMODEL``)."""
        return self._verb_single("srv", None, {key: value}, key)

    def get_node(self, node: str) -> dict:
        """Fetch the entire dict for a node (e.g. all of MOT2)."""
        request = {"req": {"get": {node: ""}}}
        res = self.send_request(request)
        if not isinstance(res, dict) or "get" not in res:
            raise ProtocolError(f"unexpected response shape: {res!r}")
        return res["get"].get(node, {})

    def raw(self, request: dict) -> Optional[dict]:
        """Escape hatch: send an arbitrary ``{"req": ...}`` and return ``res``.

        Lets callers reach commands not yet wrapped by this library.
        """
        return self.send_request(request)

    # ---- internal ------------------------------------------------------------

    def _verb_single(
        self,
        verb: str,
        node: Optional[str],
        payload: dict,
        probe_key: str,
    ) -> Any:
        if node:
            request = {"req": {verb: {node: payload}}}
        else:
            request = {"req": {verb: payload}}

        res = self.send_request(request)
        if not isinstance(res, dict) or verb not in res:
            raise ProtocolError(f"response missing '{verb}': {res!r}")

        body = res[verb]
        if node:
            if node not in body:
                raise ProtocolError(f"response missing node '{node}': {body!r}")
            body = body[node]

        if isinstance(body, dict):
            if "ERROR" in body:
                raise DeviceError(f"{verb} {node or ''}/{probe_key}: {body['ERROR']}")
            if probe_key in body:
                return body[probe_key]
            # Some commands embed the answer one level deeper, e.g.
            # CAL_FOCUSER -> "done".
            if len(body) == 1:
                return next(iter(body.values()))
        return body
