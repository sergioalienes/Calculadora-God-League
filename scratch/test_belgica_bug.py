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
p_circ = list(Path('profiles/God League').glob('*lgica.json'))[0]
circ_data = json.loads(p_circ.read_text(encoding='utf-8'))
p_fuel = list(Path('profiles/God League').glob('*lgica_fuel.json'))[0]
p_tyres = list(Path('profiles/God League').glob('*lgica_tyres.json'))[0]
p_strat = list(Path('profiles/God League').glob('*lgica_strategies.json'))[0]

mod.session_data = {
    'circuit': circ_data.get('circuit', 'Bélgica'),
    'championship_name': 'God League',
    'lap_time_seconds': 140.0,
    'race_duration_minutes': 45.0,
    'fuel_capacity_l': 70.0,
    'fuel_per_lap_l': 5.0,
    'safety_margin_l': 0.4,
    'pitlane_loss_s': 22.0,
    'refuel_rate_ls': 12.0,
    'tyre_change_s': 4.0,
    'weight_penalty_s_per_10l': 0.02,
}
mod.fuel_data = json.loads(p_fuel.read_text(encoding='utf-8'))
mod.tyre_data = json.loads(p_tyres.read_text(encoding='utf-8'))
strat_data = json.loads(p_strat.read_text(encoding='utf-8'))
p1_plus_1 = strat_data['P1 +1']

mod._refresh_models_selectors()
mod._on_strat_fuel_model_changed('Modelo 1', trigger_plot=False)
mod._on_strat_tyre_model_changed('Modelo 1', trigger_plot=False)

print("P1 +1 strategy:", p1_plus_1)

# Simulate P1 +1 WITHOUT draft
res_nodraft = mod._simulate_strategy(
    num_stops=p1_plus_1['num_stops'],
    p1=p1_plus_1['p1'],
    p2=p1_plus_1.get('p2', 0),
    stint_comps=[p1_plus_1['stint1_comp'], p1_plus_1['stint2_comp'], p1_plus_1.get('stint3_comp', 'hard')],
    draft_enabled=False
)

# Simulate P1 +1 WITH draft (V1..V13)
res_draft = mod._simulate_strategy(
    num_stops=p1_plus_1['num_stops'],
    p1=p1_plus_1['p1'],
    p2=p1_plus_1.get('p2', 0),
    stint_comps=[p1_plus_1['stint1_comp'], p1_plus_1['stint2_comp'], p1_plus_1.get('stint3_comp', 'hard')],
    draft_enabled=True,
    draft_segments=p1_plus_1['draft_segments']
)

print("\n--- Belgica P1 +1: Laps comparison ---")
for i in range(len(res_nodraft['lap_times'])):
    lap = i + 1
    t_no = res_nodraft['lap_times'][i]
    t_df = res_draft['lap_times'][i]
    d = t_df - t_no
    cold = " [RUEDA FRIA]" if lap in [1, p1_plus_1['p1'] + 1] else ""
    print(f"V{lap:02d}: Sin={t_no:.3f}s | Con={t_df:.3f}s | Delta={d:+.3f}s{cold}")
