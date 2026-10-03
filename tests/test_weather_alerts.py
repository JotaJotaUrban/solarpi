import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from xml.sax.saxutils import escape

from solarpi.weather_alerts import parse_alerts, WeatherAlerts

NOW = datetime(2026, 10, 3, 10, tzinfo=timezone.utc)


def entry(**changes):
    fields = dict(areaDesc='Litoral norte de Castellón', event='Severe rain warning',
                  status='Actual', scope='Public', message_type='Alert', identifier='rain-1',
                  onset='2026-10-03T08:00:00Z', expires='2026-10-03T22:00:00Z',
                  sent='2026-10-03T06:00:00Z', severity='Severe')
    fields.update(changes)
    return '<entry>' + ''.join(f'<cap:{key}>{escape(value)}</cap:{key}>' for key,value in fields.items()) + '</entry>'


def feed(*entries):
    return ('<feed xmlns="http://www.w3.org/2005/Atom" xmlns:cap="urn:oasis:names:tc:emergency:cap:1.2">' + ''.join(entries) + '</feed>').encode()


class WeatherAlertsTests(unittest.TestCase):
    def test_province_includes_inland_coast_and_future(self):
        alerts = parse_alerts(feed(entry(), entry(identifier='inland', areaDesc='Interior sur de Castellón', severity='Extreme'), entry(identifier='coast', areaDesc='Aguas costeras de Castellón', event='Moderate coastal warning', severity='Moderate', onset='2026-10-03T12:00:00Z'), entry(areaDesc='Valencia')), NOW)
        self.assertEqual(len(alerts), 3)
        self.assertEqual([x['level'] for x in alerts], ['red','orange','yellow'])
        self.assertEqual(alerts[1]['event'], 'Lluvias')
        self.assertEqual(alerts[2]['event'], 'Fenómenos costeros')

    def test_expired_test_green_cancel_and_duplicates(self):
        result = parse_alerts(feed(entry(),entry(),entry(identifier='old',expires='2026-10-03T09:00:00Z'),entry(identifier='test',status='Test'),entry(identifier='green',severity='Minor')), NOW)
        self.assertEqual(len(result), 1)
        self.assertEqual(parse_alerts(feed(entry(),entry(identifier='cancellation',message_type='Cancel',references='aemet,rain-1,2026-10-03T06:00:00Z')), NOW), [])

    def test_unknown_hazard_is_not_lost_and_revisions_replace(self):
        result = parse_alerts(feed(entry(event='New hazard'),entry(identifier='revised',event='New hazard',sent='2026-10-03T07:00:00Z',severity='Extreme',message_type='Update',references='aemet,rain-1,2026-10-03T06:00:00Z')),NOW)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['event'],'New hazard')
        self.assertEqual(result[0]['level'],'red')
        self.assertEqual(len(parse_alerts(feed(entry(),entry(identifier='another-threshold')),NOW)),2)

    def test_invalid_response_not_treated_as_no_warnings(self):
        for body in (b'<html/>', b'broken', b'<!DOCTYPE feed><feed/>', feed(entry(expires='bad'))):
            with self.assertRaises(Exception):
                parse_alerts(body,NOW)
        self.assertEqual(parse_alerts(feed(),NOW), [])

    def test_fetch_failure_retains_nonexpired_alerts_and_marks_stale(self):
        client = WeatherAlerts()
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = feed(entry())
        with patch('solarpi.weather_alerts.datetime') as clock:
            clock.now.return_value = NOW
            clock.fromisoformat.side_effect = datetime.fromisoformat
            with patch('solarpi.weather_alerts.urlopen',return_value=response):
                client.refresh()
            self.assertEqual(client.snapshot()['status'],'ok')
            self.assertEqual(len(client.snapshot()['alerts']),1)
            with patch('solarpi.weather_alerts.urlopen',side_effect=OSError('offline')):
                client.refresh()
            self.assertEqual(client.snapshot()['status'],'unavailable')
            self.assertEqual(len(client.snapshot()['alerts']),1)
            clock.now.return_value = datetime(2026,10,4,tzinfo=timezone.utc)
            self.assertEqual(client.snapshot()['alerts'],[])


if __name__ == '__main__':
    unittest.main()
