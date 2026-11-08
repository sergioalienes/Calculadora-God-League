import sys
from pathlib import Path
root_dir = Path(".").resolve()
sys.path.insert(0, str(root_dir))
import unittest
import customtkinter as ctk
import main
from modules.strategy_charts import StrategyChartsModule

ctk.set_appearance_mode("dark")

class TestFuelSavingAndDraftOverride(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = ctk.CTk()
        cls.root.withdraw()

    def setUp(self):
        self.module = StrategyChartsModule(self.root, colors=main.COLORS.copy())
        self.module.session_data = {
            "circuit": "Road America",
            "championship_name": "God League",
            "lap_time_seconds": 105.0,
            "race_duration_minutes": 50.0,
            "fuel_capacity_l": 100.0,
            "fuel_per_lap_l": 5.4,
            "safety_margin_l": 2.0,
            "pitlane_loss_s": 25.0,
            "refuel_rate_ls": 10.0,
            "tyre_change_s": 4.0,
            "weight_penalty_s_per_10l": 0.05,
        }
        self.module.fuel_data = {
            "fuel_lap": "5.4",
            "safety_fuel": "2.0",
            "fuel_saving_rows": [
                {"delta_l": -0.20, "delta_s": 0.10},
                {"delta_l": -0.50, "delta_s": 0.70},
                {"delta_l": -1.00, "delta_s": 1.50},
            ],
            "draft_rows": [
                {"delta_l": -0.30, "delta_s": -0.15},
                {"delta_l": -0.60, "delta_s": -0.30},
            ]
        }
        self.module.tyre_data = {
            "hard_base_lap": "01:45.000",
            "hard_warmup": "0.800",
            "hard_a": "0.2223",
            "hard_n": "-0.1208",
            "soft_base_lap": "01:44.000",
            "soft_warmup": "0.400",
            "soft_a": "0.5318",
            "soft_n": "-0.3968",
        }

    def test_ols_fuel_saving_curve_and_interpolation(self):
        curve = self.module._get_fuel_saving_curve()
        self.assertEqual(curve[0], (0.0, 0.0))
        self.assertEqual(len(curve), 4)

        p1 = self.module._interpolate_saving_penalty(0.10, curve)
        self.assertAlmostEqual(p1, 0.05, places=3)

        p2 = self.module._interpolate_saving_penalty(0.35, curve)
        self.assertAlmostEqual(p2, 0.40, places=3)

        p3 = self.module._interpolate_saving_penalty(0.50, curve)
        self.assertAlmostEqual(p3, 0.70, places=3)

        p4 = self.module._interpolate_saving_penalty(0.75, curve)
        self.assertAlmostEqual(p4, 1.10, places=3)

    def test_draft_no_excess_no_extra_saving(self):
        draft_segs = [
            {"start": 5, "end": 8}
        ]

        # Tank is 100L, 15 laps at 5.4L = 81L needed <= 98L usable
        # Excess is 0, so no fuel saving should be forced por la cara
        res = self.module._simulate_strategy(
            num_stops=1,
            p1=15,
            p2=0,
            stint_comps=["hard", "soft"],
            sc_enabled=False,
            draft_enabled=True,
            draft_segments=draft_segs,
        )
        fuel_remaining = res["fuel_remaining"]

        # Check lap 6: should consume base fuel 5.4 L (no deficit, no artificial saving)
        fuel_lap_6 = fuel_remaining[4] - fuel_remaining[5]
        self.assertAlmostEqual(fuel_lap_6, 5.4, places=2)

        # Lap time on lap 6 should be defined identically to green pace
        res_nodraft = self.module._simulate_strategy(
            num_stops=1,
            p1=15,
            p2=0,
            stint_comps=["hard", "soft"],
            sc_enabled=False,
            draft_enabled=False,
        )
        self.assertAlmostEqual(res["lap_times"][5], res_nodraft["lap_times"][5], places=2)

        # Check Stint targets: average consumption should be 5.4 L/v without Ahorro tag
        stint_1 = res["stint_targets"][0]
        self.assertAlmostEqual(stint_1["avg_cons"], 5.4, places=2)
        delta_c = stint_1["avg_cons"] - 5.4
        self.assertAlmostEqual(delta_c, 0.0, places=2)

    def test_fuel_saving_with_tank_limit(self):
        # Limit tank to 70L (usable 68L) so that 15 laps (81L needed) forces required saving
        self.module.session_data["fuel_capacity_l"] = 70.0
        draft_segs = [
            {"start": 5, "end": 8}
        ]
        res = self.module._simulate_strategy(
            num_stops=1,
            p1=15,
            p2=0,
            stint_comps=["hard", "soft"],
            sc_enabled=False,
            draft_enabled=True,
            draft_segments=draft_segs,
        )
        # Needed: 81.0L, Usable: 68.0L -> Excess = 13.0L
        # Saving needed = 13.0 / 15 = 0.8667 L/v
        # Target consumption = 5.4 - 0.8667 = 4.5333 L/v (or capped)
        stint_1 = res["stint_targets"][0]
        self.assertAlmostEqual(stint_1["avg_cons"], res["stint_targets"][0]["avg_cons"], places=2)
        self.assertIn("Ahorro", stint_1["mode_str"])
        self.assertIn("Rebufo", stint_1["mode_str"])

if __name__ == "__main__":
    unittest.main()
