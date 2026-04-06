import tkinter as tk
import customtkinter as ctk

class DiagnosticPanel(ctk.CTkFrame):
    def __init__(self, master, controller=None, colors=None, **kwargs):
        super().__init__(master, **kwargs)
        self.controller = controller
        self.colors = colors
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        title = ctk.CTkLabel(self, text="Diagnóstico del Vehículo", font=("Arial", 12, "bold"))
        title.grid(row=0, column=0, columnspan=2, sticky="w", pady=(6, 6))

        self.read_btn = ctk.CTkButton(self, text="Leer DTCs (Puntos)", command=self._read_dtcs)
        self.read_btn.grid(row=1, column=0, padx=5, pady=6, sticky="w")

        self.clear_btn = ctk.CTkButton(self, text="Borrar DTCs", command=self._clear_dtcs)
        self.clear_btn.grid(row=1, column=1, padx=5, pady=6, sticky="e")

        # Lista de DTCs (simulada)
        self._dtc_listbox = tk.Listbox(self, height=8, width=60)
        self._dtc_listbox.grid(row=2, column=0, columnspan=2, padx=6, pady=6, sticky="nsew")

        # Live data placeholder
        self.live_label = ctk.CTkLabel(self, text="Live: -", text_color=self.colors.get("text_muted") if self.colors else "#8B949E")
        self.live_label.grid(row=3, column=0, columnspan=2, sticky="w", padx=6, pady=6)

        # Suscripción a actualizaciones de diagnóstico (opcional)
        if self.controller and hasattr(self.controller, "on"):
            self.controller.on("dtc_update", self._on_dtcs_changed)
            self.controller.on("live_data_update", self._on_live_update)

    def _read_dtcs(self):
        if self.controller and hasattr(self.controller, "read_dtcs"):
            self.controller.read_dtcs()
        else:
            self._update_list(["P0000 - Simulado"])

    def _clear_dtcs(self):
        if self.controller and hasattr(self.controller, "clear_dtcs"):
            self.controller.clear_dtcs()
        self._update_list([])

    def _on_dtcs_changed(self, dtcs=None, **kwargs):
        self._update_list(dtcs or [])

    def _update_list(self, dtcs):
        self._dtc_listbox.delete(0, tk.END)
        for dtc in (dtcs or []):
            self._dtc_listbox.insert(tk.END, dtc)

    def _on_live_update(self, data=None, **kwargs):
        if isinstance(data, dict):
            self.live_label.configure(text=f"Live: rpm={data.get('rpm','')}, T={data.get('coolant_temp','')}")

    # Public API para AppController
    def update_dtcs(self, dtcs):
        self._update_list(dtcs or [])
