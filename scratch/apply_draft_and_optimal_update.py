import re
from pathlib import Path

charts_path = Path("modules/strategy_charts.py")
content = charts_path.read_text(encoding="utf-8")

# 1. Update _get_fuel_saving_curve, _get_draft_saving_curve, _interpolate_saving_penalty, _get_draft_saving_l
old_curve_block = '''    def _get_fuel_saving_curve(self) -> list[tuple[float, float]]:
        """
        Obtiene los puntos de calibración (delta_litros_ahorrados, delta_tiempo_perdido)
        de la tabla de combustible de la sesión para correlacionar en tiempo real.
        """
        rows = []
        if self._active_fuel_override and "fuel_saving_rows" in self._active_fuel_override:
            rows = self._active_fuel_override["fuel_saving_rows"]

        if not rows and self.fuel_data and "fuel_saving_rows" in self.fuel_data:
            rows = self.fuel_data["fuel_saving_rows"]

        if not rows:
            champ = self.session_data.get("championship_name")
            circuit = self.session_data.get("circuit")
            if champ and circuit:
                safe_champ = re.sub(r'[\\\\/*?:"<>|]', "_", champ)
                safe_circ = re.sub(r'[\\\\/*?:"<>|]', "_", circuit)
                f_path = PROFILES_ROOT / safe_champ / f"{safe_circ}_fuel.json"
                if f_path.exists():
                    try:
                        data = json.loads(f_path.read_text(encoding="utf-8"))
                        rows = data.get("fuel_saving_rows", [])
                    except Exception:
                        pass

        pts = [(0.0, 0.0)]
        for r in rows:
            try:
                dl = abs(float(r.get("delta_l", r.get("saving_l", r.get("fuel_l", 0.0)))))
                ds = abs(float(r.get("delta_s", r.get("penalty_s", r.get("time_s", 0.0)))))
                if dl > 1e-4:
                    pts.append((dl, ds))
            except Exception:
                continue

        pts.sort(key=lambda p: p[0])

        if len(pts) <= 1:
            cons_base = self._get_base_consumption()
            # Fallback analítico estándar: ~0.35s por 10% ahorro, ~0.80s por 20% ahorro
            pts = [(0.0, 0.0), (cons_base * 0.10, 0.35), (cons_base * 0.20, 0.80)]

        return pts

    def _interpolate_saving_penalty(self, save_per_l: float, pts: list[tuple[float, float]]) -> float:
        """
        Interpola en tiempo real la pérdida de tiempo por vuelta (s)
        para un ahorro objetivo de save_per_l (L/v), correlacionando con la tabla de combustible.
        """
        if save_per_l <= 0.001:
            return 0.0

        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]

        if save_per_l <= xs[-1]:
            return float(np.interp(save_per_l, xs, ys))
        else:
            dx = xs[-1] - xs[-2] if len(xs) >= 2 else xs[-1]
            dy = ys[-1] - ys[-2] if len(ys) >= 2 else ys[-1]
            slope = dy / max(0.01, dx)
            return float(ys[-1] + slope * (save_per_l - xs[-1]))

    def _get_draft_saving_l(self) -> float:
        """
        Obtiene la reducción de consumo por rebufo (L/v) definida en la tabla de combustible.
        Siempre devuelve un valor negativo (p. ej. -0.25) para descontar en el consumo por vuelta.
        """
        rows = []
        if self._active_fuel_override and "draft_rows" in self._active_fuel_override:
            rows = self._active_fuel_override["draft_rows"]

        if not rows and self.fuel_data and "draft_rows" in self.fuel_data:
            rows = self.fuel_data["draft_rows"]

        if not rows:
            champ = self.session_data.get("championship_name")
            circuit = self.session_data.get("circuit")
            if champ and circuit:
                safe_champ = re.sub(r'[\\\\/*?:"<>|]', "_", champ)
                safe_circ = re.sub(r'[\\\\/*?:"<>|]', "_", circuit)
                f_path = PROFILES_ROOT / safe_champ / f"{safe_circ}_fuel.json"
                if f_path.exists():
                    try:
                        data = json.loads(f_path.read_text(encoding="utf-8"))
                        rows = data.get("draft_rows", [])
                    except Exception:
                        pass

        if rows:
            try:
                raw_dl = float(rows[0].get("delta_l", rows[0].get("saving_l", -0.25)))
                return -abs(raw_dl) if raw_dl != 0.0 else -0.25
            except Exception:
                pass

        return -0.25'''

new_curve_block = '''    def _get_fuel_saving_curve(self) -> list[tuple[float, float]]:
        """
        Obtiene los puntos de calibración (delta_litros_ahorrados, delta_tiempo_perdido)
        de la tabla de combustible de la sesión para correlacionar en tiempo real.
        """
        rows = []
        if self._active_fuel_override and "fuel_saving_rows" in self._active_fuel_override:
            rows = self._active_fuel_override["fuel_saving_rows"]

        if not rows and self.fuel_data and "fuel_saving_rows" in self.fuel_data:
            rows = self.fuel_data["fuel_saving_rows"]

        if not rows:
            champ = self.session_data.get("championship_name")
            circuit = self.session_data.get("circuit")
            if champ and circuit:
                safe_champ = re.sub(r'[\\/*?:"<>|]', "_", champ)
                safe_circ = re.sub(r'[\\/*?:"<>|]', "_", circuit)
                f_path = PROFILES_ROOT / safe_champ / f"{safe_circ}_fuel.json"
                if f_path.exists():
                    try:
                        data = json.loads(f_path.read_text(encoding="utf-8"))
                        rows = data.get("fuel_saving_rows", [])
                    except Exception:
                        pass

        pts = [(0.0, 0.0)]
        for r in rows:
            try:
                dl = abs(float(r.get("delta_l", r.get("saving_l", r.get("fuel_l", 0.0)))))
                ds = abs(float(r.get("delta_s", r.get("penalty_s", r.get("time_s", 0.0)))))
                if dl > 1e-4:
                    pts.append((dl, ds))
            except Exception:
                continue

        pts.sort(key=lambda p: p[0])

        if len(pts) <= 1:
            cons_base = self._get_base_consumption()
            # Fallback analítico estándar: ~0.35s por 10% ahorro, ~0.80s por 20% ahorro
            pts = [(0.0, 0.0), (cons_base * 0.10, 0.35), (cons_base * 0.20, 0.80)]

        return pts

    def _get_draft_saving_curve(self) -> list[tuple[float, float]]:
        """
        Obtiene los puntos de calibración (delta_litros_ahorrados, delta_tiempo)
        de la tabla de rebufo (draft_rows) de la sesión para correlacionar en tiempo real.
        """
        rows = []
        if self._active_fuel_override and "draft_rows" in self._active_fuel_override:
            rows = self._active_fuel_override["draft_rows"]

        if not rows and self.fuel_data and "draft_rows" in self.fuel_data:
            rows = self.fuel_data["draft_rows"]

        if not rows:
            champ = self.session_data.get("championship_name")
            circuit = self.session_data.get("circuit")
            if champ and circuit:
                safe_champ = re.sub(r'[\\/*?:"<>|]', "_", champ)
                safe_circ = re.sub(r'[\\/*?:"<>|]', "_", circuit)
                f_path = PROFILES_ROOT / safe_champ / f"{safe_circ}_fuel.json"
                if f_path.exists():
                    try:
                        data = json.loads(f_path.read_text(encoding="utf-8"))
                        rows = data.get("draft_rows", [])
                    except Exception:
                        pass

        pts = [(0.0, 0.0)]
        for r in rows:
            try:
                dl = abs(float(r.get("delta_l", r.get("saving_l", r.get("fuel_l", 0.0)))))
                # delta_s conserva su signo (puede ser ganancia de tiempo negativa o leve pérdida positiva)
                ds = float(r.get("delta_s", r.get("penalty_s", r.get("time_s", 0.0))))
                if dl > 1e-4:
                    pts.append((dl, ds))
            except Exception:
                continue

        pts.sort(key=lambda p: p[0])

        if len(pts) <= 1:
            cons_base = self._get_base_consumption()
            # Fallback analítico estándar rebufo: ~-0.05s por 10% ahorro, ~-0.10s por 20% ahorro
            pts = [(0.0, 0.0), (cons_base * 0.10, -0.05), (cons_base * 0.20, -0.10)]

        return pts

    def _interpolate_saving_penalty(self, save_per_l: float, pts: list[tuple[float, float]]) -> float:
        """
        Interpola en tiempo real la pérdida/ganancia de tiempo por vuelta (s)
        para un ahorro objetivo de save_per_l (L/v), correlacionando con la tabla de combustible.
        """
        if save_per_l <= 0.0001:
            return 0.0

        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]

        if save_per_l <= xs[-1]:
            return float(np.interp(save_per_l, xs, ys))
        else:
            dx = xs[-1] - xs[-2] if len(xs) >= 2 else xs[-1]
            dy = ys[-1] - ys[-2] if len(ys) >= 2 else ys[-1]
            slope = dy / max(0.001, dx)
            return float(ys[-1] + slope * (save_per_l - xs[-1]))

    def _get_draft_saving_l(self) -> float:
        """
        Obtiene la reducción máxima de consumo por rebufo (L/v) definida en la tabla de combustible.
        Siempre devuelve un valor negativo (p. ej. -0.45) para descontar en el consumo por vuelta.
        """
        curve = self._get_draft_saving_curve()
        if len(curve) > 1:
            return -abs(curve[-1][0])
        return -0.25'''

# Normalize line endings for replacement
norm_content = content.replace("\r\n", "\n")
norm_old_block = old_curve_block.replace("\r\n", "\n")

if norm_old_block in norm_content:
    norm_content = norm_content.replace(norm_old_block, new_curve_block)
    print("Block 1 (curves and interpolation) replaced successfully!")
else:
    print("Block 1 NOT found!")

# 2. Update _simulate_pass inside _simulate_strategy
old_sim_pass = '''            # 6. Cálculo previo de necesidad de combustible y penalización por ahorro (Lift & Coast)
            usable_tank = max(1.0, tank_cap - safety_l)
            stint_saving_penalties = []
            saving_curve = self._get_fuel_saving_curve()

            for _, start_v, end_v, _ in stints_def:
                st_len = end_v - start_v + 1
                st_sc_count = sum(sc_fractions.get(v, 0.0) for v in range(start_v, end_v + 1))
                st_draft_count = len([v for v in range(start_v, end_v + 1) if (v in draft_laps_set and v not in sc_laps_set)])
                st_pure_green_count = max(0.0, st_len - st_sc_count - st_draft_count)

                f_needed = 0.0
                for v in range(start_v, end_v + 1):
                    if v in sc_laps_set:
                        frac = sc_fractions.get(v, 1.0)
                        f_needed += (1.0 - frac) * cons_base + frac * sc_fuel_map.get(v, 1.80)
                    elif v in draft_laps_set:
                        # El ahorro en rebufo se lee de la tabla de combustible
                        f_needed += max(0.1, cons_base + draft_saving_l)
                    else:
                        f_needed += cons_base

                # Si el combustible necesario (ya beneficiado por SC y rebufo) supera el tanque usable:
                if f_needed > usable_tank and st_pure_green_count > 0:
                    excess = f_needed - usable_tank
                    save_per_l = excess / st_pure_green_count
                    save_per_l = min(save_per_l, 0.20 * cons_base)
                    # Correlación en tiempo real con la tabla de combustible
                    time_penalty = self._interpolate_saving_penalty(save_per_l, saving_curve)
                else:
                    save_per_l = 0.0
                    time_penalty = 0.0

                stint_saving_penalties.append((save_per_l, time_penalty))

            # 7. Simulación Vuelta a Vuelta
            lap_times = []
            fuel_remaining = []
            lap_fuel_consumed = []
            curr_fuel = tank_cap
            pit_info = []  # (pit_lap, pit_time, fuel_loaded, is_sc_gratis)
            total_pit_time = 0.0
            stint_targets = []

            for s_idx, (st_num, start_v, end_v, comp) in enumerate(stints_def):
                save_l, t_pen = stint_saving_penalties[s_idx]

                base_p = h_base if comp == "hard" else s_base
                warmup = h_warm if comp == "hard" else s_warm
                a_val = h_a if comp == "hard" else s_a
                n_val = h_n if comp == "hard" else s_n

                tyre_x = 0  # Vida del neumático en vueltas lanzadas
                st_fuel_initial = curr_fuel
                st_sc_count = 0.0
                st_draft_count = 0

                for v in range(start_v, end_v + 1):
                    delta_peso = (curr_fuel - tank_cap) * weight_sens
                    delta_peso = min(0.0, delta_peso)

                    is_sc = (v in sc_laps_set)
                    is_draft = (v in draft_laps_set and not is_sc)

                    if is_sc:
                        frac = sc_fractions.get(v, 1.0)
                        st_sc_count += frac
                        sc_f = sc_fuel_map.get(v, 1.80)
                        if tyre_x == 0:
                            t_deg = warmup
                        elif tyre_x == 1:
                            t_deg = 0.0
                        else:
                            t_deg = max(0.0, a_val * math.log(tyre_x) + n_val)

                        t_green = base_p + t_deg + delta_peso + t_pen
                        t_lap = (1.0 - frac) * t_green + frac * sc_pace_full
                        cons_lap = (1.0 - frac) * cons_base + frac * sc_f
                        if (1.0 - frac) >= 0.5:
                            tyre_x += 1
                    elif is_draft:
                        # REBUFO LEYENDO DE LA TABLA DE COMBUSTIBLE:
                        # El ritmo del stint queda definido tal y como se hace como si no hubiera rebufo
                        st_draft_count += 1
                        if tyre_x == 0:
                            t_deg = warmup
                        elif tyre_x == 1:
                            t_deg = 0.0
                        else:
                            t_deg = max(0.0, a_val * math.log(tyre_x) + n_val)

                        t_lap = base_p + t_deg + delta_peso + t_pen
                        cons_lap = max(0.1, cons_base + draft_saving_l)
                        tyre_x += 1
                    else:
                        # VUELTA VERDE PURA (SIN REBUFO):
                        # Se aplica el ahorro Lift & Coast y la penalización de tiempo correlacionada
                        if tyre_x == 0:
                            t_deg = warmup
                        elif tyre_x == 1:
                            t_deg = 0.0
                        else:
                            t_deg = max(0.0, a_val * math.log(tyre_x) + n_val)

                        t_lap = base_p + t_deg + delta_peso + t_pen
                        cons_lap = max(0.1, cons_base - save_l)
                        tyre_x += 1'''

new_sim_pass = '''            # 6. Cálculo previo de necesidad de combustible y penalización por ahorro (Lift & Coast y Rebufo)
            usable_tank = max(1.0, tank_cap - safety_l)
            stint_saving_penalties = []
            saving_curve = self._get_fuel_saving_curve()
            draft_curve = self._get_draft_saving_curve()
            max_draft_l = draft_curve[-1][0] if len(draft_curve) > 1 else (0.15 * cons_base)

            for _, start_v, end_v, _ in stints_def:
                st_len = end_v - start_v + 1
                st_sc_count = sum(sc_fractions.get(v, 0.0) for v in range(start_v, end_v + 1))
                st_draft_count = len([v for v in range(start_v, end_v + 1) if (v in draft_laps_set and v not in sc_laps_set)])
                st_pure_green_count = max(0.0, st_len - st_sc_count - st_draft_count)

                # Combustible requerido a ritmo base sin ahorro adicional
                f_needed_base = 0.0
                for v in range(start_v, end_v + 1):
                    if v in sc_laps_set:
                        frac = sc_fractions.get(v, 1.0)
                        f_needed_base += (1.0 - frac) * cons_base + frac * sc_fuel_map.get(v, 1.80)
                    else:
                        f_needed_base += cons_base

                excess = max(0.0, f_needed_base - usable_tank)

                save_draft = 0.0
                t_pen_draft = 0.0
                save_green = 0.0
                t_pen_green = 0.0

                if excess <= 1e-4:
                    # Sin déficit de combustible en el tanque:
                    # Si hay tramo de rebufo, se aplica el ahorro natural de rebufo de la tabla
                    if st_draft_count > 0:
                        save_draft = min(max_draft_l, 0.20 * cons_base)
                        t_pen_draft = self._interpolate_saving_penalty(save_draft, draft_curve)
                else:
                    # Hay déficit de combustible en el stint:
                    if st_pure_green_count == 0 and st_draft_count > 0:
                        # Todo el stint restante es rebufo: absorbe todo el ahorro
                        save_draft = min(0.20 * cons_base, excess / st_draft_count)
                        t_pen_draft = self._interpolate_saving_penalty(save_draft, draft_curve)
                    elif st_draft_count == 0 and st_pure_green_count > 0:
                        # Todo el stint restante es verde limpio: ahorro Lift & Coast
                        save_green = min(0.20 * cons_base, excess / st_pure_green_count)
                        t_pen_green = self._interpolate_saving_penalty(save_green, saving_curve)
                    elif st_draft_count > 0 and st_pure_green_count > 0:
                        # Hay vueltas a rebufo y vueltas en aire limpio:
                        # Prioridad de ahorro en rebufo (más eficiente y menor pérdida de tiempo)
                        cap_draft = st_draft_count * max_draft_l
                        if excess <= cap_draft:
                            save_draft = excess / st_draft_count
                            t_pen_draft = self._interpolate_saving_penalty(save_draft, draft_curve)
                            save_green = 0.0
                            t_pen_green = 0.0
                        else:
                            save_draft = max_draft_l
                            t_pen_draft = self._interpolate_saving_penalty(save_draft, draft_curve)
                            rem_excess = excess - cap_draft
                            save_green = min(0.20 * cons_base, rem_excess / st_pure_green_count)
                            t_pen_green = self._interpolate_saving_penalty(save_green, saving_curve)

                stint_saving_penalties.append((save_draft, t_pen_draft, save_green, t_pen_green))

            # 7. Simulación Vuelta a Vuelta
            lap_times = []
            fuel_remaining = []
            lap_fuel_consumed = []
            curr_fuel = tank_cap
            pit_info = []  # (pit_lap, pit_time, fuel_loaded, is_sc_gratis)
            total_pit_time = 0.0
            stint_targets = []

            for s_idx, (st_num, start_v, end_v, comp) in enumerate(stints_def):
                save_draft, t_pen_draft, save_green, t_pen_green = stint_saving_penalties[s_idx]

                base_p = h_base if comp == "hard" else s_base
                warmup = h_warm if comp == "hard" else s_warm
                a_val = h_a if comp == "hard" else s_a
                n_val = h_n if comp == "hard" else s_n

                tyre_x = 0  # Vida del neumático en vueltas lanzadas
                st_fuel_initial = curr_fuel
                st_sc_count = 0.0
                st_draft_count = 0

                for v in range(start_v, end_v + 1):
                    delta_peso = (curr_fuel - tank_cap) * weight_sens
                    delta_peso = min(0.0, delta_peso)

                    is_sc = (v in sc_laps_set)
                    is_draft = (v in draft_laps_set and not is_sc)

                    if is_sc:
                        frac = sc_fractions.get(v, 1.0)
                        st_sc_count += frac
                        sc_f = sc_fuel_map.get(v, 1.80)
                        if tyre_x == 0:
                            t_deg = warmup
                        elif tyre_x == 1:
                            t_deg = 0.0
                        else:
                            t_deg = max(0.0, a_val * math.log(tyre_x) + n_val)

                        t_green = base_p + t_deg + delta_peso + t_pen_green
                        t_lap = (1.0 - frac) * t_green + frac * sc_pace_full
                        cons_lap = (1.0 - frac) * max(0.1, cons_base - save_green) + frac * sc_f
                        if (1.0 - frac) >= 0.5:
                            tyre_x += 1
                    elif is_draft:
                        # REBUFO LEYENDO DE LA TABLA DE COMBUSTIBLE:
                        # Utiliza exclusivamente la pérdida o ganancia de tiempo de la tabla de rebufo
                        st_draft_count += 1
                        if tyre_x == 0:
                            t_deg = warmup
                        elif tyre_x == 1:
                            t_deg = 0.0
                        else:
                            t_deg = max(0.0, a_val * math.log(tyre_x) + n_val)

                        t_lap = base_p + t_deg + delta_peso + t_pen_draft
                        cons_lap = max(0.1, cons_base - save_draft)
                        tyre_x += 1
                    else:
                        # VUELTA VERDE PURA (SIN REBUFO):
                        # Se aplica el ahorro Lift & Coast y la penalización de tiempo correlacionada
                        if tyre_x == 0:
                            t_deg = warmup
                        elif tyre_x == 1:
                            t_deg = 0.0
                        else:
                            t_deg = max(0.0, a_val * math.log(tyre_x) + n_val)

                        t_lap = base_p + t_deg + delta_peso + t_pen_green
                        cons_lap = max(0.1, cons_base - save_green)
                        tyre_x += 1'''

norm_old_sim = old_sim_pass.replace("\r\n", "\n")
if norm_old_sim in norm_content:
    norm_content = norm_content.replace(norm_old_sim, new_sim_pass)
    print("Block 2 (simulate pass) replaced successfully!")
else:
    print("Block 2 NOT found!")

# 3. Update mode_parts in stint_targets: save_l -> save_green
old_mode = '''                if save_l > 0.01:
                    mode_parts.append(f"🟡 Ahorro (-{save_l:.2f}L)")'''
new_mode = '''                if save_green > 0.01:
                    mode_parts.append(f"🟡 Ahorro (-{save_green:.2f}L)")'''

if old_mode in norm_content:
    norm_content = norm_content.replace(old_mode, new_mode)
    print("Block 3 (mode parts) replaced successfully!")
else:
    print("Block 3 NOT found!")

# 4. Update solve_optimal_strategy to respect active SC and Rebufo simultaneously
old_solve = '''        # 1. Evaluar 1 Parada si es viable y no se ha forzado el Stint 3 (que solo existe en 2 paradas)
        if "1 Parada" in viable_modes and ("Duro" not in f3 and "Blando" not in f3):
            p1_min = max(1, total_laps_base - max_laps_save20)
            p1_max = min(max_laps_save20, total_laps_base - 1)

            pairs = [("hard", "soft"), ("soft", "hard")]
            if not mandatory_change:
                pairs.extend([("hard", "hard"), ("soft", "soft")])

            pairs = [p for p in pairs if match_comp(p[0], f1) and match_comp(p[1], f2)]

            for p1 in range(p1_min, p1_max + 1):
                st1_l = p1
                st2_l = total_laps_base - p1
                if st1_l > max_laps_save20 or st2_l > max_laps_save20:
                    continue

                for c1, c2 in pairs:
                    res = self._simulate_strategy(
                        num_stops=1,
                        p1=p1,
                        p2=0,
                        stint_comps=[c1, c2],
                        sc_enabled=False,
                        draft_enabled=False,
                    )
                    if res["total_race_time"] < min_time:
                        min_time = res["total_race_time"]
                        best_res = res
                        best_cfg = {
                            "num_stops": 1,
                            "p1": p1,
                            "p2": 0,
                            "stint1_comp": c1,
                            "stint2_comp": c2,
                            "stint3_comp": "soft",
                        }

        # 2. Evaluar 2 Paradas si es viable
        if "2 Paradas" in viable_modes:
            triplets = [
                ("hard", "hard", "soft"),
                ("hard", "soft", "hard"),
                ("soft", "hard", "hard"),
                ("soft", "hard", "soft"),
                ("hard", "soft", "soft"),
                ("soft", "soft", "hard"),
            ]
            if not mandatory_change:
                triplets.extend([("hard", "hard", "hard"), ("soft", "soft", "soft")])

            triplets = [
                t for t in triplets
                if match_comp(t[0], f1) and match_comp(t[1], f2) and match_comp(t[2], f3)
            ]

            p1_min = max(1, total_laps_base - 2 * max_laps_save20)
            p1_max = min(max_laps_save20, total_laps_base - 2)

            for p1 in range(p1_min, p1_max + 1):
                if p1 > max_laps_save20:
                    continue
                p2_min = p1 + 1
                p2_max = min(p1 + max_laps_save20, total_laps_base - 1)

                for p2 in range(p2_min, p2_max + 1):
                    st2_l = p2 - p1
                    st3_l = total_laps_base - p2
                    if st2_l > max_laps_save20 or st3_l > max_laps_save20:
                        continue

                    for c1, c2, c3 in triplets:
                        res = self._simulate_strategy(
                            num_stops=2,
                            p1=p1,
                            p2=p2,
                            stint_comps=[c1, c2, c3],
                            sc_enabled=False,
                            draft_enabled=False,
                        )'''

new_solve = '''        sc_en = self._var_sc_enabled.get()
        sc_segs = self._get_active_sc_segments() if sc_en else []
        df_en = self._var_draft_enabled.get()
        df_segs = self._get_active_draft_segments() if df_en else []

        max_stint_laps = max_laps_save20
        if sc_en or df_en:
            max_stint_laps = min(total_laps_base, math.floor(usable_tank / max(0.5, cons_base * 0.70)))

        # 1. Evaluar 1 Parada si es viable y no se ha forzado el Stint 3 (que solo existe en 2 paradas)
        if "1 Parada" in viable_modes and ("Duro" not in f3 and "Blando" not in f3):
            p1_min = max(1, total_laps_base - max_stint_laps)
            p1_max = min(max_stint_laps, total_laps_base - 1)

            pairs = [("hard", "soft"), ("soft", "hard")]
            if not mandatory_change:
                pairs.extend([("hard", "hard"), ("soft", "soft")])

            pairs = [p for p in pairs if match_comp(p[0], f1) and match_comp(p[1], f2)]

            for p1 in range(p1_min, p1_max + 1):
                st1_l = p1
                st2_l = total_laps_base - p1
                if st1_l > max_stint_laps or st2_l > max_stint_laps:
                    continue

                for c1, c2 in pairs:
                    res = self._simulate_strategy(
                        num_stops=1,
                        p1=p1,
                        p2=0,
                        stint_comps=[c1, c2],
                        sc_enabled=sc_en,
                        sc_segments=sc_segs,
                        draft_enabled=df_en,
                        draft_segments=df_segs,
                    )
                    if res["total_race_time"] < min_time:
                        min_time = res["total_race_time"]
                        best_res = res
                        best_cfg = {
                            "num_stops": 1,
                            "p1": p1,
                            "p2": 0,
                            "stint1_comp": c1,
                            "stint2_comp": c2,
                            "stint3_comp": "soft",
                        }

        # 2. Evaluar 2 Paradas si es viable
        if "2 Paradas" in viable_modes:
            triplets = [
                ("hard", "hard", "soft"),
                ("hard", "soft", "hard"),
                ("soft", "hard", "hard"),
                ("soft", "hard", "soft"),
                ("hard", "soft", "soft"),
                ("soft", "soft", "hard"),
            ]
            if not mandatory_change:
                triplets.extend([("hard", "hard", "hard"), ("soft", "soft", "soft")])

            triplets = [
                t for t in triplets
                if match_comp(t[0], f1) and match_comp(t[1], f2) and match_comp(t[2], f3)
            ]

            p1_min = max(1, total_laps_base - 2 * max_stint_laps)
            p1_max = min(max_stint_laps, total_laps_base - 2)

            for p1 in range(p1_min, p1_max + 1):
                if p1 > max_stint_laps:
                    continue
                p2_min = p1 + 1
                p2_max = min(p1 + max_stint_laps, total_laps_base - 1)

                for p2 in range(p2_min, p2_max + 1):
                    st2_l = p2 - p1
                    st3_l = total_laps_base - p2
                    if st2_l > max_stint_laps or st3_l > max_stint_laps:
                        continue

                    for c1, c2, c3 in triplets:
                        res = self._simulate_strategy(
                            num_stops=2,
                            p1=p1,
                            p2=p2,
                            stint_comps=[c1, c2, c3],
                            sc_enabled=sc_en,
                            sc_segments=sc_segs,
                            draft_enabled=df_en,
                            draft_segments=df_segs,
                        )'''

norm_old_solve = old_solve.replace("\r\n", "\n")
if norm_old_solve in norm_content:
    norm_content = norm_content.replace(norm_old_solve, new_solve)
    print("Block 4 (solve optimal strategy coexisting with SC and draft) replaced successfully!")
else:
    print("Block 4 NOT found!")

# 5. Update _find_best_1stop_opportunity draft handling & factor identification
old_opp = '''        if best_p is not None:
            has_sc = (sc_en and len(sc_laps_set) > 0)
            has_df = (df_en and len(draft_laps_set) > 0)
            if has_sc and has_df:
                factor = "COMBINADA (SC + REBUFO)"
            elif has_sc:
                factor = "SAFETY CAR"
            elif has_df:
                factor = "REBUFO"
            else:
                factor = "AHORRO DE COMBUSTIBLE"

            return (best_p, best_c1, best_c2, best_time, factor, best_res)
        return None'''

new_opp = '''        if best_p is not None:
            has_sc = bool(sc_en and sc_segs)
            has_df = bool(df_en and draft_laps_set)
            if has_sc and has_df:
                factor = "COMBINADA (SC + REBUFO)"
            elif has_sc:
                factor = "SAFETY CAR"
            elif has_df:
                factor = "REBUFO"
            else:
                factor = "AHORRO DE COMBUSTIBLE"

            return (best_p, best_c1, best_c2, best_time, factor, best_res)
        return None'''

norm_old_opp = old_opp.replace("\r\n", "\n")
if norm_old_opp in norm_content:
    norm_content = norm_content.replace(norm_old_opp, new_opp)
    print("Block 5 (factor identification) replaced successfully!")
else:
    print("Block 5 NOT found!")

# Also in _find_best_1stop_opportunity: update st1_min_fuel and st2_min_fuel draft saving check
old_opp_fuel = '''                elif v in draft_laps_set:
                    st1_min_fuel += max(0.1, cons_base + draft_saving_l)'''
new_opp_fuel = '''                elif v in draft_laps_set:
                    st1_min_fuel += max(0.1, cons_base * 0.80)'''

if old_opp_fuel in norm_content:
    norm_content = norm_content.replace(old_opp_fuel, new_opp_fuel)
    print("Block 6 (opp fuel st1) replaced successfully!")

old_opp_fuel2 = '''                elif v in draft_laps_set:
                    st2_min_fuel += max(0.1, cons_base + draft_saving_l)'''
new_opp_fuel2 = '''                elif v in draft_laps_set:
                    st2_min_fuel += max(0.1, cons_base * 0.80)'''

if old_opp_fuel2 in norm_content:
    norm_content = norm_content.replace(old_opp_fuel2, new_opp_fuel2)
    print("Block 7 (opp fuel st2) replaced successfully!")

charts_path.write_text(norm_content, encoding="utf-8")
print("All changes written successfully to modules/strategy_charts.py!")
