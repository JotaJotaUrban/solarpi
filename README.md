# SolarPi

Monitor local Deye/Solarman portado a Docker Compose para Debian. Las carpetas `solarpi/` y `web/` son copias intactas de `legacy/`: se conservan las pantallas, los cálculos y la frecuencia de lectura. Las dependencias se fijan a las versiones del entorno local existente.

## Despliegue

Requiere Docker Engine con Compose y acceso de red al inversor.

```bash
git clone https://github.com/JotaJotaUrban/solarpi.git
cd solarpi
cp .env.example .env
nano .env
sudo docker compose up -d --build
```

Revisar IP y número de serie en `.env`. Abrir `http://IP_DEL_HOMELAB:8080`. El puerto publicado se cambia con `SOLARPI_WEB_PORT`. Compose fija el puerto interno en 8000 y la base de datos en `/app/data/solarpi.sqlite3`.

El servicio se reinicia automáticamente salvo parada manual. Ejecutar una sola instancia del recolector para esta instalación.

## Datos

SQLite se almacena en el volumen Docker `solarpi_solarpi-data`, separado del contenedor. Una instalación nueva empieza sin histórico; los datos recuperados no se importan automáticamente.

Recrear el contenedor conserva el volumen. **No ejecutar `docker compose down -v` si se quieren conservar los datos:** esa opción elimina los volúmenes. El volumen no sustituye una copia en otro dispositivo.

Copia consistente manual desde el directorio del proyecto:

```bash
mkdir -p backups
sudo docker compose exec -T solarpi python -c 'import sqlite3; src=sqlite3.connect("/app/data/solarpi.sqlite3"); dst=sqlite3.connect("/tmp/solarpi-backup.sqlite3"); src.backup(dst); dst.close(); src.close()'
sudo docker compose cp solarpi:/tmp/solarpi-backup.sqlite3 "backups/solarpi-$(date +%Y%m%d-%H%M%S).sqlite3"
```

Copiar el resultado a otro dispositivo. La automatización de copias y la importación del histórico quedan fuera de este portado.

## Operación

```bash
sudo docker compose ps
sudo docker compose logs --tail=100 -f
sudo docker compose stop
sudo docker compose up -d
```

Para actualizar: `git pull --ff-only` y `sudo docker compose up -d --build`.

Docker comprueba que la API responde. El estado de lectura del inversor se consulta en `/api/health`: un contenedor saludable no garantiza conexión con el inversor. Los logs tienen rotación. La parada usa SIGINT para activar el cierre previsto por el servidor original.

La pantalla de sistema mantiene la implementación original y muestra los recursos visibles desde el contenedor en el homelab. La temperatura depende de los sensores expuestos por Linux; ya no describe la Raspberry Pi.

## Legacy

`legacy/` conserva intactos los 27 archivos de `solarpi_app_to_rpi.zip`, fechado localmente el 12 de septiembre de 2026 e importado el 21 de septiembre. Coincidían byte a byte con los correspondientes de `from_rpi`.

Las instrucciones systemd de esa carpeta corresponden a la Raspberry Pi. No se incluyen bases de datos, configuración privada, entornos virtuales ni scripts externos de reparación.
