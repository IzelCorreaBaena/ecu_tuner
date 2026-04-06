import tkinter as tk
import customtkinter as ctk

class VCDSPanel(ctk.CTkFrame):
    def __init__(self, master, controller=None, colors=None, **kwargs):
        super().__init__(master, **kwargs)
        self.controller = controller
        self.colors = colors
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)

        title = ctk.CTkLabel(self, text="VCDS Profiles", font=("Arial", 12, "bold"))
        title.grid(row=0, column=0, columnspan=2, sticky="w", pady=(6, 6))

        self.load_btn = ctk.CTkButton(self, text="Cargar perfiles", command=self._load_profiles)
        self.load_btn.grid(row=1, column=0, padx=5, pady=4, sticky="w")

        self.apply_btn = ctk.CTkButton(self, text="Aplicar perfil", command=self._apply_profile)
        self.apply_btn.grid(row=1, column=1, padx=5, pady=4, sticky="e")

        # Combobox de perfiles
        self.profile_var = tk.StringVar(self)
        # Algunas versiones de CTk usan CTkComboBox; si no, fallback a OptionMenu
        try:
            self.combo = ctk.CTkComboBox(self, values=[], variable=self.profile_var)
        except Exception:
            self.combo = tk.OptionMenu(self, self.profile_var, "")
        self.combo.grid(row=2, column=0, columnspan=2, padx=5, pady=4, sticky="ew")

        self.status = ctk.CTkLabel(self, text="")
        self.status.grid(row=3, column=0, columnspan=2, sticky="w", padx=5, pady=(0,6))

    def _load_profiles(self):
        path = "data/configs/vcds_profiles.json"
        if self.controller and hasattr(self.controller, "load_vcds_profiles"):
            self.controller.load_vcds_profiles(path)
            profiles = getattr(self.controller, "_vcds_profiles", [])
            names = [p.get("name", "") for p in profiles]
            # No forzamos la actualización dinámica de valores en CTkComboBox para compatibilidad
            if isinstance(self.combo, ctk.CTkComboBox):
                pass
            # Selección por defecto si hay perfiles
            if names:
                self.profile_var.set(names[0])
            self.status.configure(text=f"Cargados {len(names)} perfiles")
        else:
            self.status.configure(text="Cargar perfiles no soportado")

    def _apply_profile(self):
        name = self.profile_var.get()
        if not name:
            self.status.configure(text="Selecciona un perfil")
            return
        if self.controller and hasattr(self.controller, "apply_vcds_profile_by_name"):
            ok = self.controller.apply_vcds_profile_by_name(name)
            self.status.configure(text="Perfil aplicado" if ok else "Error al aplicar perfil")
        else:
            self.status.configure(text="Función no disponible")
