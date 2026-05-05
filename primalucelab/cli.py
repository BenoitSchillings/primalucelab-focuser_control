"""Tiny CLI for smoke-testing primalucelab against a real device.

Examples:
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

    args = parser.parse_args(argv)
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(name)s %(levelname)s %(message)s")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
