# Como pasar SolarPi a la Raspberry Pi

## 1. En Windows

Desde PowerShell, dentro de esta carpeta del proyecto:

```powershell
scp .\solarpi_app.zip solarpi@solarpi:/home/solarpi/
```

Si `solarpi` no resuelve por nombre, usa la IP de la Raspberry:

```powershell
scp .\solarpi_app.zip solarpi@IP_DE_LA_RPI:/home/solarpi/
```

## 2. En la Raspberry Pi

Conectate por SSH:

```bash
ssh solarpi@solarpi
```

Entra en la carpeta del proyecto y descomprime:

```bash
cd /home/solarpi
mkdir -p solar-monitor
unzip -o solarpi_app.zip -d solar-monitor
cd solar-monitor
```

Instala el entorno:

```bash
bash deploy/setup_rpi.sh
```

Instala o reinicia el servicio:

```bash
sudo cp deploy/solarpi.service /etc/systemd/system/solarpi.service
sudo systemctl daemon-reload
sudo systemctl enable --now solarpi.service
sudo systemctl restart solarpi.service
```

Abre en el navegador:

```text
http://solarpi
```

o:

```text
http://IP_DE_LA_RPI
```

## Puertos

El puerto `80` es el de la web/API de SolarPi en la Raspberry Pi.

El puerto `8899` es el del inversor Deye. Ese no se cambia.

El instalador deja esta línea en `.env`:

```text
SOLARPI_API_PORT=80
```

Para usar `80`, SolarPi debe arrancar como servicio systemd, porque un usuario normal no puede abrir puertos bajos manualmente.

## Instalar como servicio

```bash
sudo cp deploy/solarpi.service /etc/systemd/system/solarpi.service
sudo systemctl daemon-reload
sudo systemctl enable --now solarpi.service
```

Ver logs:

```bash
journalctl -u solarpi.service -f
```
