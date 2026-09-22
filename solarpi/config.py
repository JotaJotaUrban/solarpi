from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_env_file(ROOT_DIR / ".env")


def _env_str(name: str, default: str) -> str:
    return os.environ.get(name, default).strip()


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return int(value)


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return float(value)


@dataclass(frozen=True)
class Settings:
    inverter_ip: str
    inverter_serial: int
    inverter_port: int
    modbus_slave_id: int
    socket_timeout_seconds: float
    poll_interval_seconds: float
    database_path: Path
    api_host: str
    api_port: int
    weather_cache_seconds: float
    weather_update_seconds: float
    weather_timeout_seconds: float
    timezone_name: str
    totals_max_gap_seconds: float
    summary_update_seconds: float
    system_update_seconds: float
    backup_token: str = ""


def load_settings() -> Settings:
    database_path = Path(
        _env_str("SOLARPI_DATABASE", str(ROOT_DIR / "data" / "solarpi.sqlite3"))
    )
    if not database_path.is_absolute():
        database_path = ROOT_DIR / database_path

    return Settings(
        inverter_ip=_env_str("SOLARPI_INVERTER_IP", "192.168.1.137"),
        inverter_serial=_env_int("SOLARPI_INVERTER_SERIAL", 3594884342),
        inverter_port=_env_int("SOLARPI_INVERTER_PORT", 8899),
        modbus_slave_id=_env_int("SOLARPI_MODBUS_SLAVE_ID", 1),
        socket_timeout_seconds=_env_float("SOLARPI_SOCKET_TIMEOUT", 10.0),
        poll_interval_seconds=_env_float("SOLARPI_POLL_INTERVAL", 4.0),
        database_path=database_path,
        api_host=_env_str("SOLARPI_API_HOST", "0.0.0.0"),
        api_port=_env_int("SOLARPI_API_PORT", 80),
        weather_cache_seconds=_env_float("SOLARPI_WEATHER_CACHE_SECONDS", 600.0),
        weather_update_seconds=_env_float("SOLARPI_WEATHER_UPDATE_SECONDS", 600.0),
        weather_timeout_seconds=_env_float("SOLARPI_WEATHER_TIMEOUT", 4.0),
        timezone_name=_env_str("SOLARPI_TIMEZONE", "Europe/Madrid"),
        totals_max_gap_seconds=_env_float("SOLARPI_TOTALS_MAX_GAP_SECONDS", 300.0),
        summary_update_seconds=_env_float("SOLARPI_SUMMARY_UPDATE_SECONDS", 60.0),
        system_update_seconds=_env_float("SOLARPI_SYSTEM_UPDATE_SECONDS", 30.0),
        backup_token=_env_str("SOLARPI_BACKUP_TOKEN", ""),
    )
