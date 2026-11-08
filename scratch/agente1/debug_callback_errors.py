"""Reproduce cambios de zoom/tamaño/navegación y vuelca a fichero las excepciones de callbacks Tk."""
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402,F401
import main  # noqa: E402

OUT = Path(__file__).resolve().parent / "callback_errors.txt"
OUT.unlink(missing_ok=True)
app = main.CalculadoraApp()


def rep(*a):
    with open(OUT, "a", encoding="utf-8") as f:
        f.write("".join(traceback.format_exception(*a))[-2500:] + "\n=====\n")


app.report_callback_exception = rep
app.update()
for z in ["100%", "115%", "85%"]:
    app._seg_zoom.set(z)
    app._on_zoom_changed(z)
    app.update()
    for g in ["960x560", "1280x780"]:
        app.geometry(g + "+0+0")
        app.update()
        for m in ["championship", "fuel", "tyres", "charts", "live"]:
            app.navigate_to(m)
            app.update()
            time.sleep(0.05)
            app.update()
app.destroy()
n = OUT.read_text(encoding="utf-8").count("=====") if OUT.exists() else 0
print("errores en callbacks:", n)
