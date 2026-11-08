"""
Prueba 5 — Aplicación completa (main.CalculadoraApp) con la ventana oculta y perfiles temporales.
  * Arranque con _last_state.json -> 'live' (¿se pierde la sesión en vivo guardada?)
  * navigate_to por todos los módulos (¿avisos no fatales?)
  * Persistencia de _last_state con nombres que contienen caracteres saneados
  * Guardar campeonato con coma decimal; mandatory_compound_change; borrado de circuito
"""
import io
import json
import contextlib
import harness as H
import main

main.PROFILES_ROOT = H.TMP_PROFILES
main.STATE_FILE = H.TMP_PROFILES / "_last_state.json"

# Sesión en vivo con datos reales en Bélgica
lp = H.TMP_PROFILES / "God League" / "Bélgica_live.json"
d = json.loads(lp.read_text(encoding="utf-8"))
d["race_header"]["leader_lap"] = 7
d["race_header"]["time_rem_str"] = "00:46:20"
d["pilots"][0]["meta_records"] = [{"lap": 1, "fuel": 64.3, "cons": 5.7}, {"lap": 2, "fuel": 58.7, "cons": 5.6}]
lp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
main.STATE_FILE.write_text(json.dumps({"last_module": "live", "championship": "God League", "circuit": "Bélgica", "ui_zoom": "100%"}), encoding="utf-8")

buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    app = main.CalculadoraApp()
    app.withdraw()
    app.update()
d2 = json.loads(lp.read_text(encoding="utf-8"))
print("1) Arranque con last_module='live' en Bélgica:")
print("   antes: leader_lap=7, registros piloto1=2 | después (disco): leader_lap=", d2["race_header"]["leader_lap"],
      " registros piloto1=", len(d2["pilots"][0]["meta_records"]))

with contextlib.redirect_stdout(buf):
    for mid in ["championship", "fuel", "tyres", "charts", "live", "fuel", "charts"]:
        app.navigate_to(mid)
        app.update()
avisos = [l for l in buf.getvalue().splitlines() if "Aviso" in l or "Error" in l]
print("2) Avisos/errores impresos durante la navegación:", avisos if avisos else "ninguno")
fd = app._modules["fuel"].get_fuel_strategy_data()
print("   fuel exporta num_stops/pit1/pit2 =", fd["num_stops"], fd["pit1_lap"], fd["pit2_lap"], "viable=", fd["viable_modes"])
print("   comparador óptima =", app._modules["charts"].optimal_config)
print("   live piloto1 active_strategy =", {k: app._modules["live"].pilots[0].active_strategy.get(k) for k in ("num_stops", "p1", "p2", "target_cons")})

# 3) Campeonato con caracteres saneados -> restauración de _last_state
ch = app._modules["championship"]
ch._new_championship()
ch._var_champ_name.set("IMSA: GT3?")
ch._var_fuel_capacity.set("105"); ch._var_refuel_rate.set("2.8"); ch._var_tyre_change.set("18")
ch._var_car_lift.set("2"); ch._var_race_duration.set("45")
ch._save_championship()
ch._new_circuit()
ch._var_circuit.set("Daytona: Road"); ch._var_lap_time.set("01:46.000"); ch._var_pitlane_loss.set("30")
ch._save_circuit()
ch._save_session_data()
app.save_app_state()
st = json.loads(main.STATE_FILE.read_text(encoding="utf-8"))
print("3) carpetas:", sorted(p.name for p in H.TMP_PROFILES.iterdir() if p.is_dir()))
print("   _last_state guardado:", st)
ok = ch.load_session_by_names(st["championship"], st["circuit"])
print("   load_session_by_names(estado guardado) ->", ok, "(False = no se restaurará al reabrir)")
cj = json.loads((H.TMP_PROFILES / "IMSA_ GT3_" / "_campeonato.json").read_text(encoding="utf-8"))
print("   mandatory_compound_change guardado =", cj["mandatory_compound_change"], "(no hay control en la UI para desactivarlo)")

# 4) Coma decimal en campos numéricos
ch._var_fuel_capacity.set("105,5")
try:
    ch._save_championship()
    print("4) Guardar campeonato con '105,5': OK")
except Exception as e:
    print(f"4) Guardar campeonato con '105,5': CRASH {type(e).__name__}: {e}  (el validador lo aceptó)")
ch._var_fuel_capacity.set("105")
ch._var_pitlane_loss.set("30,5")
try:
    ch._save_circuit()
    print("   Guardar circuito con pitlane '30,5': OK")
except Exception as e:
    print(f"   Guardar circuito con pitlane '30,5': CRASH {type(e).__name__}: {e}")

# 5) Borrado de circuito: ficheros que quedan
champ_dir = H.TMP_PROFILES / "God League"
ch.load_session_by_names("God League", "Road America")
ch._delete_circuit()
print("5) Tras borrar 'Road America' quedan:", sorted(p.name for p in champ_dir.glob("Road America*")))

app.destroy()
print("\nTodo en carpeta temporal:", H.TMP_PROFILES)
