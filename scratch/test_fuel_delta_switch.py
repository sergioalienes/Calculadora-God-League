import sys, os, json
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "e:/Calculadora God League")

from pathlib import Path
from modules.live_control import LiveControlModule
from main import CalculadoraApp

app = CalculadoraApp()
app.withdraw()

# Load Road America
champ_mod = app._modules["championship"]
champ_mod.load_session_by_names("God League", "Road America")
sdata = champ_mod.get_session_data()

charts_mod = app._modules["charts"]
charts_mod.on_session_data_updated(sdata)
saved_strats = charts_mod._load_saved_strategies_dict()

live_mod: LiveControlModule = app._modules["live"]
live_mod.on_session_data_updated(sdata)
fuel_mod = app._modules["fuel"]
live_mod.on_fuel_strategy_updated(fuel_mod.get_fuel_strategy_data())
live_mod.on_strategies_updated(saved_strats)

p = live_mod.pilots[0]

print("=== TEST DE CAMBIO DE ESTRATEGIAS Y DELTA DE COMBUSTIBLE ===")
# Simular coche en Vuelta 5 con 45.0 L
p._var_quick_lap.set("5")
p._var_quick_fuel.set("45.0")
p._submit_quick_meta()

results = {}
for strat in ["E1", "E2", "E3"]:
    p._var_selected_strategy.set(strat)
    p._apply_selected_strategy()
    
    tgt = p.active_strategy.get("target_cons")
    fuel_plan = p.active_strategy.get("fuel_plan")
    planned_v5 = fuel_plan[4] if (fuel_plan and len(fuel_plan) >= 5) else None
    hud_delta = p._lbl_delta_fuel.cget("text")
    hud_status = p._lbl_hud_status.cget("text")
    hud_cons = p._lbl_cons_stint.cget("text")

    results[strat] = {
        "target_cons": tgt,
        "planned_fuel_v5": planned_v5,
        "hud_delta": hud_delta,
        "hud_status": hud_status,
        "hud_cons": hud_cons,
    }

    print(f"\nEstrategia: {strat}")
    print(f"  Target cons: {tgt}")
    print(f"  Combustible previsto en V5: {planned_v5:.2f} L" if planned_v5 else "  Combustible previsto en V5: None")
    print(f"  Delta HUD en V5 (45.0 L reales): {hud_delta}")
    print(f"  Estado HUD: {hud_status}")
    print(f"  Consumo texto: {hud_cons}")

# Verificaciones
assert results["E1"]["target_cons"][0] != results["E2"]["target_cons"][0], "ERROR: E1 y E2 deben tener targets de consumo diferentes debido al rebufo!"
assert results["E1"]["planned_fuel_v5"] != results["E2"]["planned_fuel_v5"], "ERROR: E1 y E2 deben prever combustibles diferentes en la vuelta 5!"
assert results["E1"]["hud_delta"] != results["E2"]["hud_delta"], "ERROR: El Delta mostrado en el HUD DEBE CAMBIAR al cambiar de estrategia!"

print("\n✔ ¡VERIFICACIÓN EXITOSA! Los Deltas y consumos objetivos cambian reactivamente según la estrategia cargada.")
app.destroy()
