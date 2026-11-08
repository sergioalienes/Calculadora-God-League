import math

def solve_tactical_test(
    curr_lap: int,
    curr_fuel: float,
    tot_laps: int,
    initial_tyre_lap: int = 0,
    curr_comp: str = "hard",
    base_lap_s: float = 84.5,
    tank_cap: float = 70.0,
    cons_base: float = 5.65,
    safety_l: float = 2.5,
    weight_sens: float = 0.015,
    refuel_rate: float = 12.0,
    tyre_change_s: float = 4.0,
    pitlane_loss_s: float = 22.5,
    sc_active: bool = False,
    sc_sector: str = "Sector 1",
    sc_dur: int = 3,
    mandatory_change: bool = True,
):
    h_base = base_lap_s
    h_warm = 0.800
    h_a = 0.2223
    h_n = -0.1208

    s_base = base_lap_s - 0.450
    s_warm = 0.400
    s_a = 0.5318
    s_n = -0.3968

    usable_tank = max(1.0, tank_cap - safety_l)
    max_stint_save = math.floor(usable_tank / (cons_base * 0.80))
    rem_laps = tot_laps - curr_lap

    # Safety Car parameters
    # The car is at finish line of curr_lap. Incident happens on next lap (curr_lap + 1)
    sc_dep_lap = curr_lap + 1
    sec_num = 1 if "1" in sc_sector else (2 if "2" in sc_sector else 3)
    frac_dep = 1.0 if sec_num == 1 else (2.0 / 3.0 if sec_num == 2 else 1.0 / 3.0)
    sc_end = sc_dep_lap + sc_dur  # Laps sc_dep_lap .. sc_end

    def get_lap_fuel_and_sc(v: int) -> tuple[float, bool, bool, bool]:
        """Returns (fuel_cons, is_sc_neutralized, is_sc_deployment, is_sc_restart)."""
        if not sc_active or v < sc_dep_lap or v > sc_end:
            return cons_base, False, False, False
        if v == sc_dep_lap:
            f = (1.0 - frac_dep) * cons_base + frac_dep * 1.80
            return f, True, True, False
        if v == sc_end:
            return 1.80, True, False, True
        return 1.80, True, False, False

    def calc_lap_time(comp: str, tyre_age: int, fuel_l: float, is_sc_neutralized: bool, is_sc_dep: bool = False) -> float:
        if is_sc_neutralized:
            sc_pace = base_lap_s * 1.40
            if is_sc_dep:
                return (1.0 - frac_dep) * base_lap_s + frac_dep * sc_pace
            return sc_pace

        if comp == "hard":
            base_p = h_base
            if tyre_age == 0:
                deg = h_warm
            elif tyre_age == 1:
                deg = 0.0
            else:
                deg = max(0.0, h_a * math.log(tyre_age) + h_n)
        else:
            base_p = s_base
            if tyre_age == 0:
                deg = s_warm
            elif tyre_age == 1:
                deg = 0.0
            else:
                deg = max(0.0, s_a * math.log(tyre_age) + s_n)

        delta_peso = min(0.0, (fuel_l - tank_cap) * weight_sens)
        return base_p + deg + delta_peso

    best_time = float("inf")
    best_plan = None

    # Earliest pit stop must strictly be at least curr_lap + 1
    p_min_1stop = max(curr_lap + 1, tot_laps - max_stint_save)
    p_max_1stop = tot_laps - 1

    comp_options = ["hard", "soft"]

    # 1. Evaluate 1-Stop Strategies
    for p_cand in range(p_min_1stop, p_max_1stop + 1):
        st2_len = tot_laps - p_cand
        if st2_len > max_stint_save:
            continue

        # Check fuel to reach p_cand
        f_needed_st1 = 0.0
        for v in range(curr_lap + 1, p_cand + 1):
            c_l, _, _, _ = get_lap_fuel_and_sc(v)
            f_needed_st1 += c_l

        if (curr_fuel - safety_l) < (f_needed_st1 * 0.80):
            continue  # Not enough fuel even with max 20% saving

        for next_comp in comp_options:
            if mandatory_change and curr_comp == next_comp:
                continue

            # Simulate Stint 1 from curr_lap + 1 to p_cand
            t_acc = 0.0
            f_sim = curr_fuel
            t_age = curr_lap + initial_tyre_lap

            for v in range(curr_lap + 1, p_cand + 1):
                c_l, is_sc, is_dep, is_rst = get_lap_fuel_and_sc(v)
                t_acc += calc_lap_time(curr_comp, t_age, f_sim, is_sc, is_dep)
                f_sim = max(0.0, f_sim - c_l)
                t_age += 1

            # Pit stop at p_cand
            f_entry = f_sim
            # Fuel needed for Stint 2
            f_needed_st2 = 0.0
            for v in range(p_cand + 1, tot_laps + 1):
                c_l, _, _, _ = get_lap_fuel_and_sc(v)
                f_needed_st2 += c_l
            f_needed_st2 += safety_l

            fuel_to_load = min(tank_cap - f_entry, max(0.0, f_needed_st2 - f_entry))
            refuel_t = fuel_to_load / refuel_rate
            normal_t_box = pitlane_loss_s + max(refuel_t, tyre_change_s)

            # SC Pit rules
            is_sc_free = False
            if sc_active and (sc_dep_lap < p_cand < sc_end):
                t_box = 0.0  # Free stop during full neutralisation
                is_sc_free = True
            elif sc_active and p_cand == sc_dep_lap:
                t_box = normal_t_box + 30.0  # Illegal stop: pit lane closed
            else:
                t_box = normal_t_box

            t_acc += t_box

            # Simulate Stint 2 from p_cand + 1 to tot_laps
            f_sim = f_entry + fuel_to_load
            t_age2 = 0
            for v in range(p_cand + 1, tot_laps + 1):
                c_l, is_sc, is_dep, is_rst = get_lap_fuel_and_sc(v)
                t_acc += calc_lap_time(next_comp, t_age2, f_sim, is_sc, is_dep)
                f_sim = max(0.0, f_sim - c_l)
                t_age2 += 1

            if t_acc < best_time:
                best_time = t_acc
                best_plan = {
                    "num_stops": 1,
                    "p1": p_cand,
                    "p2": 0,
                    "stint1_comp": curr_comp,
                    "stint2_comp": next_comp,
                    "stint3_comp": "soft",
                    "fuel_to_load": fuel_to_load,
                    "next_comp_label": "Prime (Duro)" if next_comp == "hard" else "Alternative (Blando)",
                    "is_sc_free": is_sc_free,
                    "total_rem_time": t_acc,
                }

    # 2. Evaluate 2-Stop Strategies if 1-stop is impossible or if 2-stop might be faster
    p1_min_2stop = curr_lap + 1
    p1_max_2stop = tot_laps - 2

    for p1_cand in range(p1_min_2stop, p1_max_2stop + 1):
        f_needed_st1 = 0.0
        for v in range(curr_lap + 1, p1_cand + 1):
            c_l, _, _, _ = get_lap_fuel_and_sc(v)
            f_needed_st1 += c_l
        if (curr_fuel - safety_l) < (f_needed_st1 * 0.80):
            continue

        p2_min = p1_cand + 1
        p2_max = min(p1_cand + max_stint_save, tot_laps - 1)

        for p2_cand in range(p2_min, p2_max + 1):
            st3_len = tot_laps - p2_cand
            if st3_len > max_stint_save:
                continue

            for c_next in comp_options:
                for c_final in comp_options:
                    if mandatory_change and len({curr_comp, c_next, c_final}) < 2:
                        continue

                    # Simulate Stint 1
                    t_acc = 0.0
                    f_sim = curr_fuel
                    t_age = curr_lap + initial_tyre_lap
                    for v in range(curr_lap + 1, p1_cand + 1):
                        c_l, is_sc, is_dep, is_rst = get_lap_fuel_and_sc(v)
                        t_acc += calc_lap_time(curr_comp, t_age, f_sim, is_sc, is_dep)
                        f_sim = max(0.0, f_sim - c_l)
                        t_age += 1

                    # Pit 1
                    f_entry1 = f_sim
                    f_needed_st2 = 0.0
                    for v in range(p1_cand + 1, p2_cand + 1):
                        c_l, _, _, _ = get_lap_fuel_and_sc(v)
                        f_needed_st2 += c_l
                    f_needed_st2 += safety_l
                    fuel_to_load1 = min(tank_cap - f_entry1, max(0.0, f_needed_st2 - f_entry1))
                    refuel_t1 = fuel_to_load1 / refuel_rate
                    normal_t_box1 = pitlane_loss_s + max(refuel_t1, tyre_change_s)
                    is_sc_free1 = False
                    if sc_active and (sc_dep_lap < p1_cand < sc_end):
                        t_box1 = 0.0
                        is_sc_free1 = True
                    elif sc_active and p1_cand == sc_dep_lap:
                        t_box1 = normal_t_box1 + 30.0
                    else:
                        t_box1 = normal_t_box1
                    t_acc += t_box1

                    # Stint 2
                    f_sim = f_entry1 + fuel_to_load1
                    t_age2 = 0
                    for v in range(p1_cand + 1, p2_cand + 1):
                        c_l, is_sc, is_dep, is_rst = get_lap_fuel_and_sc(v)
                        t_acc += calc_lap_time(c_next, t_age2, f_sim, is_sc, is_dep)
                        f_sim = max(0.0, f_sim - c_l)
                        t_age2 += 1

                    # Pit 2
                    f_entry2 = f_sim
                    f_needed_st3 = 0.0
                    for v in range(p2_cand + 1, tot_laps + 1):
                        c_l, _, _, _ = get_lap_fuel_and_sc(v)
                        f_needed_st3 += c_l
                    f_needed_st3 += safety_l
                    fuel_to_load2 = min(tank_cap - f_entry2, max(0.0, f_needed_st3 - f_entry2))
                    refuel_t2 = fuel_to_load2 / refuel_rate
                    normal_t_box2 = pitlane_loss_s + max(refuel_t2, tyre_change_s)
                    is_sc_free2 = False
                    if sc_active and (sc_dep_lap < p2_cand < sc_end):
                        t_box2 = 0.0
                        is_sc_free2 = True
                    elif sc_active and p2_cand == sc_dep_lap:
                        t_box2 = normal_t_box2 + 30.0
                    else:
                        t_box2 = normal_t_box2
                    t_acc += t_box2

                    # Stint 3
                    f_sim = f_entry2 + fuel_to_load2
                    t_age3 = 0
                    for v in range(p2_cand + 1, tot_laps + 1):
                        c_l, is_sc, is_dep, is_rst = get_lap_fuel_and_sc(v)
                        t_acc += calc_lap_time(c_final, t_age3, f_sim, is_sc, is_dep)
                        f_sim = max(0.0, f_sim - c_l)
                        t_age3 += 1

                    if t_acc < best_time:
                        best_time = t_acc
                        best_plan = {
                            "num_stops": 2,
                            "p1": p1_cand,
                            "p2": p2_cand,
                            "stint1_comp": curr_comp,
                            "stint2_comp": c_next,
                            "stint3_comp": c_final,
                            "fuel_to_load": fuel_to_load1,
                            "next_comp_label": "Prime (Duro)" if c_next == "hard" else "Alternative (Blando)",
                            "is_sc_free": is_sc_free1,
                            "total_rem_time": t_acc,
                        }

    return best_plan


if __name__ == "__main__":
    print("Test 1: curr_lap=5, curr_fuel=42.0, tot_laps=28, starting hard")
    p = solve_tactical_test(curr_lap=5, curr_fuel=42.0, tot_laps=28, curr_comp="hard")
    print("Result:", p)
    assert p["p1"] >= 6, f"p1 ({p['p1']}) must be >= 6"
    print("Test 1 passed! Suggested pit:", p["p1"], "Comp:", p["next_comp_label"])

    print("\nTest 2: curr_lap=10, curr_fuel=20.0, tot_laps=28 (low fuel, needs 2 stops)")
    p2 = solve_tactical_test(curr_lap=10, curr_fuel=20.0, tot_laps=28, curr_comp="hard")
    print("Result:", p2)
    assert p2["p1"] >= 11
    print("Test 2 passed! Suggested:", p2["num_stops"], "stops, pit 1:", p2["p1"])

    print("\nTest 3: curr_lap=10, curr_fuel=25.0, tot_laps=28 with SC at lap 11 (Sector 2)")
    p3 = solve_tactical_test(curr_lap=10, curr_fuel=25.0, tot_laps=28, curr_comp="hard", sc_active=True, sc_sector="Sector 2", sc_dur=3)
    print("Result:", p3)
    print("Test 3 passed! Pit 1:", p3["p1"], "is_sc_free:", p3["is_sc_free"])
