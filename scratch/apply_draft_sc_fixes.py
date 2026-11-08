import sys
from pathlib import Path

target_file = Path("modules/strategy_charts.py")
content = target_file.read_text(encoding="utf-8")

# 1. Add _sc_post_time_frame in _build_chart_section
target_1 = """        # Conectar evento interactivo de clic sobre el canvas
        self._mpl_canvas.mpl_connect("button_press_event", self._on_chart_clicked)"""

replacement_1 = """        # Conectar evento interactivo de clic sobre el canvas
        self._mpl_canvas.mpl_connect("button_press_event", self._on_chart_clicked)

        # Apunte de tiempo total de carrera tras Safety Car (al terminar el SC)
        self._sc_post_time_frame = ctk.CTkFrame(
            chart_wrapper,
            fg_color="#181500",
            corner_radius=8,
            border_width=1,
            border_color="#FFD60A",
        )
        self._lbl_sc_post_time = ctk.CTkLabel(
            self._sc_post_time_frame,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#FFD60A",
            anchor="w",
            justify="left",
        )
        self._lbl_sc_post_time.pack(side="left", padx=14, pady=8, fill="x", expand=True)"""

if target_1 not in content:
    print("ERROR: target_1 not found!")
    sys.exit(1)
content = content.replace(target_1, replacement_1, 1)

# 2. Update _simulate_pass saving and draft logic
target_2 = """            # 6. Cálculo previo de necesidad de combustible y penalización por ahorro (Lift & Coast y Rebufo)
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
                        tyre_x += 1

                    lap_times.append(t_lap)
                    curr_fuel = max(0.0, curr_fuel - cons_lap)
                    fuel_remaining.append(curr_fuel)
                    lap_fuel_consumed.append(cons_lap)"""

replacement_2 = """            # 6. Cálculo previo de necesidad de combustible y penalización por ahorro (Lift & Coast y Rebufo)
            usable_tank = max(1.0, tank_cap - safety_l)
            stint_saving_penalties = []
            saving_curve = self._get_fuel_saving_curve()
            draft_curve = self._get_draft_saving_curve()

            for _, start_v, end_v, _ in stints_def:
                st_len = end_v - start_v + 1
                st_sc_count = sum(sc_fractions.get(v, 0.0) for v in range(start_v, end_v + 1))
                st_draft_count = len([v for v in range(start_v, end_v + 1) if (v in draft_laps_set and v not in sc_laps_set)])
                n_racing_laps = max(0.0, sum(1.0 - sc_fractions.get(v, 0.0) for v in range(start_v, end_v + 1)))

                # Combustible requerido a ritmo base sin ahorro adicional
                fuel_sc = sum(sc_fractions.get(v, 0.0) * sc_fuel_map.get(v, 1.80) for v in range(start_v, end_v + 1))
                fuel_needed_racing = n_racing_laps * cons_base
                f_needed_base = fuel_sc + fuel_needed_racing

                excess = max(0.0, f_needed_base - usable_tank)

                if excess <= 1e-4:
                    # Sin déficit de combustible en el tanque:
                    # El stint cabe con holgura a ritmo base, no se exige ahorro artificial
                    save_needed = 0.0
                    target_cons = cons_base
                    t_pen_draft = 0.0
                    t_pen_green = 0.0
                else:
                    # Hay déficit de combustible en el stint:
                    # Se calcula el consumo necesario uniforme por vuelta de carrera del stint
                    save_needed = excess / max(0.1, n_racing_laps)
                    save_needed = min(save_needed, 0.20 * cons_base)
                    target_cons = max(0.1, cons_base - save_needed)

                    # Se interpola la pérdida de tiempo según la tabla correspondiente:
                    # 1. En vueltas con rebufo: de la tabla de rebufo (draft_rows)
                    t_pen_draft = self._interpolate_saving_penalty(save_needed, draft_curve)
                    # 2. En vueltas normales: de la tabla normal de combustible (fuel_saving_rows)
                    t_pen_green = self._interpolate_saving_penalty(save_needed, saving_curve)

                stint_saving_penalties.append((save_needed, target_cons, t_pen_draft, t_pen_green))

            # 7. Simulación Vuelta a Vuelta
            lap_times = []
            fuel_remaining = []
            lap_fuel_consumed = []
            curr_fuel = tank_cap
            pit_info = []  # (pit_lap, pit_time, fuel_loaded, is_sc_gratis)
            total_pit_time = 0.0
            stint_targets = []

            for s_idx, (st_num, start_v, end_v, comp) in enumerate(stints_def):
                save_needed, target_cons, t_pen_draft, t_pen_green = stint_saving_penalties[s_idx]

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
                            t_pen_this = 0.0
                        elif tyre_x == 1:
                            t_deg = 0.0
                            t_pen_this = t_pen_draft if is_draft else t_pen_green
                        else:
                            t_deg = max(0.0, a_val * math.log(tyre_x) + n_val)
                            t_pen_this = t_pen_draft if is_draft else t_pen_green

                        t_green = base_p + t_deg + delta_peso + t_pen_this
                        t_lap = (1.0 - frac) * t_green + frac * sc_pace_full
                        cons_lap = (1.0 - frac) * target_cons + frac * sc_f
                        if (1.0 - frac) >= 0.5:
                            tyre_x += 1
                    elif is_draft:
                        st_draft_count += 1
                        if tyre_x == 0:
                            t_deg = warmup
                            t_pen_this = 0.0  # Vuelta de ruedas frías protegida de penalizaciones de ahorro
                        elif tyre_x == 1:
                            t_deg = 0.0
                            t_pen_this = t_pen_draft
                        else:
                            t_deg = max(0.0, a_val * math.log(tyre_x) + n_val)
                            t_pen_this = t_pen_draft

                        t_lap = base_p + t_deg + delta_peso + t_pen_this
                        cons_lap = target_cons
                        tyre_x += 1
                    else:
                        # VUELTA VERDE PURA (SIN REBUFO):
                        if tyre_x == 0:
                            t_deg = warmup
                            t_pen_this = 0.0  # Vuelta de ruedas frías protegida de penalizaciones de ahorro
                        elif tyre_x == 1:
                            t_deg = 0.0
                            t_pen_this = t_pen_green
                        else:
                            t_deg = max(0.0, a_val * math.log(tyre_x) + n_val)
                            t_pen_this = t_pen_green

                        t_lap = base_p + t_deg + delta_peso + t_pen_this
                        cons_lap = target_cons
                        tyre_x += 1

                    lap_times.append(t_lap)
                    curr_fuel = max(0.0, curr_fuel - cons_lap)
                    fuel_remaining.append(curr_fuel)
                    lap_fuel_consumed.append(cons_lap)"""

if target_2 not in content:
    print("ERROR: target_2 not found!")
    sys.exit(1)
content = content.replace(target_2, replacement_2, 1)

# 3. Update stint mode_str in _simulate_pass
target_3 = """                if save_green > 0.01:
                    mode_parts.append(f"🟡 Ahorro (-{save_green:.2f}L)")"""

replacement_3 = """                if save_needed > 0.005:
                    mode_parts.append(f"🟡 Ahorro (-{save_needed:.2f}L/v)")"""

if target_3 not in content:
    print("ERROR: target_3 not found!")
    sys.exit(1)
content = content.replace(target_3, replacement_3, 1)

# 4. Add post_sc_info calculation in _simulate_strategy
target_4 = """        total_race_time = total_track_time + total_pit_time

        return {
            "total_laps": total_laps,"""

replacement_4 = """        total_race_time = total_track_time + total_pit_time

        # 8. Cálculo de tiempos totales de carrera tras Safety Car (suma de vueltas y paradas tras terminar el SC)
        post_sc_info = []
        if sc_enabled and sc_segments:
            sorted_sc_segs = sorted(
                [s for s in sc_segments if s.get("enabled", True)],
                key=lambda s: int(s.get("lap", 8))
            )
            for idx, s_item in enumerate(sorted_sc_segs):
                s_lap = int(s_item.get("lap", 8))
                s_dur = int(s_item.get("duration", 3))
                s_end = s_lap + s_dur
                restart_lap = s_end + 1

                if restart_lap <= total_laps:
                    track_post = sum(lap_times[v - 1] for v in range(restart_lap, total_laps + 1))
                    pit_post = sum(p[1] for p in pit_info if p[0] >= restart_lap)
                    time_post = track_post + pit_post
                    rem_laps = total_laps - restart_lap + 1
                else:
                    track_post = 0.0
                    pit_post = 0.0
                    time_post = 0.0
                    rem_laps = 0

                post_sc_info.append({
                    "segment_idx": idx + 1,
                    "sc_start_lap": s_lap,
                    "sc_end_lap": s_end,
                    "restart_lap": restart_lap,
                    "rem_laps": rem_laps,
                    "post_sc_time_s": time_post,
                    "post_sc_track_s": track_post,
                    "post_sc_pit_s": pit_post,
                })

        return {
            "total_laps": total_laps,
            "post_sc_info": post_sc_info,"""

if target_4 not in content:
    print("ERROR: target_4 not found!")
    sys.exit(1)
content = content.replace(target_4, replacement_4, 1)

# 5. Update recalculate_and_plot to render _sc_post_time_frame
target_5 = """        if self._mpl_canvas:
            self._mpl_canvas.draw_idle()"""

replacement_5 = """        if self._mpl_canvas:
            self._mpl_canvas.draw_idle()

        # ── 5. Actualizar Apunte de Tiempo Total de Carrera tras Safety Car ──
        post_sc_items = res.get("post_sc_info", [])
        if sc_en and post_sc_items and hasattr(self, "_sc_post_time_frame") and hasattr(self, "_lbl_sc_post_time"):
            lines_sc = []
            for item in post_sc_items:
                seg_i = item["segment_idx"]
                s_start = item["sc_start_lap"]
                s_end = item["sc_end_lap"]
                r_lap = item["restart_lap"]
                rem_l = item["rem_laps"]
                t_s = item["post_sc_time_s"]
                t_str = self._format_seconds_hh_mm_ss(t_s)

                if rem_l > 0:
                    if len(post_sc_items) == 1:
                        line = (
                            f"🟡 TIEMPO TRAS SAFETY CAR (desde V{r_lap} hasta Meta V{tot_laps}, {rem_l}v):  "
                            f"⏱️ {t_str} ({t_s:.1f}s)  │  Suma de vueltas y boxes tras terminar el SC (V{s_start}–V{s_end})"
                        )
                    else:
                        line = (
                            f"🟡 SC TRAMO {seg_i} (V{s_start}–V{s_end}) ➔ TIEMPO TRAS SC (desde V{r_lap} hasta Meta V{tot_laps}, {rem_l}v):  "
                            f"⏱️ {t_str} ({t_s:.1f}s)  │  Suma de vueltas y boxes"
                        )
                else:
                    line = f"🟡 SC TRAMO {seg_i} (V{s_start}–V{s_end}): El SC finaliza en o tras la meta (0 vueltas restantes de carrera verde)."
                lines_sc.append(line)

            self._lbl_sc_post_time.configure(text="\\n".join(lines_sc))
            self._sc_post_time_frame.pack(fill="x", padx=16, pady=(0, 14))
        else:
            if hasattr(self, "_sc_post_time_frame"):
                self._sc_post_time_frame.pack_forget()"""

if target_5 not in content:
    print("ERROR: target_5 not found!")
    sys.exit(1)
content = content.replace(target_5, replacement_5, 1)

target_file.write_text(content, encoding="utf-8")
print("SUCCESS: All 5 updates applied successfully to modules/strategy_charts.py!")
