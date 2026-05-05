# primalucelab-focuser_control

A Python driver for PrimaLuceLab focusers — **SESTO SENSO 2**, **SESTO SENSO 3**, and the
**ESATTO** family. Wraps the JSON-over-serial USB protocol (Revision 3.3, July 2022) and
provides clean Python classes for every command exposed by the indilib reference C++
driver, plus a small CLI for ad-hoc testing.

> Status: alpha. The wire-shape of every request is verified by unit tests against a
> fake serial port, but the package has not yet been validated against live hardware.
> File issues with the raw frames you see (`-v` flag on the CLI) and they will be
> fixed quickly.

---

## Contents

- [Installation](#installation)
- [Quick start](#quick-start)
- [Architecture](#architecture)
- [CLI](#cli)
- [API reference](#api-reference)
  - [`Transport`](#class-transport)
  - [`Focuser` (base class)](#class-focuser)
  - [`SestoSenso2`](#class-sestosenso2)
  - [`SestoSenso3`](#class-sestosenso3)
  - [`Esatto`](#class-esatto)
  - [Data classes — `MotorRates`, `MotorCurrents`](#data-classes)
  - [Exceptions](#exceptions)
- [Wire protocol notes](#wire-protocol-notes)
- [Threading](#threading)
- [Error handling](#error-handling)
- [Development](#development)
- [License](#license)

---

## Installation

The only runtime dependency is `pyserial`.

```bash
pip install pyserial
git clone https://github.com/BenoitSchillings/primalucelab-focuser_control
cd primalucelab-focuser_control
pip install -e .
```

After installation a `primalucelab` console script is also available.

### Connecting

Both SESTO SENSO and ESATTO devices appear as a USB CDC ACM serial port. On Linux
this is typically `/dev/ttyACM0`; on macOS something like `/dev/cu.usbmodem*`; on
Windows a `COM*` port. The default baud rate is **115200, 8N1**.

If you do not have permission to open the port on Linux, add yourself to the
`dialout` group (or `uucp` on Arch):

```bash
sudo usermod -aG dialout "$USER"
```

---

## Quick start

```python
from primalucelab import Transport, Esatto

with Transport("/dev/ttyACM0") as t:
    focuser = Esatto(t)

    print("model:    ", focuser.get_model())
    print("firmware: ", focuser.get_firmware_version())
    print("position: ", focuser.get_absolute_position())

    focuser.go_absolute_position(12000)
    focuser.wait_until_idle()

    print("final pos:", focuser.get_absolute_position())
    print("motor T:  ", focuser.get_motor_temp(), "°C")
```

For a SESTO SENSO 3, swap `Esatto` for `SestoSenso3`. The base motion API is
identical; SS3 internally uses `GOTO`/`ABS_POS_STEP` rather than `MOVE_ABS`/`ABS_POS`,
and reports motion via both `BUSY` and the textual `MST` field.

---

## Architecture

```
primalucelab/
├── transport.py     # JSON-over-serial transport, lock-protected
├── exceptions.py    # PrimaLuceError → Transport/Protocol/DeviceError
├── types.py         # MotorRates, MotorCurrents dataclasses
├── focuser.py       # Focuser base class (shared SS2/SS3/ESATTO surface)
├── sestosenso.py    # SestoSenso2, SestoSenso3
├── esatto.py        # Esatto
├── cli.py           # `python -m primalucelab …`
└── __main__.py
tests/
└── test_smoke.py    # 15 tests against a fake serial
```

`Transport` owns the serial port and is the only place that touches bytes on the
wire. Device classes are thin wrappers that build dicts, hand them to the transport,
and unwrap the responses into Python types.

A single `Transport` instance can be passed to multiple device classes when several
products share one bus (rare for focusers; common for ESATTO + ARCO setups, but the
ARCO surface has been intentionally omitted from this package — focuser only).

---

## CLI

```
python -m primalucelab [--baud 115200] [--timeout 5.0] [-v] <subcommand>
```

The CLI auto-detects the device class from `MODNAME` and picks `SestoSenso3`,
`SestoSenso2`, or falls back to `Esatto`.

| Command | What it does |
|---|---|
| `info <port>` | Prints model, serial, firmware, current and max position, motor and external temperatures. |
| `status <port>` | Pretty-prints the full `STATUS` dict from the device. |
| `move <port> <position> [--wait] [--wait-timeout=120]` | Moves to absolute step position. With `--wait`, blocks until `BUSY` returns 0. |
| `stop <port>` | Issues `MOT_STOP`. |
| `raw <port> '<json>'` | Sends an arbitrary `{"req": …}` frame and prints the response. Use this for keys not yet wrapped. |

`-v` enables debug logging that prints every `<REQ>` and `<RES>` frame — invaluable
when troubleshooting against a real device.

```bash
python -m primalucelab info /dev/ttyACM0
python -m primalucelab move /dev/ttyACM0 25000 --wait
python -m primalucelab raw /dev/ttyACM0 '{"req":{"get":{"MOT1":{"ABS_POS":""}}}}'
```

---

## API reference

All classes live under the top-level `primalucelab` package:

```python
from primalucelab import (
    Transport,
    Focuser,
    SestoSenso2,
    SestoSenso3,
    Esatto,
    MotorRates,
    MotorCurrents,
    PrimaLuceError,
    TransportError,
    ProtocolError,
    DeviceError,
)
```

---

### class `Transport`

Owns the serial port, serializes JSON request/response frames, and provides verb
helpers used by every device class. Thread-safe (one `threading.Lock` per
instance).

#### Construction

```python
Transport(port: str, *, baudrate: int = 115200, timeout: float = 5.0, name: str = "primalucelab")
```

Opens the named serial port immediately. `timeout` applies to both reads and writes.

```python
Transport.from_serial(ser: serial.Serial, name: str = "primalucelab") -> Transport
```

Wrap an already-opened pyserial-compatible object. Useful for tests with
`serial.serial_for_url("loop://")` or with the `FakeSerial` shown in `tests/`.

#### Context manager

```python
with Transport("/dev/ttyACM0") as t:
    ...
```

Closes the underlying port on exit.

#### Verb helpers

These mirror the four protocol verbs (`get` / `set` / `cmd` / `srv`) and handle
node routing (`MOT1`, `MOT2`, or no node).

| Method | Description |
|---|---|
| `get(node: Optional[str], key: str) -> Any` | Issue a single-key `get`. Returns the raw value (int, str, dict, …). |
| `set(node: Optional[str], payload: dict) -> None` | Issue a `set` and verify the device replies `"done"`. Multi-key payloads accepted. |
| `cmd(node: Optional[str], payload: dict) -> None` | Issue a `cmd` and verify `"done"` echo. |
| `srv(key: str, value: Any = "") -> Any` | Issue a `srv` request (e.g. `GET_MODEL_SUBMODEL`). |
| `get_node(node: str) -> dict` | Fetch every reported field for a node in one frame. |
| `raw(request: dict) -> Optional[dict]` | Escape hatch — send any pre-built `{"req": …}` and return the `res` body. |
| `send_request(request, *, expect_response=True) -> Optional[dict]` | Lowest-level call; returns the `res` body verbatim. |
| `close() -> None` | Close the underlying serial port. |

`node` may be `"MOT1"`, `"MOT2"`, or `None` for device-wide keys (e.g. `SN`,
`MODNAME`, `EXT_T`, `VIN_12V`).

#### Example — calling something the package does not wrap yet

```python
res = t.raw({"req": {"get": {"MOT1": {"FORCEDIR": ""}}}})
print(res["get"]["MOT1"]["FORCEDIR"])
```

---

### class `Focuser`

Base class shared by SESTO SENSO 2 / 3 and ESATTO. You normally instantiate one
of the subclasses, but every method below is available on all of them.

```python
Focuser(transport: Transport)
```

#### Position

| Method | Returns |
|---|---|
| `get_absolute_position() -> int` | Current position in motor steps. |
| `get_max_position() -> int` | Calibrated maximum travel in steps. |
| `is_hall_sensor_detected() -> bool` | Whether a Hall sensor is reporting. |

#### Motion

| Method | Notes |
|---|---|
| `go_absolute_position(position: int) -> None` | Move to `position` steps. |
| `stop() -> None` | Immediate stop. |
| `fast_move_out() -> None` | Run outward at full speed until stopped. |
| `fast_move_in() -> None` | Run inward at full speed until stopped. |
| `get_current_speed() -> int` | Live speed (device-defined units). |
| `get_status() -> dict` | Full `STATUS` dict — `BUSY`, `MST`, position, etc. |
| `is_busy() -> bool` | Convenience: `STATUS["BUSY"] == 1`. |
| `wait_until_idle(*, poll_interval=0.2, timeout=None) -> None` | Block until `is_busy()` is False; raises `TimeoutError`. |

#### Sensors

| Method | Returns |
|---|---|
| `get_motor_temp() -> float` | Internal motor NTC temperature (°C). |
| `get_external_temp() -> float` | External probe temperature (°C). |
| `get_voltage_12v() -> float` | 12 V input bus voltage. |

The firmware returns these as strings (e.g. `"23.50"`); the wrapper converts to
`float` automatically.

#### Firmware / identity

| Method | Returns |
|---|---|
| `get_serial_number() -> str` | Device serial number. |
| `get_firmware_version() -> str` | Application firmware version (`SWAPP`). |
| `get_model() -> str` | Model name string. |

#### Backlash

| Method | Notes |
|---|---|
| `set_backlash(steps: int) -> None` | Persist backlash compensation in steps. |
| `get_backlash() -> int` | Current backlash setting. |

---

### class `SestoSenso2`

Adds presets, motor rates/currents, hold-current toggle, and the manual
calibration sequence used by SS2 firmware.

#### Presets

| Method | Notes |
|---|---|
| `apply_motor_preset(name: str) -> None` | Apply a built-in preset (`"light"`, `"medium"`, `"slow"`) or a user preset (`"user_1"`, `"user_2"`, …). |
| `set_motor_user_preset(index: int, rates: MotorRates, currents: MotorCurrents) -> None` | Persist preset slot `index` (typically 1–3). |

#### Motor settings

| Method | Notes |
|---|---|
| `get_motor_settings() -> tuple[MotorRates, MotorCurrents, bool]` | Returns rates, currents, and whether holding current is active. |
| `set_motor_rates(rates: MotorRates) -> None` | Updates `FnRUN_ACC` / `FnRUN_DEC` / `FnRUN_SPD`. |
| `set_motor_currents(currents: MotorCurrents) -> None` | Updates the four `FnRUN_CURR_*` fields. |
| `set_motor_hold(hold: bool) -> None` | Energize the motor at standstill (`HOLDCURR_STATUS`). |

#### Calibration

| Method | Sends |
|---|---|
| `init_calibration()` | `CAL_FOCUSER: "Init"` |
| `go_out_to_find_max_pos()` | `CAL_FOCUSER: "GoOutToFindMaxPos"` |
| `store_as_max_position()` | `CAL_FOCUSER: "StoreAsMaxPos"` |
| `store_as_min_position()` | `CAL_FOCUSER: "StoreAsMinPos"` |

A typical SS2 manual calibration walk looks like:

```python
ss2 = SestoSenso2(t)
ss2.init_calibration()
ss2.fast_move_in(); ss2.wait_until_idle(); ss2.store_as_min_position()
ss2.go_out_to_find_max_pos(); ss2.wait_until_idle()
ss2.store_as_max_position()
```

---

### class `SestoSenso3`

SESTO SENSO 3 firmware diverges enough to warrant a dedicated class:

- Motion uses `GOTO` instead of `MOVE_ABS`.
- Position is read from `ABS_POS_STEP` instead of `ABS_POS`.
- `is_busy` checks both the integer `BUSY` flag and the textual `MST` field
  (which can lag during encoder-feedback transitions through values like
  `"CstSpeed"` and `"dec"` before settling on `"stop"`).

#### Motion overrides

| Method | Notes |
|---|---|
| `go_absolute_position(position: int) -> None` | Sends `cmd MOT1 {GOTO: position}`. |
| `get_absolute_position() -> int` | Reads `MOT1.ABS_POS_STEP`. |
| `is_busy() -> bool` | True if `BUSY == 1` *or* `MST != "stop"`. |

#### Model / submodel

| Method | Returns |
|---|---|
| `get_model() -> str` | Inherited from `Focuser`. |
| `get_sub_model() -> str` | Parses the `SubModel = …` field out of the `srv GET_MODEL_SUBMODEL` reply. |

#### Recovery delay

| Method | Notes |
|---|---|
| `set_recovery_delay(delay: int) -> None` | Persist `RECOVER_DELAY`. |
| `get_recovery_delay() -> int` | Read it back. |

#### Motor settings

Same shape as SS2 but on SS3 firmware:

- `get_motor_settings() -> tuple[MotorRates, MotorCurrents, bool]`
- `set_motor_rates(rates: MotorRates) -> None`
- `set_motor_currents(currents: MotorCurrents) -> None`
- `set_motor_hold(hold: bool) -> None`
- `apply_motor_preset(name: str) -> None`

#### Calibration

SS3 supports both a manual / semi-automatic walk and a single-shot automatic
sweep (on SC variants only).

| Method | Sends |
|---|---|
| `init_calibration_semi_auto()` | `CAL_FOCUSER: "Init"` |
| `go_in_to_find_min_pos()` | `CAL_FOCUSER: "GoInToFindMinPos"` |
| `go_out_to_find_max_pos()` | `CAL_FOCUSER: "GoOutToFindMaxPos"` |
| `stop_motor()` | `CAL_FOCUSER: "StopMotor"` |
| `store_as_min_position()` | `CAL_FOCUSER: "StoreAsMinPos"` |
| `store_as_max_position()` | `CAL_FOCUSER: "StoreAsMaxPos"` |
| `move_in(steps: int)` | `CAL_FOCUSER: "MoveIn-<steps>"` |
| `move_out(steps: int)` | `CAL_FOCUSER: "MoveOut-<steps>"` |
| `start_auto_calibration()` | `CAL_FOCUSER: "start_auto_cal"` (SC only) |
| `stop_calibration()` | `CAL_FOCUSER: "stop_calib"` |

---

### class `Esatto`

ESATTO 2"/2"LP/3"/3.5"LP/4" focusers. Uses the shared `Focuser` motion API
(`MOVE_ABS` and `ABS_POS`). The only ESATTO-specific surface is:

| Method | Returns |
|---|---|
| `get_voltage_usb() -> float` | USB bus voltage (V), parsed from the string `VIN_USB` field. |

ESATTO inherits `set_backlash` / `get_backlash` from `Focuser`.

---

### Data classes

```python
from dataclasses import dataclass

@dataclass
class MotorRates:
    acc_rate: int = 0     # 1-10
    run_speed: int = 0    # 1-10
    dec_rate: int = 0     # 1-10

@dataclass
class MotorCurrents:
    acc_current: int = 0  # 1-10
    run_current: int = 0  # 1-10
    dec_current: int = 0  # 1-10
    hold_current: int = 0 # 1-5
```

`MotorRates` and `MotorCurrents` are plain dataclasses — equality, repr, and
keyword construction work as expected.

---

### Exceptions

All exceptions inherit from `PrimaLuceError`.

| Exception | Raised when |
|---|---|
| `TransportError` | Serial I/O failure (timeout, write error, frame too long). |
| `ProtocolError` | Response was not valid JSON, missing the expected `res` wrapper, or did not contain the expected verb / node. |
| `DeviceError` | The device returned an `ERROR` field inside the `res` body, or an `Error:` line on the wire. |

```python
from primalucelab import TransportError, DeviceError

try:
    focuser.go_absolute_position(50_000_000)
except DeviceError as exc:
    print("device rejected the command:", exc)
except TransportError as exc:
    print("serial bus problem:", exc)
```

---

## Wire protocol notes

- All frames are **plain JSON** terminated by **`\r` (0x0D)**.
- Default baud rate **115200, 8N1**.
- Verbs: `get`, `set`, `cmd`, `srv`.
- Nodes: `MOT1` (focuser motor) or no node for device-wide keys.
- A successful `set`/`cmd` echoes the key with the value `"done"`.
- A failed call returns an `ERROR` field inside the affected node’s body.
- The device may emit `ERR: …\r` warning lines before the actual response;
  the transport drains and logs these as warnings before parsing JSON.
- Floating-point sensor fields (`NTC_T`, `EXT_T`, `VIN_12V`, `VIN_USB`) are
  returned as **strings**, not numbers — the wrapper converts to `float`.
- The transport flushes both input and output buffers before each request to
  avoid catching partial frames left over from a previous command.

Example raw exchange:

```text
<REQ> {"req":{"cmd":{"MOT1":{"MOVE_ABS":{"STEP":12000}}}}}
<RES> {"res":{"cmd":{"MOT1":{"MOVE_ABS":"done"}}}}
```

```text
<REQ> {"req":{"get":{"MOT1":{"STATUS":""}}}}
<RES> {"res":{"get":{"MOT1":{"STATUS":{"BUSY":1,"MST":"CstSpeed","SPEED":540, ...}}}}}
```

---

## Threading

A single `Transport` is safe to share across threads — every request is taken
under an internal lock that wraps both the write and the response read, so
two callers can never interleave bytes on the wire.

If you need true parallelism (e.g. a status poller alongside a motion thread),
share **one** `Transport` between the device classes — do not open two serial
connections to the same physical port.

---

## Error handling

The transport never returns silent failures: every method either succeeds and
returns the parsed value, or raises one of the exceptions above. Suggested
pattern for production code:

```python
import logging
from primalucelab import Transport, Esatto, PrimaLuceError

logging.basicConfig(level=logging.INFO)

with Transport("/dev/ttyACM0", timeout=10.0) as t:
    f = Esatto(t)
    try:
        f.go_absolute_position(15000)
        f.wait_until_idle(timeout=60.0)
    except PrimaLuceError:
        f.stop()                       # always quench motion before re-raising
        raise
```

For verbose debugging, enable the `primalucelab` logger:

```python
logging.getLogger("primalucelab").setLevel(logging.DEBUG)
```

This logs every `<REQ>` and `<RES>` frame, which is the same information the
CLI prints with `-v`.

---

## Development

```bash
# install in editable mode with test deps
pip install -e .

# run the smoke tests
python -m unittest discover -s tests -v
```

The smoke suite uses an in-memory `FakeSerial` that captures every emitted
request and returns canned responses, so it runs in milliseconds and catches
regressions in the wire-shape of any command.

To add a new wrapped command, the pattern is:

1. Pick the right verb (`get` / `set` / `cmd` / `srv`).
2. Add a method on `Focuser` (or a subclass) that calls
   `self.transport.<verb>(node, payload)`.
3. Add a smoke test that asserts on the request shape via
   `last_request(fake) == {...}`.

Full reference for command names lives in the indilib source the package was
ported from:

- <https://github.com/indilib/indi/blob/master/drivers/focuser/primalucacommandset.h>
- <https://github.com/indilib/indi/blob/master/drivers/focuser/primalucacommandset.cpp>

---

## License

LGPL-2.1-or-later, matching the indilib reference driver this package was
ported from.
