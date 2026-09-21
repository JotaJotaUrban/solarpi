from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List


@dataclass
class InverterSnapshot:
    timestamp: datetime
    source: str
    house_power_w: int
    pv1_power_w: int
    pv2_power_w: int
    solar_power_w: int
    battery_soc_percent: int
    battery_voltage_v: float
    battery_current_a: float
    battery_power_w: int
    battery_status_code: int
    battery_mode: str
    grid_power_w: int
    grid_voltage_v: float
    inverter_power_w: int
    raw_register_start: int
    raw_registers: List[int]

    @property
    def age_seconds(self) -> float:
        timestamp = self.timestamp
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - timestamp).total_seconds())

    @property
    def grid_direction(self) -> str:
        if self.grid_power_w > 0:
            return "importing"
        if self.grid_power_w < 0:
            return "exporting"
        return "idle"

    def to_dict(self, include_raw: bool = False) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "age_seconds": round(self.age_seconds, 3),
            "house_power_w": self.house_power_w,
            "pv1_power_w": self.pv1_power_w,
            "pv2_power_w": self.pv2_power_w,
            "solar_power_w": self.solar_power_w,
            "battery_soc_percent": self.battery_soc_percent,
            "battery_voltage_v": self.battery_voltage_v,
            "battery_current_a": self.battery_current_a,
            "battery_power_w": self.battery_power_w,
            "battery_status_code": self.battery_status_code,
            "battery_mode": self.battery_mode,
            "grid_power_w": self.grid_power_w,
            "grid_direction": self.grid_direction,
            "grid_voltage_v": self.grid_voltage_v,
            "inverter_power_w": self.inverter_power_w,
        }

        if include_raw:
            payload["raw_register_start"] = self.raw_register_start
            payload["raw_registers"] = self.raw_registers

        return payload

