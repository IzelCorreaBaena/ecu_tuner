"""
ui/panels/flash_panel.py
========================
Panel GUI del Módulo de Flasheo.
El más crítico: muestra advertencias, valida el binario
y supervisa el proceso de escritura con estado detallado.
"""

import customtkinter as ctk
from tkinter import filedialog
from core.app_controller import AppController


class FlashPanel(ctk.CTkFrame):
    def __init__(self, parent, controller: AppController, colors: dict):
        super().__init__(parent, fg_color=colors["bg_dark"], corner_radius=0)
        self.controller = controller
        self.C = colors
        self._build_ui()

    def _build_ui(self):
        ctk.CTkLabel(
            self, text="🔥 Módulo de Flasheo — Escritura a la ECU",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=self.C["accent"]
        ).pack(anchor="w", padx=30, pady=(24, 4))

        # ── Advertencia principal ─────────────────────────────────
        warn = ctk.CTkFrame(self, fg_color="#3A1010", corner_radius=8,
                             border_width=2, border_color=self.C["accent"])
        warn.pack(fill="x", padx=30, pady=(0, 16))

        ctk.CTkLabel(
            warn,
            text="⚠️  ADVERTENCIA — OPERACIÓN IRREVERSIBLE",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.C["accent"]
        ).pack(anchor="w", padx=20, pady=(14, 4))

        ctk.CTkLabel(
            warn,
            text="El flasheo escribe directamente en la memoria flash de la ECU. "
                 "Un proceso interrumpido o un archivo corrupto puede dejar el vehículo inoperativo (brick). "
                 "ASEGÚRATE de:\n"
                 "  • Tener el backup original verificado\n"
                 "  • El motor está parado y el contacto en posición ON\n"
                 "  • No desconectar el cable durante el proceso\n"
                 "  • La batería está cargada (>12V) o conectada a cargador",
            font=ctk.CTkFont(size=11),
            text_color="#FF9999",
            justify="left", wraplength=750
        ).pack(anchor="w", padx=20, pady=(0, 14))

        # ── Selector de archivo ──────────────────────────────────
        file_frame = ctk.CTkFrame(self, fg_color=self.C["bg_panel"], corner_radius=8)
        file_frame.pack(fill="x", padx=30, pady=(0, 12))

        ctk.CTkLabel(file_frame, text="Archivo a flashear",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=self.C["text_primary"]).pack(anchor="w", padx=20, pady=(14, 8))

        row = ctk.CTkFrame(file_frame, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(0, 16))

        self._bin_path = ctk.StringVar(value="")
        ctk.CTkEntry(row, textvariable=self._bin_path, width=380,
                     placeholder_text="Ruta al archivo .bin modificado...",
                     fg_color=self.C["bg_widget"]).pack(side="left")
        ctk.CTkButton(row, text="📂 Examinar", width=110,
                      fg_color=self.C["bg_widget"],
                      command=self._browse).pack(side="left", padx=8)
        self._validate_btn = ctk.CTkButton(
            row, text="✓ Validar", width=90,
            fg_color=self.C["accent_yellow"], hover_color="#B8922E",
            text_color="#000",
            command=self._validate
        )
        self._validate_btn.pack(side="left")

        # ── Panel de validación ──────────────────────────────────
        self._val_frame = ctk.CTkFrame(self, fg_color=self.C["bg_panel"], corner_radius=8)
        self._val_frame.pack(fill="x", padx=30, pady=(0, 12))

        ctk.CTkLabel(self._val_frame, text="Resultado de Validación Pre-Flash",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=self.C["text_muted"]).pack(anchor="w", padx=20, pady=(12, 6))

        self._val_items = {}
        checks = [
            ("size_ok",      "Tamaño del archivo"),
            ("structure_ok", "Estructura del binario"),
            ("checksum_ok",  "Checksum (se recalcula)"),
        ]

        for key, label in checks:
            row2 = ctk.CTkFrame(self._val_frame, fg_color="transparent")
            row2.pack(fill="x", padx=20, pady=2)
            ctk.CTkLabel(row2, text=label, width=200, anchor="w",
                         text_color=self.C["text_muted"]).pack(side="left")
            lbl = ctk.CTkLabel(row2, text="— Pendiente", width=180,
                                text_color=self.C["text_muted"])
            lbl.pack(side="left")
            self._val_items[key] = lbl

        self._checksum_lbl = ctk.CTkLabel(
            self._val_frame, text="",
            font=ctk.CTkFont(size=10, family="Courier New"),
            text_color=self.C["text_muted"]
        )
        self._checksum_lbl.pack(anchor="w", padx=20, pady=(4, 12))

        # ── Botón de flasheo ─────────────────────────────────────
        flash_row = ctk.CTkFrame(self, fg_color="transparent")
        flash_row.pack(fill="x", padx=30, pady=(0, 12))

        self._flash_btn = ctk.CTkButton(
            flash_row,
            text="🔥 INICIAR FLASHEO",
            font=ctk.CTkFont(size=15, weight="bold"),
            width=200, height=48,
            fg_color="#8B0000", hover_color="#5A0000",
            state="disabled",
            command=self._start_flash
        )
        self._flash_btn.pack(side="left")

        ctk.CTkButton(
            flash_row, text="⛔ ABORTAR",
            width=110, height=48,
            fg_color=self.C["bg_widget"], hover_color="#5A0000",
            command=self._abort
        ).pack(side="left", padx=12)

        # ── Progreso detallado ────────────────────────────────────
        self._phase_lbl = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.C["accent_yellow"]
        )
        self._phase_lbl.pack(anchor="w", padx=30, pady=(0, 4))

        self._progress = ctk.CTkProgressBar(self, height=16, corner_radius=6)
        self._progress.pack(fill="x", padx=30, pady=(0, 4))
        self._progress.set(0)

        self._step_lbl = ctk.CTkLabel(
            self, text="Esperando inicio de flasheo...",
            font=ctk.CTkFont(size=11),
            text_color=self.C["text_muted"]
        )
        self._step_lbl.pack(anchor="w", padx=30)

        # Log
        log_frame = ctk.CTkFrame(self, fg_color=self.C["bg_panel"], corner_radius=8)
        log_frame.pack(fill="both", expand=True, padx=30, pady=12)

        ctk.CTkLabel(log_frame, text="Log de Flasheo",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=self.C["text_muted"]).pack(anchor="w", padx=16, pady=(10, 4))

        self._log = ctk.CTkTextbox(
            log_frame, font=ctk.CTkFont(family="Courier New", size=10),
            fg_color=self.C["bg_widget"], text_color=self.C["accent_green"]
        )
        self._log.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        # Suscribir eventos
        self.controller.on("flash_progress", self._on_progress)
        self.controller.on("flash_complete", self._on_complete)
        self.controller.on("flash_error", self._on_error)
        self.controller.on("flash_warning", self._on_warning)

    def _browse(self):
        path = filedialog.askopenfilename(
            filetypes=[("Binary files", "*.bin"), ("All files", "*.*")]
        )
        if path:
            self._bin_path.set(path)

    def _validate(self):
        path = self._bin_path.get()
        if not path:
            return
        try:
            with open(path, "rb") as f:
                data = f.read()
            result = self.controller.flash.validate_binary(data)
            self._show_validation(result)
        except FileNotFoundError:
            self._log_append(f"[ERROR] Archivo no encontrado: {path}\n")

    def _show_validation(self, result):
        """Muestra el resultado de validación en la UI."""
        status_map = {
            True:  ("✓ OK",   self.C["accent_green"]),
            False: ("✗ FAIL", self.C["accent"]),
        }

        for key, lbl in self._val_items.items():
            ok = getattr(result, key, False)
            text, color = status_map[ok]
            self.after(0, lambda l=lbl, t=text, c=color:
                       l.configure(text=t, text_color=c))

        cs_text = (f"CRC calculado: 0x{result.calculated_checksum:08X}  "
                   f"| Almacenado: 0x{result.stored_checksum:08X}")
        self.after(0, lambda: self._checksum_lbl.configure(text=cs_text))

        if result.errors:
            for err in result.errors:
                self._log_append(f"[VALIDACIÓN ERROR] {err}\n")
        else:
            self._log_append("[VALIDACIÓN OK] El archivo pasó todos los checks. Listo para flashear.\n")
            self.after(0, lambda: self._flash_btn.configure(state="normal"))

    def _start_flash(self):
        path = self._bin_path.get()
        if not path:
            return
        self._flash_btn.configure(state="disabled")
        self._log_append(f"\n[FLASH START] Iniciando escritura → {path}\n")
        self.controller.start_flash(path)

    def _abort(self):
        self.controller.flash.abort()
        self._log_append("[ABORT] Solicitud de cancelación enviada.\n")

    def _on_progress(self, phase="", step="", pct=0, bytes_written=0, total=0, **kwargs):
        self.after(0, lambda: self._phase_lbl.configure(text=phase))
        self.after(0, lambda: self._progress.set(pct / 100))
        label = f"{step}"
        if bytes_written and total:
            label += f"  —  {bytes_written // 1024} KB / {total // 1024} KB"
        self.after(0, lambda: self._step_lbl.configure(text=label))
        self.after(0, lambda: self._log_append(f"[{pct:>3}%] {step}\n"))

    def _on_complete(self, size_kb=0, checksum="", **kwargs):
        self.after(0, lambda: self._log_append(
            f"\n[✓ COMPLETADO] Flasheo exitoso. {size_kb} KB escritos. Checksum: {checksum}\n"
            f"[INFO] La ECU ha sido reiniciada. Espere ~10s antes de arrancar el motor.\n"
        ))
        self.after(0, lambda: self._progress.set(1.0))
        self.after(0, lambda: self._phase_lbl.configure(
            text="✓ Flasheo completado con éxito", text_color=self.C["accent_green"]
        ))

    def _on_error(self, error="", **kwargs):
        self.after(0, lambda: self._log_append(f"\n[✗ ERROR] {error}\n"))
        self.after(0, lambda: self._phase_lbl.configure(
            text=f"✗ Error: {error}", text_color=self.C["accent"]
        ))
        self.after(0, lambda: self._flash_btn.configure(state="normal"))

    def _on_warning(self, warnings=None, **kwargs):
        if warnings:
            for w in warnings:
                self.after(0, lambda msg=w: self._log_append(f"[⚠ AVISO] {msg}\n"))

    def _log_append(self, text: str):
        self._log.insert("end", text)
        self._log.see("end")
