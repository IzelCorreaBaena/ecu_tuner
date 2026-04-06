"""
ui/main_window.py
=================
Ventana principal de la aplicación.
Orquesta todos los paneles y la barra de estado.

LAYOUT:
  ┌─────────────────────────────────────────────────────┐
  │  HEADER: Logo + nombre + indicador de estado        │
  ├──────────────┬──────────────────────────────────────┤
  │  SIDEBAR     │  CONTENT AREA (tabs)                 │
  │  - Conexión  │  ┌──────┬─────────┬────────┬──────┐ │
  │  - Backup    │  │Conn. │ Backup  │ Tuning │Flash │ │
  │  - Tuning    │  └──────┴─────────┴────────┴──────┘ │
  │  - Flash     │  [Panel activo]                      │
  │  - Live Data │                                      │
  ├──────────────┴──────────────────────────────────────┤
  │  STATUS BAR: Estado + progreso + log rápido         │
  └─────────────────────────────────────────────────────┘
"""

import customtkinter as ctk
from ui.panels.vcds_panel import VCDSPanel
from ui.panels.diagnostic_panel import DiagnosticPanel
from core.app_controller import AppController, AppState
from ui.panels.connection_panel import ConnectionPanel
from ui.panels.backup_panel import BackupPanel
from ui.panels.tuning_panel import TuningPanel
from ui.panels.flash_panel import FlashPanel
from ui.panels.logs_panel import LogsPanel
import logging

logger = logging.getLogger("ECUTuner.MainWindow")

# ─── Tema visual ────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

# Paleta de colores personalizada "ECU Diagnostic"
COLORS = {
    "bg_dark":     "#0D1117",   # Fondo principal (GitHub dark)
    "bg_panel":    "#161B22",   # Fondo de paneles
    "bg_widget":   "#21262D",   # Fondo de widgets
    "accent":      "#F78166",   # Rojo-naranja (alertas, acción principal)
    "accent_blue": "#58A6FF",   # Azul (info, conexión activa)
    "accent_green":"#3FB950",   # Verde (éxito, conectado)
    "accent_yellow":"#E3B341",  # Amarillo (advertencia)
    "text_primary":"#F0F6FC",   # Texto principal
    "text_muted":  "#8B949E",   # Texto secundario
    "border":      "#30363D",   # Bordes
}


class MainWindow(ctk.CTk):
    """
    Ventana principal. Hereda de CTk (CustomTkinter root window).

    Gestiona:
      - Layout global de la UI
      - Navegación entre paneles
      - Suscripción a eventos del AppController
      - Barra de estado global
    """

    def __init__(self, controller: AppController):
        super().__init__()
        self.controller = controller

        # ── Configuración de ventana ────────────────────────────────
        self.title("ECU Tuner — Gestor Didáctico de ECU v1.0")
        self.geometry("1280x800")
        self.minsize(1024, 680)
        self.configure(fg_color=COLORS["bg_dark"])

        # ── Construir UI ────────────────────────────────────────────
        self._build_header()
        self._build_main_layout()
        self._build_status_bar()

        # ── Suscribir eventos del controlador ──────────────────────
        self._subscribe_events()

        # ── Mostrar panel inicial ───────────────────────────────────
        self._show_panel("connection")
        logger.info("MainWindow lista.")

    # ─── Construcción de UI ─────────────────────────────────────────

    def _build_header(self):
        """Header superior con logo y estado de conexión."""
        header = ctk.CTkFrame(self, fg_color=COLORS["bg_panel"],
                               corner_radius=0, height=60)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        # Logo / título
        title_frame = ctk.CTkFrame(header, fg_color="transparent")
        title_frame.pack(side="left", padx=20, pady=8)

        ctk.CTkLabel(
            title_frame,
            text="⚙ ECU TUNER",
            font=ctk.CTkFont(family="Courier New", size=20, weight="bold"),
            text_color=COLORS["accent"]
        ).pack(side="left")

        ctk.CTkLabel(
            title_frame,
            text=" — Gestor Didáctico de Centralitas",
            font=ctk.CTkFont(size=13),
            text_color=COLORS["text_muted"]
        ).pack(side="left")

        # Indicador de estado (derecha)
        self._state_indicator = ctk.CTkLabel(
            header,
            text="● DESCONECTADO",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLORS["text_muted"]
        )
        self._state_indicator.pack(side="right", padx=20)

    def _build_main_layout(self):
        """Layout principal: sidebar izquierda + área de contenido."""
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=0, pady=0)

        # ── Sidebar ──────────────────────────────────────────────
        sidebar = ctk.CTkFrame(main_frame, fg_color=COLORS["bg_panel"],
                                corner_radius=0, width=200)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        ctk.CTkLabel(
            sidebar,
            text="MÓDULOS",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=COLORS["text_muted"]
        ).pack(pady=(20, 8), padx=16, anchor="w")

        self._nav_buttons = {}
        nav_items = [
            ("connection", "🔌 Conexion",    "Detectar puerto y conectar"),
            ("backup",     "💾 Backup",       "Volcar memoria flash ECU"),
            ("tuning",     "⚡ Tuning",       "Editar mapas del motor"),
            ("flash",      "🔥 Flashear",     "Escribir a la ECU"),
            ("diagnostic", "🩺 Diagnostico",  "Leer/limpiar DTCs"),
            ("vcds",       "🔧 Aj. Ocultos",  "Coding y Adaptacion VCDS"),
            ("logs",       "📋 Logs",         "Monitor de eventos"),
        ]

        for panel_id, label, tooltip in nav_items:
            btn = ctk.CTkButton(
                sidebar,
                text=label,
                anchor="w",
                font=ctk.CTkFont(size=13),
                fg_color="transparent",
                hover_color=COLORS["bg_widget"],
                text_color=COLORS["text_primary"],
                corner_radius=6,
                command=lambda p=panel_id: self._show_panel(p)
            )
            btn.pack(fill="x", padx=10, pady=2)
            self._nav_buttons[panel_id] = btn

        # Live data mini-panel en sidebar
        self._build_live_data_sidebar(sidebar)

        # ── Área de contenido ─────────────────────────────────────
        self._content_area = ctk.CTkFrame(main_frame, fg_color=COLORS["bg_dark"],
                                           corner_radius=0)
        self._content_area.pack(side="left", fill="both", expand=True)

        # Instanciar los paneles (todos al mismo grid, solo uno visible)
        self._panels = {
            "connection": ConnectionPanel(self._content_area, self.controller, COLORS),
            "backup":     BackupPanel(self._content_area, self.controller, COLORS),
            "tuning":     TuningPanel(self._content_area, self.controller, COLORS),
            "flash":      FlashPanel(self._content_area, self.controller, COLORS),
            "diagnostic": DiagnosticPanel(self._content_area, self.controller, COLORS),
            "vcds":       VCDSPanel(self._content_area, self.controller, COLORS),
            "logs":       LogsPanel(self._content_area, self.controller, COLORS),
        }

        for panel in self._panels.values():
            panel.place(relx=0, rely=0, relwidth=1, relheight=1)

    def _build_live_data_sidebar(self, parent):
        """Mini panel de datos en tiempo real en la sidebar."""
        ctk.CTkLabel(
            parent,
            text="LIVE DATA",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=COLORS["text_muted"]
        ).pack(pady=(30, 8), padx=16, anchor="w")

        live_frame = ctk.CTkFrame(parent, fg_color=COLORS["bg_widget"], corner_radius=8)
        live_frame.pack(fill="x", padx=10)

        self._live_labels = {}
        live_items = [
            ("rpm",          "RPM",       "0"),
            ("coolant_temp", "Refriger.", "—°C"),
            ("boost_kpa",    "Boost",     "—mbar"),
            ("battery_v",    "Batería",   "—V"),
        ]

        for key, label, default in live_items:
            row = ctk.CTkFrame(live_frame, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=3)

            ctk.CTkLabel(row, text=label, font=ctk.CTkFont(size=10),
                          text_color=COLORS["text_muted"]).pack(side="left")

            val_label = ctk.CTkLabel(row, text=default,
                                      font=ctk.CTkFont(size=10, weight="bold"),
                                      text_color=COLORS["accent_blue"])
            val_label.pack(side="right")
            self._live_labels[key] = val_label

    def _build_status_bar(self):
        """Barra de estado inferior."""
        status_bar = ctk.CTkFrame(self, fg_color=COLORS["bg_panel"],
                                   corner_radius=0, height=28)
        status_bar.pack(fill="x", side="bottom")
        status_bar.pack_propagate(False)

        self._status_label = ctk.CTkLabel(
            status_bar,
            text="Listo. Conecte el adaptador OBD-II para comenzar.",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text_muted"]
        )
        self._status_label.pack(side="left", padx=12, pady=4)

        self._progress_bar = ctk.CTkProgressBar(status_bar, width=150, height=8)
        self._progress_bar.pack(side="right", padx=12, pady=10)
        self._progress_bar.set(0)

    # ─── Navegación ─────────────────────────────────────────────────

    def _show_panel(self, panel_id: str):
        """Muestra el panel seleccionado y oculta los demás."""
        for pid, panel in self._panels.items():
            if pid == panel_id:
                panel.lift()
            else:
                panel.lower()

        # Actualizar estilo de botón activo
        for pid, btn in self._nav_buttons.items():
            if pid == panel_id:
                btn.configure(fg_color=COLORS["bg_widget"],
                              text_color=COLORS["accent_blue"])
            else:
                btn.configure(fg_color="transparent",
                              text_color=COLORS["text_primary"])

    # ─── Suscripción a eventos ───────────────────────────────────────

    def _subscribe_events(self):
        """Suscribe callbacks a los eventos del controlador."""
        self.controller.on("connected",             self._on_connected)
        self.controller.on("connection_error",      self._on_connection_error)
        self.controller.on("state_changed",         self._on_state_changed)
        self.controller.on("live_data_update",      self._on_live_data)
        self.controller.on("backup_progress",       self._on_progress)
        self.controller.on("flash_progress",        self._on_progress)
        self.controller.on("backup_complete",       self._on_backup_complete)
        self.controller.on("flash_complete",        self._on_flash_complete)
        self.controller.on("dtc_update",            self._on_dtc_update)

    def _on_connected(self, ecu_info: dict):
        self.after(0, lambda: self._state_indicator.configure(
            text=f"● {ecu_info.get('ecu_type', 'CONECTADO')}",
            text_color=COLORS["accent_green"]
        ))
        self.after(0, lambda: self._update_status(
            f"✓ Conectado: {ecu_info.get('ecu_type')} | VIN: {ecu_info.get('vin', '—')}"
        ))

    def _on_connection_error(self, error: str):
        self.after(0, lambda: self._state_indicator.configure(
            text="● ERROR", text_color=COLORS["accent"]
        ))
        self.after(0, lambda: self._update_status(f"✗ Error de conexión: {error}"))

    def _on_state_changed(self, state: AppState):
        state_colors = {
            AppState.DISCONNECTED:   COLORS["text_muted"],
            AppState.CONNECTED:      COLORS["accent_green"],
            AppState.READING_BACKUP: COLORS["accent_yellow"],
            AppState.FLASHING:       COLORS["accent"],
            AppState.ERROR:          COLORS["accent"],
        }
        color = state_colors.get(state, COLORS["text_muted"])
        self.after(0, lambda: self._state_indicator.configure(
            text=f"● {state.name}", text_color=color
        ))

    def _on_live_data(self, data: dict):
        """Actualiza los labels de live data en la sidebar."""
        units = {"rpm": " RPM", "coolant_temp": "°C",
                 "boost_kpa": " kPa", "battery_v": "V"}
        for key, label in self._live_labels.items():
            if key in data:
                val = data[key]
                unit = units.get(key, "")
                self.after(0, lambda l=label, v=val, u=unit:
                           l.configure(text=f"{v}{u}"))

    def _on_dtc_update(self, dtcs=None, **kwargs):
        panel = self._panels.get("diagnostic")
        if panel and hasattr(panel, "update_dtcs"):
            panel.update_dtcs(dtcs or [])

    def _on_progress(self, step: str = "", pct: float = 0, **kwargs):
        self.after(0, lambda: self._update_status(step))
        self.after(0, lambda: self._progress_bar.set(pct / 100))

    def _on_backup_complete(self, path: str, size_kb: int):
        self.after(0, lambda: self._update_status(
            f"✓ Backup completado: {path} ({size_kb} KB)"
        ))
        self.after(0, lambda: self._progress_bar.set(1.0))

    def _on_flash_complete(self, size_kb: int, checksum: str):
        self.after(0, lambda: self._update_status(
            f"✓ Flash completado ({size_kb} KB) | Checksum: {checksum}"
        ))
        self.after(0, lambda: self._progress_bar.set(1.0))

    def _update_status(self, text: str):
        self._status_label.configure(text=text)
