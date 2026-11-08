"""
Utilidades comunes del Agente 1 (optimización):
  - Bloquea cualquier escritura de la app dentro de profiles/ (datos reales del usuario).
  - Silencia los messagebox para ejecución desatendida.
  - Conversión de resultados a JSON estable.
"""
import sys
import json
import math
import pathlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROFILES_ROOT = (PROJECT_ROOT / "profiles").resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BLOCKED_WRITES: list[str] = []

_orig_write_text = pathlib.Path.write_text
_orig_mkdir = pathlib.Path.mkdir
_orig_unlink = pathlib.Path.unlink


def _inside_profiles(p) -> bool:
    try:
        rp = Path(p).resolve()
        return rp == PROFILES_ROOT or PROFILES_ROOT in rp.parents
    except Exception:
        return False


def _guarded_write_text(self, *a, **k):
    if _inside_profiles(self):
        BLOCKED_WRITES.append(str(self))
        return 0
    return _orig_write_text(self, *a, **k)


def _guarded_mkdir(self, *a, **k):
    if _inside_profiles(self):
        return None
    return _orig_mkdir(self, *a, **k)


def _guarded_unlink(self, *a, **k):
    if _inside_profiles(self):
        BLOCKED_WRITES.append("UNLINK " + str(self))
        return None
    return _orig_unlink(self, *a, **k)


pathlib.Path.write_text = _guarded_write_text
pathlib.Path.mkdir = _guarded_mkdir
pathlib.Path.unlink = _guarded_unlink

import shutil as _shutil
_orig_rmtree = _shutil.rmtree


def _guarded_rmtree(path, *a, **k):
    if _inside_profiles(path):
        BLOCKED_WRITES.append("RMTREE " + str(path))
        return None
    return _orig_rmtree(path, *a, **k)


_shutil.rmtree = _guarded_rmtree

from tkinter import messagebox as _mb
for _name in ("showwarning", "showinfo", "showerror"):
    setattr(_mb, _name, lambda *a, **k: None)
_mb.askyesno = lambda *a, **k: False
_mb.askokcancel = lambda *a, **k: False


def jsonable(obj):
    """Convierte estructuras con tuplas, sets, numpy y claves no-str a JSON estable."""
    try:
        import numpy as np
        if isinstance(obj, np.generic):
            obj = obj.item()
        elif isinstance(obj, np.ndarray):
            obj = obj.tolist()
    except Exception:
        pass
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in sorted(obj.items(), key=lambda kv: str(kv[0]))}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, (set, frozenset)):
        return sorted(jsonable(v) for v in obj)
    if isinstance(obj, float):
        if math.isnan(obj):
            return "NaN"
        if math.isinf(obj):
            return "Inf" if obj > 0 else "-Inf"
        return obj
    if isinstance(obj, (int, str, bool)) or obj is None:
        return obj
    return repr(obj)
