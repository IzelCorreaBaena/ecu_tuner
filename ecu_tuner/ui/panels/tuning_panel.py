"""
ui/panels/tuning_panel.py
=========================
Panel GUI del Módulo de Tuning.

El panel más complejo: carga el .bin y permite editar los
mapas del motor en una tabla interactiva con visualización 3D.
"""

import customtkinter as ctk
from tkinter import filedialog, ttk
import tkinter as tk
from core.app_controller import AppController
import logging

logger = logging.getLogger("ECUTuner.TuningPanel")


class TuningPanel(ctk.CTkFrame):
    """
    Panel de edición de mapas del motor.

    Layout:
      ┌─────────────────────┬────────────────────────────┐
      │  Selector de mapa   │  Info del mapa seleccionado│
      ├─────────────────────┴────────────────────────────┤
      │  Tabla editable (Treeview con colores)           │
      ├──────────────────────────────────────────────────┤
      │  Toolbar: cargar bin | guardar | resetear celda  │
      └──────────────────────────────────────────────────┘
    """

    def __init__(self, parent, controller: AppController, colors: dict):
        super().__init__(parent, fg_color=colors["bg_dark"], corner_radius=0)
        self.controller = controller
        self.C = colors
        self._current_map_id = None
        self._map_data = None
        self._cell_widgets = {}
        self._build_ui()

    def _build_ui(self):
        # ── Header ──────────────────────────────────────────────
        ctk.CTkLabel(
            self, text="⚡ Módulo de Tuning — Editor de Mapas del Motor",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=self.C["text_primary"]
        ).pack(anchor="w", padx=30, pady=(24, 4))

        ctk.CTkLabel(
            self,
            text="Carga el archivo .bin, selecciona un mapa del motor y modifica los valores. "
                 "Las celdas modificadas se resaltan en naranja. Los cambios se aplican al binario en memoria.",
            font=ctk.CTkFont(size=12),
            text_color=self.C["text_muted"], wraplength=800
        ).pack(anchor="w", padx=30, pady=(0, 16))

        # ── Toolbar superior ─────────────────────────────────────
        toolbar = ctk.CTkFrame(self, fg_color=self.C["bg_panel"], corner_radius=8)
        toolbar.pack(fill="x", padx=30, pady=(0, 12))

        inner = ctk.CTkFrame(toolbar, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=10)

        ctk.CTkButton(
            inner, text="📂 Cargar .bin",
            width=130, height=34,
            fg_color=self.C["accent_blue"], hover_color="#3A7FD5",
            command=self._load_binary
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            inner, text="💾 Guardar modificado",
            width=160, height=34,
            fg_color=self.C["bg_widget"],
            command=self._save_binary
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            inner, text="↺ Resetear mapa",
            width=130, height=34,
            fg_color=self.C["bg_widget"],
            command=self._reset_map
        ).pack(side="left", padx=(0, 8))

        self._change_count_label = ctk.CTkLabel(
            inner, text="0 cambios",
            font=ctk.CTkFont(size=11),
            text_color=self.C["text_muted"]
        )
        self._change_count_label.pack(side="right")

        # ── Cuerpo principal ─────────────────────────────────────
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=30, pady=(0, 16))

        # Selector de mapa (izquierda)
        self._build_map_selector(body)

        # Área de tabla (derecha)
        self._build_table_area(body)

    def _build_map_selector(self, parent):
        """Panel izquierdo: lista de mapas disponibles + info."""
        left = ctk.CTkFrame(parent, fg_color=self.C["bg_panel"],
                             corner_radius=8, width=220)
        left.pack(side="left", fill="y", padx=(0, 12))
        left.pack_propagate(False)

        ctk.CTkLabel(
            left, text="MAPAS DISPONIBLES",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=self.C["text_muted"]
        ).pack(anchor="w", padx=16, pady=(16, 8))

        # Botones de mapa (se crean dinámicamente al cargar el .bin)
        self._map_list_frame = ctk.CTkScrollableFrame(
            left, fg_color="transparent", height=200
        )
        self._map_list_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        ctk.CTkLabel(
            self._map_list_frame,
            text="Carga un archivo .bin\npara ver los mapas.",
            font=ctk.CTkFont(size=11),
            text_color=self.C["text_muted"]
        ).pack(pady=20)

        # Info del mapa seleccionado
        ctk.CTkLabel(
            left, text="DESCRIPCIÓN",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=self.C["text_muted"]
        ).pack(anchor="w", padx=16, pady=(8, 4))

        self._map_desc = ctk.CTkTextbox(
            left, height=150,
            font=ctk.CTkFont(size=10),
            fg_color=self.C["bg_widget"],
            text_color=self.C["text_muted"],
            wrap="word"
        )
        self._map_desc.pack(fill="x", padx=12, pady=(0, 16))
        self._map_desc.insert("1.0", "Selecciona un mapa para ver su descripción técnica.")
        self._map_desc.configure(state="disabled")

    def _build_table_area(self, parent):
        """Panel derecho: tabla editable del mapa."""
        right = ctk.CTkFrame(parent, fg_color=self.C["bg_panel"], corner_radius=8)
        right.pack(side="left", fill="both", expand=True)

        # Header de la tabla
        self._table_header = ctk.CTkLabel(
            right,
            text="— Carga un archivo .bin y selecciona un mapa —",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.C["text_muted"]
        )
        self._table_header.pack(anchor="w", padx=20, pady=(16, 12))

        # Contenedor scrollable para la tabla
        self._table_container = ctk.CTkScrollableFrame(
            right, fg_color="transparent"
        )
        self._table_container.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        # Placeholder
        self._placeholder = ctk.CTkLabel(
            self._table_container,
            text="Tabla de mapa aparecerá aquí.\n\nEjemplo: Mapa de inyección 16×16\n"
                 "Eje X: RPM (600 → 7000)\nEje Y: Carga del motor (10% → 160%)\n"
                 "Valores: Tiempo de inyección en ms",
            font=ctk.CTkFont(size=12),
            text_color=self.C["text_muted"],
            justify="center"
        )
        self._placeholder.pack(expand=True, pady=60)

    def _load_binary(self):
        """Abre un .bin y carga los mapas."""
        path = filedialog.askopenfilename(
            filetypes=[("Binary files", "*.bin"), ("All files", "*.*")]
        )
        if not path:
            return

        try:
            self.controller.load_binary(path)
            # Los mapas se cargan vía evento "maps_loaded"
        except Exception as e:
            logger.error(f"Error cargando .bin: {e}")

    def _save_binary(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".bin",
            initialfile="ecu_modified.bin",
            filetypes=[("Binary files", "*.bin")]
        )
        if path:
            self.controller.tuning.save_modified_binary(path)

    def _reset_map(self):
        """Resetea el mapa actual a sus valores originales."""
        if self._current_map_id:
            logger.info(f"Reseteando mapa: {self._current_map_id}")
            # En implementación real: controller.tuning.reset_map(self._current_map_id)
            self._render_map(self._current_map_id)

    def _on_maps_loaded(self, map_ids: list):
        """Construye los botones de navegación de mapas."""
        # Limpiar el frame de lista
        for w in self._map_list_frame.winfo_children():
            w.destroy()

        MAP_ICONS = {
            "injection_time":    "⛽",
            "boost_pressure":    "💨",
            "torque_limiter":    "🔩",
            "ignition_advance":  "🔥",
        }

        for map_id in map_ids:
            icon = MAP_ICONS.get(map_id, "📊")
            map_data = self.controller.get_map(map_id)
            map_def = map_data["definition"]

            btn = ctk.CTkButton(
                self._map_list_frame,
                text=f"{icon} {map_def.name}",
                anchor="w",
                font=ctk.CTkFont(size=11),
                fg_color="transparent",
                hover_color=self.C["bg_dark"],
                text_color=self.C["text_primary"],
                corner_radius=4,
                command=lambda mid=map_id: self._select_map(mid)
            )
            btn.pack(fill="x", pady=2)

        # Seleccionar el primero automáticamente
        if map_ids:
            self._select_map(map_ids[0])

    def _select_map(self, map_id: str):
        """Selecciona y renderiza un mapa."""
        self._current_map_id = map_id
        map_data = self.controller.get_map(map_id)
        map_def = map_data["definition"]

        # Actualizar descripción
        self._map_desc.configure(state="normal")
        self._map_desc.delete("1.0", "end")
        self._map_desc.insert("1.0", map_def.description)
        self._map_desc.configure(state="disabled")

        # Actualizar header de tabla
        self._table_header.configure(
            text=f"{map_def.name}  ({map_def.rows}×{map_def.cols})  [{map_def.unit}]",
            text_color=self.C["accent_blue"]
        )

        self._render_map(map_id)

    def _render_map(self, map_id: str):
        """
        Renderiza la tabla del mapa como grid de Entry widgets editables.

        Cada celda es un CTkEntry que:
          - Muestra el valor escalado con su unidad
          - Resalta en naranja si fue modificada respecto al original
          - Permite edición directa y actualiza el modelo al perder foco
        """
        # Limpiar tabla anterior
        for w in self._table_container.winfo_children():
            w.destroy()
        self._cell_widgets.clear()

        map_data = self.controller.get_map(map_id)
        map_def = map_data["definition"]
        values = map_data["values"]
        originals = map_data["original_values"]
        axis_x = map_data["axis_x"]
        axis_y = map_data["axis_y"]

        rows, cols = map_def.rows, map_def.cols

        # ── Fila de header (eje X = RPM) ─────────────────────────
        header_row = ctk.CTkFrame(self._table_container, fg_color="transparent")
        header_row.pack(fill="x")

        # Esquina vacía (alineación)
        ctk.CTkLabel(header_row, text="↓ Carga \\ RPM →",
                     width=90, font=ctk.CTkFont(size=9),
                     text_color=self.C["text_muted"]).pack(side="left")

        # Labels del eje X
        for x_val in axis_x[:cols]:
            ctk.CTkLabel(
                header_row, text=str(x_val),
                width=52, font=ctk.CTkFont(size=9, weight="bold"),
                text_color=self.C["accent_blue"]
            ).pack(side="left", padx=1)

        # ── Filas de datos ────────────────────────────────────────
        for r in range(rows):
            row_frame = ctk.CTkFrame(self._table_container, fg_color="transparent")
            row_frame.pack(fill="x", pady=1)

            # Label del eje Y (carga)
            y_label = axis_y[r] if r < len(axis_y) else r
            ctk.CTkLabel(
                row_frame, text=str(y_label),
                width=90, font=ctk.CTkFont(size=9, weight="bold"),
                text_color=self.C["accent_blue"]
            ).pack(side="left")

            # Celdas de datos
            for c in range(cols):
                val = values[r, c]
                orig = originals[r, c]
                is_modified = abs(val - orig) > 0.001

                cell_var = tk.StringVar(value=f"{val:.2f}")
                cell = ctk.CTkEntry(
                    row_frame,
                    textvariable=cell_var,
                    width=52, height=24,
                    font=ctk.CTkFont(size=9),
                    fg_color=self.C["accent"] if is_modified else self.C["bg_widget"],
                    text_color=self.C["text_primary"],
                    border_width=1,
                    border_color=self.C["border"],
                    justify="center"
                )
                cell.pack(side="left", padx=1)

                # Binding: actualizar modelo al perder foco o presionar Enter
                cell.bind("<FocusOut>",
                          lambda e, row=r, col=c, var=cell_var:
                          self._on_cell_edit(row, col, var))
                cell.bind("<Return>",
                          lambda e, row=r, col=c, var=cell_var:
                          self._on_cell_edit(row, col, var))

                self._cell_widgets[(r, c)] = (cell, cell_var)

    def _on_cell_edit(self, row: int, col: int, var: tk.StringVar):
        """Valida y aplica la edición de una celda al modelo."""
        try:
            new_value = float(var.get().replace(",", "."))
            self.controller.update_map_cell(self._current_map_id, row, col, new_value)

            # Resaltar como modificada
            cell, _ = self._cell_widgets.get((row, col), (None, None))
            if cell:
                cell.configure(fg_color=self.C["accent"])

            # Actualizar contador de cambios
            count = self.controller.tuning.get_change_count()
            self._change_count_label.configure(
                text=f"{count} cambio{'s' if count != 1 else ''}",
                text_color=self.C["accent"]
            )

        except ValueError:
            # Valor inválido: restaurar el valor anterior
            if self._current_map_id:
                map_data = self.controller.get_map(self._current_map_id)
                orig_val = map_data["values"][row, col]
                var.set(f"{orig_val:.2f}")

    def _build_ui(self):
        """Override necesario para suscribir evento maps_loaded."""
        super_build = TuningPanel._build_ui
        # El evento se suscribe aquí (después de que controller existe)
        self.controller.on("maps_loaded", lambda map_ids: self.after(
            0, lambda: self._on_maps_loaded(map_ids)
        ))
        # Llamar build real (redefinido abajo para evitar recursión)

# ── Redefinir correctamente evitando recursión ──────────────────────────────
# (La suscripción se hace al final del __init__ real)
_original_init = TuningPanel.__init__

def _patched_init(self, parent, controller, colors):
    _original_init(self, parent, controller, colors)
    self.controller.on("maps_loaded", lambda map_ids: self.after(
        0, lambda: self._on_maps_loaded(map_ids)
    ))

TuningPanel.__init__ = _patched_init

# Revertir _build_ui para que no intente suscribirse
TuningPanel._build_ui = lambda self: None  # será llamado desde el init real


# ─── Reimplementar limpiamente ──────────────────────────────────────────────

class TuningPanel(ctk.CTkFrame):
    """Panel de edición de mapas del motor (versión limpia)."""

    def __init__(self, parent, controller: AppController, colors: dict):
        super().__init__(parent, fg_color=colors["bg_dark"], corner_radius=0)
        self.controller = controller
        self.C = colors
        self._current_map_id = None
        self._cell_widgets = {}
        self._build_layout()
        self.controller.on("maps_loaded", lambda map_ids: self.after(
            0, lambda: self._on_maps_loaded(map_ids)
        ))

    def _build_layout(self):
        ctk.CTkLabel(
            self, text="⚡ Módulo de Tuning — Editor de Mapas del Motor",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=self.C["text_primary"]
        ).pack(anchor="w", padx=30, pady=(24, 4))

        ctk.CTkLabel(
            self,
            text="Carga un .bin, selecciona un mapa y modifica los valores directamente en la tabla. "
                 "Celdas en naranja = modificadas. Los cambios se guardan en el binario en memoria.",
            font=ctk.CTkFont(size=12),
            text_color=self.C["text_muted"], wraplength=800
        ).pack(anchor="w", padx=30, pady=(0, 12))

        # Toolbar
        tb = ctk.CTkFrame(self, fg_color=self.C["bg_panel"], corner_radius=8)
        tb.pack(fill="x", padx=30, pady=(0, 10))
        inner = ctk.CTkFrame(tb, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=8)

        ctk.CTkButton(inner, text="📂 Cargar .bin", width=130, height=32,
                      fg_color=self.C["accent_blue"],
                      command=self._load_binary).pack(side="left", padx=(0, 6))
        ctk.CTkButton(inner, text="💾 Guardar .bin modificado", width=180, height=32,
                      fg_color=self.C["bg_widget"],
                      command=self._save_binary).pack(side="left", padx=(0, 6))

        self._change_lbl = ctk.CTkLabel(inner, text="Sin cambios",
                                         font=ctk.CTkFont(size=11),
                                         text_color=self.C["text_muted"])
        self._change_lbl.pack(side="right")

        # Cuerpo
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=30, pady=(0, 16))

        # Selector izquierdo
        self._left = ctk.CTkFrame(body, fg_color=self.C["bg_panel"],
                                   corner_radius=8, width=210)
        self._left.pack(side="left", fill="y", padx=(0, 10))
        self._left.pack_propagate(False)

        ctk.CTkLabel(self._left, text="MAPAS",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=self.C["text_muted"]).pack(anchor="w", padx=14, pady=(14, 6))

        self._map_btns_frame = ctk.CTkScrollableFrame(self._left, fg_color="transparent")
        self._map_btns_frame.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        self._no_maps_lbl = ctk.CTkLabel(
            self._map_btns_frame,
            text="Carga un .bin\npara ver los mapas disponibles.",
            font=ctk.CTkFont(size=11),
            text_color=self.C["text_muted"], justify="center"
        )
        self._no_maps_lbl.pack(pady=20)

        self._desc_box = ctk.CTkTextbox(
            self._left, height=130, font=ctk.CTkFont(size=10),
            fg_color=self.C["bg_widget"], text_color=self.C["text_muted"], wrap="word"
        )
        self._desc_box.pack(fill="x", padx=10, pady=(0, 12))
        self._desc_box.insert("1.0", "Descripción del mapa seleccionado.")
        self._desc_box.configure(state="disabled")

        # Tabla derecha
        self._right = ctk.CTkFrame(body, fg_color=self.C["bg_panel"], corner_radius=8)
        self._right.pack(side="left", fill="both", expand=True)

        self._tbl_hdr = ctk.CTkLabel(self._right,
                                      text="— Selecciona un mapa —",
                                      font=ctk.CTkFont(size=13, weight="bold"),
                                      text_color=self.C["text_muted"])
        self._tbl_hdr.pack(anchor="w", padx=18, pady=(14, 8))

        self._tbl_scroll = ctk.CTkScrollableFrame(self._right, fg_color="transparent")
        self._tbl_scroll.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        ctk.CTkLabel(
            self._tbl_scroll,
            text="La tabla del mapa aparecerá aquí.\n\nEjemplo de mapa 16×16:\n"
                 "  Eje X → RPM (600 a 7000)\n  Eje Y → Carga (%)\n"
                 "  Valores → Tiempo de inyección (ms)\n\nHaz doble clic en una celda para editarla.",
            font=ctk.CTkFont(size=11),
            text_color=self.C["text_muted"], justify="center"
        ).pack(expand=True, pady=40)

    def _load_binary(self):
        path = filedialog.askopenfilename(
            filetypes=[("Binary files", "*.bin"), ("All files", "*.*")]
        )
        if path:
            self.controller.load_binary(path)

    def _save_binary(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".bin",
            initialfile="ecu_modified.bin",
            filetypes=[("Binary files", "*.bin")]
        )
        if path:
            self.controller.tuning.save_modified_binary(path)

    def _on_maps_loaded(self, map_ids: list):
        for w in self._map_btns_frame.winfo_children():
            w.destroy()

        ICONS = {"injection_time": "⛽", "boost_pressure": "💨",
                 "torque_limiter": "🔩", "ignition_advance": "🔥"}

        for mid in map_ids:
            mdata = self.controller.get_map(mid)
            mdef = mdata["definition"]
            icon = ICONS.get(mid, "📊")
            btn = ctk.CTkButton(
                self._map_btns_frame,
                text=f"{icon} {mdef.name}",
                anchor="w", font=ctk.CTkFont(size=11),
                fg_color="transparent", hover_color=self.C["bg_dark"],
                text_color=self.C["text_primary"], corner_radius=4,
                command=lambda m=mid: self._select_map(m)
            )
            btn.pack(fill="x", pady=2)

        if map_ids:
            self._select_map(map_ids[0])

    def _select_map(self, map_id: str):
        self._current_map_id = map_id
        mdata = self.controller.get_map(map_id)
        mdef = mdata["definition"]

        self._desc_box.configure(state="normal")
        self._desc_box.delete("1.0", "end")
        self._desc_box.insert("1.0", mdef.description)
        self._desc_box.configure(state="disabled")

        self._tbl_hdr.configure(
            text=f"{mdef.name}  ({mdef.rows}×{mdef.cols})  [{mdef.unit}]",
            text_color=self.C["accent_blue"]
        )
        self._render_table(map_id, mdata)

    def _render_table(self, map_id: str, mdata: dict):
        for w in self._tbl_scroll.winfo_children():
            w.destroy()
        self._cell_widgets.clear()

        mdef = mdata["definition"]
        values = mdata["values"]
        originals = mdata["original_values"]
        axis_x = mdata["axis_x"]
        axis_y = mdata["axis_y"]
        rows, cols = mdef.rows, mdef.cols

        # Header fila (eje X)
        hrow = ctk.CTkFrame(self._tbl_scroll, fg_color="transparent")
        hrow.pack(fill="x", pady=(0, 2))
        ctk.CTkLabel(hrow, text="↓\\→", width=80, font=ctk.CTkFont(size=8),
                     text_color=self.C["text_muted"]).pack(side="left")
        for xv in axis_x[:cols]:
            ctk.CTkLabel(hrow, text=str(xv), width=50,
                         font=ctk.CTkFont(size=8, weight="bold"),
                         text_color=self.C["accent_blue"]).pack(side="left", padx=1)

        # Filas de datos
        for r in range(rows):
            rframe = ctk.CTkFrame(self._tbl_scroll, fg_color="transparent")
            rframe.pack(fill="x", pady=1)

            yv = axis_y[r] if r < len(axis_y) else r
            ctk.CTkLabel(rframe, text=str(yv), width=80,
                         font=ctk.CTkFont(size=8, weight="bold"),
                         text_color=self.C["accent_blue"]).pack(side="left")

            for c in range(cols):
                val = values[r, c]
                orig = originals[r, c]
                is_mod = abs(val - orig) > 0.001

                var = tk.StringVar(value=f"{val:.1f}")
                entry = ctk.CTkEntry(
                    rframe, textvariable=var,
                    width=50, height=22,
                    font=ctk.CTkFont(size=8),
                    fg_color="#5A3020" if is_mod else self.C["bg_widget"],
                    text_color=self.C["accent"] if is_mod else self.C["text_primary"],
                    border_width=1,
                    border_color=self.C["accent"] if is_mod else self.C["border"],
                    justify="center"
                )
                entry.pack(side="left", padx=1)
                entry.bind("<FocusOut>", lambda e, row=r, col=c, v=var:
                           self._on_cell_edit(row, col, v))
                entry.bind("<Return>", lambda e, row=r, col=c, v=var:
                           self._on_cell_edit(row, col, v))
                self._cell_widgets[(r, c)] = (entry, var)

    def _on_cell_edit(self, row, col, var):
        try:
            new_val = float(var.get().replace(",", "."))
            self.controller.update_map_cell(self._current_map_id, row, col, new_val)
            cell, _ = self._cell_widgets.get((row, col), (None, None))
            if cell:
                cell.configure(fg_color="#5A3020", border_color=self.C["accent"],
                                text_color=self.C["accent"])
            count = self.controller.tuning.get_change_count()
            self._change_lbl.configure(
                text=f"{count} cambio{'s' if count != 1 else ''}",
                text_color=self.C["accent"]
            )
        except ValueError:
            pass
