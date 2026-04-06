"""
ui/panels/connection_panel.py
=============================
Panel GUI del Módulo de Conexión.
Permite al usuario seleccionar puerto, baudios y protocolo,
y ver el estado de la conexión en tiempo real.
"""

import customtkinter as ctk
from core.app_controller import AppController


class ConnectionPanel(ctk.CTkFrame):
    """Panel de conexión OBD-II."""

    def __init__(self, parent, controller: AppController, colors: dict):
        super().__init__(parent, fg_color=colors["bg_dark"], corner_radius=0)
        self.controller = controller
        self.C = colors
        self._build_ui()

    def _build_ui(self):
        # ── Título de sección ────────────────────────────────────
        ctk.CTkLabel(
            self,
            text="🔌 Módulo de Conexión OBD-II",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=self.C["text_primary"]
        ).pack(anchor="w", padx=30, pady=(24, 4))

        ctk.CTkLabel(
            self,
            text="Detecta el adaptador ELM327 o J2534, selecciona el protocolo y establece la comunicación con el bus CAN del vehículo.",
            font=ctk.CTkFont(size=12),
            text_color=self.C["text_muted"],
            wraplength=700
        ).pack(anchor="w", padx=30, pady=(0, 20))

        # ── Zona de configuración ─────────────────────────────────
        config_frame = ctk.CTkFrame(self, fg_color=self.C["bg_panel"], corner_radius=10)
        config_frame.pack(fill="x", padx=30, pady=10)

        # Título config
        ctk.CTkLabel(
            config_frame,
            text="Configuración de Conexión",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.C["text_primary"]
        ).pack(anchor="w", padx=20, pady=(16, 12))

        # Grid de controles
        grid = ctk.CTkFrame(config_frame, fg_color="transparent")
        grid.pack(fill="x", padx=20, pady=(0, 20))

        # Puerto serial
        ctk.CTkLabel(grid, text="Puerto Serial / USB:",
                      text_color=self.C["text_muted"]).grid(row=0, column=0, sticky="w", pady=6)
        self._port_var = ctk.StringVar(value="Seleccionar...")
        self._port_combo = ctk.CTkComboBox(
            grid, variable=self._port_var, width=280,
            values=["Escaneando..."],
            command=lambda v: None
        )
        self._port_combo.grid(row=0, column=1, padx=(12, 0), pady=6, sticky="w")

        scan_btn = ctk.CTkButton(
            grid, text="🔍 Escanear",
            width=100, height=28,
            fg_color=self.C["bg_widget"],
            hover_color=self.C["accent_blue"],
            command=self._scan_ports
        )
        scan_btn.grid(row=0, column=2, padx=8, pady=6)

        # Baudrate
        ctk.CTkLabel(grid, text="Velocidad (baudios):",
                     text_color=self.C["text_muted"]).grid(row=1, column=0, sticky="w", pady=6)
        self._baud_var = ctk.StringVar(value="38400")
        ctk.CTkComboBox(
            grid, variable=self._baud_var, width=280,
            values=["9600", "38400", "115200", "500000 (CAN directo)"]
        ).grid(row=1, column=1, padx=(12, 0), pady=6, sticky="w")

        # Protocolo
        ctk.CTkLabel(grid, text="Protocolo OBD-II:",
                     text_color=self.C["text_muted"]).grid(row=2, column=0, sticky="w", pady=6)
        self._protocol_var = ctk.StringVar(value="6 - ISO 15765-4 CAN (500kbps)")
        ctk.CTkComboBox(
            grid, variable=self._protocol_var, width=280,
            values=[
                "0 - Auto-detección",
                "3 - ISO 9141-2 (Europa)",
                "4 - ISO 14230 KWP2000",
                "6 - ISO 15765-4 CAN (500kbps)",
                "8 - ISO 15765-4 CAN (250kbps)",
            ]
        ).grid(row=2, column=1, padx=(12, 0), pady=6, sticky="w")

        # Botón principal de conexión
        btn_frame = ctk.CTkFrame(config_frame, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(0, 20))

        self._connect_btn = ctk.CTkButton(
            btn_frame,
            text="⚡ CONECTAR",
            font=ctk.CTkFont(size=14, weight="bold"),
            width=180, height=44,
            fg_color=self.C["accent_green"],
            hover_color="#2E8B40",
            command=self._on_connect
        )
        self._connect_btn.pack(side="left")

        ctk.CTkButton(
            btn_frame,
            text="Desconectar",
            width=120, height=44,
            fg_color=self.C["bg_widget"],
            hover_color=self.C["accent"],
            command=self.controller.disconnect
        ).pack(side="left", padx=12)

        # ── Barra de progreso de conexión ─────────────────────────
        self._progress = ctk.CTkProgressBar(self, height=6)
        self._progress.pack(fill="x", padx=30, pady=(10, 0))
        self._progress.set(0)

        self._progress_label = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont(size=11),
            text_color=self.C["text_muted"]
        )
        self._progress_label.pack(anchor="w", padx=30, pady=(4, 0))

        # ── Info ECU (post-conexión) ───────────────────────────────
        self._ecu_frame = ctk.CTkFrame(self, fg_color=self.C["bg_panel"], corner_radius=10)
        self._ecu_frame.pack(fill="x", padx=30, pady=16)

        ctk.CTkLabel(
            self._ecu_frame,
            text="Información de la ECU",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.C["text_primary"]
        ).pack(anchor="w", padx=20, pady=(16, 8))

        self._ecu_info_text = ctk.CTkTextbox(
            self._ecu_frame, height=140,
            font=ctk.CTkFont(family="Courier New", size=11),
            fg_color=self.C["bg_widget"],
            text_color=self.C["accent_blue"]
        )
        self._ecu_info_text.pack(fill="x", padx=20, pady=(0, 16))
        self._ecu_info_text.insert("1.0", "→ Sin conexión. Escanee puertos y conecte el adaptador.")
        self._ecu_info_text.configure(state="disabled")

        # Suscribir eventos
        self.controller.on("connection_progress", self._on_progress)
        self.controller.on("connected", self._on_connected)

        # Escanear al inicio
        self._scan_ports()

    def _scan_ports(self):
        ports = self.controller.get_available_ports()
        self._port_combo.configure(values=ports if ports else ["No detectado"])
        if ports:
            self._port_var.set(ports[0])

    def _on_connect(self):
        port = self._port_var.get()
        baud_str = self._baud_var.get().split()[0]
        protocol = self._protocol_var.get().split()[0]
        self.controller.connect(port, int(baud_str), protocol)

    def _on_progress(self, step: str = "", pct: float = 0, **kwargs):
        self.after(0, lambda: self._progress.set(pct / 100))
        self.after(0, lambda: self._progress_label.configure(text=step))

    def _on_connected(self, ecu_info: dict):
        info_lines = [f"  {k:<24}: {v}" for k, v in ecu_info.items()]
        text = "ECU Identificada:\n" + "\n".join(info_lines)
        self.after(0, lambda: self._update_ecu_text(text))

    def _update_ecu_text(self, text: str):
        self._ecu_info_text.configure(state="normal")
        self._ecu_info_text.delete("1.0", "end")
        self._ecu_info_text.insert("1.0", text)
        self._ecu_info_text.configure(state="disabled")
