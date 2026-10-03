import json
import sqlite3
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from solarpi.config import load_settings
from solarpi.database_backup import copy_database
from solarpi.deye import map_registers, QUANTITY
from solarpi.server import SolarPiHTTPServer, SolarPiRequestHandler
from solarpi.store import SnapshotStore


class Worker:
    def __init__(self, *args, **kwargs):
        self.stopped = False
        self.started = False
        self.store = None

    def stop(self, wait=False):
        self.stopped = wait

    def start(self):
        self.started = True

    def get_health(self):
        return {"status": "ok"}


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / "live.sqlite3"
        SnapshotStore(self.path).init_db()
        SnapshotStore(self.path).insert_snapshot(map_registers([0] * QUANTITY))
        self.writer = sqlite3.connect(self.path)
        self.writer.execute("PRAGMA journal_mode=WAL")
        self.writer.execute("INSERT INTO solar_prediction_state VALUES ('marker', 'original', '2026-09-22')")
        self.writer.execute("INSERT INTO economics_balance_cache VALUES ('2026-01-01', '2026-09-22', '{}')")
        self.writer.commit()
        self.server = SolarPiHTTPServer(("127.0.0.1", 0), SolarPiRequestHandler)
        self.server.settings = replace(load_settings(), database_path=self.path)
        self.server.service = Worker()
        self.server.metrics = Worker()
        self.server.system_monitor = object()
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.writer.close()
        self.temp.cleanup()

    def request(self, path, data=None, headers=None):
        defaults = {}
        if data is not None:
            defaults.update({"Content-Type": "application/vnd.sqlite3", "X-SolarPi-Confirm": "replace-database"})
        defaults.update(headers or {})
        try:
            with urlopen(Request(self.url + path, data=data, headers=defaults), timeout=10) as response:
                return response.status, response.read(), response.headers
        except HTTPError as exc:
            with exc:
                return exc.code, exc.read(), exc.headers

    def marker(self):
        return self.writer.execute("SELECT value FROM solar_prediction_state WHERE key='marker'").fetchone()[0]

    def test_roundtrip_all_tables_wal_and_new_workers(self):
        status, backup, headers = self.request('/api/backup')
        self.assertEqual(status, 200)
        self.assertIn('attachment;', headers['Content-Disposition'])
        exported = self.root / 'exported.sqlite3'
        exported.write_bytes(backup)
        conn = sqlite3.connect(exported)
        self.assertEqual(list(conn.iterdump()), list(self.writer.iterdump()))
        conn.close()
        self.writer.execute("UPDATE solar_prediction_state SET value='newer'")
        self.writer.execute("DELETE FROM economics_balance_cache")
        self.writer.commit()
        old_service, old_metrics = self.server.service, self.server.metrics
        with patch('solarpi.server.create_service', return_value=Worker()), patch('solarpi.server.ComputedMetricsService', Worker):
            status, body, _ = self.request('/api/restore', backup)
        self.assertEqual(status, 200, body)
        self.assertEqual(self.marker(), 'original')
        self.assertEqual(self.writer.execute('SELECT COUNT(*) FROM economics_balance_cache').fetchone()[0], 1)
        self.assertTrue(old_service.stopped and old_metrics.stopped)
        self.assertTrue(self.server.service.started and self.server.metrics.started)
        self.assertIsNot(self.server.metrics, old_metrics)
        self.assertEqual(self.request('/api/health')[0], 200)
        self.assertFalse(list(self.root.glob('backup-*')) + list(self.root.glob('restore-*')))

    def test_no_authentication_required_but_restore_needs_confirmation(self):
        self.assertEqual(self.request('/api/backup')[0], 200)
        # Header rejection happens before the body is sent (avoids a Windows
        # socket reset from deliberately unread request bytes).
        self.assertEqual(self.request('/api/restore', b'', {'X-SolarPi-Confirm': '', 'Content-Length': '3'})[0], 400)
        self.assertEqual(self.marker(), 'original')

    def test_invalid_upload_does_not_stop_or_modify_current_database(self):
        for payload in (b'not sqlite', self.request('/api/backup')[1][:200]):
            self.assertEqual(self.request('/api/restore', payload)[0], 400)
        other = self.root / 'partial.sqlite3'
        conn = sqlite3.connect(other)
        conn.execute('CREATE TABLE snapshots (id INTEGER, ts TEXT)')
        conn.close()
        self.assertEqual(self.request('/api/restore', other.read_bytes())[0], 400)
        self.assertFalse(self.server.service.stopped)
        self.assertEqual(self.marker(), 'original')
        self.assertEqual(self.request('/api/restore', b'', {'Content-Type': 'text/plain', 'Content-Length': '1'})[0], 415)
        self.assertFalse(list(self.root.glob('restore-*')))

    def test_failed_copy_resumes_service_without_changing_database(self):
        backup = self.request('/api/backup')[1]
        with patch('solarpi.server.copy_database', side_effect=OSError('disk failure')), patch('solarpi.server.create_service', return_value=Worker()), patch('solarpi.server.ComputedMetricsService', Worker):
            self.assertEqual(self.request('/api/restore', backup)[0], 500)
        self.assertEqual(self.marker(), 'original')
        self.assertTrue(self.server.service.started and self.server.metrics.started)

    def test_interrupted_sqlite_copy_rolls_back_destination(self):
        large = self.root / 'large.sqlite3'
        conn = sqlite3.connect(large)
        conn.execute('CREATE TABLE payload (data BLOB)')
        conn.execute('INSERT INTO payload VALUES (zeroblob(3000000))')
        conn.commit()
        conn.close()
        original = list(self.writer.iterdump())
        with patch('solarpi.database_backup.time.monotonic', side_effect=[0, 301]):
            with self.assertRaises(TimeoutError):
                copy_database(large, self.path)
        self.assertEqual(list(self.writer.iterdump()), original)


if __name__ == '__main__':
    unittest.main()
