"""
ui/panels/vcds_panel.py
========================
Panel de Ajustes Ocultos (VCDS-Style Coding).

Permite activar/desactivar funciones del vehículo mediante modificación
de bytes de codificación y canales de adaptación en los módulos de control,
SIN modificar el firmware.

Layout:
  ┌─────────────────────────────────────────────────────────┐
  │  HEADER: título + botones (Aplicar / Rollback / Reset)  │
  ├──────────────────┬──────────────────────────────────────┤
  │  CATEGORÍAS      │  AJUSTES DE LA CATEGORÍA ACTIVA      │
  │  (sidebar)       │  (tarjetas con control interactivo)  │
  ├──────────────────┴──────────────────────────────────────┤
  │  HISTORIAL DE CAMBIOS                                   │
  └─────────────────────────────────────────────────────────┘
"""

import customtkinter as ctk
import tkinter as tk
import logging
from typing import Optional

logger = logging.getLogger("ECUTuner.VCDSPanel")


class VCDSPanel(ctk.CTkFrame):
    """
    Panel de ajustes ocultos VCDS-style.
    Muestra configuraciones agrupadas por categoría con controles
    según el tipo de ajuste (toggle, select, adapt).
    """

    def __init__(self, parent, controller=None, colors=None, **kwargs):
        if colors is None:
            colors = {}
        super().__init__(parent, fg_color=colors.get("bg_dark", "#0D1117"), corner_radius=0)
        self.controller = controller
        self.C = colors
        self._current_category: Optional[str] = None
        self._category_btns: dict = {}
        self._setting_cards: list = []
        self._build_ui()

        if controller and hasattr(controller, "on"):
            controller.on("hidden_setting_applied",    self._on_setting_applied)
            controller.on("hidden_setting_rolled_back",self._on_setting_rolled_back)
            controller.on("hidden_settings_reset_all", self._on_all_reset)
            controller.on("hidden_setting_risk_warning", self._on_risk_warning)

    # ─── Helpers de color ───────────────────────────────────────────────

    def _c(self, key: str, default: str = "#888") -> str:
        return self.C.get(key, default)

    # ─── Construcción de UI ─────────────────────────────────────────────

    def _build_ui(self):
        self._build_header()

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=(0, 6))
        body.grid_columnconfigure(0, weight=0)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        self._build_category_sidebar(body)
        self._build_settings_area(body)

        self._build_history_bar()

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color=self._c("bg_panel"), corner_radius=0)
        header.pack(fill="x")

        inner = ctk.CTkFrame(header, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(inner, text="Ajustes Ocultos",
                     font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=self._c("text_primary")).pack(side="left")
        ctk.CTkLabel(inner, text=" — Coding y Adaptacion (VCDS-Style)",
                     font=ctk.CTkFont(size=12),
                     text_color=self._c("text_muted")).pack(side="left")

        ctk.CTkLabel(
            inner,
            text="Sin modificar firmware",
            font=ctk.CTkFont(size=10),
            fg_color=self._c("accent_green"),
            text_color="#0D1117",
            corner_radius=4,
            width=130
        ).pack(side="right", padx=(0, 0))

        btn_frame = ctk.CTkFrame(inner, fg_color="transparent")
        btn_frame.pack(side="right", padx=(0, 12))

        ctk.CTkButton(btn_frame, text="Rollback Ultimo",
                      width=125, height=30, fg_color=self._c("accent_yellow"),
                      hover_color="#B8922F", text_color="#0D1117",
                      font=ctk.CTkFont(size=12),
                      command=self._rollback_last).pack(side="left", padx=(0, 5))

        ctk.CTkButton(btn_frame, text="Reset Fabrica",
                      width=110, height=30, fg_color=self._c("accent"),
                      hover_color="#C5533A",
                      font=ctk.CTkFont(size=12),
                      command=self._reset_all).pack(side="left")

    def _build_category_sidebar(self, parent):
        sidebar = ctk.CTkFrame(parent, fg_color=self._c("bg_panel"),
                               corner_radius=8, width=180)
        sidebar.grid(row=0, column=0, sticky="ns", padx=(0, 10), pady=4)
        sidebar.grid_propagate(False)

        ctk.CTkLabel(sidebar, text="CATEGORIAS",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=self._c("text_muted")
                     ).pack(pady=(14, 6), padx=14, anchor="w")

        self._cat_scroll = ctk.CTkScrollableFrame(sidebar, fg_color="transparent")
        self._cat_scroll.pack(fill="both", expand=True, padx=4, pady=(0, 8))

        # Mostrar categorías o mensaje de espera
        self._no_cat_label = ctk.CTkLabel(
            self._cat_scroll,
            text="Sin modulo\nconectado",
            font=ctk.CTkFont(size=11),
            text_color=self._c("text_muted"), justify="center")
        self._no_cat_label.pack(pady=16)

        # Cargar desde el módulo hidden_settings si disponible
        self.after(100, self._load_categories)

    def _build_settings_area(self, parent):
        right = ctk.CTkFrame(parent, fg_color=self._c("bg_panel"), corner_radius=8)
        right.grid(row=0, column=1, sticky="nsew", pady=4)
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        self._settings_title = ctk.CTkLabel(
            right, text="Selecciona una categoria del panel izquierdo",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self._c("text_muted"))
        self._settings_title.grid(row=0, column=0, sticky="w", padx=16, pady=(14, 8))

        self._settings_scroll = ctk.CTkScrollableFrame(right, fg_color="transparent")
        self._settings_scroll.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self._settings_scroll.grid_columnconfigure(0, weight=1)

    def _build_history_bar(self):
        hist = ctk.CTkFrame(self, fg_color=self._c("bg_panel"), corner_radius=0, height=56)
        hist.pack(fill="x")
        hist.pack_propagate(False)

        ctk.CTkLabel(hist, text="ULTIMO CAMBIO:",
                     font=ctk.CTkFont(size=9, weight="bold"),
                     text_color=self._c("text_muted")
                     ).pack(side="left", padx=16, pady=4)

        self._history_label = ctk.CTkLabel(
            hist, text="Ningun cambio aplicado aun.",
            font=ctk.CTkFont(size=11),
            text_color=self._c("text_muted"))
        self._history_label.pack(side="left", padx=4)

    # ─── Carga de datos ─────────────────────────────────────────────────

    def _load_categories(self):
        """Carga las categorías desde el módulo hidden_settings."""
        if not (self.controller and hasattr(self.controller, "hidden_settings")):
            return

        self._no_cat_label.pack_forget()
        categories = self.controller.hidden_settings.get_by_category()

        for cat_name in categories:
            btn = ctk.CTkButton(
                self._cat_scroll,
                text=cat_name,
                anchor="w",
                fg_color="transparent",
                hover_color=self._c("bg_widget"),
                text_color=self._c("text_primary"),
                font=ctk.CTkFont(size=12),
                corner_radius=6,
                command=lambda n=cat_name: self._show_category(n)
            )
            btn.pack(fill="x", padx=4, pady=2)
            self._category_btns[cat_name] = btn

        # Mostrar primera categoría por defecto
        if categories:
            first = next(iter(categories))
            self._show_category(first)

    def _show_category(self, category_name: str):
        """Muestra los ajustes de la categoría seleccionada."""
        self._current_category = category_name

        # Resaltar botón activo
        for name, btn in self._category_btns.items():
            if name == category_name:
                btn.configure(fg_color=self._c("bg_widget"),
                              text_color=self._c("accent_blue"))
            else:
                btn.configure(fg_color="transparent",
                              text_color=self._c("text_primary"))

        # Limpiar tarjetas anteriores
        for card in self._setting_cards:
            card.destroy()
        self._setting_cards.clear()

        self._settings_title.configure(text=f"Ajustes — {category_name}")

        if not (self.controller and hasattr(self.controller, "hidden_settings")):
            return

        by_cat = self.controller.hidden_settings.get_by_category()
        settings = by_cat.get(category_name, [])

        for setting in settings:
            card = self._make_setting_card(setting)
            card.grid(column=0, sticky="ew", padx=4, pady=4)
            self._settings_scroll.grid_columnconfigure(0, weight=1)
            self._setting_cards.append(card)

    def _make_setting_card(self, setting) -> ctk.CTkFrame:
        """Crea una tarjeta interactiva para un ajuste oculto."""
        from modules.hidden_settings_module import SettingType

        risk_colors = {
            "low":    self._c("accent_green"),
            "medium": self._c("accent_yellow"),
            "high":   self._c("accent"),
        }
        risk_color = risk_colors.get(setting.risk_level, self._c("text_muted"))

        card = ctk.CTkFrame(self._settings_scroll,
                            fg_color=self._c("bg_widget"), corner_radius=8,
                            border_width=1, border_color=self._c("border"))
        card.grid_columnconfigure(0, weight=1)

        # Cabecera de la tarjeta
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(10, 4))
        top.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(top, text=setting.name,
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=self._c("text_primary"),
                     anchor="w").grid(row=0, column=0, sticky="w")

        # Badge de módulo y riesgo
        badge_frame = ctk.CTkFrame(top, fg_color="transparent")
        badge_frame.grid(row=0, column=1, sticky="e")

        ctk.CTkLabel(badge_frame, text=setting.module,
                     font=ctk.CTkFont(size=9),
                     fg_color=self._c("bg_panel"),
                     text_color=self._c("text_muted"),
                     corner_radius=4, width=50
                     ).pack(side="left", padx=(0, 4))

        risk_labels = {"low": "BAJO", "medium": "MEDIO", "high": "ALTO"}
        ctk.CTkLabel(badge_frame,
                     text=f"Riesgo {risk_labels.get(setting.risk_level, '')}",
                     font=ctk.CTkFont(size=9),
                     fg_color=risk_color,
                     text_color="#0D1117" if setting.risk_level != "high" else "#FFFFFF",
                     corner_radius=4, width=80
                     ).pack(side="left")

        # Descripción
        ctk.CTkLabel(card, text=setting.description,
                     font=ctk.CTkFont(size=10),
                     text_color=self._c("text_muted"),
                     anchor="w", wraplength=550, justify="left"
                     ).grid(row=1, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 6))

        # Nota técnica (si existe)
        if setting.note:
            ctk.CTkLabel(card,
                         text=f"  Nota: {setting.note}",
                         font=ctk.CTkFont(size=9),
                         text_color=self._c("accent_blue"),
                         anchor="w", wraplength=550
                         ).grid(row=2, column=0, columnspan=2, sticky="w",
                                padx=12, pady=(0, 4))

        # Control según tipo de ajuste
        ctrl_row = 3
        if setting.setting_type == SettingType.TOGGLE:
            self._add_toggle_control(card, setting, ctrl_row)
        elif setting.setting_type == SettingType.SELECT:
            self._add_select_control(card, setting, ctrl_row)
        elif setting.setting_type == SettingType.ADAPT:
            self._add_adapt_control(card, setting, ctrl_row)

        return card

    def _add_toggle_control(self, card, setting, row: int):
        """Control On/Off para ajustes tipo TOGGLE."""
        ctrl = ctk.CTkFrame(card, fg_color="transparent")
        ctrl.grid(row=row, column=0, columnspan=2, sticky="ew", padx=12, pady=(4, 12))

        var = tk.BooleanVar(value=bool(setting.current_val))

        lbl = ctk.CTkLabel(ctrl,
                           text="ACTIVADO" if var.get() else "DESACTIVADO",
                           font=ctk.CTkFont(size=11, weight="bold"),
                           text_color=self._c("accent_green") if var.get() else self._c("text_muted"),
                           width=100)
        lbl.pack(side="left", padx=(0, 12))

        def on_toggle():
            new_val = var.get()
            lbl.configure(
                text="ACTIVADO" if new_val else "DESACTIVADO",
                text_color=self._c("accent_green") if new_val else self._c("text_muted")
            )
            self._apply(setting.id, new_val)

        sw = ctk.CTkSwitch(ctrl, variable=var, text="",
                           onvalue=True, offvalue=False,
                           progress_color=self._c("accent_green"),
                           command=on_toggle)
        sw.pack(side="left")

        default_txt = "Fabrica: ACTIVADO" if setting.default_val else "Fabrica: DESACTIVADO"
        ctk.CTkLabel(ctrl, text=default_txt,
                     font=ctk.CTkFont(size=9),
                     text_color=self._c("text_muted")).pack(side="right")

    def _add_select_control(self, card, setting, row: int):
        """Control de selección para ajustes tipo SELECT."""
        ctrl = ctk.CTkFrame(card, fg_color="transparent")
        ctrl.grid(row=row, column=0, columnspan=2, sticky="ew", padx=12, pady=(4, 12))

        ctk.CTkLabel(ctrl, text="Valor:",
                     font=ctk.CTkFont(size=11),
                     text_color=self._c("text_muted")).pack(side="left", padx=(0, 8))

        options = [str(o) for o in setting.options]
        current = str(setting.current_val)

        combo = ctk.CTkComboBox(
            ctrl,
            values=options,
            width=180,
            fg_color=self._c("bg_panel"),
            border_color=self._c("border"),
            text_color=self._c("text_primary"),
            command=lambda val, sid=setting.id: self._apply(sid, val)
        )
        combo.set(current)
        combo.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(ctrl, text=f"Fabrica: {setting.default_val}",
                     font=ctk.CTkFont(size=9),
                     text_color=self._c("text_muted")).pack(side="left")

    def _add_adapt_control(self, card, setting, row: int):
        """Control numérico para ajustes tipo ADAPT."""
        ctrl = ctk.CTkFrame(card, fg_color="transparent")
        ctrl.grid(row=row, column=0, columnspan=2, sticky="ew", padx=12, pady=(4, 12))

        ctk.CTkLabel(ctrl, text="Valor:",
                     font=ctk.CTkFont(size=11),
                     text_color=self._c("text_muted")).pack(side="left", padx=(0, 8))

        var = tk.StringVar(value=str(setting.current_val))
        entry = ctk.CTkEntry(ctrl, textvariable=var, width=90,
                             fg_color=self._c("bg_panel"),
                             border_color=self._c("border"),
                             text_color=self._c("text_primary"))
        entry.pack(side="left")

        ctk.CTkLabel(ctrl, text=setting.unit,
                     font=ctk.CTkFont(size=11),
                     text_color=self._c("text_muted")).pack(side="left", padx=(4, 16))

        if setting.min_val is not None and setting.max_val is not None:
            ctk.CTkLabel(ctrl,
                         text=f"Rango: {setting.min_val}–{setting.max_val} {setting.unit}",
                         font=ctk.CTkFont(size=9),
                         text_color=self._c("text_muted")).pack(side="left", padx=(0, 12))

        def apply_adapt():
            try:
                val = float(var.get())
                if setting.min_val is not None and val < setting.min_val:
                    val = setting.min_val
                    var.set(str(val))
                if setting.max_val is not None and val > setting.max_val:
                    val = setting.max_val
                    var.set(str(val))
                self._apply(setting.id, val)
            except ValueError:
                pass

        ctk.CTkButton(ctrl, text="Aplicar", width=70, height=26,
                      fg_color=self._c("accent_blue"), hover_color="#3A7FD5",
                      font=ctk.CTkFont(size=11),
                      command=apply_adapt).pack(side="left")

        ctk.CTkLabel(ctrl, text=f"Fabrica: {setting.default_val} {setting.unit}",
                     font=ctk.CTkFont(size=9),
                     text_color=self._c("text_muted")).pack(side="right")

    # ─── Acciones ────────────────────────────────────────────────────────

    def _apply(self, setting_id: str, value):
        if self.controller and hasattr(self.controller, "hidden_settings"):
            self.controller.hidden_settings.apply_setting(setting_id, value)
        else:
            logger.warning("HiddenSettingsModule no disponible en el controlador.")

    def _rollback_last(self):
        if self.controller and hasattr(self.controller, "hidden_settings"):
            self.controller.hidden_settings.rollback_last()

    def _reset_all(self):
        if self.controller and hasattr(self.controller, "hidden_settings"):
            self.controller.hidden_settings.rollback_all()

    # ─── Callbacks de eventos ────────────────────────────────────────────

    def _on_setting_applied(self, setting_id="", name="", old_value=None,
                            new_value=None, **kw):
        msg = f"'{name}': {old_value} → {new_value}"
        self.after(0, lambda: self._history_label.configure(
            text=msg, text_color=self._c("accent_green")))

        # Refrescar tarjetas si seguimos en la misma categoría
        if self._current_category:
            self.after(50, lambda: self._show_category(self._current_category))

    def _on_setting_rolled_back(self, name="", restored_value=None, **kw):
        msg = f"Revertido: '{name}' → {restored_value}"
        self.after(0, lambda: self._history_label.configure(
            text=msg, text_color=self._c("accent_yellow")))
        if self._current_category:
            self.after(50, lambda: self._show_category(self._current_category))

    def _on_all_reset(self, **kw):
        self.after(0, lambda: self._history_label.configure(
            text="Todos los ajustes revertidos a valores de fabrica.",
            text_color=self._c("accent_yellow")))
        if self._current_category:
            self.after(50, lambda: self._show_category(self._current_category))

    def _on_risk_warning(self, setting=None, message="", **kw):
        logger.warning(message)
        self.after(0, lambda: self._history_label.configure(
            text=f"AVISO: {message[:80]}...",
            text_color=self._c("accent")))
