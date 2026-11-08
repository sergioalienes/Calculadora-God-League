"""
Prueba 4 — Control en vivo (live_control.py).
  a) ¿on_session_data_updated sobrescribe <circuito>_live.json antes de cargarlo?
  b) Consumo del primer registro de meta cuando no es la vuelta 1.
  c) Frontera curr_lap == p1 con estrategia de 2 paradas (litros a cargar).
  d) Proyección de vueltas del líder vs combustible/comparador.
  e) Optimizador táctico con SC: ritmo SC y consumo SC hardcodeados; parámetros de
     neumáticos en formato texto (modelo alternativo seleccionado en el comparador).
"""
import json
import traceback
import harness as H
from harness import tk_root, COLORS, m_champ, m_live, build_pipeline

root = tk_root()
champ = m_champ.ChampionshipDataModule(root, colors=COLORS)
champ.load_session_by_names("God League", "Bélgica")
sd = dict(champ.get_session_data())
fuel, tyre, charts, fd = build_pipeline(sd)
root._modules = {"charts": charts, "fuel": fuel, "tyres": tyre}  # live_control busca charts vía winfo_toplevel()._modules

# ── a) Sobrescritura del fichero _live.json ─────────────────────────────
live_path = H.TMP_PROFILES / "God League" / "Bélgica_live.json"
data = json.loads(live_path.read_text(encoding="utf-8"))
data["race_header"]["leader_lap"] = 5
data["race_header"]["time_rem_str"] = "00:50:15"
data["pilots"][0]["name"] = "Piloto PRUEBA"
data["pilots"][0]["meta_records"] = [{"lap": 1, "fuel": 64.3, "cons": 5.7}, {"lap": 2, "fuel": 58.7, "cons": 5.6}]
live_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
print("a) _live.json preparado con leader_lap=5, piloto 'Piloto PRUEBA' con 2 registros")

live = m_live.LiveControlModule(root, colors=COLORS)
live.fuel_data = fd
live.on_session_data_updated(sd)          # lo mismo que hace main.navigate_to('live') al arrancar
after = json.loads(live_path.read_text(encoding="utf-8"))
print("   tras on_session_data_updated -> en memoria: nombre=", live.pilots[0]._var_name.get(),
      " registros=", len(live.pilots[0].meta_records), " leader_lap=", live.race_header._var_leader_lap.get())
print("   en disco: nombre=", after["pilots"][0]["name"], " registros=", len(after["pilots"][0]["meta_records"]),
      " leader_lap=", after["race_header"]["leader_lap"])

# ── b) Primer registro de meta en la vuelta 3 ───────────────────────────
p = live.pilots[1]
p.meta_records = []
live.race_header._var_leader_lap.set("3")
p._var_quick_lap.set("3"); p._var_quick_fuel.set("53.05")   # 70 - 3*5.65 = 53.05
p._submit_quick_meta()
print(f"b) Primer registro V3 con 53.05 L -> consumo registrado = {p.meta_records[-1]['cons']:.2f} L/v (esperado 5.65)")

# ── c) Frontera curr_lap == p1 en 2 paradas ────────────────────────────
p = live.pilots[2]
p.active_strategy = {"num_stops": 2, "p1": 12, "p2": 24, "stint1_comp": "hard", "stint2_comp": "hard",
                     "stint3_comp": "soft", "target_cons": [5.65, 5.65, 5.65], "refuel_litres": [66.0, 39.5]}
live.race_header._var_leader_lap.set("12"); live.race_header._on_params_changed()
tot = live.race_header.get_race_state()["total_projected_laps"]
for lap, fl in [(11, 7.85), (12, 2.2)]:
    p.meta_records = [{"lap": 10, "fuel": 13.5, "cons": 5.65}, {"lap": lap, "fuel": fl, "cons": 5.65}]
    p._recalculate_all()
    print(f"c) V{lap} ({fl} L) plan 2 paradas V12/V24, total={tot}: '{p._lbl_next_pit.cget('text')}' | '{p._lbl_refuel_calc.cget('text')}'")
print("   esperado en V12: 'Box 1: Fin V12', cargar (24-12)*5.65+0.4-2.2 = %.1f L" % ((24 - 12) * 5.65 + 0.4 - 2.2))

# ── d) Proyección de vueltas ───────────────────────────────────────────
live.race_header._var_leader_lap.set("0"); live.race_header._reset_clock_to_nominal()
for mode in ["0 Paradas", "1 Parada (Tanque Lleno)", "2 Paradas", "Solo Ruedas"]:
    live.race_header._var_leader_strategy.set(mode)
    st = live.race_header.get_race_state()
    print(f"d) líder modo '{mode}': pit_loss={st['leader_pit_loss_s']:.1f}s total_proyectado={st['total_projected_laps']} (combustible={fd['truncated_laps']})")
live.race_header._var_leader_strategy.set("2 Paradas")
live.race_header._var_leader_lap.set("20"); live.race_header._var_time_rem_str.set(m_live.format_seconds_to_clock(3600 - 20 * 117 - 72))
st = live.race_header.get_race_state()
print(f"   V20 (líder YA hizo sus 2 paradas, reloj {live.race_header._var_time_rem_str.get()}): pit_loss restado otra vez={st['leader_pit_loss_s']:.1f}s -> total={st['total_projected_laps']}")
print("   parse_clock_to_seconds('120') =", m_live.parse_clock_to_seconds("120"), " ; ('200') =", m_live.parse_clock_to_seconds("200"))

# ── e) Táctico con SC ─────────────────────────────────────────────────
p = live.pilots[0]
live.race_header._var_leader_lap.set("6"); live.race_header._var_leader_strategy.set("2 Paradas")
live.race_header._var_time_rem_str.set(m_live.format_seconds_to_clock(3600 - 6 * 117)); live.race_header._on_params_changed()
p.active_strategy = {"num_stops": 2, "p1": 12, "p2": 24, "stint1_comp": "hard", "stint2_comp": "hard",
                     "stint3_comp": "soft", "target_cons": [5.65] * 3, "refuel_litres": [66.0, 39.5]}
p.meta_records = [{"lap": 6, "fuel": 70 - 6 * 5.65, "cons": 5.65}]
p._var_tac_sc.set(True); p._var_tac_sc_sector.set("Sector 2"); p._var_tac_sc_dur.set("3")
try:
    p.solve_tactical_strategy()
    tr = p.tactical_result
    print("e) Táctico SC V7 S2 x3 ->", {k: tr[k] for k in ("rem_stops", "p1", "p2", "fuel_to_load", "fuel_to_load2", "is_sc_free", "total_rem_time")} if tr else None)
    print("   descripción:", p._lbl_tac_desc.cget("text").replace("\n", " | "))
except Exception:
    print("e) CRASH táctico:", traceback.format_exc().splitlines()[-1])
r = charts._simulate_strategy(2, 12, 24, ["hard", "hard", "soft"], sc_enabled=True,
                              sc_segments=[{"enabled": True, "lap": 7, "sector": "Sector 2", "duration": 3, "fuel_l": 1.8}])
print(f"   comparador mismo SC (V7 S2 x3): total_laps={r['total_laps']} (el táctico usa tot_laps del líder = {live.race_header.get_race_state()['total_projected_laps']}, sin descontar el SC)")

# Modelo de neumáticos alternativo seleccionado en el comparador (valores en texto 'MM:SS.mmm')
charts._on_strat_tyre_model_changed("Prueba 1", trigger_plot=False)
print("   override de neumáticos del comparador:", {k: charts._active_tyre_override.get(k) for k in ("hard_base_lap", "soft_base_lap")} if charts._active_tyre_override else None)
try:
    p.solve_tactical_strategy()
    print("   táctico con modelo alternativo: OK")
except Exception:
    print("   táctico con modelo alternativo: CRASH ->", traceback.format_exc().splitlines()[-1])

# Plan por defecto (sin estrategia del comparador) y estado inicial
fresh = m_live.PilotLiveCard(root, pilot_id=9, colors=COLORS, parent_module=live)
print("f) active_strategy por defecto de un piloto nuevo:", fresh.active_strategy)
