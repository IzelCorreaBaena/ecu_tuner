import json
from pathlib import Path
from typing import List, Dict, Any

def load_profiles(path: str) -> List[Dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("profiles", [])

def apply_profile(app_controller, profile: Dict[str, Any]):
    """
    Aplica un perfil de configuración tipo VCDS a los mapas activos.
    Soporta cambios en celdas específicas: map_id, row, col, value.
    """
    for change in profile.get("changes", []):
        map_id = change.get("map_id")
        row = change.get("row")
        col = change.get("col")
        value = change.get("value")
        if map_id is None or row is None or col is None or value is None:
            continue
        app_controller.update_map_cell(map_id, int(row), int(col), float(value))
