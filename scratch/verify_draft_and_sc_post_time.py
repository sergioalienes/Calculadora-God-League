import sys
from pathlib import Path
root_dir = Path(".").resolve()
sys.path.insert(0, str(root_dir))
import json
import customtkinter as ctk
import main
from modules.strategy_charts import StrategyChartsModule

ctk.set_appearance_mode("dark")
root = ctk.CTk()
root.withdraw()

mod = StrategyChartsModule(root, colors=main.COLORS.copy())
mod.session_data = {
    "circuit": "Road America",
    "championship_name": "God League",
    "lap_time_seconds": 105.0,
    "race_duration_minutes": 45.0,
    "fuel_capacity_l": 70.0,
    "fuel_per_lap_l": 5.4,
    "safety_margin_l": 0.4,
    "pitlane_loss_s": 29.0,
    "refuel_rate_ls": 12.0,
    "tyre_change_s": 4.0,
    "weight_penalty_s_per_10l": 0.02,
}
mod.fuel_data = json.loads(Path("profiles/God League/Road America_fuel.json").read_text(encoding="utf-8"))
mod.tyre_data = json.loads(Path("profiles/God League/Road America_tyres.json").read_text(encoding="utf-8"))
mod._refresh_models_selectors()
mod._on_strat_fuel_model_changed("Modelo 1", trigger_plot=False)
mod._on_strat_tyre_model_changed("Modelo 1", trigger_plot=False)

print("=" * 60)
print("TEST 1: 2-STOP STRATEGY (V1-V10 DRAFT)")
print("=" * 60)
r_no = mod._simulate_strategy(num_stops=2, p1=10, p2=18, stint_comps=["soft", "hard", "hard"], draft_enabled=False)
r_df = mod._simulate_strategy(num_stops=2, p1=10, p2=18, stint_comps=["soft", "hard", "hard"], draft_enabled=True, draft_segments=[{"start": 1, "end": 10}])

print(f"Sin rebufo V01 (Soft cold): {r_no['lap_times'][0]:.3f}s")
print(f"Con rebufo V01 (Soft cold): {r_df['lap_times'][0]:.3f}s (delta: {r_df['lap_times'][0] - r_no['lap_times'][0]:+.3f}s)")
print(f"Sin rebufo V02:             {r_no['lap_times'][1]:.3f}s")
print(f"Con rebufo V02:             {r_df['lap_times'][1]:.3f}s (delta: {r_df['lap_times'][1] - r_no['lap_times'][1]:+.3f}s)")

# Check Stint 1 target consumption
st1_no = r_no["stint_targets"][0]
st1_df = r_df["stint_targets"][0]
print(f"Stint 1 avg_cons sin rebufo: {st1_no['avg_cons']:.2f} L/v")
print(f"Stint 1 avg_cons con rebufo: {st1_df['avg_cons']:.2f} L/v")

assert abs(r_df['lap_times'][0] - r_no['lap_times'][0]) < 1e-4, "Cold tyre lap should not have draft penalty when excess==0!"
assert abs(st1_df['avg_cons'] - 5.40) < 1e-4, "Stint 1 should not ask to save fuel when excess==0!"
assert "Ahorro" not in st1_df['mode_str'], "Mode str should not say Ahorro when excess==0!"
print(">>> TEST 1 PASSED!")

print("\n" + "=" * 60)
print("TEST 2: 2-STOP STRATEGY (V5-V15 DRAFT, COVERS V11 OUT-LAP)")
print("=" * 60)
r_df_15 = mod._simulate_strategy(num_stops=2, p1=10, p2=18, stint_comps=["soft", "hard", "hard"], draft_enabled=True, draft_segments=[{"start": 5, "end": 15}])
print(f"Sin rebufo V11 (Hard out-lap): {r_no['lap_times'][10]:.3f}s")
print(f"Con rebufo V11 (Hard out-lap): {r_df_15['lap_times'][10]:.3f}s (delta: {r_df_15['lap_times'][10] - r_no['lap_times'][10]:+.3f}s)")
assert abs(r_df_15['lap_times'][10] - r_no['lap_times'][10]) < 1e-4, "Out-lap V11 should not have draft penalty when excess==0!"
print(">>> TEST 2 PASSED!")

print("\n" + "=" * 60)
print("TEST 3: 1-STOP STRATEGY (DEFICIT EXISTS, V1-V5 DRAFT)")
print("=" * 60)
r_1s_no = mod._simulate_strategy(num_stops=1, p1=13, p2=0, stint_comps=["soft", "hard"], draft_enabled=False)
r_1s_df = mod._simulate_strategy(num_stops=1, p1=13, p2=0, stint_comps=["soft", "hard"], draft_enabled=True, draft_segments=[{"start": 1, "end": 5}])
print(f"Stint 1 (13 laps) con rebufo V1-V5:")
print(f"  Target cons: {r_1s_df['stint_targets'][0]['avg_cons']:.3f} L/v (Base 5.40)")
print(f"  V01 [Rueda Fria]: {r_1s_df['lap_times'][0]:.3f}s (Sin rebufo: {r_1s_no['lap_times'][0]:.3f}s)")
print(f"  V02 [Rebufo]:     {r_1s_df['lap_times'][1]:.3f}s (Sin rebufo: {r_1s_no['lap_times'][1]:.3f}s)")
print(f"  V06 [Limpio]:     {r_1s_df['lap_times'][5]:.3f}s (Sin rebufo: {r_1s_no['lap_times'][5]:.3f}s)")
assert abs(r_1s_df['lap_times'][0] - r_1s_no['lap_times'][0]) < 1e-4, "Cold tyre lap V01 protected from saving penalty!"
print(">>> TEST 3 PASSED!")

print("\n" + "=" * 60)
print("TEST 4: SAFETY CAR POST-SC TOTAL RACE TIME CALCULATION")
print("=" * 60)
r_sc1 = mod._simulate_strategy(
    num_stops=2, p1=10, p2=18, stint_comps=["soft", "hard", "hard"],
    sc_enabled=True, sc_segments=[{"lap": 2, "sector": "Sector 1", "duration": 3, "fuel_l": 1.80}]
)
print("Single SC Segment post_sc_info:")
for item in r_sc1.get("post_sc_info", []):
    print(f"  SC: V{item['sc_start_lap']}-V{item['sc_end_lap']} -> Restart V{item['restart_lap']}")
    print(f"  Remaining laps: {item['rem_laps']}")
    print(f"  Track time post-SC: {item['post_sc_track_s']:.3f}s")
    print(f"  Pit time post-SC:   {item['post_sc_pit_s']:.3f}s")
    print(f"  Total time post-SC: {item['post_sc_time_s']:.3f}s")

# Verify manual sum from V6 to 26
restart_v = 6
man_track = sum(r_sc1["lap_times"][v - 1] for v in range(restart_v, r_sc1["total_laps"] + 1))
man_pit = sum(p[1] for p in r_sc1["pit_info"] if p[0] >= restart_v)
assert abs(r_sc1["post_sc_info"][0]["post_sc_track_s"] - man_track) < 1e-4
assert abs(r_sc1["post_sc_info"][0]["post_sc_pit_s"] - man_pit) < 1e-4
assert abs(r_sc1["post_sc_info"][0]["post_sc_time_s"] - (man_track + man_pit)) < 1e-4
print(">>> TEST 4 SINGLE SC PASSED!")

print("\n" + "=" * 60)
print("TEST 5: MULTIPLE SC SEGMENTS POST-SC TIME (CONSECUTIVE)")
print("=" * 60)
r_sc2 = mod._simulate_strategy(
    num_stops=2, p1=10, p2=18, stint_comps=["soft", "hard", "hard"],
    sc_enabled=True, sc_segments=[
        {"lap": 2, "sector": "Sector 1", "duration": 3, "fuel_l": 1.80},
        {"lap": 12, "sector": "Sector 1", "duration": 2, "fuel_l": 1.80},
    ]
)
assert len(r_sc2.get("post_sc_info", [])) == 2
for item in r_sc2.get("post_sc_info", []):
    print(f"  Tramo SC {item['segment_idx']}: V{item['sc_start_lap']}-V{item['sc_end_lap']} -> Restart V{item['restart_lap']} ({item['rem_laps']}v)")
    print(f"    Total tras SC: {item['post_sc_time_s']:.3f}s")
print(">>> TEST 5 MULTIPLE SC PASSED!")

print("\n" + "=" * 60)
print("TEST 6: UI RENDERING OF POST-SC HUD APUNTE")
print("=" * 60)
mod._var_sc_enabled.set(True)
mod.recalculate_and_plot()
assert mod._sc_post_time_frame.winfo_manager() == 'pack', "_sc_post_time_frame should be packed when SC enabled!"
text_shown = repr(mod._lbl_sc_post_time.cget("text"))
print("Rendered HUD Text:\n" + text_shown)
assert "TIEMPO" in text_shown and "SAFETY CAR" in text_shown

mod._var_sc_enabled.set(False)
mod.recalculate_and_plot()
assert mod._sc_post_time_frame.winfo_manager() == '', "_sc_post_time_frame should be hidden when SC disabled!"
print(">>> TEST 6 UI RENDERING PASSED!")

print("\nALL 6 VERIFICATION TESTS COMPLETED SUCCESSFULLY!")
