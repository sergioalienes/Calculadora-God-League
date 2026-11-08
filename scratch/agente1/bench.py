"""Mediciones de rendimiento (time.perf_counter) con la GUI oculta.
Uso: python scratch/agente1/bench.py
Imprime una línea JSON con los tiempos.
"""
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
t0 = time.perf_counter()
import harness  # noqa: E402,F401
import main as app_main  # noqa: E402
t_import = time.perf_counter() - t0

r = {"import_s": round(t_import, 3)}
t0 = time.perf_counter()
app = app_main.CalculadoraApp()
app.withdraw()
app.update_idletasks()
r["init_s"] = round(time.perf_counter() - t0, 3)

# Navegación: ciclo completo de módulos (2 vueltas, se reporta media por cambio)
nav = {}
for rep in range(2):
    for mod in ("championship", "fuel", "tyres", "charts", "live"):
        t0 = time.perf_counter()
        app.navigate_to(mod)
        app.update_idletasks()
        app.update()
        nav.setdefault(mod, []).append(time.perf_counter() - t0)
r["nav_s"] = {k: round(sum(v) / len(v), 3) for k, v in nav.items()}

# Sliders: recálculo + render de neumáticos y estrategias (lo que dispara cada arrastre)
tyre = app._modules["tyres"]
ch = app._modules["charts"]
tot = tyre._var_total_laps.get()
t0 = time.perf_counter()
n = 0
for p in range(3, max(4, tot - 2)):
    tyre._var_pit1_lap.set(p)
    tyre.recalculate_and_plot()
    tyre._mpl_canvas.draw()  # forzar el render que draw_idle aplaza
    n += 1
r["tyre_slider_ms"] = round(1000 * (time.perf_counter() - t0) / max(1, n), 1)

app.navigate_to("charts")
app.update()
t0 = time.perf_counter()
n = 0
for p in range(3, max(4, tot - 3)):
    ch._var_p1.set(p)
    ch.recalculate_and_plot()
    ch._mpl_canvas.draw()
    n += 1
r["charts_slider_ms"] = round(1000 * (time.perf_counter() - t0) / max(1, n), 1)

t0 = time.perf_counter()
for _ in range(5):
    ch.solve_optimal_strategy()
r["optimal_ms"] = round(1000 * (time.perf_counter() - t0) / 5, 1)

t0 = time.perf_counter()
for _ in range(5):
    ch._find_best_1stop_opportunity()
r["opp1stop_ms"] = round(1000 * (time.perf_counter() - t0) / 5, 1)

# CPU en reposo: tiempo de proceso consumido durante 3 s de mainloop sin interacción
import os
cpu0 = time.process_time()
w0 = time.perf_counter()
app.after(3000, app.quit)
app.mainloop()
r["idle_cpu_pct"] = round(100 * (time.process_time() - cpu0) / (time.perf_counter() - w0), 2)

import matplotlib.pyplot as plt  # noqa: E402
r["pyplot_figs"] = len(plt.get_fignums())
print(json.dumps(r))
app.destroy()
