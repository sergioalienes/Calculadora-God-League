import sys, os, json
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "e:/Calculadora God League")

from pathlib import Path
from modules.live_control import PilotLiveCard, LiveControlModule
from main import CalculadoraApp

app = CalculadoraApp()
app.withdraw()

# Load Road America
champ_mod = app._modules["championship"]
champ_mod.load_session_by_names("God League", "Road America")
sdata = champ_mod.get_session_data()

# Update charts_mod session data and get saved strategies
charts_mod = app._modules["charts"]
charts_mod.on_session_data_updated(sdata)
saved_strats = charts_mod._load_saved_strategies_dict()

# Update live_mod
live_mod: LiveControlModule = app._modules["live"]
live_mod.on_session_data_updated(sdata)
fuel_mod = app._modules["fuel"]
live_mod.on_fuel_strategy_updated(fuel_mod.get_fuel_strategy_data())
live_mod.on_strategies_updated(saved_strats)

p = live_mod.pilots[0]

# Set pilot with E1 strategy
p._var_selected_strategy.set("E1")
p._apply_selected_strategy()

print("ESTRATEGIA INICIAL CARGADA E1:")
print(f"  num_stops: {p.active_strategy['num_stops']}")
print(f"  p1: {p.active_strategy['p1']}, p2: {p.active_strategy['p2']}")
print(f"  stint1: {p.active_strategy['stint1_comp']}")
print(f"  stint2: {p.active_strategy['stint2_comp']}")
print(f"  stint3: {p.active_strategy['stint3_comp']}")

# Let's test at different laps: Lap 5, Lap 10, Lap 13, Lap 14, Lap 18, Lap 20
for test_lap in [5, 10, 13, 14, 18, 20]:
    print(f"\n==================== PROBANDO EN VUELTA {test_lap} ====================")
    # Restore E1 before each test
    p._var_selected_strategy.set("E1")
    p._apply_selected_strategy()
    
    p.meta_records = [{"lap": test_lap, "fuel": 30.0, "cons": 5.4}]
    p._recalculate_all()
    p.solve_tactical_strategy()
    tac = p.tactical_result
    if not tac:
        print("  NO SE ENCONTRÓ PLAN TÁCTICO!")
        continue
    print(f"  Táctico sugerido:")
    print(f"    rem_stops: {tac.get('rem_stops')}, full_stops: {tac.get('full_stops')}")
    print(f"    p1: {tac.get('p1')}, p2: {tac.get('p2')}")
    print(f"    stint1: {tac.get('stint1_comp')}, stint2: {tac.get('stint2_comp')}, stint3: {tac.get('stint3_comp')}")
    print(f"    full_stints: {tac.get('full_stints')}")
    print(f"    full_pit_laps: {tac.get('full_pit_laps')}")
    
    # Promovemos
    p.promote_tactical_strategy()
    print(f"  Tras PROMOVER:")
    print(f"    active_strategy num_stops: {p.active_strategy.get('num_stops')}")
    print(f"    active_strategy p1: {p.active_strategy.get('p1')}, p2: {p.active_strategy.get('p2')}")
    print(f"    active_strategy stint1: {p.active_strategy.get('stint1_comp')}")
    print(f"    active_strategy stint2: {p.active_strategy.get('stint2_comp')}")
    print(f"    active_strategy stint3: {p.active_strategy.get('stint3_comp')}")

    # Chequeamos cómo lo vería el usuario en el PLAN (líneas 1188-1198)
    stops = p.active_strategy.get("num_stops", 1)
    p1 = p.active_strategy.get("p1", 15)
    p2 = p.active_strategy.get("p2", 0)
    c1 = p.active_strategy.get("stint1_comp")
    c2 = p.active_strategy.get("stint2_comp")
    c3 = p.active_strategy.get("stint3_comp")
    tot_laps = live_mod.race_header.get_race_state()["total_projected_laps"]
    if stops == 0 or p1 <= 0 or p1 >= tot_laps:
        stints = [(0, tot_laps, c1)]
    elif stops == 1:
        stints = [(0, p1, c1), (p1, tot_laps, c2)]
    else:
        stints = [(0, p1, c1), (p1, p2, c2), (p2, tot_laps, c3)]
    print(f"    Stints resultantes en el PLAN visual:")
    for st in stints:
        print(f"      V{st[0]} a V{st[1]}: {st[2]}")

app.destroy()
