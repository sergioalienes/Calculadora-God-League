import sys
from pathlib import Path
root_dir = Path('.').resolve()
sys.path.insert(0, str(root_dir))
import customtkinter as ctk
import main
from modules.strategy_charts import StrategyChartsModule
import json

ctk.set_appearance_mode('dark')
root = ctk.CTk()
root.withdraw()

mod = StrategyChartsModule(root, colors=main.COLORS.copy())
mod.session_data = {
    'circuit': 'Road America',
    'championship_name': 'God League',
    'lap_time_seconds': 105.0,
    'race_duration_minutes': 45.0,
    'fuel_capacity_l': 70.0,
    'fuel_per_lap_l': 5.4,
    'safety_margin_l': 0.4,
    'pitlane_loss_s': 29.0,
    'refuel_rate_ls': 12.0,
    'tyre_change_s': 4.0,
    'weight_penalty_s_per_10l': 0.02,
}
mod.fuel_data = json.loads(Path('profiles/God League/Road America_fuel.json').read_text(encoding='utf-8'))
mod.tyre_data = json.loads(Path('profiles/God League/Road America_tyres.json').read_text(encoding='utf-8'))
mod._refresh_models_selectors()
mod._on_strat_fuel_model_changed('Modelo 1', trigger_plot=False)
mod._on_strat_tyre_model_changed('Modelo 1', trigger_plot=False)

# 1. Test clean race optimal strategy
mod._var_sc_enabled.set(False)
mod._var_draft_enabled.set(False)
cfg_clean, res_clean = mod.solve_optimal_strategy()
print("=== Clean race optimal ===")
print("Stops:", cfg_clean['num_stops'], "p1:", cfg_clean['p1'], "p2:", cfg_clean['p2'], "time:", res_clean['total_race_time'])

# 2. Test optimal strategy with Rebufo V3-V12 enabled
mod._var_draft_enabled.set(True)
mod.draft_segments = [{'start': ctk.StringVar(value='3'), 'end': ctk.StringVar(value='12')}]
cfg_draft, res_draft = mod.solve_optimal_strategy()
print("\n=== Optimal with Rebufo V3-V12 ===")
print("Stops:", cfg_draft['num_stops'], "p1:", cfg_draft['p1'], "p2:", cfg_draft['p2'], "time:", res_draft['total_race_time'])

# 3. Test optimal strategy with SC enabled (V8 duration 3)
mod._var_draft_enabled.set(False)
mod._var_sc_enabled.set(True)
mod.sc_segments = [{'lap': ctk.StringVar(value='8'), 'sector': ctk.StringVar(value='Sector 2'), 'duration': ctk.StringVar(value='3'), 'fuel_l': ctk.StringVar(value='1.80'), 'enabled': True}]
cfg_sc, res_sc = mod.solve_optimal_strategy()
print("\n=== Optimal with Safety Car V8-V11 ===")
print("Stops:", cfg_sc['num_stops'], "p1:", cfg_sc['p1'], "p2:", cfg_sc['p2'], "time:", res_sc['total_race_time'])

# 4. Test optimal strategy with BOTH SC and Rebufo coexisting
mod._var_draft_enabled.set(True)
cfg_both, res_both = mod.solve_optimal_strategy()
print("\n=== Optimal with BOTH SC and Rebufo ===")
print("Stops:", cfg_both['num_stops'], "p1:", cfg_both['p1'], "p2:", cfg_both['p2'], "time:", res_both['total_race_time'])

# 5. Test 1-stop opportunity detection for Rebufo and Combined
cand_both = mod._find_best_1stop_opportunity()
print("\n=== 1-Stop Opportunity (Both active) ===")
print("Factor:", cand_both[4], "p:", cand_both[0], "c1:", cand_both[1], "c2:", cand_both[2])

mod._var_sc_enabled.set(False)
cand_df = mod._find_best_1stop_opportunity()
print("\n=== 1-Stop Opportunity (Rebufo only) ===")
print("Factor:", cand_df[4], "p:", cand_df[0], "c1:", cand_df[1], "c2:", cand_df[2])
