"""
ECU Tuner - Aplicación Didáctica de Gestión y Reprogramación de ECU
====================================================================
Punto de entrada principal de la aplicación.

ARQUITECTURA: MVC (Model-View-Controller)
  - Model   → core/ + modules/  (lógica de negocio, protocolo, datos)
  - View    → ui/               (interfaces gráficas CustomTkinter)
  - Controller → cada módulo actúa como controlador de su dominio

STACK TECNOLÓGICO:
  - Python 3.10+
  - CustomTkinter  → GUI moderna estilo dark/pro
  - pyserial       → Comunicación serial (OBD-II)
  - python-can     → CAN bus (opcional, hardware real)
  - numpy          → Manipulación de tablas de mapas
  - matplotlib     → Visualización 3D de mapas de motor
"""

import sys
import os
import logging
from pathlib import Path

# ─── Configuración de paths del proyecto ───────────────────────────────────
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# ─── Logging centralizado ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    # Usar ASCII para evitar problemas de codificación en cmd/PowerShell
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.FileHandler(PROJECT_ROOT / "data" / "ecu_tuner.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("ECUTuner.Main")


def main():
    """
    Bootstrap de la aplicación.
    Orden de inicialización:
      1. Verificar dependencias del sistema
      2. Cargar configuración persistente
      3. Inicializar el AppController central
      4. Lanzar la ventana principal (MainWindow)
      5. Arrancar el event loop de Tkinter
    """
    logger.info("═══════════════════════════════════════")
    logger.info("  ECU Tuner v1.0 — Iniciando sistema  ")
    logger.info("═══════════════════════════════════════")

    # 1. Verificar dependencias antes de importar la GUI
    _check_dependencies()

    # 2. Importar y lanzar la GUI (diferido para evitar errores de import)
    from ui.main_window import MainWindow
    from core.app_controller import AppController

    # 3. Crear el controlador central (Model side)
    controller = AppController()

    # 4. Crear y arrancar la ventana principal (View side)
    app = MainWindow(controller=controller)
    logger.info("Ventana principal inicializada. Arrancando event loop...")
    app.mainloop()

    logger.info("Aplicación cerrada correctamente.")


def _check_dependencies():
    """
    Verifica que las librerías críticas estén instaladas.
    En producción usaríamos un requirements.txt y un instalador.
    """
    required = {
        "customtkinter": "pip install customtkinter",
        "serial":        "pip install pyserial",
        "numpy":         "pip install numpy",
        "matplotlib":    "pip install matplotlib",
    }
    missing = []
    for module, install_cmd in required.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(f"  - {module} → {install_cmd}")

    if missing:
        logger.error("Dependencias faltantes:\n" + "\n".join(missing))
        print("\n⚠️  Dependencias faltantes. Ejecuta:\n" + "\n".join(missing))
        sys.exit(1)

    logger.info("OK: Todas las dependencias verificadas.")


if __name__ == "__main__":
    main()
