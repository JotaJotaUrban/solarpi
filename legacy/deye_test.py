from pysolarmanv5 import PySolarmanV5
from datetime import datetime
import time

IP = "192.168.1.137"
SERIAL = 3594884342
INTERVALO = 4  # segundos

# Leeremos todo este bloque de una sola vez
START_REGISTER = 0x0096
END_REGISTER = 0x00BF
QUANTITY = END_REGISTER - START_REGISTER + 1


def signed16(value):
    """Convierte un registro unsigned de 16 bits en signed."""
    return value - 65536 if value > 32767 else value


def reg(data, address):
    """Obtiene un registro por su dirección."""
    return data[address - START_REGISTER]


def battery_mode(power):
    if power > 30:
        return "DESCARGANDO"
    if power < -30:
        return "CARGANDO"
    return "ESPERA"


modbus = PySolarmanV5(
    IP,
    SERIAL,
    port=8899,
    mb_slave_id=1,
    socket_timeout=10,
    auto_reconnect=True
)

print("Monitor Deye iniciado. Ctrl+C para salir.\n")

try:
    while True:
        try:
            data = modbus.read_holding_registers(
                register_addr=START_REGISTER,
                quantity=QUANTITY
            )

            # CASA
            casa = reg(data, 0x00B2)

            # PLACAS
            pv1 = reg(data, 0x00BA)
            pv2 = reg(data, 0x00BB)
            solar = pv1 + pv2

            # BATERÍA
            soc = reg(data, 0x00B8)
            bat_voltage = reg(data, 0x00B7) * 0.01
            bat_current = signed16(reg(data, 0x00BF)) * 0.01
            bat_power = signed16(reg(data, 0x00BE))
            bat_mode = battery_mode(bat_power)

            # RED
            grid_power = signed16(reg(data, 0x00A9))
            grid_voltage = reg(data, 0x0096) * 0.1

            # POTENCIA DEL INVERSOR
            inverter_power = signed16(reg(data, 0x00AF))

            # Texto para la red
            if grid_power > 0:
                grid_text = f"IMPORTANDO {grid_power} W"
            elif grid_power < 0:
                grid_text = f"EXPORTANDO {abs(grid_power)} W"
            else:
                grid_text = "0 W"

            ahora = datetime.now().strftime("%H:%M:%S")

            print(
                f"{ahora} | "
                f"CASA {casa:5d} W | "
                f"SOLAR {solar:5d} W "
                f"(PV1 {pv1:4d} + PV2 {pv2:4d}) | "
                f"BAT {soc:3d}% {bat_mode:11s} {abs(bat_power):4d} W | "
                f"RED {grid_text}"
            )

            time.sleep(INTERVALO)

        except Exception as e:
            print(f"{datetime.now():%H:%M:%S} | Error de lectura: {e}")
            time.sleep(5)

except KeyboardInterrupt:
    print("\nMonitor detenido.")

finally:
    modbus.disconnect()
