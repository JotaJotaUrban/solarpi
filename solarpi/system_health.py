from __future__ import annotations

import os
import platform
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


class SystemMonitor:
    def __init__(self, disk_path: Path | str = "/") -> None:
        self.disk_path = Path(disk_path)
        self._lock = threading.Lock()
        self._last_cpu = _read_cpu_sample()

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            cpu_sample = _read_cpu_sample()
            cpu_percent = _cpu_percent(self._last_cpu, cpu_sample)
            if cpu_sample is not None:
                self._last_cpu = cpu_sample

        load = _load_average()
        if cpu_percent is None:
            cpu_percent = load.get("load_percent")

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "platform": platform.platform(),
            "cpu": {
                "percent": _round_or_none(cpu_percent),
                "cores": os.cpu_count(),
                "load_1m": _round_or_none(load.get("load_1m")),
                "load_percent": _round_or_none(load.get("load_percent")),
            },
            "memory": _memory(),
            "storage": _storage(self.disk_path),
            "temperature": _temperature(),
        }


def _read_cpu_sample() -> Optional[Tuple[int, int]]:
    stat_path = Path("/proc/stat")
    if not stat_path.exists():
        return None

    try:
        first_line = stat_path.read_text(encoding="utf-8").splitlines()[0]
    except (OSError, IndexError):
        return None

    parts = first_line.split()
    if not parts or parts[0] != "cpu":
        return None

    try:
        values = [int(value) for value in parts[1:]]
    except ValueError:
        return None

    if len(values) < 4:
        return None

    idle = values[3] + (values[4] if len(values) > 4 else 0)
    total = sum(values)
    return total, idle


def _cpu_percent(
    previous: Optional[Tuple[int, int]],
    current: Optional[Tuple[int, int]],
) -> Optional[float]:
    if previous is None or current is None:
        return None

    previous_total, previous_idle = previous
    current_total, current_idle = current
    total_delta = current_total - previous_total
    idle_delta = current_idle - previous_idle
    if total_delta <= 0:
        return None

    return max(0.0, min(100.0, (1.0 - idle_delta / total_delta) * 100.0))


def _load_average() -> Dict[str, Optional[float]]:
    try:
        load_1m = float(os.getloadavg()[0])
    except (AttributeError, OSError):
        return {"load_1m": None, "load_percent": None}

    cores = os.cpu_count() or 1
    return {
        "load_1m": load_1m,
        "load_percent": max(0.0, load_1m / cores * 100.0),
    }


def _memory() -> Dict[str, Optional[float]]:
    linux_memory = _linux_memory()
    if linux_memory:
        return linux_memory
    return {
        "total_bytes": None,
        "available_bytes": None,
        "used_bytes": None,
        "percent": None,
    }


def _linux_memory() -> Optional[Dict[str, Optional[float]]]:
    meminfo_path = Path("/proc/meminfo")
    if not meminfo_path.exists():
        return None

    try:
        meminfo = _parse_meminfo(meminfo_path.read_text(encoding="utf-8"))
    except OSError:
        return None

    total = meminfo.get("MemTotal")
    available = meminfo.get("MemAvailable")
    if total is None or available is None or total <= 0:
        return None

    used = max(0, total - available)
    return {
        "total_bytes": total,
        "available_bytes": available,
        "used_bytes": used,
        "percent": round(used / total * 100.0, 1),
    }


def _parse_meminfo(content: str) -> Dict[str, int]:
    values: Dict[str, int] = {}
    for line in content.splitlines():
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        parts = raw_value.strip().split()
        if not parts:
            continue
        try:
            amount = int(parts[0])
        except ValueError:
            continue
        unit = parts[1].lower() if len(parts) > 1 else ""
        values[key] = amount * 1024 if unit == "kb" else amount
    return values


def _storage(path: Path) -> Dict[str, Optional[float]]:
    target = _existing_path(path)
    try:
        usage = shutil.disk_usage(target)
    except OSError:
        return {
            "path": str(target),
            "total_bytes": None,
            "free_bytes": None,
            "used_bytes": None,
            "percent": None,
        }

    percent = usage.used / usage.total * 100.0 if usage.total > 0 else None
    return {
        "path": str(target),
        "total_bytes": usage.total,
        "free_bytes": usage.free,
        "used_bytes": usage.used,
        "percent": _round_or_none(percent),
    }


def _existing_path(path: Path) -> Path:
    current = path.resolve()
    while not current.exists() and current.parent != current:
        current = current.parent
    return current


def _temperature() -> Dict[str, Optional[float]]:
    for path in _temperature_paths():
        value = _read_temperature(path)
        if value is not None:
            return {
                "celsius": round(value, 1),
                "source": str(path),
            }

    return {
        "celsius": None,
        "source": None,
    }


def _temperature_paths() -> list[Path]:
    paths = [Path("/sys/class/thermal/thermal_zone0/temp")]
    hwmon_root = Path("/sys/class/hwmon")
    if hwmon_root.exists():
        paths.extend(sorted(hwmon_root.glob("hwmon*/temp*_input")))
    return paths


def _read_temperature(path: Path) -> Optional[float]:
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None

    try:
        value = float(raw)
    except ValueError:
        return None

    return value / 1000.0 if value > 200 else value


def _round_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return round(float(value), 1)
    except (TypeError, ValueError):
        return None
