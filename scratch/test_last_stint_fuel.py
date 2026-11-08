import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))
sys.stdout.reconfigure(encoding='utf-8')

from tkinter import messagebox
from main import CalculadoraApp
from modules.live_control import LiveControlModule, PilotLiveCard

def test_last_stint():
    print("=== TEST ESPECÍFICO: COMBUSTIBLE EN ÚLTIMO STINT ===")
    warning_calls = []
    messagebox.showwarning = lambda title, msg: warning_calls.append((title, msg))

    app = CalculadoraApp()
    app.withdraw()

    # Navegar a 'live'
    app.navigate_to("live")
    live_mod: LiveControlModule = app._modules.get("live")

    test_session = {
        "championship_name": "God League 2024",
        "circuit": "Watkins Glen",
        "pitlane_loss": 30.0,
        "pitlane_loss_s": 30.0,
        "fuel_capacity_l": 70.0,
        "refuel_rate_ls": 12.0,
        "tyre_change_s": 4.0,
        "tyre_change_time": 4.0,
        "lap_time_str": "01:24.500",
        "lap_time_seconds": 84.5,
        "race_duration_min": 35.0,
        "mandatory_compound_change": True,
    }
    test_fuel = {
        "cons_lap": 5.65,
        "safety_fuel_l": 2.5,
        "weight_sens": 0.015,
        "pit1_lap": 15,
        "pit2_lap": 0,
        "num_stops": 1,
    }
    test_tyre = {
        "hard_base_lap": 84.5,
        "hard_warmup": 0.8,
        "hard_a": 0.2223,
        "hard_n": -0.1208,
        "soft_base_lap": 84.05,
        "soft_warmup": 0.4,
        "soft_a": 0.5318,
        "soft_n": -0.3968,
    }

    live_mod.on_session_data_updated(test_session)
    live_mod.on_fuel_strategy_updated(test_fuel)
    live_mod.on_tyre_strategy_updated(test_tyre)
    live_mod.race_header.set_race_state({
        "leader_lap": 16,
        "leader_pace_str": "1:24.500",
        "leader_strategy": "1 Parada (V15)",
        "race_dur_min": "35",
        "time_rem_str": "05:38",
    })

    # Líder en V16, total proyectado de carrera: 20 vueltas
    state = live_mod.race_header.get_race_state()
    tot_laps = state["total_projected_laps"]
    print(f"Total vueltas proyectadas: {tot_laps}")

    p1_card: PilotLiveCard = live_mod.pilots[0]
    p1_card.active_strategy = {
        "num_stops": 1,
        "p1": 15,
        "p2": 0,
        "stint1_comp": "hard",
        "stint2_comp": "soft",
        "stint3_comp": "soft",
        "target_cons": [5.65, 5.65],
        "refuel_litres": [30.0],
    }

    # Simular registros anteriores en Stint 1
    p1_card.meta_records = [
        {"lap": 5, "fuel": 41.75, "cons": 5.65},
        {"lap": 10, "fuel": 13.50, "cons": 5.65},
        {"lap": 15, "fuel": 8.00, "cons": 5.65},
    ]

    # Ahora el piloto para en V15 y repostó para terminar la carrera.
    # En V16 cruza por meta con 25.1 L en el tanque.
    # Quedan 4 vueltas (V17, V18, V19, V20). 4 * 5.65 + 2.5 = 25.1 L requeridos.
    p1_card._var_quick_lap.set("16")
    p1_card._var_quick_fuel.set("25.1")
    p1_card._submit_quick_meta()

    print("\n1. Verificando Registro V16 con 25.1 L (Suficiente combustible):")
    print(f"   - Tanque actual mostrado: {p1_card._lbl_curr_fuel.cget('text')}")
    print(f"   - Delta combustible: {p1_card._lbl_delta_fuel.cget('text')}")
    print(f"   - Semáforo HUD: {p1_card._lbl_hud_status.cget('text')}")
    print(f"   - Consumo Stint: {p1_card._lbl_cons_stint.cget('text')}")
    print(f"   - Info Próxima Parada: {p1_card._lbl_next_pit.cget('text')}")
    print(f"   - Info Repostaje / Margen: {p1_card._lbl_refuel_calc.cget('text')}")

    delta_val = float(p1_card._lbl_delta_fuel.cget('text').replace("L", "").replace("+", "").replace("±", "").strip())
    assert delta_val >= -0.5, f"ERROR: Delta no debería ser fuertemente negativo, fue {delta_val}"
    assert "SAVE" not in p1_card._lbl_hud_status.cget('text'), "ERROR: No debería pedir SAVE con 25.1 L"
    assert "44." not in p1_card._lbl_cons_stint.cget('text'), "ERROR: Consumo observado contaminado por repostaje"

    # Caso 2: Cargar un poco más de combustible (ej: 28.0 L, margen positivo de casi +3 L)
    p1_card.meta_records.pop()  # Quitar V16
    p1_card._var_quick_lap.set("16")
    p1_card._var_quick_fuel.set("28.0")
    p1_card._submit_quick_meta()

    print("\n2. Verificando Registro V16 con 28.0 L (Margen positivo):")
    print(f"   - Delta combustible: {p1_card._lbl_delta_fuel.cget('text')}")
    print(f"   - Semáforo HUD: {p1_card._lbl_hud_status.cget('text')}")
    print(f"   - Info Repostaje / Margen: {p1_card._lbl_refuel_calc.cget('text')}")

    assert "PUSH" in p1_card._lbl_hud_status.cget('text'), "ERROR: Debería decir PUSH (MARGEN +)"
    assert "Margen: +" in p1_card._lbl_refuel_calc.cget('text'), "ERROR: Debería mostrar margen positivo a meta"

    # Caso 3: Combustible insuficiente en el último stint (ej: 18.0 L para 4 vueltas de 5.65)
    p1_card.meta_records.pop()
    p1_card._var_quick_lap.set("16")
    p1_card._var_quick_fuel.set("18.0")
    p1_card._submit_quick_meta()

    print("\n3. Verificando Registro V16 con 18.0 L (Combustible insuficiente real):")
    print(f"   - Delta combustible: {p1_card._lbl_delta_fuel.cget('text')}")
    print(f"   - Semáforo HUD: {p1_card._lbl_hud_status.cget('text')}")
    print(f"   - Info Repostaje / Margen: {p1_card._lbl_refuel_calc.cget('text')}")

    assert "SAVE" in p1_card._lbl_hud_status.cget('text'), "ERROR: Debe pedir SAVE si realmente falta combustible"
    assert "Falta:" in p1_card._lbl_refuel_calc.cget('text'), "ERROR: Debe mostrar los litros que faltan a meta"

    # Caso 4: Optimizador táctico en el último stint con combustible suficiente
    p1_card.meta_records[-1]["fuel"] = 28.0
    p1_card._recalculate_all()
    p1_card.solve_tactical_strategy()
    print("\n4. Optimizador Táctico en el último stint:")
    print(f"   - Sugerencia Táctica: {p1_card._lbl_tac_desc.cget('text')}")
    assert p1_card.tactical_result["num_stops"] == 0, "ERROR: Debe sugerir 0 paradas hacia meta"

    p1_card.promote_tactical_strategy()
    print(f"   - Plan asignado tras promover: {p1_card._lbl_plan_details.cget('text')}")

    print("\n=== TODAS LAS PRUEBAS DE ÚLTIMO STINT COMPLETADAS CON ÉXITO ===")
    app.destroy()

if __name__ == "__main__":
    test_last_stint()
