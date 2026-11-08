"""
Arnés común de pruebas del Agente 2 (revisión de estrategias y coherencia).

- Añade la raíz del worktree a sys.path (NO la ruta del repo original).
- Copia profiles/ a una carpeta temporal y redirige PROFILES_ROOT de todos los
  módulos (y STATE_FILE de main) hacia esa copia, para no tocar los perfiles reales.
- Silencia messagebox (registra las llamadas).
- Crea una raíz CTk oculta (withdraw) para instanciar los módulos sin GUI visible.
"""
import sys
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

TMP_DIR = Path(tempfile.mkdtemp(prefix="agente2_profiles_"))
TMP_PROFILES = TMP_DIR / "profiles"
shutil.copytree(ROOT / "profiles", TMP_PROFILES)

from tkinter import messagebox  # noqa: E402

MSG_CALLS = []
messagebox.showwarning = lambda *a, **k: MSG_CALLS.append(("warning", a))
messagebox.showinfo = lambda *a, **k: MSG_CALLS.append(("info", a))
messagebox.showerror = lambda *a, **k: MSG_CALLS.append(("error", a))
messagebox.askyesno = lambda *a, **k: True

import customtkinter as ctk  # noqa: E402
import modules.championship_data as m_champ  # noqa: E402
import modules.fuel_strategy as m_fuel  # noqa: E402
import modules.tyre_strategy as m_tyre  # noqa: E402
import modules.strategy_charts as m_charts  # noqa: E402
import modules.live_control as m_live  # noqa: E402

for _m in (m_champ, m_fuel, m_tyre, m_charts, m_live):
    _m.PROFILES_ROOT = TMP_PROFILES

COLORS = {
    "bg_primary": "#0A0A0A", "bg_secondary": "#131313", "sidebar_bg": "#0D0D0D",
    "accent": "#F26419", "accent_hover": "#FF7A2F", "accent_dim": "#3D2008",
    "accent_glow": "#FF6B1A", "text_primary": "#FFFFFF", "text_secondary": "#9A9A9A",
    "border": "#222222", "input_bg": "#1A1A1A", "success": "#4CAF50",
    "warning": "#F26419", "danger": "#FF453A",
}

_ROOT_WIN = None


def tk_root():
    global _ROOT_WIN
    if _ROOT_WIN is None:
        ctk.set_appearance_mode("dark")
        _ROOT_WIN = ctk.CTk()
        _ROOT_WIN.withdraw()
    return _ROOT_WIN


def make_session(champ="Test", circuit="TestTrack", lap="01:45.000", pit=30.0,
                 tank=105.0, rate=2.8, tyre=18.0, lift=2.0, dur_min=45.0,
                 mandatory=True, trk=5.0, sc_kmh=100.0):
    """Construye session_data con las MISMAS claves que championship_data._save_session_data."""
    lap_s = int(lap[:2]) * 60 + float(lap[3:])
    sc_pace_s = (trk / sc_kmh) * 3600.0
    return {
        "championship_name": champ, "car": "TestCar",
        "fuel_capacity_l": float(tank), "refuel_rate_ls": float(rate),
        "tyre_change_time": float(tyre), "tyre_change_s": float(tyre),
        "car_lift_s": float(lift), "car_lift_time": float(lift),
        "race_duration_s": float(dur_min) * 60, "race_duration_min": float(dur_min),
        "race_duration_minutes": float(dur_min),
        "tyre_compounds": ["Prime (Duro)", "Alternative (Blando)"],
        "mandatory_compound_change": mandatory,
        "circuit": circuit, "lap_time_str": lap, "lap_time_seconds": lap_s,
        "pitlane_loss": float(pit), "pitlane_loss_s": float(pit),
        "track_length_km": trk, "sc_speed_kmh": sc_kmh,
        "sc_pace_s": sc_pace_s, "sc_pace_str": "",
    }


def new_fuel(session, cons, safety, wsens, num_stops=None, p1=None, p2=None):
    mod = m_fuel.FuelStrategyModule(tk_root(), colors=COLORS)
    mod.session_data = session
    mod._var_fuel_lap.set(str(cons))
    mod._var_safety_fuel.set(str(safety))
    mod._var_weight_sens.set(str(wsens))
    if num_stops is not None:
        mod._var_num_stops.set(num_stops)
    if p1 is not None:
        mod._var_pit1_lap.set(p1)
    if p2 is not None:
        mod._var_pit2_lap.set(p2)
    mod.calculate_strategy()
    return mod


def build_pipeline(sd, fuel_over=None, tyre_over=None):
    """Combustible -> Neumáticos -> Comparador, en el mismo orden que main.navigate_to."""
    root = tk_root()
    fuel = m_fuel.FuelStrategyModule(root, colors=COLORS)
    tyre = m_tyre.TyreStrategyModule(root, colors=COLORS)
    charts = m_charts.StrategyChartsModule(root, colors=COLORS)
    fuel.on_session_data_updated(sd)
    if fuel_over:
        for k, v in fuel_over.items():
            getattr(fuel, k).set(v)
        fuel._on_params_changed()
    fd = fuel.get_fuel_strategy_data()
    tyre.on_session_data_updated(sd)
    if tyre_over:
        for k, v in tyre_over.items():
            getattr(tyre, k).set(v)
    tyre.on_fuel_strategy_updated(fd)
    charts.on_session_data_updated(sd)
    charts.on_fuel_strategy_updated(fd)
    charts.on_tyre_strategy_updated(tyre.get_tyre_strategy_data())
    return fuel, tyre, charts, fd
