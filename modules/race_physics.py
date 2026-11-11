"""
Física compartida entre módulos (sin dependencias de UI).

Funciones puras usadas por Gráficos de Estrategia (strategy_charts.py) y por
Estrategia de Neumáticos (tyre_strategy.py) para que ambos calculen igual el
coste en tiempo del ahorro de combustible (Lift & Coast).
"""
from __future__ import annotations

import math

import numpy as np

# Ahorro máximo legal/físico por vuelta respecto al consumo base (Lift & Coast)
MAX_SAVING_FRACTION = 0.20


def saving_curve_from_rows(rows, cons_base: float, *, signed: bool = False,
                           fallback: tuple[float, float] = (0.35, 0.80)) -> list[tuple[float, float]]:
    """
    Convierte las filas de una tabla de ahorro (fuel_saving_rows / draft_rows) en
    puntos (litros_ahorrados_por_vuelta, delta_tiempo_s) ordenados, empezando en (0, 0).

    - signed=False: el delta de tiempo se toma en valor absoluto (tabla de Fuel Saving).
    - signed=True: conserva el signo (tabla de Rebufo, donde puede haber ganancia).
    - fallback: (delta_s al 10 %, delta_s al 20 % de ahorro) si la tabla está vacía.
    """
    pts = [(0.0, 0.0)]
    for r in rows or []:
        try:
            dl = abs(float(r.get("delta_l", r.get("saving_l", r.get("fuel_l", 0.0)))))
            ds = float(r.get("delta_s", r.get("penalty_s", r.get("time_s", 0.0))))
            if not signed:
                ds = abs(ds)
            if dl > 1e-4:
                pts.append((dl, ds))
        except Exception:
            continue

    pts.sort(key=lambda p: p[0])

    if len(pts) <= 1:
        pts = [(0.0, 0.0), (cons_base * 0.10, fallback[0]), (cons_base * 0.20, fallback[1])]
    return pts


def interpolate_saving_penalty(save_per_l: float, pts: list[tuple[float, float]]) -> float:
    """
    Pérdida/ganancia de tiempo por vuelta (s) para un ahorro de save_per_l (L/v),
    interpolando linealmente en la curva y extrapolando con la última pendiente.
    """
    if save_per_l <= 0.0001:
        return 0.0

    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]

    if save_per_l <= xs[-1]:
        return float(np.interp(save_per_l, xs, ys))
    dx = xs[-1] - xs[-2] if len(xs) >= 2 else xs[-1]
    dy = ys[-1] - ys[-2] if len(ys) >= 2 else ys[-1]
    slope = dy / max(0.001, dx)
    return float(ys[-1] + slope * (save_per_l - xs[-1]))


def stint_saving(n_racing_laps: float, fuel_needed: float, usable_tank: float, cons_base: float):
    """
    Ahorro necesario en un stint para que su combustible quepa en el depósito útil.

    Devuelve (save_needed_l_por_vuelta, target_cons, feasible), con el ahorro
    limitado al MAX_SAVING_FRACTION del consumo base. feasible=False si haría
    falta ahorrar más de ese límite (el coche se quedaría sin gasolina).
    """
    excess = max(0.0, fuel_needed - usable_tank)
    feasible = excess <= MAX_SAVING_FRACTION * cons_base * n_racing_laps + 1e-4
    if excess <= 1e-4:
        return 0.0, cons_base, feasible
    save_needed = excess / max(0.1, n_racing_laps)
    save_needed = min(save_needed, MAX_SAVING_FRACTION * cons_base)
    target_cons = max(0.1, cons_base - save_needed)
    return save_needed, target_cons, feasible


# ════════════════════════════════════════════════════════════════════
#  MODELOS DE DEGRADACIÓN DE NEUMÁTICOS
#  x = vueltas de vida de la goma (x=0 vuelta de salida, x=1 vuelta óptima,
#  x>=2 degradación). Todos devuelven segundos perdidos respecto al ritmo base.
# ════════════════════════════════════════════════════════════════════
TYRE_MODEL_KINDS = ("log", "lin", "pw")
TYRE_MODEL_LABELS = {"log": "Logarítmico", "lin": "Lineal", "pw": "A tramos"}
PW_MIN_POINTS = 6  # puntos (x >= 2) necesarios para detectar 3 zonas


def _to_float(val, default: float) -> float:
    """Convierte números o textos ('0,57', '01:57.500') a float."""
    if val is None or val == "":
        return float(default)
    if isinstance(val, (int, float)):
        return float(val)
    txt = str(val).strip().replace(",", ".")
    try:
        if ":" in txt:
            mins, secs = txt.split(":", 1)
            return float(mins) * 60.0 + float(secs)
        return float(txt)
    except ValueError:
        return float(default)


def tyre_deg(x: float, model: dict) -> float:
    """Segundos de degradación con x vueltas de vida (válido para x >= 2; nunca negativo)."""
    kind = model.get("kind", "log")
    if kind == "lin":
        return max(0.0, model["a"] * x + model["n"])
    if kind == "pw":
        y = (model["c"] + model["s1"] * x
             + model["d2"] * max(0.0, x - model["b1"])
             + model["d3"] * max(0.0, x - model["b2"]))
        return max(0.0, y)
    return max(0.0, model["a"] * math.log(max(1, x)) + model["n"])


def tyre_model_from_data(data: dict, comp: str, default_a: float, default_n: float) -> dict:
    """
    Construye el modelo de degradación de un compuesto ('hard'/'soft') a partir de los
    datos exportados o guardados por el módulo de neumáticos. Los perfiles antiguos
    (solo <comp>_a / <comp>_n) se interpretan como modelo logarítmico.
    """
    data = data or {}
    m = data.get(f"{comp}_model")
    if isinstance(m, dict) and m.get("kind") in TYRE_MODEL_KINDS:
        try:
            if m["kind"] == "pw":
                return {"kind": "pw", **{k: float(m[k]) for k in ("c", "s1", "d2", "d3", "b1", "b2")}}
            return {"kind": m["kind"], "a": float(m["a"]), "n": float(m["n"])}
        except (KeyError, TypeError, ValueError):
            pass
    return {"kind": "log",
            "a": _to_float(data.get(f"{comp}_a"), default_a),
            "n": _to_float(data.get(f"{comp}_n"), default_n)}


def _r2(ys, pred) -> float:
    ss_res = float(np.sum((ys - pred) ** 2))
    ss_tot = float(np.sum((ys - np.mean(ys)) ** 2))
    r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 1.0
    return max(0.0, min(1.0, r2))


def fit_tyre_model(kind: str, xs, ys) -> dict:
    """
    Ajusta por mínimos cuadrados el modelo pedido a los puntos (x, delta) con x >= 2.
    Devuelve el modelo con su 'r2'. Lanza ValueError si no hay puntos suficientes.

    - 'log': delta = a·ln(x) + n
    - 'lin': delta = a·x + n
    - 'pw' : lineal continuo en 3 zonas (peak, mid, cliff) con los dos cambios de
             pendiente (b1, b2) elegidos automáticamente para minimizar el error.
    """
    xs = np.asarray(xs, dtype=float)
    ys = np.asarray(ys, dtype=float)
    if len(xs) < 2 or len(set(xs.tolist())) < 2:
        raise ValueError("Se necesitan al menos 2 vueltas distintas (a partir de la 3.ª del stint).")

    if kind == "lin":
        a, n = np.polyfit(xs, ys, 1)
        return {"kind": "lin", "a": float(a), "n": float(n), "r2": _r2(ys, a * xs + n)}

    if kind == "pw":
        ux = sorted(set(xs.tolist()))
        if len(xs) < PW_MIN_POINTS or len(ux) < PW_MIN_POINTS:
            raise ValueError(f"El modelo a tramos necesita al menos {PW_MIN_POINTS} vueltas distintas "
                             "(a partir de la 3.ª del stint) para detectar las 3 zonas.")
        best = None
        # Cada zona debe contener al menos 2 vueltas medidas
        for i in range(1, len(ux) - 3):
            for j in range(i + 2, len(ux) - 1):
                b1, b2 = ux[i], ux[j]
                A = np.column_stack([np.ones_like(xs), xs, np.maximum(0.0, xs - b1), np.maximum(0.0, xs - b2)])
                coef, *_ = np.linalg.lstsq(A, ys, rcond=None)
                sse = float(np.sum((A @ coef - ys) ** 2))
                if best is None or sse < best[0] - 1e-12:
                    best = (sse, b1, b2, coef, A)
        if best is None:
            raise ValueError("No hay suficientes vueltas para separar las 3 zonas.")
        _, b1, b2, coef, A = best
        c, s1, d2, d3 = (float(v) for v in coef)
        return {"kind": "pw", "c": c, "s1": s1, "d2": d2, "d3": d3, "b1": float(b1), "b2": float(b2),
                "r2": _r2(ys, A @ coef)}

    us = np.log(xs)
    a, n = np.polyfit(us, ys, 1)
    return {"kind": "log", "a": float(a), "n": float(n), "r2": _r2(ys, a * us + n)}


def pw_zone_slopes(model: dict) -> tuple[float, float, float]:
    """Pendientes (s/vuelta) de las zonas peak, mid y cliff de un modelo a tramos."""
    s1 = model["s1"]
    return s1, s1 + model["d2"], s1 + model["d2"] + model["d3"]


# ═══════════════════════════════════════════════════════════════
#  COMPARATIVA DE COMPUESTOS: CRUCES Y PODER DE UNDERCUT
# ═══════════════════════════════════════════════════════════════

def stint_lap_time(x: int, base: float, warmup: float, model: dict) -> float:
    """Tiempo de vuelta solo por goma (a depósito lleno): x = vuelta del stint − 1."""
    if x <= 0:
        return base + warmup
    if x == 1:
        return base
    return base + tyre_deg(x, model)


def first_zero_crossing(xs, ys, start: int = 0):
    """
    Primer punto (x interpolado linealmente) en el que la serie ys cambia de signo
    a partir del índice 'start'. Devuelve None si no hay cambio de signo.
    """
    prev_i = None
    for i in range(start, len(ys)):
        if abs(ys[i]) < 1e-12:
            if prev_i is not None:
                return float(xs[i])
            continue
        if prev_i is not None and (ys[prev_i] > 0) != (ys[i] > 0):
            x0, x1, y0, y1 = xs[prev_i], xs[i], ys[prev_i], ys[i]
            return float(x0 + (x1 - x0) * (0.0 - y0) / (y1 - y0))
        prev_i = i
    return None


def compound_comparison(n_laps: int, hard: dict, soft: dict) -> dict:
    """
    Compara un stint de dura con uno de blanda vuelta a vuelta, con la misma gasolina
    (el efecto peso es igual para los dos y se anula en la diferencia).
      hard / soft = {"base": s, "warmup": s, "model": modelo de degradación}
    Devuelve:
      laps        vueltas del stint 1..n
      hard, soft  tiempo de vuelta de cada compuesto (solo goma)
      cum_diff    acumulado dura − acumulado blanda (positivo = la blanda va por delante)
      pace_cross  vuelta (decimal) en la que cambia el compuesto más rápido por vuelta
      cum_cross   vuelta (decimal) en la que el acumulado se iguala
    """
    n_laps = max(2, int(n_laps))
    laps = list(range(1, n_laps + 1))
    th = [stint_lap_time(l - 1, hard["base"], hard["warmup"], hard["model"]) for l in laps]
    ts = [stint_lap_time(l - 1, soft["base"], soft["warmup"], soft["model"]) for l in laps]
    cum, acc = [], 0.0
    for a, b in zip(th, ts):
        acc += a - b
        cum.append(acc)
    lap_diff = [a - b for a, b in zip(th, ts)]
    return {
        "laps": laps, "hard": th, "soft": ts, "cum_diff": cum,
        # La vuelta de salida (gomas frías) no cuenta para el cruce de ritmo
        "pace_cross": first_zero_crossing(laps, lap_diff, start=1),
        "cum_cross": first_zero_crossing(laps, cum, start=0),
    }


def undercut_series(new: dict, old: dict, *, tank: float, cons: float, sens: float,
                    total_laps: int, rival_extra_age: int = 0, rival_delay: int = 1,
                    safety_fuel: float = 0.0) -> tuple[list[int], list[float]]:
    """
    Poder de undercut para cada vuelta de parada L (tú paras al final de la vuelta L y el
    rival 'rival_delay' vueltas después). Valor = tiempo del rival − tu tiempo, sumado en
    las vueltas en las que tú ya llevas goma nueva y él sigue en pista:
        positivo = el undercut funciona (ganas tiempo), negativo = mejor quedarse fuera.
      new = tu goma nueva   {"base", "warmup", "model"}
      old = goma del rival  {"base", "warmup", "model"}, con L + rival_extra_age vueltas de uso
    Gasolina: los dos salieron con el depósito lleno; el rival sigue quemando (cada vez más
    ligero) y tú sales con lo necesario para acabar la carrera (máximo, el depósito).
    El tiempo en boxes es el mismo para los dos y no entra en la comparación.
    """
    if cons <= 0:
        return [], []
    rival_delay = max(1, int(rival_delay))
    laps, gains = [], []
    max_stop = int(math.floor((tank - safety_fuel) / cons + 1e-9)) - rival_delay
    max_stop = min(max_stop, int(total_laps) - rival_delay)
    for L in range(1, max_stop + 1):
        fuel_after = min(tank, (total_laps - L) * cons + safety_fuel)
        gain = 0.0
        for k in range(1, rival_delay + 1):
            my_fuel = max(0.0, fuel_after - (k - 1) * cons)
            my_t = stint_lap_time(k - 1, new["base"], new["warmup"], new["model"]) + (my_fuel - tank) * sens
            rv_fuel = max(0.0, tank - (L + k - 1) * cons)
            rv_x = L + k - 1 + max(0, int(rival_extra_age))
            rv_t = stint_lap_time(rv_x, old["base"], old["warmup"], old["model"]) + (rv_fuel - tank) * sens
            gain += rv_t - my_t
        laps.append(L)
        gains.append(gain)
    return laps, gains
