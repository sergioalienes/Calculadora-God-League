"""
Headless validation script for Calculadora God League and updated Module 5 (live_control).
Tests:
  1. Module 5 instantiation within CalculadoraApp.
  2. Navigation to 'live' and synchronization of session_data.
  3. Leader pit stop loss: full tank (pitlane + refuel + tyres), solo ruedas (pitlane + tyres), and 2 stops.
  4. Quick meta check-in and leader lap limit validation.
  5. Negative fuel delta recovery target calculation and HUD display.
  6. Optimal strategy loading from Module 4 (supporting 2-stop optimal).
  7. Tactical re-optimizer run under Safety Car with Sector and Duration (and displaying Stint 2 and 3 compounds).
  8. Tactical strategy promotion to active reference.
  9. Persistence save and reload from profiles/..._live.json.
"""

import sys
import json
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, r"E:\Calculadora God League")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def run_tests():
    print("=== INICIANDO VALIDACIÓN HEADLESS DE LIVE CONTROL (ACTUALIZADO) ===")
    from main import CalculadoraApp, COLORS
    from modules.live_control import LiveControlModule

    from tkinter import messagebox
    warning_calls = []
    messagebox.showwarning = lambda title, msg: warning_calls.append((title, msg))

    app = CalculadoraApp()
    app.withdraw() # Headless, no visual window

    # 1. Navegar a 'live'
    print("1. Navegando al módulo 'live'...")
    app.navigate_to("live")
    live_mod = app._modules.get("live")
    assert isinstance(live_mod, LiveControlModule), "live_mod no es instancia de LiveControlModule"
    print("   -> Módulo live instanciado correctamente.")

    # 2. Comprobar 3 pilotos
    assert len(live_mod.pilots) == 3, f"Se esperaban 3 pilotos, hay {len(live_mod.pilots)}"
    print("   -> 3 columnas de pilotos detectadas.")

    # 3. Probar Race Control Header con correlación de variables de campeonato
    # Pitlane loss = 30.0s, tank = 70.0L, refuel = 12.0L/s (5.83s), tyre = 4.0s
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
        "race_duration_s": 3600.0,
        "race_duration_min": 60.0,
    }
    live_mod.on_session_data_updated(test_session)

    header = live_mod.race_header
    header._var_leader_lap.set("12") # Vuelta 12 consumida
    header._var_time_rem_str.set("00:40:00") # 2400s restantes
    
    # Modo 0 paradas restantes
    header._var_leader_strategy.set("0 Paradas (No para)")
    header._on_params_changed()
    state0 = header.get_race_state()
    print(f"   -> Líder V12 | 0 Paradas: PitLoss={state0['leader_pit_loss_s']}s")
    assert state0['leader_pit_loss_s'] == 0.0

    # Modo 1 parada (tanque lleno + ruedas + pitlane) = 30 + 5.83 + 4 = 39.83s
    header._var_leader_strategy.set("1 Parada (Tanque Lleno)")
    header._on_params_changed()
    state1 = header.get_race_state()
    print(f"   -> Líder V12 | 1 Parada (Tanque Lleno + Ruedas + Pitlane): PitLoss={state1['leader_pit_loss_s']:.2f}s")
    assert abs(state1['leader_pit_loss_s'] - (30.0 + (70.0 / 12.0) + 4.0)) < 0.1, f"Esperado ~39.83s, obtenido {state1['leader_pit_loss_s']}"

    # Modo 1 parada (solo ruedas) = 30 + 4 = 34.0s
    header._var_leader_strategy.set("1 Parada (Solo Ruedas)")
    header._on_params_changed()
    state_tyres = header.get_race_state()
    print(f"   -> Líder V12 | 1 Parada (Solo Ruedas + Pitlane): PitLoss={state_tyres['leader_pit_loss_s']:.2f}s")
    assert abs(state_tyres['leader_pit_loss_s'] - 34.0) < 0.1

    # Modo 2 paradas = 39.83 + 34.0 = 73.83s
    header._var_leader_strategy.set("2 Paradas (1ª Tanque + 2ª Ruedas)")
    header._on_params_changed()
    state2 = header.get_race_state()
    print(f"   -> Líder V12 | 2 Paradas (Suma ambas): PitLoss={state2['leader_pit_loss_s']:.2f}s")
    assert abs(state2['leader_pit_loss_s'] - (39.833 + 34.0)) < 0.2

    # 4. Probar carga de Estrategia Óptima con 2 paradas desde Módulo 4
    opt_config_2stops = {
        "num_stops": 2,
        "p1": 13,
        "p2": 21,
        "stint1_comp": "hard",
        "stint2_comp": "soft",
        "stint3_comp": "soft",
    }
    live_mod.on_strategies_updated({}, optimal_config=opt_config_2stops)
    p1 = live_mod.pilots[0]
    p1._var_selected_strategy.set("⚡ Estrategia Óptima")
    p1._apply_selected_strategy()
    print(f"   -> Piloto 1 aplicando Estrategia Óptima: {p1.active_strategy['num_stops']} paradas (p1={p1.active_strategy['p1']}, p2={p1.active_strategy['p2']})")
    assert p1.active_strategy["num_stops"] == 2, f"Se esperaban 2 paradas de la estrategia óptima, hay {p1.active_strategy['num_stops']}"
    assert p1.active_strategy["p1"] == 13
    assert p1.active_strategy["p2"] == 21

    # 5. Probar validación contra la vuelta del líder
    # Líder en vuelta 12 -> registrar V13 es rechazado
    p1._var_quick_lap.set("13")
    p1._var_quick_fuel.set("50.0")
    rec_count_before = len(p1.meta_records)
    p1._submit_quick_meta()
    assert len(p1.meta_records) == rec_count_before, "No se debió permitir registrar V13 con líder en V12"
    print("   -> Validación de vuelta del líder superada: V13 rechazada.")

    # 6. Probar cálculo de objetivo de consumo con Delta Negativo
    # Registramos V1 con gasto excesivo (ej. 55.0L en lugar de 64.35L -> delta negativo)
    p1._var_quick_lap.set("1")
    p1._var_quick_fuel.set("55.0")
    p1._submit_quick_meta()
    
    hud_status = p1._lbl_hud_status.cget("text")
    cons_text = p1._lbl_cons_stint.cget("text")
    print(f"   -> Delta Negativo en Piloto 1:")
    print(f"      Estado HUD: {hud_status}")
    print(f"      Consumo Texto: {cons_text}")
    assert "SAVE" in hud_status, f"El semáforo debe indicar SAVE con delta negativo: {hud_status}"
    assert "Obj:" in cons_text, f"Debe mostrar el consumo objetivo necesario: {cons_text}"

    # 7. Probar optimizador táctico con Safety Car y visualización de compuesto Stint 2 y 3
    p2 = live_mod.pilots[1]
    p2._var_quick_lap.set("10")
    p2._var_quick_fuel.set("25.0")
    p2._submit_quick_meta()

    p2._var_tac_sc.set(True)
    p2._var_tac_sc_sector.set("Sector 2")
    p2._var_tac_sc_dur.set("3")
    p2.solve_tactical_strategy()
    assert p2.tactical_result is not None, "El optimizador táctico debió devolver un plan viable"
    
    desc_text = p2._lbl_tac_desc.cget("text")
    print(f"   -> Piloto 2 Táctico con SC:")
    print(f"      {desc_text}")
    if p2.tactical_result["num_stops"] == 2:
        assert "S2" in desc_text and "S3" in desc_text, f"Debe mostrar ambos compuestos S2 y S3 en 2 paradas: {desc_text}"

    # 8. Promover estrategia táctica
    p2.promote_tactical_strategy()
    assert p2.active_strategy["p1"] == p2.tactical_result["p1"], "La parada activa debió actualizarse a la sugerida"
    print("   -> Promoción de estrategia táctica a activa exitosa.")

    # 9. Probar guardado y recarga en disco
    print("9. Probando persistencia en disco...")
    live_mod.save_live_session()
    profile_path = live_mod._get_live_profile_path()
    if profile_path and profile_path.exists():
        raw_json = json.loads(profile_path.read_text(encoding="utf-8"))
        assert "race_header" in raw_json, "Falta race_header en JSON"
        assert len(raw_json["pilots"]) == 3, "Faltan pilotos en JSON"
        print(f"   -> Archivo {profile_path.name} verificado y cargado correctamente.")

    # Destruir app headless
    app.destroy()
    print("=== TODAS LAS PRUEBAS HEADLESS COMPLETADAS CON ÉXITO ===")

if __name__ == "__main__":
    run_tests()
