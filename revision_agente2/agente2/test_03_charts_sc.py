"""
Prueba 3 — Comparador (strategy_charts.py): viabilidad física, Safety Car y ranking.
"""
import json
import traceback
import harness as H
from harness import tk_root, COLORS, m_champ, m_fuel, m_tyre, m_charts
from harness import build_pipeline

print("\n\n######## PRUEBA 3: COMPARADOR / SAFETY CAR ########")
root = tk_root()
champ = m_champ.ChampionshipDataModule(root, colors=COLORS)
champ.load_session_by_names("God League", "Bélgica")
sd = dict(champ.get_session_data())
fuel, tyre, charts, fd = build_pipeline(sd)

def summ(tag, r):
    print(f"  {tag}: laps={r['total_laps']} t={r['total_race_time']:.2f}s pit={r['total_pit_time']:.1f}s "
          f"final_fuel={r['final_fuel']:.2f}L min_fuel={min(r['fuel_remaining']):.2f}L "
          f"pits={[(p[0], round(p[1],1), round(p[2],1), 'SCgratis' if p[3] else '', 'CERRADO' if p[4] else '') for p in r['pit_info']]}")
    for s in r["stint_targets"]:
        print(f"     S{s['stint_num']} V{s['start_v']}-{s['end_v']} ({s['laps']}v) {s['comp']} cons_verde={s['avg_cons']:.2f} {s['mode_str'].encode('ascii','ignore').decode().strip()}")

# 1. Plan del live por defecto en Bélgica: 1 parada en V15 (físicamente imposible: 31 v x 5.65 = 175 L)
r = charts._simulate_strategy(num_stops=1, p1=15, p2=0, stint_comps=["hard", "soft"])
summ("Bélgica 1 parada V15 (plan por defecto del live)", r)
dry = [i + 1 for i, f in enumerate(r["fuel_remaining"]) if f <= 0.0]
print(f"     vueltas con depósito a 0 L: {dry[:10]}{'...' if len(dry) > 10 else ''} -> el simulador NO marca la estrategia como inviable")

# 2. SC: SC en V8 sector 2, 3 vueltas, 1.8 L/v
sc = [{"enabled": True, "lap": 8, "sector": "Sector 2", "duration": 3, "fuel_l": 1.8}]
for p1, p2 in [(12, 24), (9, 22), (10, 22), (11, 22)]:
    r = charts._simulate_strategy(num_stops=2, p1=p1, p2=p2, stint_comps=["hard", "hard", "soft"], sc_enabled=True, sc_segments=sc)
    summ(f"Bélgica 2 paradas V{p1}/V{p2} + SC V8 S2 x3", r)
print("  SC pace comparador (track_len/sc_speed) =", (sd["track_length_km"] / sd["sc_speed_kmh"]) * 3600, "s ; sc_pace_s del perfil =", sd.get("sc_pace_s"),
      "; live_control usa base_lap*1.40 =", sd["lap_time_seconds"] * 1.40, "s")

# 3. Optimizador con SC habilitado en la UI del comparador
charts._var_sc_enabled.set(True)
charts.sc_segments[0]["lap"].set("8"); charts.sc_segments[0]["sector"].set("Sector 2")
charts.sc_segments[0]["duration"].set("3"); charts.sc_segments[0]["fuel_l"].set("1.80")
cfg, res = charts.solve_optimal_strategy()
print("  Óptima con SC:", cfg)
if res:
    summ("óptima con SC", res)
cand = charts._find_best_1stop_opportunity() if charts.current_result else None
print("  Oportunidad 1 parada con SC V8:", cand[:5] if cand else None)
if cand:
    summ("candidato 1 parada", cand[5])

# SC largo (10 vueltas en V12) -> ¿1 parada viable?
charts.sc_segments[0]["lap"].set("12"); charts.sc_segments[0]["duration"].set("10")
cfg, res = charts.solve_optimal_strategy()
print("  Óptima con SC largo V12 x10:", cfg)
if res:
    summ("óptima SC largo", res)
charts._var_sc_enabled.set(False)

# 4. Rebufo: max_stint_laps usa 30 % de ahorro en vez de 20 %
charts._var_draft_enabled.set(True)
charts.draft_segments[0]["start"].set("20"); charts.draft_segments[0]["end"].set("21")
cfg, res = charts.solve_optimal_strategy()
print("  Óptima con rebufo V20-21:", cfg)
if res:
    summ("óptima rebufo", res)
charts._var_draft_enabled.set(False)

# 5. Ranking: las 3 estrategias guardadas en Bélgica
print("  Estrategias guardadas Bélgica (simulate_strategy_for_config):")
for name, st in charts._load_saved_strategies_dict().items():
    rr = charts.simulate_strategy_for_config(st)
    if rr:
        print(f"    {name:12s}: stops={st['num_stops']} p1={st['p1']} p2={st['p2']} comps={st['stint1_comp']}/{st['stint2_comp']}/{st['stint3_comp']} fuel_model={st.get('fuel_model')} -> laps={rr['total_laps']} t={rr['total_race_time']:.2f}s min_fuel={min(rr['fuel_remaining']):.2f}")
    else:
        print(f"    {name}: simulate_strategy_for_config devolvió None")

# 6. Comparación de fórmulas de 'vueltas totales' entre módulos (Bélgica, 1 y 2 paradas)
print("  Vueltas totales por módulo (Bélgica): combustible=", fd["truncated_laps"],
      "| comparador 1 parada V15 =", charts._simulate_strategy(1, 15, 0, ["hard", "soft"])["total_laps"],
      "| comparador 2 paradas V12/V24 =", charts._simulate_strategy(2, 12, 24, ["hard", "hard", "soft"])["total_laps"])

# 7. Selector de num_stops del comparador si viable_modes = ['3 Paradas']
fd3 = dict(fd); fd3["viable_modes"] = ["3 Paradas", "4 Paradas"]
charts.on_fuel_strategy_updated(fd3)
print("  viable_modes=['3 Paradas','4 Paradas'] -> _var_num_stops del comparador =", charts._var_num_stops.get(),
      "-> recalculate_and_plot simula num_stops =", 1 if "1" in charts._var_num_stops.get() else 2)
cfg, res = charts.solve_optimal_strategy()
print("  solve_optimal_strategy con solo 3/4 paradas viables ->", cfg)
