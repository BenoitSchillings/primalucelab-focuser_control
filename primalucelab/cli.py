"""Tiny CLI for smoke-testing primalucelab against a real device.

Examples:
    python -m primalucelab discover
    python -m primalucelab info /dev/ttyACM0
    python -m primalucelab status /dev/ttyACM0
    python -m primalucelab move /dev/ttyACM0 12345
    python -m primalucelab raw /dev/ttyACM0 '{"req":{"get":{"MOT1":{"ABS_POS":""}}}}'
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from .discover import discover, list_usb_ports
from .esatto import Esatto
from .sestosenso import SestoSenso2, SestoSenso3
from .transport import Transport


def _make_focuser(transport: Transport):
    """Pick a Focuser subclass based on MODNAME."""
    try:
        model = str(transport.get(None, "MODNAME")).upper()
    except Exception:
        model = ""
    if "SESTO" in model and "3" in model:
        return SestoSenso3(transport), model
    if "SESTO" in model:
        return SestoSenso2(transport), model
    return Esatto(transport), model


def _cmd_info(args: argparse.Namespace) -> int:
    with Transport(args.port, baudrate=args.baud, timeout=args.timeout) as t:
        focuser, model = _make_focuser(t)
        print(f"model:    {model or '?'}")
        print(f"serial:   {focuser.get_serial_number()}")
        print(f"firmware: {focuser.get_firmware_version()}")
        try:
            print(f"position: {focuser.get_absolute_position()}")
            print(f"max_pos:  {focuser.get_max_position()}")
        except Exception as exc:
            print(f"position: <error: {exc}>")
        try:
            print(f"motor_T:  {focuser.get_motor_temp():.2f} C")
        except Exception:
            pass
        try:
            print(f"ext_T:    {focuser.get_external_temp():.2f} C")
        except Exception:
            pass
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    with Transport(args.port, baudrate=args.baud, timeout=args.timeout) as t:
        focuser, _ = _make_focuser(t)
        json.dump(focuser.get_status(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    return 0


def _cmd_move(args: argparse.Namespace) -> int:
    with Transport(args.port, baudrate=args.baud, timeout=args.timeout) as t:
        focuser, _ = _make_focuser(t)
        focuser.go_absolute_position(args.position)
        if args.wait:
            focuser.wait_until_idle(timeout=args.wait_timeout)
            print(f"final position: {focuser.get_absolute_position()}")
    return 0


def _cmd_stop(args: argparse.Namespace) -> int:
    with Transport(args.port, baudrate=args.baud, timeout=args.timeout) as t:
        focuser, _ = _make_focuser(t)
        focuser.stop()
    return 0


def _cmd_raw(args: argparse.Namespace) -> int:
    request = json.loads(args.json)
    with Transport(args.port, baudrate=args.baud, timeout=args.timeout) as t:
        result = t.raw(request)
        json.dump(result, sys.stdout, indent=2)
        sys.stdout.write("\n")
    return 0


def _cmd_discover(args: argparse.Namespace) -> int:
    if args.all:
        # Filter to actual USB devices — pyserial enumerates legacy ttyS*
        # lines too, which clutter the output.
        ports = [p for p in list_usb_ports() if p.vid is not None]
        if not ports:
            print("no USB serial ports found")
            return 0
        for p in ports:
            print(
                f"{p.device}  vid=0x{p.vid:04x} pid=0x{p.pid:04x}  "
                f"serial={p.serial_number!r}  product={p.product!r}"
            )
        return 0

    devices = discover(timeout=args.timeout, baudrate=args.baud)
    if not devices:
        print("no PrimaLuceLab devices found")
        return 1
    for d in devices:
        print(f"{d.device}  model={d.model!r}  serial={d.serial_number!r}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="primalucelab")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_info = sub.add_parser("info", help="show model / firmware / position")
    p_info.add_argument("port")
    p_info.set_defaults(func=_cmd_info)

    p_status = sub.add_parser("status", help="dump full STATUS dict")
    p_status.add_argument("port")
    p_status.set_defaults(func=_cmd_status)

    p_move = sub.add_parser("move", help="move to absolute position (steps)")
    p_move.add_argument("port")
    p_move.add_argument("position", type=int)
    p_move.add_argument("--wait", action="store_true", help="wait until idle")
    p_move.add_argument("--wait-timeout", type=float, default=120.0)
    p_move.set_defaults(func=_cmd_move)

    p_stop = sub.add_parser("stop", help="stop motion immediately")
    p_stop.add_argument("port")
    p_stop.set_defaults(func=_cmd_stop)

    p_raw = sub.add_parser("raw", help="send a raw JSON request")
    p_raw.add_argument("port")
    p_raw.add_argument("json", help='e.g. \'{"req":{"get":{"MOT1":{"ABS_POS":""}}}}\'')
    p_raw.set_defaults(func=_cmd_raw)

    p_discover = sub.add_parser(
        "discover",
        help="probe USB serial ports for PrimaLuceLab devices (or --all)",
    )
    p_discover.add_argument(
        "--all",
        action="store_true",
        help="list every USB serial port the OS sees, without probing",
    )
    p_discover.set_defaults(func=_cmd_discover)

    args = parser.parse_args(argv)
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(name)s %(levelname)s %(message)s")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
