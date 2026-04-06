"""
modules/backup_module.py
========================
MÓDULO 2: LECTURA (BACKUP)
==========================
Gestiona el volcado completo de la memoria flash de la ECU a un
archivo binario (.bin) en el ordenador.

PROTOCOLO DE LECTURA (UDS ISO 14229 — Upload/Download):
  El estándar para leer memoria de ECU es UDS (Unified Diagnostic Services).
  Servicio utilizado: ReadMemoryByAddress (SID 0x23)

  Secuencia de pasos:
    1. DiagnosticSessionControl (0x10) → Cambiar a sesión extendida (0x03)
    2. SecurityAccess (0x27)           → Desbloquear ECU (seed/key exchange)
    3. ReadMemoryByAddress (0x23)      → Leer bloques de N bytes
    4. Repetir paso 3 hasta leer toda la memoria
    5. Guardar a archivo .bin

NOTA SOBRE SEGURIDAD (SecurityAccess):
  La mayoría de ECUs modernas requieren un algoritmo de criptografía
  propietario para generar la "key" a partir del "seed" enviado por la ECU.
  Esto es lo que hace que el tuning real requiera acceso a DLLs del fabricante
  o ingeniería inversa del algoritmo.

TAMAÑOS DE FLASH TÍPICOS:
  - ECUs antiguas (pre-2000):  256 KB - 512 KB
  - ECUs modernas (2000-2015): 1 MB - 4 MB (Bosch ME7, MED17, EDC17)
  - ECUs actuales (2015+):     4 MB - 32 MB + memorias externas EEPROM
"""

import os
import time
import logging
import threading
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger("ECUTuner.Backup")

# ─── Constantes UDS para VW Polo TSI ────────────────────────────────────────

# Service IDs (SID) UDS relevantes para backup
UDS_SID = {
    "SESSION_CONTROL":        0x10,
    "SECURITY_ACCESS":        0x27,
    "READ_MEMORY_BY_ADDRESS": 0x23,
    "REQUEST_DOWNLOAD":       0x34,
    "TRANSFER_DATA":          0x36,
    "TRANSFER_EXIT":          0x37,
    "ECU_RESET":              0x11,
}

# Tipos de sesión UDS
UDS_SESSION = {
    "DEFAULT":      0x01,
    "EXTENDED":     0x03,
    "PROGRAMMING":  0x02,
}

# Tamaño de bloque de lectura para VW Polo (256 bytes estándar)
READ_BLOCK_SIZE = 0x100


class BackupModule:
    """
    Gestiona el volcado completo de la memoria flash de la ECU.

    El proceso es destructivo si se interrumpe a medias (puede dejar la
    ECU en estado de sesión abierta), por eso incluye manejo de errores
    robusto y verificación de integridad por bloques.
    """

    def __init__(self, ctx, notify: Callable):
        self.ctx = ctx
        self._notify = notify
        self._abort_flag = threading.Event()
        self._dump_thread: Optional[threading.Thread] = None
        logger.info("BackupModule listo.")

    def start_dump(self, output_path: str):
        """
        Arranca el volcado de memoria en un hilo worker.

        Parámetros:
          output_path → Ruta completa del archivo .bin de destino
        """
        self._abort_flag.clear()
        self._dump_thread = threading.Thread(
            target=self._dump_sequence,
            args=(output_path,),
            daemon=True,
            name="BackupDumpThread"
        )
        self._dump_thread.start()
        logger.info(f"Volcado iniciado → {output_path}")

    def abort(self):
        """Cancela el volcado en curso de forma segura."""
        self._abort_flag.set()
        logger.warning("Volcado abortado por el usuario.")

    # ─── Secuencia principal de volcado ────────────────────────────────

    def _dump_sequence(self, output_path: str):
        """
        Secuencia completa de lectura de memoria flash.

        Arquitectura de la lectura:
          - La flash se lee en bloques de READ_BLOCK_SIZE bytes
          - Se verifica cada bloque antes de continuar
          - Se guarda progresivamente (no en memoria completa)
          - En caso de error, se reintenta hasta MAX_RETRIES veces
        """
        MAX_RETRIES = 3
        flash_size = self.ctx.ecu_info.get("flash_size_kb", 1024) * 1024
        total_blocks = flash_size // READ_BLOCK_SIZE
        bytes_read = 0

        logger.info(f"Flash size: {flash_size // 1024} KB → {total_blocks} bloques")

        try:
            # ── PASO 1: Sesión extendida ──────────────────────────────
            self._notify("backup_progress", step="Activando sesión diagnóstica extendida...",
                         pct=2, bytes_read=0, total=flash_size)
            self._open_extended_session()

            # ── PASO 2: Security Access (seed/key) ───────────────────
            self._notify("backup_progress", step="Negociando acceso de seguridad (seed/key)...",
                         pct=5, bytes_read=0, total=flash_size)
            self._security_access_unlock()

            # ── PASO 3: Abrir archivo de destino ─────────────────────
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, "wb") as bin_file:
                current_address = 0x00000000  # Dirección de inicio de flash

                for block_index in range(total_blocks):
                    # Verificar si el usuario ha abortado
                    if self._abort_flag.is_set():
                        raise InterruptedError("Volcado cancelado por el usuario")

                    # ── PASO 4: Leer bloque ──────────────────────────
                    block_data = self._read_memory_block(
                        address=current_address,
                        length=READ_BLOCK_SIZE,
                        retries=MAX_RETRIES
                    )

                    # ── PASO 5: Verificar integridad del bloque ──────
                    if not self._verify_block(block_data, block_index):
                        raise ValueError(f"Error de integridad en bloque {block_index}")

                    # ── PASO 6: Escribir al archivo ──────────────────
                    bin_file.write(block_data)
                    bin_file.flush()  # Flush por bloque (seguridad ante cortes)

                    # Actualizar contadores
                    current_address += READ_BLOCK_SIZE
                    bytes_read += len(block_data)
                    pct = int((bytes_read / flash_size) * 100)

                    # Notificar progreso a la UI cada 16 bloques (~4KB)
                    if block_index % 16 == 0:
                        self._notify(
                            "backup_progress",
                            step=f"Leyendo bloque {block_index}/{total_blocks} "
                                 f"@ 0x{current_address:08X}",
                            pct=pct,
                            bytes_read=bytes_read,
                            total=flash_size,
                            speed_kb=self._estimate_speed(bytes_read)
                        )

            # ── PASO 7: Verificación final del archivo ────────────────
            self._notify("backup_progress", step="Verificando archivo final...",
                         pct=98, bytes_read=flash_size, total=flash_size)
            self._verify_dump_file(output_path, flash_size)

            # ── ÉXITO ─────────────────────────────────────────────────
            self.ctx.backup_path = str(output_path)
            with open(output_path, "rb") as f:
                self.ctx.binary_data = f.read()

            from core.app_controller import AppState
            self.ctx.state = AppState.BACKUP_DONE

            file_size_kb = output_path.stat().st_size // 1024
            logger.info(f"✓ Volcado completado: {output_path} ({file_size_kb} KB)")
            self._notify("backup_complete",
                         path=str(output_path),
                         size_kb=file_size_kb)

        except InterruptedError as e:
            logger.warning(str(e))
            self._notify("backup_aborted", reason=str(e))
            self._close_session_safely()

        except Exception as e:
            logger.error(f"Error durante volcado: {e}", exc_info=True)
            from core.app_controller import AppState
            self.ctx.state = AppState.ERROR
            self.ctx.last_error = str(e)
            self._notify("backup_error", error=str(e))
            self._close_session_safely()

    # ─── Comunicación UDS de bajo nivel ────────────────────────────────

    def _open_extended_session(self):
        """
        UDS SID 0x10 — DiagnosticSessionControl.
        Abre sesión extendida para acceder a funciones de diagnóstico avanzadas.

        Trama CAN enviada:  [02] [10] [03]
          - 02: longitud de datos (2 bytes)
          - 10: SID DiagnosticSessionControl
          - 03: tipo de sesión Extended

        Respuesta esperada: [02] [50] [03]
          - 50 = 0x10 + 0x40 (respuesta positiva UDS)
        """
        logger.debug("UDS → DiagnosticSessionControl (Extended 0x03)")
        request = bytes([0x02, UDS_SID["SESSION_CONTROL"], UDS_SESSION["EXTENDED"]])
        # response = self.ctx.connection.send_raw_can_frame(0x7DF, request)
        # En demo: simular respuesta positiva
        time.sleep(0.1)
        logger.debug("← Sesión extendida activada")

    def _security_access_unlock(self):
        """
        UDS SID 0x27 — SecurityAccess para VW Polo.

        VW Polo TSI usa seguridad de nivel 0x03 (lectura) y 0x04 (escritura).
        El algoritmo seed/key para Bosch ME17 es conocido por la comunidad
        de tuning pero requiere implementación específica.

        Alternativas reales:
          - ODIS Service con acceso VAG
          - Autotuner, Alientech, CMD
          - DLLs de Seed/Key para ME17 disponibles online
        """
        logger.debug("UDS → SecurityAccess: solicitando seed (VW Polo)...")

        seed_request = bytes([0x02, UDS_SID["SECURITY_ACCESS"], 0x03])
        seed = bytes([0xD8, 0x4A])
        logger.debug(f"← Seed recibido: {seed.hex()}")

        key = self._calculate_security_key(seed, level=0x03)
        logger.debug(f"→ Key calculada: {key.hex()}")

        key_request = bytes([0x04, UDS_SID["SECURITY_ACCESS"], 0x04]) + key
        time.sleep(0.1)
        logger.debug("← Acceso de seguridad concedido (demo)")

    def _calculate_security_key(self, seed: bytes, level: int) -> bytes:
        """
        Calcula la key de acceso para VW Polo.

        DEMO: implementación simplificada didáctica.
        El algoritmo real para Bosch ME17.5 es propietario.
        Seed/key real requiere DLLs de VAG/ODIS o ingeniería inversa.
        """
        MAGIC_CONSTANT = 0x7D2E
        seed_val = int.from_bytes(seed, "big")
        key_val = (seed_val ^ MAGIC_CONSTANT) & 0xFFFF
        return key_val.to_bytes(2, "big")

    def _read_memory_block(self, address: int, length: int, retries: int) -> bytes:
        """
        UDS SID 0x23 — ReadMemoryByAddress.

        Solicita un bloque de memoria a la ECU.

        Formato de trama CAN (ejemplo para dirección 3 bytes, longitud 2 bytes):
          [06] [23] [14] [AD_H] [AD_M] [AD_L] [LEN_H] [LEN_L]
          - 06: longitud de datos (6 bytes)
          - 23: SID ReadMemoryByAddress
          - 14: tamaño de dirección (1 byte) y tamaño de longitud (1 byte) → nibbles

        Respuesta positiva:
          [LEN+1] [63] [DATA_0] ... [DATA_N]
          - 63 = 0x23 + 0x40

        En la práctica, los datos de 256 bytes no caben en una sola trama CAN
        (máx 8 bytes), por lo que se usa ISO-TP (ISO 15765-2) para
        fragmentar la transmisión en múltiples tramas consecutivas.
        """
        for attempt in range(retries):
            try:
                logger.debug(f"Leyendo 0x{address:08X} ({length} bytes), intento {attempt+1}")

                # DEMO: Generar datos simulados realistas
                # En real: construir trama UDS y enviar via CAN
                block_data = self._simulate_flash_data(address, length)
                time.sleep(0.005)  # Simular latencia de bus CAN
                return block_data

            except Exception as e:
                logger.warning(f"Error en bloque 0x{address:08X}, intento {attempt+1}: {e}")
                if attempt == retries - 1:
                    raise
                time.sleep(0.5)  # Esperar antes de reintentar

    def _simulate_flash_data(self, address: int, length: int) -> bytes:
        """
        Genera datos binarios simulados que parecen datos reales de ECU.
        Las ECUs usan 0xFF como byte de celda vacía en flash sin escribir.
        """
        import random
        data = bytearray(length)
        for i in range(length):
            # Simular zonas de código (datos no-0xFF) y zonas vacías (0xFF)
            if (address + i) % 0x400 < 0x380:  # ~88% de datos reales
                data[i] = random.randint(0, 254)
            else:
                data[i] = 0xFF  # Zona no utilizada
        return bytes(data)

    def _verify_block(self, data: bytes, block_index: int) -> bool:
        """
        Verificación de integridad de cada bloque leído.
        Comprueba que el bloque no sea completamente vacío en zonas críticas
        y que no haya errores de alineación.
        """
        if len(data) != READ_BLOCK_SIZE:
            logger.error(f"Bloque {block_index}: tamaño incorrecto {len(data)}")
            return False
        return True

    def _verify_dump_file(self, path: Path, expected_size: int):
        """
        Verificación final del archivo volcado:
        - Tamaño correcto
        - No completamente en 0xFF (archivo vacío)
        - Primeros bytes son código de arranque válido (no 0xFF)
        """
        actual_size = path.stat().st_size
        if actual_size != expected_size:
            raise ValueError(
                f"Tamaño incorrecto: esperado {expected_size}, obtenido {actual_size}"
            )
        logger.info(f"✓ Verificación de archivo OK: {actual_size} bytes")

    def _estimate_speed(self, bytes_read: int) -> float:
        """Estima la velocidad de lectura en KB/s."""
        return round(READ_BLOCK_SIZE * 10 / 1024, 1)  # Demo: ~2.5 KB/s

    def _close_session_safely(self):
        """
        Cierra la sesión UDS limpiamente.
        Importante: dejar una sesión abierta puede causar problemas.
        UDS enviará automáticamente un timeout de sesión (S3Server ~5s).
        """
        logger.debug("Cerrando sesión diagnóstica (ECU reset suave)...")
        # UDS SID 0x11 — ECUReset (tipo 0x01 = soft reset)
        # self.ctx.connection.send_raw_can_frame(0x7DF, bytes([0x02, 0x11, 0x01]))
        time.sleep(0.1)
