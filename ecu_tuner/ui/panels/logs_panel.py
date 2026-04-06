"""
ui/panels/logs_panel.py
========================
Panel de Visualización de Logs en tiempo real.

Muestra los mensajes de log de la aplicación dentro de la UI,
con filtrado por nivel, búsqueda de texto y exportación.

Funciona como observer del sistema de logging de Python,
capturando todos los mensajes via un Handler personalizado.
"""

import customtkinter as ctk
import tkinter as tk
import logging
import queue
import os
from pathlib import Path
from tkinter import filedialog
from datetime import datetime

logger = logging.getLogger("ECUTuner.LogsPanel")


# ─── Handler de logging que redirige mensajes a la UI ──────────────────────

class UILogHandler(logging.Handler):
    """
    Handler de logging que encola mensajes para la UI.
    Thread-safe: usa queue.Queue para comunicar desde workers a la UI.
    """

    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self._queue = log_queue
        self.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
            datefmt="%H:%M:%S"
        ))

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            self._queue.put_nowait((record.levelno, msg))
        except Exception:
            pass   # No propagar errores dentro del handler


# ─── Colores por nivel de log ───────────────────────────────────────────────

LOG_LEVEL_COLORS = {
    logging.DEBUG:    "#8B949E",   # gris
    logging.INFO:     "#58A6FF",   # azul
    logging.WARNING:  "#E3B341",   # amarillo
    logging.ERROR:    "#F78166",   # naranja-rojo
    logging.CRITICAL: "#FF0000",   # rojo brillante
}

LOG_LEVEL_NAMES = {
    logging.DEBUG:    "DEBUG",
    logging.INFO:     "INFO",
    logging.WARNING:  "WARN",
    logging.ERROR:    "ERROR",
    logging.CRITICAL: "CRIT",
}


class LogsPanel(ctk.CTkFrame):
    """
    Panel de logs en tiempo real con filtrado y búsqueda.
    Se registra como handler en el logger raíz de la aplicación.
    """

    MAX_LINES = 2000   # Máximo de líneas en el buffer

    def __init__(self, parent, controller=None, colors=None, **kwargs):
        if colors is None:
            colors = {}
        super().__init__(parent, fg_color=colors.get("bg_dark", "#0D1117"), corner_radius=0)
        self.controller = controller
        self.C = colors
        self._log_queue: queue.Queue = queue.Queue(maxsize=500)
        self._min_level = logging.DEBUG
        self._filter_text = ""
        self._paused = False
        self._line_count = 0
        self._build_ui()
        self._install_log_handler()
        self._start_queue_poll()

    # ─── Helpers de color ───────────────────────────────────────────────

    def _c(self, key: str, default: str = "#888") -> str:
        return self.C.get(key, default)

    # ─── Construcción de UI ─────────────────────────────────────────────

    def _build_ui(self):
        self._build_header()
        self._build_toolbar()
        self._build_log_area()
        self._build_status_bar()

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color=self._c("bg_panel"), corner_radius=0)
        header.pack(fill="x")
        inner = ctk.CTkFrame(header, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(inner, text="Logs del Sistema",
                     font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=self._c("text_primary")).pack(side="left")
        ctk.CTkLabel(inner, text=" — Monitor de eventos en tiempo real",
                     font=ctk.CTkFont(size=12),
                     text_color=self._c("text_muted")).pack(side="left")

        self._line_count_label = ctk.CTkLabel(
            inner, text="0 lineas",
            font=ctk.CTkFont(size=11),
            text_color=self._c("text_muted"))
        self._line_count_label.pack(side="right")

    def _build_toolbar(self):
        toolbar = ctk.CTkFrame(self, fg_color=self._c("bg_panel"), corner_radius=0)
        toolbar.pack(fill="x")
        inner = ctk.CTkFrame(toolbar, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=8)

        # Filtro por nivel
        ctk.CTkLabel(inner, text="Nivel:",
                     font=ctk.CTkFont(size=11),
                     text_color=self._c("text_muted")).pack(side="left", padx=(0, 6))

        self._level_var = tk.StringVar(value="DEBUG")
        level_combo = ctk.CTkComboBox(
            inner,
            values=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            variable=self._level_var,
            width=100,
            fg_color=self._c("bg_widget"),
            border_color=self._c("border"),
            text_color=self._c("text_primary"),
            command=self._on_level_change
        )
        level_combo.pack(side="left", padx=(0, 16))

        # Búsqueda de texto
        ctk.CTkLabel(inner, text="Filtrar:",
                     font=ctk.CTkFont(size=11),
                     text_color=self._c("text_muted")).pack(side="left", padx=(0, 6))

        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", self._on_filter_change)
        ctk.CTkEntry(inner, textvariable=self._search_var,
                     width=200, placeholder_text="Buscar en logs...",
                     fg_color=self._c("bg_widget"),
                     border_color=self._c("border"),
                     text_color=self._c("text_primary")
                     ).pack(side="left", padx=(0, 16))

        # Botones de acción
        self._pause_btn = ctk.CTkButton(
            inner, text="Pausar", width=80, height=28,
            fg_color=self._c("bg_widget"),
            font=ctk.CTkFont(size=11),
            command=self._toggle_pause)
        self._pause_btn.pack(side="left", padx=(0, 6))

        ctk.CTkButton(inner, text="Limpiar", width=75, height=28,
                      fg_color=self._c("bg_widget"),
                      font=ctk.CTkFont(size=11),
                      command=self._clear_logs).pack(side="left", padx=(0, 6))

        ctk.CTkButton(inner, text="Exportar", width=80, height=28,
                      fg_color=self._c("accent_blue"), hover_color="#3A7FD5",
                      font=ctk.CTkFont(size=11),
                      command=self._export_logs).pack(side="left", padx=(0, 6))

        ctk.CTkButton(inner, text="Scroll Final", width=90, height=28,
                      fg_color=self._c("bg_widget"),
                      font=ctk.CTkFont(size=11),
                      command=self._scroll_to_end).pack(side="right")

    def _build_log_area(self):
        log_frame = ctk.CTkFrame(self, fg_color=self._c("bg_panel"), corner_radius=0)
        log_frame.pack(fill="both", expand=True, padx=0, pady=0)

        self._log_text = ctk.CTkTextbox(
            log_frame,
            font=ctk.CTkFont(family="Courier New", size=11),
            fg_color="#0A0E12",    # negro profundo para logs
            text_color=self._c("text_primary"),
            wrap="none",
            state="disabled"
        )
        self._log_text.pack(fill="both", expand=True, padx=8, pady=8)

        # Configurar tags de color por nivel en el widget subyacente
        tw = self._log_text._textbox
        for level, color in LOG_LEVEL_COLORS.items():
            level_name = LOG_LEVEL_NAMES[level]
            tw.tag_configure(f"level_{level_name}", foreground=color)

    def _build_status_bar(self):
        status = ctk.CTkFrame(self, fg_color=self._c("bg_panel"),
                              corner_radius=0, height=26)
        status.pack(fill="x")
        status.pack_propagate(False)

        self._status_label = ctk.CTkLabel(
            status, text="Capturando logs de todos los modulos...",
            font=ctk.CTkFont(size=10),
            text_color=self._c("text_muted"))
        self._status_label.pack(side="left", padx=12)

    # ─── Sistema de logging ──────────────────────────────────────────────

    def _install_log_handler(self):
        """Instala el handler de UI en el logger raíz de ECUTuner."""
        self._ui_handler = UILogHandler(self._log_queue)
        root_logger = logging.getLogger("ECUTuner")
        root_logger.addHandler(self._ui_handler)
        logger.info("LogsPanel: handler de UI instalado correctamente.")

    def _start_queue_poll(self):
        """Inicia el polling de la queue de logs (cada 100ms)."""
        self._poll_logs()

    def _poll_logs(self):
        """Lee mensajes de la queue y los añade al widget."""
        try:
            count = 0
            while not self._log_queue.empty() and count < 50:
                level, msg = self._log_queue.get_nowait()
                if not self._paused:
                    self._append_log_line(level, msg)
                count += 1
        except Exception:
            pass
        finally:
            self.after(100, self._poll_logs)

    def _append_log_line(self, level: int, msg: str):
        """Añade una línea de log al widget con color apropiado."""
        # Aplicar filtro de nivel
        if level < self._min_level:
            return

        # Aplicar filtro de texto
        if self._filter_text and self._filter_text.lower() not in msg.lower():
            return

        # Limitar buffer
        if self._line_count >= self.MAX_LINES:
            self._log_text.configure(state="normal")
            self._log_text._textbox.delete("1.0", "50.0")
            self._line_count -= 49
            self._log_text.configure(state="disabled")

        level_name = LOG_LEVEL_NAMES.get(level, "INFO")
        color = LOG_LEVEL_COLORS.get(level, self._c("text_muted"))

        self._log_text.configure(state="normal")
        self._log_text._textbox.insert("end", msg + "\n", f"level_{level_name}")
        self._log_text.configure(state="disabled")

        self._line_count += 1
        self._line_count_label.configure(text=f"{self._line_count} lineas")

        # Auto-scroll al final
        self._scroll_to_end()

    def _scroll_to_end(self):
        self._log_text._textbox.see("end")

    # ─── Controles ──────────────────────────────────────────────────────

    def _on_level_change(self, level_name: str):
        levels = {
            "DEBUG": logging.DEBUG, "INFO": logging.INFO,
            "WARNING": logging.WARNING, "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL
        }
        self._min_level = levels.get(level_name, logging.DEBUG)

    def _on_filter_change(self, *args):
        self._filter_text = self._search_var.get()

    def _toggle_pause(self):
        self._paused = not self._paused
        if self._paused:
            self._pause_btn.configure(text="Reanudar",
                                      fg_color=self._c("accent_yellow"),
                                      text_color="#0D1117")
            self._status_label.configure(text="Captura PAUSADA")
        else:
            self._pause_btn.configure(text="Pausar",
                                      fg_color=self._c("bg_widget"),
                                      text_color=self._c("text_primary"))
            self._status_label.configure(text="Capturando logs de todos los modulos...")

    def _clear_logs(self):
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.configure(state="disabled")
        self._line_count = 0
        self._line_count_label.configure(text="0 lineas")

    def _export_logs(self):
        """Exporta los logs actuales a un archivo .txt."""
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Texto", "*.txt"), ("Log", "*.log")],
            initialfile=f"ecu_tuner_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )
        if not path:
            return
        try:
            content = self._log_text.get("1.0", "end")
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            self._status_label.configure(
                text=f"Exportado: {Path(path).name}",
                text_color=self._c("accent_green"))
            logger.info(f"Logs exportados a: {path}")
        except Exception as e:
            logger.error(f"Error exportando logs: {e}")
