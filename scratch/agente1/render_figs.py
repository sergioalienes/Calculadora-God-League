"""Guarda a PNG las figuras matplotlib de Neumáticos y Estrategias para comparar píxeles antes/después.
Uso: python scratch/agente1/render_figs.py <carpeta_salida>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402,F401
import main as app_main  # noqa: E402

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
app = app_main.CalculadoraApp()
app.withdraw()
for circ in ("Bélgica", "Road America", "Nurburgring Nordschleife"):
    app._modules["championship"].load_session_by_names("God League", circ)
    for mod in ("tyres", "charts"):
        app.navigate_to(mod)
        app.update()
        m = app._modules[mod]
        m.recalculate_and_plot()
        app.update()
        tag = circ.split()[0]
        m._fig.set_size_inches(10, 5.5) if mod == "charts" else m._fig.set_size_inches(9, 4.4)
        m._fig.savefig(out / f"{tag}_{mod}.png", facecolor=m._fig.get_facecolor())
        if mod == "charts":
            # Variante con SC + rebufo + inspector
            m._is_updating = True
            m._var_sc_enabled.set(True)
            m._var_draft_enabled.set(True)
            m._is_updating = False
            m._inspected_lap = 7
            m.recalculate_and_plot()
            m._fig.savefig(out / f"{tag}_{mod}_sc.png", facecolor=m._fig.get_facecolor())
            m._is_updating = True
            m._var_sc_enabled.set(False)
            m._var_draft_enabled.set(False)
            m._is_updating = False
            m._inspected_lap = None
app.destroy()
print("ok")
