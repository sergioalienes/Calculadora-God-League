from pathlib import Path

target = Path(r"E:\Calculadora God League\modules\strategy_charts.py")
content = target.read_text(encoding="utf-8")

# Marker before section 5
marker_before = "        # 4. Normalizar códigos de compuestos de stints\n        c1_code = self._label_to_code(stint_comps[0])\n        c2_code = self._label_to_code(stint_comps[1] if len(stint_comps) > 1 else \"soft\")\n        c3_code = self._label_to_code(stint_comps[2] if len(stint_comps) > 2 else \"soft\")\n"

# Marker at the end of stints loop
marker_after = "        total_track_time = sum(lap_times)\n        total_race_time = total_track_time + total_pit_time\n"

idx_before = content.find(marker_before)
if idx_before == -1:
    # Try with CRLF
    marker_before = marker_before.replace("\n", "\r\n")
    idx_before = content.find(marker_before)
    marker_after = marker_after.replace("\n", "\r\n")
    crlf = True
else:
    crlf = False

assert idx_before != -1, "Marker before not found"
split_pt1 = idx_before + len(marker_before)
idx_after = content.find(marker_after, split_pt1)
assert idx_after != -1, "Marker after not found"

stints_code = content[split_pt1:idx_after]

# Indent stints_code by 4 spaces
lines = stints_code.splitlines(keepends=True)
indented_lines = ["    " + line if line.strip() else line for line in lines]
indented_stints_code = "".join(indented_lines)

nl = "\r\n" if crlf else "\n"

new_block = (
    f"        # 5. Bucle de convergencia de pasadas para restar la pérdida exacta en boxes del líder{nl}"
    f"        usable_tank = max(1.0, tank_cap - safety_l){nl}"
    f"        saving_curve = self._get_fuel_saving_curve(){nl}"
    f"{nl}"
    f"        def _simulate_pass(target_laps: int):{nl}"
    f"{indented_stints_code.replace('total_laps', 'target_laps')}"
    f"            return stints_def, stint_targets, lap_times, fuel_remaining, lap_fuel_consumed, curr_fuel, pit_info, total_pit_time, p1_eff, p2_eff, pit_laps{nl}"
    f"{nl}"
    f"        # Pasada 1: con estimación preliminar de vueltas{nl}"
    f"        (stints_def, stint_targets, lap_times, fuel_remaining, lap_fuel_consumed,{nl}"
    f"         curr_fuel, pit_info, total_pit_time, p1_eff, p2_eff, pit_laps) = _simulate_pass(total_laps){nl}"
    f"{nl}"
    f"        # Recálculo exacto de vueltas del líder restando el tiempo total en boxes (tiempo de carteles){nl}"
    f"        green_time_exact = max(0.0, total_race_time_s - time_sc - total_pit_time){nl}"
    f"        exact_green_laps = math.floor(green_time_exact / max(1.0, base_lap_s)) + 1{nl}"
    f"        converged_total_laps = (len(sc_laps_set) if (sc_enabled and sc_laps_set) else 0) + exact_green_laps{nl}"
    f"        min_laps_required = (max(pit_laps) + 1) if pit_laps else 1{nl}"
    f"        converged_total_laps = max(min_laps_required, converged_total_laps){nl}"
    f"{nl}"
    f"        # Pasada 2: si las vueltas del líder cambiaron al descontar el tiempo de boxes, re-simular con converged_total_laps{nl}"
    f"        if converged_total_laps != total_laps:{nl}"
    f"            total_laps = converged_total_laps{nl}"
    f"            (stints_def, stint_targets, lap_times, fuel_remaining, lap_fuel_consumed,{nl}"
    f"             curr_fuel, pit_info, total_pit_time, p1_eff, p2_eff, pit_laps) = _simulate_pass(total_laps){nl}"
    f"{nl}"
)

new_content = content[:split_pt1] + new_block + content[idx_after:]
target.write_text(new_content, encoding="utf-8")
print("Successfully updated strategy_charts.py with 2-pass convergence!")
