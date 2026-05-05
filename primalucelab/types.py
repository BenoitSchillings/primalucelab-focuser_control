from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MotorRates:
    """Motor acceleration / run / deceleration rates (1-10)."""

    acc_rate: int = 0
    run_speed: int = 0
    dec_rate: int = 0


@dataclass
class MotorCurrents:
    """Motor currents.

    `acc_current`, `run_current`, `dec_current` are 1-10.
    `hold_current` is 1-5.
    """

    acc_current: int = 0
    run_current: int = 0
    dec_current: int = 0
    hold_current: int = 0
