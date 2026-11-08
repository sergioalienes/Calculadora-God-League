"""Perfila el arranque (CalculadoraApp()) y la navegación entre módulos con cProfile.
Uso: python scratch/agente1/profile_startup.py [init|nav] [n_lineas]
"""
import sys
import time
import cProfile
import pstats
import io
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402,F401

mode = sys.argv[1] if len(sys.argv) > 1 else "init"
nlines = int(sys.argv[2]) if len(sys.argv) > 2 else 40

import main as app_main  # noqa: E402

pr = cProfile.Profile()
if mode == "init":
    t0 = time.perf_counter()
    pr.enable()
    app = app_main.CalculadoraApp()
    app.update_idletasks()
    pr.disable()
    print(f"init: {time.perf_counter() - t0:.3f}s")
else:
    app = app_main.CalculadoraApp()
    app.update_idletasks()
    t0 = time.perf_counter()
    pr.enable()
    for mod in ("championship", "fuel", "tyres", "charts", "live", "championship", "charts"):
        app.navigate_to(mod)
        app.update_idletasks()
    pr.disable()
    print(f"nav x7: {time.perf_counter() - t0:.3f}s")

s = io.StringIO()
ps = pstats.Stats(pr, stream=s).sort_stats("cumulative")
ps.print_stats(nlines)
print(s.getvalue())
s = io.StringIO()
ps = pstats.Stats(pr, stream=s).sort_stats("tottime")
ps.print_stats(25)
print(s.getvalue())
app.destroy()
