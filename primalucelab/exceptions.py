class PrimaLuceError(Exception):
    """Base exception for all primalucelab errors."""


class TransportError(PrimaLuceError):
    """Serial I/O failure (timeout, write error, malformed line)."""


class ProtocolError(PrimaLuceError):
    """Response could not be parsed or didn't match the request shape."""


class DeviceError(PrimaLuceError):
    """The device returned an ERROR/Error: payload."""
