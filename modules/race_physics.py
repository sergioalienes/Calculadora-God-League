"""
Física compartida entre módulos (sin dependencias de UI).

Funciones puras usadas por Gráficos de Estrategia (strategy_charts.py) y por
Estrategia de Neumáticos (tyre_strategy.py) para que ambos calculen igual el
coste en tiempo del ahorro de combustible (Lift & Coast).
"""
from __future__ import annotations

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
