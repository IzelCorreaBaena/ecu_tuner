"""
ui/panels/diagnostic_panel.py
==============================
Panel de Diagnóstico OBD-II completo.

Layout:
  ┌───────────────────────────────────────────────────────────────┐
  │  HEADER: título + botones lectura/borrado + indicador MIL     │
  ├───────────────────────┬───────────────────────────────────────┤
  │  LISTA DE DTCs        │  DETALLE del DTC seleccionado         │
  │  (tarjetas con color  │  + Freeze Frame + Monitors ITV        │
  │   por severidad)      │                                       │
  ├───────────────────────┴───────────────────────────────────────┤
  │  LIVE DATA: gauges numéricos en tiempo real                   │
  └───────────────────────────────────────────────────────────────┘
"""

import customtkinter as ctk
import logging

logger = logging.getLogger("ECUTuner.DiagnosticPanel")

SEVERITY_COLORS = {"high": "#F78166", "medium": "#E3B341", "low": "#58A6FF"}
SEVERITY_LABELS = {"high": "CRITICO", "medium": "MODERADO", "low": "INFO"}


class DiagnosticPanel(ctk.CTkFrame):
    """Panel de diagnóstico: DTCs, freeze frame, monitors readiness, live gauges."""

    def __init__(self, parent, controller=None, colors=None, **kwargs):
        # Soporte para dos firmas de constructor: (parent, controller, colors) y keyword
        if colors is None:
            colors = {}
        super().__init__(parent, fg_color=colors.get("bg_dark", "#0D1117"), corner_radius=0)
        self.controller = controller
        self.C = colors
        self._dtc_rows: list = []
        self._selected_dtc: dict = {}
        self._build_ui()

        if controller and hasattr(controller, "on"):
            controller.on("dtc_update",         self._on_dtc_update)
            controller.on("live_data_update",    self._on_live_update)
            controller.on("freeze_frame_update", self._on_freeze_update)
            controller.on("dtc_cleared",         self._on_dtc_cleared)

    # ─── Construcción de UI ─────────────────────────────────────────────

    def _c(self, key: str, default: str = "#888") -> str:
        return self.C.get(key, default)

    def _build_ui(self):
        self._build_header()
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=(0, 6))
        body.grid_columnconfigure(0, weight=2)
        body.grid_columnconfigure(1, weight=3)
        body.grid_rowconfigure(0, weight=1)
        self._build_dtc_list(body)
        self._build_detail_panel(body)
        self._build_live_gauges()

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color=self._c("bg_panel"), corner_radius=0)
        header.pack(fill="x")
        inner = ctk.CTkFrame(header, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(inner, text="Diagnostico OBD-II",
                     font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=self._c("text_primary")).pack(side="left")
        ctk.CTkLabel(inner, text=" — Leer, interpretar y borrar DTCs",
                     font=ctk.CTkFont(size=12),
                     text_color=self._c("text_muted")).pack(side="left")

        self._mil_label = ctk.CTkLabel(inner, text="  MIL: OFF",
                                       font=ctk.CTkFont(size=12, weight="bold"),
                                       text_color=self._c("text_muted"))
        self._mil_label.pack(side="right", padx=(0, 16))

        btn_frame = ctk.CTkFrame(inner, fg_color="transparent")
        btn_frame.pack(side="right")

        for label, cmd, fg, hover in [
            ("Leer DTCs",   self._read_dtcs,    self._c("accent_blue"), "#3A7FD5"),
            ("Pendientes",  self._read_pending, self._c("bg_widget"),   "#2A3240"),
            ("Borrar DTCs", self._clear_dtcs,   self._c("accent"),      "#C5533A"),
            ("Freeze Frame",self._read_freeze,  self._c("bg_widget"),   "#2A3240"),
        ]:
            ctk.CTkButton(btn_frame, text=label, width=105, height=30,
                          fg_color=fg, hover_color=hover,
                          font=ctk.CTkFont(size=12), command=cmd
                          ).pack(side="left", padx=(0, 5))

    def _build_dtc_list(self, parent):
        left = ctk.CTkFrame(parent, fg_color=self._c("bg_panel"), corner_radius=8)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=4)
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(left, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        self._dtc_count_label = ctk.CTkLabel(
            hdr, text="Sin datos",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=self._c("text_muted"))
        self._dtc_count_label.pack(side="left")

        self._dtc_scroll = ctk.CTkScrollableFrame(left, fg_color="transparent")
        self._dtc_scroll.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 8))
        self._dtc_scroll.grid_columnconfigure(0, weight=1)

        self._empty_label = ctk.CTkLabel(
            self._dtc_scroll,
            text="Presiona 'Leer DTCs'\npara escanear el vehiculo.",
            font=ctk.CTkFont(size=11), text_color=self._c("text_muted"), justify="center")
        self._empty_label.pack(pady=24)

    def _build_detail_panel(self, parent):
        right = ctk.CTkFrame(parent, fg_color=self._c("bg_panel"), corner_radius=8)
        right.grid(row=0, column=1, sticky="nsew", pady=4)
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(right, text="DETALLE DEL FALLO",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=self._c("text_muted")
                     ).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 6))

        self._detail_text = ctk.CTkTextbox(
            right, font=ctk.CTkFont(family="Courier New", size=11),
            fg_color=self._c("bg_widget"), text_color=self._c("text_primary"),
            wrap="word", state="disabled")
        self._detail_text.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))

        ctk.CTkLabel(right, text="MONITORS READINESS (ITV)",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=self._c("text_muted")
                     ).grid(row=2, column=0, sticky="w", padx=16, pady=(4, 4))

        self._readiness_frame = ctk.CTkFrame(right, fg_color=self._c("bg_widget"), corner_radius=6)
        self._readiness_frame.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 12))
        self._readiness_labels: dict = {}
        self._build_readiness_grid()

        self._update_detail_text(
            "Selecciona un DTC de la lista para\nver su descripcion detallada.\n\n"
            "Usa los botones superiores para:\n"
            "  Leer DTCs confirmados\n"
            "  Ver DTCs pendientes\n"
            "  Borrar todos los DTCs\n"
            "  Ver datos freeze frame"
        )

    def _build_readiness_grid(self):
        monitors = [
            "MIL (Luz Averia)", "Catalizador", "Sonda O2",
            "Sistema EVAP", "EGR / VVT", "Sensor O2",
            "Combustible", "Encendido", "Temperatura",
        ]
        for i, monitor in enumerate(monitors):
            row_f = ctk.CTkFrame(self._readiness_frame, fg_color="transparent")
            row_f.grid(row=i // 2, column=i % 2, sticky="ew", padx=8, pady=2)
            self._readiness_frame.grid_columnconfigure(0, weight=1)
            self._readiness_frame.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(row_f, text=monitor,
                         font=ctk.CTkFont(size=9),
                         text_color=self._c("text_muted")).pack(side="left")
            val = ctk.CTkLabel(row_f, text="—",
                               font=ctk.CTkFont(size=9, weight="bold"),
                               text_color=self._c("text_muted"))
            val.pack(side="right")
            self._readiness_labels[monitor] = val

    def _build_live_gauges(self):
        gauge_bar = ctk.CTkFrame(self, fg_color=self._c("bg_panel"), corner_radius=0, height=90)
        gauge_bar.pack(fill="x")
        gauge_bar.pack_propagate(False)

        ctk.CTkLabel(gauge_bar, text="DATOS EN TIEMPO REAL",
                     font=ctk.CTkFont(size=9, weight="bold"),
                     text_color=self._c("text_muted")
                     ).pack(anchor="w", padx=16, pady=(6, 0))

        gf = ctk.CTkFrame(gauge_bar, fg_color="transparent")
        gf.pack(fill="x", padx=8, pady=(2, 6))

        self._gauge_widgets: dict = {}
        gauge_defs = [
            ("rpm",          "RPM",      self._c("accent_blue")),
            ("coolant_temp", "Refrig.",  self._c("accent_green")),
            ("boost_kpa",    "Boost",    self._c("accent_yellow")),
            ("throttle_pos", "Mariposa", self._c("accent_blue")),
            ("engine_load",  "Carga",    self._c("text_muted")),
            ("battery_v",    "Bateria",  self._c("accent_green")),
            ("fuel_press",   "Combust.", self._c("accent_yellow")),
            ("oil_temp",     "Aceite",   self._c("text_muted")),
            ("vehicle_speed","Veloc.",   self._c("accent_blue")),
            ("timing_adv",   "Avance",   self._c("accent")),
        ]
        for key, label, color in gauge_defs:
            cell = ctk.CTkFrame(gf, fg_color=self._c("bg_widget"),
                                corner_radius=6, width=88, height=56)
            cell.pack(side="left", padx=4, pady=2)
            cell.pack_propagate(False)
            ctk.CTkLabel(cell, text=label, font=ctk.CTkFont(size=9),
                         text_color=self._c("text_muted")).pack(pady=(5, 0))
            val_lbl = ctk.CTkLabel(cell, text="—",
                                   font=ctk.CTkFont(size=13, weight="bold"),
                                   text_color=color)
            val_lbl.pack()
            self._gauge_widgets[key] = val_lbl

    # ─── Callbacks de botones ────────────────────────────────────────────

    def _read_dtcs(self):
        if self.controller and hasattr(self.controller, "read_dtcs"):
            self.controller.read_dtcs()

    def _read_pending(self):
        if self.controller and hasattr(self.controller, "diagnostic"):
            self.controller.diagnostic.read_pending_dtcs()

    def _clear_dtcs(self):
        if self.controller and hasattr(self.controller, "clear_dtcs"):
            self.controller.clear_dtcs()

    def _read_freeze(self):
        if self.controller and hasattr(self.controller, "diagnostic"):
            ff = self.controller.diagnostic.read_freeze_frame()
            if ff:
                self._on_freeze_update(data=ff)

    # ─── Callbacks de eventos ────────────────────────────────────────────

    def _on_dtc_update(self, dtcs=None, pending=None, mil=False, count=0, **kw):
        self.after(0, lambda: self._render_dtcs(dtcs or [], pending or [], mil, count))

    def _on_dtc_cleared(self, **kw):
        self.after(0, lambda: self._render_dtcs([], [], False, 0))

    def _on_live_update(self, data=None, **kw):
        if isinstance(data, dict):
            self.after(0, lambda d=data: self._update_gauges(d))

    def _on_freeze_update(self, data=None, **kw):
        if isinstance(data, dict) and data:
            self.after(0, lambda d=data: self._show_freeze_frame(d))

    # ─── Renderizado ─────────────────────────────────────────────────────

    def _render_dtcs(self, dtcs: list, pending: list, mil: bool, count: int):
        for row in self._dtc_rows:
            row.destroy()
        self._dtc_rows.clear()
        self._empty_label.pack_forget()

        self._mil_label.configure(
            text="  MIL: ON" if mil else "  MIL: OFF",
            text_color=self._c("accent") if mil else self._c("accent_green")
        )

        all_dtcs = dtcs + [dict(d, _is_pending=True) for d in pending]
        if not all_dtcs:
            self._dtc_count_label.configure(text="0 DTCs — Sistema OK")
            self._empty_label.pack(pady=24)
            self._update_detail_text("No se encontraron fallos.\nEl sistema esta OK.")
            return

        parts = []
        if dtcs:    parts.append(f"{len(dtcs)} confirmado{'s' if len(dtcs)!=1 else ''}")
        if pending: parts.append(f"{len(pending)} pendiente{'s' if len(pending)!=1 else ''}")
        self._dtc_count_label.configure(text=" | ".join(parts))

        for dtc in all_dtcs:
            card = self._make_dtc_card(dtc)
            card.pack(fill="x", padx=4, pady=3)
            self._dtc_rows.append(card)

        if self.controller and hasattr(self.controller, "diagnostic"):
            self._update_readiness(self.controller.diagnostic.get_readiness_tests())

    def _make_dtc_card(self, dtc: dict) -> ctk.CTkFrame:
        severity = dtc.get("severity", "low")
        is_pending = dtc.get("_is_pending", False)
        color = SEVERITY_COLORS.get(severity, self._c("text_muted"))

        card = ctk.CTkFrame(self._dtc_scroll, fg_color=self._c("bg_widget"),
                            corner_radius=6, border_width=1,
                            border_color=color if not is_pending else self._c("border"))
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkFrame(card, fg_color=color, width=4, corner_radius=3
                     ).grid(row=0, column=0, rowspan=2, sticky="ns", padx=(4, 8), pady=4)

        ctk.CTkLabel(card, text=dtc.get("code", "????"),
                     font=ctk.CTkFont(family="Courier New", size=13, weight="bold"),
                     text_color=color, fg_color=self._c("bg_panel"), corner_radius=4, width=70
                     ).grid(row=0, column=1, sticky="w", padx=(0, 6), pady=(6, 0))

        type_text = "PENDIENTE" if is_pending else SEVERITY_LABELS.get(severity, "")
        ctk.CTkLabel(card, text=type_text, font=ctk.CTkFont(size=8, weight="bold"),
                     text_color=self._c("text_muted") if is_pending else color
                     ).grid(row=0, column=2, sticky="e", padx=(0, 10), pady=(6, 0))

        ctk.CTkLabel(card, text=dtc.get("description", ""),
                     font=ctk.CTkFont(size=10), text_color=self._c("text_primary"),
                     anchor="w", wraplength=210
                     ).grid(row=1, column=1, columnspan=2, sticky="w", padx=(0, 10), pady=(0, 6))

        for w in [card]:
            w.bind("<Button-1>", lambda e, d=dtc: self._show_dtc_detail(d))

        return card

    def _show_dtc_detail(self, dtc: dict):
        sev = dtc.get("severity", "low")
        sym = {"high": "●●●", "medium": "●●○", "low": "●○○"}.get(sev, "")
        text = (
            f"CODIGO:      {dtc.get('code', '—')}\n"
            f"SEVERIDAD:   {sym} {SEVERITY_LABELS.get(sev, sev.upper())}\n"
            f"SISTEMA:     {dtc.get('system', '—')}\n"
            f"TIPO:        {'Pendiente' if dtc.get('_is_pending') else 'Confirmado'}\n"
            f"\nDESCRIPCION:\n{dtc.get('description', '—')}\n\n"
            f"{'─'*36}\n"
            f"POSIBLES CAUSAS:\n"
        )
        for cause in self._get_causes(dtc.get("code", "")):
            text += f"  • {cause}\n"
        text += f"\nACCION RECOMENDADA:\n{self._get_action(sev)}"
        self._update_detail_text(text)

    def _update_detail_text(self, text: str):
        self._detail_text.configure(state="normal")
        self._detail_text.delete("1.0", "end")
        self._detail_text.insert("1.0", text)
        self._detail_text.configure(state="disabled")

    def _update_gauges(self, data: dict):
        units = {
            "rpm": " RPM", "coolant_temp": "°C", "boost_kpa": " kPa",
            "throttle_pos": "%", "engine_load": "%", "battery_v": " V",
            "fuel_press": " bar", "oil_temp": "°C",
            "vehicle_speed": " km/h", "timing_adv": "°",
        }
        for key, widget in self._gauge_widgets.items():
            if key in data:
                widget.configure(text=f"{data[key]}{units.get(key, '')}")

    def _update_readiness(self, readiness: dict):
        label_map = {
            "MIL (Luz Averia)": "MIL (Luz Avería)",
            "Catalizador": "Catalizador",
            "Sonda O2": "Sonda calefactada O2",
            "Sistema EVAP": "Sistema EVAP",
            "EGR / VVT": "EGR / VVT",
            "Sensor O2": "Sensor O2",
            "Combustible": "Sistema combustible",
            "Encendido": "Fallo encendido",
            "Temperatura": "Temperatura global",
        }
        for short, label in self._readiness_labels.items():
            full_key = label_map.get(short, short)
            value = readiness.get(full_key, readiness.get(short, "—"))
            if value == "ON":
                label.configure(text="ON", text_color=self._c("accent"))
            elif value == "OFF":
                label.configure(text="OFF", text_color=self._c("accent_green"))
            elif value == "Completo":
                label.configure(text="OK", text_color=self._c("accent_green"))
            elif value == "Incompleto":
                label.configure(text="—", text_color=self._c("accent_yellow"))
            else:
                label.configure(text=value, text_color=self._c("text_muted"))

    def _show_freeze_frame(self, data: dict):
        text = (
            f"FREEZE FRAME — DTC: {data.get('trigger_dtc', '—')}\n"
            f"{'─'*38}\n"
            f"RPM:              {data.get('rpm', '—')} RPM\n"
            f"Temp. refriger.:  {data.get('coolant_temp', '—')}°C\n"
            f"Pos. mariposa:    {data.get('throttle_pos', '—')}%\n"
            f"Carga motor:      {data.get('engine_load', '—')}%\n"
            f"Velocidad:        {data.get('vehicle_speed', '—')} km/h\n"
            f"Presion combust.: {data.get('fuel_press', '—')} bar\n"
            f"Presion turbo:    {data.get('boost_kpa', '—')} kPa\n"
            f"{'─'*38}\n"
            f"Datos en el momento del primer fallo."
        )
        self._update_detail_text(text)

    # ─── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _get_causes(code: str) -> list:
        db = {
            "P0300": ["Bujias desgastadas", "Bobinas encendido defectuosas",
                      "Inyectores sucios", "Compresion baja", "Fallo sensor CKP/CMP"],
            "P0420": ["Catalizador envejecido", "Sonda lambda trasera defectuosa",
                      "Fugas en el escape", "Mezcla muy rica"],
            "P0171": ["Sensor MAF sucio", "Fugas de vacio en admision",
                      "Inyectores sucios", "Presion combustible baja"],
            "P0087": ["Filtro combustible obstruido", "Bomba combustible desgastada",
                      "Regulador presion defectuoso"],
            "P0016": ["Cadena de distribucion estirada", "Tensor cadena defectuoso",
                      "Sensor CKP o CMP defectuoso", "Aceite sucio o bajo nivel"],
        }
        return db.get(code, ["Sensor o actuador defectuoso", "Cableado danado o corroido",
                              "Conector mal conectado"])

    @staticmethod
    def _get_action(severity: str) -> str:
        return {
            "high":   "  URGENTE: Para el vehiculo si es posible.\n"
                      "  Lleva el coche al taller inmediatamente.",
            "medium": "  Programa revision en los proximos dias.\n"
                      "  Conduce con precaucion.",
            "low":    "  Monitoriza en proximas revisiones.\n"
                      "  No es critico pero conviene diagnosticarlo.",
        }.get(severity, "  Consulta con tecnico especializado.")

    # ─── API pública (compatibilidad con main_window) ─────────────────────

    def update_dtcs(self, dtcs):
        if isinstance(dtcs, list) and dtcs and isinstance(dtcs[0], str):
            converted = []
            for item in dtcs:
                parts = item.split(" - ", 1)
                converted.append({
                    "code": parts[0].strip(),
                    "description": parts[1].strip() if len(parts) > 1 else item,
                    "system": "Motor", "severity": "medium", "type": "confirmed",
                })
            dtcs = converted
        self._on_dtc_update(dtcs=dtcs, pending=[], mil=bool(dtcs), count=len(dtcs))
