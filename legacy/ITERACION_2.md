# SolarPi - Iteración 2

## Objetivo

Seguir puliendo SolarPi como monitor local estable, bonito y útil, manteniendo el backend solar independiente del frontend y de servicios externos como el tiempo.

## Mejoras candidatas

1. Persistencia y visualización histórica del tiempo
   - Guardar algunas muestras meteorológicas junto a las solares.
   - Mostrar si la producción solar encaja con nubosidad, lluvia o franja horaria.

2. Resumen energético diario
   - Energía producida hoy.
   - Energía consumida por el hogar.
   - Energía importada/exportada de red.
   - Energía cargada/descargada de batería.

3. Vista de rendimiento
   - Comparar potencia solar actual contra un máximo esperado por hora.
   - Detectar caídas raras entre PV1 y PV2.
   - Avisar si un string produce mucho menos que el otro.

4. Estados y alertas discretas
   - Sin lectura del inversor.
   - Batería baja.
   - Consumo alto.
   - Importación de red sostenida.
   - Producción solar anómala.

5. Modo pantalla de pared
   - Layout simplificado para tablet o monitor.
   - Números grandes.
   - Menos gráficas pequeñas.
   - Sin scroll si se abre en una pantalla fija.

6. Mejoras del diagrama de flujo
   - Ajustar responsive móvil/tablet.
   - Afinar velocidades de animación según potencia real.
   - Mostrar pequeñas etiquetas de potencia sobre cada línea.

7. Configuración desde la app
   - Elegir puerto web.
   - Cambiar intervalos de lectura.
   - Activar/desactivar clima.
   - Seleccionar ubicación por defecto.

8. Servicio y despliegue
   - Comando único de actualización en RPI.
   - Healthcheck local más claro.
   - Página de diagnóstico con versión, IP del inversor, puerto, última lectura y último error.
   - Evolucionar el footer de salud de la RPI.
   - Cambiar la etiqueta "DISCO" por "HD".
   - Definir umbrales visuales discretos para temperatura, CPU, RAM y HD.
   - Para temperatura: normal hasta 70 °C, aviso desde 70 °C y alerta desde 80 °C.
   - Definir umbrales equivalentes para CPU, RAM y HD en la próxima iteración.

9. Exportación de datos
   - Descargar CSV.
   - Exportar histórico por rango de fechas.
   - Preparar una futura sincronización con servidor externo.

10. Integración futura con domótica
   - Publicar datos por MQTT.
   - Preparar Home Assistant.
   - Mantener cualquier orden de control separada y protegida por una capa explícita de seguridad.

## Primera propuesta de hito

Para la próxima sesión, un buen hito sería: resumen energético diario + página de diagnóstico. Aporta utilidad real, ayuda a depurar la RPI y no nos obliga aún a tocar control domótico.
