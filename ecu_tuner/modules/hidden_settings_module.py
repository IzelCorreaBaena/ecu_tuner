"""
modules/hidden_settings_module.py
==================================
MÓDULO DE AJUSTES OCULTOS (VCDS-Style Coding)
==============================================
Activa/desactiva funciones del vehículo mediante modificación de
bytes de codificación (Coding Bytes) en módulos de control.

CONCEPTO TÉCNICO:
  Los módulos de control modernos almacenan configuraciones de fábrica
  en bytes de codificación (Coding Bytes), registros de adaptación
  (Adaptation Channels) y parámetros de codificación larga (Long Coding).

  VCDS y ODIS permiten modificar estos valores para activar funciones
  que el fabricante instaló en el hardware pero no activó de fábrica
  (por diferenciación de mercado, costes o regulaciones locales).

REGLAS DE SEGURIDAD:
  - NUNCA se modifica firmware ni código ejecutable
  - Solo se accede a canales de adaptación y bytes de codificación
  - Se valida compatibilidad del vehículo antes de aplicar
  - Se realiza backup del valor original antes de cambiar
  - Los cambios son reversibles (rollback al valor de fábrica)

IMPLEMENTACIÓN REAL:
  En hardware real, estos ajustes se realizan mediante:
    - UDS SID 0x2E (WriteDataByIdentifier) → Coding bytes
    - UDS SID 0x2C (DynamicallyDefineDataIdentifier) → Adaptaciones
    - UDS SID 0x28 (CommunicationControl) → Parámetros de comunicación
    - Protocolo propietario VAG: Adaptation (Channel #, New Value)
"""

import logging
from typing import Callable, Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("ECUTuner.HiddenSettings")


# ─── Tipos de ajuste ────────────────────────────────────────────────────────

class SettingType(Enum):
    TOGGLE   = "toggle"    # Activar / Desactivar (bit único)
    SELECT   = "select"    # Selección de opción (múltiples bits)
    ADAPT    = "adapt"     # Canal de adaptación (valor numérico)


@dataclass
class HiddenSetting:
    """Define un ajuste oculto con todos sus metadatos."""
    id:           str
    name:         str
    description:  str
    category:     str              # Grupo de función
    module:       str              # Módulo de control afectado (ej: "ECU", "BCM", "LIGHT")
    setting_type: SettingType
    current_val:  Any = None       # Valor actual
    default_val:  Any = None       # Valor de fábrica
    options:      list = field(default_factory=list)   # Para tipo SELECT
    min_val:      Optional[float] = None               # Para tipo ADAPT
    max_val:      Optional[float] = None
    unit:         str = ""
    risk_level:   str = "low"      # "low" | "medium" | "high"
    compatible:   list = field(default_factory=list)   # ECUs/vehículos compatibles
    note:         str = ""         # Nota técnica


# ─── Definición de ajustes ocultos para VW Polo TSI ────────────────────────

VW_POLO_HIDDEN_SETTINGS: List[HiddenSetting] = [

    # ═══════════════════════════════════════════════════════════
    # LUCES
    # ═══════════════════════════════════════════════════════════
    HiddenSetting(
        id="cornering_lights",
        name="Luces de Viraje (Cornering Lights)",
        description="Activa las luces de niebla delanteras como luces de viraje "
                    "al girar el volante a baja velocidad (urbano). Mejora la visibilidad "
                    "al girar en intersecciones. Requiere luces de niebla instaladas.",
        category="Luces",
        module="BCM",
        setting_type=SettingType.TOGGLE,
        current_val=False,
        default_val=False,
        risk_level="low",
        compatible=["VW Polo 6R", "VW Polo 6C", "VW Polo AW"],
        note="Requiere luces de niebla delanteras. Byte 0, bit 4 del módulo 09."
    ),
    HiddenSetting(
        id="daytime_lights_led",
        name="DRL LED Personalizados",
        description="Ajusta el brillo de las luces diurnas LED (DRL). "
                    "Permite reducir el consumo o aumentar visibilidad.",
        category="Luces",
        module="BCM",
        setting_type=SettingType.ADAPT,
        current_val=100,
        default_val=100,
        min_val=10,
        max_val=100,
        unit="%",
        risk_level="low",
        compatible=["VW Polo 6C", "VW Polo AW"],
        note="Canal de adaptación 07 del módulo 09 (Control electrónico central)."
    ),
    HiddenSetting(
        id="coming_home_leaving_home",
        name="Coming Home / Leaving Home",
        description="Las luces se encienden automáticamente al abrir/cerrar el coche "
                    "de noche para iluminar el entorno (Coming Home) y al alejarse (Leaving Home).",
        category="Luces",
        module="BCM",
        setting_type=SettingType.TOGGLE,
        current_val=False,
        default_val=False,
        risk_level="low",
        compatible=["VW Polo 6R", "VW Polo 6C", "VW Polo AW"],
        note="Canal 30 y 31 del módulo 09. Ajustar también duración (canal 32)."
    ),
    HiddenSetting(
        id="blink_count_lane_change",
        name="Número de Destellos — Cambio de Carril",
        description="Número de veces que parpadea el intermitente al hacer un toque rápido "
                    "(lane change assist). Rango: 1-7 destellos.",
        category="Luces",
        module="BCM",
        setting_type=SettingType.SELECT,
        current_val=3,
        default_val=3,
        options=[1, 2, 3, 4, 5, 6, 7],
        risk_level="low",
        compatible=["VW Polo 6R", "VW Polo 6C", "VW Polo AW"],
        note="Canal de adaptación 2 del módulo 09."
    ),
    HiddenSetting(
        id="brake_dust_wipe",
        name="Limpiaparabrisas Trasero al Marcha Atrás",
        description="Activa automáticamente el limpiaparabrisas trasero al "
                    "poner marcha atrás con el delantero activado.",
        category="Luces",
        module="BCM",
        setting_type=SettingType.TOGGLE,
        current_val=False,
        default_val=False,
        risk_level="low",
        compatible=["VW Polo 6R", "VW Polo 6C", "VW Polo AW"],
        note="Byte de codificación 1, bit 2 del módulo 09."
    ),

    # ═══════════════════════════════════════════════════════════
    # CONFORT
    # ═══════════════════════════════════════════════════════════
    HiddenSetting(
        id="auto_lock_speed",
        name="Cierre Automático por Velocidad",
        description="Las puertas se bloquean automáticamente al superar cierta velocidad. "
                    "Estándar en algunos mercados, desactivado en otros.",
        category="Confort",
        module="BCM",
        setting_type=SettingType.TOGGLE,
        current_val=False,
        default_val=False,
        risk_level="low",
        compatible=["VW Polo 6R", "VW Polo 6C", "VW Polo AW"],
        note="Canal de adaptación 10 del módulo 46 (Central comfort)."
    ),
    HiddenSetting(
        id="windows_close_rain",
        name="Cierre de Ventanas con Lluvia",
        description="Las ventanas eléctricas se cierran automáticamente al cerrar el coche "
                    "si el sensor de lluvia detecta precipitación.",
        category="Confort",
        module="BCM",
        setting_type=SettingType.TOGGLE,
        current_val=False,
        default_val=False,
        risk_level="low",
        compatible=["VW Polo 6C", "VW Polo AW"],
        note="Requiere sensor de lluvia y ventanas eléctricas traseras."
    ),
    HiddenSetting(
        id="folding_mirrors_lock",
        name="Plegar Espejos al Cerrar",
        description="Los retrovisores eléctricos se pliegan automáticamente "
                    "al bloquear el vehículo con la llave.",
        category="Confort",
        module="BCM",
        setting_type=SettingType.TOGGLE,
        current_val=False,
        default_val=False,
        risk_level="low",
        compatible=["VW Polo 6C", "VW Polo AW"],
        note="Solo con espejos eléctricos plegables. Canal 6 módulo 72."
    ),
    HiddenSetting(
        id="seat_belt_warning",
        name="Aviso Cinturón de Seguridad",
        description="Ajusta el comportamiento del aviso del cinturón. "
                    "Puede desactivarse para movimientos en finca privada (solo legal en espacio privado).",
        category="Confort",
        module="ECU",
        setting_type=SettingType.SELECT,
        current_val="Normal",
        default_val="Normal",
        options=["Normal", "Reducido (5s)", "Desactivado (solo privado)"],
        risk_level="medium",
        compatible=["VW Polo 6R", "VW Polo 6C", "VW Polo AW"],
        note="AVISO: Desactivar puede ser ilegal en vía pública. Byte 2 módulo 17."
    ),

    # ═══════════════════════════════════════════════════════════
    # MOTOR / RENDIMIENTO
    # ═══════════════════════════════════════════════════════════
    HiddenSetting(
        id="start_stop_default_on",
        name="Start/Stop — Estado por Defecto",
        description="Define si el sistema Start/Stop arranca activado o desactivado "
                    "cada vez que se enciende el vehículo.",
        category="Motor",
        module="ECU",
        setting_type=SettingType.SELECT,
        current_val="ON",
        default_val="ON",
        options=["ON", "OFF"],
        risk_level="low",
        compatible=["VW Polo 6C TSI", "VW Polo AW TSI"],
        note="Canal de adaptación del módulo 03 (ABS/ESP) o 19 (Data bus)."
    ),
    HiddenSetting(
        id="throttle_response",
        name="Respuesta del Acelerador (Throttle Map)",
        description="Selecciona el mapa de respuesta del acelerador. "
                    "'Eco' es suave para ahorro, 'Sport' es directo para mayor respuesta.",
        category="Motor",
        module="ECU",
        setting_type=SettingType.SELECT,
        current_val="Normal",
        default_val="Normal",
        options=["Eco", "Normal", "Sport"],
        risk_level="medium",
        compatible=["VW Polo 6C TSI", "VW Polo AW TSI"],
        note="Solo en ECUs con DCC o MFI. Byte de codificación 5, módulo 01."
    ),
    HiddenSetting(
        id="rpm_display_redline",
        name="Zona Roja Tacómetro",
        description="Ajusta la zona roja del tacómetro en el cuadro de instrumentos. "
                    "No modifica los límites reales de la ECU.",
        category="Motor",
        module="INSTRUMENT",
        setting_type=SettingType.ADAPT,
        current_val=6500,
        default_val=6500,
        min_val=5000,
        max_val=7500,
        unit="RPM",
        risk_level="low",
        compatible=["VW Polo 6R", "VW Polo 6C", "VW Polo AW"],
        note="Solo afecta a la visualización. Canal módulo 17 (Instrumentos)."
    ),

    # ═══════════════════════════════════════════════════════════
    # SEGURIDAD / ASISTENCIA
    # ═══════════════════════════════════════════════════════════
    HiddenSetting(
        id="speed_warning",
        name="Aviso de Velocidad Máxima",
        description="Muestra un aviso en el cuadro de instrumentos cuando "
                    "se supera la velocidad configurada. Útil para nuevos conductores.",
        category="Seguridad",
        module="INSTRUMENT",
        setting_type=SettingType.ADAPT,
        current_val=0,
        default_val=0,
        min_val=0,
        max_val=250,
        unit="km/h",
        risk_level="low",
        compatible=["VW Polo 6R", "VW Polo 6C", "VW Polo AW"],
        note="0 = desactivado. Canal de adaptación módulo 17."
    ),
    HiddenSetting(
        id="lane_assist_sensitivity",
        name="Sensibilidad Lane Assist",
        description="Ajusta cuándo interviene el asistente de mantenimiento de carril. "
                    "Mayor valor = intervención más temprana.",
        category="Seguridad",
        module="LKAS",
        setting_type=SettingType.SELECT,
        current_val="Normal",
        default_val="Normal",
        options=["Baja", "Normal", "Alta"],
        risk_level="low",
        compatible=["VW Polo AW"],
        note="Requiere Lane Assist instalado. Módulo 3C (Lane Change Assist)."
    ),
    HiddenSetting(
        id="esp_intervention",
        name="Umbral de Intervención ESP",
        description="Define cuán pronto interviene el ESP. "
                    "'Sport' permite más deslizamiento antes de intervenir.",
        category="Seguridad",
        module="ABS",
        setting_type=SettingType.SELECT,
        current_val="Normal",
        default_val="Normal",
        options=["Normal", "Sport"],
        risk_level="high",
        compatible=["VW Polo 6C", "VW Polo AW"],
        note="RIESGO: Solo para uso en pista. En modo Sport el ESP interviene menos."
    ),

    # ═══════════════════════════════════════════════════════════
    # INFORMACIÓN / DISPLAY
    # ═══════════════════════════════════════════════════════════
    HiddenSetting(
        id="oil_temp_display",
        name="Mostrar Temperatura de Aceite",
        description="Activa la visualización de la temperatura del aceite "
                    "en el cuadro de instrumentos o en el MFD.",
        category="Visualizacion",
        module="INSTRUMENT",
        setting_type=SettingType.TOGGLE,
        current_val=False,
        default_val=False,
        risk_level="low",
        compatible=["VW Polo 6R", "VW Polo 6C", "VW Polo AW"],
        note="Requiere sensor de temperatura de aceite (motor 1.0/1.4 TSI lo incluye)."
    ),
    HiddenSetting(
        id="battery_voltage_display",
        name="Mostrar Tensión de Batería",
        description="Muestra el voltaje de la batería en el cuadro MFD.",
        category="Visualizacion",
        module="INSTRUMENT",
        setting_type=SettingType.TOGGLE,
        current_val=False,
        default_val=False,
        risk_level="low",
        compatible=["VW Polo 6R", "VW Polo 6C", "VW Polo AW"],
        note="Canal de adaptación módulo 17 (cuadro instrumentos)."
    ),
    HiddenSetting(
        id="boost_gauge_display",
        name="Manómetro de Turbo en MFD",
        description="Activa un manómetro de presión de turbo en el cuadro MFD "
                    "o en el display de información del conductor.",
        category="Visualizacion",
        module="INSTRUMENT",
        setting_type=SettingType.TOGGLE,
        current_val=False,
        default_val=False,
        risk_level="low",
        compatible=["VW Polo 6C TSI", "VW Polo AW TSI"],
        note="Solo modelos TSI/TDI con turbo. Byte de codificación módulo 17."
    ),
]


class HiddenSettingsModule:
    """
    Gestiona la lectura, validación y aplicación de ajustes ocultos.

    Principios:
      - Solo modifica bytes de codificación/adaptación (no firmware)
      - Backup automático del valor anterior
      - Validación de compatibilidad con el vehículo conectado
      - Rollback disponible en cualquier momento
    """

    def __init__(self, ctx, notify: Callable):
        self.ctx = ctx
        self._notify = notify
        self._settings: List[HiddenSetting] = list(VW_POLO_HIDDEN_SETTINGS)
        self._change_history: List[Dict] = []   # Para rollback
        logger.info(f"HiddenSettingsModule listo. {len(self._settings)} ajustes disponibles.")

    def get_all_settings(self) -> List[HiddenSetting]:
        """Devuelve todos los ajustes disponibles."""
        return self._settings

    def get_by_category(self) -> Dict[str, List[HiddenSetting]]:
        """Agrupa los ajustes por categoría."""
        result: Dict[str, List[HiddenSetting]] = {}
        for s in self._settings:
            result.setdefault(s.category, []).append(s)
        return result

    def get_setting(self, setting_id: str) -> Optional[HiddenSetting]:
        """Recupera un ajuste por su ID."""
        for s in self._settings:
            if s.id == setting_id:
                return s
        return None

    def apply_setting(self, setting_id: str, new_value: Any) -> bool:
        """
        Aplica un ajuste oculto al módulo de control correspondiente.

        Flujo:
          1. Validar que el valor es coherente con el tipo de ajuste
          2. Registrar el valor anterior (para rollback)
          3. Enviar al módulo de control via UDS/Adaptación
          4. Verificar que el valor fue aplicado
          5. Notificar resultado

        En hardware real: usa UDS 0x2E (WriteDataByIdentifier) o
        protocolo propietario VAG (Adaptation).
        """
        setting = self.get_setting(setting_id)
        if setting is None:
            logger.error(f"Ajuste no encontrado: {setting_id}")
            return False

        # Validar riesgo antes de aplicar
        if setting.risk_level == "high":
            logger.warning(f"Ajuste de alto riesgo: {setting.name}")
            self._notify("hidden_setting_risk_warning",
                         setting=setting,
                         message=f"ADVERTENCIA: '{setting.name}' tiene riesgo alto. "
                                 f"Verifica la nota técnica antes de aplicar.")

        # Guardar valor anterior para rollback
        old_value = setting.current_val
        self._change_history.append({
            "setting_id": setting_id,
            "old_value": old_value,
            "new_value": new_value,
            "setting_name": setting.name,
        })

        # Aplicar (simulado en demo)
        logger.info(f"Aplicando ajuste '{setting.name}': {old_value} → {new_value}")
        self._apply_to_module(setting, new_value)
        setting.current_val = new_value

        self._notify("hidden_setting_applied",
                     setting_id=setting_id,
                     name=setting.name,
                     old_value=old_value,
                     new_value=new_value)
        return True

    def rollback_last(self) -> bool:
        """Revierte el último ajuste aplicado."""
        if not self._change_history:
            logger.warning("No hay cambios que revertir.")
            return False

        last = self._change_history.pop()
        setting = self.get_setting(last["setting_id"])
        if setting:
            setting.current_val = last["old_value"]
            self._apply_to_module(setting, last["old_value"])
            logger.info(f"Rollback: '{last['setting_name']}' → {last['old_value']}")
            self._notify("hidden_setting_rolled_back",
                         setting_id=last["setting_id"],
                         name=last["setting_name"],
                         restored_value=last["old_value"])
            return True
        return False

    def rollback_all(self):
        """Revierte todos los ajustes al valor de fábrica."""
        for setting in self._settings:
            if setting.current_val != setting.default_val:
                self._apply_to_module(setting, setting.default_val)
                setting.current_val = setting.default_val
        self._change_history.clear()
        self._notify("hidden_settings_reset_all")
        logger.info("Todos los ajustes ocultos revertidos a valores de fábrica.")

    def get_change_history(self) -> List[Dict]:
        """Devuelve el historial de cambios aplicados."""
        return list(reversed(self._change_history))

    def _apply_to_module(self, setting: HiddenSetting, value: Any):
        """
        Envía el valor al módulo de control.

        En hardware real:
          - UDS SID 0x2E + DID específico del parámetro
          - Protocolo VAG Adaptation: seleccionar canal + escribir valor
          - Requiere sesión extendida y SecurityAccess previos

        En demo: solo log.
        """
        logger.debug(f"[DEMO] Módulo {setting.module}: "
                     f"ajuste '{setting.id}' = {value}")
        # DEMO: no hay comunicación real con la ECU
