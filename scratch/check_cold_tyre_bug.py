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

# Let's test a 2-stop strategy: p1=10, p2=18
# And 1-stop strategy: p1=13
for stops, p1, p2, comps in [(1, 13, 0, ['soft', 'hard']), (2, 10, 18, ['soft', 'hard', 'hard'])]:
    print(f"\n==================== {stops} PARADA(S) ====================")
    res_no = mod._simulate_strategy(num_stops=stops, p1=p1, p2=p2, stint_comps=comps, draft_enabled=False)
    
    # Try different draft segments:
    # Segment A: V1-V5 (includes cold tyre lap V1)
    res_df_v1 = mod._simulate_strategy(num_stops=stops, p1=p1, p2=p2, stint_comps=comps, draft_enabled=True, draft_segments=[{'start': 1, 'end': 5}])
    
    # Segment B: V5-V10 (does not include V1)
    res_df_v5 = mod._simulate_strategy(num_stops=stops, p1=p1, p2=p2, stint_comps=comps, draft_enabled=True, draft_segments=[{'start': 5, 'end': 10}])

    # Segment C: V11-V15 (includes out-lap V11 of Stint 2 if p1=10)
    res_df_v11 = mod._simulate_strategy(num_stops=stops, p1=p1, p2=p2, stint_comps=comps, draft_enabled=True, draft_segments=[{'start': 11, 'end': 15}])

    print(f"--- Sin rebufo ---")
    for i, t in enumerate(res_no['lap_times']):
        lap = i + 1
        # highlight cold tyre laps: lap 1, lap p1+1, lap p2+1
        cold = " [RUEDA FRIA]" if lap in [1, p1+1, p2+1] else ""
        print(f"V{lap:02d}: {t:.3f}s{cold}")

    print(f"\n--- Con rebufo V1-V5 ---")
    for i, t in enumerate(res_df_v1['lap_times']):
        lap = i + 1
        cold = " [RUEDA FRIA]" if lap in [1, p1+1, p2+1] else ""
        delta = t - res_no['lap_times'][i]
        d_str = f" (delta: {delta:+.3f}s)" if abs(delta) > 0.001 else ""
        print(f"V{lap:02d}: {t:.3f}s{cold}{d_str}")

    print(f"\n--- Con rebufo V11-V15 ---")
    for i, t in enumerate(res_df_v11['lap_times']):
        lap = i + 1
        cold = " [RUEDA FRIA]" if lap in [1, p1+1, p2+1] else ""
        delta = t - res_no['lap_times'][i]
        d_str = f" (delta: {delta:+.3f}s)" if abs(delta) > 0.001 else ""
        print(f"V{lap:02d}: {t:.3f}s{cold}{d_str}")
