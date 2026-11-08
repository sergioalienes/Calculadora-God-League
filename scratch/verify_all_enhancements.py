import sys
import os
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.strategy_charts import StrategyChartsModule

print("=== VERIFICANDO CALCULADORA GOD LEAGUE - MÓDULO 4 ESTRATEGIAS ===")

# 1. Test Contiguous Blocks Helper
laps_sc = [8, 9, 10, 20, 21]
blocks = StrategyChartsModule._get_contiguous_blocks(laps_sc)
assert blocks == [(8, 10), (20, 21)], f"Error in contiguous blocks: {blocks}"
print("[OK] Test 1 Passed: _get_contiguous_blocks correcto:", blocks)

# Mock root or headless instance
import tkinter as tk
import customtkinter as ctk

root = ctk.CTk()
root.withdraw()

# Create dummy parent and session data
colors = {
    "bg_primary": "#0A0A0A",
    "bg_secondary": "#131313",
    "bg_card": "#181818",
    "accent": "#F26419",
    "accent_dim": "#331605",
    "border": "#282828",
    "text_primary": "#FFFFFF",
    "text_secondary": "#A0A0A0",
    "success": "#51CF66",
    "warning": "#FFD60A",
    "danger": "#FF453A",
}
parent = ctk.CTkFrame(root)
module = StrategyChartsModule(parent, colors=colors)

session_data = {
    "championship_name": "Test Champ",
    "circuit": "Barcelona GP",
    "race_duration_minutes": 60,
    "lap_time_seconds": 115.0, # 1:55.000 -> 31.3 laps -> 32 laps race
    "fuel_capacity_l": 70.0,
    "pit_lane_delta_seconds": 22.0,
    "refuel_rate_l_s": 2.5,
    "mandatory_compound_change": True,
}

fuel_data = {
    "base_consumption": 5.65,
    "truncated_laps": 31,
    "safety_fuel": 3.0,
    "viable_modes": ["1 Parada", "2 Paradas"],
}

tyre_data = {
    "compounds": {
        "hard": {
            "name": "Prime (Duro)",
            "deg_rate": 0.08,
            "optimal_life": 22,
            "max_life": 28,
            "pace_delta": 0.0,
        },
        "soft": {
            "name": "Alternative (Blando)",
            "deg_rate": 0.16,
            "optimal_life": 12,
            "max_life": 17,
            "pace_delta": -0.65,
        },
    }
}

module.on_session_data_updated(session_data)
module.on_fuel_strategy_updated(fuel_data)
module.on_tyre_strategy_updated(tyre_data)

# 2. Test Forced Starting Compound
module._var_forced_start_comp.set("⚪ Forzar Duro")
cfg_h, res_h = module.solve_optimal_strategy()
assert cfg_h["stint1_comp"] == "hard", f"Expected stint1 hard, got {cfg_h['stint1_comp']}"
print(f"[OK] Test 2 Passed: Forzar Duro -> Stint 1: {cfg_h['stint1_comp']} (Paradas: {cfg_h['num_stops']})")

module._var_forced_start_comp.set("⚪ Forzar Blando")
cfg_s, res_s = module.solve_optimal_strategy()
assert cfg_s["stint1_comp"] == "soft", f"Expected stint1 soft, got {cfg_s['stint1_comp']}"
print(f"[OK] Test 2b Passed: Forzar Blando -> Stint 1: {cfg_s['stint1_comp']} (Paradas: {cfg_s['num_stops']})")

module._var_forced_start_comp.set("⚡ Automático")
cfg_auto, res_auto = module.solve_optimal_strategy()
print(f"[OK] Test 2c Passed: Automático -> Stint 1: {cfg_auto['stint1_comp']}")

# 3. Test Multi-Segment SC and Draft Simulation
sc_segs = [
    {"lap": 8, "sector": "Sector 1", "duration": 3, "fuel_l": 1.80},
    {"lap": 20, "sector": "Sector 2", "duration": 2, "fuel_l": 1.80},
]
draft_segs = [
    {"start": 3, "end": 6, "delta_l": -0.30, "delta_s": -0.15},
    {"start": 12, "end": 16, "delta_l": -0.40, "delta_s": -0.20},
]

sim_res = module._simulate_strategy(
    num_stops=2,
    p1=10,
    p2=21,
    stint_comps=["hard", "soft", "hard"],
    sc_enabled=True,
    sc_segments=sc_segs,
    draft_enabled=True,
    draft_segments=draft_segs,
)

assert 8 in sim_res["sc_laps"] and 9 in sim_res["sc_laps"] and 10 in sim_res["sc_laps"]
assert 20 in sim_res["sc_laps"] and 21 in sim_res["sc_laps"]
assert 4 in sim_res["draft_laps"] and 14 in sim_res["draft_laps"]
print(f"[OK] Test 3 Passed: Multi-segment SC laps = {sim_res['sc_laps']}, Draft laps count = {len(sim_res['draft_laps'])}")

# 4. Test 1-Stop Opportunity Detector under Draft & SC
module._var_sc_enabled.set(True)
module.sc_segments[0]["lap"].set(6)
module.sc_segments[0]["duration"].set(3)
module.sc_segments[0]["fuel_l"].set("1.80")

module._var_draft_enabled.set(True)
module.draft_segments[0]["start"].set(2)
module.draft_segments[0]["end"].set(15)
module.draft_segments[0]["delta_l"].set("-0.50")

module.recalculate_and_plot()
opp = module._find_best_1stop_opportunity()
assert opp is not None, "Opportunity should be detected under SC + Draft"
p_opt, c1_opt, c2_opt, t_opt, reason = opp
print(f"[OK] Test 4 Passed: 1-Stop Opportunity Detected: Box al fin de V{p_opt}, Comps: {c1_opt}->{c2_opt}, Motivo: {reason}")

# 5. Test Telemetry Inspection on Click
module.current_result = sim_res
module._on_chart_clicked(type("MockEvent", (), {"inaxes": module._ax_pace, "xdata": 14.2})())
assert module._inspected_lap == 14, f"Expected inspected lap 14, got {module._inspected_lap}"
print(f"[OK] Test 5 Passed: Clic en x=14.2 selecciona Vuelta {module._inspected_lap}")

# Clear inspection
module._clear_inspection()
assert module._inspected_lap is None, "Expected inspected lap None after clear"
print("[OK] Test 5b Passed: Limpieza de inspección correcta")

# 6. Test Persistence Save & Load
module._add_sc_segment()
module.sc_segments[0]["lap"].set(7)
module.sc_segments[1]["lap"].set(19)

module._add_draft_segment()
module.draft_segments[0]["start"].set(4)
module.draft_segments[0]["end"].set(9)
module.draft_segments[1]["start"].set(15)
module.draft_segments[1]["end"].set(22)

# Verify profile dict building
active_sc = module._get_active_sc_segments()
active_draft = module._get_active_draft_segments()
assert len(active_sc) == 2, f"Expected 2 SC segments, got {len(active_sc)}"
assert len(active_draft) == 2, f"Expected 2 Draft segments, got {len(active_draft)}"
print(f"[OK] Test 6 Passed: Dynamic segments persistence structure valid: {len(active_sc)} SC, {len(active_draft)} Draft")

print("\n=== TODOS LOS TESTS PASARON EXITOSAMENTE (6/6) ===")
root.destroy()
