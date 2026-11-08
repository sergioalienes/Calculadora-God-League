import sys
from pathlib import Path

target_file = Path("modules/strategy_charts.py")
content = target_file.read_text(encoding="utf-8")

crlf_mode = "\r\n" in content
if crlf_mode:
    content = content.replace("\r\n", "\n")

# 1. Post SC info calculation (lines ~1838)
t1 = """                if restart_lap <= total_laps:
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
                })"""

r1 = """                if restart_lap <= total_laps:
                    track_post = sum(lap_times[v - 1] for v in range(restart_lap, total_laps + 1))
                    # Incluir paradas tras el SC o en la vuelta de fin de SC si no fueron gratis (perdieron tiempo de box)
                    post_pits = [
                        p for p in pit_info
                        if (p[0] >= restart_lap or (p[0] >= s_end and not (p[3] if len(p) > 3 else False)))
                    ]
                    pit_post = sum(p[1] for p in post_pits)
                    time_post = track_post + pit_post
                    rem_laps = total_laps - restart_lap + 1
                    n_pits_post = len(post_pits)
                else:
                    track_post = 0.0
                    pit_post = 0.0
                    time_post = 0.0
                    rem_laps = 0
                    n_pits_post = 0

                post_sc_info.append({
                    "segment_idx": idx + 1,
                    "sc_start_lap": s_lap,
                    "sc_end_lap": s_end,
                    "restart_lap": restart_lap,
                    "rem_laps": rem_laps,
                    "post_sc_time_s": time_post,
                    "post_sc_track_s": track_post,
                    "post_sc_pit_s": pit_post,
                    "n_pits_post": n_pits_post,
                })"""

assert t1 in content, "t1 not found"
content = content.replace(t1, r1, 1)
print("Step 1 ok")

# 2. solve_optimal_strategy init
t2 = """        best_cfg = None
        best_res = None
        min_time = float("inf")"""

r2 = """        best_cfg = None
        best_res = None
        best_score = (0, float("inf"))"""

assert t2 in content, "t2 not found"
content = content.replace(t2, r2, 1)
print("Step 2 ok")

# 3. 1-stop in solve_optimal_strategy
t3 = """                    if res["total_race_time"] < min_time:
                        min_time = res["total_race_time"]
                        best_res = res
                        best_cfg = {
                            "num_stops": 1,
                            "p1": p1,
                            "p2": 0,
                            "stint1_comp": c1,
                            "stint2_comp": c2,
                            "stint3_comp": "soft",
                        }"""

r3 = """                    score = (-res["total_laps"], res["total_race_time"])
                    if score < best_score:
                        best_score = score
                        best_res = res
                        best_cfg = {
                            "num_stops": 1,
                            "p1": p1,
                            "p2": 0,
                            "stint1_comp": c1,
                            "stint2_comp": c2,
                            "stint3_comp": "soft",
                        }"""

assert t3 in content, "t3 not found"
content = content.replace(t3, r3, 1)
print("Step 3 ok")

# 4. 2-stop in solve_optimal_strategy
t4 = """                        if res["total_race_time"] < min_time:
                            min_time = res["total_race_time"]
                            best_res = res
                            best_cfg = {
                                "num_stops": 2,
                                "p1": p1,
                                "p2": p2,
                                "stint1_comp": c1,
                                "stint2_comp": c2,
                                "stint3_comp": c3,
                            }"""

r4 = """                        score = (-res["total_laps"], res["total_race_time"])
                        if score < best_score:
                            best_score = score
                            best_res = res
                            best_cfg = {
                                "num_stops": 2,
                                "p1": p1,
                                "p2": p2,
                                "stint1_comp": c1,
                                "stint2_comp": c2,
                                "stint3_comp": c3,
                            }"""

assert t4 in content, "t4 not found"
content = content.replace(t4, r4, 1)
print("Step 4 ok")

# 5. _find_best_1stop_opportunity init
t5 = """        best_p = None
        best_c1 = None
        best_c2 = None
        best_res = None
        best_time = float("inf")

        for p in range(1, tot_laps):"""

r5 = """        best_p = None
        best_c1 = None
        best_c2 = None
        best_res = None
        best_score = (0, float("inf"))

        for p in range(1, tot_laps + 1):"""

assert t5 in content, "t5 not found"
content = content.replace(t5, r5, 1)
print("Step 5 ok")

# 6. _find_best_1stop_opportunity inner loop
t6 = """                if res1["total_race_time"] < best_time:
                    best_time = res1["total_race_time"]
                    best_p = p
                    best_c1 = c1
                    best_c2 = c2
                    best_res = res1"""

r6 = """                score1 = (-res1["total_laps"], res1["total_race_time"])
                if score1 < best_score:
                    best_score = score1
                    best_p = p
                    best_c1 = c1
                    best_c2 = c2
                    best_res = res1"""

assert t6 in content, "t6 not found"
content = content.replace(t6, r6, 1)
print("Step 6 ok")

# 7. _find_best_1stop_opportunity return assignment
t7 = """        if best_p is not None:
            has_sc = bool(sc_en and sc_segs)"""

r7 = """        if best_p is not None:
            best_time = best_res["total_race_time"]
            has_sc = bool(sc_en and sc_segs)"""

assert t7 in content, "t7 not found"
content = content.replace(t7, r7, 1)
print("Step 7 ok")

# 8. _check_stop_saving_opportunity
t8_a = '            curr_time = self.current_result.get("total_race_time", best_time)'
r8_a = '            curr_time = self.current_result.get("total_race_time", best_time)\n            cand_laps = cand_res.get("total_laps", tot_laps) if cand_res else tot_laps'
assert t8_a in content, "t8_a not found"
content = content.replace(t8_a, r8_a, 1)

t8_b = """            time_diff = curr_time - best_time
            gain_str = f" \xa1Ganancia estimada: -{time_diff:.1f}s!" if time_diff > 0.05 else \"\""""
if t8_b not in content:
    t8_b = """            time_diff = curr_time - best_time
            gain_str = f" ¡Ganancia estimada: -{time_diff:.1f}s!" if time_diff > 0.05 else \"\""""

r8_b = """            if cand_laps > tot_laps:
                gain_str = f" ¡Permite completar +{cand_laps - tot_laps} vuelta(s) de carrera (Líder en vuelta sin doblar)!"
            else:
                time_diff = curr_time - best_time
                gain_str = f" ¡Ganancia estimada: -{time_diff:.1f}s!" if time_diff > 0.05 else \"\""""
assert t8_b in content, "t8_b not found"
content = content.replace(t8_b, r8_b, 1)

t8_c = 'Es viable completar las {tot_laps} vueltas con 1 SOLA PARADA'
r8_c = 'Es viable completar las {cand_laps} vueltas con 1 SOLA PARADA'
assert t8_c in content, "t8_c not found"
content = content.replace(t8_c, r8_c, 1)
print("Step 8 ok")

# 9. KPI Delta Optima
t9 = """        if self.optimal_result:
            opt_time = self.optimal_result["total_race_time"]
            delta_opt = tot_time_s - opt_time
            if abs(delta_opt) < 0.05:
                self._lbl_kpi_delta_opt.configure(text="0.000s (ÓPTIMA)", text_color=self.colors["success"])
            elif delta_opt > 0:
                self._lbl_kpi_delta_opt.configure(text=f"+{delta_opt:.3f}s", text_color="#FFA94D")
            else:
                self._lbl_kpi_delta_opt.configure(text=f"{delta_opt:.3f}s (SUPERIOR)", text_color=self.colors["success"])
        else:
            self._lbl_kpi_delta_opt.configure(text="—")"""

r9 = """        if self.optimal_result:
            opt_time = self.optimal_result["total_race_time"]
            opt_laps = self.optimal_result.get("total_laps", tot_laps)
            delta_laps = tot_laps - opt_laps

            if delta_laps > 0:
                self._lbl_kpi_delta_opt.configure(
                    text=f"+{delta_laps}v (SUPERIOR)",
                    text_color=self.colors["success"]
                )
            elif delta_laps < 0:
                self._lbl_kpi_delta_opt.configure(
                    text=f"{delta_laps}v (DOBLADO)",
                    text_color=self.colors["danger"]
                )
            else:
                delta_opt = tot_time_s - opt_time
                if abs(delta_opt) < 0.05:
                    self._lbl_kpi_delta_opt.configure(text="0.000s (ÓPTIMA)", text_color=self.colors["success"])
                elif delta_opt > 0:
                    self._lbl_kpi_delta_opt.configure(text=f"+{delta_opt:.3f}s", text_color="#FFA94D")
                else:
                    self._lbl_kpi_delta_opt.configure(text=f"{delta_opt:.3f}s (SUPERIOR)", text_color=self.colors["success"])
        else:
            self._lbl_kpi_delta_opt.configure(text="—")"""

assert t9 in content, "t9 not found"
content = content.replace(t9, r9, 1)
print("Step 9 ok")

# 10. Post SC HUD text
t10 = """            for item in post_sc_items:
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
                lines_sc.append(line)"""

r10 = """            for item in post_sc_items:
                seg_i = item["segment_idx"]
                s_start = item["sc_start_lap"]
                s_end = item["sc_end_lap"]
                r_lap = item["restart_lap"]
                rem_l = item["rem_laps"]
                t_s = item["post_sc_time_s"]
                t_track = item.get("post_sc_track_s", t_s)
                t_pit = item.get("post_sc_pit_s", 0.0)
                n_pits = item.get("n_pits_post", 0)
                t_str = self._format_seconds_hh_mm_ss(t_s)

                if t_pit > 0.05:
                    pit_desc = f" + Boxes: {t_pit:.1f}s ({n_pits} parada{'s' if n_pits != 1 else ''} tras SC)"
                else:
                    pit_desc = " │ Boxes tras SC: 0.0s (Sin paradas o gratis en SC)"

                if rem_l > 0:
                    if len(post_sc_items) == 1:
                        line = (
                            f"🟡 TIEMPO TRAS SAFETY CAR (desde V{r_lap} hasta Meta V{tot_laps}, {rem_l}v):  "
                            f"⏱️ {t_str} ({t_s:.1f}s)  │  Pista: {t_track:.1f}s{pit_desc}"
                        )
                    else:
                        line = (
                            f"🟡 SC TRAMO {seg_i} (V{s_start}–V{s_end}) ➔ TIEMPO TRAS SC (desde V{r_lap} hasta Meta V{tot_laps}, {rem_l}v):  "
                            f"⏱️ {t_str} ({t_s:.1f}s)  │  Pista: {t_track:.1f}s{pit_desc}"
                        )
                else:
                    line = f"🟡 SC TRAMO {seg_i} (V{s_start}–V{s_end}): El SC finaliza en o tras la meta (0 vueltas restantes de carrera verde)."
                lines_sc.append(line)"""

assert t10 in content, "t10 not found"
content = content.replace(t10, r10, 1)
print("Step 10 ok")

if crlf_mode:
    content = content.replace("\n", "\r\n")

target_file.write_text(content, encoding="utf-8")
print("SUCCESS: All modifications written successfully!")
