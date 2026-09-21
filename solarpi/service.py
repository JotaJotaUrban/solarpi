from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .models import InverterSnapshot
from .store import SnapshotStore


class SolarPiService:
    def __init__(
        self,
        reader: Any,
        store: SnapshotStore,
        poll_interval_seconds: float,
    ) -> None:
        self.reader = reader
        self.store = store
        self.poll_interval_seconds = poll_interval_seconds

        self._latest: Optional[InverterSnapshot] = None
        self._last_error: Optional[str] = None
        self._last_error_at: Optional[datetime] = None
        self._read_count = 0
        self._error_count = 0
        self._started_at: Optional[datetime] = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        self.store.init_db()
        self._started_at = datetime.now(timezone.utc)
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="solarpi-poller",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        self.reader.disconnect()

    def get_latest(self) -> Optional[InverterSnapshot]:
        with self._lock:
            return self._latest

    def get_health(self) -> Dict[str, Any]:
        with self._lock:
            latest = self._latest
            last_error = self._last_error
            last_error_at = self._last_error_at
            read_count = self._read_count
            error_count = self._error_count
            started_at = self._started_at

        if latest is None:
            status = "starting" if last_error is None else "degraded"
            latest_read_at = None
            age_seconds = None
        else:
            age_seconds = latest.age_seconds
            stale_after = max(15.0, self.poll_interval_seconds * 3)
            status = "ok" if age_seconds <= stale_after and last_error is None else "degraded"
            latest_read_at = latest.timestamp.isoformat()

        return {
            "status": status,
            "started_at": started_at.isoformat() if started_at else None,
            "latest_read_at": latest_read_at,
            "latest_age_seconds": age_seconds,
            "last_error": last_error,
            "last_error_at": last_error_at.isoformat() if last_error_at else None,
            "read_count": read_count,
            "error_count": error_count,
            "poll_interval_seconds": self.poll_interval_seconds,
            "snapshot_persist_interval_seconds": self.poll_interval_seconds,
        }

    def _run(self) -> None:
        while not self._stop_event.is_set():
            started = time.monotonic()
            try:
                snapshot = self.reader.read_snapshot()
                with self._lock:
                    self._latest = snapshot
                    self._last_error = None
                    self._last_error_at = None
                    self._read_count += 1

                self._store_snapshot(snapshot)
            except Exception as exc:
                self._record_error("read: %s" % exc)

            elapsed = time.monotonic() - started
            wait_seconds = max(0.2, self.poll_interval_seconds - elapsed)
            self._stop_event.wait(wait_seconds)

    def _store_snapshot(self, snapshot: InverterSnapshot) -> None:
        try:
            self.store.insert_snapshot(snapshot)
        except Exception as exc:
            self._record_error("store: %s" % exc)

    def _record_error(self, message: str) -> None:
        with self._lock:
            self._last_error = message
            self._last_error_at = datetime.now(timezone.utc)
            self._error_count += 1
