"""
ui/panels/backup_panel.py
=========================
Panel GUI del Módulo de Backup (volcado de memoria ECU).
"""

import customtkinter as ctk
from tkinter import filedialog
from core.app_controller import AppController


class BackupPanel(ctk.CTkFrame):
    def __init__(self, parent, controller: AppController, colors: dict):
        super().__init__(parent, fg_color=colors["bg_dark"], corner_radius=0)
        self.controller = controller
        self.C = colors
        self._build_ui()

    def _build_ui(self):
        ctk.CTkLabel(
            self, text="💾 Módulo de Backup — Volcado de Memoria Flash",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=self.C["text_primary"]
        ).pack(anchor="w", padx=30, pady=(24, 4))

        ctk.CTkLabel(
            self,
            text="Lee y guarda la memoria flash completa de la ECU en un archivo .bin de seguridad. "
                 "SIEMPRE haz un backup antes de modificar nada.",
            font=ctk.CTkFont(size=12),
            text_color=self.C["text_muted"], wraplength=700
        ).pack(anchor="w", padx=30, pady=(0, 20))

        # ── Info técnica ─────────────────────────────────────────
        info = ctk.CTkFrame(self, fg_color=self.C["bg_panel"], corner_radius=10)
        info.pack(fill="x", padx=30, pady=(0, 16))

        info_content = ctk.CTkFrame(info, fg_color="transparent")
        info_content.pack(fill="x", padx=20, pady=16)

        steps = [
            ("1", "DiagnosticSessionControl (0x10/0x03)", "Abre sesión extendida de diagnóstico"),
            ("2", "SecurityAccess (0x27) — Seed/Key", "Desbloqueo criptográfico de la ECU"),
            ("3", "ReadMemoryByAddress (0x23) × N", "Lectura de bloques de 256B por CAN-TP"),
            ("4", "Verificación por bloque", "Integridad de cada chunk antes de continuar"),
            ("5", "Guardado progresivo en .bin", "Escritura incremental (seguro ante cortes)"),
        ]

        for num, step, desc in steps:
            row = ctk.CTkFrame(info_content, fg_color="transparent")
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, text=f"[{num}]", font=ctk.CTkFont(size=11, weight="bold"),
                          text_color=self.C["accent_blue"], width=30).pack(side="left")
            ctk.CTkLabel(row, text=step, font=ctk.CTkFont(size=11, weight="bold"),
                          text_color=self.C["text_primary"], width=280).pack(side="left")
            ctk.CTkLabel(row, text=desc, font=ctk.CTkFont(size=11),
                          text_color=self.C["text_muted"]).pack(side="left")

        # ── Configuración de salida ───────────────────────────────
        out_frame = ctk.CTkFrame(self, fg_color=self.C["bg_panel"], corner_radius=10)
        out_frame.pack(fill="x", padx=30, pady=10)

        ctk.CTkLabel(out_frame, text="Archivo de destino",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=self.C["text_primary"]).pack(anchor="w", padx=20, pady=(16, 8))

        path_row = ctk.CTkFrame(out_frame, fg_color="transparent")
        path_row.pack(fill="x", padx=20, pady=(0, 16))

        self._path_var = ctk.StringVar(value="~/Desktop/ecu_backup_original.bin")
        ctk.CTkEntry(path_row, textvariable=self._path_var, width=400,
                     fg_color=self.C["bg_widget"]).pack(side="left")
        ctk.CTkButton(
            path_row, text="📂 Examinar", width=110,
            fg_color=self.C["bg_widget"], hover_color=self.C["accent_blue"],
            command=self._browse_path
        ).pack(side="left", padx=8)

        # Botón de inicio
        self._start_btn = ctk.CTkButton(
            self, text="▶ INICIAR VOLCADO",
            font=ctk.CTkFont(size=14, weight="bold"),
            width=200, height=44,
            fg_color=self.C["accent_blue"], hover_color="#3A7FD5",
            command=self._start_backup
        )
        self._start_btn.pack(anchor="w", padx=30, pady=(16, 0))

        # Progreso
        self._progress = ctk.CTkProgressBar(self, height=12, corner_radius=4)
        self._progress.pack(fill="x", padx=30, pady=(16, 4))
        self._progress.set(0)

        self._progress_label = ctk.CTkLabel(
            self, text="Esperando inicio de volcado...",
            font=ctk.CTkFont(size=11), text_color=self.C["text_muted"]
        )
        self._progress_label.pack(anchor="w", padx=30)

        # Log de actividad
        log_frame = ctk.CTkFrame(self, fg_color=self.C["bg_panel"], corner_radius=10)
        log_frame.pack(fill="both", expand=True, padx=30, pady=16)

        ctk.CTkLabel(log_frame, text="Log de Actividad",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=self.C["text_muted"]).pack(anchor="w", padx=16, pady=(12, 4))

        self._log = ctk.CTkTextbox(
            log_frame, font=ctk.CTkFont(family="Courier New", size=10),
            fg_color=self.C["bg_widget"], text_color=self.C["accent_green"]
        )
        self._log.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        self.controller.on("backup_progress", self._on_progress)
        self.controller.on("backup_complete", self._on_complete)
        self.controller.on("backup_error", self._on_error)

    def _browse_path(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".bin",
            filetypes=[("Binary files", "*.bin"), ("All files", "*.*")]
        )
        if path:
            self._path_var.set(path)

    def _start_backup(self):
        path = self._path_var.get()
        self._log_append(f"[INICIO] Iniciando volcado → {path}\n")
        self.controller.start_backup(path)

    def _on_progress(self, step="", pct=0, bytes_read=0, total=0, **kwargs):
        self.after(0, lambda: self._progress.set(pct / 100))
        label_text = f"{step} — {bytes_read // 1024} KB / {total // 1024} KB ({pct}%)"
        self.after(0, lambda: self._progress_label.configure(text=label_text))
        self.after(0, lambda: self._log_append(f"[{pct:>3}%] {step}\n"))

    def _on_complete(self, path="", size_kb=0, **kwargs):
        self.after(0, lambda: self._log_append(f"[OK] Volcado completado: {path} ({size_kb} KB)\n"))
        self.after(0, lambda: self._progress.set(1.0))

    def _on_error(self, error="", **kwargs):
        self.after(0, lambda: self._log_append(f"[ERROR] {error}\n"))

    def _log_append(self, text: str):
        self._log.insert("end", text)
        self._log.see("end")
