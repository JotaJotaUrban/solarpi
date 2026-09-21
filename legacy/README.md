# SolarPi

SolarPi is a small local-first monitor for a Deye/Solarman inverter.

The first milestone is intentionally simple:

- Python backend.
- Direct low-level reader based on the working `deye_test.py` script.
- SQLite storage for recent/history data.
- JSON API served with Python's standard library.
- Static dashboard served by the same backend.
- Weather data in the top bar using Open-Meteo, without an API key.

## Ports

SolarPi uses two different ports:

- `8899`: Deye/Solarman Modbus TCP logger port. The backend uses this to read the inverter.
- `80`: SolarPi web/API port on the Raspberry Pi. Open this in a browser as `http://solarpi`.

Port `8000` is only useful for local development or manual diagnostics.
On the Raspberry Pi, run SolarPi through the included systemd service so it can bind to port `80`.

## Run on the Raspberry Pi

Project path:

```bash
cd /home/solarpi/solar-monitor
```

Create a virtual environment and install the only external runtime dependency:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` if needed. The current defaults match the working script:

```text
SOLARPI_INVERTER_IP=192.168.1.137
SOLARPI_INVERTER_SERIAL=3594884342
SOLARPI_INVERTER_PORT=8899
SOLARPI_MODBUS_SLAVE_ID=1
SOLARPI_API_PORT=80
```

Install or restart the service:

```bash
sudo cp deploy/solarpi.service /etc/systemd/system/solarpi.service
sudo systemctl daemon-reload
sudo systemctl enable --now solarpi.service
sudo systemctl restart solarpi.service
```

Open from another machine on the same network:

```text
http://solarpi
```

or:

```text
http://<RPI_IP>
```

## Check the inverter package

Use the Python executable that will run the app:

```bash
python3 -m pip show pysolarmanv5
```

If the app uses a virtual environment:

```bash
/home/solarpi/solar-monitor/.venv/bin/python -m pip show pysolarmanv5
```

## API

```text
GET /api/health
GET /api/now
GET /api/raw
GET /api/history?minutes=60&limit=720
GET /api/weather?location=borriol
GET /api/weather?location=merida
GET /api/totals
GET /api/peaks
GET /api/settings
```

`/api/raw` keeps the raw register block alongside the interpreted fields. That lets us reinterpret historical readings later if we discover a better register map.

`/api/weather` uses Borriol by default and also supports Mérida. Weather responses are cached in memory for `SOLARPI_WEATHER_CACHE_SECONDS` seconds.

`/api/totals` returns estimated kWh totals for the current day and natural month. It integrates stored power samples and caps long gaps with `SOLARPI_TOTALS_MAX_GAP_SECONDS` to avoid inflating totals when the app is stopped.

`/api/peaks` returns the maximum demanded, generated, grid-imported, and grid-exported power for the current day, natural month, and year.

## Raspberry Pi notes

Suggested starting values:

```text
SOLARPI_POLL_INTERVAL=4
```

The app reads every 4 seconds and stores every successful reading as a snapshot. Peaks and totals are calculated from those snapshots and kept as in-memory summaries for the API.

## systemd service

Install or restart it as a service:

```bash
sudo cp deploy/solarpi.service /etc/systemd/system/solarpi.service
sudo systemctl daemon-reload
sudo systemctl enable --now solarpi.service
```

Inspect logs:

```bash
journalctl -u solarpi.service -f
```

## Future milestones

1. Confirm register meanings against real data.
2. Add a systemd unit for boot startup.
3. Add retention/export jobs for SQLite.
4. Add MQTT publishing for Home Assistant or other automations.
5. Add an outbound sync agent to a remote server.
6. Add write/command support only behind an explicit safety layer.
