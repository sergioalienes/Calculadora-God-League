import sys
from pathlib import Path
root_dir = Path(".").resolve()
sys.path.insert(0, str(root_dir))
import unittest
import customtkinter as ctk
import main
from modules.strategy_charts import StrategyChartsModule

ctk.set_appearance_mode("dark")

class TestDraftFuelSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = ctk.CTk()
        cls.root.withdraw()

        cls.colors = main.COLORS.copy()
        cls.module = StrategyChartsModule(cls.root, colors=cls.colors)

        cls.module.session_data = {
            "circuit": "Barcelona",
            "championship_name": "God League",
            "lap_time_seconds": 90.0,
            "race_duration_minutes": 45.0,
            "fuel_capacity_l": 100.0,
            "fuel_per_lap_l": 3.0,
            "safety_margin_l": 2.0,
            "pitlane_loss_s": 20.0,
            "refuel_rate_ls": 10.0,
            "tyre_change_s": 4.0,
            "weight_penalty_s_per_10l": 0.150,
            "mandatory_compound_change": True,
        }
        cls.module.fuel_data = {
            "viable_modes": ["1 Parada", "2 Paradas"],
            "truncated_laps": 30,
            "draft_rows": [
                {"label": "Rebufo", "delta_l": -0.40, "delta_s": -0.20}
            ]
        }
        cls.module.tyre_data = {
            "hard_base_lap": 90.0,
            "hard_warmup": 0.5,
            "hard_a": 0.20,
            "hard_n": -0.10,
            "soft_base_lap": 89.0,
            "soft_warmup": 0.3,
            "soft_a": 0.50,
            "soft_n": -0.30,
        }

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def test_get_draft_saving_l_fallback(self):
        # When fuel_data has draft_rows
        saving_l = self.module._get_draft_saving_l()
        self.assertAlmostEqual(saving_l, -0.40, places=2)

        # When fuel_data is empty and file doesn't exist, fallback is -0.20 * cons_base = -0.60
        self.module.fuel_data = {}
        fallback_l = self.module._get_draft_saving_l()
        self.assertAlmostEqual(fallback_l, -0.20 * 3.0, places=2)

    def test_pace_defined_identically_to_normal_green_laps(self):
        # Reset fuel data
        self.module.fuel_data = {
            "viable_modes": ["1 Parada", "2 Paradas"],
            "truncated_laps": 30,
            "draft_rows": [
                {"label": "Rebufo", "delta_l": -0.40, "delta_s": -0.20}
            ]
        }
        self.module.session_data["fuel_capacity_l"] = 100.0

        # Simulate with draft on laps 6..9 (4 laps)
        res_draft = self.module._simulate_strategy(
            num_stops=1,
            p1=15,
            p2=0,
            stint_comps=["hard", "soft"],
            sc_enabled=False,
            draft_enabled=True,
            draft_segments=[{"start": 6, "end": 9}],
        )

        # Simulate without draft
        res_nodraft = self.module._simulate_strategy(
            num_stops=1,
            p1=15,
            p2=0,
            stint_comps=["hard", "soft"],
            sc_enabled=False,
            draft_enabled=False,
        )

        # When excess == 0, pace on lap 6 with draft matches green pace exactly
        self.assertAlmostEqual(
            res_draft["lap_times"][5],
            res_nodraft["lap_times"][5],
            places=5,
            msg="Pace on lap 6 with draft must match green pace without draft"
        )

        # Fuel consumption on lap 6 should be base fuel 3.0L when excess==0
        cons_lap_6_draft = res_draft["fuel_remaining"][4] - res_draft["fuel_remaining"][5]
        cons_lap_6_nodraft = res_nodraft["fuel_remaining"][4] - res_nodraft["fuel_remaining"][5]
        self.assertAlmostEqual(cons_lap_6_draft, cons_lap_6_nodraft, places=2)

    def test_draft_saving_when_excess_exists(self):
        # Set tank capacity to 40L (usable 38L). Stint 1 needs 15 * 3.0 = 45L.
        # Excess = 7.0L. Saving needed = 7.0 / 15 = 0.4667 L/v (capped at 20% = 0.60 L/v)
        self.module.session_data["fuel_capacity_l"] = 40.0
        res_draft = self.module._simulate_strategy(
            num_stops=1,
            p1=15,
            p2=0,
            stint_comps=["hard", "soft"],
            sc_enabled=False,
            draft_enabled=True,
            draft_segments=[{"start": 6, "end": 9}],
        )
        stint_1 = res_draft["stint_targets"][0]
        self.assertAlmostEqual(stint_1["avg_cons"], 3.0 - (7.0 / 15.0), places=2)
        self.assertIn("Ahorro", stint_1["mode_str"])
        self.assertIn("Rebufo", stint_1["mode_str"])

    def test_serialization_and_deserialization(self):
        self.module.draft_segments = [
            {"enabled": ctk.BooleanVar(value=True), "start": ctk.StringVar(value="8"), "end": ctk.StringVar(value="14")}
        ]
        serialized_segs = [
            {
                "enabled": seg["enabled"].get(),
                "start": int(seg["start"].get()),
                "end": int(seg["end"].get()),
            }
            for seg in self.module.draft_segments
        ]
        self.assertEqual(len(serialized_segs), 1)
        self.assertEqual(serialized_segs[0], {"enabled": True, "start": 8, "end": 14})

if __name__ == "__main__":
    unittest.main()
