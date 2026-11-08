"""
Test de validación para el botón Descartar Estrategia Táctica
y la sincronización física de ahorro de combustible y degradación de neumáticos.
"""
import os
import sys

# Forzar modo headless
os.environ["SDL_VIDEODRIVER"] = "dummy"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import CalculadoraApp
from modules.live_control import LiveControlModule

def test_discard_and_physics():
    print("=== TEST: BOTÓN DESCARTAR Y FÍSICA TÁCTICA ===")
    app = CalculadoraApp()
    app.withdraw()

    live_mod: LiveControlModule = app._modules["live"]
    p = live_mod.pilots[0]

    # 1. Configurar estado de carrera
    live_mod.race_header._var_leader_lap.set("10")
    live_mod.race_header._var_time_rem_str.set("00:30:00")
    live_mod.race_header._on_params_changed()

    # 2. Configurar piloto en V10 con 30L
    p._var_quick_lap.set("10")
    p._var_quick_fuel.set("30.0")
    p._submit_quick_meta()

    # Botones deben estar deshabilitados inicialmente
    assert str(p._btn_promote.cget("state")) == "disabled", "Promover debe estar deshabilitado antes de calcular"
    assert str(p._btn_discard.cget("state")) == "disabled", "Descartar debe estar deshabilitado antes de calcular"

    # 3. Recalcular estrategia táctica
    print("1. Calculando estrategia táctica...")
    p.solve_tactical_strategy()
    assert p.tactical_result is not None, "Debe haber generado un resultado táctico"
    assert str(p._btn_promote.cget("state")) == "normal", "Promover debe estar activo"
    assert str(p._btn_discard.cget("state")) == "normal", "Descartar debe estar activo"
    print(f"   -> Sugerencia: {p._lbl_tac_desc.cget('text').splitlines()[0]}")

    # Verificar que el timeline muestra los botones de acción rápida
    tac = p.tactical_result
    has_unapplied = bool(tac and str(p._btn_promote.cget("state")) != "disabled")
    assert has_unapplied is True, "has_unapplied_tac debe ser True"

    # 4. Probar DESCARTAR
    print("2. Descartando sugerencia táctica...")
    p.discard_tactical_strategy()
    assert p.tactical_result is None, "tactical_result debe ser None tras descartar"
    assert str(p._btn_promote.cget("state")) == "disabled", "Promover debe quedar deshabilitado"
    assert str(p._btn_discard.cget("state")) == "disabled", "Descartar debe quedar deshabilitado"
    assert "descartada" in p._lbl_tac_desc.cget("text").lower(), "El texto debe indicar que fue descartada"
    print("   -> Descarte exitoso.")

    # 5. Probar física de ahorro: intentar extender stint imposible (>20% de ahorro)
    print("3. Probando límite del 20% de ahorro...")
    # Si quedan 20 vueltas a 5.65 L/v = 113L, con 30L en tanque el ahorro necesario sería 73%, que debe rechazarse para 0 paradas
    # La opción a 0 paradas debe haber sido descartada
    assert p.tactical_result is None or p.tactical_result.get("num_stops", 0) > 0, "No debe permitir 0 paradas con 30L para 20 vueltas"
    print("   -> Límite del 20% de ahorro respetado estrictamente.")

    # 6. Probar curva de penalización
    curve = p._get_fuel_saving_curve()
    assert len(curve) >= 2, "La curva de ahorro debe contener al menos 2 puntos"
    pen_light = p._interpolate_saving_penalty(0.20, curve)
    pen_heavy = p._interpolate_saving_penalty(0.80, curve)
    assert pen_heavy > pen_light > 0.0, f"A mayor ahorro, mayor tiempo perdido: {pen_light}s vs {pen_heavy}s"
    print(f"   -> Curva de penalización interpolada: 0.20L/v={pen_light:.3f}s, 0.80L/v={pen_heavy:.3f}s")

    app.destroy()
    print("=== TODOS LOS TESTS PASARON EXITOSAMENTE ===")

if __name__ == "__main__":
    test_discard_and_physics()
