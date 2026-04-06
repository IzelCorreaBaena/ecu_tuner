"""
modules/connection_module.py
============================
MÓDULO 1: CONEXIÓN
==================
Gestiona todo el ciclo de vida de la comunicación con el vehículo:
  - Detección automática de puertos seriales/USB
  - Negociación de baudios
  - Selección de protocolo OBD-II (ISO 9141, CAN ISO 15765, KWP2000...)
  - Establecimiento del flujo de datos con el bus CAN
  - Envío/recepción de PIDs y tramas brutas

PROTOCOLOS SOPORTADOS (simulados en modo demo):
  - ELM327  → Adaptador USB/BT barato, protocolo AT commands
  - J2534   → Interfaz profesional, acceso directo al bus CAN
  - ISO 15765-4 (CAN) → Protocolo estándar para ECUs modernas
  - KWP2000 (ISO 14230) → Vehículos más antiguos

HARDWARE REAL vs SIMULACIÓN:
  En producción, esta clase usaría `pyserial` (ELM327) o
  `python-can` (J2534/CAN directo). En modo demo simula respuestas.
"""

import time
import logging
import threading
from typing import Optional, Callable
from enum import Enum

logger = logging.getLogger("ECUTuner.Connection")


# ─── Enumeraciones de protocolo ────────────────────────────────────────────

class OBDProtocol(Enum):
    """
    Protocolos OBD-II soportados.
    El ELM327 los detecta automáticamente; J2534 requiere selección manual.
    """
    AUTO            = "0"   # Auto-detección (ELM327)
    SAE_J1850_PWM   = "1"   # Ford antiguo
    SAE_J1850_VPW   = "2"   # GM antiguo
    ISO_9141_2      = "3"   # Europa años 90
    ISO_14230_KWP   = "4"   # KWP2000 (coche 2000-2008)
    ISO_15765_CAN   = "6"   # CAN 500kbps — más común hoy
    ISO_15765_CAN_B = "8"   # CAN 250kbps


class ConnectionState(Enum):
    IDLE        = "idle"
    CONNECTING  = "connecting"
    CONNECTED   = "connected"
    ERROR       = "error"


# ─── Constantes ELM327 (AT Commands) ───────────────────────────────────────
ELM327_COMMANDS = {
    "reset":          "ATZ",       # Reset total del adaptador
    "echo_off":       "ATE0",      # Desactivar eco (más limpio para parsear)
    "linefeeds_off":  "ATL0",      # Sin saltos de línea extra
    "headers_on":     "ATH1",      # Mostrar headers CAN (necesario para tuning)
    "protocol_auto":  "ATSP0",     # Auto-selección de protocolo
    "device_info":    "ATI",       # Versión del adaptador
    "voltage":        "ATRV",      # Voltaje de batería del vehículo
    "pid_supported":  "0100",      # PID: lista de PIDs soportados
}

# PIDs estándar OBD-II (SAE J1979) relevantes para VW Polo TSI
OBD_PIDS = {
    "0104": ("engine_load",    "%",     lambda r: int(r, 16) / 2.55),
    "0105": ("coolant_temp",   "°C",    lambda r: int(r, 16) - 40),
    "010B": ("intake_pressure","kPa",   lambda r: int(r, 16)),
    "010C": ("rpm",            "RPM",   lambda r: int(r[:2], 16) * 256 + int(r[2:4], 16) / 4),
    "010D": ("vehicle_speed",  "km/h",  lambda r: int(r, 16)),
    "010F": ("intake_temp",    "°C",    lambda r: int(r, 16) - 40),
    "0111": ("throttle_pos",   "%",     lambda r: int(r, 16) / 2.55),
    "012F": ("fuel_level",     "%",     lambda r: int(r, 16) / 2.55),
    "0122": ("fuel_pressure",  "kPa",   lambda r: int(r, 16)),
    "015E": ("fuel_press_high","kPa",   lambda r: int(r, 16) * 3),
    "015C": ("oil_temp",       "°C",    lambda r: int(r, 16) - 40),
    "0142": ("sensor_crank",   "°",     lambda r: int(r[:2], 16) * 256 + int(r[2:4], 16) / 2),
}


# ─── Módulo principal ───────────────────────────────────────────────────────

class ConnectionModule:
    """
    Gestiona la conexión física y lógica con el vehículo.

    Flujo de conexión:
      scan_ports() → connect() → _handshake() → _negotiate_protocol()
                   → _identify_ecu() → [CONNECTED]
    """

    def __init__(self, ctx, notify: Callable):
        self.ctx = ctx
        self._notify = notify
        self._serial = None          # pyserial.Serial en hardware real
        self._connected = False
        self._read_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.state = ConnectionState.IDLE
        logger.info("ConnectionModule listo.")

    # ─── Descubrimiento de puertos ──────────────────────────────────────

    def scan_ports(self) -> list[str]:
        """
        Escanea el sistema en busca de puertos seriales/USB disponibles.

        En hardware real: usa serial.tools.list_ports.comports()
        En modo demo: devuelve puertos simulados.

        Returns:
            Lista de strings con nombres de puerto (ej: ["COM3", "/dev/ttyUSB0"])
        """
        try:
            # ── PRODUCCIÓN: descomentar estas líneas ──
            # import serial.tools.list_ports
            # ports = serial.tools.list_ports.comports()
            # return [p.device for p in ports if p.description]

            # ── DEMO: puertos simulados para VW Polo ──
            demo_ports = [
                "DEMO:COM3 (ELM327 v2.1 - VW Polo)",
                "DEMO:COM5 (J2534 PassThru - VAG)",
                "DEMO:COM7 (Bluetooth OBD - VW",
            ]
            logger.info(f"Puertos detectados (demo): {demo_ports}")
            return demo_ports

        except Exception as e:
            logger.error(f"Error escaneando puertos: {e}")
            return []

    # ─── Conexión principal ─────────────────────────────────────────────

    def connect(self, port: str, baudrate: int, protocol: str):
        """
        Establece la conexión con el adaptador OBD-II.

        Parámetros:
          port      → Puerto serial (ej: "COM3", "/dev/ttyUSB0")
          baudrate  → Velocidad serial (38400 estándar ELM327, 500000 CAN)
          protocol  → Código OBD-II (ver OBDProtocol enum)

        Ejecuta en hilo separado para no bloquear la UI.
        """
        logger.info(f"Iniciando conexión: puerto={port}, baud={baudrate}, protocolo={protocol}")
        thread = threading.Thread(
            target=self._connect_sequence,
            args=(port, baudrate, protocol),
            daemon=True,
            name="ConnectionThread"
        )
        thread.start()

    def _connect_sequence(self, port: str, baudrate: int, protocol: str):
        """
        Secuencia completa de conexión (ejecuta en hilo worker).

        Pasos:
          1. Abrir puerto serial
          2. Reset del adaptador (ATZ)
          3. Configurar modo silencioso (echo off, headers on)
          4. Seleccionar protocolo
          5. Identificar la ECU
          6. Leer información del vehículo
        """
        try:
            self._notify("connection_progress", step="Abriendo puerto serial...", pct=10)
            self._open_serial(port, baudrate)
            time.sleep(0.5)

            self._notify("connection_progress", step="Reseteando adaptador ELM327...", pct=25)
            self._send_at_command(ELM327_COMMANDS["reset"])
            time.sleep(1.5)  # El ELM327 tarda ~1s en reset

            self._notify("connection_progress", step="Configurando parámetros...", pct=40)
            self._configure_adapter()
            time.sleep(0.3)

            self._notify("connection_progress", step=f"Negociando protocolo {protocol}...", pct=55)
            self._negotiate_protocol(protocol)
            time.sleep(0.5)

            self._notify("connection_progress", step="Identificando ECU...", pct=70)
            ecu_info = self._identify_ecu()

            self._notify("connection_progress", step="Leyendo datos del vehículo...", pct=85)
            vehicle_data = self._read_vehicle_info()

            # ── Éxito ──
            self._connected = True
            self.ctx.connected_port = port
            self.ctx.ecu_info = {**ecu_info, **vehicle_data}

            from core.app_controller import AppState
            self.ctx.state = AppState.CONNECTED

            logger.info(f"✓ Conexión establecida. ECU info: {self.ctx.ecu_info}")
            self._notify("connection_progress", step="¡Conectado!", pct=100)
            self._notify("connected", ecu_info=self.ctx.ecu_info)

            # Arrancar hilo de lectura continua de datos en tiempo real
            self._start_live_data_thread()

        except Exception as e:
            logger.error(f"Error en secuencia de conexión: {e}")
            from core.app_controller import AppState
            self.ctx.state = AppState.ERROR
            self.ctx.last_error = str(e)
            self._notify("connection_error", error=str(e))

    def _open_serial(self, port: str, baudrate: int):
        """
        Abre el puerto serial físico.

        En hardware real:
          import serial
          self._serial = serial.Serial(
              port=port, baudrate=baudrate,
              timeout=1, bytesize=serial.EIGHTBITS,
              parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE
          )

        En demo: simula la apertura.
        """
        logger.debug(f"[DEMO] Abriendo puerto serial: {port} @ {baudrate} baud")
        # DEMO: no abrimos serial real
        time.sleep(0.2)

    def _configure_adapter(self):
        """
        Envía comandos de configuración inicial al ELM327.
        Desactiva echo, activa headers CAN para ver todos los bytes de la trama.
        """
        config_commands = [
            ELM327_COMMANDS["echo_off"],
            ELM327_COMMANDS["linefeeds_off"],
            ELM327_COMMANDS["headers_on"],
        ]
        for cmd in config_commands:
            response = self._send_at_command(cmd)
            logger.debug(f"AT cmd {cmd} → {response}")
            time.sleep(0.1)

    def _negotiate_protocol(self, protocol: str):
        """
        Selecciona el protocolo de bus.

        Para CAN (ISO 15765-4):
          - 500kbps para coches modernos (>2008)
          - 250kbps para algunos diesels y coches antiguos
          - El ELM327 puede auto-detectarlo con ATSP0

        Para diagnóstico profesional con J2534:
          - Se usa PassThruConnect() de la API J2534
          - Permite acceso directo al bus sin AT commands
        """
        cmd = f"ATSP{protocol}"
        response = self._send_at_command(cmd)
        logger.debug(f"Protocolo seleccionado: {protocol} → {response}")

    def _identify_ecu(self) -> dict:
        """
        Lee los identificadores de la ECU para VW Polo.

        En un vehículo real, se usan servicios UDS (ISO 14229):
          - SID 0x22 + DID 0xF190 → VIN del vehículo
          - SID 0x22 + DID 0xF18C → Número de serie ECU
          - SID 0x22 + DID 0xF187 → Part number de software
          - SID 0x22 + DID 0xF189 → Versión de software

        VW Polo usa ECUs Bosch:
          - 1.0 TSI: ME17.5.22 / Bosch EDC17C74 (en algunos markets)
          - 1.4 TSI: MED17.5.5 / ME17.5.21
          - 1.6 MPI: Magneti Marelli 4GV
        """
        logger.debug("[DEMO] Identificando ECU VW Polo via UDS SID 0x22...")
        return {
            "ecu_type":        "Bosch ME17.5.22",
            "software_version": "1037508740",
            "hardware_version": "1037508739",
            "vin":             "WVWZZZ6RZHY123456",
            "part_number":     "03C906026E",
            "supplier":        "0281015120",
            "flash_size_kb":   2048,
            "vehicle":         "VW Polo 1.0 TSI",
            "engine":          "999cc Turbo",
            "power":           "95-115 PS",
            "torque":          "175-200 Nm",
        }

    def _read_vehicle_info(self) -> dict:
        """
        Lee parámetros básicos del VW Polo en tiempo real.
        Usa los PIDs estándar OBD-II definidos en OBD_PIDS.
        """
        logger.debug("[DEMO] Leyendo PIDs del VW Polo...")
        return {
            "battery_voltage": "12.6V",
            "coolant_temp":    "88°C",
            "rpm":             "850 RPM (ralentí)",
            "protocol_used":   "ISO 15765-4 CAN (500kbps)",
            "fuel_pressure":   "3.5 bar (baja)",
            "oil_temp":        "95°C",
            "intake_temp":     "32°C",
        }

    # ─── Comunicación de bajo nivel ────────────────────────────────────

    def _send_at_command(self, command: str) -> str:
        """
        Envía un comando AT al ELM327 y espera respuesta.

        En hardware real:
          self._serial.write(f"{command}\r".encode())
          response = b""
          while True:
              chunk = self._serial.read(64)
              if b">" in chunk:  # ">" indica fin de respuesta ELM327
                  response += chunk
                  break
          return response.decode("ascii", errors="ignore").strip()

        En demo: retorna respuestas estáticas simuladas.
        """
        logger.debug(f"[AT CMD] → {command}")
        demo_responses = {
            "ATZ":   "ELM327 v2.1",
            "ATE0":  "OK",
            "ATL0":  "OK",
            "ATH1":  "OK",
            "ATSP0": "OK",
            "ATI":   "ELM327 v2.1",
            "ATRV":  "12.4V",
        }
        time.sleep(0.05)  # Simular latencia serial
        return demo_responses.get(command, "OK")

    def send_raw_can_frame(self, arbitration_id: int, data: bytes) -> bytes:
        """
        Envía una trama CAN bruta al bus.

        Usado por el módulo de backup y flash para comunicación UDS directa.
        Formato trama CAN: [ID 11-bit][DLC][Data 0-8 bytes]

        En hardware real con python-can:
          msg = can.Message(
              arbitration_id=arbitration_id,
              data=data,
              is_extended_id=False
          )
          self._can_bus.send(msg)
          response = self._can_bus.recv(timeout=1.0)
          return bytes(response.data)
        """
        logger.debug(f"[CAN TX] ID={hex(arbitration_id)} Data={data.hex()}")
        # DEMO: simular respuesta ACK
        return bytes([0x06, 0x50] + list(data[:2]) + [0x00, 0x00, 0x00])

    # ─── Live data (tiempo real) ────────────────────────────────────────

    def _start_live_data_thread(self):
        """
        Arranca un hilo que lee parámetros del motor en tiempo real.
        Los datos se emiten como evento para que la UI los muestre.
        Ciclo de actualización: ~100ms (10 Hz).
        """
        self._stop_event.clear()
        self._read_thread = threading.Thread(
            target=self._live_data_loop,
            daemon=True,
            name="LiveDataThread"
        )
        self._read_thread.start()
        logger.info("Hilo de live data arrancado.")

    def _live_data_loop(self):
        """
        Loop de lectura continua de PIDs en tiempo real para VW Polo.
        Simula variaciones de RPM, temperatura, boost, etc. específicas del TSI.
        """
        import random
        import math
        t = 0
        while not self._stop_event.is_set():
            rpm = int(850 + abs(math.sin(t * 0.1)) * 5000)
            live = {
                "rpm":          rpm,
                "coolant_temp": 88 + random.randint(-3, 3),
                "throttle_pos": round(random.uniform(0, 12), 1),
                "boost_kpa":    abs(int(math.sin(t * 0.15) * 120)),
                "battery_v":    round(13.7 + random.uniform(-0.2, 0.2), 1),
                "intake_temp":  30 + random.randint(-5, 10),
                "fuel_press":   round(random.uniform(3.0, 4.0), 1),
                "oil_temp":     92 + random.randint(-4, 4),
            }
            self._notify("live_data_update", data=live)
            t += 1
            time.sleep(0.1)

    def disconnect(self):
        """Cierra la conexión limpiamente."""
        self._stop_event.set()
        if self._serial:
            self._serial.close()
        self._connected = False
        logger.info("Conexión cerrada.")
