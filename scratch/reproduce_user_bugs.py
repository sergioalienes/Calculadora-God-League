import os, sys, json
os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, ".")
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
from main import CalculadoraApp

app = CalculadoraApp()
app.withdraw()

champ_mod = app._modules["championship"]
champ_mod.load_session_by_names("God League", "Road America")

# Navigate to charts first to load strategies from disk into memory
app.navigate_to("charts")

# Navigate to live
app.navigate_to("live")
live_mod = app._modules["live"]

print("=== TEST 1: DELTA DE COMBUSTIBLE AL CAMBIAR ESTRATEGIAS ===")
p = live_mod.pilots[0]
print(f"Piloto: {p._var_name.get()}")

# Configurar vuelta 5 con 45L
p._var_quick_lap.set("5")
p._var_quick_fuel.set("45.0")
p._submit_quick_meta()

for strat in ["E1", "E2", "E3"]:
    p._var_selected_strategy.set(strat)
    p._apply_selected_strategy()
    t_cons = p.active_strategy.get("target_cons")
    d_fuel = p._lbl_delta_fuel.cget("text")
    c_text = p._lbl_cons_stint.cget("text")
    print(f"\nEstrategia '{strat}':")
    print(f"  active_strategy.target_cons = {t_cons}")
    print(f"  Delta combustible HUD = {d_fuel}")
    print(f"  Consumo texto = {c_text}")

print("\n=== TEST 2: PROMOCIÓN DE ESTRATEGIA A MITAD DE STINT ===")
p._var_selected_strategy.set("E1")
p._apply_selected_strategy()
print(f"E1 Plan inicial: num_stops={p.active_strategy['num_stops']}, p1={p.active_strategy['p1']}, p2={p.active_strategy['p2']}")
print(f"  Comps: S1={p.active_strategy['stint1_comp']}, S2={p.active_strategy['stint2_comp']}, S3={p.active_strategy['stint3_comp']}")

# El coche para en V13, y ahora rueda en V18 (mitad de stint 2) con neumático Duro
p._var_quick_lap.set("18")
p._var_quick_fuel.set("35.0")
p._submit_quick_meta()

print(f"\nPiloto en V18 (mitad de Stint 2):")
print(f"Goma montada calculada: {p.get_current_mounted_compound()}")

# Recalcular táctica
p.solve_tactical_strategy()
tac = p.tactical_result
print(f"\nResultado táctico sugerido:")
if tac:
    print(f"  rem_stops: {tac.get('rem_stops')}, full_stops: {tac.get('full_stops')}")
    print(f"  p1: {tac.get('p1')}, p2: {tac.get('p2')}")
    print(f"  stint1: {tac.get('stint1_comp')}, stint2: {tac.get('stint2_comp')}, stint3: {tac.get('stint3_comp')}")
    print(f"  full_stints: {tac.get('full_stints')}")
    print(f"  descripción:\n{p._lbl_tac_desc.cget('text')}")

    # Ahora promovemos
    print("\n--- Promoviendo estrategia táctica ---")
    p.promote_tactical_strategy()
    print(f"active_strategy tras promover:")
    print(f"  num_stops: {p.active_strategy.get('num_stops')}")
    print(f"  p1: {p.active_strategy.get('p1')}, p2: {p.active_strategy.get('p2')}")
    print(f"  stint1_comp: {p.active_strategy.get('stint1_comp')}")
    print(f"  stint2_comp: {p.active_strategy.get('stint2_comp')}")
    print(f"  stint3_comp: {p.active_strategy.get('stint3_comp')}")

    # Cómo queda dibujado en el PLAN
    plan_stops = p.active_strategy.get('num_stops', 1)
    plan_p1 = p.active_strategy.get('p1', 15)
    plan_p2 = p.active_strategy.get('p2', 0)
    c1 = p.active_strategy.get('stint1_comp')
    c2 = p.active_strategy.get('stint2_comp')
    c3 = p.active_strategy.get('stint3_comp')
    tot_laps = live_mod.race_header.get_race_state()['total_projected_laps']
    
    if plan_stops == 1:
        stints = [(0, plan_p1, c1), (plan_p1, tot_laps, c2)]
    else:
        stints = [(0, plan_p1, c1), (plan_p1, plan_p2, c2), (plan_p2, tot_laps, c3)]
    print(f"\nStints que renderiza el PLAN tras promover:")
    for s in stints:
        print(f"  V{s[0]} a V{s[1]}: {s[2]}")

app.destroy()
