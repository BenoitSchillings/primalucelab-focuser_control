"""Smoke tests using a fake serial port.

These exercise the request/response framing and verb dispatch without
needing real hardware. The fake captures every request payload and
returns canned ``res`` frames so we can verify our wire format matches
what the indilib reference driver sends.
"""

from __future__ import annotations

import json
import unittest

from primalucelab import (
    Esatto,
    MotorCurrents,
    MotorRates,
    SestoSenso2,
    SestoSenso3,
    Transport,
)


class FakeSerial:
    """Minimal pyserial stand-in. Each request maps to one response."""

    def __init__(self) -> None:
        self.requests: list[bytes] = []
        self.responses: list[bytes] = []
        self._read_buf = b""

    def reply(self, response: dict) -> None:
        self.responses.append(json.dumps(response, separators=(",", ":")).encode("ascii") + b"\r")

    # pyserial-ish surface ----------------------------------------------------
    def write(self, data: bytes) -> int:
        self.requests.append(data)
        if self.responses:
            self._read_buf += self.responses.pop(0)
        return len(data)

    def flush(self) -> None:
        pass

    def read(self, n: int) -> bytes:
        if not self._read_buf:
            return b""
        chunk = self._read_buf[:n]
        self._read_buf = self._read_buf[n:]
        return chunk

    def reset_input_buffer(self) -> None:
        self._read_buf = b""

    def reset_output_buffer(self) -> None:
        pass

    def close(self) -> None:
        pass


def make_transport() -> tuple[Transport, FakeSerial]:
    fake = FakeSerial()
    return Transport.from_serial(fake), fake


def last_request(fake: FakeSerial) -> dict:
    return json.loads(fake.requests[-1])


class FocuserTests(unittest.TestCase):
    def test_get_absolute_position_request_shape(self) -> None:
        t, fake = make_transport()
        fake.reply({"res": {"get": {"MOT1": {"ABS_POS": 12345}}}})
        f = Esatto(t)
        self.assertEqual(f.get_absolute_position(), 12345)
        self.assertEqual(
            last_request(fake),
            {"req": {"get": {"MOT1": {"ABS_POS": ""}}}},
        )

    def test_go_absolute_position_uses_move_abs(self) -> None:
        t, fake = make_transport()
        fake.reply({"res": {"cmd": {"MOT1": {"MOVE_ABS": "done"}}}})
        Esatto(t).go_absolute_position(2000)
        self.assertEqual(
            last_request(fake),
            {"req": {"cmd": {"MOT1": {"MOVE_ABS": {"STEP": 2000}}}}},
        )

    def test_stop(self) -> None:
        t, fake = make_transport()
        fake.reply({"res": {"cmd": {"MOT1": {"MOT_STOP": "done"}}}})
        Esatto(t).stop()
        self.assertEqual(
            last_request(fake),
            {"req": {"cmd": {"MOT1": {"MOT_STOP": ""}}}},
        )

    def test_set_backlash(self) -> None:
        t, fake = make_transport()
        fake.reply({"res": {"set": {"MOT1": {"BKLASH": "done"}}}})
        Esatto(t).set_backlash(120)
        self.assertEqual(
            last_request(fake),
            {"req": {"set": {"MOT1": {"BKLASH": 120}}}},
        )

    def test_temperature_string_parses_to_float(self) -> None:
        t, fake = make_transport()
        fake.reply({"res": {"get": {"MOT1": {"NTC_T": "23.50"}}}})
        self.assertAlmostEqual(Esatto(t).get_motor_temp(), 23.5)

    def test_firmware_unwraps_swapp(self) -> None:
        t, fake = make_transport()
        fake.reply({"res": {"get": {"SWVERS": {"SWAPP": "3.05", "SWBL": "1.2"}}}})
        self.assertEqual(Esatto(t).get_firmware_version(), "3.05")

    def test_is_busy_when_stopped(self) -> None:
        t, fake = make_transport()
        fake.reply({"res": {"get": {"MOT1": {"STATUS": {"BUSY": 0, "MST": "stop"}}}}})
        self.assertFalse(Esatto(t).is_busy())

    def test_is_busy_when_busy_flag_set(self) -> None:
        t, fake = make_transport()
        fake.reply({"res": {"get": {"MOT1": {"STATUS": {"BUSY": 1, "MST": "acc"}}}}})
        self.assertTrue(Esatto(t).is_busy())

    def test_is_busy_during_fast_move_constant_speed(self) -> None:
        # L6470 RUN command clears BUSY at cruise speed; MST still reports
        # motion. Without the MST check, is_busy would wrongly return False
        # mid-fast_move_in/out.
        t, fake = make_transport()
        fake.reply({"res": {"get": {"MOT1": {"STATUS": {"BUSY": 0, "MST": "CstSpeed"}}}}})
        self.assertTrue(Esatto(t).is_busy())

    def test_is_busy_during_deceleration(self) -> None:
        t, fake = make_transport()
        fake.reply({"res": {"get": {"MOT1": {"STATUS": {"BUSY": 0, "MST": "dec"}}}}})
        self.assertTrue(Esatto(t).is_busy())

    def test_is_busy_with_no_mst_field(self) -> None:
        # Some firmware variants may omit MST entirely; fall back to BUSY.
        t, fake = make_transport()
        fake.reply({"res": {"get": {"MOT1": {"STATUS": {"BUSY": 0}}}}})
        self.assertFalse(Esatto(t).is_busy())


class SestoSenso3Tests(unittest.TestCase):
    def test_goto_uses_goto_command(self) -> None:
        t, fake = make_transport()
        fake.reply({"res": {"cmd": {"MOT1": {"GOTO": "done"}}}})
        SestoSenso3(t).go_absolute_position(8000)
        self.assertEqual(
            last_request(fake),
            {"req": {"cmd": {"MOT1": {"GOTO": 8000}}}},
        )

    def test_abs_pos_step(self) -> None:
        t, fake = make_transport()
        fake.reply({"res": {"get": {"MOT1": {"ABS_POS_STEP": 4321}}}})
        self.assertEqual(SestoSenso3(t).get_absolute_position(), 4321)

    def test_busy_with_mst_in_motion(self) -> None:
        t, fake = make_transport()
        # BUSY=0 but MST not yet "stop" -> still busy.
        fake.reply({"res": {"get": {"MOT1": {"STATUS": {"BUSY": 0, "MST": "CstSpeed"}}}}})
        self.assertTrue(SestoSenso3(t).is_busy())

    def test_busy_when_stopped(self) -> None:
        t, fake = make_transport()
        fake.reply({"res": {"get": {"MOT1": {"STATUS": {"BUSY": 0, "MST": "stop"}}}}})
        self.assertFalse(SestoSenso3(t).is_busy())

    def test_move_in_calibration_command(self) -> None:
        t, fake = make_transport()
        fake.reply({"res": {"cmd": {"MOT1": {"CAL_FOCUSER": "done"}}}})
        SestoSenso3(t).move_in(50)
        self.assertEqual(
            last_request(fake),
            {"req": {"cmd": {"MOT1": {"CAL_FOCUSER": "MoveIn-50"}}}},
        )


class SestoSenso2Tests(unittest.TestCase):
    def test_apply_motor_preset(self) -> None:
        t, fake = make_transport()
        fake.reply({"res": {"cmd": {"RUNPRESET": "done"}}})
        SestoSenso2(t).apply_motor_preset("light")
        self.assertEqual(
            last_request(fake),
            {"req": {"cmd": {"RUNPRESET": "light"}}},
        )

    def test_set_motor_rates(self) -> None:
        t, fake = make_transport()
        fake.reply({"res": {"set": {"MOT1": {"FnRUN_ACC": "done"}}}})
        SestoSenso2(t).set_motor_rates(MotorRates(acc_rate=5, dec_rate=4, run_speed=7))
        self.assertEqual(
            last_request(fake),
            {"req": {"set": {"MOT1": {"FnRUN_ACC": 5, "FnRUN_DEC": 4, "FnRUN_SPD": 7}}}},
        )

    def test_get_motor_settings(self) -> None:
        t, fake = make_transport()
        fake.reply({
            "res": {
                "get": {
                    "MOT1": {
                        "FnRUN_ACC": 3,
                        "FnRUN_DEC": 4,
                        "FnRUN_SPD": 5,
                        "FnRUN_CURR_ACC": 6,
                        "FnRUN_CURR_DEC": 7,
                        "FnRUN_CURR_SPD": 8,
                        "FnRUN_CURR_HOLD": 2,
                        "HOLDCURR_STATUS": 1,
                    }
                }
            }
        })
        rates, currents, hold = SestoSenso2(t).get_motor_settings()
        self.assertEqual(rates, MotorRates(acc_rate=3, dec_rate=4, run_speed=5))
        self.assertEqual(
            currents,
            MotorCurrents(acc_current=6, dec_current=7, run_current=8, hold_current=2),
        )
        self.assertTrue(hold)


class _ErrLineFakeSerial(FakeSerial):
    """Variant that emits an ERR: warning before the JSON response."""

    def write(self, data: bytes) -> int:
        self.requests.append(data)
        good = json.dumps(
            {"res": {"get": {"MOT1": {"ABS_POS": 7}}}}, separators=(",", ":")
        ).encode("ascii")
        self._read_buf += b"ERR: noise\r" + good + b"\r"
        return len(data)


class TransportFramingTests(unittest.TestCase):
    def test_skips_err_lines(self) -> None:
        fake = _ErrLineFakeSerial()
        t = Transport.from_serial(fake)
        result = t.send_request({"req": {"get": {"MOT1": {"ABS_POS": ""}}}})
        self.assertEqual(result, {"get": {"MOT1": {"ABS_POS": 7}}})


if __name__ == "__main__":
    unittest.main()
