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

print("--- 1 STOP (P1=15), hard -> soft ---")
res_no = mod._simulate_strategy(num_stops=1, p1=15, p2=0, stint_comps=['hard', 'soft'], draft_enabled=False)
print("Without draft:")
for i in range(len(res_no['lap_times'])):
    lap = i + 1
    t = res_no['lap_times'][i]
    cold = " [RUEDA FRIA]" if lap in [1, 16] else ""
    print(f"V{lap:02d}: {t:.3f}s{cold}")

# Now what if draft is on V3-V10?
print("\nWith draft V3-V10:")
res_df = mod._simulate_strategy(num_stops=1, p1=15, p2=0, stint_comps=['hard', 'soft'], draft_enabled=True, draft_segments=[{'start': 3, 'end': 10}])
for i in range(len(res_df['lap_times'])):
    lap = i + 1
    t = res_df['lap_times'][i]
    delta = t - res_no['lap_times'][i]
    cold = " [RUEDA FRIA]" if lap in [1, 16] else ""
    print(f"V{lap:02d}: {t:.3f}s{cold} (delta: {delta:+.3f}s)")
