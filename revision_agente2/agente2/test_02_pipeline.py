"""
Prueba 2 — Cadena completa Campeonato -> Combustible -> Neumáticos -> Comparador
con perfiles reales (copiados a carpeta temporal) y escenarios inventados.

Verifica:
  * _list_circuits (¿aparecen ficheros auxiliares como circuitos?)
  * modelo de neumáticos x=0 / x=1 / x>=2 y delta de peso <= 0
  * tiempo total de neumáticos vs referencia independiente
  * mismo plan simulado en strategy_charts: ¿mismas vueltas, mismo tiempo?
  * ranking del comparador (estrategia óptima) y viabilidad física (combustible >= 0)
"""
import math
import re
import json
import traceback
import harness as H
from harness import make_session, tk_root, COLORS, m_champ, m_fuel, m_tyre, m_charts


def parse_hms(txt):
    # "58m 12.345s" o "01h 00m 05.123s"
    h = re.search(r"(\d+)h", txt); m = re.search(r"(\d+)m", txt); s = re.search(r"([\d.]+)s", txt)
    return (int(h.group(1)) * 3600 if h else 0) + (int(m.group(1)) * 60 if m else 0) + (float(s.group(1)) if s else 0)


def ref_tyre_total(tm, sd, fd, num_stops, p1, p2, comps):
    """Referencia independiente del Módulo 3 según doc 4.4/4.6 + 01_modulo_neumaticos 3.4."""
    tank = sd["fuel_capacity_l"]; cons = fd["cons_lap"]; saf = fd["safety_fuel_l"]; ws = fd["weight_sens"]
    rate = sd["refuel_rate_ls"]; tyre = sd["tyre_change_s"]; lift = sd["car_lift_s"]; pit = sd["pitlane_loss_s"]
    total = tm._var_total_laps.get()
    bounds = [0, p1, total] if num_stops == 1 else [0, p1, p2, total]
    fuel = tank; t = 0.0; boxes = 0.0; laps = []; wd = []
    for i in range(len(bounds) - 1):
        a, b = bounds[i], bounds[i + 1]
        comp = comps[i]
        if i > 0:
            need = (b - a) * cons + saf
            load = min(tank - fuel, max(0.0, need - fuel))
            boxes += pit + lift + max(load / rate, tyre)
            fuel += load
        start_f = fuel
        for k in range(b - a):
            x = k
            pace = tm.get_tyre_pace(comp, x)
            f = max(saf, start_f - k * cons)
            w = (f - tank) * ws
            wd.append(w)
            laps.append(pace + w)
        fuel = max(0.0, start_f - (b - a) * cons)
    return sum(laps) + boxes, boxes, laps, wd


def build_pipeline(sd, fuel_over=None, tyre_over=None):
    root = tk_root()
    fuel = m_fuel.FuelStrategyModule(root, colors=COLORS)
    tyre = m_tyre.TyreStrategyModule(root, colors=COLORS)
    charts = m_charts.StrategyChartsModule(root, colors=COLORS)
    fuel.on_session_data_updated(sd)
    if fuel_over:
        for k, v in fuel_over.items():
            getattr(fuel, k).set(v)
        # Igual que pulsar Return / 'Recalcular' en la UI: regenera tablas de ahorro con el consumo nuevo
        fuel._on_params_changed()
    fd = fuel.get_fuel_strategy_data()
    tyre.on_session_data_updated(sd)
    if tyre_over:
        for k, v in tyre_over.items():
            getattr(tyre, k).set(v)
    tyre.on_fuel_strategy_updated(fd)
    charts.on_session_data_updated(sd)
    charts.on_fuel_strategy_updated(fd)
    charts.on_tyre_strategy_updated(tyre.get_tyre_strategy_data())
    return fuel, tyre, charts, fd


def report(name, sd, fuel_over=None, tyre_over=None):
    print("=" * 100)
    print(name)
    try:
        fuel, tyre, charts, fd = build_pipeline(sd, fuel_over, tyre_over)
    except Exception:
        print("  CRASH pipeline:\n", traceback.format_exc())
        return
    ns = tyre._var_num_stops.get(); p1 = tyre._var_pit1_lap.get(); p2 = tyre._var_pit2_lap.get()
    comps = [tyre._var_stint1_tyre.get(), tyre._var_stint2_tyre.get(), tyre._var_stint3_tyre.get()]
    print(f"  Combustible -> vueltas={fd['truncated_laps']} viable={fd['viable_modes']} num_stops={fd['num_stops']} pit1={fd['pit1_lap']} pit2={fd['pit2_lap']} cons={fd['cons_lap']} reserva={fd['safety_fuel_l']} sens={fd['weight_sens']}")
    print(f"  Neumáticos  -> total_laps={tyre._var_total_laps.get()} num_stops={ns} p1={p1} p2={p2} comps={comps[:ns+1]}")
    # Modelo a tramos
    for c in ("hard", "soft"):
        b = tyre._get_hard_base_lap() if c == "hard" else tyre._get_soft_base_lap()
        vals = [round(tyre.get_tyre_pace(c, x) - b, 3) for x in range(0, 6)]
        print(f"    get_tyre_pace({c}) - base para x=0..5: {vals}")
    app_total = parse_hms(tyre._lbl_m_total_time.cget("text"))
    app_box = float(tyre._lbl_m_box_time.cget("text").split()[0])
    ref_total, ref_box, laps, wd = ref_tyre_total(tyre, sd, fd, ns, p1, p2, comps)
    print(f"  Tiempo total Neumáticos app={tyre._lbl_m_total_time.cget('text')} ({app_total:.3f}s)  ref={ref_total:.3f}s  boxes app={app_box} ref={ref_box:.1f}")
    print(f"    max delta peso = {max(wd):.4f} s (debe ser <= 0)   min = {min(wd):.3f} s")
    # Mismo plan en el comparador
    try:
        r = charts._simulate_strategy(num_stops=min(ns, 2), p1=p1, p2=p2, stint_comps=comps)
        print(f"  Comparador mismo plan -> total_laps={r['total_laps']} total={r['total_race_time']:.3f}s boxes={r['total_pit_time']:.1f}s final_fuel={r['final_fuel']:.2f} L  min_fuel={min(r['fuel_remaining']):.2f} L")
        print(f"    Diferencia comparador - neumáticos = {r['total_race_time'] - app_total:+.3f} s ; vueltas {r['total_laps']} vs {tyre._var_total_laps.get()}")
        print(f"    stints comparador: " + " | ".join(f"S{s['stint_num']} V{s['start_v']}-{s['end_v']} {s['avg_cons']:.2f}L/v {s['mode_str'].encode('ascii','ignore').decode().strip()}" for s in r['stint_targets']))
        print(f"    pit_info: {[(p[0], round(p[1],1), round(p[2],1)) for p in r['pit_info']]}")
    except Exception:
        print("  CRASH comparador:", traceback.format_exc().splitlines()[-1])
    # Óptima
    oc, orr = charts.optimal_config, charts.optimal_result
    if oc:
        print(f"  ÓPTIMA comparador: {oc}  -> laps={orr['total_laps']} t={orr['total_race_time']:.2f}s final_fuel={orr['final_fuel']:.2f} min_fuel={min(orr['fuel_remaining']):.2f}")
    else:
        print("  ÓPTIMA comparador: NINGUNA (solve_optimal_strategy devolvió None)")
    return fuel, tyre, charts, fd


# ── 1. Perfiles reales vía Módulo 1 ─────────────────────────────────────
root = tk_root()
champ = m_champ.ChampionshipDataModule(root, colors=COLORS)
print("Circuitos listados para 'God League':", champ._list_circuits("God League"))
for circ in ["Bélgica", "Road America", "Nurburgring Nordschleife"]:
    ok = champ.load_session_by_names("God League", circ)
    sd = dict(champ.get_session_data())
    print(f"\n[session_data {circ}] ok={ok} claves={sorted(sd.keys())}")
    print("  ¿Contiene fuel_per_lap_l / weight_penalty_s_per_10l / safety_margin_l?",
          [k in sd for k in ("fuel_per_lap_l", "weight_penalty_s_per_10l", "safety_margin_l")])
    report(f"PERFIL REAL: God League / {circ}", sd)

# ── 2. Escenarios inventados ───────────────────────────────────────────
GT3 = make_session(champ="Test GT3", circuit="Daytona", lap="01:46.000", pit=30, tank=105, rate=2.8, tyre=18, lift=2, dur_min=45)
report("GT3 105 L / 2.8 L/s / 45 min, 3.2 L/v", GT3,
       fuel_over={"_var_fuel_lap": "3.2", "_var_safety_fuel": "1.0", "_var_weight_sens": "0.03"},
       tyre_over={"_var_hard_base_lap": "01:46.000", "_var_soft_base_lap": "01:45.400"})
GTP = make_session(champ="Test GTP", circuit="Le Mans", lap="03:30.000", pit=35, tank=110, rate=3.5, tyre=20, lift=2, dur_min=120, trk=13.6, sc_kmh=110)
report("GTP 110 L / 120 min / 3:30, 9.5 L/v", GTP,
       fuel_over={"_var_fuel_lap": "9.5", "_var_safety_fuel": "1.0", "_var_weight_sens": "0.03"},
       tyre_over={"_var_hard_base_lap": "03:30.000", "_var_soft_base_lap": "03:29.000"})
SPR = make_session(champ="Test Sprint", circuit="Sprint", lap="01:24.500", pit=22.5, tank=70, rate=12, tyre=4, lift=2, dur_min=20)
report("Sprint 20 min IR-18 (compuesto obligatorio)", SPR,
       fuel_over={"_var_fuel_lap": "2.15", "_var_safety_fuel": "2.5"},
       tyre_over={"_var_hard_base_lap": "01:24.500", "_var_soft_base_lap": "01:24.050"})
SPR_FREE = make_session(champ="Test Sprint", circuit="SprintFree", lap="01:24.500", pit=22.5, tank=70, rate=12, tyre=4, lift=2, dur_min=20, mandatory=False)
report("Sprint 20 min SIN cambio obligatorio de compuesto", SPR_FREE,
       fuel_over={"_var_fuel_lap": "2.15", "_var_safety_fuel": "2.5"},
       tyre_over={"_var_hard_base_lap": "01:24.500", "_var_soft_base_lap": "01:24.050"})
END3 = make_session(champ="Test GT3", circuit="Endurance3", lap="01:46.000", pit=30, tank=105, rate=2.8, tyre=18, lift=2, dur_min=120)
report("GT3 120 min 5 L/v (viable 2 y 3 paradas)", END3,
       fuel_over={"_var_fuel_lap": "5.0", "_var_safety_fuel": "1.0", "_var_weight_sens": "0.03"},
       tyre_over={"_var_hard_base_lap": "01:46.000", "_var_soft_base_lap": "01:45.400"})
HI = make_session(champ="Test", circuit="HighCons", lap="01:30.000", pit=25, tank=70, rate=12, tyre=4, lift=2, dur_min=60)
report("Consumo altísimo 12 L/v (solo >=3 paradas viables)", HI,
       fuel_over={"_var_fuel_lap": "12", "_var_safety_fuel": "1.0"},
       tyre_over={"_var_hard_base_lap": "01:30.000", "_var_soft_base_lap": "01:29.500"})

# ── 3. Sensibilidad de peso = 0 (fallback con 'or') ─────────────────────
print("=" * 100)
print("Sensibilidad de peso 0.0 en combustible")
fuel, tyre, charts, fd = build_pipeline(GT3, fuel_over={"_var_fuel_lap": "3.2", "_var_safety_fuel": "1.0", "_var_weight_sens": "0"})
print("  fuel_data['weight_sens'] =", fd["weight_sens"])
ws_tyre = float(fd.get("weight_sens") or fd.get("calc_results", {}).get("weight_sens") or tyre.session_data.get("weight_sens", 0.015))
print("  sensibilidad efectiva en tyre_strategy.recalculate_and_plot (misma expresión) =", ws_tyre)
print("  sensibilidad efectiva en strategy_charts =", charts._get_weight_sensitivity())

# ── 4. OLS: casos límite ───────────────────────────────────────────────
print("=" * 100)
print("OLS casos límite")
import numpy as np, warnings
for pts in ([{"lap": 5, "delta": 0.3}, {"lap": 5, "delta": 0.5}], [{"lap": 2, "delta": 0.5}, {"lap": 3, "delta": 0.2}, {"lap": 6, "delta": 0.1}]):
    tyre.hard_test_points = pts
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        try:
            tyre.fit_regression("hard", update_ui=False)
            print(f"  puntos={pts} -> a={tyre._var_hard_a.get()} n={tyre._var_hard_n.get()} R2={tyre._var_hard_r2.get()} warnings={[str(x.message)[:60] for x in w]}")
        except Exception as e:
            print(f"  puntos={pts} -> CRASH {type(e).__name__}: {e}")
# verificación OLS con perfil real Bélgica (duro)
bel = json.loads((H.TMP_PROFILES / "God League" / "Bélgica_tyres.json").read_text(encoding="utf-8"))
xs = np.array([p["lap"] for p in bel["hard_test_points"] if p["lap"] >= 2], float)
ys = np.array([p["delta"] for p in bel["hard_test_points"] if p["lap"] >= 2], float)
a, n = np.polyfit(np.log(xs), ys, 1)
pred = a * np.log(xs) + n
r2 = 1 - ((ys - pred) ** 2).sum() / ((ys - ys.mean()) ** 2).sum()
print(f"  Bélgica duro: guardado a={bel['hard_a']} n={bel['hard_n']} R2={bel['hard_r2']}  | recalculado a={a:.4f} n={n:.4f} R2={r2:.4f}")
print("  Mensajes messagebox capturados:", H.MSG_CALLS[-5:])
