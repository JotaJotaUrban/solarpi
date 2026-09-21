# SolarPi

Monitor local de un inversor Deye/Solarman.

## Versión legacy

La carpeta [`legacy/`](legacy/) conserva la aplicación existente para Raspberry Pi, antes de su evolución hacia un despliegue con Docker Compose en un servidor Debian.

- Backend Python, base de datos SQLite y panel web estático.
- Lectura del inversor por red mediante `pysolarmanv5`.
- Incluye la documentación original y los scripts de despliegue con systemd.
- No incluye bases de datos, datos recuperados, entornos virtuales ni configuración privada `.env`.

Consulta las [instrucciones originales](legacy/README.md) para entender su funcionamiento. Las rutas de Raspberry Pi y los valores predeterminados corresponden a la instalación anterior; deben revisarse antes de ejecutar la aplicación en otro equipo. Esta versión todavía no incluye Docker.

## Procedencia

Importación realizada el 21 de septiembre de 2026 desde `solarpi_app_to_rpi.zip`, fechado localmente el 12 de septiembre de 2026. Sus 27 archivos coinciden byte a byte con los correspondientes de la carpeta local `from_rpi`.

Los archivos de `legacy/` se conservan sin modificaciones. Los ZIP anteriores y los scripts externos de reparación de datos no forman parte de esta instantánea de la aplicación.

## Evolución prevista

La nueva versión se desarrollará fuera de `legacy/`, manteniendo esta carpeta como referencia histórica. El objetivo es un despliegue reproducible con Docker Compose, almacenamiento persistente y copias de seguridad con restauración verificable.
