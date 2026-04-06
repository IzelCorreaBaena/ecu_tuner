"""
modules/tuning_module.py
========================
MÓDULO 3: MAPEO Y TUNING
========================
Carga el archivo .bin y expone los mapas de motor para edición.

CONCEPTOS CLAVE:
  Un archivo .bin de ECU es una imagen plana de la memoria flash.
  Los "mapas" son tablas 2D/3D de valores almacenadas en posiciones
  fijas de memoria (offsets) con un formato específico por fabricante.

ESTRUCTURA DE UN MAPA DE MOTOR:
  Un mapa típico (ej: mapa de inyección) consiste en:
    - Eje X: valores de RPM  (16 valores, 2 bytes cada uno = 32 bytes)
    - Eje Y: valores de carga (16 valores, 2 bytes cada uno = 32 bytes)
    - Tabla: 16×16 valores de duración de inyección (512 bytes)
    - Total: ~576 bytes en una dirección conocida del .bin

  Los offsets son específicos de cada ECU/fabricante.
  Herramientas como WinOLS, ECM Titanium o TunerPro tienen
  "definiciones" (XDF) que mapean estos offsets por ECU.

ESCALADO DE VALORES:
  Los valores en flash están codificados en enteros (uint8, uint16).
  Para obtener valores físicos se aplica: valor_real = raw * factor + offset
  Ejemplo en Bosch ME7: inyección_ms = raw_uint16 * 0.0039 (ms por bit)

IDENTIFICACIÓN DE MAPAS:
  En un .bin desconocido, los mapas se buscan mediante:
    1. Firmas de secuencia conocidas en el binario
    2. Análisis estadístico (tablas tienen distribución no aleatoria)
    3. Ingeniería inversa del código de la ECU (desensamblado)
    4. Archivos de definición XDF/A2L específicos del hardware

MAPAS INCLUIDOS EN ESTA DEMO:
  - Mapa de inyección (tiempo de inyección vs RPM×carga)
  - Mapa de presión de turbo (boost vs RPM×carga)
  - Limitador de par por marcha
  - Mapa de avance de encendido (solo gasolina)
"""

import logging
import numpy as np
from pathlib import Path
from typing import Callable, Optional
from dataclasses import dataclass, field

logger = logging.getLogger("ECUTuner.Tuning")


# ─── Definición de mapas (equivalente a un XDF simplificado) ───────────────

@dataclass
class MapDefinition:
    """
    Define la ubicación y formato de un mapa para VW Polo TSI.

    En herramientas profesionales, esto viene de archivos XDF (TunerPro)
    o A2L (ASAP2 standard, usado por WinOLS y herramientas OEM).
    """
    id:           str              # Identificador único del mapa
    name:         str              # Nombre legible
    description:  str              # Descripción técnica
    category:     str              # "fuel", "boost", "ignition", "torque"

    # Geometría del mapa
    rows:         int              # Número de filas (generalmente = len(axis_y))
    cols:         int              # Número de columnas (generalmente = len(axis_x))

    # Offsets en el archivo .bin
    offset_table: int              # Offset del array de valores
    offset_axis_x: int            # Offset del eje X (RPM generalmente)
    offset_axis_y: int            # Offset del eje Y (carga/presión)

    # Formato de datos
    data_type:    str = "uint16"   # "uint8", "uint16", "int16"
    byte_order:   str = "little"   # "little" (Intel) o "big" (Motorola)
    factor:       float = 1.0     # Factor de escala: real = raw * factor + offset_val
    offset_val:   float = 0.0     # Offset de valor

    # Unidades y límites para la UI
    unit:         str = ""
    min_val:      float = 0.0
    max_val:      float = 100.0

    # Labels de ejes por defecto (se sobreescriben con valores del .bin)
    axis_x_labels: list = field(default_factory=list)
    axis_y_labels: list = field(default_factory=list)


# ─── Definiciones de mapas para VW Polo 1.0 TSI / 1.4 TSI ──────────────────
# ECU: Bosch ME17.5.22 (TSI) / Bosch MED17.5.5 (TSI antiguo)
# Nota: offsets simulados para demo. En real varían por versión de software.

MAP_DEFINITIONS: dict[str, MapDefinition] = {

    "injection_time": MapDefinition(
        id="injection_time",
        name="Tiempo de Inyección",
        description=(
            "Mapa principal de inyección (VW Polo TSI). Define el tiempo de "
            "inyección en ms según RPM y carga. "
            "Polo 1.0 TSI: inyectores ~440cc, presión turbo stock ~1200 mbar."
        ),
        category="fuel",
        rows=16, cols=16,
        offset_table=0x14A00,
        offset_axis_x=0x149C0,
        offset_axis_y=0x149E0,
        data_type="uint16",
        factor=0.0039,
        unit="ms",
        min_val=0.5, max_val=20.0,
        axis_x_labels=[700,900,1100,1300,1600,2000,2500,3000,3500,4000,4500,5000,5500,6000,6500,7000],
        axis_y_labels=[10,15,20,25,30,40,50,60,70,80,90,100,110,120,140,160],
    ),

    "boost_pressure": MapDefinition(
        id="boost_pressure",
        name="Presión de Turbo (Boost)",
        description=(
            "Presión de sobrealimentación objetivo en mbar relativo. "
            "VW Polo 1.0 TSI: stock ~1200 mbar, 1.4 TSI: stock ~1500 mbar. "
            "La wastegate electrónica (TD05 turbo) se controla con este mapa."
        ),
        category="boost",
        rows=12, cols=16,
        offset_table=0x1C800,
        offset_axis_x=0x1C780,
        offset_axis_y=0x1C7A0,
        data_type="uint16",
        factor=0.1,
        unit="mbar",
        min_val=0, max_val=2500,
        axis_x_labels=[700,900,1100,1300,1600,2000,2500,3000,3500,4000,4500,5000,5500,6000,6500,7000],
        axis_y_labels=[10,20,30,40,50,60,70,80,90,100,120,140],
    ),

    "torque_limiter": MapDefinition(
        id="torque_limiter",
        name="Limitador de Par por Marcha",
        description=(
            "Límites de par máximo (Nm) por marcha. "
            "VW Polo 1.0 TSI: 200 Nm máx. Incrementar con precaución."
        ),
        category="torque",
        rows=1, cols=8,
        offset_table=0x24800,
        offset_axis_x=0x247F0,
        offset_axis_y=0x247F0,
        data_type="uint16",
        factor=0.25,
        unit="Nm",
        min_val=50, max_val=400,
        axis_x_labels=["1ª","2ª","3ª","4ª","5ª","6ª","R","Neutro"],
        axis_y_labels=["Límite Par"],
    ),

    "ignition_advance": MapDefinition(
        id="ignition_advance",
        name="Avance de Encendido",
        description=(
            "Punto de encendido en grados BTDC. "
            "VW Polo TSI: compresión 10.5:1 (1.0) o 10.0:1 (1.4). "
            "Usar combustible de 95 octanos mínimo. Ajustar para mayor rendimiento."
        ),
        category="ignition",
        rows=16, cols=16,
        offset_table=0x16E00,
        offset_axis_x=0x16DC0,
        offset_axis_y=0x16DE0,
        data_type="int16",
        factor=0.1,
        unit="° BTDC",
        min_val=-10.0, max_val=50.0,
        axis_x_labels=[700,900,1100,1300,1600,2000,2500,3000,3500,4000,4500,5000,5500,6000,6500,7000],
        axis_y_labels=[10,15,20,25,30,40,50,60,70,80,90,100,110,120,140,160],
    ),

    "lamda_correction": MapDefinition(
        id="lamda_correction",
        name="Corrección Lambda",
        description=(
            "Corrección de la mezcla aire/combustible en torno a lambda=1. "
            "Valores >1 = enriquecimiento, <1 = empobrecimiento. "
            "VW Polo TSI: sonda lambda Bosch LSU 4.9."
        ),
        category="fuel",
        rows=16, cols=16,
        offset_table=0x1A400,
        offset_axis_x=0x1A3C0,
        offset_axis_y=0x1A3E0,
        data_type="int16",
        factor=0.001,
        unit="lambda",
        min_val=0.8, max_val=1.2,
        axis_x_labels=[700,900,1100,1300,1600,2000,2500,3000,3500,4000,4500,5000,5500,6000,6500,7000],
        axis_y_labels=[10,15,20,25,30,40,50,60,70,80,90,100,110,120,140,160],
    ),

    "rpm_limiter": MapDefinition(
        id="rpm_limiter",
        name="Limitador de RPM",
        description=(
            "Corte de inyección (RPM máximo). "
            "VW Polo 1.0 TSI: 6500 RPM stock, 1.4 TSI: 6800 RPM."
        ),
        category="torque",
        rows=1, cols=4,
        offset_table=0x2A000,
        offset_axis_x=0x29FF0,
        offset_axis_y=0x29FF0,
        data_type="uint16",
        factor=1.0,
        unit="RPM",
        min_val=4000, max_val=8000,
        axis_x_labels=["Corte Bajo","Corte Alto","Corte Decel.","Reserva"],
        axis_y_labels=["RPM"],
    ),
}


class TuningModule:
    """
    Carga el .bin, parsea los mapas y gestiona las modificaciones.

    Patrón: Repository + Command
      - Repository: almacena el estado original y modificado de cada mapa
      - Command: cada modificación se registra (para undo/redo futuro)
    """

    def __init__(self, ctx, notify: Callable):
        self.ctx = ctx
        self._notify = notify

        # Cache de mapas cargados: {map_id: MapData}
        self._maps: dict[str, "MapData"] = {}

        # Historial de cambios (para undo/redo)
        self._change_history: list[dict] = []

        logger.info("TuningModule listo.")

    def load_file(self, file_path: str):
        """
        Carga un archivo .bin y parsea todos los mapas definidos.

        En producción, también detectaría automáticamente el tipo de ECU
        comparando firmas del binario con una base de datos.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Archivo no encontrado: {file_path}")

        with open(path, "rb") as f:
            raw_data = f.read()

        self.ctx.binary_data = raw_data
        self.ctx.modified_data = bytearray(raw_data)

        logger.info(f"Cargado: {path.name} ({len(raw_data)} bytes)")

        # Parsear todos los mapas definidos
        for map_id, map_def in MAP_DEFINITIONS.items():
            try:
                map_data = self._parse_map(raw_data, map_def)
                self._maps[map_id] = map_data
                logger.debug(f"  ✓ Mapa '{map_def.name}' parseado ({map_def.rows}×{map_def.cols})")
            except Exception as e:
                logger.warning(f"  ✗ Error parseando '{map_def.name}': {e}")

        self._notify("maps_loaded", map_ids=list(self._maps.keys()))
        logger.info(f"✓ {len(self._maps)} mapas cargados correctamente.")

    def _parse_map(self, raw_data: bytes, map_def: MapDefinition) -> "MapData":
        """
        Extrae y escala una tabla de valores del binario.

        El proceso:
          1. Leer los bytes de la tabla desde el offset
          2. Interpretar como array de uint16 (o el tipo definido)
          3. Aplicar factor y offset de escala → valores físicos reales
          4. Leer los ejes X e Y desde sus offsets
        """
        # Determinar tipo numpy
        dtype_map = {
            "uint8":  np.uint8,
            "uint16": np.uint16,
            "int16":  np.int16,
        }
        dtype = dtype_map[map_def.data_type]
        bytes_per_val = np.dtype(dtype).itemsize

        # Calcular tamaño total de la tabla
        table_size = map_def.rows * map_def.cols * bytes_per_val

        # ── Extraer tabla ──
        # En demo generamos datos simulados si el offset supera el tamaño del bin
        if map_def.offset_table + table_size <= len(raw_data):
            table_bytes = raw_data[map_def.offset_table:map_def.offset_table + table_size]
            raw_array = np.frombuffer(table_bytes, dtype=dtype)
        else:
            # DEMO: generar datos simulados realistas
            raw_array = self._generate_demo_map(map_def)

        # Dar forma de matriz
        raw_matrix = raw_array.reshape((map_def.rows, map_def.cols))

        # Aplicar escala para obtener valores físicos
        scaled_matrix = raw_matrix.astype(float) * map_def.factor + map_def.offset_val

        # ── Extraer ejes (o usar los predefinidos) ──
        axis_x = map_def.axis_x_labels or list(range(map_def.cols))
        axis_y = map_def.axis_y_labels or list(range(map_def.rows))

        return MapData(
            definition=map_def,
            raw_matrix=raw_matrix.copy(),
            scaled_matrix=scaled_matrix,
            modified_matrix=scaled_matrix.copy(),
            axis_x=axis_x,
            axis_y=axis_y,
        )

    def _generate_demo_map(self, map_def: MapDefinition) -> np.ndarray:
        """
        Genera datos simulados realistas para cada tipo de mapa.
        Los datos tienen forma de gradiente con algo de ruido para simular
        el aspecto real de un mapa de motor calibrado.
        """
        rows, cols = map_def.rows, map_def.cols
        dtype_map = {"uint8": np.uint8, "uint16": np.uint16, "int16": np.int16}
        dtype = dtype_map[map_def.data_type]

        if map_def.category == "fuel":
            # Inyección: gradiente RPM/carga típico
            base = np.linspace(800, 4000, cols * rows).reshape(rows, cols) / map_def.factor
        elif map_def.category == "boost":
            # Boost: campana de Gauss centrada en mid-RPM
            x = np.linspace(0, np.pi, cols)
            y = np.linspace(0.3, 1.0, rows)
            base = np.outer(y, np.sin(x)) * (2500 / map_def.factor)
        elif map_def.category == "torque":
            # Limitador de par: valores fijos por marcha
            torque_vals = [200, 280, 340, 380, 380, 360, 150, 0][:cols]
            base = np.array([torque_vals] * rows) / map_def.factor
        elif map_def.category == "ignition":
            # Avance: gradiente con zona de máximo avance en RPM medias
            x = np.linspace(-5, 35, cols * rows).reshape(rows, cols)
            base = x / map_def.factor
        else:
            base = np.ones((rows, cols)) * 100

        return np.clip(base, 0, np.iinfo(dtype).max if dtype != np.int16 else np.iinfo(dtype).max).astype(dtype)

    # ─── API de acceso a mapas ──────────────────────────────────────────

    def get_map(self, map_id: str) -> dict:
        """
        Devuelve los datos de un mapa para renderización en la UI.

        Returns:
          {
            "definition": MapDefinition,
            "values": ndarray 2D de floats (valores modificados),
            "original_values": ndarray 2D de floats (valores originales),
            "axis_x": lista de labels eje X,
            "axis_y": lista de labels eje Y,
            "has_changes": bool
          }
        """
        if map_id not in self._maps:
            raise KeyError(f"Mapa no encontrado: {map_id}")

        md = self._maps[map_id]
        return {
            "definition":       md.definition,
            "values":           md.modified_matrix,
            "original_values":  md.scaled_matrix,
            "axis_x":           md.axis_x,
            "axis_y":           md.axis_y,
            "has_changes":      not np.array_equal(md.modified_matrix, md.scaled_matrix),
        }

    def get_all_map_ids(self) -> list[str]:
        return list(self._maps.keys())

    def update_cell(self, map_id: str, row: int, col: int, value: float):
        """
        Modifica una celda del mapa con validación de rango.

        La modificación se registra en el historial para undo/redo.
        El binario modificado se actualiza en ctx.modified_data.
        """
        if map_id not in self._maps:
            return

        md = self._maps[map_id]
        map_def = md.definition

        # Validar rango
        value = max(map_def.min_val, min(map_def.max_val, value))

        # Registrar cambio en historial
        old_value = md.modified_matrix[row, col]
        self._change_history.append({
            "map_id": map_id, "row": row, "col": col,
            "old": old_value, "new": value
        })

        # Actualizar matriz modificada
        md.modified_matrix[row, col] = value

        # Actualizar el binario en memoria (reescalar valor físico → raw)
        raw_value = int((value - map_def.offset_val) / map_def.factor)
        self._write_to_binary(map_def, row, col, raw_value)

        logger.debug(f"Celda actualizada [{map_id}][{row},{col}]: {old_value:.3f} → {value:.3f}")
        self._notify("map_cell_changed",
                     map_id=map_id, row=row, col=col,
                     old=old_value, new=value)

    def _write_to_binary(self, map_def: MapDefinition, row: int, col: int, raw_value: int):
        """
        Escribe un valor raw en la posición correcta del binario modificado.
        Respeta el byte order (endianness) del fabricante.
        """
        if self.ctx.modified_data is None:
            return

        bytes_per_val = 2 if map_def.data_type in ("uint16", "int16") else 1
        cell_offset = map_def.offset_table + (row * map_def.cols + col) * bytes_per_val

        if cell_offset + bytes_per_val <= len(self.ctx.modified_data):
            raw_bytes = raw_value.to_bytes(bytes_per_val, byteorder=map_def.byte_order,
                                            signed=(map_def.data_type == "int16"))
            self.ctx.modified_data[cell_offset:cell_offset + bytes_per_val] = raw_bytes

    def get_change_count(self) -> int:
        """Número de celdas modificadas respecto al original."""
        return len(self._change_history)

    def save_modified_binary(self, output_path: str):
        """Guarda el binario modificado a disco."""
        with open(output_path, "wb") as f:
            f.write(self.ctx.modified_data)
        logger.info(f"Binario modificado guardado: {output_path}")
        self._notify("binary_saved", path=output_path)


@dataclass
class MapData:
    """Contenedor de datos de un mapa parseado y en edición."""
    definition:       MapDefinition
    raw_matrix:       np.ndarray    # Valores brutos del .bin
    scaled_matrix:    np.ndarray    # Valores originales escalados
    modified_matrix:  np.ndarray    # Valores con modificaciones del usuario
    axis_x:           list
    axis_y:           list
