"""
Script de verificación del bug reportado por el usuario:
Al estar en Stint 2 (V13) tras parar en V10 (Duro -> Blando),
recalcular la táctica visualmente se come el Stint 1 y asume que
desde V0 se ha corrido con Blando.
"""
import os
import sys

os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import CalculadoraApp
from modules.live_control import LiveControlModule

def inspect_bug():
    print("=== INSPECCIONANDO BUG REPORTADO POR EL USUARIO ===")
    app = CalculadoraApp()
    app.withdraw()

    live_mod: LiveControlModule = app._modules["live"]
    p = live_mod.pilots[0]

    # Configurar carrera de 30 vueltas
    live_mod.race_header._var_leader_lap.set("13")
    live_mod.race_header._var_time_rem_str.set("00:25:00")
    live_mod.race_header._on_params_changed()

    # Estrategia inicial asignada (PLAN): 2 paradas
    # Stint 1 (V0 - V10): Duro
    # Stint 2 (V10 - V20): Blando
    # Stint 3 (V20 - V30): Blando
    p.active_strategy = {
        "num_stops": 2,
        "p1": 10,
        "p2": 20,
        "stint1_comp": "hard",
        "stint2_comp": "soft",
        "stint3_comp": "soft",
        "target_cons": [5.65, 5.65, 5.65],
        "refuel_litres": [30.0, 30.0],
    }

    # Piloto en V13 (ya hizo la parada de V10 y ahora lleva Blando montado)
    p._var_mounted_comp.set("Alternative (Blando)")
    p._var_quick_lap.set("13")
    p._var_quick_fuel.set("42.0")
    p._submit_quick_meta()

    print(f"Estado antes de recalcular:")
    print(f"  Vuelta actual: {p.meta_records[-1]['lap']}")
    print(f"  Goma montada: {p._var_mounted_comp.get()}")
    print(f"  Plan asignado: {p.active_strategy['num_stops']} paradas (p1={p.active_strategy['p1']}, p2={p.active_strategy['p2']})")
    print(f"  Plan compuestos: S1={p.active_strategy['stint1_comp']}, S2={p.active_strategy['stint2_comp']}, S3={p.active_strategy['stint3_comp']}")

    # Ejecutar recálculo táctico
    print("\nEjecutando solve_tactical_strategy() en V13...")
    p.solve_tactical_strategy()

    print(f"\nResultado táctico generado (tactical_result):")
    for k, v in p.tactical_result.items():
        print(f"  {k}: {v}")

    # Ver qué dibuja get_stints para la fila táctica en _render_strategy_timeline:
    tac = p.tactical_result
    tot_laps = 30
    def get_stints(stops, p1, p2, c1, c2, c3):
        if stops == 0 or p1 <= 0 or p1 >= tot_laps:
            return [(0, tot_laps, c1)]
        elif stops == 1:
            p1_c = min(tot_laps, max(1, p1))
            return [(0, p1_c, c1), (p1_c, tot_laps, c2)]
        else:
            p1_c = min(tot_laps - 2, max(1, p1))
            p2_c = min(tot_laps, max(p1_c + 1, p2))
            return [(0, p1_c, c1), (p1_c, p2_c, c2), (p2_c, tot_laps, c3)]

    tac_stops = tac.get("num_stops", 1)
    tac_p1 = tac.get("p1", 15)
    tac_p2 = tac.get("p2", 0)
    tac_c1 = tac.get("stint1_comp")
    tac_c2 = tac.get("stint2_comp")
    tac_c3 = tac.get("stint3_comp")

    drawn_stints = get_stints(tac_stops, tac_p1, tac_p2, tac_c1, tac_c2, tac_c3)
    print(f"\nStints que dibuja la fila TÁCT en el monitor:")
    for s_start, s_end, s_comp in drawn_stints:
        print(f"  V{s_start} a V{s_end}: Compuesto {s_comp}")

    app.destroy()

if __name__ == "__main__":
    inspect_bug()
