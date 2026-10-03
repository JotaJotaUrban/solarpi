import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from solarpi.store import SnapshotStore


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'history.sqlite3'
        self.store = SnapshotStore(self.path)
        self.store.init_db()
        self.now = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)
        conn = sqlite3.connect(self.path)
        try:
            conn.executemany(
                'INSERT INTO snapshots VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                [((self.now + timedelta(seconds=seconds)).isoformat(), 'deye',
                  100, 200, 300, 500, 50, 52., 1., 52, 0, 'standby', 0, 230., 500, 0, '[]')
                 for seconds in range(-86404, 5, 4)],
            )
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        self.temp.cleanup()

    def history(self, minutes, limit):
        with patch('solarpi.store.datetime') as clock:
            clock.now.return_value = self.now
            return self.store.history(minutes, limit)

    def test_all_widget_ranges_cover_the_entire_window(self):
        for minutes in (60, 360, 1440):
            with self.subTest(minutes=minutes):
                points = self.history(minutes, 900)
                self.assertEqual(len(points), 900)
                times = [datetime.fromisoformat(p['ts']) for p in points]
                self.assertEqual(times[0], self.now - timedelta(minutes=minutes))
                self.assertEqual(times[-1], self.now)
                self.assertEqual(times, sorted(set(times)))
                self.assertLess(max((b-a).total_seconds() for a,b in zip(times, times[1:])), 300)
                self.assertTrue(all(p['house_power_w'] == 100 for p in points))

    def test_small_windows_and_limits(self):
        self.assertEqual(len(self.history(1, 900)), 16)
        self.assertEqual(self.history(1440, 1)[0]['ts'], self.now.isoformat())
        self.assertEqual(len(self.history(1440, 2)), 2)
        with self.assertRaises(ValueError):
            self.history(60, 0)

    def test_missing_data_is_not_stretched_or_invented(self):
        conn = sqlite3.connect(self.path)
        try:
            conn.execute('DELETE FROM snapshots WHERE ts < ?', ((self.now-timedelta(minutes=30)).isoformat(),))
            conn.commit()
        finally:
            conn.close()
        points = self.history(1440, 900)
        self.assertEqual(len(points), 451)
        self.assertEqual(points[0]['ts'], (self.now-timedelta(minutes=30)).isoformat())
        conn = sqlite3.connect(self.path)
        try:
            conn.execute('DELETE FROM snapshots')
            conn.commit()
        finally:
            conn.close()
        self.assertEqual(self.history(1440, 900), [])


if __name__ == '__main__':
    unittest.main()
