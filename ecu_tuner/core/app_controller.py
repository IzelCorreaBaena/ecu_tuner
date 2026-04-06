"""
core/app_controller.py
======================
Controlador Central de la Aplicación (MVC Controller layer).

Responsabilidades:
  - Instanciar y coordinar todos los módulos
  - Gestionar el estado global de la aplicación
  - Proveer la API unificada que consume la UI
  - Emitir eventos/callbacks hacia la View

No tiene dependencias de UI → es testeable de forma aislada.
"""

import logging
from typing import Optional, Callable
from dataclasses import dataclass, field
from enum import Enum, auto

from modules.connection_module import ConnectionModule
from modules.diagnostic_module import DiagnosticModule
from modules.vcds_config import load_profiles, apply_profile
from modules.backup_module import BackupModule
from modules.tuning_module import TuningModule
from modules.flash_module import FlashModule
from modules.hidden_settings_module import HiddenSettingsModule

logger = logging.getLogger("ECUTuner.AppController")


# ─── Estado global de la aplicación ───────────────────────────────────────
class AppState(Enum):
    """
    Máquina de estados que controla qué operaciones están permitidas.
    Evita condiciones de carrera (ej: no se puede flashear si no hay conexión).
    """
    DISCONNECTED    = auto()   # Sin conexión activa
    CONNECTING      = auto()   # Proceso de conexión en curso
    CONNECTED       = auto()   # Conectado, listo para leer
    READING_BACKUP  = auto()   # Volcado de memoria en progreso
    BACKUP_DONE     = auto()   # Backup disponible, listo para editar
    EDITING         = auto()   # Usuario modificando el mapa
    VALIDATING      = auto()   # Validando checksum antes de flashear
    FLASHING        = auto()   # Escritura a ECU en progreso
    ERROR           = auto()   # Estado de error recuperable


@dataclass
class AppContext:
    """
    Contexto compartido entre módulos.
    Actúa como 'session store' de la aplicación.
    """
    state: AppState = AppState.DISCONNECTED
    connected_port: Optional[str] = None
    ecu_info: dict = field(default_factory=dict)
    backup_path: Optional[str] = None
    binary_data: Optional[bytes] = None
    modified_data: Optional[bytes] = None
    flash_progress: float = 0.0
    last_error: Optional[str] = None


class AppController:
    """
    Orquestador principal. La UI solo habla con esta clase.

    Patrón: Facade + Mediator
      - Facade:   expone API simplificada hacia la UI
      - Mediator: coordina comunicación entre módulos sin acoplamientos directos
    """

    def __init__(self):
        self.ctx = AppContext()
        self._callbacks: dict[str, list[Callable]] = {}
        self._vcds_profiles: list[dict] = []

        # ── Instanciar módulos pasando el contexto compartido ──
        self.connection      = ConnectionModule(ctx=self.ctx, notify=self._notify)
        self.backup          = BackupModule(ctx=self.ctx, notify=self._notify)
        self.tuning          = TuningModule(ctx=self.ctx, notify=self._notify)
        self.flash           = FlashModule(ctx=self.ctx, notify=self._notify)
        self.diagnostic      = DiagnosticModule(ctx=self.ctx, notify=self._notify)
        self.hidden_settings = HiddenSettingsModule(ctx=self.ctx, notify=self._notify)

        logger.info("AppController inicializado. Estado: DISCONNECTED")

    # ─────────────────────────────────────────────────────────────────────
    # SISTEMA DE EVENTOS (Observable pattern simplificado)
    # La UI suscribe callbacks; los módulos los disparan via self._notify()
    # ─────────────────────────────────────────────────────────────────────

    def on(self, event: str, callback: Callable):
        """Suscribir un callback a un evento."""
        self._callbacks.setdefault(event, []).append(callback)

    def _notify(self, event: str, **kwargs):
        """Disparar un evento a todos los listeners suscritos."""
        logger.debug(f"Evento: '{event}' → {kwargs}")
        for cb in self._callbacks.get(event, []):
            cb(**kwargs)

    # ─────────────────────────────────────────────────────────────────────
    # API PÚBLICA → llamada desde la UI
    # ─────────────────────────────────────────────────────────────────────

    def get_state(self) -> AppState:
        return self.ctx.state

    def get_available_ports(self) -> list[str]:
        """Devuelve lista de puertos seriales detectados en el sistema."""
        return self.connection.scan_ports()

    def connect(self, port: str, baudrate: int, protocol: str):
        """Inicia la secuencia de conexión OBD-II."""
        if self.ctx.state not in (AppState.DISCONNECTED, AppState.ERROR):
            logger.warning("Intento de conexión en estado inválido.")
            return
        self.ctx.state = AppState.CONNECTING
        self.connection.connect(port, baudrate, protocol)

    def disconnect(self):
        """Cierra la conexión activa."""
        self.connection.disconnect()
        self.ctx.state = AppState.DISCONNECTED
        self._notify("state_changed", state=AppState.DISCONNECTED)

    def start_backup(self, output_path: str):
        """Inicia el volcado de la memoria flash de la ECU."""
        if self.ctx.state != AppState.CONNECTED:
            logger.warning("Se requiere conexión activa para hacer backup.")
            return
        self.ctx.state = AppState.READING_BACKUP
        self.backup.start_dump(output_path)

    def load_binary(self, file_path: str):
        """Carga un archivo .bin existente para edición (sin conexión)."""
        self.tuning.load_file(file_path)
        self.ctx.state = AppState.EDITING
        self._notify("state_changed", state=AppState.EDITING)

    def read_dtcs(self):
        """Lee códigos DTC desde el módulo de diagnóstico (simulado)."""
        if hasattr(self, 'diagnostic'):
            return self.diagnostic.read_dtcs()
        return []

    def clear_dtcs(self):
        if hasattr(self, 'diagnostic'):
            self.diagnostic.clear_dtcs()

    def load_vcds_profiles(self, profiles_path: str):
        """Carga perfiles VCDS desde un JSON y almacena en el contexto."""
        self._vcds_profiles = load_profiles(profiles_path)
        self._notify("vcds_profiles_loaded", profiles=self._vcds_profiles)

    def apply_vcds_profile_by_name(self, name: str) -> bool:
        """Aplica un perfil VCDS conocido por nombre a los mapas activos."""
        for prof in self._vcds_profiles:
            if prof.get("name") == name:
                try:
                    apply_profile(self, prof)
                    self._notify("vcds_profile_applied", profile=name)
                    return True
                except Exception as e:
                    self._notify("vcds_profile_error", error=str(e))
                    return False
        return False

    def get_map(self, map_id: str) -> dict:
        """Recupera una tabla de mapa para mostrarla en la UI."""
        return self.tuning.get_map(map_id)

    def update_map_cell(self, map_id: str, row: int, col: int, value: float):
        """Actualiza una celda en un mapa de motor."""
        self.tuning.update_cell(map_id, row, col, value)

    def start_flash(self, validated_path: str):
        """Inicia el proceso de escritura a la ECU."""
        if self.ctx.state not in (AppState.EDITING, AppState.BACKUP_DONE):
            logger.warning("Estado inválido para flashear.")
            return
        self.ctx.state = AppState.VALIDATING
        self.flash.start_flash(validated_path)
