"""Capturas y análisis automático de desbordes por tamaño de ventana y zoom.

Uso:
  python scratch/agente1/screens.py <carpeta> [WxH|max ...] [--zooms 85%,100%,115%] [--mods a,b] [--scroll]

Para cada combinación (tamaño, zoom, módulo):
  - Captura la ventana (PIL.ImageGrab) en <carpeta>/<mod>_<WxH>_<zoom>[_pN].png
  - Detecta widgets recortados: etiquetas/botones cuyo ancho pedido (reqwidth) supera
    el asignado, y widgets que sobresalen por la derecha del área visible del módulo.
Escrituras en profiles/ bloqueadas (harness).
"""
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402,F401
import customtkinter as ctk  # noqa: E402
from PIL import ImageGrab  # noqa: E402
import main as app_main  # noqa: E402

args = sys.argv[1:]
out = Path(args[0]); out.mkdir(parents=True, exist_ok=True)
sizes = [a for a in args[1:] if not a.startswith("--") and ("x" in a or a == "max")]
zooms = ["85%", "100%", "115%"]
mods = [m for m, _ in app_main.MODULE_IDS]
do_scroll = "--scroll" in args
for i, a in enumerate(args):
    if a == "--zooms":
        zooms = args[i + 1].split(",")
    if a == "--mods":
        mods = args[i + 1].split(",")
if not sizes:
    sizes = ["960x560", "1280x780", "1600x900", "max"]

import traceback  # noqa: E402
app = app_main.CalculadoraApp()
CALLBACK_ERRORS = []
app.report_callback_exception = lambda *a: CALLBACK_ERRORS.append("".join(traceback.format_exception(*a)))
app.update()


def settle():
    for _ in range(3):
        app.update_idletasks()
        app.update()
        time.sleep(0.05)


def grab(name):
    settle()
    x, y = app.winfo_rootx(), app.winfo_rooty()
    w, h = app.winfo_width(), app.winfo_height()
    ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).save(out / name)


def analyse(mod):
    """Devuelve widgets recortados dentro del módulo visible."""
    issues = []
    m = app._modules[mod]
    mx0 = m.winfo_rootx()
    mx1 = mx0 + m.winfo_width()
    seen = set()

    def walk(w):
        for c in w.winfo_children():
            try:
                if not c.winfo_ismapped():
                    continue
                cls = c.__class__.__name__
                x0 = c.winfo_rootx(); wd = c.winfo_width(); rq = c.winfo_reqwidth()
                key = str(c)
                if cls in ("CTkLabel", "CTkButton", "CTkSegmentedButton", "CTkOptionMenu", "CTkComboBox", "CTkEntry", "CTkCheckBox", "CTkSwitch", "Label", "Canvas") and key not in seen:
                    txt = ""
                    try:
                        txt = str(c.cget("text"))[:70]
                    except Exception:
                        pass
                    if rq > wd + 2 and wd > 1:
                        issues.append({"tipo": "recortado(req>asignado)", "cls": cls, "w": wd, "req": rq, "texto": txt, "path": key[-60:]})
                        seen.add(key)
                    elif x0 + wd > mx1 + 1 and wd > 1:
                        issues.append({"tipo": "fuera_por_derecha", "cls": cls, "sobra_px": x0 + wd - mx1, "texto": txt, "path": key[-60:]})
                        seen.add(key)
                walk(c)
            except Exception:
                continue

    walk(m)
    return issues


report = {}
for zoom in zooms:
    app._seg_zoom.set(zoom)
    app._on_zoom_changed(zoom)
    settle()
    for size in sizes:
        if size == "max":
            app.state("zoomed")
        else:
            app.state("normal")
            app.geometry(size + "+0+0")
        settle()
        real = f"{app.winfo_width()}x{app.winfo_height()}"
        for mod in mods:
            app.navigate_to(mod)
            settle()
            tag = f"{mod}_{size}_{zoom.rstrip('%')}"
            grab(tag + ".png")
            iss = analyse(mod)
            report[tag] = {"real": real, "issues": iss}
            if do_scroll:
                sc = getattr(app._modules[mod], "_scroll", None)
                if sc is not None and hasattr(sc, "_parent_canvas"):
                    for i, frac in enumerate((0.33, 0.66, 1.0), start=1):
                        sc._parent_canvas.yview_moveto(frac)
                        grab(f"{tag}_p{i}.png")
                        more = analyse(mod)
                        known = {(d["path"], d["tipo"]) for d in report[tag]["issues"]}
                        report[tag]["issues"] += [d for d in more if (d["path"], d["tipo"]) not in known]
                    sc._parent_canvas.yview_moveto(0.0)
            print(tag, real, "problemas:", len(report[tag]["issues"]))

report["_callback_errors"] = CALLBACK_ERRORS
print("errores en callbacks Tk:", len(CALLBACK_ERRORS))
(out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
app.destroy()
