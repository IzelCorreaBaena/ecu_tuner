"""
Módulo de Diagnóstico (Módulo 1)
Simula lectura y borrado de DTCs (códigos de fallo) y genera datos de diagnóstico en vivo.
Este código está pensado para entorno didáctico y pruebas sin hardware.
"""
import logging
import threading
import time
from typing import Callable, List, Optional

logger = logging.getLogger("ECUTuner.Diagnostic")


class DiagnosticModule:
    def __init__(self, ctx, notify: Callable):
        self.ctx = ctx
        self._notify = notify
        self._stop_event = threading.Event()
        self._dtc_codes: List[str] = []
        self._thread: Optional[threading.Thread] = None
        logger.info("DiagnosticModule listo.")

    def read_dtcs(self) -> List[str]:
        """Devuelve una lista simulada de DTCs para la demostración."""
        self._dtc_codes = [
            "P0300 - Random/Multiple Cylinder Misfire Detected",
            "P0420 - Catalyst System Efficiency Below Threshold",
            "P0171 - System Too Lean (Bank 1)",
        ]
        self._notify("dtc_update", dtcs=self._dtc_codes)
        logger.info("Lectura de DTCs simulada: %s", self._dtc_codes)
        return self._dtc_codes

    def clear_dtcs(self) -> None:
        self._dtc_codes = []
        self._notify("dtc_update", dtcs=self._dtc_codes)
        logger.info("DTCs limpiados (simulado)")

    def start_live(self):
        """Inicia un loop de live data (simulado)"""
        self._stop_event.clear()
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._live_loop, daemon=True, name="DiagnosticLive")
        self._thread.start()

    def _live_loop(self):
        counter = 0
        while not self._stop_event.is_set():
            live = {
                "rpm": 800 + (counter % 3200),
                "coolant_temp": 85 + (counter % 10),
                "throttle_pos": (counter % 100) / 2.0,
            }
            self._notify("live_data_update", data=live)
            counter += 1
            time.sleep(0.5)

    def stop(self):
        self._stop_event.set()
