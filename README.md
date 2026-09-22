# SolarPi

Monitor local Deye/Solarman portado a Docker Compose para Debian. Se conservan las pantallas, los cálculos y la frecuencia de lectura. La API permite exportar y restaurar la base de datos completa. `legacy/` permanece intacto. Las dependencias se fijan a las versiones del entorno local existente.

## Despliegue

Requiere Docker Engine con Compose y acceso de red al inversor.

```bash
git clone https://github.com/JotaJotaUrban/solarpi.git
cd solarpi
cp .env.example .env
nano .env
sudo docker compose up -d --build
```

Revisar IP y número de serie en `.env`. Abrir `http://IP_DEL_HOMELAB`. El puerto publicado es 80 y se cambia con `SOLARPI_WEB_PORT`. Compose fija el puerto interno en 8000 y la base de datos en `/app/data/solarpi.sqlite3`. Las instalaciones existentes conservan el puerto de su `.env`.

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

## API de backup y restauración completa

Configurar `SOLARPI_BACKUP_TOKEN` en `.env` con una clave aleatoria larga (por ejemplo, generada con `openssl rand -hex 32`) y recrear el contenedor con `sudo docker compose up -d`. Sin clave, estos endpoints devuelven 503. No publicar la clave en Git ni incluirla en URLs. La clave protege ambos endpoints; la web existente sigue funcionando igual. Utilizar desde el servidor o una red de confianza; para acceso remoto, usar HTTPS o un túnel SSH.

- `GET /api/backup`: descarga SQLite completo y consistente, incluyendo datos confirmados del WAL, mientras continúa la recogida. No incluye `.env` ni la imagen Docker.
- `POST /api/restore`: recibe el archivo SQLite como cuerpo binario, valida integridad y esquema, detiene y espera a los trabajadores, reemplaza toda la base usando una transacción de SQLite y vuelve a arrancar con las cachés en memoria renovadas. No combina registros. Requiere `X-SolarPi-Confirm: replace-database`.

Ejemplo desde Debian, introduciendo la clave sin escribirla literalmente en el historial de Bash:

```bash
read -rsp 'Clave de backup: ' SOLARPI_TOKEN; echo
curl --fail --show-error -H "Authorization: Bearer $SOLARPI_TOKEN" \
  http://localhost/api/backup -o solarpi-completa.sqlite3
```

Restauración **destructiva para los datos actuales del destino**:

```bash
curl --fail --show-error \
  -H "Authorization: Bearer $SOLARPI_TOKEN" \
  -H 'X-SolarPi-Confirm: replace-database' \
  -H 'Content-Type: application/vnd.sqlite3' \
  --data-binary @solarpi-completa.sqlite3 \
  http://localhost/api/restore
unset SOLARPI_TOKEN
```

Para migrar: desplegar la misma versión de SolarPi en otro host, configurar su `.env` y su clave, e importar allí el archivo descargado. Detener la instancia original al hacer el cambio definitivo; cada instancia recoge datos independientemente.

Se acepta el esquema completo de esta versión (no SQL, CSV ni bases parciales recuperadas de la SD), con un máximo de 4 GiB por subida y 60 segundos de espera por bloque de red. Se requiere espacio libre para el archivo temporal y los archivos de transacción de SQLite. Las peticiones HTTP se serializan durante la operación; la restauración pausa las lecturas una vez validado el archivo. Un archivo inválido no detiene el recolector ni modifica los datos. Una copia SQLite interrumpida revierte la transacción. No se conservan copias automáticas: los temporales se eliminan al terminar la petición. Tras una interrupción brusca del proceso pueden quedar directorios temporales `backup-*`, `restore-*` o `schema-*` en el volumen.

Pruebas locales: `python -m unittest discover -s tests -v`. Cubren exportación con WAL, restauración completa, reinicialización de trabajadores, autorización, rechazo de archivos incompatibles y cancelación de copia con reversión.

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
