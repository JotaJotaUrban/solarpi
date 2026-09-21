from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from .config import Settings
from .models import InverterSnapshot


START_REGISTER = 0x0096
END_REGISTER = 0x00BF
QUANTITY = END_REGISTER - START_REGISTER + 1


def signed16(value: int) -> int:
    return value - 65536 if value > 32767 else value


def register_at(data: Sequence[int], address: int) -> int:
    return int(data[address - START_REGISTER])


BATTERY_IDLE_DEADBAND_W = 30


def battery_mode_from_power(power_w: int) -> str:
    if power_w > BATTERY_IDLE_DEADBAND_W:
        return "discharging"
    if power_w < -BATTERY_IDLE_DEADBAND_W:
        return "charging"
    return "standby"


def map_registers(
    data: Sequence[int],
    timestamp: Optional[datetime] = None,
    source: str = "deye",
) -> InverterSnapshot:
    if len(data) < QUANTITY:
        raise ValueError("Expected at least %s registers, got %s" % (QUANTITY, len(data)))

    pv1 = register_at(data, 0x00BA)
    pv2 = register_at(data, 0x00BB)
    battery_status = register_at(data, 0x00BD)
    battery_power = signed16(register_at(data, 0x00BE))

    return InverterSnapshot(
        timestamp=timestamp or datetime.now(timezone.utc),
        source=source,
        house_power_w=register_at(data, 0x00B2),
        pv1_power_w=pv1,
        pv2_power_w=pv2,
        solar_power_w=pv1 + pv2,
        battery_soc_percent=register_at(data, 0x00B8),
        battery_voltage_v=round(register_at(data, 0x00B7) * 0.01, 2),
        battery_current_a=round(signed16(register_at(data, 0x00BF)) * 0.01, 2),
        battery_power_w=battery_power,
        battery_status_code=battery_status,
        battery_mode=battery_mode_from_power(battery_power),
        grid_power_w=signed16(register_at(data, 0x00A9)),
        grid_voltage_v=round(register_at(data, 0x0096) * 0.1, 1),
        inverter_power_w=signed16(register_at(data, 0x00AF)),
        raw_register_start=START_REGISTER,
        raw_registers=[int(value) for value in data[:QUANTITY]],
    )


class DeyeReader:
    def __init__(self, settings: Settings) -> None:
        try:
            from pysolarmanv5 import PySolarmanV5
        except ImportError as exc:
            raise RuntimeError(
                "Missing dependency pysolarmanv5. Install requirements.txt first."
            ) from exc

        self._settings = settings
        self._solarman_cls = PySolarmanV5
        self._client: Optional[Any] = None

    def read_snapshot(self) -> InverterSnapshot:
        client = self._connect()
        try:
            registers = client.read_holding_registers(
                register_addr=START_REGISTER,
                quantity=QUANTITY,
            )
        except Exception:
            self.disconnect()
            raise
        return map_registers(registers)

    def disconnect(self) -> None:
        if self._client is None:
            return

        try:
            self._client.disconnect()
        finally:
            self._client = None

    def _connect(self) -> Any:
        if self._client is None:
            settings = self._settings
            self._client = self._solarman_cls(
                settings.inverter_ip,
                settings.inverter_serial,
                port=settings.inverter_port,
                mb_slave_id=settings.modbus_slave_id,
                socket_timeout=settings.socket_timeout_seconds,
                auto_reconnect=True,
            )
        return self._client
