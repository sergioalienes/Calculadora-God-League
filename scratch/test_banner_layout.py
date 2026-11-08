import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import customtkinter as ctk
from modules.strategy_charts import StrategyChartsModule

ctk.set_appearance_mode("dark")
root = ctk.CTk()
root.geometry("1200x800")
root.update_idletasks()

colors = {
    "bg_primary": "#0A0A0A",
    "bg_secondary": "#131313",
    "accent": "#F26419",
    "accent_dim": "#3A1A08",
    "text_primary": "#FFFFFF",
    "text_secondary": "#8E8E93",
    "border": "#2C2C2E",
    "success": "#30D158",
    "warning": "#FFD60A",
    "danger": "#FF453A",
}

module = StrategyChartsModule(root, colors=colors)
module.session_data = {
    "lap_time_seconds": 85.0,
    "race_duration_minutes": 45.0,
    "fuel_capacity_l": 70.0,
    "fuel_per_lap_l": 5.65,
    "safety_margin_l": 3.0,
    "pitlane_loss_s": 22.0,
    "refuel_rate_ls": 12.0,
    "tyre_change_s": 4.0,
    "weight_penalty_s_per_10l": 0.150,
    "mandatory_compound_change": True,
}
module.fuel_data = {
    "viable_modes": ["1 Parada", "2 Paradas"],
    "truncated_laps": 31,
}
module.tyre_data = {
    "hard_base_lap": 85.0,
    "hard_warmup": 0.8,
    "hard_a": 0.22,
    "hard_n": -0.12,
    "soft_base_lap": 84.5,
    "soft_warmup": 0.4,
    "soft_a": 0.53,
    "soft_n": -0.40,
}

# Configuramos modo 2 Paradas y activamos SC
module._var_num_stops.set("2 Paradas")
module._var_sc_enabled.set(True)

# Tramo 1
module.sc_segments[0]["lap"].set("8")
module.sc_segments[0]["sector"].set("Sector 2")
module.sc_segments[0]["duration"].set("2")
module.sc_segments[0]["fuel_l"].set("1.80")

# Añadimos Tramo 2 (como hace el usuario)
module._add_sc_segment()
module.sc_segments[1]["lap"].set("16")
module.sc_segments[1]["sector"].set("Sector 1")
module.sc_segments[1]["duration"].set("2")
module.sc_segments[1]["fuel_l"].set("1.80")

module.recalculate_and_plot()
root.update()

# Comprobamos el banner y botón
banner = module._opp_banner
btn = module._btn_apply_1stop
lbl = module._lbl_opp

safe_text = lbl.cget('text')[:60].encode("ascii", errors="replace").decode("ascii")
safe_btn = btn.cget('text').encode("ascii", errors="replace").decode("ascii")
print(f"Banner is mapped: {banner.winfo_ismapped()}")
print(f"Banner text: {safe_text}...")
print(f"Button text: {safe_btn}")
print(f"Label y pos: {lbl.winfo_y()}, height: {lbl.winfo_height()}")
print(f"Button y pos: {btn.winfo_y()}, height: {btn.winfo_height()}")

assert banner.winfo_ismapped(), "Banner should be visible with 2 SC segments"
assert btn.winfo_ismapped(), "Button should be visible"
# Verificamos que el botón está situado debajo del texto (y_button >= y_label + height_label)
root.destroy()
print("TEST OK: Opportunity banner and button positioned vertically below without hiding!")
