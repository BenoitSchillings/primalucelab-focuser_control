"""SESTO SENSO 2 and SESTO SENSO 3 driver classes."""

from __future__ import annotations

from typing import Tuple

from .focuser import Focuser
from .transport import Transport
from .types import MotorCurrents, MotorRates


class SestoSenso2(Focuser):
    """SESTO SENSO 2 robotic focusing motor."""

    # ---- presets ------------------------------------------------------------

    def apply_motor_preset(self, name: str) -> None:
        """Apply a built-in or user preset (``light``, ``medium``, ``slow``, ``user_1`` ...)."""
        self.transport.cmd(None, {"RUNPRESET": name})

    def set_motor_user_preset(
        self, index: int, rates: MotorRates, currents: MotorCurrents
    ) -> None:
        """Persist a user-defined preset under slot ``index`` (typically 1-3)."""
        slot_name = f"RUNPRESET_{index}"
        preset = {
            "RP_NAME": f"user_{index}",
            "M1ACC": rates.acc_rate,
            "M1DEC": rates.dec_rate,
            "M1SPD": rates.run_speed,
            "M1CACC": currents.acc_current,
            "M1CDEC": currents.dec_current,
            "M1CSPD": currents.run_current,
            "M1CHOLD": currents.hold_current,
        }
        self.transport.set("MOT1", {slot_name: preset})

    # ---- motor settings ----------------------------------------------------

    def get_motor_settings(self) -> Tuple[MotorRates, MotorCurrents, bool]:
        """Return (rates, currents, hold_active)."""
        request = {
            "req": {
                "get": {
                    "MOT1": {
                        "FnRUN_ACC": "",
                        "FnRUN_DEC": "",
                        "FnRUN_SPD": "",
                        "FnRUN_CURR_ACC": "",
                        "FnRUN_CURR_DEC": "",
                        "FnRUN_CURR_SPD": "",
                        "FnRUN_CURR_HOLD": "",
                        "HOLDCURR_STATUS": "",
                    }
                }
            }
        }
        res = self.transport.send_request(request)
        body = res["get"]["MOT1"]
        rates = MotorRates(
            acc_rate=int(body["FnRUN_ACC"]),
            dec_rate=int(body["FnRUN_DEC"]),
            run_speed=int(body["FnRUN_SPD"]),
        )
        currents = MotorCurrents(
            acc_current=int(body["FnRUN_CURR_ACC"]),
            dec_current=int(body["FnRUN_CURR_DEC"]),
            run_current=int(body["FnRUN_CURR_SPD"]),
            hold_current=int(body["FnRUN_CURR_HOLD"]),
        )
        hold_active = int(body["HOLDCURR_STATUS"]) == 1
        return rates, currents, hold_active

    def set_motor_rates(self, rates: MotorRates) -> None:
        self.transport.set(
            "MOT1",
            {
                "FnRUN_ACC": rates.acc_rate,
                "FnRUN_DEC": rates.dec_rate,
                "FnRUN_SPD": rates.run_speed,
            },
        )

    def set_motor_currents(self, currents: MotorCurrents) -> None:
        self.transport.set(
            "MOT1",
            {
                "FnRUN_CURR_ACC": currents.acc_current,
                "FnRUN_CURR_DEC": currents.dec_current,
                "FnRUN_CURR_SPD": currents.run_current,
                "FnRUN_CURR_HOLD": currents.hold_current,
            },
        )

    def set_motor_hold(self, hold: bool) -> None:
        """Energize the motor at standstill (uses ``hold_current``)."""
        self.transport.set("MOT1", {"HOLDCURR_STATUS": 1 if hold else 0})

    # ---- calibration -------------------------------------------------------

    def init_calibration(self) -> None:
        """Begin a manual calibration cycle."""
        self.transport.cmd("MOT1", {"CAL_FOCUSER": "Init"})

    def go_out_to_find_max_pos(self) -> None:
        self.transport.cmd("MOT1", {"CAL_FOCUSER": "GoOutToFindMaxPos"})

    def store_as_max_position(self) -> None:
        self.transport.cmd("MOT1", {"CAL_FOCUSER": "StoreAsMaxPos"})

    def store_as_min_position(self) -> None:
        self.transport.cmd("MOT1", {"CAL_FOCUSER": "StoreAsMinPos"})


class SestoSenso3(Focuser):
    """SESTO SENSO 3 robotic focusing motor.

    SS3 firmware uses ``GOTO`` instead of ``MOVE_ABS`` and reports its
    position via ``ABS_POS_STEP``. ``is_busy`` is inherited from
    :class:`Focuser`, which combines ``BUSY`` and ``MST`` correctly.
    """

    # ---- motion overrides --------------------------------------------------

    def go_absolute_position(self, position: int) -> None:
        self.transport.cmd("MOT1", {"GOTO": int(position)})

    def get_absolute_position(self) -> int:
        return int(self.transport.get("MOT1", "ABS_POS_STEP"))

    # ---- model / submodel --------------------------------------------------

    def get_sub_model(self) -> str:
        """Pull the ``SubModel = ...`` field out of ``GET_MODEL_SUBMODEL``."""
        response = str(self.transport.srv("GET_MODEL_SUBMODEL"))
        marker = "SubModel = "
        idx = response.find(marker)
        if idx < 0:
            return ""
        idx += len(marker)
        comma = response.find(",", idx)
        return response[idx:comma] if comma >= 0 else response[idx:]

    # ---- recovery delay ----------------------------------------------------

    def set_recovery_delay(self, delay: int) -> None:
        self.transport.set(None, {"RECOVER_DELAY": int(delay)})

    def get_recovery_delay(self) -> int:
        return int(self.transport.get(None, "RECOVER_DELAY"))

    # ---- motor settings ----------------------------------------------------

    def get_motor_settings(self) -> Tuple[MotorRates, MotorCurrents, bool]:
        request = {
            "req": {
                "get": {
                    "MOT1": {
                        "FnRUN_ACC": "",
                        "FnRUN_DEC": "",
                        "FnRUN_SPD": "",
                        "FnRUN_CURR_ACC": "",
                        "FnRUN_CURR_DEC": "",
                        "FnRUN_CURR_SPD": "",
                        "FnRUN_CURR_HOLD": "",
                        "HOLDCURR_STATUS": "",
                    }
                }
            }
        }
        res = self.transport.send_request(request)
        body = res["get"]["MOT1"]
        rates = MotorRates(
            acc_rate=int(body["FnRUN_ACC"]),
            dec_rate=int(body["FnRUN_DEC"]),
            run_speed=int(body["FnRUN_SPD"]),
        )
        currents = MotorCurrents(
            acc_current=int(body["FnRUN_CURR_ACC"]),
            dec_current=int(body["FnRUN_CURR_DEC"]),
            run_current=int(body["FnRUN_CURR_SPD"]),
            hold_current=int(body["FnRUN_CURR_HOLD"]),
        )
        hold_active = int(body["HOLDCURR_STATUS"]) == 1
        return rates, currents, hold_active

    def set_motor_rates(self, rates: MotorRates) -> None:
        self.transport.set(
            "MOT1",
            {
                "FnRUN_ACC": rates.acc_rate,
                "FnRUN_DEC": rates.dec_rate,
                "FnRUN_SPD": rates.run_speed,
            },
        )

    def set_motor_currents(self, currents: MotorCurrents) -> None:
        self.transport.set(
            "MOT1",
            {
                "FnRUN_CURR_ACC": currents.acc_current,
                "FnRUN_CURR_DEC": currents.dec_current,
                "FnRUN_CURR_SPD": currents.run_current,
                "FnRUN_CURR_HOLD": currents.hold_current,
            },
        )

    def set_motor_hold(self, hold: bool) -> None:
        self.transport.set("MOT1", {"HOLDCURR_STATUS": 1 if hold else 0})

    def apply_motor_preset(self, name: str) -> None:
        self.transport.cmd(None, {"RUNPRESET": name})

    # ---- calibration -------------------------------------------------------

    def init_calibration_semi_auto(self) -> None:
        self.transport.cmd("MOT1", {"CAL_FOCUSER": "Init"})

    def go_in_to_find_min_pos(self) -> None:
        self.transport.cmd("MOT1", {"CAL_FOCUSER": "GoInToFindMinPos"})

    def go_out_to_find_max_pos(self) -> None:
        self.transport.cmd("MOT1", {"CAL_FOCUSER": "GoOutToFindMaxPos"})

    def stop_motor(self) -> None:
        self.transport.cmd("MOT1", {"CAL_FOCUSER": "StopMotor"})

    def store_as_min_position(self) -> None:
        self.transport.cmd("MOT1", {"CAL_FOCUSER": "StoreAsMinPos"})

    def store_as_max_position(self) -> None:
        self.transport.cmd("MOT1", {"CAL_FOCUSER": "StoreAsMaxPos"})

    def move_in(self, steps: int) -> None:
        """Calibration-mode incremental inward move."""
        self.transport.cmd("MOT1", {"CAL_FOCUSER": f"MoveIn-{int(steps)}"})

    def move_out(self, steps: int) -> None:
        """Calibration-mode incremental outward move."""
        self.transport.cmd("MOT1", {"CAL_FOCUSER": f"MoveOut-{int(steps)}"})

    def start_auto_calibration(self) -> None:
        """SC variant only — full automatic calibration sweep."""
        self.transport.cmd("MOT1", {"CAL_FOCUSER": "start_auto_cal"})

    def stop_calibration(self) -> None:
        self.transport.cmd("MOT1", {"CAL_FOCUSER": "stop_calib"})
