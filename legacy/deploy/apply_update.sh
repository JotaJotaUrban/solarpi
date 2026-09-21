#!/usr/bin/env bash
set -eu

zip_path="${1:-/home/solarpi/solarpi_app_new.zip}"
expected_hash="${2:-}"
app_dir="/home/solarpi/solar-monitor"
ts="$(date +%Y%m%d-%H%M%S)"
backup_dir="/home/solarpi/solar-monitor.before-update-$ts"
failed_dir="/home/solarpi/solar-monitor.failed-update-$ts"

if [ ! -f "$zip_path" ]; then
  echo "ZIP not found: $zip_path" >&2
  exit 1
fi

if [ -n "$expected_hash" ]; then
  actual_hash="$(sha256sum "$zip_path" | cut -c1-64)"
  if [ "$actual_hash" != "$expected_hash" ]; then
    echo "Hash mismatch: $actual_hash" >&2
    exit 1
  fi
fi

tmp_dir="$(mktemp -d)"
echo "Checking package..."
unzip -oq "$zip_path" -d "$tmp_dir"
python3 -m py_compile "$tmp_dir"/solarpi/*.py
test -f "$tmp_dir/solarpi/economics.py"
test -f "$tmp_dir/solarpi/prime_cache.py"
test -f "$tmp_dir/deploy/solarpi.service"

restore_on_error() {
  code=$?
  if [ "$code" -ne 0 ]; then
    echo "Update failed, restoring backup..." >&2
    sudo systemctl stop solarpi.service >/dev/null 2>&1 || true
    if [ -d "$app_dir" ]; then
      mv "$app_dir" "$failed_dir"
    fi
    cp -a "$backup_dir" "$app_dir"
    if [ -d "$failed_dir/.venv" ]; then
      mv "$failed_dir/.venv" "$app_dir/.venv"
    fi
    if [ -d "$failed_dir/data" ]; then
      mv "$failed_dir/data" "$app_dir/data"
    fi
    sudo systemctl start solarpi.service >/dev/null 2>&1 || true
    echo "FAILED restored=$backup_dir failed=$failed_dir" >&2
  fi
  exit "$code"
}

echo "Backing up application files..."
mkdir -p "$backup_dir"
tar -C "$app_dir" \
  --exclude='./data' \
  --exclude='./.venv' \
  -cf - . | tar -C "$backup_dir" -xf -
trap restore_on_error EXIT

echo "Installing update..."
sudo systemctl stop solarpi.service
unzip -oq "$zip_path" -d "$app_dir"
cd "$app_dir"

if [ ! -f .env ]; then
  touch .env
fi

set_env() {
  key="$1"
  value="$2"
  if grep -q "^$key=" .env; then
    sed -i "s/^$key=.*/$key=$value/" .env
  else
    printf "\n%s=%s\n" "$key" "$value" >> .env
  fi
}

set_env SOLARPI_API_PORT 80
set_env SOLARPI_INVERTER_IP 192.168.1.137

.venv/bin/python -m compileall -q solarpi
echo "Priming cached totals..."
.venv/bin/python -m solarpi.prime_cache

sudo cp deploy/solarpi.service /etc/systemd/system/solarpi.service
sudo systemctl daemon-reload
sudo systemctl start solarpi.service
sleep 5

echo "Checking service..."
systemctl is-active --quiet solarpi.service
for attempt in 1 2 3 4 5 6 7 8 9 10 11 12; do
  if curl -fsS --connect-timeout 2 --max-time 8 http://127.0.0.1/api/health \
      | python3 -c 'import json,sys; sys.exit(0 if json.load(sys.stdin).get("status") == "ok" else 1)'; then
    break
  fi
  if [ "$attempt" = 12 ]; then
    echo "Service did not reach ok health" >&2
    systemctl status solarpi.service --no-pager -l >&2 || true
    journalctl -u solarpi.service -b --no-pager -n 80 >&2 || true
    exit 1
  fi
  sleep 5
done
curl -fsS --connect-timeout 2 --max-time 15 http://127.0.0.1/api/totals >/dev/null
curl -fsS --connect-timeout 2 --max-time 15 "http://127.0.0.1/api/economics-balance?start_date=2026-08-21" >/dev/null

trap - EXIT
echo "OK backup=$backup_dir"
