import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

from solarpi.config import load_settings
from solarpi.economics import build_economics_balance_payload
from solarpi.server import SolarPiRequestHandler


class EconomicsDatesTests(unittest.TestCase):
    def setUp(self):
        self.settings = load_settings()
        self.store = Mock()
        self.store.energy_totals_daily_summarized.return_value = {
            'grid_export_kwh': 100, 'grid_import_kwh': 10,
        }
        self.now = datetime(2026, 10, 3, 12, tzinfo=ZoneInfo('Europe/Madrid'))

    def calculate(self, start, end=None, now=None):
        return build_economics_balance_payload(
            self.settings, self.store, start, now or self.now, Mock(), end_day=end,
        )

    def test_past_end_includes_whole_day_and_excludes_live_reading(self):
        payload = self.calculate(date(2026, 9, 1), date(2026, 9, 30))
        args = self.store.energy_totals_daily_summarized.call_args.kwargs
        self.assertEqual(args['end'], datetime(2026, 10, 1, tzinfo=self.now.tzinfo))
        self.assertIsNone(args['latest'])
        self.assertEqual(payload['end_date'], '2026-09-30')
        self.assertEqual(payload['export_credit_eur'], 6)
        self.assertAlmostEqual(payload['recovery_cost_eur'], 1.35915, places=3)

    def test_today_stops_at_now_and_same_day_is_valid(self):
        self.calculate(self.now.date(), self.now.date())
        self.assertEqual(self.store.energy_totals_daily_summarized.call_args.kwargs['end'], self.now)

    def test_invalid_ranges(self):
        for start, end in [(date(2026, 10, 3), date(2026, 10, 2)), (date(2026, 10, 1), date(2026, 10, 4))]:
            with self.assertRaises(ValueError):
                self.calculate(start, end)

    def test_end_boundary_obeys_daylight_saving(self):
        now = datetime(2026, 10, 27, 12, tzinfo=self.now.tzinfo)
        self.calculate(date(2026, 10, 25), date(2026, 10, 25), now)
        args = self.store.energy_totals_daily_summarized.call_args.kwargs
        duration = args['end'].astimezone(timezone.utc) - args['start'].astimezone(timezone.utc)
        self.assertEqual(duration.total_seconds(), 25 * 3600)

    def test_api_defaults_and_validation(self):
        handler = object.__new__(SolarPiRequestHandler)
        metrics = Mock()
        handler.server = SimpleNamespace(settings=self.settings, metrics=metrics)
        handler._json = Mock()
        with patch('solarpi.server.datetime') as clock:
            clock.now.return_value = self.now
            clock.side_effect = datetime
            handler._economics_balance({})
            metrics.economics_balance.assert_called_once_with(date(2026, 10, 1), date(2026, 10, 3))
            for query in ({'end_date': ['bad']}, {'start_date': ['2026-10-03'], 'end_date': ['2026-10-02']}, {'end_date': ['2026-10-04']}):
                with self.assertRaises(ValueError):
                    handler._economics_balance(query)


if __name__ == '__main__':
    unittest.main()
