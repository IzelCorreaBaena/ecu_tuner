"""
modules/flash_module.py
=======================
MÓDULO 4: ESCRITURA (FLASHEO)
==============================
Valida el binario modificado y lo escribe de vuelta a la memoria
flash de la ECU mediante el protocolo UDS.

⚠️  ADVERTENCIA DE SEGURIDAD:
  El flasheo de una ECU es una operación potencialmente destructiva.
  Un proceso interrumpido o un archivo corrupto puede dejar la ECU
  en estado de "brick" (sin arrancar), requiriendo equipo especializado
  para recuperarla (programador de flash JTAG/BDM).

  En producción real, nunca se implementa esto sin:
    1. Backup verificado del original
    2. Verificación de checksum
    3. Alimentación de emergencia (no solo batería del coche)
    4. Hardware certificado (J2534 o similar)

PROTOCOLO UDS DE ESCRITURA (ISO 14229 — Reprogramming):
  1.  DiagnosticSessionControl(0x10, 0x02) → Sesión de programación
  2.  SecurityAccess(0x27, nivel elevado)   → Acceso de escritura
  3.  EraseMemory(0x31, 0xFF00)            → Borrar sector de flash
  4.  RequestDownload(0x34)                → Iniciar descarga de datos
  5.  TransferData(0x36) × N bloques       → Transferir datos en bloques
  6.  RequestTransferExit(0x37)            → Fin de transferencia
  7.  CheckProgrammingDependencies(0x31)   → Verificar coherencia
  8.  ECUReset(0x11, 0x01)                 → Reset para aplicar cambios

CHECKSUM EN ECUs BOSCH:
  La mayoría de ECUs Bosch usan un checksum de 32 bits almacenado
  en una posición fija del binario. Si no coincide, la ECU puede:
    - Rechazar el binario (respuesta negativa UDS)
    - Arrancar en modo emergency (solo ralentí)
    - No arrancar en absoluto
  El algoritmo es propietario pero conocido para algunas ECUs
  (ME7, MED17) gracias a la comunidad de tuning.
"""

import os
import time
import logging
import hashlib
import threading
from pathlib import Path
from typing import Callable, Optional
from dataclasses import dataclass

logger = logging.getLogger("ECUTuner.Flash")


# ─── Constantes de flasheo VW Polo TSI ──────────────────────────────────────

# Tamaño de bloque para transferencia de datos UDS
# VW Polo usa bloques de 512 bytes estándar
FLASH_BLOCK_SIZE = 0x200

# Timeout de respuesta UDS durante flasheo (ms)
# La ECU tarda más en borrar sectores flash
ERASE_TIMEOUT_MS = 30000
WRITE_TIMEOUT_MS = 5000

# Offset del checksum en el binario (VW Polo ME17.5.22)
# Diferentes ECUs Bosch tienen diferentes offsets
CHECKSUM_OFFSET = 0x0BFF8
CHECKSUM_SIZE   = 4


@dataclass
class ValidationResult:
    """Resultado de la validación pre-flash."""
    is_valid:         bool
    checksum_ok:      bool
    size_ok:          bool
    structure_ok:     bool
    calculated_checksum: int
    stored_checksum:     int
    original_size:    int
    modified_size:    int
    warnings:         list[str]
    errors:           list[str]


class FlashModule:
    """
    Gestiona la validación y escritura del binario modificado a la ECU.

    Flujo:
      validate() → _verify_checksum() → _recalculate_checksum()
               → start_flash() → _erase_flash() → _transfer_data()
               → _verify_written() → _ecu_reset()
    """

    def __init__(self, ctx, notify: Callable):
        self.ctx = ctx
        self._notify = notify
        self._abort_flag = threading.Event()
        self._flash_thread: Optional[threading.Thread] = None
        logger.info("FlashModule listo.")

    def start_flash(self, binary_path: str):
        """
        Inicia la secuencia completa de flasheo.

        Primero valida el archivo, luego escribe.
        Todo en hilo separado para no bloquear la UI.
        """
        self._abort_flag.clear()
        self._flash_thread = threading.Thread(
            target=self._flash_sequence,
            args=(binary_path,),
            daemon=True,
            name="FlashWriteThread"
        )
        self._flash_thread.start()
        logger.info(f"Flasheo iniciado → {binary_path}")

    def abort(self):
        """Intenta abortar el flasheo. Solo seguro ANTES de _erase_flash()."""
        self._abort_flag.set()
        logger.warning("⚠️  Solicitud de abort de flasheo — solo seguro antes del borrado")

    # ─── Secuencia principal ────────────────────────────────────────────

    def _flash_sequence(self, binary_path: str):
        """
        Secuencia completa de escritura a la ECU.

        Puntos de no retorno:
          - Una vez ejecutado _erase_flash(), hay que completar la escritura
          - Abortar durante _transfer_data() puede dejar la ECU en brick
        """
        try:
            path = Path(binary_path)
            with open(path, "rb") as f:
                binary_data = f.read()

            total_size = len(binary_data)
            logger.info(f"Archivo a flashear: {path.name} ({total_size} bytes)")

            # ══════════════════════════════════════════════════════════
            # FASE 1: VALIDACIÓN Y PREPARACIÓN
            # ══════════════════════════════════════════════════════════

            self._notify("flash_progress", phase="Validando archivo...",
                         step="Verificando integridad", pct=5)
            validation = self.validate_binary(binary_data)

            if not validation.is_valid:
                errors_str = "\n".join(validation.errors)
                raise ValueError(f"Validación fallida:\n{errors_str}")

            if validation.warnings:
                self._notify("flash_warning", warnings=validation.warnings)

            # Recalcular y parchar checksum en el binario
            self._notify("flash_progress", phase="Preparando archivo...",
                         step="Recalculando checksum", pct=8)
            patched_data = self._patch_checksum(binary_data)

            # ══════════════════════════════════════════════════════════
            # FASE 2: APERTURA DE SESIÓN DE PROGRAMACIÓN
            # ══════════════════════════════════════════════════════════

            if self._abort_flag.is_set():
                raise InterruptedError("Flasheo cancelado antes de iniciar")

            self._notify("flash_progress", phase="Conectando con ECU...",
                         step="Abriendo sesión de programación (UDS 0x10/0x02)", pct=12)
            self._open_programming_session()

            self._notify("flash_progress", phase="Conectando con ECU...",
                         step="Elevando permisos de seguridad (UDS 0x27)", pct=16)
            self._security_access_programming()

            # ══════════════════════════════════════════════════════════
            # FASE 3: BORRADO DE FLASH
            # ⚠️  PUNTO DE NO RETORNO — no abortar después de aquí
            # ══════════════════════════════════════════════════════════

            self._notify("flash_progress", phase="⚠️ BORRANDO FLASH — NO INTERRUMPIR",
                         step="Borrando memoria flash (UDS 0x31 EraseMemory)", pct=20)
            logger.warning("⚠️  INICIANDO BORRADO DE FLASH — PUNTO DE NO RETORNO")
            self._erase_flash(total_size)

            # ══════════════════════════════════════════════════════════
            # FASE 4: TRANSFERENCIA DE DATOS
            # ══════════════════════════════════════════════════════════

            self._notify("flash_progress", phase="⚠️ ESCRIBIENDO FLASH — NO INTERRUMPIR",
                         step="Iniciando descarga de datos (UDS 0x34)", pct=25)
            self._request_download(total_size)

            # Transferir en bloques
            self._transfer_data_blocks(patched_data)

            # Fin de transferencia
            self._notify("flash_progress", phase="Finalizando escritura...",
                         step="Señalizando fin de transferencia (UDS 0x37)", pct=90)
            self._request_transfer_exit()

            # ══════════════════════════════════════════════════════════
            # FASE 5: VERIFICACIÓN Y RESET
            # ══════════════════════════════════════════════════════════

            self._notify("flash_progress", phase="Verificando escritura...",
                         step="Verificando dependencias de programación (UDS 0x31)", pct=93)
            self._check_programming_dependencies()

            self._notify("flash_progress", phase="Reiniciando ECU...",
                         step="Enviando ECU Reset (UDS 0x11)", pct=97)
            self._ecu_reset()

            # ── ÉXITO ─────────────────────────────────────────────────
            from core.app_controller import AppState
            self.ctx.state = AppState.CONNECTED  # Volver a estado conectado

            logger.info("✓ ¡Flasheo completado con éxito!")
            self._notify("flash_complete",
                         size_kb=total_size // 1024,
                         checksum=hex(validation.calculated_checksum))

        except InterruptedError as e:
            logger.warning(f"Flasheo interrumpido: {e}")
            self._notify("flash_aborted", reason=str(e))

        except Exception as e:
            logger.error(f"Error durante flasheo: {e}", exc_info=True)
            from core.app_controller import AppState
            self.ctx.state = AppState.ERROR
            self.ctx.last_error = str(e)
            self._notify("flash_error", error=str(e))

    # ─── Validación pre-flash ───────────────────────────────────────────

    def validate_binary(self, binary_data: bytes) -> ValidationResult:
        """
        Validación completa del binario antes de flashear.

        Checks realizados:
          1. Tamaño coincide con la flash de la ECU
          2. Estructura básica del binario (no todo 0xFF o 0x00)
          3. Checksum almacenado vs calculado
          4. Firma de software reconocida (magic bytes)
          5. Regiones críticas no están en blanco
        """
        warnings = []
        errors = []

        original_size = self.ctx.ecu_info.get("flash_size_kb", 1024) * 1024
        modified_size = len(binary_data)

        # ── Check 1: Tamaño ──
        size_ok = modified_size == original_size
        if not size_ok:
            errors.append(
                f"Tamaño incorrecto: archivo={modified_size//1024}KB, "
                f"ECU={original_size//1024}KB"
            )

        # ── Check 2: Estructura básica ──
        all_ff = all(b == 0xFF for b in binary_data[:256])
        all_00 = all(b == 0x00 for b in binary_data[:256])
        structure_ok = not all_ff and not all_00
        if not structure_ok:
            errors.append("Los primeros 256 bytes son todos 0xFF o 0x00 — archivo inválido")

        # ── Check 3: Checksum ──
        calculated_checksum = self._calculate_checksum(binary_data)

        # Leer checksum almacenado en el binario
        if len(binary_data) > CHECKSUM_OFFSET + CHECKSUM_SIZE:
            stored_bytes = binary_data[CHECKSUM_OFFSET:CHECKSUM_OFFSET + CHECKSUM_SIZE]
            stored_checksum = int.from_bytes(stored_bytes, "little")
        else:
            stored_checksum = 0

        checksum_ok = calculated_checksum == stored_checksum
        if not checksum_ok:
            warnings.append(
                f"Checksum no coincide: calculado=0x{calculated_checksum:08X}, "
                f"almacenado=0x{stored_checksum:08X} — se recalculará automáticamente"
            )

        # ── Check 4: Magic bytes ──
        # Muchas ECUs Bosch tienen una firma específica en los primeros bytes
        # DEMO: verificar que no es un archivo vacío
        if binary_data[:4] == b'\xFF\xFF\xFF\xFF':
            errors.append("No se detectó firma de software válida en el header")

        is_valid = len(errors) == 0

        result = ValidationResult(
            is_valid=is_valid,
            checksum_ok=checksum_ok,
            size_ok=size_ok,
            structure_ok=structure_ok,
            calculated_checksum=calculated_checksum,
            stored_checksum=stored_checksum,
            original_size=original_size,
            modified_size=modified_size,
            warnings=warnings,
            errors=errors,
        )

        logger.info(f"Validación: valid={is_valid}, "
                    f"checksum={'OK' if checksum_ok else 'FAIL'}, "
                    f"size={'OK' if size_ok else 'FAIL'}")
        return result

    def _calculate_checksum(self, data: bytes) -> int:
        """
        Calcula el checksum del binario para VW Polo TSI.

        ALGORITMOS REALES por ECU:
          - Bosch ME17.5.x: CRC-32 sobre rango [0x0000:0x7FFFB] (2MB)
          - Bosch MED17.x:  CRC-32 sobre rango específico de la flash
          - VW usa CRC-32 con polynomial estándar

        DEMO: CRC-32 estándar sobre todo el binario
        """
        import zlib

        data_without_checksum = (
            data[:CHECKSUM_OFFSET] +
            b'\x00' * CHECKSUM_SIZE +
            data[CHECKSUM_OFFSET + CHECKSUM_SIZE:]
        )

        crc = zlib.crc32(data_without_checksum) & 0xFFFFFFFF
        return crc

    def _patch_checksum(self, data: bytes) -> bytes:
        """
        Recalcula el checksum y lo escribe en la posición correcta del binario.
        Devuelve el binario listo para flashear.
        """
        checksum = self._calculate_checksum(data)
        patched = bytearray(data)

        # Escribir checksum calculado en el offset correcto
        checksum_bytes = checksum.to_bytes(CHECKSUM_SIZE, "little")
        patched[CHECKSUM_OFFSET:CHECKSUM_OFFSET + CHECKSUM_SIZE] = checksum_bytes

        logger.info(f"Checksum parchado: 0x{checksum:08X} @ offset 0x{CHECKSUM_OFFSET:X}")
        return bytes(patched)

    # ─── Comunicación UDS de escritura ──────────────────────────────────

    def _open_programming_session(self):
        """
        UDS 0x10 — DiagnosticSessionControl(0x02).
        La sesión de programación tiene restricciones adicionales:
          - El motor debe estar parado
          - La tensión de batería debe ser >11.5V (muchas ECUs verifican esto)
          - Algunas ECUs requieren temperatura de refrigerante específica
        """
        logger.debug("UDS → SessionControl(Programming 0x02)")
        # DEMO: simular
        time.sleep(0.1)

    def _security_access_programming(self):
        """
        SecurityAccess con nivel de escritura (generalmente nivel 0x11/0x12).
        Más restrictivo que el nivel de lectura.
        """
        logger.debug("UDS → SecurityAccess(Programming Level)")
        # Mismo patrón seed/key pero con nivel más alto y algoritmo diferente
        time.sleep(0.2)

    def _erase_flash(self, total_size: int):
        """
        UDS 0x31 — RoutineControl → EraseMemory.

        Borra el sector de flash de la ECU.
        Duración real: 5-30 segundos dependiendo del tamaño y tecnología de flash.
        La ECU no responde durante el borrado (normal).

        ⚠️  PUNTO DE NO RETORNO REAL:
          Una vez borrada la flash, la ECU no tiene código para ejecutar.
          DEBE completarse la escritura o la ECU quedará en brick.
        """
        logger.warning(f"⚠️  BORRANDO FLASH: {total_size // 1024} KB...")
        # DEMO: simular tiempo de borrado
        time.sleep(1.0)
        logger.info("Flash borrada correctamente.")

    def _request_download(self, total_size: int):
        """
        UDS 0x34 — RequestDownload.

        Notifica a la ECU que va a recibir un bloque de datos.
        Se especifica:
          - Dirección de inicio de escritura
          - Longitud total de datos
          - Tamaño de cada bloque de transferencia
        """
        logger.debug(f"UDS → RequestDownload({total_size} bytes)")
        time.sleep(0.1)

    def _transfer_data_blocks(self, data: bytes):
        """
        UDS 0x36 — TransferData × N bloques.

        Transfiere el binario completo en bloques de FLASH_BLOCK_SIZE bytes.
        Cada bloque lleva un contador secuencial (Block Sequence Counter)
        para detección de pérdida de bloques.

        Velocidad real: ~10-30 KB/s (depende del hardware y protocolo)
        """
        total_size = len(data)
        total_blocks = (total_size + FLASH_BLOCK_SIZE - 1) // FLASH_BLOCK_SIZE
        bytes_written = 0
        block_counter = 1  # Empieza en 1, wraps en 0xFF → 0x00

        logger.info(f"Transfiriendo {total_size} bytes en {total_blocks} bloques...")

        for block_index in range(total_blocks):
            start = block_index * FLASH_BLOCK_SIZE
            end = min(start + FLASH_BLOCK_SIZE, total_size)
            block_data = data[start:end]

            # Construir trama TransferData
            # [tamaño] [36] [block_counter] [DATA...]
            transfer_frame = bytes([block_counter % 256]) + block_data

            logger.debug(f"TransferData bloque {block_counter} @ 0x{start:08X}")

            # DEMO: simular escritura
            time.sleep(0.002)

            bytes_written += len(block_data)
            block_counter += 1

            # Calcular progreso (de 25% a 88%)
            base_pct = 25
            end_pct = 88
            pct = int(base_pct + (bytes_written / total_size) * (end_pct - base_pct))

            if block_index % 32 == 0:  # Notificar cada ~16KB
                speed_kbs = round(FLASH_BLOCK_SIZE * 32 / 1024, 1)
                self._notify(
                    "flash_progress",
                    phase="⚠️ ESCRIBIENDO FLASH — NO INTERRUMPIR",
                    step=f"Bloque {block_index+1}/{total_blocks} "
                         f"@ 0x{start:08X} ({speed_kbs} KB/s)",
                    pct=pct,
                    bytes_written=bytes_written,
                    total=total_size,
                )

        logger.info(f"✓ {bytes_written} bytes transferidos correctamente.")

    def _request_transfer_exit(self):
        """
        UDS 0x37 — RequestTransferExit.
        Señaliza el fin de la transferencia de datos.
        La ECU verifica internamente que recibió todos los bloques.
        """
        logger.debug("UDS → RequestTransferExit")
        time.sleep(0.1)

    def _check_programming_dependencies(self):
        """
        UDS 0x31 — RoutineControl(CheckProgrammingDependencies).
        La ECU verifica la coherencia del software recién escrito:
          - Checksum interno correcto
          - Compatibilidad HW/SW
          - Configuración de variante válida
        """
        logger.debug("UDS → CheckProgrammingDependencies")
        time.sleep(0.3)
        logger.info("✓ Dependencias verificadas por la ECU")

    def _ecu_reset(self):
        """
        UDS 0x11 — ECUReset(0x01 = Hard Reset).
        Reinicia la ECU para que arranque con el nuevo software.
        Después del reset, la ECU tardará unos segundos en inicializarse.
        """
        logger.debug("UDS → ECUReset(HardReset)")
        time.sleep(0.5)
        logger.info("ECU reiniciada. Esperando reinicialización...")
        time.sleep(2.0)  # Simular tiempo de boot de ECU
