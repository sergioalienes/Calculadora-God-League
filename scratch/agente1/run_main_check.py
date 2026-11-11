"""Arranca main.py tal cual (como `python main.py`), lo cierra a los 8 s con on_closing()
y deja profiles/ exactamente como estaba ANTES de esta ejecución (la app escribe
_last_state.json y <circuito>_live.json al navegar y al cerrar).

La copia de seguridad se hace al empezar cada ejecución, en una carpeta temporal.
(Antes se restauraba desde una copia fija y antigua, lo que pisaba los cambios
posteriores del usuario y borraba sus circuitos nuevos.)"""
import runpy
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
import tempfile  # noqa: E402

# Copia de profiles/ tal y como está AHORA (nunca una copia antigua)
BACKUP = Path(tempfile.mkdtemp(prefix="main_check_profiles_")) / "profiles"
shutil.copytree(ROOT / "profiles", BACKUP)
sys.path.insert(0, str(ROOT))

import customtkinter as ctk  # noqa: E402

_orig_mainloop = ctk.CTk.mainloop
T0 = time.perf_counter()


def _mainloop(self, *a, **k):
    print(f"[check] ventana creada en {time.perf_counter() - T0:.2f}s", flush=True)
    self.after(8000, self.on_closing)
    return _orig_mainloop(self, *a, **k)


ctk.CTk.mainloop = _mainloop
try:
    runpy.run_path(str(ROOT / "main.py"), run_name="__main__")
    print("[check] main.py cerrado sin excepciones", flush=True)
finally:
    prof = ROOT / "profiles"
    for src in BACKUP.rglob("*"):
        if src.is_file():
            dst = prof / src.relative_to(BACKUP)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    for f in list(prof.rglob("*")):
        if f.is_file() and not (BACKUP / f.relative_to(prof)).exists():
            print("[check] archivo nuevo creado por la app (se elimina):", f, flush=True)
            f.unlink()
    print("[check] profiles/ restaurado desde la copia", flush=True)
