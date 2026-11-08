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

print("Active fuel model:", mod._var_strat_fuel_model.get())
print("Active tyre model:", mod._var_strat_tyre_model.get())
print("Fuel saving curve:", mod._get_fuel_saving_curve())
print("Draft saving L:", mod._get_draft_saving_l())

# Check 1 stop: p1=13
# Total laps for 45 min at 105s with 1 stop losing ~34s: ~26 laps (13 + 13)
# Let's test p1=13 without draft
res1 = mod._simulate_strategy(num_stops=1, p1=13, p2=0, stint_comps=['soft', 'hard'], draft_enabled=False)
print("\n--- 1 STOP (P1=13) WITHOUT DRAFT ---")
print("Total race time:", res1['total_race_time'])
print("Total laps:", res1['total_laps'])
for st in res1['stint_targets']:
    print(f"Stint {st['stint_num']} (Laps {st['start_v']}-{st['end_v']}): cons={st['avg_cons']:.3f} L/v, mode={st['mode_str'].encode('ascii', 'ignore').decode()}")
print("Lap 1-5 times:", [round(t, 3) for t in res1['lap_times'][:5]])

# Test p1=13 with draft in Stint 1 (laps 4-11, 8 laps)
res2 = mod._simulate_strategy(num_stops=1, p1=13, p2=0, stint_comps=['soft', 'hard'], draft_enabled=True, draft_segments=[{'start': 4, 'end': 11}])
print("\n--- 1 STOP (P1=13) WITH DRAFT (V4-V11) ---")
print("Total race time:", res2['total_race_time'])
print("Total laps:", res2['total_laps'])
for st in res2['stint_targets']:
    print(f"Stint {st['stint_num']} (Laps {st['start_v']}-{st['end_v']}): cons={st['avg_cons']:.3f} L/v, mode={st['mode_str'].encode('ascii', 'ignore').decode()}")
print("Lap 1-5 times:", [round(t, 3) for t in res2['lap_times'][:5]])

# Test 1 stop p1=14 (needs more saving)
res3 = mod._simulate_strategy(num_stops=1, p1=14, p2=0, stint_comps=['soft', 'hard'], draft_enabled=False)
print("\n--- 1 STOP (P1=14) WITHOUT DRAFT ---")
print("Total race time:", res3['total_race_time'])
for st in res3['stint_targets']:
    print(f"Stint {st['stint_num']} (Laps {st['start_v']}-{st['end_v']}): cons={st['avg_cons']:.3f} L/v, mode={st['mode_str'].encode('ascii', 'ignore').decode()}")
print("Lap 1-5 times:", [round(t, 3) for t in res3['lap_times'][:5]])

res4 = mod._simulate_strategy(num_stops=1, p1=14, p2=0, stint_comps=['soft', 'hard'], draft_enabled=True, draft_segments=[{'start': 3, 'end': 12}])
print("\n--- 1 STOP (P1=14) WITH DRAFT (V3-V12) ---")
print("Total race time:", res4['total_race_time'])
for st in res4['stint_targets']:
    print(f"Stint {st['stint_num']} (Laps {st['start_v']}-{st['end_v']}): cons={st['avg_cons']:.3f} L/v, mode={st['mode_str'].encode('ascii', 'ignore').decode()}")
print("Lap 1-5 times:", [round(t, 3) for t in res4['lap_times'][:5]])
