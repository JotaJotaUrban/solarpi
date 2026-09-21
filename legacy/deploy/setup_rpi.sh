#!/usr/bin/env bash
set -eu

cd "$(dirname "$0")/.."

echo "SolarPi: preparando entorno Python..."
python3 -m venv .venv
. .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo "SolarPi: creado .env desde .env.example"
fi

if grep -q '^SOLARPI_API_PORT=' .env; then
  sed -i 's/^SOLARPI_API_PORT=.*/SOLARPI_API_PORT=80/' .env
else
  printf '\nSOLARPI_API_PORT=80\n' >> .env
fi

echo "SolarPi: puerto web de Raspberry fijado a 80"

echo
echo "Listo."
echo "Instalar o reiniciar servicio:"
echo "  cd $(pwd)"
echo "  sudo cp deploy/solarpi.service /etc/systemd/system/solarpi.service"
echo "  sudo systemctl daemon-reload"
echo "  sudo systemctl enable --now solarpi.service"
echo "  sudo systemctl restart solarpi.service"
echo
echo "Luego abre:"
echo "  http://solarpi"
