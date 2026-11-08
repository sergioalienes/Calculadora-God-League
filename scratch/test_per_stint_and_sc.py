import sys
import unittest
from pathlib import Path

# Ensure root directory is in sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import customtkinter as ctk
from modules.strategy_charts import StrategyChartsModule


class TestPerStintAndSCRules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ctk.set_appearance_mode("dark")
        cls.root = ctk.CTk()
        cls.root.withdraw()
        colors = {
            "bg_primary": "#0A0A0A",
            "bg_secondary": "#131313",
            "accent": "#F26419",
            "accent_dim": "#3A1A08",
            "text_primary": "#FFFFFF",
            "text_secondary": "#8E8E93",
            "border": "#2C2C2E",
            "success": "#30D158",
            "warning": "#FFD60A",
            "danger": "#FF453A",
        }
        cls.module = StrategyChartsModule(cls.root, colors=colors)
        cls.module.session_data = {
            "lap_time_seconds": 85.0,
            "race_duration_minutes": 45.0,
            "fuel_capacity_l": 70.0,
            "fuel_per_lap_l": 5.65,
            "safety_margin_l": 3.0,
            "pitlane_loss_s": 22.0,
            "refuel_rate_ls": 12.0,
            "tyre_change_s": 4.0,
            "weight_penalty_s_per_10l": 0.150,
            "mandatory_compound_change": True,
        }
        cls.module.fuel_data = {
            "viable_modes": ["1 Parada", "2 Paradas"],
            "truncated_laps": 31,
        }
        cls.module.tyre_data = {
            "hard_base_lap": 85.0,
            "hard_warmup": 0.8,
            "hard_a": 0.22,
            "hard_n": -0.12,
            "soft_base_lap": 84.5,
            "soft_warmup": 0.4,
            "soft_a": 0.53,
            "soft_n": -0.40,
        }

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def test_sc_fractions_math(self):
        """Verifica que el cálculo de fracciones de Safety Car refleje correctamente la vuelta de salida y vueltas tras meta."""
        self.module._var_sc_enabled.set(True)
        self.module.sc_segments[0]["lap"].set("8")
        self.module.sc_segments[0]["sector"].set("Sector 2")
        self.module.sc_segments[0]["duration"].set("2")
        self.module.sc_segments[0]["fuel_l"].set("1.80")

        sc_segs = self.module._get_active_sc_segments()
        self.assertEqual(len(sc_segs), 1)
        self.assertEqual(sc_segs[0]["lap"], 8)
        self.assertEqual(sc_segs[0]["sector"], "Sector 2")
        self.assertEqual(sc_segs[0]["duration"], 2)

        res = self.module._simulate_strategy(
            num_stops=1,
            p1=15,
            p2=0,
            stint_comps=["hard", "soft"],
            sc_enabled=True,
            sc_segments=sc_segs,
        )
        self.assertIsNotNone(res)
        sc_fracs = res["sc_fractions"]
        self.assertIn(8, sc_fracs)
        self.assertIn(9, sc_fracs)
        self.assertIn(10, sc_fracs)
        self.assertNotIn(11, sc_fracs)

        self.assertAlmostEqual(sc_fracs[8], 2.0 / 3.0, places=3)
        self.assertAlmostEqual(sc_fracs[9], 1.0, places=3)
        self.assertAlmostEqual(sc_fracs[10], 1.0, places=3)

        total_sc_distance = sum(sc_fracs.values())
        self.assertAlmostEqual(total_sc_distance, 2.0 + 2.0 / 3.0, places=3)
        print(f"Total SC Distance (S2, 2 laps): {total_sc_distance:.3f} laps (Confirmed 2.667 laps)")

    def test_user_exact_sc_scenario_v12_s2_duration2(self):
        """
        Prueba el caso exacto planteado por el usuario:
        SC en V12 Sector 2 con duración de 2 vueltas.
        - Vuelta 12: Pit CERRADO (sanción Stop&Go de 30s, no es gratis).
        - Vuelta 13: Pit ABIERTO neutralizado tras meta (PARADA GRATIS, t_box = 0s).
        - Vuelta 14: Final de SC, relanzamiento ("pelotón sale escopetado", PARADA NO GRATIS).
        - Verifica que en todos los casos se informe los litros exactos a poner.
        """
        sc_segs = [{"enabled": True, "lap": 12, "sector": "Sector 2", "duration": 2, "fuel_l": 1.80}]

        # 1. Parar al final de V12 (Vuelta de despliegue de SC)
        res_v12 = self.module._simulate_strategy(
            num_stops=1,
            p1=12,
            p2=0,
            stint_comps=["hard", "soft"],
            sc_enabled=True,
            sc_segments=sc_segs,
        )
        pit_lap_12, t_box_12, fuel_12, gratis_12, closed_12, end_12 = res_v12["pit_info"][0]
        self.assertEqual(pit_lap_12, 12)
        self.assertTrue(closed_12, "V12 must be marked as PIT CERRADO!")
        self.assertFalse(gratis_12, "V12 pit must NOT be gratis!")
        self.assertGreater(t_box_12, 50.0, "V12 must include pitlane + Stop&Go penalty (+30s)!")
        self.assertGreater(fuel_12, 0.0, "V12 must calculate fuel to load!")

        # 2. Parar al final de V13 (Primera vuelta tras cruzar meta, neutralizada)
        res_v13 = self.module._simulate_strategy(
            num_stops=1,
            p1=13,
            p2=0,
            stint_comps=["hard", "soft"],
            sc_enabled=True,
            sc_segments=sc_segs,
        )
        pit_lap_13, t_box_13, fuel_13, gratis_13, closed_13, end_13 = res_v13["pit_info"][0]
        self.assertEqual(pit_lap_13, 13)
        self.assertFalse(closed_13, "V13 pit lane is OPEN!")
        self.assertFalse(end_13, "V13 is intermediate, not ending/restart!")
        self.assertTrue(gratis_13, "V13 pit stop MUST be GRATIS under SC!")
        self.assertEqual(t_box_13, 0.0, "V13 pit time MUST be 0.0s!")
        self.assertGreater(fuel_13, 0.0, "V13 must calculate fuel to load!")

        # 3. Parar al final de V14 (Última vuelta de SC, el SC entra a boxes y el pelotón relanza)
        res_v14 = self.module._simulate_strategy(
            num_stops=1,
            p1=14,
            p2=0,
            stint_comps=["hard", "soft"],
            sc_enabled=True,
            sc_segments=sc_segs,
        )
        pit_lap_14, t_box_14, fuel_14, gratis_14, closed_14, end_14 = res_v14["pit_info"][0]
        self.assertEqual(pit_lap_14, 14)
        self.assertFalse(closed_14, "V14 pit lane is open!")
        self.assertTrue(end_14, "V14 MUST be marked as SC ending / restart lap!")
        self.assertFalse(gratis_14, "V14 pit stop MUST NOT be gratis because pack restarts escopetado!")
        self.assertGreater(t_box_14, 0.0, "V14 pit time must be normal positive pit time!")
        self.assertGreater(fuel_14, 0.0, "V14 must calculate fuel to load!")

        print(f"V12 Pit: Closed={closed_12}, Gratis={gratis_12}, Time={t_box_12:.1f}s, Fuel={fuel_12:.1f}L")
        print(f"V13 Pit: Closed={closed_13}, Gratis={gratis_13}, Time={t_box_13:.1f}s, Fuel={fuel_13:.1f}L")
        print(f"V14 Pit: Ending={end_14}, Gratis={gratis_14}, Time={t_box_14:.1f}s, Fuel={fuel_14:.1f}L")

        # 4. Verificar que el detector de oportunidad de 1 parada jamás sugiera parar en V12 (pit cerrado)
        self.module._var_sc_enabled.set(True)
        self.module.sc_segments[0]["lap"].set("12")
        self.module.sc_segments[0]["sector"].set("Sector 2")
        self.module.sc_segments[0]["duration"].set("2")
        self.module.sc_segments[0]["fuel_l"].set("1.80")
        self.module.current_result = res_v13

        cand = self.module._find_best_1stop_opportunity()
        if cand:
            best_p = cand[0]
            self.assertNotEqual(best_p, 12, "Opportunity detector must NEVER recommend pitting on closed deployment lap V12!")
            print(f"1-Stop Opportunity detector recommended Lap: V{best_p} (NOT V12!)")

    def test_per_stint_forced_compounds_optimizer(self):
        """Verifica que el optimizador respete el forzado de compuesto en cualquier stint."""
        self.module._var_forced_s1.set("Duro")
        self.module._var_forced_s2.set("Blando")
        self.module._var_forced_s3.set("Auto")

        opt_cfg, opt_res = self.module.solve_optimal_strategy()
        self.assertIsNotNone(opt_cfg)
        self.assertEqual(opt_cfg["stint1_comp"], "hard")
        self.assertEqual(opt_cfg["stint2_comp"], "soft")

        self.module._var_forced_s1.set("Auto")
        self.module._var_forced_s2.set("Duro")
        self.module._var_forced_s3.set("Blando")
        opt_cfg3, opt_res3 = self.module.solve_optimal_strategy()
        self.assertIsNotNone(opt_cfg3)
        self.assertEqual(opt_cfg3["num_stops"], 2)
        self.assertEqual(opt_cfg3["stint2_comp"], "hard")
        self.assertEqual(opt_cfg3["stint3_comp"], "soft")

    def test_stint_consumption_ignores_sc(self):
        """Verifica que el consumo medio del stint mostrado se calcule ÚNICAMENTE para las vueltas verdes (sin SC)."""
        sc_segs = [{"enabled": True, "lap": 6, "sector": "Sector 2", "duration": 2, "fuel_l": 1.80}]
        res = self.module._simulate_strategy(
            num_stops=1,
            p1=10,
            p2=0,
            stint_comps=["hard", "soft"],
            sc_enabled=True,
            sc_segments=sc_segs,
        )
        st1 = res["stint_targets"][0]
        cons_base = self.module._get_base_consumption()  # 5.65 L/v

        # Stint 1 tiene 10 vueltas: V1..V5 verdes, V6..V8 SC (V6 en S2 es 2/3 SC), V9..V10 verdes.
        # Las vueltas puramente verdes son V1..V5 y V9..V10 (7 vueltas).
        # El consumo mostrado avg_cons DEBE ser 5.65 L/v (Δ 0.00 L/v), NO diluido por el SC (~4.43 L/v).
        self.assertAlmostEqual(st1["avg_cons"], cons_base, places=2)
        self.assertGreater(st1["total_avg_cons"], 0.0)
        self.assertLess(st1["total_avg_cons"], cons_base)  # total_avg_cons sí está diluido

        # sc_count debe ser fraccional: 2/3 (V6) + 1 (V7) + 1 (V8) = 2.67 vueltas
        self.assertAlmostEqual(st1["sc_count"], 2.0 + 2.0 / 3.0, places=2)
        self.assertIn("2.67v", st1["mode_str"])
        safe_mode = st1["mode_str"].encode("ascii", errors="replace").decode("ascii")
        print(f"Stint 1 Green Consumption: {st1['avg_cons']:.2f} L/v (Base: {cons_base:.2f}), SC Count: {st1['sc_count']:.2f}v, Mode: {safe_mode}")

    def test_v0_deployment_pace_and_fuel_by_sector(self):
        """Verifica que en la vuelta V0 sólo se aplique ritmo y consumo de SC en los sectores afectados (S1, S2, S3)."""
        track_len_km = float(self.module.session_data.get("track_length_km", 5.47))
        sc_speed_kmh = float(self.module.session_data.get("sc_speed_kmh", 72.0))
        sc_pace_full = float(self.module.session_data.get("sc_pace_s") or ((track_len_km / max(1.0, sc_speed_kmh)) * 3600.0))
        cons_base = 5.65
        sc_fuel = 1.80

        # Caso Sector 1: toda la vuelta bajo SC (frac = 1.0)
        sc_s1 = [{"enabled": True, "lap": 5, "sector": "Sector 1", "duration": 1, "fuel_l": sc_fuel}]
        res_s1 = self.module._simulate_strategy(num_stops=1, p1=10, p2=0, stint_comps=["hard", "soft"], sc_enabled=True, sc_segments=sc_s1)
        self.assertAlmostEqual(res_s1["lap_times"][4], sc_pace_full, delta=0.5)
        self.assertAlmostEqual(res_s1["lap_fuel_consumed"][4], sc_fuel, places=2)

        # Caso Sector 2: 1/3 verde + 2/3 SC (frac = 2/3)
        sc_s2 = [{"enabled": True, "lap": 5, "sector": "Sector 2", "duration": 1, "fuel_l": sc_fuel}]
        res_s2 = self.module._simulate_strategy(num_stops=1, p1=10, p2=0, stint_comps=["hard", "soft"], sc_enabled=True, sc_segments=sc_s2)
        expected_s2_fuel = (1.0 / 3.0) * cons_base + (2.0 / 3.0) * sc_fuel
        self.assertAlmostEqual(res_s2["lap_fuel_consumed"][4], expected_s2_fuel, places=2)
        # Ritmo V0: 1/3 ritmo verde + 2/3 ritmo SC
        t_green_v0 = res_s2["lap_times"][3]  # vuelta 4 como referencia verde
        expected_s2_pace = (1.0 / 3.0) * t_green_v0 + (2.0 / 3.0) * sc_pace_full
        self.assertAlmostEqual(res_s2["lap_times"][4], expected_s2_pace, delta=1.0)

        # Caso Sector 3: 2/3 verde + 1/3 SC (frac = 1/3)
        sc_s3 = [{"enabled": True, "lap": 5, "sector": "Sector 3", "duration": 1, "fuel_l": sc_fuel}]
        res_s3 = self.module._simulate_strategy(num_stops=1, p1=10, p2=0, stint_comps=["hard", "soft"], sc_enabled=True, sc_segments=sc_s3)
        expected_s3_fuel = (2.0 / 3.0) * cons_base + (1.0 / 3.0) * sc_fuel
        self.assertAlmostEqual(res_s3["lap_fuel_consumed"][4], expected_s3_fuel, places=2)
        expected_s3_pace = (2.0 / 3.0) * t_green_v0 + (1.0 / 3.0) * sc_pace_full
        self.assertAlmostEqual(res_s3["lap_times"][4], expected_s3_pace, delta=1.0)

        print(f"V0 Sector 1: Pace={res_s1['lap_times'][4]:.1f}s, Fuel={res_s1['lap_fuel_consumed'][4]:.2f}L")
        print(f"V0 Sector 2: Pace={res_s2['lap_times'][4]:.1f}s, Fuel={res_s2['lap_fuel_consumed'][4]:.2f}L")
        print(f"V0 Sector 3: Pace={res_s3['lap_times'][4]:.1f}s, Fuel={res_s3['lap_fuel_consumed'][4]:.2f}L")


if __name__ == "__main__":
    unittest.main()

