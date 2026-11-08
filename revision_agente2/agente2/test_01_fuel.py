"""
Prueba 1 — Módulo de Combustible (fuel_strategy.py).
Compara cada escenario contra una implementación de referencia independiente
escrita a partir de las fórmulas de contexto_global.txt (4.1, 4.2, 4.3).
"""
import math
import traceback
from harness import make_session, new_fuel


def ref_fuel(sd, cons, safety):
    """Referencia según documentación (sección 4.1)."""
    lap = sd["lap_time_seconds"]; dur = sd["race_duration_s"]; tank = sd["fuel_capacity_l"]
    rate = sd["refuel_rate_ls"]; tyre = sd["tyre_change_s"]; pit = sd["pitlane_loss_s"]
    lift = sd["car_lift_s"]
    raw_laps = dur / lap
    raw_fuel = raw_laps * cons + safety
    usable = tank - safety
    f_stops = math.ceil(max(0, raw_fuel - tank) / usable)
    min_stops = max(1, f_stops) if sd["mandatory_compound_change"] else f_stops
    need = max(0.0, raw_fuel - tank)
    if min_stops > 0:
        per = need / min_stops
        t_box_doc = max(per / rate, tyre)            # doc: sin car_lift
        t_box_code = lift + max(per / rate, tyre)    # código: + car_lift
        loss_doc = min_stops * (pit + t_box_doc)
        loss_code = min_stops * (pit + t_box_code)
    else:
        loss_doc = loss_code = 0.0
    trunc_doc = math.floor(max(0, dur - loss_doc) / lap) + 1
    trunc_code = math.floor(max(0, dur - loss_code) / lap) + 1
    l_base = math.floor(usable / cons); l_save = math.floor(usable / (0.8 * cons))
    return dict(raw_laps=raw_laps, raw_fuel=raw_fuel, min_stops=min_stops,
                trunc_doc=trunc_doc, trunc_code=trunc_code, l_base=l_base, l_save=l_save)


SCEN = [
    # nombre, kwargs sesión, consumo, reserva, sens
    ("Bélgica (perfil real)", dict(champ="God League", circuit="Bélgica", lap="01:57.000", pit=30, tank=70, rate=10, tyre=5, lift=1, dur_min=60, trk=7, sc_kmh=105), 5.65, 0.4, 0.022),
    ("Road America (perfil real)", dict(champ="God League", circuit="Road America", lap="01:45.000", pit=29, tank=70, rate=10, tyre=5, lift=1, dur_min=60, trk=6.515, sc_kmh=105), 5.4, 0.4, 0.02),
    ("Nordschleife (perfil real)", dict(champ="God League", circuit="Nurburgring Nordschleife", lap="07:03.000", pit=24, tank=70, rate=10, tyre=5, lift=1, dur_min=60, trk=25.24, sc_kmh=100), 20.0, 0.4, 0.072),
    ("GT3 105L 2.8L/s 45min", dict(lap="01:46.000", pit=30, tank=105, rate=2.8, tyre=18, lift=2, dur_min=45), 3.20, 1.0, 0.03),
    ("GTP 110L 120min", dict(lap="01:35.000", pit=32, tank=110, rate=3.5, tyre=20, lift=2, dur_min=120), 3.60, 1.0, 0.03),
    ("Sprint 20 min IR-18", dict(lap="01:24.500", pit=22.5, tank=70, rate=12, tyre=4, lift=2, dur_min=20), 2.15, 2.5, 0.015),
    ("Tanque enorme 500L sin compuesto obligatorio", dict(lap="01:30.000", pit=25, tank=500, rate=5, tyre=10, lift=2, dur_min=60, mandatory=False), 2.0, 1.0, 0.01),
    ("Consumo altísimo 30 L/v", dict(lap="01:30.000", pit=25, tank=70, rate=12, tyre=4, lift=2, dur_min=60), 30.0, 2.5, 0.015),
    ("2-3 paradas (GT3 120 min, 5 L/v)", dict(lap="01:46.000", pit=30, tank=105, rate=2.8, tyre=18, lift=2, dur_min=120), 5.0, 1.0, 0.03),
]

for name, kw, cons, safety, ws in SCEN:
    print("=" * 90)
    print(name)
    sd = make_session(**kw)
    try:
        mod = new_fuel(sd, cons, safety, ws)
        print("  [nota] _build_stints_section existe en el módulo pero nunca se invoca desde _build_scroll ->",
              "hasattr(_stints_card)=", hasattr(mod, "_stints_card"))
        fd0 = mod.get_fuel_strategy_data()
        print(f"  exportado SIN sección de stints: num_stops={fd0['num_stops']} pit1_lap={fd0['pit1_lap']} pit2_lap={fd0['pit2_lap']} (vueltas={fd0['truncated_laps']})")
        mod._build_stints_section()   # forzamos la sección muerta para auditar su lógica
        mod.calculate_strategy()
    except Exception:
        print("  CRASH:", traceback.format_exc().splitlines()[-1])
        continue
    r = mod.calc_results
    ref = ref_fuel(sd, cons, safety)
    fd = mod.get_fuel_strategy_data()
    print(f"  vueltas truncadas app={r['truncated_laps']}  ref(código, con car_lift)={ref['trunc_code']}  ref(doc, sin car_lift)={ref['trunc_doc']}")
    print(f"  paradas mínimas app={r['min_stops_req']}  ref={ref['min_stops']}  (mandatory={sd['mandatory_compound_change']})")
    print(f"  autonomía base={ref['l_base']} v  autonomía -20%={ref['l_save']} v  (app max_laps_per_stint_20={r['max_laps_per_stint_20']})")
    print(f"  viable_modes={fd['viable_modes']}  num_stops seleccionado={fd['num_stops']}  p1={fd['pit1_lap']} p2={fd['pit2_lap']}")
    print(f"  gasolina gratis={r['free_fuel_l']:.1f} L   combustible final={r['final_race_fuel']:.1f} L")
    # Comprobación física: con k paradas y autonomía -20% ¿se cubren las vueltas?
    for m in fd["viable_modes"]:
        k = int(m.split()[0])
        cover = (k + 1) * ref["l_save"]
        print(f"    - {m}: (k+1)*autonomía_-20% = {cover} v  vs {r['truncated_laps']} v -> {'OK' if cover >= r['truncated_laps'] else 'INVIABLE'}")
    # Etiquetas de stints (lo que ve el usuario)
    ns = fd["num_stops"]
    if ns == 1 and hasattr(mod, "_lbl_s1_laps"):
        for attr in ("_lbl_s1_laps", "_lbl_s1_target", "_lbl_s1_box", "_lbl_s2_laps", "_lbl_s2_target", "_lbl_s2_meta", "_lbl_pit1_load", "_lbl_pit1_tank", "_lbl_pit1_loss", "_lbl_pit1_free"):
            print("     ", attr, "=>", getattr(mod, attr).cget("text"))
    elif ns >= 2 and hasattr(mod, "_lbl_2s1_laps"):
        for attr in ("_lbl_2s1_laps", "_lbl_2s1_target", "_lbl_2s2_laps", "_lbl_2s2_target", "_lbl_2s3_laps", "_lbl_2s3_target", "_lbl_2s3_meta", "_lbl_2pit1_info", "_lbl_2pit2_info"):
            print("     ", attr, "=>", getattr(mod, attr).cget("text"))
        if ns > 2:
            print("   >>> ATENCIÓN: num_stops =", ns, "pero la UI solo tiene widgets de 2 paradas (rendered_mode=", mod._rendered_mode, ")")

# Casos de entrada degenerada
print("=" * 90)
print("Entradas degeneradas")
sd = make_session(lap="01:30.000", tank=70, rate=12, tyre=4, dur_min=60)
for cons, safety in [(0.0, 2.5), (-1.0, 2.5), (2.15, 80.0)]:
    try:
        mod = new_fuel(sd, cons, safety, 0.015)
        print(f"  cons={cons} safety={safety}: OK  trunc={mod.calc_results['truncated_laps']} viable={mod._available_stops_modes} max20={mod.calc_results['max_laps_per_stint_20']}")
    except Exception as e:
        print(f"  cons={cons} safety={safety}: CRASH {type(e).__name__}: {e}")
    try:
        mod2 = new_fuel(sd, 2.15, 2.5, 0.015)
        mod2._var_fuel_lap.set(str(cons)); mod2._var_safety_fuel.set(str(safety))
        mod2._on_params_changed()
        print(f"     _on_params_changed (Return en el campo): OK")
    except Exception as e:
        print(f"     _on_params_changed (Return en el campo): CRASH {type(e).__name__}: {e}")
# refuel_rate = 0
try:
    mod = new_fuel(make_session(rate=0.0), 3.0, 1.0, 0.02)
    print("  refuel_rate=0: OK")
except Exception as e:
    print(f"  refuel_rate=0: CRASH {type(e).__name__}: {e}")
