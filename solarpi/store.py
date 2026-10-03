from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from .models import InverterSnapshot


ENERGY_SUMMARY_VERSION = 3


class SnapshotStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def init_db(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    source TEXT NOT NULL,
                    house_power_w INTEGER NOT NULL,
                    pv1_power_w INTEGER NOT NULL,
                    pv2_power_w INTEGER NOT NULL,
                    solar_power_w INTEGER NOT NULL,
                    battery_soc_percent INTEGER NOT NULL,
                    battery_voltage_v REAL NOT NULL,
                    battery_current_a REAL NOT NULL,
                    battery_power_w INTEGER NOT NULL,
                    battery_status_code INTEGER NOT NULL,
                    battery_mode TEXT NOT NULL,
                    grid_power_w INTEGER NOT NULL,
                    grid_voltage_v REAL NOT NULL,
                    inverter_power_w INTEGER NOT NULL,
                    raw_register_start INTEGER NOT NULL,
                    raw_registers TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_snapshots_ts ON snapshots(ts)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_snapshots_ts_id ON snapshots(ts, id)"
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_snapshots_ts_house
                ON snapshots(ts, house_power_w)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_snapshots_ts_solar
                ON snapshots(ts, solar_power_w)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_snapshots_ts_grid
                ON snapshots(ts, grid_power_w)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS weather_current (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    location_key TEXT NOT NULL,
                    observed_at TEXT,
                    fetched_at TEXT NOT NULL,
                    temperature_c REAL,
                    humidity_percent REAL,
                    wind_speed_kmh REAL,
                    weather_code INTEGER,
                    weather_label TEXT,
                    condition TEXT,
                    is_day INTEGER,
                    cloud_cover_percent REAL,
                    precipitation_mm REAL,
                    rain_mm REAL,
                    snowfall_cm REAL,
                    raw_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_weather_current_location_fetched
                ON weather_current(location_key, fetched_at)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_weather_current_location_fetched_desc
                ON weather_current(location_key, fetched_at DESC, id DESC)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS weather_daily_forecasts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    location_key TEXT NOT NULL,
                    forecast_date TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    weather_code INTEGER,
                    weather_label TEXT,
                    condition TEXT,
                    temperature_min_c REAL,
                    temperature_max_c REAL,
                    precipitation_probability_percent REAL,
                    precipitation_sum_mm REAL,
                    rain_sum_mm REAL,
                    snowfall_sum_cm REAL,
                    wind_speed_max_kmh REAL,
                    shortwave_radiation_sum_mj_m2 REAL,
                    sunshine_duration_seconds REAL,
                    daylight_duration_seconds REAL,
                    raw_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_weather_daily_location_date
                ON weather_daily_forecasts(location_key, forecast_date, fetched_at)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_weather_daily_location_date_fetched_desc
                ON weather_daily_forecasts(location_key, forecast_date, fetched_at DESC, id DESC)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS solar_daily_predictions (
                    target_date TEXT PRIMARY KEY,
                    location_key TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    base_kwh REAL,
                    base_source TEXT,
                    base_sample_count INTEGER NOT NULL,
                    weather_factor REAL,
                    correction_factor REAL,
                    predicted_kwh REAL,
                    actual_kwh REAL,
                    actualized_at TEXT,
                    error_ratio REAL,
                    method_version TEXT NOT NULL,
                    details_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS solar_prediction_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS economics_balance_cache (
                    start_date TEXT PRIMARY KEY,
                    generated_at TEXT NOT NULL,
                    raw_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS energy_summary_cache (
                    cache_key TEXT PRIMARY KEY,
                    generated_at TEXT NOT NULL,
                    raw_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_energy_summaries (
                    day TEXT NOT NULL,
                    timezone TEXT NOT NULL,
                    generated_at TEXT NOT NULL,
                    from_ts TEXT NOT NULL,
                    to_ts TEXT NOT NULL,
                    sample_count INTEGER NOT NULL,
                    max_gap_seconds REAL NOT NULL,
                    production_kwh REAL NOT NULL,
                    consumption_kwh REAL NOT NULL,
                    grid_import_kwh REAL NOT NULL,
                    grid_export_kwh REAL NOT NULL,
                    raw_json TEXT NOT NULL,
                    PRIMARY KEY (day, timezone)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_daily_energy_summaries_timezone_day
                ON daily_energy_summaries(timezone, day)
                """
            )
            conn.execute("DROP TABLE IF EXISTS energy_period_summaries")
            conn.execute("DROP TABLE IF EXISTS power_peak_summaries")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS system_health_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    generated_at TEXT NOT NULL,
                    platform TEXT,
                    cpu_percent REAL,
                    cpu_cores INTEGER,
                    cpu_load_1m REAL,
                    cpu_load_percent REAL,
                    memory_total_bytes INTEGER,
                    memory_available_bytes INTEGER,
                    memory_used_bytes INTEGER,
                    memory_percent REAL,
                    storage_path TEXT,
                    storage_total_bytes INTEGER,
                    storage_free_bytes INTEGER,
                    storage_used_bytes INTEGER,
                    storage_percent REAL,
                    temperature_celsius REAL,
                    temperature_source TEXT,
                    raw_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_system_health_generated
                ON system_health_snapshots(generated_at)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_system_health_generated_desc
                ON system_health_snapshots(generated_at DESC, id DESC)
                """
            )

    def insert_snapshot(self, snapshot: InverterSnapshot) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO snapshots (
                    ts, source, house_power_w, pv1_power_w, pv2_power_w,
                    solar_power_w, battery_soc_percent, battery_voltage_v,
                    battery_current_a, battery_power_w, battery_status_code,
                    battery_mode, grid_power_w, grid_voltage_v,
                    inverter_power_w, raw_register_start, raw_registers
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.timestamp.isoformat(),
                    snapshot.source,
                    snapshot.house_power_w,
                    snapshot.pv1_power_w,
                    snapshot.pv2_power_w,
                    snapshot.solar_power_w,
                    snapshot.battery_soc_percent,
                    snapshot.battery_voltage_v,
                    snapshot.battery_current_a,
                    snapshot.battery_power_w,
                    snapshot.battery_status_code,
                    snapshot.battery_mode,
                    snapshot.grid_power_w,
                    snapshot.grid_voltage_v,
                    snapshot.inverter_power_w,
                    snapshot.raw_register_start,
                    json.dumps(snapshot.raw_registers),
                ),
            )

    def latest(self) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT ts, source, house_power_w, pv1_power_w, pv2_power_w,
                    solar_power_w, battery_soc_percent, battery_voltage_v,
                    battery_current_a, battery_power_w, battery_status_code,
                    battery_mode, grid_power_w, grid_voltage_v,
                    inverter_power_w
                FROM snapshots
                ORDER BY ts DESC
                LIMIT 1
                """
            ).fetchone()
        return dict(row) if row else None

    def history(self, minutes: int = 60, limit: int = 720) -> List[Dict[str, Any]]:
        if minutes < 1 or limit < 1:
            raise ValueError("minutes and limit must be positive")
        end = datetime.now(timezone.utc)
        cutoff = end - timedelta(minutes=minutes)
        with self._connection() as conn:
            rows = conn.execute(
                """
                WITH ranked AS (
                    SELECT ts, source, house_power_w, pv1_power_w, pv2_power_w,
                        solar_power_w, battery_soc_percent, battery_power_w,
                        grid_power_w, inverter_power_w,
                        ROW_NUMBER() OVER (ORDER BY ts, id) AS position,
                        COUNT(*) OVER () AS total
                    FROM snapshots
                    WHERE ts >= :start AND ts <= :end
                )
                SELECT ts, source, house_power_w, pv1_power_w, pv2_power_w,
                    solar_power_w, battery_soc_percent, battery_power_w,
                    grid_power_w, inverter_power_w
                FROM ranked
                -- Evenly sample the whole interval, retaining both endpoints.
                WHERE total <= :limit
                    OR (:limit = 1 AND position = total)
                    OR (:limit > 1 AND (
                        position = 1
                        OR (position - 1) * (:limit - 1) / (total - 1)
                           > (position - 2) * (:limit - 1) / (total - 1)
                    ))
                ORDER BY position
                """,
                {"start": cutoff.isoformat(), "end": end.isoformat(), "limit": limit},
            ).fetchall()
        return [dict(row) for row in rows]

    def energy_totals(
        self,
        start: datetime,
        end: datetime,
        latest: Optional[InverterSnapshot] = None,
        max_gap_seconds: float = 300.0,
    ) -> Dict[str, Any]:
        start_utc = _as_utc(start)
        end_utc = _as_utc(end)
        if end_utc <= start_utc:
            return _empty_energy_totals(start_utc, end_utc, max_gap_seconds)

        with self._connection() as conn:
            previous = conn.execute(
                """
                SELECT ts, house_power_w, solar_power_w, grid_power_w
                FROM snapshots
                WHERE ts < ?
                ORDER BY ts DESC
                LIMIT 1
                """,
                (start_utc.isoformat(),),
            ).fetchone()
            rows = conn.execute(
                """
                SELECT ts, house_power_w, solar_power_w, grid_power_w
                FROM snapshots
                WHERE ts >= ? AND ts <= ?
                ORDER BY ts ASC
                """,
                (start_utc.isoformat(), end_utc.isoformat()),
            ).fetchall()

        points = [dict(row) for row in rows]
        if previous:
            points.insert(0, dict(previous))
        if latest is not None:
            latest_ts = _as_utc(latest.timestamp)
            if start_utc <= latest_ts <= end_utc:
                points.append(
                    {
                        "ts": latest_ts.isoformat(),
                        "house_power_w": latest.house_power_w,
                        "solar_power_w": latest.solar_power_w,
                        "grid_power_w": latest.grid_power_w,
                    }
                )

        normalized = _normalize_energy_points(points)
        return {
            "from": start_utc.isoformat(),
            "to": end_utc.isoformat(),
            "sample_count": sum(1 for timestamp, _ in normalized if start_utc <= timestamp <= end_utc),
            "max_gap_seconds": max_gap_seconds,
            "production_kwh": _integrate_kwh(
                normalized,
                start_utc,
                end_utc,
                lambda point: max(0.0, float(point.get("solar_power_w") or 0)),
                max_gap_seconds,
            ),
            "consumption_kwh": _integrate_kwh(
                normalized,
                start_utc,
                end_utc,
                lambda point: max(0.0, float(point.get("house_power_w") or 0)),
                max_gap_seconds,
            ),
            "grid_import_kwh": _integrate_kwh(
                normalized,
                start_utc,
                end_utc,
                lambda point: max(0.0, float(point.get("grid_power_w") or 0)),
                max_gap_seconds,
            ),
            "grid_export_kwh": _integrate_kwh(
                normalized,
                start_utc,
                end_utc,
                lambda point: max(0.0, -float(point.get("grid_power_w") or 0)),
                max_gap_seconds,
            ),
        }

    def energy_totals_fast(
        self,
        start: datetime,
        end: datetime,
        latest: Optional[InverterSnapshot] = None,
        max_gap_seconds: float = 300.0,
    ) -> Dict[str, Any]:
        start_utc = _as_utc(start)
        end_utc = _as_utc(end)
        if end_utc <= start_utc:
            return _empty_energy_totals(start_utc, end_utc, max_gap_seconds)

        latest_ts: Optional[str] = None
        latest_house: Optional[int] = None
        latest_solar: Optional[int] = None
        latest_grid: Optional[int] = None
        if latest is not None:
            latest_dt = _as_utc(latest.timestamp)
            if start_utc <= latest_dt <= end_utc:
                latest_ts = latest_dt.isoformat()
                latest_house = latest.house_power_w
                latest_solar = latest.solar_power_w
                latest_grid = latest.grid_power_w

        start_iso = start_utc.isoformat()
        end_iso = end_utc.isoformat()
        max_gap = max(1.0, float(max_gap_seconds))

        with self._connection() as conn:
            row = conn.execute(
                """
                WITH base AS (
                    SELECT 0 AS priority, ts, house_power_w, solar_power_w, grid_power_w
                    FROM (
                        SELECT ts, house_power_w, solar_power_w, grid_power_w
                        FROM snapshots
                        WHERE ts < ?
                        ORDER BY ts DESC
                        LIMIT 1
                    )
                    UNION ALL
                    SELECT 1 AS priority, ts, house_power_w, solar_power_w, grid_power_w
                    FROM snapshots
                    WHERE ts >= ? AND ts <= ?
                    UNION ALL
                    SELECT 2 AS priority, ? AS ts, ? AS house_power_w,
                        ? AS solar_power_w, ? AS grid_power_w
                    WHERE ? IS NOT NULL
                ),
                ranked AS (
                    SELECT
                        ts,
                        house_power_w,
                        solar_power_w,
                        grid_power_w,
                        ROW_NUMBER() OVER (PARTITION BY ts ORDER BY priority DESC) AS rn
                    FROM base
                ),
                points AS (
                    SELECT ts, house_power_w, solar_power_w, grid_power_w
                    FROM ranked
                    WHERE rn = 1
                ),
                ordered AS (
                    SELECT
                        ts,
                        house_power_w,
                        solar_power_w,
                        grid_power_w,
                        LEAD(ts) OVER (ORDER BY ts) AS next_ts
                    FROM points
                ),
                segments AS (
                    SELECT
                        MAX((julianday(ts) - 2440587.5) * 86400.0, ?) AS segment_start,
                        MIN((julianday(COALESCE(next_ts, ?)) - 2440587.5) * 86400.0, ?) AS segment_end,
                        house_power_w,
                        solar_power_w,
                        grid_power_w
                    FROM ordered
                )
                SELECT
                    (
                        SELECT COUNT(*)
                        FROM points
                        WHERE ts >= ? AND ts <= ?
                    ) AS sample_count,
                    ROUND(COALESCE(SUM(
                        CASE
                            WHEN segment_end > segment_start
                            THEN MAX(0.0, solar_power_w) * MIN(segment_end - segment_start, ?) / 3600.0
                            ELSE 0.0
                        END
                    ), 0.0) / 1000.0, 3) AS production_kwh,
                    ROUND(COALESCE(SUM(
                        CASE
                            WHEN segment_end > segment_start
                            THEN MAX(0.0, house_power_w) * MIN(segment_end - segment_start, ?) / 3600.0
                            ELSE 0.0
                        END
                    ), 0.0) / 1000.0, 3) AS consumption_kwh,
                    ROUND(COALESCE(SUM(
                        CASE
                            WHEN segment_end > segment_start
                            THEN MAX(0.0, grid_power_w) * MIN(segment_end - segment_start, ?) / 3600.0
                            ELSE 0.0
                        END
                    ), 0.0) / 1000.0, 3) AS grid_import_kwh,
                    ROUND(COALESCE(SUM(
                        CASE
                            WHEN segment_end > segment_start
                            THEN MAX(0.0, -grid_power_w) * MIN(segment_end - segment_start, ?) / 3600.0
                            ELSE 0.0
                        END
                    ), 0.0) / 1000.0, 3) AS grid_export_kwh
                FROM segments
                """,
                (
                    start_iso,
                    start_iso,
                    end_iso,
                    latest_ts,
                    latest_house,
                    latest_solar,
                    latest_grid,
                    latest_ts,
                    start_utc.timestamp(),
                    end_iso,
                    end_utc.timestamp(),
                    start_iso,
                    end_iso,
                    max_gap,
                    max_gap,
                    max_gap,
                    max_gap,
                ),
            ).fetchone()

        return {
            "from": start_utc.isoformat(),
            "to": end_utc.isoformat(),
            "sample_count": int(row["sample_count"] or 0) if row else 0,
            "max_gap_seconds": max_gap_seconds,
            "calculation_method": "capped_interval",
            "production_kwh": float(row["production_kwh"] or 0.0) if row else 0.0,
            "consumption_kwh": float(row["consumption_kwh"] or 0.0) if row else 0.0,
            "grid_import_kwh": float(row["grid_import_kwh"] or 0.0) if row else 0.0,
            "grid_export_kwh": float(row["grid_export_kwh"] or 0.0) if row else 0.0,
        }

    def energy_totals_sampled(
        self,
        start: datetime,
        end: datetime,
        sample_seconds: float,
        max_gap_seconds: float = 300.0,
    ) -> Dict[str, Any]:
        start_utc = _as_utc(start)
        end_utc = _as_utc(end)
        if end_utc <= start_utc:
            return _empty_energy_totals(start_utc, end_utc, max_gap_seconds)

        interval_seconds = max(1.0, min(float(sample_seconds), float(max_gap_seconds)))
        interval_hours = interval_seconds / 3600.0

        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS sample_count,
                    ROUND(COALESCE(SUM(
                        CASE WHEN solar_power_w > 0 THEN solar_power_w ELSE 0 END
                    ), 0.0) * ? / 1000.0, 3) AS production_kwh,
                    ROUND(COALESCE(SUM(
                        CASE WHEN house_power_w > 0 THEN house_power_w ELSE 0 END
                    ), 0.0) * ? / 1000.0, 3) AS consumption_kwh,
                    ROUND(COALESCE(SUM(
                        CASE WHEN grid_power_w > 0 THEN grid_power_w ELSE 0 END
                    ), 0.0) * ? / 1000.0, 3) AS grid_import_kwh,
                    ROUND(COALESCE(SUM(
                        CASE WHEN grid_power_w < 0 THEN -grid_power_w ELSE 0 END
                    ), 0.0) * ? / 1000.0, 3) AS grid_export_kwh
                FROM snapshots
                WHERE ts >= ? AND ts <= ?
                """,
                (
                    interval_hours,
                    interval_hours,
                    interval_hours,
                    interval_hours,
                    start_utc.isoformat(),
                    end_utc.isoformat(),
                ),
            ).fetchone()

        return {
            "from": start_utc.isoformat(),
            "to": end_utc.isoformat(),
            "sample_count": int(row["sample_count"] or 0) if row else 0,
            "max_gap_seconds": max_gap_seconds,
            "sample_seconds": interval_seconds,
            "calculation_method": "sampled_poll_interval",
            "production_kwh": float(row["production_kwh"] or 0.0) if row else 0.0,
            "consumption_kwh": float(row["consumption_kwh"] or 0.0) if row else 0.0,
            "grid_import_kwh": float(row["grid_import_kwh"] or 0.0) if row else 0.0,
            "grid_export_kwh": float(row["grid_export_kwh"] or 0.0) if row else 0.0,
        }

    def energy_totals_daily_summarized(
        self,
        start: datetime,
        end: datetime,
        timezone_name: str,
        tz: tzinfo,
        latest: Optional[InverterSnapshot] = None,
        max_gap_seconds: float = 300.0,
    ) -> Dict[str, Any]:
        start_utc = _as_utc(start)
        end_utc = _as_utc(end)
        if end_utc <= start_utc:
            return _empty_energy_totals(start_utc, end_utc, max_gap_seconds)

        totals = _empty_energy_totals(start_utc, end_utc, max_gap_seconds)
        totals["calculation_method"] = "daily_summary_capped_interval"
        totals["daily_summary_days"] = 0
        totals["live_segments"] = 0

        first_snapshot = self._first_valid_snapshot_timestamp(start_utc, end_utc)
        if first_snapshot is None and latest is not None:
            latest_dt = _as_utc(latest.timestamp)
            if start_utc <= latest_dt <= end_utc:
                first_snapshot = latest_dt
        if first_snapshot is None:
            return totals

        cursor = max(
            start.astimezone(tz),
            first_snapshot.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0),
        )
        end_local = end.astimezone(tz)
        while cursor < end_local:
            day_start = cursor.replace(hour=0, minute=0, second=0, microsecond=0)
            next_day = day_start + timedelta(days=1)
            segment_end = min(next_day, end_local)
            is_full_local_day = cursor == day_start and segment_end == next_day

            if is_full_local_day:
                day_payload, _ = self.ensure_daily_energy_summary(
                    target_day=cursor.date(),
                    timezone_name=timezone_name,
                    tz=tz,
                    max_gap_seconds=max_gap_seconds,
                )
                _add_energy_totals(totals, day_payload)
                totals["daily_summary_days"] += 1
            else:
                segment_totals = self.energy_totals_fast(
                    start=cursor,
                    end=segment_end,
                    latest=latest,
                    max_gap_seconds=max_gap_seconds,
                )
                _add_energy_totals(totals, segment_totals)
                totals["live_segments"] += 1

            cursor = segment_end

        _round_energy_totals(totals)
        return totals

    def _first_valid_snapshot_timestamp(
        self,
        start_utc: datetime,
        end_utc: datetime,
    ) -> Optional[datetime]:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT ts
                FROM snapshots
                WHERE ts >= ? AND ts <= ?
                ORDER BY ts ASC
                LIMIT 1
                """,
                (start_utc.isoformat(), end_utc.isoformat()),
            ).fetchone()
        if not row:
            return None
        return _parse_ts(row["ts"])

    def daily_energy_summary(
        self,
        target_day: date,
        timezone_name: str,
        max_gap_seconds: float,
    ) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT raw_json, max_gap_seconds
                FROM daily_energy_summaries
                WHERE day = ? AND timezone = ?
                """,
                (target_day.isoformat(), timezone_name),
            ).fetchone()
        if not row:
            return None
        if abs(float(row["max_gap_seconds"]) - float(max_gap_seconds)) > 0.001:
            return None
        payload = _json_loads(row["raw_json"])
        if payload.get("summary_version") != ENERGY_SUMMARY_VERSION:
            return None
        return payload

    def ensure_daily_energy_summary(
        self,
        target_day: date,
        timezone_name: str,
        tz: tzinfo,
        max_gap_seconds: float,
    ) -> Tuple[Dict[str, Any], bool]:
        cached = self.daily_energy_summary(
            target_day=target_day,
            timezone_name=timezone_name,
            max_gap_seconds=max_gap_seconds,
        )
        if cached is not None:
            return cached, False
        return (
            self.rebuild_daily_energy_summary(
                target_day=target_day,
                timezone_name=timezone_name,
                tz=tz,
                max_gap_seconds=max_gap_seconds,
            ),
            True,
        )

    def rebuild_daily_energy_summary(
        self,
        target_day: date,
        timezone_name: str,
        tz: tzinfo,
        max_gap_seconds: float,
    ) -> Dict[str, Any]:
        start = datetime(
            target_day.year,
            target_day.month,
            target_day.day,
            tzinfo=tz,
        )
        end = start + timedelta(days=1)
        totals = self.energy_totals_fast(
            start=start,
            end=end,
            max_gap_seconds=max_gap_seconds,
        )
        payload = {
            **totals,
            "day": target_day.isoformat(),
            "timezone": timezone_name,
            "generated_at": datetime.now(tz).isoformat(),
            "calculation_method": "daily_summary_capped_interval",
            "summary_version": ENERGY_SUMMARY_VERSION,
        }
        self.save_daily_energy_summary(payload)
        return payload

    def save_daily_energy_summary(self, payload: Dict[str, Any]) -> None:
        target_day = str(payload.get("day") or "").strip()
        timezone_name = str(payload.get("timezone") or "").strip()
        generated_at = str(payload.get("generated_at") or "").strip()
        if not target_day or not timezone_name or not generated_at:
            return

        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO daily_energy_summaries (
                    day, timezone, generated_at, from_ts, to_ts, sample_count,
                    max_gap_seconds, production_kwh, consumption_kwh,
                    grid_import_kwh, grid_export_kwh, raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    target_day,
                    timezone_name,
                    generated_at,
                    str(payload.get("from") or ""),
                    str(payload.get("to") or ""),
                    int(payload.get("sample_count") or 0),
                    float(payload.get("max_gap_seconds") or 0.0),
                    float(payload.get("production_kwh") or 0.0),
                    float(payload.get("consumption_kwh") or 0.0),
                    float(payload.get("grid_import_kwh") or 0.0),
                    float(payload.get("grid_export_kwh") or 0.0),
                    _json_dumps(payload),
                ),
            )

    def power_peaks(
        self,
        start: datetime,
        end: datetime,
        latest: Optional[InverterSnapshot] = None,
    ) -> Dict[str, Any]:
        start_utc = _as_utc(start)
        end_utc = _as_utc(end)
        if end_utc <= start_utc:
            return _empty_power_peaks(start_utc, end_utc)

        with self._connection() as conn:
            sample_count = conn.execute(
                """
                SELECT COUNT(*)
                FROM snapshots
                WHERE ts >= ? AND ts <= ?
                """,
                (start_utc.isoformat(), end_utc.isoformat()),
            ).fetchone()[0]
            demand_row = conn.execute(
                """
                SELECT ts, house_power_w
                FROM snapshots
                WHERE ts >= ? AND ts <= ?
                ORDER BY house_power_w DESC, ts ASC
                LIMIT 1
                """,
                (start_utc.isoformat(), end_utc.isoformat()),
            ).fetchone()
            production_row = conn.execute(
                """
                SELECT ts, solar_power_w
                FROM snapshots
                WHERE ts >= ? AND ts <= ?
                ORDER BY solar_power_w DESC, ts ASC
                LIMIT 1
                """,
                (start_utc.isoformat(), end_utc.isoformat()),
            ).fetchone()
            grid_import_row = conn.execute(
                """
                SELECT ts, grid_power_w
                FROM snapshots
                WHERE ts >= ? AND ts <= ? AND grid_power_w > 0
                ORDER BY grid_power_w DESC, ts ASC
                LIMIT 1
                """,
                (start_utc.isoformat(), end_utc.isoformat()),
            ).fetchone()
            grid_export_row = conn.execute(
                """
                SELECT ts, grid_power_w
                FROM snapshots
                WHERE ts >= ? AND ts <= ? AND grid_power_w < 0
                ORDER BY grid_power_w ASC, ts ASC
                LIMIT 1
                """,
                (start_utc.isoformat(), end_utc.isoformat()),
            ).fetchone()

        demand = _peak_from_row(demand_row, "house_power_w")
        production = _peak_from_row(production_row, "solar_power_w")
        grid_import = _peak_from_row(grid_import_row, "grid_power_w")
        grid_export = _peak_from_row(grid_export_row, "grid_power_w", invert=True)

        if latest is not None:
            latest_ts = _as_utc(latest.timestamp)
            if start_utc <= latest_ts <= end_utc:
                sample_count += 1
                demand = _max_peak(
                    demand,
                    {
                        "value_w": max(0, int(latest.house_power_w)),
                        "timestamp": latest_ts.isoformat(),
                    },
                )
                production = _max_peak(
                    production,
                    {
                        "value_w": max(0, int(latest.solar_power_w)),
                        "timestamp": latest_ts.isoformat(),
                    },
                )
                if latest.grid_power_w > 0:
                    grid_import = _max_peak(
                        grid_import,
                        {
                            "value_w": int(latest.grid_power_w),
                            "timestamp": latest_ts.isoformat(),
                        },
                    )
                elif latest.grid_power_w < 0:
                    grid_export = _max_peak(
                        grid_export,
                        {
                            "value_w": abs(int(latest.grid_power_w)),
                            "timestamp": latest_ts.isoformat(),
                        },
                    )

        return {
            "from": start_utc.isoformat(),
            "to": end_utc.isoformat(),
            "sample_count": sample_count,
            "demand_peak": demand,
            "production_peak": production,
            "grid_import_peak": grid_import,
            "grid_export_peak": grid_export,
        }

    def persist_weather_payload(
        self,
        payload: Dict[str, Any],
        location_key: str = "borriol",
    ) -> None:
        location = payload.get("location")
        if not isinstance(location, dict):
            return

        key = str(location.get("id") or "").strip().lower()
        if key != location_key:
            return

        fetched_at = str(payload.get("fetched_at") or datetime.now(timezone.utc).isoformat())
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO weather_current (
                    location_key, observed_at, fetched_at, temperature_c,
                    humidity_percent, wind_speed_kmh, weather_code,
                    weather_label, condition, is_day, cloud_cover_percent,
                    precipitation_mm, rain_mm, snowfall_cm, raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    key,
                    payload.get("timestamp"),
                    fetched_at,
                    _optional_float(payload.get("temperature_c")),
                    _optional_float(payload.get("humidity_percent")),
                    _optional_float(payload.get("wind_speed_kmh")),
                    _optional_int(payload.get("weather_code")),
                    payload.get("weather_label"),
                    payload.get("condition"),
                    1 if payload.get("is_day") else 0,
                    _optional_float(payload.get("cloud_cover_percent")),
                    _optional_float(payload.get("precipitation_mm")),
                    _optional_float(payload.get("rain_mm")),
                    _optional_float(payload.get("snowfall_cm")),
                    _json_dumps(payload),
                ),
            )

            for forecast_key in ("today", "tomorrow"):
                forecast = payload.get(forecast_key)
                if not isinstance(forecast, dict) or not forecast.get("date"):
                    continue

                conn.execute(
                    """
                    INSERT INTO weather_daily_forecasts (
                        location_key, forecast_date, fetched_at, weather_code,
                        weather_label, condition, temperature_min_c,
                        temperature_max_c, precipitation_probability_percent,
                        precipitation_sum_mm, rain_sum_mm, snowfall_sum_cm,
                        wind_speed_max_kmh, shortwave_radiation_sum_mj_m2,
                        sunshine_duration_seconds, daylight_duration_seconds,
                        raw_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        key,
                        forecast.get("date"),
                        fetched_at,
                        _optional_int(forecast.get("weather_code")),
                        forecast.get("weather_label"),
                        forecast.get("condition"),
                        _optional_float(forecast.get("temperature_min_c")),
                        _optional_float(forecast.get("temperature_max_c")),
                        _optional_float(
                            forecast.get("precipitation_probability_percent")
                        ),
                        _optional_float(forecast.get("precipitation_sum_mm")),
                        _optional_float(forecast.get("rain_sum_mm")),
                        _optional_float(forecast.get("snowfall_sum_cm")),
                        _optional_float(forecast.get("wind_speed_max_kmh")),
                        _optional_float(
                            forecast.get("shortwave_radiation_sum_mj_m2")
                        ),
                        _optional_float(forecast.get("sunshine_duration_seconds")),
                        _optional_float(forecast.get("daylight_duration_seconds")),
                        _json_dumps(forecast),
                    ),
                )

    def daily_production_for_date(
        self,
        day: date,
        tz: tzinfo,
        max_gap_seconds: float,
        latest: Optional[InverterSnapshot] = None,
    ) -> Dict[str, Any]:
        start = datetime(day.year, day.month, day.day, tzinfo=tz)
        end = start + timedelta(days=1)
        totals = self.energy_totals(
            start=start,
            end=end,
            latest=latest,
            max_gap_seconds=max_gap_seconds,
        )
        return {
            "date": day.isoformat(),
            "production_kwh": totals["production_kwh"],
            "sample_count": totals["sample_count"],
        }

    def daily_production_history(
        self,
        end_date: date,
        days: int,
        tz: tzinfo,
        max_gap_seconds: float,
        latest: Optional[InverterSnapshot] = None,
    ) -> List[Dict[str, Any]]:
        history: List[Dict[str, Any]] = []
        current = end_date - timedelta(days=max(1, int(days)))

        while current < end_date:
            item = self.daily_production_for_date(
                day=current,
                tz=tz,
                max_gap_seconds=max_gap_seconds,
                latest=latest,
            )
            if item["sample_count"] > 0:
                history.append(item)
            current += timedelta(days=1)

        return history

    def weather_radiation_history(
        self,
        location_key: str = "borriol",
    ) -> List[Dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT forecast_date, fetched_at, shortwave_radiation_sum_mj_m2
                FROM weather_daily_forecasts
                WHERE location_key = ?
                    AND shortwave_radiation_sum_mj_m2 IS NOT NULL
                ORDER BY forecast_date ASC, fetched_at ASC
                """,
                (location_key,),
            ).fetchall()

        latest_by_day: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            item = dict(row)
            latest_by_day[item["forecast_date"]] = item

        return list(latest_by_day.values())

    def get_prediction_state(self, key: str, default: Any = None) -> Any:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT value
                FROM solar_prediction_state
                WHERE key = ?
                """,
                (key,),
            ).fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value"])
        except json.JSONDecodeError:
            return row["value"]

    def set_prediction_state(self, key: str, value: Any) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO solar_prediction_state (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, _json_dumps(value), now),
            )

    def pending_predictions(self, before_date: date) -> List[Dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT target_date, predicted_kwh
                FROM solar_daily_predictions
                WHERE target_date < ?
                    AND actual_kwh IS NULL
                    AND predicted_kwh IS NOT NULL
                ORDER BY target_date ASC
                """,
                (before_date.isoformat(),),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_prediction_actual(
        self,
        target_date: date,
        actual_kwh: float,
        error_ratio: float,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            conn.execute(
                """
                UPDATE solar_daily_predictions
                SET actual_kwh = ?,
                    actualized_at = ?,
                    error_ratio = ?
                WHERE target_date = ?
                """,
                (
                    round(float(actual_kwh), 3),
                    now,
                    round(float(error_ratio), 4),
                    target_date.isoformat(),
                ),
            )

    def upsert_solar_prediction(self, prediction: Dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        created_at = str(prediction.get("created_at") or now)
        updated_at = str(prediction.get("updated_at") or now)
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO solar_daily_predictions (
                    target_date, location_key, created_at, updated_at,
                    base_kwh, base_source, base_sample_count, weather_factor,
                    correction_factor, predicted_kwh, method_version,
                    details_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(target_date) DO UPDATE SET
                    location_key = excluded.location_key,
                    updated_at = excluded.updated_at,
                    base_kwh = excluded.base_kwh,
                    base_source = excluded.base_source,
                    base_sample_count = excluded.base_sample_count,
                    weather_factor = excluded.weather_factor,
                    correction_factor = excluded.correction_factor,
                    predicted_kwh = excluded.predicted_kwh,
                    method_version = excluded.method_version,
                    details_json = excluded.details_json
                """,
                (
                    prediction["target_date"],
                    prediction["location_key"],
                    created_at,
                    updated_at,
                    _optional_float(prediction.get("base_kwh")),
                    prediction.get("base_source"),
                    int(prediction.get("base_sample_count") or 0),
                    _optional_float(prediction.get("weather_factor")),
                    _optional_float(prediction.get("correction_factor")),
                    _optional_float(prediction.get("predicted_kwh")),
                    prediction["method_version"],
                    _json_dumps(prediction.get("details") or {}),
                ),
            )

    def insert_system_health_snapshot(self, payload: Dict[str, Any]) -> None:
        cpu = payload.get("cpu") if isinstance(payload.get("cpu"), dict) else {}
        memory = payload.get("memory") if isinstance(payload.get("memory"), dict) else {}
        storage = payload.get("storage") if isinstance(payload.get("storage"), dict) else {}
        temperature = (
            payload.get("temperature")
            if isinstance(payload.get("temperature"), dict)
            else {}
        )
        generated_at = str(payload.get("timestamp") or datetime.now(timezone.utc).isoformat())

        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO system_health_snapshots (
                    generated_at, platform, cpu_percent, cpu_cores,
                    cpu_load_1m, cpu_load_percent, memory_total_bytes,
                    memory_available_bytes, memory_used_bytes, memory_percent,
                    storage_path, storage_total_bytes, storage_free_bytes,
                    storage_used_bytes, storage_percent, temperature_celsius,
                    temperature_source, raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    generated_at,
                    payload.get("platform"),
                    _optional_float(cpu.get("percent")),
                    _optional_int(cpu.get("cores")),
                    _optional_float(cpu.get("load_1m")),
                    _optional_float(cpu.get("load_percent")),
                    _optional_int(memory.get("total_bytes")),
                    _optional_int(memory.get("available_bytes")),
                    _optional_int(memory.get("used_bytes")),
                    _optional_float(memory.get("percent")),
                    storage.get("path"),
                    _optional_int(storage.get("total_bytes")),
                    _optional_int(storage.get("free_bytes")),
                    _optional_int(storage.get("used_bytes")),
                    _optional_float(storage.get("percent")),
                    _optional_float(temperature.get("celsius")),
                    temperature.get("source"),
                    _json_dumps(payload),
                ),
            )

    def latest_system_health(self) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT raw_json
                FROM system_health_snapshots
                ORDER BY generated_at DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
        if not row:
            return None
        return _json_loads(row["raw_json"])

    def save_energy_summaries(self, payload: Dict[str, Any]) -> None:
        generated_at = str(payload.get("generated_at") or "").strip()
        if not generated_at:
            return

        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO energy_summary_cache (
                    cache_key, generated_at, raw_json
                )
                VALUES ('default', ?, ?)
                """,
                (generated_at, _json_dumps(payload)),
            )

    def latest_energy_summaries(self) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT raw_json
                FROM energy_summary_cache
                WHERE cache_key = 'default'
                """
            ).fetchone()
        if not row:
            return None
        return _json_loads(row["raw_json"])

    def save_economics_balance(self, payload: Dict[str, Any]) -> None:
        start_date = str(payload.get("start_date") or "").strip()
        generated_at = str(payload.get("generated_at") or "").strip()
        if not start_date or not generated_at:
            return

        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO economics_balance_cache (
                    start_date, generated_at, raw_json
                )
                VALUES (?, ?, ?)
                """,
                (start_date, generated_at, _json_dumps(payload)),
            )

    def latest_economics_balance(self, start_date: date) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT raw_json
                FROM economics_balance_cache
                WHERE start_date = ?
                """,
                (start_date.isoformat(),),
            ).fetchone()
        if not row:
            return None
        return _json_loads(row["raw_json"])

    def latest_weather_payload(
        self,
        location_key: str = "borriol",
    ) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT raw_json
                FROM weather_current
                WHERE location_key = ?
                ORDER BY fetched_at DESC, id DESC
                LIMIT 1
                """,
                (location_key,),
            ).fetchone()
        if not row:
            return None
        return _json_loads(row["raw_json"])

    def solar_prediction_for_date(self, target_date: date) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT target_date, location_key, created_at, updated_at,
                    base_kwh, base_source, base_sample_count, weather_factor,
                    correction_factor, predicted_kwh, actual_kwh,
                    actualized_at, error_ratio, method_version, details_json
                FROM solar_daily_predictions
                WHERE target_date = ?
                """,
                (target_date.isoformat(),),
            ).fetchone()

        if not row:
            return None

        prediction = dict(row)
        prediction["estimated_kwh"] = prediction.get("predicted_kwh")
        prediction["details"] = _json_loads(prediction.pop("details_json"))
        return prediction

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn


def _optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_loads(value: Any) -> Dict[str, Any]:
    if not value:
        return {}
    try:
        loaded = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        return _as_utc(value)
    return _as_utc(datetime.fromisoformat(str(value)))


def _normalize_energy_points(points: List[Dict[str, Any]]) -> List[Tuple[datetime, Dict[str, Any]]]:
    by_timestamp: Dict[datetime, Dict[str, Any]] = {}
    for point in points:
        by_timestamp[_parse_ts(point["ts"])] = point
    return sorted(by_timestamp.items(), key=lambda item: item[0])


def _integrate_kwh(
    points: List[Tuple[datetime, Dict[str, Any]]],
    start: datetime,
    end: datetime,
    watts: Callable[[Dict[str, Any]], float],
    max_gap_seconds: float,
) -> float:
    total_wh = 0.0
    max_gap = max(1.0, float(max_gap_seconds))

    for index, (timestamp, point) in enumerate(points):
        segment_start = max(timestamp, start)
        next_timestamp = points[index + 1][0] if index + 1 < len(points) else end
        segment_end = min(next_timestamp, end)

        if segment_end <= segment_start:
            continue

        duration_seconds = min((segment_end - segment_start).total_seconds(), max_gap)
        total_wh += watts(point) * duration_seconds / 3600.0

    return round(total_wh / 1000.0, 3)


def _empty_energy_totals(
    start: datetime,
    end: datetime,
    max_gap_seconds: float,
) -> Dict[str, Any]:
    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "sample_count": 0,
        "max_gap_seconds": max_gap_seconds,
        "production_kwh": 0.0,
        "consumption_kwh": 0.0,
        "grid_import_kwh": 0.0,
        "grid_export_kwh": 0.0,
    }


def _add_energy_totals(target: Dict[str, Any], source: Dict[str, Any]) -> None:
    target["sample_count"] = int(target.get("sample_count") or 0) + int(
        source.get("sample_count") or 0
    )
    for key in (
        "production_kwh",
        "consumption_kwh",
        "grid_import_kwh",
        "grid_export_kwh",
    ):
        target[key] = float(target.get(key) or 0.0) + float(source.get(key) or 0.0)


def _round_energy_totals(payload: Dict[str, Any]) -> None:
    for key in (
        "production_kwh",
        "consumption_kwh",
        "grid_import_kwh",
        "grid_export_kwh",
    ):
        payload[key] = round(float(payload.get(key) or 0.0), 3)


def _peak_from_row(row: Any, field: str, invert: bool = False) -> Dict[str, Any]:
    if not row:
        return {"value_w": None, "timestamp": None}
    value = int(row[field])
    if invert:
        value = -value
    return {
        "value_w": max(0, value),
        "timestamp": row["ts"],
    }


def _max_peak(current: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
    current_value = current.get("value_w")
    candidate_value = candidate.get("value_w")
    if current_value is None:
        return candidate
    if candidate_value is None:
        return current
    if int(candidate_value) > int(current_value):
        return candidate
    return current


def _empty_power_peaks(start: datetime, end: datetime) -> Dict[str, Any]:
    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "sample_count": 0,
        "demand_peak": {"value_w": None, "timestamp": None},
        "production_peak": {"value_w": None, "timestamp": None},
        "grid_import_peak": {"value_w": None, "timestamp": None},
        "grid_export_peak": {"value_w": None, "timestamp": None},
    }
