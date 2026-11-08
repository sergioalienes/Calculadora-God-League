import sys
from pathlib import Path
root_dir = Path(".").resolve()
sys.path.insert(0, str(root_dir))
import json
import customtkinter as ctk
import main
from modules.strategy_charts import StrategyChartsModule

ctk.set_appearance_mode("dark")
root = ctk.CTk()
root.withdraw()

mod = StrategyChartsModule(root, colors=main.COLORS.copy())
mod.session_data = {
    "circuit": "Road America",
    "championship_name": "God League",
    "lap_time_seconds": 105.0,
    "race_duration_minutes": 45.0,
    "fuel_capacity_l": 70.0,
    "fuel_per_lap_l": 5.4,
    "safety_margin_l": 0.4,
    "pitlane_loss_s": 29.0,
    "refuel_rate_ls": 12.0,
    "tyre_change_s": 4.0,
    "weight_penalty_s_per_10l": 0.02,
}
mod.fuel_data = json.loads(Path("profiles/God League/Road America_fuel.json").read_text(encoding="utf-8"))
mod.tyre_data = json.loads(Path("profiles/God League/Road America_tyres.json").read_text(encoding="utf-8"))
mod._refresh_models_selectors()
mod._on_strat_fuel_model_changed("Modelo 1", trigger_plot=False)
mod._on_strat_tyre_model_changed("Modelo 1", trigger_plot=False)

mod._var_sc_enabled.set(True)
mod.sc_segments.clear()
mod.sc_segments.append({
    "lap": ctk.StringVar(value="8"),
    "duration": ctk.StringVar(value="3"),
    "sector": ctk.StringVar(value="Sector 1"),
    "fuel_l": ctk.StringVar(value="2.0"),
    "enabled": ctk.BooleanVar(value=True),
})

print("=" * 70)
print("TEST 1: OPTIMIZER CHOOSES FREE SC STOP")
print("=" * 70)
cfg, res = mod.solve_optimal_strategy()
print("Optimal cfg:", cfg)
assert cfg is not None, "Optimizer should return a config!"
p_info = res["pit_info"]
print(f"Optimal res: Laps={res['total_laps']}, RaceTime={res['total_race_time']:.2f}s, PitInfo={p_info}")
has_free_sc = any(item[3] for item in p_info)
assert has_free_sc, f"Optimal strategy MUST choose a free pit stop under SC! Got: {p_info}"
assert res["total_laps"] == 20, f"Optimal strategy with free SC stop must complete 20 laps! Got: {res['total_laps']}"
print(">>> TEST 1 PASSED: Optimizer successfully selected free SC stop and 20 laps!")

print("\n" + "=" * 70)
print("TEST 2: 1-STOP OPPORTUNITY DETECTOR SELECTS SC WINDOW")
print("=" * 70)
mod._var_num_stops.set("2 Paradas")
mod.current_result = res
cand = mod._find_best_1stop_opportunity()
assert cand is not None, "1-stop opportunity should be found!"
best_p, best_c1, best_c2, best_time, factor, best_res = cand
print(f"1-stop candidate: pit lap={best_p}, comps={best_c1}-{best_c2}, factor={factor}, laps={best_res['total_laps']}")
assert best_p in (9, 10), f"1-stop candidate should pit in free SC window (lap 9 or 10)! Got: {best_p}"
assert best_res["pit_info"][0][3] is True, "Candidate stop must be free under SC (is_sc_gratis == True)!"
assert best_res["total_pit_time"] == 0.0, "Candidate total_pit_time must be 0.0!"
print(">>> TEST 2 PASSED: 1-stop opportunity detector chose free SC window!")

print("\n" + "=" * 70)
print("TEST 3: POST-SC RACE TIME & PIT ACCOUNTING")
print("=" * 70)
# Case A: Free stop during SC (lap 9)
r_sc9 = mod._simulate_strategy(num_stops=1, p1=9, p2=0, stint_comps=["soft", "hard"], sc_enabled=True, sc_segments=mod._get_active_sc_segments())
ps9 = r_sc9["post_sc_info"][0]
print(f"Stop V9 (in SC): rem_laps={ps9['rem_laps']}, track_s={ps9['post_sc_track_s']:.1f}s, pit_s={ps9['post_sc_pit_s']:.1f}s, n_pits={ps9['n_pits_post']}")
assert ps9["post_sc_pit_s"] == 0.0, "Post-SC pit time for stop in SC must be 0.0s!"
assert ps9["n_pits_post"] == 0, "n_pits_post must be 0 for stop in SC!"

# Case B: Stop at SC ending lap (lap 11, pays normal box time)
r_sc11 = mod._simulate_strategy(num_stops=1, p1=11, p2=0, stint_comps=["soft", "hard"], sc_enabled=True, sc_segments=mod._get_active_sc_segments())
ps11 = r_sc11["post_sc_info"][0]
print(f"Stop V11 (SC ending): rem_laps={ps11['rem_laps']}, track_s={ps11['post_sc_track_s']:.1f}s, pit_s={ps11['post_sc_pit_s']:.1f}s, n_pits={ps11['n_pits_post']}")
assert ps11["post_sc_pit_s"] == 35.0, f"Stop at SC ending lap must be included in post-SC pit time! Got: {ps11['post_sc_pit_s']}"
assert ps11["n_pits_post"] == 1, f"n_pits_post must be 1 for stop at SC ending lap! Got: {ps11['n_pits_post']}"

# Case C: Stop at lap 15 (green after SC)
r_sc15 = mod._simulate_strategy(num_stops=1, p1=15, p2=0, stint_comps=["soft", "hard"], sc_enabled=True, sc_segments=mod._get_active_sc_segments())
ps15 = r_sc15["post_sc_info"][0]
print(f"Stop V15 (green): rem_laps={ps15['rem_laps']}, track_s={ps15['post_sc_track_s']:.1f}s, pit_s={ps15['post_sc_pit_s']:.1f}s, n_pits={ps15['n_pits_post']}")
assert ps15["post_sc_pit_s"] == 35.0, "Post-SC pit time for stop in green must be 35.0s!"
assert ps15["n_pits_post"] == 1, "n_pits_post must be 1!"

# Case D: 2 stops: Stop 1 at lap 9 (free under SC), Stop 2 at lap 15 (green)
r_sc_2st = mod._simulate_strategy(num_stops=2, p1=9, p2=15, stint_comps=["soft", "hard", "soft"], sc_enabled=True, sc_segments=mod._get_active_sc_segments())
ps_2st = r_sc_2st["post_sc_info"][0]
print(f"2 stops (V9 SC gratis + V15 green): rem_laps={ps_2st['rem_laps']}, track_s={ps_2st['post_sc_track_s']:.1f}s, pit_s={ps_2st['post_sc_pit_s']:.1f}s, n_pits={ps_2st['n_pits_post']}")
assert ps_2st["post_sc_pit_s"] == 35.0, "Post-SC pit time should only include the green stop (35.0s)!"
assert ps_2st["n_pits_post"] == 1, "n_pits_post should be 1!"
print(">>> TEST 3 PASSED: Post-SC pit accounting verified across all edge cases!")

print("\n" + "=" * 70)
print("TEST 4: KPI DELTA ÓPTIMA MOTORSPORT RANKING")
print("=" * 70)
mod.optimal_result = res

# 1. User has optimal 1-stop @ V10 (20 laps) -> delta should be 0.000s (Óptima)
mod._var_num_stops.set("1 Parada")
mod._var_p1.set(10)
mod._var_stint1_comp.set("Blando")
mod._var_stint2_comp.set("Duro")
mod.recalculate_and_plot()
t_kpi_opt = mod._lbl_kpi_delta_opt.cget("text")
print("User 20 laps (Optimal) vs Opt 20 laps:", t_kpi_opt)
assert "0.000s" in t_kpi_opt, f"Expected 0.000s (ÓPTIMA), got: {t_kpi_opt}"

# 2. User has green 1-stop @ V15 (19 laps) -> delta should be -1v (DOBLADO)
mod._var_p1.set(15)
mod.recalculate_and_plot()
t_kpi_19 = mod._lbl_kpi_delta_opt.cget("text")
print("User 19 laps vs Opt 20 laps:", t_kpi_19)
assert "DOBLADO" in t_kpi_19, f"Expected -1v (DOBLADO), got: {t_kpi_19}"

# 3. Reference is 19 laps, user is 20 laps -> delta should be +1v (SUPERIOR)
mod.optimal_result = {"total_laps": 19, "total_race_time": 2709.32}
mod._var_p1.set(10)
mod.recalculate_and_plot()
t_kpi_sup = mod._lbl_kpi_delta_opt.cget("text")
print("User 20 laps vs Opt 19 laps:", t_kpi_sup)
assert "SUPERIOR" in t_kpi_sup and "+1v" in t_kpi_sup, f"Expected +1v (SUPERIOR), got: {t_kpi_sup}"
print(">>> TEST 4 PASSED: KPI Delta Óptima reflects motorsport reality in all comparisons!")

print("\n" + "=" * 70)
print("ALL VERIFICATION TESTS COMPLETED SUCCESSFULLY!")
print("=" * 70)
