"""
Baseline numérico de no-regresión (Agente 1).

Uso:
    python scratch/agente1/baseline.py <salida.json>

Carga los perfiles reales de God League (Bélgica, Road America, Nurburgring Nordschleife)
con la GUI oculta y vuelca a JSON los resultados numéricos clave de cada módulo.
Las escrituras en profiles/ quedan bloqueadas por harness.py.
"""
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402  (aplica los parches de protección)
from harness import jsonable  # noqa: E402

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "baseline_out.json"

CHAMP = "God League"
CIRCUITS = ["Bélgica", "Road America", "Nurburgring Nordschleife"]


def lbl(w):
    try:
        return w.cget("text")
    except Exception:
        return None


def collect_fuel(app):
    fuel = app._modules["fuel"]
    out = {
        "calc_results": dict(fuel.calc_results),
        "strategy_data": {k: v for k, v in fuel.get_fuel_strategy_data().items()},
        "steps": {k: lbl(v) for k, v in fuel._step_labels.items()},
    }
    # Barrido de modos viables (la sección de sliders de stints no se monta en la UI actual)
    orig_stops = fuel._var_num_stops.get()
    sweep = {}
    for mode in list(fuel._available_stops_modes):
        fuel._on_segmented_stops_changed(mode)
        sweep[mode] = [dict(fuel.calc_results), {k: lbl(v) for k, v in fuel._step_labels.items()}]
    out["mode_sweep"] = sweep
    fuel._var_num_stops.set(orig_stops)
    fuel.calculate_strategy()
    # Viabilidad de paradas en rejilla de parámetros
    grid = []
    for laps in (12, 20, 25, 30, 31, 35, 43, 50, 70):
        for cons in (1.5, 2.15, 3.2, 4.0, 5.0, 5.65, 6.5):
            for safety in (0.0, 0.4, 2.5):
                grid.append([laps, cons, safety, fuel._evaluate_viable_stop_strategies(laps, 70.0, cons, safety)])
    out["viability_grid"] = grid
    return out


def collect_tyres(app):
    tyre = app._modules["tyres"]
    out = {
        "tyre_data": tyre.get_tyre_strategy_data(),
        "metrics": [lbl(tyre._lbl_m_total_time), lbl(tyre._lbl_m_track_time), lbl(tyre._lbl_m_box_time), lbl(tyre._lbl_m_deg_loss)],
        "lines": [list(map(float, ln.get_ydata())) for ln in tyre._ax.get_lines()],
        "pace": {c: [tyre.get_tyre_pace(c, x) for x in range(0, 40)] for c in ("hard", "soft")},
    }
    # Barrido de slider (stint 1)
    orig = (tyre._var_num_stops.get(), tyre._var_pit1_lap.get(), tyre._var_pit2_lap.get())
    sweep = []
    tot = tyre._var_total_laps.get()
    for p in range(2, tot - 1, 3):
        tyre._var_pit1_lap.set(p)
        if tyre._var_num_stops.get() == 2 and tyre._var_pit2_lap.get() <= p:
            tyre._var_pit2_lap.set(p + 1)
        tyre.recalculate_and_plot()
        sweep.append([p, lbl(tyre._lbl_m_total_time), lbl(tyre._lbl_m_track_time), lbl(tyre._lbl_m_box_time),
                      lbl(tyre._lbl_m_deg_loss),
                      [list(map(float, ln.get_ydata())) for ln in tyre._ax.get_lines()][:3]])
    out["slider_sweep"] = sweep
    tyre._var_num_stops.set(orig[0]); tyre._var_pit1_lap.set(orig[1]); tyre._var_pit2_lap.set(orig[2])
    tyre.recalculate_and_plot()

    # OLS (restaurando los valores originales tras ajustar)
    ols = {}
    for comp in ("hard", "soft"):
        vars_ = [getattr(tyre, f"_var_{comp}_{s}") for s in ("a", "n", "r2")]
        saved = [v.get() for v in vars_]
        tyre.fit_regression(comp, update_ui=False)
        ols[comp] = [v.get() for v in vars_]
        for v, s in zip(vars_, saved):
            v.set(s)
    out["ols"] = ols
    return out


def sim_summary(res):
    if not res:
        return None
    keys = ("total_laps", "lap_times", "lap_start_fuel", "lap_weight_deltas", "fuel_remaining",
            "lap_fuel_consumed", "total_race_time", "total_track_time", "total_pit_time",
            "final_fuel", "pit_info", "sc_laps", "sc_fractions", "draft_laps", "stints_def",
            "stint_targets", "p1", "p2", "post_sc_info")
    return {k: res.get(k) for k in keys}


def collect_charts(app):
    ch = app._modules["charts"]
    out = {}
    out["current_result"] = sim_summary(ch.current_result)
    t0 = time.perf_counter()
    cfg, res = ch.solve_optimal_strategy()
    out["_t_optimal"] = time.perf_counter() - t0
    out["optimal_cfg"] = cfg
    out["optimal_res"] = sim_summary(res)
    out["opp_1stop"] = None
    cand = ch._find_best_1stop_opportunity()
    if cand:
        out["opp_1stop"] = list(cand[:5]) + [sim_summary(cand[5])]

    saved = ch._load_saved_strategies_dict()
    out["saved_strategies"] = {name: sim_summary(ch.simulate_strategy_for_config(st)) for name, st in saved.items()}

    # Rejilla de simulaciones con/sin SC y rebufo
    grid = []
    tot = (ch.current_result or {}).get("total_laps", 30)
    sc_segs = [
        {"lap": 8, "sector": "Sector 2", "duration": 3, "fuel_l": 1.8},
        {"lap": 17, "sector": "Sector 3", "duration": 2, "fuel_l": 1.5},
    ]
    df_segs = [{"start": 4, "end": 10}, {"start": 20, "end": 24}]
    for sc_en in (False, True):
        for df_en in (False, True):
            for p1 in range(4, max(5, tot - 3), 4):
                grid.append(["1s", sc_en, df_en, p1, sim_summary(ch._simulate_strategy(
                    1, p1, 0, ["hard", "soft"], sc_enabled=sc_en, sc_segments=sc_segs,
                    draft_enabled=df_en, draft_segments=df_segs))])
                for p2 in range(p1 + 3, max(p1 + 4, tot - 2), 5):
                    grid.append(["2s", sc_en, df_en, p1, p2, sim_summary(ch._simulate_strategy(
                        2, p1, p2, ["soft", "hard", "hard"], sc_enabled=sc_en, sc_segments=sc_segs,
                        draft_enabled=df_en, draft_segments=df_segs))])
    out["sim_grid"] = grid

    # Optimizador con SC y con Rebufo activados (UI vars)
    for tag, sc_on, df_on in (("sc", True, False), ("draft", False, True), ("sc_draft", True, True)):
        ch._is_updating = True
        ch._var_sc_enabled.set(sc_on)
        ch._var_draft_enabled.set(df_on)
        ch._is_updating = False
        c2, r2 = ch.solve_optimal_strategy()
        out[f"optimal_{tag}"] = [c2, sim_summary(r2)]
        ch.recalculate_and_plot()
        out[f"current_{tag}"] = sim_summary(ch.current_result)
        cand = ch._find_best_1stop_opportunity()
        out[f"opp_{tag}"] = (list(cand[:5]) + [sim_summary(cand[5])]) if cand else None
    ch._is_updating = True
    ch._var_sc_enabled.set(False)
    ch._var_draft_enabled.set(False)
    ch._is_updating = False
    ch.recalculate_and_plot()
    return out


def collect_live(app):
    live = app._modules["live"]
    out = {"race_state": live.race_header.get_race_state(), "pilots": []}
    for p in live.pilots:
        pd = {"labels": [lbl(getattr(p, n, None)) for n in (
            "_lbl_curr_fuel", "_lbl_cons_stint", "_lbl_delta_fuel", "_lbl_hud_status",
            "_lbl_next_pit", "_lbl_refuel_calc")]}
        saved_meta = list(p.meta_records)
        saved_sc = (p._var_tac_sc.get(), p._var_tac_sc_sector.get(), p._var_tac_sc_dur.get())
        scen = {}
        tank = float(live.session_data.get("fuel_capacity_l", 70.0))
        cons = float(live.fuel_data.get("cons_lap", 5.0))
        for tag, meta, sc in (
            ("start", [], (False, "Sector 1", "3")),
            ("start_sc", [], (True, "Sector 2", "3")),
            ("lap5", [{"lap": 5, "fuel": tank - 5 * cons, "cons": cons}], (False, "Sector 1", "3")),
            ("lap5_sc", [{"lap": 5, "fuel": tank - 5 * cons, "cons": cons}], (True, "Sector 3", "2")),
        ):
            p.meta_records = list(meta)
            p._var_tac_sc.set(sc[0]); p._var_tac_sc_sector.set(sc[1]); p._var_tac_sc_dur.set(sc[2])
            p.tactical_result = None
            t0 = time.perf_counter()
            p.solve_tactical_strategy()
            scen[tag] = {"_t": time.perf_counter() - t0, "result": getattr(p, "tactical_result", None),
                         "desc": lbl(getattr(p, "_lbl_tac_desc", None))}
        p.meta_records = saved_meta
        p._var_tac_sc.set(saved_sc[0]); p._var_tac_sc_sector.set(saved_sc[1]); p._var_tac_sc_dur.set(saved_sc[2])
        p.tactical_result = None
        pd["tactical"] = scen
        out["pilots"].append(pd)
    return out


def main():
    t_start = time.perf_counter()
    import main as app_main
    t_import = time.perf_counter()
    app = app_main.CalculadoraApp()
    app.withdraw()
    app.update_idletasks()
    t_app = time.perf_counter()
    result = {"_timing": {"import_s": t_import - t_start, "app_init_s": t_app - t_import}, "circuits": {}}

    champ = app._modules["championship"]
    for circ in CIRCUITS:
        ok = champ.load_session_by_names(CHAMP, circ)
        circ_out = {"loaded": ok, "session_data": dict(champ.get_session_data())}
        timings = {}
        for mod in ("fuel", "tyres", "charts", "live"):
            t0 = time.perf_counter()
            app.navigate_to(mod)
            app.update_idletasks()
            timings[f"nav_{mod}"] = time.perf_counter() - t0
            if mod == "fuel":
                circ_out["fuel"] = collect_fuel(app)
            elif mod == "tyres":
                circ_out["tyres"] = collect_tyres(app)
            elif mod == "charts":
                circ_out["charts"] = collect_charts(app)
            elif mod == "live":
                circ_out["live"] = collect_live(app)
        circ_out["_timing"] = timings
        result["circuits"][circ] = circ_out
        app.navigate_to("championship")

    result["_blocked_writes"] = sorted(set(harness.BLOCKED_WRITES))
    result["_timing"]["total_s"] = time.perf_counter() - t_start
    OUT.write_text(json.dumps(jsonable(result), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[baseline] OK -> {OUT}  ({result['_timing']['total_s']:.1f}s)")
    print(f"[baseline] escrituras bloqueadas en profiles/: {len(set(harness.BLOCKED_WRITES))}")
    try:
        app.destroy()
    except Exception:
        pass


if __name__ == "__main__":
    main()
