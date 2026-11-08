import sys
from pathlib import Path

# Simulate scenario
# Session params
tank_cap = 70.0
safety_l = 2.5
base_cons = 5.65
tot_laps = 20

# Active strategy: 1 stop at lap 15
p1 = 15
p2 = 0
num_stops = 1

# Telemetry entries:
# Stint 1: Lap 5: 41.75 L, Lap 10: 13.5 L, Lap 15: 8.0 L
# At Lap 15: Stop, load fuel up to e.g. 30.75 L (needed for 5 laps: 5*5.65 + 2.5 = 30.75 L)
# Stint 2 (last stint):
# Lap 16: car has 25.1 L. (30.75 - 5.65 = 25.1 L).
meta_records = [
    {"lap": 5, "fuel": 41.75, "cons": 5.65},
    {"lap": 10, "fuel": 13.5, "cons": 5.65},
    {"lap": 15, "fuel": 8.0, "cons": 5.65},
    {"lap": 16, "fuel": 25.1, "cons": 0.0},
]

# Old logic:
curr_lap = 16
curr_fuel = 25.1
if curr_lap <= p1:
    st_start_lap_old = 0
    st_start_fuel_old = tank_cap
    st_idx_old = 0
else:
    st_start_lap_old = p1
    st_start_fuel_old = tank_cap  # BUG!
    st_idx_old = 1

st_entries_old = [r for r in meta_records if r["lap"] > st_start_lap_old]
st_laps_old = curr_lap - st_start_lap_old
obs_cons_old = max(0.1, (st_start_fuel_old - curr_fuel) / max(1, st_laps_old))
plan_fuel_lap_old = max(0.0, st_start_fuel_old - (st_laps_old * base_cons))
delta_f_old = curr_fuel - plan_fuel_lap_old

print("--- OLD LOGIC ---")
print(f"curr_fuel: {curr_fuel}")
print(f"obs_cons: {obs_cons_old:.2f} L/v")
print(f"plan_fuel_lap: {plan_fuel_lap_old:.2f} L")
print(f"delta_f: {delta_f_old:.2f} L")

# New logic:
if curr_lap <= p1:
    st_idx_new = 0
    st_start_lap_new = 0
    is_last_stint_new = False
    laps_to_target_new = max(0, p1 - curr_lap)
else:
    st_idx_new = 1
    st_start_lap_new = p1
    is_last_stint_new = True
    laps_to_target_new = max(0, tot_laps - curr_lap)

# obs_cons
st_entries_new = [r for r in meta_records if r["lap"] > st_start_lap_new]
if len(st_entries_new) >= 2:
    obs_cons_new = (st_entries_new[0]["fuel"] - st_entries_new[-1]["fuel"]) / (st_entries_new[-1]["lap"] - st_entries_new[0]["lap"])
else:
    valid_past = [r["cons"] for r in meta_records if r.get("cons", 0) > 0.1 and r["lap"] <= st_start_lap_new]
    obs_cons_new = sum(valid_past) / len(valid_past) if valid_past else base_cons

if is_last_stint_new:
    laps_to_meta = max(0, tot_laps - curr_lap)
    fuel_needed = (laps_to_meta * base_cons) + safety_l
    delta_f_new = curr_fuel - fuel_needed
else:
    fuel_needed = (laps_to_target_new * base_cons) + safety_l
    delta_f_new = curr_fuel - fuel_needed

print("\n--- NEW LOGIC ---")
print(f"curr_fuel: {curr_fuel}")
print(f"obs_cons: {obs_cons_new:.2f} L/v")
print(f"fuel_needed to finish: {fuel_needed:.2f} L")
print(f"delta_f: {delta_f_new:.2f} L")
