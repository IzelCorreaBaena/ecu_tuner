"""
modules/diagnostic_module.py
=============================
MÓDULO DE DIAGNÓSTICO OBD-II
=============================
Gestiona lectura e interpretación de DTCs (Diagnostic Trouble Codes),
datos en tiempo real (PIDs) e información del vehículo.

PROTOCOLOS CUBIERTOS:
  - OBD-II SAE J1979 (Modos 01-09)
  - ISO 15031-6 (DTCs estándar P/B/C/U)
  - UDS ISO 14229 (DTCs extendidos)

MODOS OBD-II:
  01 → Datos en tiempo real (sensor actual)
  02 → Datos congelados (freeze frame en fallo)
  03 → Leer DTCs confirmados
  04 → Borrar DTCs y reset MIL
  07 → DTCs pendientes (no confirmados)
  09 → Información del vehículo (VIN, calibración)
"""

import logging
import threading
import time
import math
import random
from typing import Callable, List, Dict, Optional

logger = logging.getLogger("ECUTuner.Diagnostic")


# ─── Base de datos de DTCs (Códigos de Fallo) ──────────────────────────────
# Formato: código → (descripción_es, sistema, severidad)
# Severidad: "high" = crítico, "medium" = moderado, "low" = informativo

DTC_DATABASE: Dict[str, tuple] = {
    # ── Sensores admisión ───────────────────────────────────────────────────
    "P0100": ("Fallo circuito sensor flujo de masa de aire (MAF)", "Motor", "medium"),
    "P0101": ("Rango/rendimiento sensor MAF fuera de especificación", "Motor", "medium"),
    "P0102": ("Señal baja en sensor MAF — circuito A", "Motor", "medium"),
    "P0103": ("Señal alta en sensor MAF — circuito A", "Motor", "medium"),
    "P0106": ("Rango/rendimiento sensor presión colector (MAP)", "Motor", "medium"),
    "P0107": ("Señal baja sensor MAP", "Motor", "medium"),
    "P0108": ("Señal alta sensor MAP", "Motor", "medium"),
    "P0110": ("Fallo sensor temperatura aire admisión (IAT)", "Motor", "low"),
    "P0112": ("Señal baja sensor IAT", "Motor", "low"),
    "P0113": ("Señal alta sensor IAT", "Motor", "low"),
    "P0115": ("Fallo sensor temperatura refrigerante (ECT)", "Motor", "high"),
    "P0116": ("Rango/rendimiento sensor ECT fuera de rango", "Motor", "high"),
    "P0117": ("Señal baja sensor ECT", "Motor", "high"),
    "P0118": ("Señal alta sensor ECT", "Motor", "high"),
    "P0120": ("Fallo circuito sensor posición mariposa (TPS)", "Motor", "medium"),
    "P0121": ("Rango/rendimiento sensor TPS", "Motor", "medium"),
    "P0122": ("Señal baja sensor TPS — circuito A", "Motor", "medium"),
    "P0123": ("Señal alta sensor TPS — circuito A", "Motor", "medium"),
    # ── Sondas Lambda (O2) ──────────────────────────────────────────────────
    "P0130": ("Sensor O2 banco 1 sonda 1 — fallo circuito", "Emisiones", "medium"),
    "P0131": ("Sensor O2 banco 1 sonda 1 — voltaje bajo", "Emisiones", "medium"),
    "P0132": ("Sensor O2 banco 1 sonda 1 — voltaje alto", "Emisiones", "medium"),
    "P0133": ("Sensor O2 banco 1 sonda 1 — respuesta lenta", "Emisiones", "low"),
    "P0134": ("Sensor O2 banco 1 sonda 1 — sin actividad", "Emisiones", "medium"),
    "P0135": ("Calefactor sensor O2 banco 1 sonda 1 — fallo", "Emisiones", "low"),
    "P0136": ("Sensor O2 banco 1 sonda 2 — fallo circuito", "Emisiones", "medium"),
    "P0141": ("Calefactor sensor O2 banco 1 sonda 2 — fallo", "Emisiones", "low"),
    # ── Mezcla / Combustible ────────────────────────────────────────────────
    "P0170": ("Ajuste mezcla combustible banco 1 fuera de rango", "Combustible", "medium"),
    "P0171": ("Sistema demasiado pobre banco 1 (mezcla lean)", "Combustible", "medium"),
    "P0172": ("Sistema demasiado rico banco 1 (mezcla rich)", "Combustible", "medium"),
    "P0174": ("Sistema demasiado pobre banco 2 (mezcla lean)", "Combustible", "medium"),
    "P0175": ("Sistema demasiado rico banco 2 (mezcla rich)", "Combustible", "medium"),
    "P0087": ("Presión carril combustible demasiado baja", "Combustible", "high"),
    "P0088": ("Presión carril combustible demasiado alta", "Combustible", "high"),
    "P0089": ("Regulación presión combustible — rendimiento", "Combustible", "medium"),
    "P0190": ("Fallo circuito sensor presión combustible (FRP)", "Combustible", "high"),
    "P0192": ("Señal baja sensor presión combustible", "Combustible", "high"),
    "P0193": ("Señal alta sensor presión combustible", "Combustible", "high"),
    "P2187": ("Sistema demasiado pobre en ralentí banco 1", "Combustible", "medium"),
    "P2293": ("Regulador presión combustible — rendimiento", "Combustible", "medium"),
    # ── Encendido / Misfires ─────────────────────────────────────────────────
    "P0300": ("Fallo de encendido aleatorio en múltiples cilindros", "Encendido", "high"),
    "P0301": ("Fallo de encendido — cilindro 1", "Encendido", "high"),
    "P0302": ("Fallo de encendido — cilindro 2", "Encendido", "high"),
    "P0303": ("Fallo de encendido — cilindro 3", "Encendido", "high"),
    "P0304": ("Fallo de encendido — cilindro 4", "Encendido", "high"),
    "P0320": ("Fallo circuito sensor posición cigüeñal (CKP)", "Encendido", "high"),
    "P0321": ("Rango/rendimiento sensor CKP", "Encendido", "high"),
    "P0322": ("Señal ausente sensor CKP", "Encendido", "high"),
    "P0325": ("Fallo circuito sensor detonación (knock) banco 1", "Encendido", "medium"),
    "P0327": ("Señal baja sensor detonación banco 1", "Encendido", "medium"),
    "P0328": ("Señal alta sensor detonación banco 1", "Encendido", "medium"),
    "P0335": ("Fallo circuito sensor posición árbol de levas (CMP)", "Encendido", "high"),
    "P0341": ("Rango/rendimiento sensor CMP banco 1", "Encendido", "high"),
    "P0345": ("Fallo circuito sensor CMP banco 2", "Encendido", "high"),
    # ── VVT / Distribución variable ─────────────────────────────────────────
    "P0011": ("Árbol levas banco 1 pos A — demasiado avanzado (VVT)", "VVT", "medium"),
    "P0012": ("Árbol levas banco 1 pos A — demasiado retrasado (VVT)", "VVT", "medium"),
    "P0014": ("Árbol levas banco 1 pos B — demasiado avanzado (VVT)", "VVT", "medium"),
    "P0016": ("Correlación árbol levas/cigüeñal banco 1 pos A", "VVT", "high"),
    "P0017": ("Correlación árbol levas/cigüeñal banco 1 pos B", "VVT", "high"),
    # ── Turbocompresor ──────────────────────────────────────────────────────
    "P0234": ("Sobrealimentación excesiva detectada (overboost)", "Turbo", "high"),
    "P0235": ("Fallo circuito sensor presión turbocompresor", "Turbo", "medium"),
    "P0236": ("Rango/rendimiento sensor presión turbo", "Turbo", "medium"),
    "P0237": ("Señal baja sensor presión turbocompresor", "Turbo", "medium"),
    "P0238": ("Señal alta sensor presión turbocompresor", "Turbo", "medium"),
    "P0243": ("Fallo solenoide wastegate turbocompresor", "Turbo", "high"),
    "P0245": ("Señal baja solenoide wastegate", "Turbo", "high"),
    "P0246": ("Señal alta solenoide wastegate", "Turbo", "high"),
    # ── Catalizador / Emisiones ──────────────────────────────────────────────
    "P0400": ("Fallo sistema recirculación gases escape (EGR)", "Emisiones", "low"),
    "P0401": ("Flujo EGR insuficiente detectado", "Emisiones", "low"),
    "P0402": ("Flujo EGR excesivo detectado", "Emisiones", "low"),
    "P0420": ("Eficiencia catalizador por debajo del umbral banco 1", "Emisiones", "medium"),
    "P0421": ("Umbral calentamiento catalizador banco 1 bajo", "Emisiones", "medium"),
    "P0430": ("Eficiencia catalizador por debajo del umbral banco 2", "Emisiones", "medium"),
    "P0440": ("Fallo genérico sistema evaporativo (EVAP)", "Emisiones", "low"),
    "P0441": ("Flujo incorrecto purgado sistema EVAP", "Emisiones", "low"),
    "P0442": ("Fuga pequeña detectada sistema EVAP", "Emisiones", "low"),
    "P0455": ("Fuga grande detectada sistema EVAP", "Emisiones", "medium"),
    "P0456": ("Fuga muy pequeña detectada sistema EVAP", "Emisiones", "low"),
    # ── Sistema eléctrico ────────────────────────────────────────────────────
    "P0560": ("Voltaje de sistema bajo (batería/alternador)", "Eléctrico", "high"),
    "P0562": ("Voltaje sistema bajo — condición intermitente", "Eléctrico", "medium"),
    "P0563": ("Voltaje sistema alto", "Eléctrico", "medium"),
    "P0600": ("Fallo bus de comunicación serial de la ECU", "Eléctrico", "high"),
    "P0604": ("Error en memoria RAM interna de la ECU", "Eléctrico", "high"),
    "P0605": ("Error en memoria ROM interna de la ECU", "Eléctrico", "high"),
    "P0606": ("Fallo procesador principal de la ECU", "Eléctrico", "high"),
    # ── Transmisión ──────────────────────────────────────────────────────────
    "P0700": ("Solicitud luz MIL desde módulo TCM (transmisión)", "Transmisión", "high"),
    "P0705": ("Fallo circuito sensor selector marcha (TR)", "Transmisión", "medium"),
    "P0715": ("Fallo circuito sensor velocidad turbina entrada", "Transmisión", "medium"),
    "P0720": ("Fallo circuito sensor velocidad salida transmisión", "Transmisión", "medium"),
    "P0730": ("Relación de marcha incorrecta detectada", "Transmisión", "medium"),
    "P0740": ("Fallo circuito embrague convertidor par (TCC)", "Transmisión", "medium"),
}

# ─── PIDs OBD-II con metadatos para la UI ──────────────────────────────────
OBD_PID_INFO: Dict[str, dict] = {
    "rpm":           {"label": "RPM Motor",          "unit": "RPM",   "min": 0,    "max": 7000, "warn": 6500},
    "coolant_temp":  {"label": "Temp. Refrigerante",  "unit": "°C",   "min": -40,  "max": 130,  "warn": 110},
    "intake_temp":   {"label": "Temp. Admisión",      "unit": "°C",   "min": -40,  "max": 80,   "warn": 60},
    "throttle_pos":  {"label": "Posición Mariposa",   "unit": "%",    "min": 0,    "max": 100,  "warn": 95},
    "boost_kpa":     {"label": "Presión Turbo",       "unit": "kPa",  "min": 0,    "max": 250,  "warn": 220},
    "engine_load":   {"label": "Carga Motor",         "unit": "%",    "min": 0,    "max": 100,  "warn": 95},
    "battery_v":     {"label": "Tensión Batería",     "unit": "V",    "min": 10.0, "max": 15.0, "warn": 14.5},
    "fuel_press":    {"label": "Presión Combustible", "unit": "bar",  "min": 0,    "max": 6.0,  "warn": 5.5},
    "oil_temp":      {"label": "Temp. Aceite",        "unit": "°C",   "min": -40,  "max": 150,  "warn": 130},
    "vehicle_speed": {"label": "Velocidad",           "unit": "km/h", "min": 0,    "max": 260,  "warn": 240},
    "timing_adv":    {"label": "Avance Encendido",    "unit": "°",    "min": -20,  "max": 50,   "warn": 45},
    "o2_voltage":    {"label": "Sonda Lambda O2",     "unit": "V",    "min": 0,    "max": 1.2,  "warn": 1.1},
}


class DiagnosticModule:
    """
    Módulo de diagnóstico OBD-II completo.

    Funciones principales:
      read_dtcs()         → Leer DTCs confirmados (Modo 03)
      read_pending_dtcs() → Leer DTCs pendientes (Modo 07)
      clear_dtcs()        → Borrar DTCs + reset MIL (Modo 04)
      read_freeze_frame() → Leer datos freeze frame (Modo 02)
      read_vin()          → Leer VIN del vehículo (Modo 09)
      get_readiness_tests()→ Estado monitors OBD (ITV)
      start_live()        → Iniciar lectura continua de PIDs
      stop()              → Detener lectura continua
    """

    def __init__(self, ctx, notify: Callable):
        self.ctx = ctx
        self._notify = notify
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._active_dtcs: List[Dict] = []
        self._pending_dtcs: List[Dict] = []
        self._freeze_frame: Dict = {}
        self._mil_on: bool = False
        logger.info("DiagnosticModule listo.")

    # ─── Lectura de DTCs ────────────────────────────────────────────────

    def read_dtcs(self) -> List[Dict]:
        """
        Lee DTCs confirmados (OBD Modo 03).
        En hardware real: enviar '03\\r' al ELM327, parsear respuesta.
        """
        logger.info("Leyendo DTCs confirmados (Modo 03)...")
        demo_codes = ["P0300", "P0420", "P0171", "P0087", "P0016"]
        self._active_dtcs = [self._build_dtc_record(c, "confirmed") for c in demo_codes]
        self._mil_on = bool(self._active_dtcs)
        logger.info(f"DTCs leídos: {[d['code'] for d in self._active_dtcs]}")
        self._notify("dtc_update",
                     dtcs=self._active_dtcs,
                     pending=self._pending_dtcs,
                     mil=self._mil_on,
                     count=len(self._active_dtcs))
        return self._active_dtcs

    def read_pending_dtcs(self) -> List[Dict]:
        """
        Lee DTCs pendientes (OBD Modo 07).
        Pendientes = detectados pero no confirmados (aún sin 2 ciclos de conducción).
        """
        logger.info("Leyendo DTCs pendientes (Modo 07)...")
        self._pending_dtcs = [self._build_dtc_record(c, "pending") for c in ["P0133", "P0401"]]
        self._notify("dtc_update",
                     dtcs=self._active_dtcs,
                     pending=self._pending_dtcs,
                     mil=self._mil_on,
                     count=len(self._active_dtcs))
        return self._pending_dtcs

    def clear_dtcs(self) -> bool:
        """
        Borra DTCs y resetea el indicador MIL (OBD Modo 04).
        En hardware real: enviar '04\\r' al ELM327.
        """
        logger.info("Borrando DTCs (Modo 04)...")
        self._active_dtcs = []
        self._pending_dtcs = []
        self._freeze_frame = {}
        self._mil_on = False
        self._notify("dtc_update", dtcs=[], pending=[], mil=False, count=0)
        self._notify("dtc_cleared")
        logger.info("DTCs borrados y MIL reseteado.")
        return True

    def read_freeze_frame(self) -> Dict:
        """
        Lee datos congelados en el momento del primer fallo (Modo 02).
        Solo disponible cuando existen DTCs confirmados.
        """
        if not self._active_dtcs:
            return {}
        self._freeze_frame = {
            "trigger_dtc":   self._active_dtcs[0]["code"],
            "rpm":           2340,
            "coolant_temp":  87,
            "throttle_pos":  42.3,
            "engine_load":   68.5,
            "vehicle_speed": 65,
            "fuel_press":    3.1,
            "boost_kpa":     98,
        }
        self._notify("freeze_frame_update", data=self._freeze_frame)
        return self._freeze_frame

    def read_vin(self) -> str:
        """Lee el VIN del vehículo (Modo 09, PID 02)."""
        vin = self.ctx.ecu_info.get("vin", "WVWZZZ6RZHY123456")
        self._notify("vin_read", vin=vin)
        return vin

    def get_readiness_tests(self) -> Dict[str, str]:
        """
        Estado de los monitors OBD-II (Modo 01, PID 01).
        Necesario para pasar la ITV/revisión de emisiones.
        """
        return {
            "MIL (Luz Avería)":        "ON" if self._mil_on else "OFF",
            "Catalizador":             "Completo",
            "Sonda calefactada O2":    "Completo",
            "Sistema EVAP":            "Incompleto",
            "EGR / VVT":               "Completo",
            "Sensor O2":               "Completo",
            "Sistema combustible":     "Completo",
            "Fallo encendido":         "Completo",
            "Temperatura global":      "Completo",
        }

    # ─── Live data (PIDs en tiempo real) ────────────────────────────────

    def start_live(self):
        """Inicia lectura continua de PIDs simulando un motor TSI."""
        self._stop_event.clear()
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._live_loop, daemon=True, name="DiagnosticLive"
        )
        self._thread.start()
        logger.info("Live data arrancado.")

    def stop(self):
        """Detiene la lectura continua de PIDs."""
        self._stop_event.set()

    def _live_loop(self):
        """
        Simula un ciclo de conducción: ralentí → aceleración → crucero → frenada.
        Genera variaciones realistas de todos los sensores del VW Polo TSI.
        """
        t = 0
        while not self._stop_event.is_set():
            cycle_t = t % 200
            if cycle_t < 40:       # ralentí
                rpm_b, load_b, spd_b, boost_b = 850, 12, 0, 5
            elif cycle_t < 90:     # aceleración
                f = (cycle_t - 40) / 50.0
                rpm_b   = int(850 + f * 5000)
                load_b  = int(12 + f * 80)
                spd_b   = int(f * 120)
                boost_b = int(f * 190)
            elif cycle_t < 150:    # crucero
                rpm_b, load_b, spd_b, boost_b = 2800, 45, 120, 110
            else:                  # frenada
                f = (cycle_t - 150) / 50.0
                rpm_b   = int(2800 - f * 1950)
                load_b  = int(45 - f * 35)
                spd_b   = int(120 - f * 120)
                boost_b = int(110 - f * 105)

            n = lambda x=3: random.randint(-x, x)
            data = {
                "rpm":           max(0, rpm_b + n(50)),
                "coolant_temp":  88 + n(2),
                "intake_temp":   32 + n(5),
                "throttle_pos":  round(min(100, max(0, load_b * 0.8 + n(2))), 1),
                "boost_kpa":     max(0, boost_b + n(8)),
                "engine_load":   round(min(100, max(0, load_b + n(3))), 1),
                "battery_v":     round(13.8 + random.uniform(-0.3, 0.3), 2),
                "fuel_press":    round(3.5 + random.uniform(-0.3, 0.3), 2),
                "oil_temp":      94 + n(3),
                "vehicle_speed": max(0, spd_b + n(3)),
                "timing_adv":    round(18 + (rpm_b / 7000) * 15 + n(2), 1),
                "o2_voltage":    round(0.45 + math.sin(t * 0.3) * 0.45, 3),
            }
            self._notify("live_data_update", data=data)
            t += 1
            time.sleep(0.25)

    # ─── Helpers ────────────────────────────────────────────────────────

    def _build_dtc_record(self, code: str, dtc_type: str) -> Dict:
        info = DTC_DATABASE.get(code, (
            f"Código desconocido ({code})", "Desconocido", "low"
        ))
        return {
            "code":        code,
            "description": info[0],
            "system":      info[1],
            "severity":    info[2],
            "type":        dtc_type,
        }
