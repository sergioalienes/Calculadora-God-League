with open('modules/strategy_charts.py', 'r', encoding='utf-8') as f:
    content = f.read()

target = '    def get_optimal_strategy_config(self) -> dict | None:'
assert target in content, 'Target not found'

addition = '''    def simulate_strategy_for_config(self, st: dict) -> dict | None:
        """
        Simula una configuracion de estrategia dada (con su modelo de combustible,
        neumaticos, eventos de SC y rebufo/draft), devolviendo el resultado completo
        con fuel_remaining vuelta a vuelta y stint_targets.
        """
        if not st or not self.session_data:
            return None
        try:
            old_f_ov = getattr(self, "_active_fuel_override", None)
            old_t_ov = getattr(self, "_active_tyre_override", None)

            f_model = st.get("fuel_model")
            if f_model and "Modelo Base" not in str(f_model) and "Modelo Activo" not in str(f_model):
                fm_path = self._get_fuel_models_path()
                if fm_path and fm_path.exists():
                    try:
                        import json
                        data = json.loads(fm_path.read_text(encoding="utf-8"))
                        self._active_fuel_override = data.get(f_model)
                    except Exception:
                        pass
                if self._active_fuel_override is None and isinstance(self.session_data.get("fuel_models"), dict):
                    self._active_fuel_override = self.session_data["fuel_models"].get(f_model)
            else:
                self._active_fuel_override = None

            t_model = st.get("tyre_model")
            if t_model and "Modelo Base" not in str(t_model) and "Modelo Activo" not in str(t_model):
                tm_path = self._get_tyre_models_path()
                if tm_path and tm_path.exists():
                    try:
                        import json
                        data = json.loads(tm_path.read_text(encoding="utf-8"))
                        self._active_tyre_override = data.get(t_model)
                    except Exception:
                        pass
            else:
                self._active_tyre_override = None

            raw_stops = st.get("num_stops", 1)
            num_stops = 1 if (raw_stops == 1 or "1" in str(raw_stops)) else 2
            p1 = int(st.get("p1", 15))
            p2 = int(st.get("p2", 0))

            c1 = self._label_to_code(st.get("stint1_comp", "hard"))
            c2 = self._label_to_code(st.get("stint2_comp", "soft"))
            c3 = self._label_to_code(st.get("stint3_comp", "soft"))
            stint_comps = [c1, c2] if num_stops == 1 else [c1, c2, c3]

            sc_en = bool(st.get("sc_enabled", False))
            sc_segs = st.get("sc_segments", [])
            df_en = bool(st.get("draft_enabled", False))
            df_segs = st.get("draft_segments", [])
            df_delta_l = float(st.get("draft_delta_l", -0.25))
            df_delta_s = float(st.get("draft_delta_s", 0.0))

            res = self._simulate_strategy(
                num_stops=num_stops,
                p1=p1,
                p2=p2,
                stint_comps=stint_comps,
                sc_enabled=sc_en,
                sc_segments=sc_segs,
                draft_enabled=df_en,
                draft_segments=df_segs,
                draft_delta_l=df_delta_l,
                draft_delta_s=df_delta_s,
            )

            self._active_fuel_override = old_f_ov
            self._active_tyre_override = old_t_ov
            return res
        except Exception as e:
            return None

'''

content = content.replace(target, addition + target, 1)
with open('modules/strategy_charts.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Successfully added simulate_strategy_for_config to strategy_charts.py')
