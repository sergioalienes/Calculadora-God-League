import sys
import unittest
import math
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import customtkinter as ctk
from modules.strategy_charts import StrategyChartsModule
import main

class TestLeaderPitLapsAndModels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ctk.set_appearance_mode("dark")
        cls.root = ctk.CTk()
        cls.root.withdraw()
        cls.colors = main.COLORS.copy()
        cls.module = StrategyChartsModule(cls.root, colors=cls.colors)

        cls.module.session_data = {
            "circuit": "Barcelona",
            "championship_name": "God League",
            "lap_time_seconds": 90.0,
            "race_duration_minutes": 45.0,  # 2700 seconds
            "fuel_capacity_l": 100.0,
            "fuel_per_lap_l": 3.0,
            "safety_margin_l": 2.0,
            "pitlane_loss_s": 30.0,
            "refuel_rate_ls": 10.0,
            "tyre_change_s": 4.0,
            "weight_penalty_s_per_10l": 0.0,
            "mandatory_compound_change": True,
            "tyre_models": {
                "Modelo Base": {
                    "hard_base_lap": 90.0,
                    "hard_warmup": 0.5,
                    "hard_a": 0.20,
                    "hard_n": -0.10,
                    "soft_base_lap": 89.0,
                    "soft_warmup": 0.3,
                    "soft_a": 0.50,
                    "soft_n": -0.30,
                },
                "Modelo Blando Pro": {
                    "hard_base_lap": 90.0,
                    "hard_warmup": 0.5,
                    "hard_a": 0.20,
                    "hard_n": -0.10,
                    "soft_base_lap": 87.0, # significantly faster
                    "soft_warmup": 0.1,
                    "soft_a": 0.10,
                    "soft_n": 0.0,
                }
            },
            "fuel_models": {
                "Consumo Alto": {
                    "fuel_per_lap_l": 3.5,
                }
            }
        }
        cls.module.fuel_data = {
            "viable_modes": ["1 Parada", "2 Paradas"],
            "truncated_laps": 31,
            "draft_rows": []
        }
        cls.module.tyre_data = cls.module.session_data["tyre_models"]["Modelo Base"]

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def test_leader_pit_loss_deduction_in_total_laps(self):
        """
        Verifica que para la estimación de vueltas de la estrategia, se suponga que el usuario
        es el líder y se reste el tiempo perdido en boxes que indican los carteles de parada:
        T_disponible = T_carrera - T_SC - T_boxes_total
        Vueltas = floor(T_disponible / lap_time) + 1 (regla White Flag)
        """
        # Caso 1: 1 Parada (P1 = Vuelta 15)
        # pitlane_loss_s = 30s. Si fuel_to_load = 45L / 10L/s = 4.5s => refuel_t = 4.5s > tyre_change (4.0s)
        # t_box = 30 + 4.5 = 34.5s
        res_1stop = self.module._simulate_strategy(
            num_stops=1, p1=15, p2=0, stint_comps=["hard", "soft"], sc_enabled=False
        )
        total_pit_1 = sum(p[1] for p in res_1stop["pit_info"])
        self.assertAlmostEqual(res_1stop["total_pit_time"], total_pit_1, places=2)
        expected_green_time_1 = 45.0 * 60.0 - total_pit_1
        expected_laps_1 = math.floor(expected_green_time_1 / 90.0) + 1
        self.assertEqual(res_1stop["total_laps"], expected_laps_1)
        self.assertEqual(len(res_1stop["lap_times"]), expected_laps_1)
        self.assertEqual(len(res_1stop["fuel_remaining"]), expected_laps_1)

        # Caso 2: 2 Paradas (P1 = 10, P2 = 20)
        # Total pit loss será la suma de los 2 carteles de parada
        res_2stops = self.module._simulate_strategy(
            num_stops=2, p1=10, p2=20, stint_comps=["hard", "soft", "soft"], sc_enabled=False
        )
        total_pit_2 = sum(p[1] for p in res_2stops["pit_info"])
        self.assertGreater(total_pit_2, 60.0, "Dos paradas deben perder más de 60s en total")
        expected_green_time_2 = 45.0 * 60.0 - total_pit_2
        expected_laps_2 = math.floor(expected_green_time_2 / 90.0) + 1
        self.assertEqual(res_2stops["total_laps"], expected_laps_2)
        self.assertEqual(len(res_2stops["lap_times"]), expected_laps_2)
        self.assertEqual(len(res_2stops["fuel_remaining"]), expected_laps_2)
        print(f"1-stop total pit: {total_pit_1:.1f}s -> {expected_laps_1} laps")
        print(f"2-stop total pit: {total_pit_2:.1f}s -> {expected_laps_2} laps")

    def test_model_names_preserved_and_no_modelo_activo(self):
        """
        Verifica que nunca se asigne la cadena '⚡ Modelo Activo' y que al cargar la óptima
        o refrescar selectores se mantengan los nombres reales de los modelos seleccionados.
        """
        # 1. Verificar comboboxes inicializados o refrescados
        self.module._refresh_models_selectors()
        tyre_vals = self.module._cbo_strat_tyre.cget("values")
        fuel_vals = self.module._cbo_strat_fuel.cget("values")
        
        self.assertNotIn("⚡ Modelo Activo", tyre_vals)
        self.assertNotIn("⚡ Modelo Activo", fuel_vals)
        self.assertIn("Modelo Blando Pro", tyre_vals)

        # 2. Seleccionar 'Modelo Blando Pro'
        self.module._var_strat_tyre_model.set("Modelo Blando Pro")
        self.module._on_strat_tyre_model_changed("Modelo Blando Pro")
        self.assertEqual(self.module._var_strat_tyre_model.get(), "Modelo Blando Pro")

        # 3. Ejecutar 'Cargar Óptima'
        self.module.load_optimal_strategy_action()

        # El selector NO debe haberse reseteado a '⚡ Modelo Activo'
        self.assertEqual(self.module._var_strat_tyre_model.get(), "Modelo Blando Pro")
        self.assertNotEqual(self.module._var_strat_tyre_model.get(), "⚡ Modelo Activo")
        self.assertNotEqual(self.module._var_strat_fuel_model.get(), "⚡ Modelo Activo")

    def test_active_tyre_model_impacts_simulation_pace(self):
        """
        Verifica que al cambiar el modelo de neumáticos, el ritmo de simulación
        utilice efectivamente los parámetros del modelo seleccionado.
        """
        # Simular con Modelo Base (soft base = 89.0)
        self.module._var_strat_tyre_model.set("⭐ Modelo Base")
        self.module._on_strat_tyre_model_changed("⭐ Modelo Base")
        res_base = self.module._simulate_strategy(
            num_stops=1, p1=15, p2=0, stint_comps=["soft", "soft"], sc_enabled=False
        )

        # Simular con Modelo Blando Pro (soft base = 87.0)
        self.module._var_strat_tyre_model.set("Modelo Blando Pro")
        self.module._on_strat_tyre_model_changed("Modelo Blando Pro")
        res_pro = self.module._simulate_strategy(
            num_stops=1, p1=15, p2=0, stint_comps=["soft", "soft"], sc_enabled=False
        )

        # Comprobar que el stint con soft es sustancialmente más rápido con Modelo Blando Pro
        self.assertLess(res_pro["lap_times"][2], res_base["lap_times"][2] - 1.5,
                        "El modelo Pro (87.0s) debe ser mucho más rápido que el Base (89.0s)")

if __name__ == "__main__":
    unittest.main()
