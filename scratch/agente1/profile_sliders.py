"""Perfila el recálculo+render de los sliders de Neumáticos y Estrategias en un circuito real.
Uso: python scratch/agente1/profile_sliders.py "Road America" [tyres|charts] [n]
"""
import sys
import time
import cProfile
import pstats
import io
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402,F401
import main as app_main  # noqa: E402

circ = sys.argv[1] if len(sys.argv) > 1 else "Road America"
which = sys.argv[2] if len(sys.argv) > 2 else "charts"
nlines = int(sys.argv[3]) if len(sys.argv) > 3 else 30

app = app_main.CalculadoraApp()
app.withdraw()
app._modules["championship"].load_session_by_names("God League", circ)
app.navigate_to("tyres" if which == "tyres" else "charts")
app.update()
mod = app._modules["tyres" if which == "tyres" else "charts"]

pr = cProfile.Profile()
t0 = time.perf_counter()
n = 0
pr.enable()
if which == "tyres":
    tot = mod._var_total_laps.get()
    for p in range(5, tot - 5):
        mod._var_pit1_lap.set(p)
        mod.recalculate_and_plot()
        mod._mpl_canvas.draw()
        n += 1
else:
    tot = mod.current_result["total_laps"]
    print("modo:", mod._var_num_stops.get(), "vueltas:", tot)
    for p in range(5, tot - 8):
        mod._var_p1.set(p)
        mod.recalculate_and_plot()
        mod._mpl_canvas.draw()
        n += 1
pr.disable()
print(f"{which}: {1000 * (time.perf_counter() - t0) / n:.1f} ms/iter (n={n})")
s = io.StringIO()
pstats.Stats(pr, stream=s).sort_stats("cumulative").print_stats(nlines)
print(s.getvalue())
app.destroy()
