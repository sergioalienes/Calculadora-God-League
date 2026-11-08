import sys
import unittest
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import customtkinter as ctk
from modules.strategy_charts import StrategyChartsModule
import main
import json

class TestDraftTableInterpolationAndSCCoexistence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ctk.set_appearance_mode("dark")
        cls.root = ctk.CTk()
        cls.root.withdraw()
        cls.colors = main.COLORS.copy()
        cls.module = StrategyChartsModule(cls.root, colors=cls.colors)

        cls.module.session_data = {
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
            "mandatory_compound_change": True,
        }

        # Modelo 1 exact data
        cls.module.fuel_data = {
            "viable_modes": ["1 Parada", "2 Paradas"],
            "truncated_laps": 26,
            "fuel_saving_rows": [
                {"label": "+1 Vuelta Extra", "delta_l": -0.05, "delta_s": 0.01},
                {"label": "+2 Vueltas Extra", "delta_l": -0.45, "delta_s": 0.40},
            ],
            "draft_rows": [
                {"label": "Rebufo +1 Vuelta Extra", "delta_l": -0.05, "delta_s": 0.01},
                {"label": "Rebufo +2 Vueltas Extra", "delta_l": -0.45, "delta_s": 0.02},
            ],
            "active_model": "Modelo 1",
        }

        cls.module.tyre_data = {
            "hard_base_lap": "01:44.700",
            "hard_warmup": "1.300",
            "hard_a": "0.2167",
            "hard_n": "0.2599",
            "soft_base_lap": "01:43.700",
            "soft_warmup": "0.500",
            "soft_a": "1.9634",
            "soft_n": "-0.6923",
            "active_model": "Modelo 1",
        }

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def test_draft_rows_curve_and_linear_interpolation(self):
        """
        Verifica que se lea correctamente la curva de rebufo (draft_rows) y que
        se realice la interpolación lineal exacta para puntos no explícitos en la tabla.
        """
        draft_curve = self.module._get_draft_saving_curve()
        self.assertEqual(draft_curve[0], (0.0, 0.0))
        self.assertEqual(draft_curve[1], (0.05, 0.01))
        self.assertEqual(draft_curve[2], (0.45, 0.02))

        # Punto intermedio no escrito: 0.25 L/v (mitad entre 0.05 y 0.45)
        # y = 0.01 + (0.25 - 0.05) / (0.45 - 0.05) * (0.02 - 0.01) = 0.01 + 0.5 * 0.01 = 0.0150s
        pen_025 = self.module._interpolate_saving_penalty(0.25, draft_curve)
        self.assertAlmostEqual(pen_025, 0.0150, places=4)

        # Punto de 0.45 L/v exacto -> 0.02s
        pen_045 = self.module._interpolate_saving_penalty(0.45, draft_curve)
        self.assertAlmostEqual(pen_045, 0.0200, places=4)

        # En la curva normal (fuel_saving_rows), 0.45 L/v pierde 0.40s
        saving_curve = self.module._get_fuel_saving_curve()
        pen_saving_045 = self.module._interpolate_saving_penalty(0.45, saving_curve)
        self.assertAlmostEqual(pen_saving_045, 0.4000, places=4)

    def test_draft_pace_isolated_from_lift_coast_penalty(self):
        """
        Verifica que en un stint que requiere ahorro de combustible, las vueltas de rebufo
        utilicen exclusivamente el delta de tiempo de rebufo (~0.02s) y NO sumen la penalización
        de Lift & Coast de la tabla normal.
        """
        # Stint 1 = 14 vueltas con rebufo en V3-V12 (10 vueltas de rebufo)
        # Requiere ahorrar ~0.43 L/v en total
        res = self.module._simulate_strategy(
            num_stops=1,
            p1=14,
            p2=0,
            stint_comps=["soft", "hard"],
            draft_enabled=True,
            draft_segments=[{"start": 3, "end": 12}],
        )

        st1 = res["stint_targets"][0]
        # El consumo medio del stint debe ajustarse al usable tank (69.6L / 14 = ~4.97 L/v)
        self.assertAlmostEqual(st1["avg_cons"], 4.971, places=2)

        # Tiempo vuelta 5 (en rebufo): debe ser ritmo natural + degradación + peso + delta_rebufo (~0.02s)
        # y NO los +2.2s de penalización excesiva que ocurría antes
        t_lap_5 = res["lap_times"][4]
        self.assertLess(t_lap_5, 107.0, "La vuelta en rebufo no debe sufrir penalizaciones astronómicas de Lift & Coast")

    def test_recalculate_optimal_strategy_and_sc_coexistence(self):
        """
        Verifica que solve_optimal_strategy() calcule la estrategia óptima teniendo en cuenta
        tanto el Safety Car como el Rebufo, y que ambos convivan simultáneamente.
        """
        # 1. Sin modificadores (carrera limpia)
        self.module._var_sc_enabled.set(False)
        self.module._var_draft_enabled.set(False)
        cfg_clean, res_clean = self.module.solve_optimal_strategy()
        self.assertIsNotNone(cfg_clean)

        # 2. Con Rebufo activo
        self.module._var_draft_enabled.set(True)
        self.module.draft_segments = [{"start": ctk.StringVar(value="3"), "end": ctk.StringVar(value="12")}]
        cfg_draft, res_draft = self.module.solve_optimal_strategy()
        self.assertIsNotNone(cfg_draft)

        # 3. Con Safety Car activo
        self.module._var_draft_enabled.set(False)
        self.module._var_sc_enabled.set(True)
        self.module.sc_segments = [{"lap": ctk.StringVar(value="8"), "sector": ctk.StringVar(value="Sector 2"), "duration": ctk.StringVar(value="3"), "fuel_l": ctk.StringVar(value="1.80"), "enabled": True}]
        cfg_sc, res_sc = self.module.solve_optimal_strategy()
        self.assertIsNotNone(cfg_sc)

        # 4. Con AMBOS activos (SC + Rebufo conviviendo)
        self.module._var_draft_enabled.set(True)
        cfg_both, res_both = self.module.solve_optimal_strategy()
        self.assertIsNotNone(cfg_both)
        self.assertIsNotNone(res_both)

        # 5. Detección de oportunidad en banner
        # Caso combinado
        cand_both = self.module._find_best_1stop_opportunity()
        self.assertIsNotNone(cand_both)
        self.assertEqual(cand_both[4], "COMBINADA (SC + REBUFO)")

        # Caso sólo rebufo
        self.module._var_sc_enabled.set(False)
        cand_df = self.module._find_best_1stop_opportunity()
        self.assertIsNotNone(cand_df)
        self.assertEqual(cand_df[4], "REBUFO")

if __name__ == "__main__":
    unittest.main()
