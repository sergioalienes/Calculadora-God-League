"""
================================================================================
 MÓDULO 4: Comparador y Optimizador Global de Estrategias (Team NIX Esports)
 Suite Universal de Estrategia de Carrera — iRacing
 Archivo: modules/strategy_charts.py
================================================================================
 Funcionalidades:
   - Solucionador analítico de Estrategia Óptima (mínimo tiempo total, ahorro <= 20%).
   - Normalización estricta de compuestos (Prime Duro vs Alternative Blando).
   - Lectura del consumo base real desde el Módulo 2 / _fuel.json.
   - Ventana visualizadora e interactiva con sliders desacoplados y compuestos por stint.
   - Desglose de consumo medio objetivo por vuelta en cada stint (PUSH/SAVE/HOLGADO SC).
   - Indicador en la gráfica del consumo y Delta L/v bajo cada stint.
   - Evento Safety Car: vuelta, sector (1,2,3), duración, consumo manual L/v,
     acortamiento de vueltas de carrera (White Flag) y parada GRATIS bajo SC.
   - Detector dinámico y recálculo óptimo de 1 Parada bajo Safety Car.
   - Gráfico dual Matplotlib:
     * Subplot 1: Ritmo vuelta a vuelta en escala natural (SC en franja amarilla
       rayada con hatch="//" sin desescalar Y) + Meta explícita.
     * Cuadrícula de vueltas individual (líneas discontinuas sutiles cada vuelta, más gruesa cada 5).
     * Leyenda con texto blanco legible.
     * Subplot 2: Timeline strip de barras horizontales (Amarillo SC, Naranja Rebufo).
   - Persistencia completa en profiles/<campeonato>/<circuito>_strategies.json.
================================================================================
"""

import json
import math
import re
import sys
import warnings
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.ticker import FuncFormatter

# Suprimir advertencias de glifos no disponibles en fuentes de matplotlib (ej. DejaVu Sans)
warnings.filterwarnings("ignore", message=r".*missing from font.*")

APP_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
PROFILES_ROOT = APP_ROOT / "profiles"


class StrategyChartsModule(ctk.CTkFrame):
    """Módulo 4 — Comparador y Optimizador Global de Estrategias."""

    @staticmethod
    def _code_to_label(code: str) -> str:
        """Convierte código interno ('hard'/'soft') a etiqueta de UI."""
        return "Prime (Duro)" if str(code).lower() in ("hard", "prime", "duro") else "Alternative (Blando)"

    @staticmethod
    def _label_to_code(label: str) -> str:
        """Convierte cualquier etiqueta o texto a código interno ('hard'/'soft')."""
        txt = str(label).lower()
        if "duro" in txt or "prime" in txt or txt == "hard":
            return "hard"
        return "soft"

    def __init__(self, parent, colors: dict, **kwargs):
        super().__init__(parent, fg_color=colors.get("bg_primary", "#0A0A0A"), **kwargs)
        self.colors = colors.copy()
        if "danger" not in self.colors:
            self.colors["danger"] = "#FF453A"
        if "warning" not in self.colors:
            self.colors["warning"] = "#FFD60A"

        # Contratos de datos entre módulos
        self.session_data: dict = {}
        self.fuel_data: dict = {}
        self.tyre_data: dict = {}

        # Estado de optimización y estrategia base
        self.optimal_config: dict | None = None
        self.optimal_result: dict | None = None
        self.current_result: dict | None = None
        self.saved_strategies: dict = {}
        self._opportunity_1stop_candidate: tuple | None = None
        self._inspected_lap: int | None = None

        # ── Variables Reactivas de Estrategia ─────────────────
        self._var_num_stops = ctk.StringVar(value="1 Parada")
        self._var_forced_s1 = ctk.StringVar(value="Auto")
        self._var_forced_s2 = ctk.StringVar(value="Auto")
        self._var_forced_s3 = ctk.StringVar(value="Auto")
        self._var_forced_start_comp = self._var_forced_s1  # Alias retrocompatibilidad
        self._var_p1 = ctk.IntVar(value=12)
        self._var_p2 = ctk.IntVar(value=24)
        self._var_stint1_comp = ctk.StringVar(value="Prime (Duro)")
        self._var_stint2_comp = ctk.StringVar(value="Alternative (Blando)")
        self._var_stint3_comp = ctk.StringVar(value="Prime (Duro)")
        self._var_selected_strategy = ctk.StringVar(value="⚡ Estrategia Óptima")

        # ── Modelos de combustible y neumáticos vinculados ────
        self._var_strat_fuel_model = ctk.StringVar(value="⭐ Modelo Base")
        self._var_strat_tyre_model = ctk.StringVar(value="⭐ Modelo Base")
        self._active_fuel_override: dict | None = None
        self._active_tyre_override: dict | None = None

        # ── Variables de Eventos Tácticos Multi-Tramo (SC & Rebufo) ───
        self._var_sc_enabled = ctk.BooleanVar(value=False)
        self.sc_segments: list[dict] = [
            {
                "lap": ctk.StringVar(value="8"),
                "sector": ctk.StringVar(value="Sector 2"),
                "duration": ctk.StringVar(value="3"),
                "fuel_l": ctk.StringVar(value="1.80"),
            }
        ]

        self._var_draft_enabled = ctk.BooleanVar(value=False)
        self.draft_segments: list[dict] = [
            {
                "start": ctk.StringVar(value="5"),
                "end": ctk.StringVar(value="15"),
            }
        ]

        # Flags internos para evitar bucles de actualización
        self._is_updating = False
        self._plot_job = None
        self._s2_slider_bounds = None
        self._mpl_canvas = None

        self._build_ui()

    # ═══════════════════════════════════════════════════════════
    #  LECTURA ROBUSTA DE PARÁMETROS REALES DE COMBUSTIBLE
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _parse_time_str(text: str, default: float) -> float:
        if not text:
            return default
        try:
            s = str(text).strip()
            if ":" in s:
                parts = s.split(":")
                return float(parts[0]) * 60.0 + float(parts[1].replace(",", "."))
            return float(s.replace(",", "."))
        except Exception:
            return default

    def _get_base_consumption(self) -> float:
        """Obtiene el consumo base configurado por el usuario en el Módulo 2 (Combustible)."""
        # 0. Intentar desde modelo de combustible forzado/vinculado
        if self._active_fuel_override:
            c = self._active_fuel_override.get("fuel_lap")
            if c:
                try:
                    fc = float(str(c).replace(",", "."))
                    if fc > 0:
                        return fc
                except Exception:
                    pass

        # 1. Intentar desde fuel_data exportado
        if self.fuel_data:
            c = self.fuel_data.get("cons_lap")
            if c and float(c) > 0:
                return float(c)
            calc_c = self.fuel_data.get("calc_results", {}).get("cons_lap")
            if calc_c and float(calc_c) > 0:
                return float(calc_c)

        # 2. Intentar leer del archivo _fuel.json del circuito activo
        champ = self.session_data.get("championship_name")
        circuit = self.session_data.get("circuit")
        if champ and circuit:
            safe_champ = re.sub(r'[\\/*?:"<>|]', "_", champ)
            safe_circ  = re.sub(r'[\\/*?:"<>|]', "_", circuit)
            f_path = PROFILES_ROOT / safe_champ / f"{safe_circ}_fuel.json"
            if f_path.exists():
                try:
                    data = json.loads(f_path.read_text(encoding="utf-8"))
                    f_lap = data.get("fuel_lap")
                    if f_lap and float(f_lap) > 0:
                        return float(f_lap)
                except Exception:
                    pass

        # 3. Fallback de seguridad
        return float(self.session_data.get("fuel_per_lap_l", 5.65))

    def _get_safety_fuel(self) -> float:
        """Obtiene el margen de seguridad de combustible configurado en el Módulo 2."""
        # 0. Intentar desde modelo de combustible forzado/vinculado
        if self._active_fuel_override:
            s = self._active_fuel_override.get("safety_fuel")
            if s is not None:
                try:
                    fs = float(str(s).replace(",", "."))
                    if fs >= 0:
                        return fs
                except Exception:
                    pass

        if self.fuel_data:
            s = self.fuel_data.get("safety_fuel_l") or self.fuel_data.get("calc_results", {}).get("safety_fuel_l")
            if s is not None and float(s) >= 0:
                return float(s)

        champ = self.session_data.get("championship_name")
        circuit = self.session_data.get("circuit")
        if champ and circuit:
            safe_champ = re.sub(r'[\\/*?:"<>|]', "_", champ)
            safe_circ  = re.sub(r'[\\/*?:"<>|]', "_", circuit)
            f_path = PROFILES_ROOT / safe_champ / f"{safe_circ}_fuel.json"
            if f_path.exists():
                try:
                    data = json.loads(f_path.read_text(encoding="utf-8"))
                    s_fuel = data.get("safety_fuel")
                    if s_fuel is not None and float(s_fuel) >= 0:
                        return float(s_fuel)
                except Exception:
                    pass

        return float(self.session_data.get("safety_margin_l", 0.4))

    def _get_weight_sensitivity(self) -> float:
        """Obtiene la sensibilidad al peso del combustible (s/L) configurada en el Módulo 2."""
        # 0. Intentar desde modelo de combustible forzado/vinculado en Estrategia
        if self._active_fuel_override:
            w = self._active_fuel_override.get("weight_sens")
            if w is not None:
                try:
                    fw = float(str(w).replace(",", "."))
                    if fw >= 0:
                        return fw
                except Exception:
                    pass

        # 1. Intentar desde fuel_data exportado en vivo desde el Módulo 2
        if self.fuel_data:
            w = self.fuel_data.get("weight_sens")
            if w is not None:
                try:
                    fw = float(str(w).replace(",", "."))
                    if fw >= 0:
                        return fw
                except Exception:
                    pass
            calc_w = self.fuel_data.get("calc_results", {}).get("weight_sens")
            if calc_w is not None:
                try:
                    fw = float(str(calc_w).replace(",", "."))
                    if fw >= 0:
                        return fw
                except Exception:
                    pass

        # 2. Intentar leer del archivo _fuel.json del circuito activo
        champ = self.session_data.get("championship_name")
        circuit = self.session_data.get("circuit")
        if champ and circuit:
            safe_champ = re.sub(r'[\\/*?:"<>|]', "_", champ)
            safe_circ  = re.sub(r'[\\/*?:"<>|]', "_", circuit)
            f_path = PROFILES_ROOT / safe_champ / f"{safe_circ}_fuel.json"
            if f_path.exists():
                try:
                    data = json.loads(f_path.read_text(encoding="utf-8"))
                    w_sens = data.get("weight_sens")
                    if w_sens is not None:
                        fw = float(str(w_sens).replace(",", "."))
                        if fw >= 0:
                            return fw
                except Exception:
                    pass

        # 3. Fallback de seguridad
        return float(self.session_data.get("weight_sens") or (float(self.session_data.get("weight_penalty_s_per_10l", 0.150)) / 10.0))

    def _get_active_tyre_params(self) -> dict:
        """
        Retorna el diccionario de parámetros de ritmo y degradación de neumáticos activo,
        usando _active_tyre_override si se seleccionó un modelo alternativo guardado,
        o self.tyre_data si se está usando el modelo activo en memoria.
        """
        if self._active_tyre_override:
            return self._active_tyre_override
        return self.tyre_data

    def _get_fuel_saving_curve(self) -> list[tuple[float, float]]:
        """
        Obtiene los puntos de calibración (delta_litros_ahorrados, delta_tiempo_perdido)
        de la tabla de combustible de la sesión para correlacionar en tiempo real.
        """
        rows = []
        if self._active_fuel_override and "fuel_saving_rows" in self._active_fuel_override:
            rows = self._active_fuel_override["fuel_saving_rows"]

        if not rows and self.fuel_data and "fuel_saving_rows" in self.fuel_data:
            rows = self.fuel_data["fuel_saving_rows"]

        if not rows:
            champ = self.session_data.get("championship_name")
            circuit = self.session_data.get("circuit")
            if champ and circuit:
                safe_champ = re.sub(r'[\/*?:"<>|]', "_", champ)
                safe_circ = re.sub(r'[\/*?:"<>|]', "_", circuit)
                f_path = PROFILES_ROOT / safe_champ / f"{safe_circ}_fuel.json"
                if f_path.exists():
                    try:
                        data = json.loads(f_path.read_text(encoding="utf-8"))
                        rows = data.get("fuel_saving_rows", [])
                    except Exception:
                        pass

        pts = [(0.0, 0.0)]
        for r in rows:
            try:
                dl = abs(float(r.get("delta_l", r.get("saving_l", r.get("fuel_l", 0.0)))))
                ds = abs(float(r.get("delta_s", r.get("penalty_s", r.get("time_s", 0.0)))))
                if dl > 1e-4:
                    pts.append((dl, ds))
            except Exception:
                continue

        pts.sort(key=lambda p: p[0])

        if len(pts) <= 1:
            cons_base = self._get_base_consumption()
            # Fallback analítico estándar: ~0.35s por 10% ahorro, ~0.80s por 20% ahorro
            pts = [(0.0, 0.0), (cons_base * 0.10, 0.35), (cons_base * 0.20, 0.80)]

        return pts

    def _get_draft_saving_curve(self) -> list[tuple[float, float]]:
        """
        Obtiene los puntos de calibración (delta_litros_ahorrados, delta_tiempo)
        de la tabla de rebufo (draft_rows) de la sesión para correlacionar en tiempo real.
        """
        rows = []
        if self._active_fuel_override and "draft_rows" in self._active_fuel_override:
            rows = self._active_fuel_override["draft_rows"]

        if not rows and self.fuel_data and "draft_rows" in self.fuel_data:
            rows = self.fuel_data["draft_rows"]

        if not rows:
            champ = self.session_data.get("championship_name")
            circuit = self.session_data.get("circuit")
            if champ and circuit:
                safe_champ = re.sub(r'[\/*?:"<>|]', "_", champ)
                safe_circ = re.sub(r'[\/*?:"<>|]', "_", circuit)
                f_path = PROFILES_ROOT / safe_champ / f"{safe_circ}_fuel.json"
                if f_path.exists():
                    try:
                        data = json.loads(f_path.read_text(encoding="utf-8"))
                        rows = data.get("draft_rows", [])
                    except Exception:
                        pass

        pts = [(0.0, 0.0)]
        for r in rows:
            try:
                dl = abs(float(r.get("delta_l", r.get("saving_l", r.get("fuel_l", 0.0)))))
                # delta_s conserva su signo (puede ser ganancia de tiempo negativa o leve pérdida positiva)
                ds = float(r.get("delta_s", r.get("penalty_s", r.get("time_s", 0.0))))
                if dl > 1e-4:
                    pts.append((dl, ds))
            except Exception:
                continue

        pts.sort(key=lambda p: p[0])

        if len(pts) <= 1:
            cons_base = self._get_base_consumption()
            # Fallback analítico estándar rebufo: ~-0.05s por 10% ahorro, ~-0.10s por 20% ahorro
            pts = [(0.0, 0.0), (cons_base * 0.10, -0.05), (cons_base * 0.20, -0.10)]

        return pts

    def _interpolate_saving_penalty(self, save_per_l: float, pts: list[tuple[float, float]]) -> float:
        """
        Interpola en tiempo real la pérdida/ganancia de tiempo por vuelta (s)
        para un ahorro objetivo de save_per_l (L/v), correlacionando con la tabla de combustible.
        """
        if save_per_l <= 0.0001:
            return 0.0

        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]

        if save_per_l <= xs[-1]:
            return float(np.interp(save_per_l, xs, ys))
        else:
            dx = xs[-1] - xs[-2] if len(xs) >= 2 else xs[-1]
            dy = ys[-1] - ys[-2] if len(ys) >= 2 else ys[-1]
            slope = dy / max(0.001, dx)
            return float(ys[-1] + slope * (save_per_l - xs[-1]))

    def _get_draft_saving_l(self) -> float:
        """
        Obtiene la reducción máxima de consumo por rebufo (L/v) definida en la tabla de combustible.
        Siempre devuelve un valor negativo (p. ej. -0.45) para descontar en el consumo por vuelta.
        """
        curve = self._get_draft_saving_curve()
        if len(curve) > 1:
            return -abs(curve[-1][0])
        return -0.25

    # ═══════════════════════════════════════════════════════════
    #  CONSTRUCCIÓN DE LA INTERFAZ DE USUARIO
    # ═══════════════════════════════════════════════════════════

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._scroll = ctk.CTkScrollableFrame(
            self,
            fg_color=self.colors["bg_primary"],
            scrollbar_button_color=self.colors["border"],
            scrollbar_button_hover_color=self.colors["accent"],
        )
        self._scroll.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        self._scroll.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_sync_banner()
        self._build_kpi_cards()
        self._build_opportunity_banner()
        self._build_controls_row()
        self._build_chart_section()

    def _build_header(self):
        header = ctk.CTkFrame(self._scroll, fg_color="transparent")
        header.pack(fill="x", padx=32, pady=(24, 8))
        header.grid_columnconfigure(1, weight=1)

        left = ctk.CTkFrame(header, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            left,
            text="📊  Comparador y Optimizador de Estrategias",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=self.colors["text_primary"],
        ).pack(anchor="w")

        ctk.CTkLabel(
            left,
            text="Simulación integral, optimizador legal más rápido, Safety Car dinámico y Rebufo",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=self.colors["text_secondary"],
        ).pack(anchor="w", pady=(2, 0))

        # Acciones superiores (CRUD y Botón Óptima)
        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.grid(row=0, column=1, sticky="e")

        ctk.CTkButton(
            actions,
            text="⚡ Cargar Óptima",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color=self.colors["accent"],
            hover_color="#D45312",
            height=32,
            corner_radius=6,
            command=self.load_optimal_strategy_action,
        ).pack(side="left", padx=(0, 10))

        self._cbo_saved = ctk.CTkComboBox(
            actions,
            variable=self._var_selected_strategy,
            values=["⚡ Estrategia Óptima"],
            width=210,
            height=32,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color=self.colors["bg_secondary"],
            border_color=self.colors["border"],
            button_color=self.colors["border"],
            button_hover_color=self.colors["accent"],
            dropdown_fg_color=self.colors["bg_secondary"],
            dropdown_text_color=self.colors["text_primary"],
            command=self._on_saved_strategy_selected,
        )
        self._cbo_saved.pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            actions,
            text="💾 Guardar",
            width=75,
            height=32,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color=self.colors["bg_secondary"],
            border_width=1,
            border_color=self.colors["border"],
            hover_color=self.colors["accent_dim"],
            text_color=self.colors["text_primary"],
            command=self.save_current_strategy_action,
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            actions,
            text="🗑️ Borrar",
            width=70,
            height=32,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color=self.colors["bg_secondary"],
            border_width=1,
            border_color=self.colors["border"],
            hover_color="#3A1515",
            text_color=self.colors.get("danger", "#FF453A"),
            command=self.delete_current_strategy_action,
        ).pack(side="left")

    def _build_sync_banner(self):
        self._sync_banner = ctk.CTkFrame(
            self._scroll,
            fg_color=self.colors["accent_dim"],
            corner_radius=8,
            border_width=1,
            border_color=self.colors["accent"],
        )
        self._sync_banner.pack(fill="x", padx=32, pady=(0, 14))
        self._sync_banner.grid_columnconfigure(0, weight=1)

        self._lbl_sync_info = ctk.CTkLabel(
            self._sync_banner,
            text="🔗  Sincronizando con Campeonatos, Combustible y Neumáticos...",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=self.colors["accent"],
        )
        self._lbl_sync_info.grid(row=0, column=0, sticky="w", padx=16, pady=8)

        models_frame = ctk.CTkFrame(self._sync_banner, fg_color="transparent")
        models_frame.grid(row=0, column=1, sticky="e", padx=12, pady=6)

        ctk.CTkLabel(
            models_frame,
            text="⛽ Combustible:",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=self.colors["text_primary"],
        ).pack(side="left", padx=(0, 4))

        self._cbo_strat_fuel = ctk.CTkComboBox(
            models_frame,
            variable=self._var_strat_fuel_model,
            values=["⭐ Modelo Base"],
            width=140,
            height=28,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=self.colors["bg_secondary"],
            border_color=self.colors["border"],
            button_color=self.colors["border"],
            button_hover_color=self.colors["accent"],
            dropdown_fg_color=self.colors["bg_secondary"],
            dropdown_text_color=self.colors["text_primary"],
            command=self._on_strat_fuel_model_changed,
        )
        self._cbo_strat_fuel.pack(side="left", padx=(0, 12))

        ctk.CTkLabel(
            models_frame,
            text="🛞 Neumáticos:",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=self.colors["text_primary"],
        ).pack(side="left", padx=(0, 4))

        self._cbo_strat_tyre = ctk.CTkComboBox(
            models_frame,
            variable=self._var_strat_tyre_model,
            values=["⭐ Modelo Base"],
            width=140,
            height=28,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=self.colors["bg_secondary"],
            border_color=self.colors["border"],
            button_color=self.colors["border"],
            button_hover_color=self.colors["accent"],
            dropdown_fg_color=self.colors["bg_secondary"],
            dropdown_text_color=self.colors["text_primary"],
            command=self._on_strat_tyre_model_changed,
        )
        self._cbo_strat_tyre.pack(side="left", padx=(0, 4))

    def _build_kpi_cards(self):
        kpi_frame = ctk.CTkFrame(self._scroll, fg_color="transparent")
        kpi_frame.pack(fill="x", padx=32, pady=(0, 14))
        kpi_frame.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        cards = [
            ("⏱️ Tiempo Total Carrera", "_lbl_kpi_total_time",  0),
            ("🏁 Vueltas Totales / Meta", "_lbl_kpi_total_laps",  1),
            ("🛑 Tiempo en Boxes",       "_lbl_kpi_box_time",    2),
            ("⛽ Gasolina Restante",     "_lbl_kpi_final_fuel",  3),
            ("📊 Delta vs Óptima",       "_lbl_kpi_delta_opt",   4),
        ]

        for title, attr_name, col in cards:
            card = ctk.CTkFrame(
                kpi_frame,
                fg_color=self.colors["bg_secondary"],
                corner_radius=8,
                border_width=1,
                border_color=self.colors["border"],
            )
            card.grid(row=0, column=col, padx=4, sticky="nsew")

            ctk.CTkLabel(
                card,
                text=title,
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                text_color=self.colors["text_secondary"],
            ).pack(anchor="w", padx=10, pady=(8, 2))

            val_lbl = ctk.CTkLabel(
                card,
                text="—",
                font=ctk.CTkFont(family="Segoe UI Mono", size=14, weight="bold"),
                text_color=self.colors["accent"],
            )
            val_lbl.pack(anchor="w", padx=10, pady=(0, 8))
            setattr(self, attr_name, val_lbl)

    def _build_opportunity_banner(self):
        """Banner desplegable dinámico cuando el Safety Car, Rebufo o ahorro permite 1 parada."""
        self._opp_banner = ctk.CTkFrame(
            self._scroll,
            fg_color="#1F1700",
            corner_radius=8,
            border_width=1,
            border_color="#FFD60A",
        )
        self._opp_banner.grid_columnconfigure(0, weight=1)

        # Contenedor vertical superior: texto explicativo de la oportunidad con auto-wrapping
        msg_f = ctk.CTkFrame(self._opp_banner, fg_color="transparent")
        msg_f.pack(fill="x", padx=16, pady=(12, 6))

        self._lbl_opp = ctk.CTkLabel(
            msg_f,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#FFD60A",
            justify="left",
            anchor="w",
            wraplength=950,
        )
        self._lbl_opp.pack(fill="x", anchor="w")

        # Fila inferior: botón de acción para aplicar 1 parada (colocado abajo en vez de al lateral)
        btn_row = ctk.CTkFrame(self._opp_banner, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(0, 12))

        self._btn_apply_1stop = ctk.CTkButton(
            btn_row,
            text="⚡ Aplicar 1 Parada Óptima",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            fg_color="#FFD60A",
            text_color="#000000",
            hover_color="#E5C000",
            height=32,
            corner_radius=6,
            command=self._apply_1stop_strategy,
        )
        self._btn_apply_1stop.pack(side="left")

        # Redimensionado dinámico del salto de línea según el ancho real de la ventana
        def _on_banner_configure(event):
            if event.width > 100:
                self._lbl_opp.configure(wraplength=max(320, event.width - 48))

        self._opp_banner.bind("<Configure>", _on_banner_configure)

        # Alias de compatibilidad
        self._sc_opp_banner = self._opp_banner
        self._lbl_sc_opp = self._lbl_opp
        self._btn_apply_sc_1stop = self._btn_apply_1stop

    def _build_controls_row(self):
        """Fila central con 2 columnas: Configuración de Stints vs Eventos Tácticos."""
        self._controls_container = ctk.CTkFrame(self._scroll, fg_color="transparent")
        self._controls_container.pack(fill="x", padx=32, pady=(0, 16))
        self._controls_container.grid_columnconfigure(0, weight=1)
        self._controls_container.grid_columnconfigure(1, weight=1)

        # ── Columna Izquierda: Stints y Compuestos ─────────────
        stints_card = ctk.CTkFrame(
            self._controls_container,
            fg_color=self.colors["bg_secondary"],
            corner_radius=10,
            border_width=1,
            border_color=self.colors["border"],
        )
        stints_card.grid(row=0, column=0, padx=(0, 8), sticky="nsew")
        stints_card.grid_columnconfigure(0, weight=1)

        # Cabecera Stints
        st_hdr = ctk.CTkFrame(stints_card, fg_color="transparent")
        st_hdr.pack(fill="x", padx=16, pady=(12, 6))

        ctk.CTkLabel(
            st_hdr,
            text="🎯 Configuración de Stints y Ruedas",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=self.colors["text_primary"],
        ).pack(side="left")

        self._seg_stops = ctk.CTkSegmentedButton(
            st_hdr,
            values=["1 Parada", "2 Paradas"],
            variable=self._var_num_stops,
            command=self._on_stops_mode_changed,
            selected_color=self.colors["accent"],
            selected_hover_color="#D45312",
            unselected_color=self.colors["bg_primary"],
            unselected_hover_color=self.colors["border"],
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            height=28,
        )
        self._seg_stops.pack(side="right")

        # Contenedor dinámico de sliders de parada
        self._sliders_frame = ctk.CTkFrame(stints_card, fg_color="transparent")
        self._sliders_frame.pack(fill="x", padx=16, pady=(4, 6))
        self._sliders_frame.grid_columnconfigure(0, weight=1)

        # Selectores de compuestos por stint con forzado individual
        comp_frame = ctk.CTkFrame(stints_card, fg_color=self.colors["bg_primary"], corner_radius=8, border_width=1, border_color=self.colors["border"])
        comp_frame.pack(fill="x", padx=16, pady=(4, 8))
        comp_frame.grid_columnconfigure((0, 1, 2), weight=1)

        # Stint 1
        s1_f = ctk.CTkFrame(comp_frame, fg_color="transparent")
        s1_f.grid(row=0, column=0, padx=8, pady=8, sticky="nsew")
        self._lbl_s1_hdr = ctk.CTkLabel(s1_f, text="Stint 1 (Salida)", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color=self.colors["text_secondary"])
        self._lbl_s1_hdr.pack(anchor="w")
        self._cbo_c1 = ctk.CTkOptionMenu(
            s1_f,
            variable=self._var_stint1_comp,
            values=["Prime (Duro)", "Alternative (Blando)"],
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=self.colors["bg_secondary"],
            button_color=self.colors["border"],
            button_hover_color=self.colors["accent"],
            command=lambda v: self._on_compound_selected(1, v),
        )
        self._cbo_c1.pack(fill="x", pady=(4, 0))

        ctk.CTkLabel(s1_f, text="Forzar en Óptima:", font=ctk.CTkFont(family="Segoe UI", size=9), text_color=self.colors["text_secondary"]).pack(anchor="w", pady=(6, 2))
        self._seg_forced_s1 = ctk.CTkSegmentedButton(
            s1_f,
            values=["Auto", "Duro", "Blando"],
            variable=self._var_forced_s1,
            command=lambda _: self._on_forced_comp_changed(),
            selected_color=self.colors["accent"],
            selected_hover_color="#D45312",
            unselected_color=self.colors["bg_secondary"],
            unselected_hover_color=self.colors["border"],
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            height=24,
        )
        self._seg_forced_s1.pack(fill="x")

        # Stint 2
        s2_f = ctk.CTkFrame(comp_frame, fg_color="transparent")
        s2_f.grid(row=0, column=1, padx=8, pady=8, sticky="nsew")
        is_1stop = "1" in self._var_num_stops.get()
        self._lbl_s2_hdr = ctk.CTkLabel(s2_f, text="Stint 2 (Final)" if is_1stop else "Stint 2 (Intermedio)", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color=self.colors["text_secondary"])
        self._lbl_s2_hdr.pack(anchor="w")
        self._cbo_c2 = ctk.CTkOptionMenu(
            s2_f,
            variable=self._var_stint2_comp,
            values=["Prime (Duro)", "Alternative (Blando)"],
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=self.colors["bg_secondary"],
            button_color=self.colors["border"],
            button_hover_color=self.colors["accent"],
            command=lambda v: self._on_compound_selected(2, v),
        )
        self._cbo_c2.pack(fill="x", pady=(4, 0))

        ctk.CTkLabel(s2_f, text="Forzar en Óptima:", font=ctk.CTkFont(family="Segoe UI", size=9), text_color=self.colors["text_secondary"]).pack(anchor="w", pady=(6, 2))
        self._seg_forced_s2 = ctk.CTkSegmentedButton(
            s2_f,
            values=["Auto", "Duro", "Blando"],
            variable=self._var_forced_s2,
            command=lambda _: self._on_forced_comp_changed(),
            selected_color=self.colors["accent"],
            selected_hover_color="#D45312",
            unselected_color=self.colors["bg_secondary"],
            unselected_hover_color=self.colors["border"],
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            height=24,
        )
        self._seg_forced_s2.pack(fill="x")

        # Stint 3
        self._s3_f = ctk.CTkFrame(comp_frame, fg_color="transparent")
        self._s3_f.grid(row=0, column=2, padx=8, pady=8, sticky="nsew")
        self._lbl_s3_hdr = ctk.CTkLabel(self._s3_f, text="Stint 3 (Final)", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color=self.colors["text_secondary"])
        self._lbl_s3_hdr.pack(anchor="w")
        self._cbo_c3 = ctk.CTkOptionMenu(
            self._s3_f,
            variable=self._var_stint3_comp,
            values=["Prime (Duro)", "Alternative (Blando)"],
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=self.colors["bg_secondary"],
            button_color=self.colors["border"],
            button_hover_color=self.colors["accent"],
            command=lambda v: self._on_compound_selected(3, v),
        )
        self._cbo_c3.pack(fill="x", pady=(4, 0))

        ctk.CTkLabel(self._s3_f, text="Forzar en Óptima:", font=ctk.CTkFont(family="Segoe UI", size=9), text_color=self.colors["text_secondary"]).pack(anchor="w", pady=(6, 2))
        self._seg_forced_s3 = ctk.CTkSegmentedButton(
            self._s3_f,
            values=["Auto", "Duro", "Blando"],
            variable=self._var_forced_s3,
            command=lambda _: self._on_forced_comp_changed(),
            selected_color=self.colors["accent"],
            selected_hover_color="#D45312",
            unselected_color=self.colors["bg_secondary"],
            unselected_hover_color=self.colors["border"],
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            height=24,
        )
        self._seg_forced_s3.pack(fill="x")

        # Desglose de Consumo Medio Objetivo por Stint
        self._stints_target_frame = ctk.CTkFrame(stints_card, fg_color=self.colors["bg_primary"], corner_radius=8, border_width=1, border_color=self.colors["border"])
        self._stints_target_frame.pack(fill="x", padx=16, pady=(0, 8))
        self._stints_target_frame.grid_columnconfigure((0, 1, 2), weight=1)

        # Alerta de reglamento de compuestos
        self._lbl_rule_status = ctk.CTkLabel(
            stints_card,
            text="🟢  Reglamento: Ambos compuestos utilizados",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=self.colors["success"],
        )
        self._lbl_rule_status.pack(anchor="w", padx=16, pady=(0, 12))

        # ── Columna Derecha: Eventos Tácticos Multi-Tramo (SC & Rebufo) ──
        events_card = ctk.CTkFrame(
            self._controls_container,
            fg_color=self.colors["bg_secondary"],
            corner_radius=10,
            border_width=1,
            border_color=self.colors["border"],
        )
        events_card.grid(row=0, column=1, padx=(8, 0), sticky="nsew")
        events_card.grid_columnconfigure(0, weight=1)

        # 1. Eventos Safety Car Multi-Tramo
        sc_box = ctk.CTkFrame(events_card, fg_color=self.colors["bg_primary"], corner_radius=8, border_width=1, border_color=self.colors["border"])
        sc_box.pack(fill="x", padx=16, pady=(12, 8))
        sc_box.grid_columnconfigure(0, weight=1)

        sc_hdr = ctk.CTkFrame(sc_box, fg_color="transparent")
        sc_hdr.pack(fill="x", padx=12, pady=(8, 4))

        self._sw_sc = ctk.CTkSwitch(
            sc_hdr,
            text="🚨  Safety Car",
            variable=self._var_sc_enabled,
            onvalue=True,
            offvalue=False,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            progress_color="#FFD60A",
            text_color="#FFD60A",
            command=self._on_modifier_changed,
        )
        self._sw_sc.pack(side="left")

        ctk.CTkButton(
            sc_hdr,
            text="+ Añadir Tramo SC",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            fg_color="#332B00",
            hover_color="#4D4100",
            text_color="#FFD60A",
            height=24,
            corner_radius=4,
            command=self._add_sc_segment,
        ).pack(side="right")

        self._sc_segments_container = ctk.CTkFrame(sc_box, fg_color="transparent")
        self._sc_segments_container.pack(fill="x", padx=12, pady=(0, 8))
        self._render_sc_segments()

        # 2. Eventos Rebufo (Draft) Multi-Tramo
        df_box = ctk.CTkFrame(events_card, fg_color=self.colors["bg_primary"], corner_radius=8, border_width=1, border_color=self.colors["border"])
        df_box.pack(fill="x", padx=16, pady=(0, 12))
        df_box.grid_columnconfigure(0, weight=1)

        df_hdr = ctk.CTkFrame(df_box, fg_color="transparent")
        df_hdr.pack(fill="x", padx=12, pady=(8, 4))

        self._sw_draft = ctk.CTkSwitch(
            df_hdr,
            text="💨  Rebufo (Draft)",
            variable=self._var_draft_enabled,
            onvalue=True,
            offvalue=False,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            progress_color=self.colors["accent"],
            text_color=self.colors["accent"],
            command=self._on_modifier_changed,
        )
        self._sw_draft.pack(side="left")

        ctk.CTkButton(
            df_hdr,
            text="+ Añadir Tramo Rebufo",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            fg_color="#331A00",
            hover_color="#522A00",
            text_color=self.colors["accent"],
            height=24,
            corner_radius=4,
            command=self._add_draft_segment,
        ).pack(side="right")

        self._draft_segments_container = ctk.CTkFrame(df_box, fg_color="transparent")
        self._draft_segments_container.pack(fill="x", padx=12, pady=(0, 8))
        self._render_draft_segments()

    def _render_sc_segments(self):
        """Renderiza dinámicamente las filas de tramos de Safety Car."""
        if not hasattr(self, "_sc_segments_container"):
            return
        for w in self._sc_segments_container.winfo_children():
            w.destroy()

        for idx, seg in enumerate(self.sc_segments):
            row_f = ctk.CTkFrame(self._sc_segments_container, fg_color="transparent")
            row_f.pack(fill="x", pady=2)
            row_f.grid_columnconfigure((1, 2, 3, 4), weight=1)

            ctk.CTkLabel(
                row_f,
                text=f"SC {idx+1}:",
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                text_color="#FFD60A",
                width=35,
            ).grid(row=0, column=0, sticky="w", padx=(0, 4))

            # Vuelta
            f_l = ctk.CTkFrame(row_f, fg_color="transparent")
            f_l.grid(row=0, column=1, padx=2, sticky="ew")
            if idx == 0:
                ctk.CTkLabel(f_l, text="V. Salida", font=ctk.CTkFont(family="Segoe UI", size=9), text_color=self.colors["text_secondary"]).pack(anchor="w")
            e_l = ctk.CTkEntry(f_l, textvariable=seg["lap"], width=54, height=30, font=ctk.CTkFont(family="Segoe UI Mono", size=11, weight="bold"), justify="center")
            e_l.pack(fill="x")
            e_l.bind("<FocusOut>", lambda e: self._on_modifier_changed())

            # Sector
            f_s = ctk.CTkFrame(row_f, fg_color="transparent")
            f_s.grid(row=0, column=2, padx=2, sticky="ew")
            if idx == 0:
                ctk.CTkLabel(f_s, text="Sector", font=ctk.CTkFont(family="Segoe UI", size=9), text_color=self.colors["text_secondary"]).pack(anchor="w")
            opt_s = ctk.CTkOptionMenu(
                f_s,
                variable=seg["sector"],
                values=["Sector 1", "Sector 2", "Sector 3"],
                font=ctk.CTkFont(family="Segoe UI", size=10),
                fg_color=self.colors["bg_secondary"],
                button_color=self.colors["border"],
                button_hover_color=self.colors["accent"],
                width=86,
                height=30,
                command=lambda v: self._on_modifier_changed(),
            )
            opt_s.pack(fill="x")

            # Duración
            f_d = ctk.CTkFrame(row_f, fg_color="transparent")
            f_d.grid(row=0, column=3, padx=2, sticky="ew")
            if idx == 0:
                ctk.CTkLabel(f_d, text="Duración (v)", font=ctk.CTkFont(family="Segoe UI", size=9), text_color=self.colors["text_secondary"]).pack(anchor="w")
            e_d = ctk.CTkEntry(f_d, textvariable=seg["duration"], width=54, height=30, font=ctk.CTkFont(family="Segoe UI Mono", size=11, weight="bold"), justify="center")
            e_d.pack(fill="x")
            e_d.bind("<FocusOut>", lambda e: self._on_modifier_changed())

            # Consumo
            f_f = ctk.CTkFrame(row_f, fg_color="transparent")
            f_f.grid(row=0, column=4, padx=2, sticky="ew")
            if idx == 0:
                ctk.CTkLabel(f_f, text="Cons. (L/v)", font=ctk.CTkFont(family="Segoe UI", size=9), text_color=self.colors["text_secondary"]).pack(anchor="w")
            e_f = ctk.CTkEntry(f_f, textvariable=seg["fuel_l"], width=60, height=30, font=ctk.CTkFont(family="Segoe UI Mono", size=11, weight="bold"), justify="center")
            e_f.pack(fill="x")
            e_f.bind("<FocusOut>", lambda e: self._on_modifier_changed())

            # Botón eliminar
            btn_del = ctk.CTkButton(
                row_f,
                text="🗑️",
                width=28,
                height=30,
                corner_radius=6,
                fg_color="transparent",
                hover_color="#3A1515",
                text_color=self.colors.get("danger", "#FF453A"),
                command=lambda i=idx: self._remove_sc_segment(i),
            )
            btn_del.grid(row=0, column=5, padx=(2, 0))

    def _add_sc_segment(self):
        last_lap = 8
        if self.sc_segments:
            try:
                last_lap = int(str(self.sc_segments[-1]["lap"].get()).strip()) + int(str(self.sc_segments[-1]["duration"].get()).strip()) + 4
            except Exception:
                last_lap = 16
        self.sc_segments.append({
            "lap": ctk.StringVar(value=str(last_lap)),
            "sector": ctk.StringVar(value="Sector 1"),
            "duration": ctk.StringVar(value="3"),
            "fuel_l": ctk.StringVar(value="1.80"),
        })
        self._render_sc_segments()
        self._on_modifier_changed()

    def _remove_sc_segment(self, idx: int):
        if len(self.sc_segments) > 1:
            self.sc_segments.pop(idx)
        else:
            self.sc_segments[0]["lap"].set("8")
            self.sc_segments[0]["sector"].set("Sector 2")
            self.sc_segments[0]["duration"].set("3")
            self.sc_segments[0]["fuel_l"].set("1.80")
        self._render_sc_segments()
        self._on_modifier_changed()

    def _render_draft_segments(self):
        """Renderiza dinámicamente las filas de tramos de Rebufo (solo intervalo de vueltas)."""
        if not hasattr(self, "_draft_segments_container"):
            return
        for w in self._draft_segments_container.winfo_children():
            w.destroy()

        for idx, seg in enumerate(self.draft_segments):
            row_f = ctk.CTkFrame(self._draft_segments_container, fg_color="transparent")
            row_f.pack(fill="x", pady=2)
            row_f.grid_columnconfigure((1, 2), weight=1)

            ctk.CTkLabel(
                row_f,
                text=f"Reb {idx+1}:",
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                text_color=self.colors["accent"],
                width=45,
            ).grid(row=0, column=0, sticky="w", padx=(0, 6))

            # Desde
            f_s = ctk.CTkFrame(row_f, fg_color="transparent")
            f_s.grid(row=0, column=1, padx=4, sticky="ew")
            if idx == 0:
                ctk.CTkLabel(f_s, text="Desde V.", font=ctk.CTkFont(family="Segoe UI", size=9), text_color=self.colors["text_secondary"]).pack(anchor="w")
            e_s = ctk.CTkEntry(f_s, textvariable=seg["start"], width=66, height=30, font=ctk.CTkFont(family="Segoe UI Mono", size=11, weight="bold"), justify="center")
            e_s.pack(fill="x")
            e_s.bind("<FocusOut>", lambda e: self._on_modifier_changed())

            # Hasta
            f_e = ctk.CTkFrame(row_f, fg_color="transparent")
            f_e.grid(row=0, column=2, padx=4, sticky="ew")
            if idx == 0:
                ctk.CTkLabel(f_e, text="Hasta V.", font=ctk.CTkFont(family="Segoe UI", size=9), text_color=self.colors["text_secondary"]).pack(anchor="w")
            e_e = ctk.CTkEntry(f_e, textvariable=seg["end"], width=66, height=30, font=ctk.CTkFont(family="Segoe UI Mono", size=11, weight="bold"), justify="center")
            e_e.pack(fill="x")
            e_e.bind("<FocusOut>", lambda e: self._on_modifier_changed())

            # Botón eliminar
            btn_del = ctk.CTkButton(
                row_f,
                text="🗑️",
                width=28,
                height=30,
                corner_radius=6,
                fg_color="transparent",
                hover_color="#3A1515",
                text_color=self.colors.get("danger", "#FF453A"),
                command=lambda j=idx: self._remove_draft_segment(j),
            )
            btn_del.grid(row=0, column=3, padx=(4, 0))

    def _add_draft_segment(self):
        last_end = 5
        if self.draft_segments:
            try:
                last_end = int(str(self.draft_segments[-1]["end"].get()).strip()) + 3
            except Exception:
                last_end = 16
        self.draft_segments.append({
            "start": ctk.StringVar(value=str(last_end)),
            "end": ctk.StringVar(value=str(last_end + 8)),
        })
        self._render_draft_segments()
        self._on_modifier_changed()

    def _remove_draft_segment(self, idx: int):
        if len(self.draft_segments) > 1:
            self.draft_segments.pop(idx)
        else:
            self.draft_segments[0]["start"].set("5")
            self.draft_segments[0]["end"].set("15")
        self._render_draft_segments()
        self._on_modifier_changed()

    def _get_active_sc_segments(self) -> list[dict]:
        res = []
        for seg in self.sc_segments:
            try:
                raw_lap = str(seg["lap"].get()).strip()
                lap = int(raw_lap) if raw_lap else 8
            except Exception:
                lap = 8
            sec = str(seg["sector"].get())
            try:
                raw_dur = str(seg["duration"].get()).strip()
                dur = int(raw_dur) if raw_dur else 3
            except Exception:
                dur = 3
            try:
                fuel_str = str(seg["fuel_l"].get()).replace(",", ".").strip()
                fuel_l = float(fuel_str) if fuel_str else 1.80
            except Exception:
                fuel_l = 1.80
            res.append({"lap": lap, "sector": sec, "duration": dur, "fuel_l": fuel_l})
        return res

    def _get_active_draft_segments(self) -> list[dict]:
        res = []
        draft_save_l = self._get_draft_saving_l()
        for seg in self.draft_segments:
            try:
                raw_s = str(seg["start"].get()).strip()
                start = int(raw_s) if raw_s else 5
            except Exception:
                start = 5
            try:
                raw_e = str(seg["end"].get()).strip()
                end = int(raw_e) if raw_e else 15
            except Exception:
                end = 15
            res.append({
                "start": min(start, end),
                "end": max(start, end),
                "delta_l": draft_save_l,
                "delta_s": 0.0,
            })
        return res

    def _on_forced_comp_changed(self):
        """Callback cuando el usuario cambia cualquiera de los compuestos forzados por stint."""
        if self._is_updating:
            return
        self.load_optimal_strategy_action()

    # Alias de compatibilidad
    _on_forced_start_comp_changed = lambda self, *_: self._on_forced_comp_changed()

    def _build_chart_section(self):
        """Contenedor para el gráfico Matplotlib dual e Inspector de Telemetría."""
        chart_wrapper = ctk.CTkFrame(
            self._scroll,
            fg_color=self.colors["bg_secondary"],
            corner_radius=10,
            border_width=1,
            border_color=self.colors["border"],
        )
        chart_wrapper.pack(fill="x", padx=32, pady=(0, 24))
        chart_wrapper.grid_columnconfigure(0, weight=1)

        c_hdr = ctk.CTkFrame(chart_wrapper, fg_color="transparent")
        c_hdr.pack(fill="x", padx=16, pady=(12, 6))

        ctk.CTkLabel(
            c_hdr,
            text="📈 Evolución de Tiempos por Vuelta y Línea Temporal de Eventos",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=self.colors["text_primary"],
        ).pack(side="left")

        # Leyenda de barras
        leg_frame = ctk.CTkFrame(c_hdr, fg_color="transparent")
        leg_frame.pack(side="right")

        # Amarillo SC
        sc_dot = ctk.CTkLabel(leg_frame, text="■", text_color="#FFD60A", font=ctk.CTkFont(size=14))
        sc_dot.pack(side="left", padx=(0, 2))
        ctk.CTkLabel(leg_frame, text="Safety Car", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color=self.colors["text_secondary"]).pack(side="left", padx=(0, 10))

        # Naranja Rebufo
        dr_dot = ctk.CTkLabel(leg_frame, text="■", text_color=self.colors["accent"], font=ctk.CTkFont(size=14))
        dr_dot.pack(side="left", padx=(0, 2))
        ctk.CTkLabel(leg_frame, text="Rebufo (Draft)", font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color=self.colors["text_secondary"]).pack(side="left")

        # HUD Inspector de Telemetría interactivo (al hacer clic en cualquier vuelta)
        self._telemetry_hud = ctk.CTkFrame(
            chart_wrapper,
            fg_color="#0D1A22",
            corner_radius=8,
            border_width=1,
            border_color="#00E5FF",
        )
        self._telemetry_hud.pack(fill="x", padx=16, pady=(0, 8))

        self._lbl_telemetry_hud = ctk.CTkLabel(
            self._telemetry_hud,
            text="💡 Haz clic en cualquier vuelta del gráfico para inspeccionar tiempo por vuelta, compuesto y combustible restante.",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#00E5FF",
            anchor="w",
        )
        self._lbl_telemetry_hud.pack(side="left", padx=12, pady=6, fill="x", expand=True)

        self._btn_clear_inspect = ctk.CTkButton(
            self._telemetry_hud,
            text="✕ Limpiar",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            fg_color="transparent",
            hover_color="#182A35",
            text_color="#A0A0A0",
            width=65,
            height=24,
            command=self._clear_inspection,
        )
        self._btn_clear_inspect.pack(side="right", padx=10, pady=4)

        # Canvas Matplotlib
        self._plot_frame = ctk.CTkFrame(
            chart_wrapper,
            fg_color=self.colors["bg_primary"],
            corner_radius=8,
            border_width=1,
            border_color=self.colors["border"],
        )
        self._plot_frame.pack(fill="x", padx=16, pady=(0, 16))

        # Figura Matplotlib con dos subplots acoplados verticalmente (4.2 : 1.1)
        self._fig = Figure(figsize=(10, 5.5), dpi=100, facecolor="#0E0E0E")
        self._gs = self._fig.add_gridspec(2, 1, height_ratios=[4.3, 1.1], hspace=0.18)
        self._ax_pace = self._fig.add_subplot(self._gs[0, 0])
        self._ax_bars = self._fig.add_subplot(self._gs[1, 0], sharex=self._ax_pace)

        self._ax_pace.set_facecolor("#141414")
        self._ax_bars.set_facecolor("#141414")

        self._mpl_canvas = FigureCanvasTkAgg(self._fig, master=self._plot_frame)
        self._mpl_canvas.draw()
        self._mpl_canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=8)

        # Conectar evento interactivo de clic sobre el canvas
        self._mpl_canvas.mpl_connect("button_press_event", self._on_chart_clicked)

        # Apunte de tiempo total de carrera tras Safety Car (al terminar el SC)
        self._sc_post_time_frame = ctk.CTkFrame(
            chart_wrapper,
            fg_color="#181500",
            corner_radius=8,
            border_width=1,
            border_color="#FFD60A",
        )
        self._lbl_sc_post_time = ctk.CTkLabel(
            self._sc_post_time_frame,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#FFD60A",
            anchor="w",
            justify="left",
        )
        self._lbl_sc_post_time.pack(side="left", padx=14, pady=8, fill="x", expand=True)

    def _on_chart_clicked(self, event):
        """Maneja el clic interactivo del usuario sobre la gráfica de ritmo o barras."""
        if event.inaxes not in [self._ax_pace, self._ax_bars]:
            return
        if event.xdata is None or not self.current_result:
            return
        lap = int(round(event.xdata))
        tot_laps = self.current_result.get("total_laps", 0)
        if lap < 1 or lap > tot_laps:
            return

        self._inspected_lap = lap
        self.recalculate_and_plot()

    def _clear_inspection(self):
        """Limpia la selección interactiva de vuelta."""
        self._inspected_lap = None
        if hasattr(self, "_lbl_telemetry_hud"):
            self._lbl_telemetry_hud.configure(
                text="💡 Haz clic en cualquier vuelta del gráfico para inspeccionar tiempo por vuelta, compuesto y combustible restante."
            )
        self.recalculate_and_plot()

    # ═══════════════════════════════════════════════════════════
    #  DESACOPLAMIENTO DE SLIDERS Y WIDGETS DE PARADA
    # ═══════════════════════════════════════════════════════════

    def _build_sliders_ui(self):
        """Construye los sliders de paradas desacoplados sin divisiones por cero."""
        for w in self._sliders_frame.winfo_children():
            w.destroy()

        num_stops = 1 if "1" in self._var_num_stops.get() else 2
        total_laps = self.current_result.get("total_laps", 31) if self.current_result else 31

        if num_stops == 1:
            p1_f = ctk.CTkFrame(self._sliders_frame, fg_color="transparent")
            p1_f.pack(fill="x", pady=2)
            p1_f.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(p1_f, text="Box 1: Parar al Fin de V.", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color=self.colors["text_primary"]).grid(row=0, column=0, sticky="w", padx=(0, 10))

            min_v = 1
            max_v = max(1, total_laps - 1)
            val_p1 = max(min_v, min(self._var_p1.get(), max_v))
            self._var_p1.set(val_p1)

            if min_v >= max_v:
                lbl_dummy = ctk.CTkLabel(p1_f, text=f"Fin V{min_v}", font=ctk.CTkFont(family="Segoe UI Mono", size=11), text_color=self.colors["accent"])
                lbl_dummy.grid(row=0, column=1, sticky="w")
                self._slider_p1 = None
            else:
                self._slider_p1 = ctk.CTkSlider(
                    p1_f,
                    from_=min_v,
                    to=max_v,
                    number_of_steps=max_v - min_v,
                    variable=self._var_p1,
                    command=self._on_p1_slider_moved,
                    button_color=self.colors["accent"],
                    button_hover_color="#D45312",
                    progress_color=self.colors["accent"],
                )
                self._slider_p1.grid(row=0, column=1, sticky="ew")

            self._lbl_p1_val = ctk.CTkLabel(p1_f, text=f"Fin V{val_p1}", font=ctk.CTkFont(family="Segoe UI Mono", size=11, weight="bold"), text_color=self.colors["accent"], width=160, anchor="e")
            self._lbl_p1_val.grid(row=0, column=2, sticky="e", padx=(8, 0))

        else:
            # 2 Paradas
            p1_f = ctk.CTkFrame(self._sliders_frame, fg_color="transparent")
            p1_f.pack(fill="x", pady=2)
            p1_f.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(p1_f, text="Box 1: Parar al Fin de V.", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color=self.colors["text_primary"]).grid(row=0, column=0, sticky="w", padx=(0, 10))

            min_p1 = 1
            max_p1 = max(1, total_laps - 2)
            val_p1 = max(min_p1, min(self._var_p1.get(), max_p1))
            self._var_p1.set(val_p1)

            if min_p1 >= max_p1:
                lbl_d1 = ctk.CTkLabel(p1_f, text=f"Fin V{min_p1}", font=ctk.CTkFont(family="Segoe UI Mono", size=11), text_color=self.colors["accent"])
                lbl_d1.grid(row=0, column=1, sticky="w")
                self._slider_p1 = None
            else:
                self._slider_p1 = ctk.CTkSlider(
                    p1_f,
                    from_=min_p1,
                    to=max_p1,
                    number_of_steps=max_p1 - min_p1,
                    variable=self._var_p1,
                    command=self._on_p1_slider_moved,
                    button_color=self.colors["accent"],
                    button_hover_color="#D45312",
                    progress_color=self.colors["accent"],
                )
                self._slider_p1.grid(row=0, column=1, sticky="ew")

            self._lbl_p1_val = ctk.CTkLabel(p1_f, text=f"Fin V{val_p1}", font=ctk.CTkFont(family="Segoe UI Mono", size=11, weight="bold"), text_color=self.colors["accent"], width=160, anchor="e")
            self._lbl_p1_val.grid(row=0, column=2, sticky="e", padx=(8, 0))

            # Parada 2
            p2_f = ctk.CTkFrame(self._sliders_frame, fg_color="transparent")
            p2_f.pack(fill="x", pady=(4, 2))
            p2_f.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(p2_f, text="Box 2: Parar al Fin de V.", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color=self.colors["text_primary"]).grid(row=0, column=0, sticky="w", padx=(0, 10))

            min_p2 = val_p1 + 1
            max_p2 = max(min_p2, total_laps - 1)
            val_p2 = max(min_p2, min(self._var_p2.get(), max_p2))
            self._var_p2.set(val_p2)

            if min_p2 >= max_p2:
                lbl_d2 = ctk.CTkLabel(p2_f, text=f"Fin V{min_p2}", font=ctk.CTkFont(family="Segoe UI Mono", size=11), text_color=self.colors["accent"])
                lbl_d2.grid(row=0, column=1, sticky="w")
                self._slider_p2 = None
            else:
                self._slider_p2 = ctk.CTkSlider(
                    p2_f,
                    from_=min_p2,
                    to=max_p2,
                    number_of_steps=max(1, max_p2 - min_p2),
                    variable=self._var_p2,
                    command=self._on_p2_slider_moved,
                    button_color=self.colors["accent"],
                    button_hover_color="#D45312",
                    progress_color=self.colors["accent"],
                )
                self._slider_p2.grid(row=0, column=1, sticky="ew")

            self._lbl_p2_val = ctk.CTkLabel(p2_f, text=f"Fin V{val_p2}", font=ctk.CTkFont(family="Segoe UI Mono", size=11, weight="bold"), text_color=self.colors["accent"], width=160, anchor="e")
            self._lbl_p2_val.grid(row=0, column=2, sticky="e", padx=(8, 0))

    def _on_stops_mode_changed(self, value: str):
        if self._is_updating:
            return
        num_stops = 1 if "1" in value else 2
        if num_stops == 1:
            self._s3_f.grid_remove()
            if hasattr(self, "_lbl_s2_hdr"):
                self._lbl_s2_hdr.configure(text="Stint 2 (Final)")
        else:
            self._s3_f.grid()
            if hasattr(self, "_lbl_s2_hdr"):
                self._lbl_s2_hdr.configure(text="Stint 2 (Intermedio)")
        self._build_sliders_ui()
        self.recalculate_and_plot()

    def _schedule_recalculate_and_plot(self):
        """Debounce de recálculo y renderizado para permitir interacción a 60 FPS sin tirones."""
        if hasattr(self, "_plot_job") and self._plot_job is not None:
            self.after_cancel(self._plot_job)
        self._plot_job = self.after(35, self.recalculate_and_plot)

    def _on_p1_slider_moved(self, val: float):
        v = int(round(val))
        self._var_p1.set(v)
        dep_laps = {seg["lap"] for seg in self._get_active_sc_segments()} if self._var_sc_enabled.get() else set()
        if hasattr(self, "_lbl_p1_val"):
            if v in dep_laps:
                self._lbl_p1_val.configure(text=f"Fin V{v} ⛔ Pit Cerrado", text_color="#FF453A")
            else:
                self._lbl_p1_val.configure(text=f"Fin V{v}", text_color=self.colors["accent"])

        # Si estamos en 2 paradas, ajustar límite inferior de slider 2
        if "2" in self._var_num_stops.get() and hasattr(self, "_slider_p2") and self._slider_p2:
            tot = self.current_result.get("total_laps", 31) if self.current_result else 31
            min_p2 = v + 1
            max_p2 = max(min_p2, tot - 1)
            new_bounds = (min_p2, max_p2)
            if getattr(self, "_s2_slider_bounds", None) != new_bounds and min_p2 < max_p2:
                self._s2_slider_bounds = new_bounds
                self._slider_p2.configure(from_=min_p2, to=max_p2, number_of_steps=max_p2 - min_p2)
            if self._var_p2.get() <= v:
                self._var_p2.set(min_p2)
                if hasattr(self, "_lbl_p2_val"):
                    self._lbl_p2_val.configure(text=f"Fin V{min_p2}")

        self._schedule_recalculate_and_plot()

    def _on_p2_slider_moved(self, val: float):
        v = int(round(val))
        self._var_p2.set(v)
        dep_laps = {seg["lap"] for seg in self._get_active_sc_segments()} if self._var_sc_enabled.get() else set()
        if hasattr(self, "_lbl_p2_val"):
            if v in dep_laps:
                self._lbl_p2_val.configure(text=f"Fin V{v} ⛔ Pit Cerrado", text_color="#FF453A")
            else:
                self._lbl_p2_val.configure(text=f"Fin V{v}", text_color=self.colors["accent"])
        self._schedule_recalculate_and_plot()

    def _on_compound_selected(self, stint_idx: int, val: str):
        c_code = self._label_to_code(val)
        c_label = self._code_to_label(c_code)
        if stint_idx == 1:
            self._var_stint1_comp.set(c_label)
        elif stint_idx == 2:
            self._var_stint2_comp.set(c_label)
        else:
            self._var_stint3_comp.set(c_label)
        self.recalculate_and_plot()

    def _on_modifier_changed(self):
        """Callback cuando cambia cualquier checkbox o valor de Safety Car o Rebufo."""
        if self._is_updating:
            return

        # Si el SC está activo y alguna parada cae en la vuelta de salida del SC (pit cerrado),
        # desplazarla a la siguiente vuelta (apertura tras pasar por meta).
        if self._var_sc_enabled.get():
            active_sc = self._get_active_sc_segments()
            dep_laps = {seg["lap"] for seg in active_sc}
            tot_laps = self.current_result.get("total_laps", 35) if self.current_result else 35
            p1_cur = self._var_p1.get()
            if p1_cur in dep_laps and p1_cur + 1 <= tot_laps:
                self._var_p1.set(p1_cur + 1)
            p2_cur = self._var_p2.get()
            if p2_cur in dep_laps and p2_cur + 1 <= tot_laps:
                self._var_p2.set(p2_cur + 1)
            self._build_sliders_ui()

        self.recalculate_and_plot()

    # ═══════════════════════════════════════════════════════════
    #  MOTOR DE SIMULACIÓN Y FÍSICA DE CARRERA
    # ═══════════════════════════════════════════════════════════

    def _simulate_strategy(
        self,
        num_stops: int,
        p1: int,
        p2: int,
        stint_comps: list[str],
        sc_enabled: bool = False,
        sc_segments: list[dict] | None = None,
        draft_enabled: bool = False,
        draft_segments: list[dict] | None = None,
        # Argumentos legacy para compatibilidad
        sc_lap: int = 8,
        sc_sector: str = "Sector 2",
        sc_duration: int = 3,
        sc_fuel_l: float = 1.80,
        draft_start: int = 5,
        draft_end: int = 15,
        draft_delta_l: float = -0.25,
        draft_delta_s: float = -0.15,
    ) -> dict:
        """
        Simulación integral vuelta a vuelta con física de neumáticos,
        sensibilidad de peso, eventos multi-tramo de SC, Rebufo y paradas en boxes.
        """
        # Constantes de sesión y combustible
        base_lap_s = float(self.session_data.get("lap_time_seconds", 84.5))
        race_dur_min = float(self.session_data.get("race_duration_min") or self.session_data.get("race_duration_minutes") or (self.session_data.get("race_duration_s", 3600.0) / 60.0))
        track_len_km = float(self.session_data.get("track_length_km", 5.47))
        sc_speed_kmh = float(self.session_data.get("sc_speed_kmh", 72.0))
        tank_cap = float(self.session_data.get("fuel_capacity_l", 70.0))
        refuel_rate = float(self.session_data.get("refuel_rate_ls", 12.0))
        tyre_change_s = float(self.session_data.get("tyre_change_time") or self.session_data.get("tyre_change_s") or 4.0)
        car_lift_s = float(self.session_data.get("car_lift_s") or self.session_data.get("car_lift_time") or 2.0)
        pitlane_loss_s = float(self.session_data.get("pitlane_loss") or self.session_data.get("pitlane_loss_s") or 22.5)
        weight_sens = self._get_weight_sensitivity()

        # OBTENCIÓN ROBUSTA DEL CONSUMO BASE Y RESERVA REALES
        cons_base = self._get_base_consumption()
        safety_l = self._get_safety_fuel()

        # Parámetros de neumáticos
        t_src = self._get_active_tyre_params()

        h_base = self._parse_time_str(str(t_src.get("hard_base_lap", base_lap_s)), base_lap_s)
        h_warm = float(str(t_src.get("hard_warmup", 0.800)).replace(",", "."))
        h_a    = float(str(t_src.get("hard_a", 0.2223)).replace(",", "."))
        h_n    = float(str(t_src.get("hard_n", -0.1208)).replace(",", "."))

        s_base = self._parse_time_str(str(t_src.get("soft_base_lap", base_lap_s - 0.450)), base_lap_s - 0.450)
        s_warm = float(str(t_src.get("soft_warmup", 0.400)).replace(",", "."))
        s_a    = float(str(t_src.get("soft_a", 0.5318)).replace(",", "."))
        s_n    = float(str(t_src.get("soft_n", -0.3968)).replace(",", "."))

        # 1. Normalización de Tramos de Safety Car Multi-Tramo
        if sc_segments is None:
            if sc_enabled:
                sc_segments = [{"lap": sc_lap, "sector": sc_sector, "duration": sc_duration, "fuel_l": sc_fuel_l}]
            else:
                sc_segments = []

        sc_pace_full = (track_len_km / max(1.0, sc_speed_kmh)) * 3600.0
        sc_laps_set = set()
        sc_fractions = {}
        sc_fuel_map = {}
        sc_deployment_laps = set()
        sc_ending_laps = set()

        if sc_enabled and sc_segments:
            for s_item in sc_segments:
                if not s_item.get("enabled", True):
                    continue
                s_lap = int(s_item.get("lap", 8))
                s_dur = int(s_item.get("duration", 3))
                s_sec = str(s_item.get("sector", "Sector 1"))
                s_fuel = float(s_item.get("fuel_l", 1.80))
                sc_deployment_laps.add(s_lap)
                sc_ending_laps.add(s_lap + s_dur)

                sec_num = 1
                if "2" in s_sec:
                    sec_num = 2
                elif "3" in s_sec:
                    sec_num = 3

                # Vuelta de despliegue inicial: fracción desde el sector del incidente hasta la meta
                frac_dep = 1.0 if sec_num == 1 else (2.0 / 3.0 if sec_num == 2 else 1.0 / 3.0)
                sc_laps_set.add(s_lap)
                sc_fractions[s_lap] = max(sc_fractions.get(s_lap, 0.0), frac_dep)
                sc_fuel_map[s_lap] = s_fuel

                # Vueltas completas de SC contadas tras cruzar por meta (duración N vueltas completas)
                for offset in range(1, s_dur + 1):
                    l_idx = s_lap + offset
                    sc_laps_set.add(l_idx)
                    sc_fractions[l_idx] = 1.0
                    sc_fuel_map[l_idx] = s_fuel

        # 2. Vueltas totales de carrera según condición de líder (restando pérdida real en boxes de los carteles de parada)
        total_race_time_s = race_dur_min * 60.0
        time_sc = sum(frac * sc_pace_full + (1.0 - frac) * base_lap_s for l_idx, frac in sc_fractions.items()) if (sc_enabled and sc_laps_set) else 0.0

        # Estimación preliminar de pérdida en boxes para inicializar la pasada 1
        est_init_pit = num_stops * (pitlane_loss_s + car_lift_s + tyre_change_s)
        green_time_avail = max(0.0, total_race_time_s - time_sc - est_init_pit)
        init_total_laps = (len(sc_laps_set) if (sc_enabled and sc_laps_set) else 0) + math.floor(green_time_avail / max(1.0, base_lap_s)) + 1
        total_laps = max(1, init_total_laps)

        # 3. Conjunto de vueltas a Rebufo Multi-Tramo leyendo de la tabla de combustible
        if draft_segments is None:
            if draft_enabled:
                draft_segments = [{"start": draft_start, "end": draft_end}]
            else:
                draft_segments = []

        draft_saving_l = self._get_draft_saving_l()
        draft_laps_set = set()
        if draft_enabled and draft_segments:
            for d_item in draft_segments:
                d_s = int(d_item.get("start", 5))
                d_e = int(d_item.get("end", 15))
                for v in range(min(d_s, d_e), max(d_s, d_e) + 1):
                    draft_laps_set.add(v)

        # 4. Normalizar códigos de compuestos de stints
        c1_code = self._label_to_code(stint_comps[0])
        c2_code = self._label_to_code(stint_comps[1] if len(stint_comps) > 1 else "soft")
        c3_code = self._label_to_code(stint_comps[2] if len(stint_comps) > 2 else "soft")
        # 5. Bucle de convergencia de pasadas para restar la pérdida exacta en boxes del líder
        usable_tank = max(1.0, tank_cap - safety_l)
        saving_curve = self._get_fuel_saving_curve()

        def _simulate_pass(target_laps: int):

            # 5. Definición de Stints
            p2_eff = 0
            if num_stops == 1:
                p1_eff = max(1, min(p1, target_laps - 1))
                stints_def = [
                    (1, 1, p1_eff, c1_code),
                    (2, p1_eff + 1, target_laps, c2_code),
                ]
                pit_laps = [p1_eff]
            else:
                p1_eff = max(1, min(p1, target_laps - 2))
                p2_eff = max(p1_eff + 1, min(p2, target_laps - 1))
                stints_def = [
                    (1, 1, p1_eff, c1_code),
                    (2, p1_eff + 1, p2_eff, c2_code),
                    (3, p2_eff + 1, target_laps, c3_code),
                ]
                pit_laps = [p1_eff, p2_eff]

            # 6. Cálculo previo de necesidad de combustible y penalización por ahorro (Lift & Coast y Rebufo)
            usable_tank = max(1.0, tank_cap - safety_l)
            stint_saving_penalties = []
            saving_curve = self._get_fuel_saving_curve()
            draft_curve = self._get_draft_saving_curve()

            for _, start_v, end_v, _ in stints_def:
                st_len = end_v - start_v + 1
                st_sc_count = sum(sc_fractions.get(v, 0.0) for v in range(start_v, end_v + 1))
                st_draft_count = len([v for v in range(start_v, end_v + 1) if (v in draft_laps_set and v not in sc_laps_set)])
                n_racing_laps = max(0.0, sum(1.0 - sc_fractions.get(v, 0.0) for v in range(start_v, end_v + 1)))

                # Combustible requerido a ritmo base sin ahorro adicional
                fuel_sc = sum(sc_fractions.get(v, 0.0) * sc_fuel_map.get(v, 1.80) for v in range(start_v, end_v + 1))
                fuel_needed_racing = n_racing_laps * cons_base
                f_needed_base = fuel_sc + fuel_needed_racing

                excess = max(0.0, f_needed_base - usable_tank)

                if excess <= 1e-4:
                    # Sin déficit de combustible en el tanque:
                    # El stint cabe con holgura a ritmo base, no se exige ahorro artificial
                    save_needed = 0.0
                    target_cons = cons_base
                    t_pen_draft = 0.0
                    t_pen_green = 0.0
                else:
                    # Hay déficit de combustible en el stint:
                    # Se calcula el consumo necesario uniforme por vuelta de carrera del stint
                    save_needed = excess / max(0.1, n_racing_laps)
                    save_needed = min(save_needed, 0.20 * cons_base)
                    target_cons = max(0.1, cons_base - save_needed)

                    # Se interpola la pérdida de tiempo según la tabla correspondiente:
                    # 1. En vueltas con rebufo: de la tabla de rebufo (draft_rows)
                    t_pen_draft = self._interpolate_saving_penalty(save_needed, draft_curve)
                    # 2. En vueltas normales: de la tabla normal de combustible (fuel_saving_rows)
                    t_pen_green = self._interpolate_saving_penalty(save_needed, saving_curve)

                stint_saving_penalties.append((save_needed, target_cons, t_pen_draft, t_pen_green))

            # 7. Simulación Vuelta a Vuelta
            lap_times = []
            lap_start_fuel = []
            lap_weight_deltas = []
            fuel_remaining = []
            lap_fuel_consumed = []
            curr_fuel = tank_cap
            pit_info = []  # (pit_lap, pit_time, fuel_loaded, is_sc_gratis)
            total_pit_time = 0.0
            stint_targets = []

            for s_idx, (st_num, start_v, end_v, comp) in enumerate(stints_def):
                save_needed, target_cons, t_pen_draft, t_pen_green = stint_saving_penalties[s_idx]

                base_p = h_base if comp == "hard" else s_base
                warmup = h_warm if comp == "hard" else s_warm
                a_val = h_a if comp == "hard" else s_a
                n_val = h_n if comp == "hard" else s_n

                tyre_x = 0  # Vida del neumático en vueltas lanzadas
                st_fuel_initial = curr_fuel
                st_sc_count = 0.0
                st_draft_count = 0

                for v in range(start_v, end_v + 1):
                    # El ritmo base (base_p) está definido con tanque lleno (tank_cap, ej. 70L).
                    # En cada vuelta se aplica la diferencia de peso según la gasolina con la que se empieza la vuelta (curr_fuel).
                    fuel_at_lap_start = curr_fuel
                    delta_peso = (fuel_at_lap_start - tank_cap) * weight_sens
                    delta_peso = min(0.0, delta_peso)
                    lap_start_fuel.append(fuel_at_lap_start)
                    lap_weight_deltas.append(delta_peso)

                    is_sc = (v in sc_laps_set)
                    is_draft = (v in draft_laps_set and not is_sc)

                    if is_sc:
                        frac = sc_fractions.get(v, 1.0)
                        st_sc_count += frac
                        sc_f = sc_fuel_map.get(v, 1.80)
                        if tyre_x == 0:
                            t_deg = warmup
                            t_pen_this = 0.0
                        elif tyre_x == 1:
                            t_deg = 0.0
                            t_pen_this = t_pen_draft if is_draft else t_pen_green
                        else:
                            t_deg = max(0.0, a_val * math.log(tyre_x) + n_val)
                            t_pen_this = t_pen_draft if is_draft else t_pen_green

                        t_green = base_p + t_deg + delta_peso + t_pen_this
                        t_lap = (1.0 - frac) * t_green + frac * sc_pace_full
                        cons_lap = (1.0 - frac) * target_cons + frac * sc_f
                        if (1.0 - frac) >= 0.5:
                            tyre_x += 1
                    elif is_draft:
                        st_draft_count += 1
                        if tyre_x == 0:
                            t_deg = warmup
                            t_pen_this = 0.0  # Vuelta de ruedas frías protegida de penalizaciones de ahorro
                        elif tyre_x == 1:
                            t_deg = 0.0
                            t_pen_this = t_pen_draft
                        else:
                            t_deg = max(0.0, a_val * math.log(tyre_x) + n_val)
                            t_pen_this = t_pen_draft

                        t_lap = base_p + t_deg + delta_peso + t_pen_this
                        cons_lap = target_cons
                        tyre_x += 1
                    else:
                        # VUELTA VERDE PURA (SIN REBUFO):
                        if tyre_x == 0:
                            t_deg = warmup
                            t_pen_this = 0.0  # Vuelta de ruedas frías protegida de penalizaciones de ahorro
                        elif tyre_x == 1:
                            t_deg = 0.0
                            t_pen_this = t_pen_green
                        else:
                            t_deg = max(0.0, a_val * math.log(tyre_x) + n_val)
                            t_pen_this = t_pen_green

                        t_lap = base_p + t_deg + delta_peso + t_pen_this
                        cons_lap = target_cons
                        tyre_x += 1

                    lap_times.append(t_lap)
                    curr_fuel = max(0.0, curr_fuel - cons_lap)
                    fuel_remaining.append(curr_fuel)
                    lap_fuel_consumed.append(cons_lap)

                    # Comprobar si esta vuelta es una parada en boxes
                    if v in pit_laps:
                        next_s_idx = s_idx + 1
                        if next_s_idx < len(stints_def):
                            n_start = stints_def[next_s_idx][1]
                            n_end = stints_def[next_s_idx][2]
                            n_laps = n_end - n_start + 1
                            f_needed_next = n_laps * cons_base + safety_l
                            fuel_to_load = min(tank_cap - curr_fuel, max(0.0, f_needed_next - curr_fuel))
                        else:
                            fuel_to_load = 0.0

                        refuel_t = fuel_to_load / max(0.1, refuel_rate)
                        normal_t_box = pitlane_loss_s + car_lift_s + max(refuel_t, tyre_change_s)

                        # REGLAS OFICIALES DE PARADA BAJO SAFETY CAR (SIM-RACING / GOD LEAGUE)
                        # 1. Vuelta de despliegue inicial: Pit lane CERRADO (no se puede parar en la vuelta que sale el SC)
                        is_pit_closed = (v in sc_deployment_laps)

                        # 2. Vuelta de fin de SC / relanzamiento: Al final de la vuelta el SC entra a boxes y el pelotón relanza
                        # ("sale escopetado"), por lo que la parada NO es gratis y se pierde el tiempo normal en boxes.
                        is_sc_ending = (v in sc_ending_laps)

                        # 3. Parada gratis: Únicamente en vueltas intermedias neutralizadas tras cruzar meta
                        is_sc_gratis = (v in sc_laps_set and not is_pit_closed and not is_sc_ending)

                        if is_pit_closed:
                            # Entrada ilegal con pitlane cerrado: sanción grave Stop&Go (+30s)
                            t_box = normal_t_box + 30.0
                        elif is_sc_gratis:
                            t_box = 0.0
                        else:
                            t_box = normal_t_box

                        total_pit_time += t_box
                        pit_info.append((v, t_box, fuel_to_load, is_sc_gratis, is_pit_closed, is_sc_ending))
                        curr_fuel += fuel_to_load

                # Datos calculados del stint para el HUD y la gráfica
                st_len = end_v - start_v + 1
                st_start_f = tank_cap if s_idx == 0 else (fuel_remaining[start_v - 2] + (pit_info[s_idx - 1][2] if s_idx - 1 < len(pit_info) else 0.0))
                st_end_f = fuel_remaining[end_v - 1]
                st_consumed_exact = max(0.1, st_start_f - st_end_f)
                avg_cons = st_consumed_exact / st_len

                # Consumo objetivo del stint: SOLO vueltas donde NO haya SC (vueltas verdes / bandera verde)
                non_sc_laps = [v for v in range(start_v, end_v + 1) if v not in sc_laps_set]
                if non_sc_laps:
                    green_avg_cons = sum(lap_fuel_consumed[v - 1] for v in non_sc_laps) / len(non_sc_laps)
                else:
                    green_avg_cons = avg_cons

                mode_parts = []
                if st_sc_count > 0.01:
                    sc_str = f"{st_sc_count:.2f}".rstrip("0").rstrip(".")
                    mode_parts.append(f"🟢 SC ({sc_str}v)")
                if st_draft_count > 0:
                    mode_parts.append(f"💨 Rebufo ({st_draft_count}v)")
                if save_needed > 0.005:
                    mode_parts.append(f"🟡 Ahorro (-{save_needed:.2f}L/v)")

                mode_str = " · ".join(mode_parts) if mode_parts else "🟢 PUSH (Normal)"

                stint_targets.append({
                    "stint_num": st_num,
                    "start_v": start_v,
                    "end_v": end_v,
                    "laps": st_len,
                    "comp": comp,
                    "avg_cons": green_avg_cons,
                    "total_avg_cons": avg_cons,
                    "sc_count": st_sc_count,
                    "draft_count": st_draft_count,
                    "mode_str": mode_str,
                    "is_last_stint": (s_idx == len(stints_def) - 1),
                })

            return stints_def, stint_targets, lap_times, lap_start_fuel, lap_weight_deltas, fuel_remaining, lap_fuel_consumed, curr_fuel, pit_info, total_pit_time, p1_eff, p2_eff, pit_laps

        # Pasada 1: con estimación preliminar de vueltas
        (stints_def, stint_targets, lap_times, lap_start_fuel, lap_weight_deltas, fuel_remaining, lap_fuel_consumed,
         curr_fuel, pit_info, total_pit_time, p1_eff, p2_eff, pit_laps) = _simulate_pass(total_laps)

        # Recálculo exacto de vueltas del líder restando el tiempo total en boxes (tiempo de carteles)
        green_time_exact = max(0.0, total_race_time_s - time_sc - total_pit_time)
        exact_green_laps = math.floor(green_time_exact / max(1.0, base_lap_s)) + 1
        converged_total_laps = (len(sc_laps_set) if (sc_enabled and sc_laps_set) else 0) + exact_green_laps
        min_laps_required = (max(pit_laps) + 1) if pit_laps else 1
        converged_total_laps = max(min_laps_required, converged_total_laps)

        # Pasada 2: si las vueltas del líder cambiaron al descontar el tiempo de boxes, re-simular con converged_total_laps
        if converged_total_laps != total_laps:
            total_laps = converged_total_laps
            (stints_def, stint_targets, lap_times, lap_start_fuel, lap_weight_deltas, fuel_remaining, lap_fuel_consumed,
             curr_fuel, pit_info, total_pit_time, p1_eff, p2_eff, pit_laps) = _simulate_pass(total_laps)

        total_track_time = sum(lap_times)
        total_race_time = total_track_time + total_pit_time

        # 8. Cálculo de tiempos totales de carrera tras Safety Car (suma de vueltas y paradas tras terminar el SC)
        post_sc_info = []
        if sc_enabled and sc_segments:
            sorted_sc_segs = sorted(
                [s for s in sc_segments if s.get("enabled", True)],
                key=lambda s: int(s.get("lap", 8))
            )
            for idx, s_item in enumerate(sorted_sc_segs):
                s_lap = int(s_item.get("lap", 8))
                s_dur = int(s_item.get("duration", 3))
                s_end = s_lap + s_dur
                restart_lap = s_end + 1

                if restart_lap <= total_laps:
                    track_post = sum(lap_times[v - 1] for v in range(restart_lap, total_laps + 1))
                    # Incluir paradas tras el SC o en la vuelta de fin de SC si no fueron gratis (perdieron tiempo de box)
                    post_pits = [
                        p for p in pit_info
                        if (p[0] >= restart_lap or (p[0] >= s_end and not (p[3] if len(p) > 3 else False)))
                    ]
                    pit_post = sum(p[1] for p in post_pits)
                    time_post = track_post + pit_post
                    rem_laps = total_laps - restart_lap + 1
                    n_pits_post = len(post_pits)
                else:
                    track_post = 0.0
                    pit_post = 0.0
                    time_post = 0.0
                    rem_laps = 0
                    n_pits_post = 0

                post_sc_info.append({
                    "segment_idx": idx + 1,
                    "sc_start_lap": s_lap,
                    "sc_end_lap": s_end,
                    "restart_lap": restart_lap,
                    "rem_laps": rem_laps,
                    "post_sc_time_s": time_post,
                    "post_sc_track_s": track_post,
                    "post_sc_pit_s": pit_post,
                    "n_pits_post": n_pits_post,
                })

        return {
            "total_laps": total_laps,
            "post_sc_info": post_sc_info,
            "lap_times": lap_times,
            "lap_start_fuel": lap_start_fuel,
            "lap_weight_deltas": lap_weight_deltas,
            "weight_sens": weight_sens,
            "fuel_remaining": fuel_remaining,
            "lap_fuel_consumed": lap_fuel_consumed,
            "total_race_time": total_race_time,
            "total_track_time": total_track_time,
            "total_pit_time": total_pit_time,
            "final_fuel": curr_fuel,
            "pit_info": pit_info,
            "sc_laps": sorted(list(sc_laps_set)),
            "sc_fractions": sc_fractions,
            "sc_segments": sc_segments if sc_enabled else [],
            "draft_laps": sorted(list(draft_laps_set)),
            "draft_segments": draft_segments if draft_enabled else [],
            "stints_def": stints_def,
            "stint_targets": stint_targets,
            "p1": p1_eff,
            "p2": p2_eff if num_stops == 2 else 0,
        }

    # ═══════════════════════════════════════════════════════════
    #  SOLUCIONADOR DE ESTRATEGIA ÓPTIMA
    # ═══════════════════════════════════════════════════════════

    def solve_optimal_strategy(self) -> tuple[dict | None, dict | None]:
        """Calcula de forma rápida la combinación de paradas y compuestos más rápida legal."""
        base_lap_s = float(self.session_data.get("lap_time_seconds", 84.5))
        race_dur_min = float(self.session_data.get("race_duration_min") or self.session_data.get("race_duration_minutes") or (self.session_data.get("race_duration_s", 3600.0) / 60.0))
        tank_cap = float(self.session_data.get("fuel_capacity_l", 70.0))
        cons_base = self._get_base_consumption()
        safety_l = self._get_safety_fuel()
        mandatory_change = bool(self.session_data.get("mandatory_compound_change", True))

        total_race_time_s = race_dur_min * 60.0
        total_laps_base = int(self.fuel_data.get("truncated_laps", math.floor(total_race_time_s / base_lap_s) + 1))
        viable_modes = self.fuel_data.get("viable_modes", ["1 Parada", "2 Paradas"])

        usable_tank = max(1.0, tank_cap - safety_l)
        max_laps_save20 = math.floor(usable_tank / (cons_base * 0.80))

        best_cfg = None
        best_res = None
        best_score = (0, float("inf"))

        f1 = self._var_forced_s1.get()
        f2 = self._var_forced_s2.get()
        f3 = self._var_forced_s3.get()

        def match_comp(comp_code: str, forced_val: str) -> bool:
            if "Duro" in forced_val:
                return comp_code == "hard"
            if "Blando" in forced_val:
                return comp_code == "soft"
            return True

        sc_en = self._var_sc_enabled.get()
        sc_segs = self._get_active_sc_segments() if sc_en else []
        df_en = self._var_draft_enabled.get()
        df_segs = self._get_active_draft_segments() if df_en else []

        max_stint_laps = max_laps_save20
        if sc_en or df_en:
            max_stint_laps = min(total_laps_base, math.floor(usable_tank / max(0.5, cons_base * 0.70)))

        # 1. Evaluar 1 Parada si es viable y no se ha forzado el Stint 3 (que solo existe en 2 paradas)
        if "1 Parada" in viable_modes and ("Duro" not in f3 and "Blando" not in f3):
            p1_min = max(1, total_laps_base - max_stint_laps)
            p1_max = min(max_stint_laps, total_laps_base - 1)

            pairs = [("hard", "soft"), ("soft", "hard")]
            if not mandatory_change:
                pairs.extend([("hard", "hard"), ("soft", "soft")])

            pairs = [p for p in pairs if match_comp(p[0], f1) and match_comp(p[1], f2)]

            for p1 in range(p1_min, p1_max + 1):
                st1_l = p1
                st2_l = total_laps_base - p1
                if st1_l > max_stint_laps or st2_l > max_stint_laps:
                    continue

                for c1, c2 in pairs:
                    res = self._simulate_strategy(
                        num_stops=1,
                        p1=p1,
                        p2=0,
                        stint_comps=[c1, c2],
                        sc_enabled=sc_en,
                        sc_segments=sc_segs,
                        draft_enabled=df_en,
                        draft_segments=df_segs,
                    )
                    score = (-res["total_laps"], res["total_race_time"])
                    if score < best_score:
                        best_score = score
                        best_res = res
                        best_cfg = {
                            "num_stops": 1,
                            "p1": p1,
                            "p2": 0,
                            "stint1_comp": c1,
                            "stint2_comp": c2,
                            "stint3_comp": "soft",
                        }

        # 2. Evaluar 2 Paradas si es viable
        if "2 Paradas" in viable_modes:
            triplets = [
                ("hard", "hard", "soft"),
                ("hard", "soft", "hard"),
                ("soft", "hard", "hard"),
                ("soft", "hard", "soft"),
                ("hard", "soft", "soft"),
                ("soft", "soft", "hard"),
            ]
            if not mandatory_change:
                triplets.extend([("hard", "hard", "hard"), ("soft", "soft", "soft")])

            triplets = [
                t for t in triplets
                if match_comp(t[0], f1) and match_comp(t[1], f2) and match_comp(t[2], f3)
            ]

            p1_min = max(1, total_laps_base - 2 * max_stint_laps)
            p1_max = min(max_stint_laps, total_laps_base - 2)

            for p1 in range(p1_min, p1_max + 1):
                if p1 > max_stint_laps:
                    continue
                p2_min = p1 + 1
                p2_max = min(p1 + max_stint_laps, total_laps_base - 1)

                for p2 in range(p2_min, p2_max + 1):
                    st2_l = p2 - p1
                    st3_l = total_laps_base - p2
                    if st2_l > max_stint_laps or st3_l > max_stint_laps:
                        continue

                    for c1, c2, c3 in triplets:
                        res = self._simulate_strategy(
                            num_stops=2,
                            p1=p1,
                            p2=p2,
                            stint_comps=[c1, c2, c3],
                            sc_enabled=sc_en,
                            sc_segments=sc_segs,
                            draft_enabled=df_en,
                            draft_segments=df_segs,
                        )
                        score = (-res["total_laps"], res["total_race_time"])
                        if score < best_score:
                            best_score = score
                            best_res = res
                            best_cfg = {
                                "num_stops": 2,
                                "p1": p1,
                                "p2": p2,
                                "stint1_comp": c1,
                                "stint2_comp": c2,
                                "stint3_comp": c3,
                            }

        return best_cfg, best_res

    def simulate_strategy_for_config(self, st: dict) -> dict | None:
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

    def get_optimal_strategy_config(self) -> dict | None:
        """Devuelve la configuración óptima calculada (o la calcula si no existe)."""
        if getattr(self, "optimal_config", None):
            return self.optimal_config
        try:
            cfg, res = self.solve_optimal_strategy()
            if cfg:
                self.optimal_config = cfg
                self.optimal_result = res
            return cfg
        except Exception:
            return None

    # ═══════════════════════════════════════════════════════════
    #  OPTIMIZADOR Y DETECTOR DE AHORRO DE PARADA (SC / REBUFO / COMBUSTIBLE)
    # ═══════════════════════════════════════════════════════════

    def _find_best_1stop_opportunity(self) -> tuple[int, str, str, float, str] | None:
        """
        Busca matemáticamente si es viable realizar 1 parada con los modificadores actuales
        (Safety Car, Rebufo y/o ahorro de combustible legal <= 20%) y halla la parada óptima.
        """
        if not self.session_data:
            return None

        tot_laps = self.current_result.get("total_laps", 25) if self.current_result else 25
        tank_cap = float(self.session_data.get("fuel_capacity_l", 70.0))
        cons_base = self._get_base_consumption()
        safety_l = self._get_safety_fuel()
        usable_tank = max(1.0, tank_cap - safety_l)

        sc_en = self._var_sc_enabled.get()
        sc_segs = self._get_active_sc_segments() if sc_en else []
        df_en = self._var_draft_enabled.get()
        df_segs = self._get_active_draft_segments() if df_en else []

        sc_laps_set = set(self.current_result.get("sc_laps", [])) if self.current_result else set()
        draft_laps_set = set(self.current_result.get("draft_laps", [])) if self.current_result else set()

        mandatory_change = bool(self.session_data.get("mandatory_compound_change", True))
        pairs = [("hard", "soft"), ("soft", "hard")]
        if not mandatory_change:
            pairs.extend([("hard", "hard"), ("soft", "soft")])

        f1 = self._var_forced_s1.get()
        f2 = self._var_forced_s2.get()
        f3 = self._var_forced_s3.get()

        # Si el usuario ha forzado específicamente el Stint 3, no se debe ofrecer una estrategia a 1 parada
        if "Duro" in f3 or "Blando" in f3:
            return None

        def match_comp(code: str, forced_val: str) -> bool:
            if "Duro" in forced_val:
                return code == "hard"
            if "Blando" in forced_val:
                return code == "soft"
            return True

        pairs = [p for p in pairs if match_comp(p[0], f1) and match_comp(p[1], f2)]

        if not pairs:
            return None

        # Vueltas a rebufo y ahorro de combustible desde la tabla de combustible
        draft_saving_l = self._get_draft_saving_l()
        draft_laps_set = set()
        if df_en and df_segs:
            for d in df_segs:
                d_s = int(d.get("start", 5))
                d_e = int(d.get("end", 15))
                for v in range(min(d_s, d_e), max(d_s, d_e) + 1):
                    draft_laps_set.add(v)

        # Mapa de combustible bajo SC (vuelta de despliegue con fracción por sector + vueltas completas tras meta)
        sc_fractions = {}
        sc_fuel_map = {}
        sc_deployment_laps = set()
        sc_ending_laps = set()
        if sc_en and sc_segs:
            for s in sc_segs:
                if not s.get("enabled", True):
                    continue
                s_l = int(s.get("lap", 8))
                s_d = int(s.get("duration", 3))
                s_sec = str(s.get("sector", "Sector 1"))
                s_fuel = float(s.get("fuel_l", 1.80))
                sec_num = 1
                if "2" in s_sec:
                    sec_num = 2
                elif "3" in s_sec:
                    sec_num = 3
                frac_dep = 1.0 if sec_num == 1 else (2.0 / 3.0 if sec_num == 2 else 1.0 / 3.0)
                sc_deployment_laps.add(s_l)
                sc_ending_laps.add(s_l + s_d)
                sc_fractions[s_l] = max(sc_fractions.get(s_l, 0.0), frac_dep)
                sc_fuel_map[s_l] = s_fuel
                for offset in range(1, s_d + 1):
                    sc_fractions[s_l + offset] = 1.0
                    sc_fuel_map[s_l + offset] = s_fuel

        best_p = None
        best_c1 = None
        best_c2 = None
        best_res = None
        best_score = (0, float("inf"))

        for p in range(1, tot_laps + 1):
            # No se puede parar en la vuelta que sale el SC (pit lane cerrado hasta pasar por meta)
            if sc_en and p in sc_deployment_laps:
                continue

            # Stint 1: vueltas 1..p
            st1_min_fuel = 0.0
            for v in range(1, p + 1):
                if v in sc_fractions:
                    frac = sc_fractions[v]
                    st1_min_fuel += (1.0 - frac) * (cons_base * 0.80) + frac * sc_fuel_map.get(v, 1.80)
                elif v in draft_laps_set:
                    st1_min_fuel += max(0.1, cons_base * 0.80)
                else:
                    st1_min_fuel += cons_base * 0.80

            if st1_min_fuel > usable_tank:
                continue

            # Stint 2: vueltas p+1..tot_laps
            st2_min_fuel = 0.0
            for v in range(p + 1, tot_laps + 1):
                if v in sc_fractions:
                    frac = sc_fractions[v]
                    st2_min_fuel += (1.0 - frac) * (cons_base * 0.80) + frac * sc_fuel_map.get(v, 1.80)
                elif v in draft_laps_set:
                    st2_min_fuel += max(0.1, cons_base * 0.80)
                else:
                    st2_min_fuel += cons_base * 0.80

            if st2_min_fuel > usable_tank:
                continue

            for c1, c2 in pairs:
                res1 = self._simulate_strategy(
                    num_stops=1,
                    p1=p,
                    p2=0,
                    stint_comps=[c1, c2],
                    sc_enabled=sc_en,
                    sc_segments=sc_segs,
                    draft_enabled=df_en,
                    draft_segments=df_segs,
                )
                score1 = (-res1["total_laps"], res1["total_race_time"])
                if score1 < best_score:
                    best_score = score1
                    best_p = p
                    best_c1 = c1
                    best_c2 = c2
                    best_res = res1

        if best_p is not None:
            best_time = best_res["total_race_time"]
            has_sc = bool(sc_en and sc_segs)
            has_df = bool(df_en and draft_laps_set)
            if has_sc and has_df:
                factor = "COMBINADA (SC + REBUFO)"
            elif has_sc:
                factor = "SAFETY CAR"
            elif has_df:
                factor = "REBUFO"
            else:
                factor = "AHORRO DE COMBUSTIBLE"

            return (best_p, best_c1, best_c2, best_time, factor, best_res)
        return None

    # Alias de compatibilidad
    _find_best_1stop_under_sc = _find_best_1stop_opportunity

    def _check_stop_saving_opportunity(self):
        """Verifica si con las condiciones actuales es viable ahorrarse una parada."""
        num_stops = 1 if "1" in self._var_num_stops.get() else 2
        banner = getattr(self, "_opp_banner", None) or getattr(self, "_sc_opp_banner", None)

        if num_stops == 1 or not self.session_data:
            if banner and banner.winfo_ismapped():
                banner.pack_forget()
            return

        cand = self._find_best_1stop_opportunity()
        if cand and self.current_result:
            best_p = cand[0]
            best_c1 = cand[1]
            best_c2 = cand[2]
            best_time = cand[3]
            factor = cand[4]
            cand_res = cand[5] if len(cand) > 5 else None

            p_fuel = 0.0
            is_sc_g = False
            if cand_res and cand_res.get("pit_info"):
                p_item = cand_res["pit_info"][0]
                p_fuel = p_item[2]
                is_sc_g = p_item[3]

            self._opportunity_1stop_candidate = (best_p, best_c1, best_c2)
            tot_laps = self.current_result.get("total_laps", 25)
            curr_time = self.current_result.get("total_race_time", best_time)
            cand_laps = cand_res.get("total_laps", tot_laps) if cand_res else tot_laps

            lbl_c1 = self._code_to_label(best_c1)
            lbl_c2 = self._code_to_label(best_c2)

            f_str = f" y repostar +{p_fuel:.1f} L" if p_fuel > 0.05 else ""
            if is_sc_g:
                pit_tag = f"al FINAL de V{best_p} (¡PARADA GRATIS BAJO SC!{f_str})"
            else:
                pit_tag = f"al FINAL de V{best_p} ({f_str.strip()})" if f_str else f"al FINAL de V{best_p}"

            if cand_laps > tot_laps:
                gain_str = f" ¡Permite completar +{cand_laps - tot_laps} vuelta(s) de carrera (Líder en vuelta sin doblar)!"
            else:
                time_diff = curr_time - best_time
                gain_str = f" ¡Ganancia estimada: -{time_diff:.1f}s!" if time_diff > 0.05 else ""

            lbl = getattr(self, "_lbl_opp", None) or getattr(self, "_lbl_sc_opp", None)
            if lbl:
                lbl.configure(
                    text=(
                        f"🚨 ¡OPORTUNIDAD DE ESTRATEGIA A 1 PARADA! ({factor})\n"
                        f"Es viable completar las {cand_laps} vueltas con 1 SOLA PARADA: Entrar a box {pit_tag} "
                        f"({lbl_c1} ➔ {lbl_c2}), ahorrando una parada en boxes.{gain_str}"
                    )
                )
            if banner:
                banner.pack(fill="x", padx=32, pady=(0, 14), before=self._controls_container)
            return

        if banner and banner.winfo_ismapped():
            banner.pack_forget()

    # Alias de compatibilidad
    _check_sc_stop_saving_opportunity = _check_stop_saving_opportunity

    def _apply_1stop_strategy(self):
        """Aplica la estrategia de 1 parada óptima calculada."""
        cand = self._find_best_1stop_opportunity()
        if not cand:
            return
        p_cand = cand[0]
        c1_cand = cand[1]
        c2_cand = cand[2]

        self._is_updating = True
        self._var_num_stops.set("1 Parada")
        if hasattr(self, "_seg_stops"):
            self._seg_stops.set("1 Parada")
        self._var_p1.set(p_cand)

        lbl_c1 = self._code_to_label(c1_cand)
        lbl_c2 = self._code_to_label(c2_cand)

        self._var_stint1_comp.set(lbl_c1)
        self._var_stint2_comp.set(lbl_c2)
        self._cbo_c1.set(lbl_c1)
        self._cbo_c2.set(lbl_c2)
        self._s3_f.grid_remove()
        if hasattr(self, "_lbl_s2_hdr"):
            self._lbl_s2_hdr.configure(text="Stint 2 (Final)")

        self._is_updating = False
        self._build_sliders_ui()
        self.recalculate_and_plot()
        banner = getattr(self, "_opp_banner", None) or getattr(self, "_sc_opp_banner", None)
        if banner:
            banner.pack_forget()

    # Alias de compatibilidad
    _apply_sc_1stop_strategy = _apply_1stop_strategy

    @staticmethod
    def _get_contiguous_blocks(laps: list[int]) -> list[tuple[int, int]]:
        """Agrupa una lista de vueltas ordenadas en intervalos contiguos [(inicio, fin), ...]."""
        if not laps:
            return []
        sorted_laps = sorted(set(laps))
        blocks = []
        start = sorted_laps[0]
        end = start
        for lap in sorted_laps[1:]:
            if lap == end + 1:
                end = lap
            else:
                blocks.append((start, end))
                start = lap
                end = lap
        blocks.append((start, end))
        return blocks

    # ═══════════════════════════════════════════════════════════
    #  ACTUALIZACIÓN, CÁLCULO Y RENDERIZADO GRÁFICO
    # ═══════════════════════════════════════════════════════════

    def recalculate_and_plot(self):
        """Ejecuta la simulación con la configuración activa y redibuja Matplotlib."""
        if hasattr(self, "_plot_job") and self._plot_job is not None:
            try:
                self.after_cancel(self._plot_job)
            except Exception:
                pass
            self._plot_job = None

        if not self.session_data:
            return

        num_stops = 1 if "1" in self._var_num_stops.get() else 2
        p1 = self._var_p1.get()
        p2 = self._var_p2.get()

        c1 = self._label_to_code(self._var_stint1_comp.get())
        c2 = self._label_to_code(self._var_stint2_comp.get())
        c3 = self._label_to_code(self._var_stint3_comp.get())

        sc_en = self._var_sc_enabled.get()
        sc_segs = self._get_active_sc_segments() if sc_en else []

        df_en = self._var_draft_enabled.get()
        df_segs = self._get_active_draft_segments() if df_en else []

        res = self._simulate_strategy(
            num_stops=num_stops,
            p1=p1,
            p2=p2,
            stint_comps=[c1, c2, c3],
            sc_enabled=sc_en,
            sc_segments=sc_segs,
            draft_enabled=df_en,
            draft_segments=df_segs,
        )
        self.current_result = res

        # ── 1. Actualizar Tarjetas KPI ────────────────────────
        tot_time_s = res["total_race_time"]
        tot_laps = res["total_laps"]
        tot_box_s = res["total_pit_time"]
        f_fuel = res["final_fuel"]

        self._lbl_kpi_total_time.configure(text=self._format_seconds_hh_mm_ss(tot_time_s))
        self._lbl_kpi_total_laps.configure(text=f"{tot_laps} v (Meta: V{tot_laps})")

        has_sc_pit = any(item[3] for item in res["pit_info"])
        if has_sc_pit:
            self._lbl_kpi_box_time.configure(text=f"{tot_box_s:.1f}s (GRATIS SC)", text_color="#FFD60A")
        else:
            self._lbl_kpi_box_time.configure(text=f"{tot_box_s:.1f}s", text_color=self.colors["accent"])

        self._lbl_kpi_final_fuel.configure(text=f"{f_fuel:.2f} L")

        if self.optimal_result:
            opt_time = self.optimal_result["total_race_time"]
            opt_laps = self.optimal_result.get("total_laps", tot_laps)
            delta_laps = tot_laps - opt_laps

            if delta_laps > 0:
                self._lbl_kpi_delta_opt.configure(
                    text=f"+{delta_laps}v (SUPERIOR)",
                    text_color=self.colors["success"]
                )
            elif delta_laps < 0:
                self._lbl_kpi_delta_opt.configure(
                    text=f"{delta_laps}v (DOBLADO)",
                    text_color=self.colors["danger"]
                )
            else:
                delta_opt = tot_time_s - opt_time
                if abs(delta_opt) < 0.05:
                    self._lbl_kpi_delta_opt.configure(text="0.000s (ÓPTIMA)", text_color=self.colors["success"])
                elif delta_opt > 0:
                    self._lbl_kpi_delta_opt.configure(text=f"+{delta_opt:.3f}s", text_color="#FFA94D")
                else:
                    self._lbl_kpi_delta_opt.configure(text=f"{delta_opt:.3f}s (SUPERIOR)", text_color=self.colors["success"])
        else:
            self._lbl_kpi_delta_opt.configure(text="—")

        # Verificar cumplimiento de reglamento de compuestos
        mandatory = bool(self.session_data.get("mandatory_compound_change", True))
        if mandatory:
            used_comps = {c1, c2} if num_stops == 1 else {c1, c2, c3}
            if "hard" in used_comps and "soft" in used_comps:
                self._lbl_rule_status.configure(text="🟢  Reglamento: Ambos compuestos utilizados", text_color=self.colors["success"])
            else:
                self._lbl_rule_status.configure(text="⚠️  Reglamento: Obligatorio usar Duro y Blando", text_color=self.colors["danger"])
        else:
            self._lbl_rule_status.configure(text="ℹ️  Reglamento: Compuesto libre", text_color=self.colors["text_secondary"])

        # ── 2. Actualizar Desglose de Consumo por Stint (UI) ──
        cons_base = self._get_base_consumption()
        stint_targets = res["stint_targets"]
        needed_boxes = len(stint_targets)

        # Crear estructura de cajas sólo si no existe o si cambió el número de stints
        if not hasattr(self, "_stint_ui_boxes") or len(self._stint_ui_boxes) != needed_boxes:
            for w in self._stints_target_frame.winfo_children():
                w.destroy()
            self._stint_ui_boxes = []
            for idx in range(needed_boxes):
                s_box = ctk.CTkFrame(self._stints_target_frame, fg_color="transparent")
                s_box.grid(row=0, column=idx, padx=8, pady=6, sticky="nsew")
                lbl_h = ctk.CTkLabel(
                    s_box,
                    text="",
                    font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                    text_color=self.colors["text_secondary"],
                )
                lbl_h.pack(anchor="w")
                lbl_v = ctk.CTkLabel(
                    s_box,
                    text="",
                    font=ctk.CTkFont(family="Segoe UI Mono", size=11, weight="bold"),
                )
                lbl_v.pack(anchor="w", pady=(2, 0))
                self._stint_ui_boxes.append((s_box, lbl_h, lbl_v))

        # Actualizar textos de los widgets existentes sin destruir nada
        for idx, st in enumerate(stint_targets):
            _, lbl_h, lbl_v = self._stint_ui_boxes[idx]
            comp_lbl = self._code_to_label(st["comp"])
            if st["is_last_stint"]:
                st_header = f"Stint {st['stint_num']} (V{st['start_v']} ➔ Meta V{st['end_v']}, {st['laps']}v) · {comp_lbl}"
            else:
                p_item = next((p for p in res["pit_info"] if p[0] == st['end_v']), None)
                if p_item:
                    p_lap = p_item[0]
                    p_t = p_item[1]
                    p_f = p_item[2]
                    p_sc_g = p_item[3]
                    p_closed = p_item[4] if len(p_item) > 4 else False
                    p_end = p_item[5] if len(p_item) > 5 else False
                    f_tag = f"Poner +{p_f:.1f} L" if p_f > 0.05 else "Solo Gomas (+0.0L)"
                    if p_closed:
                        pit_tag = f"⛔ Box fin V{st['end_v']} (¡PIT CERRADO! · {f_tag})"
                    elif p_sc_g:
                        pit_tag = f"➔ Box fin V{st['end_v']} (🚨 Gratis SC · {f_tag})"
                    elif p_end:
                        pit_tag = f"➔ Box fin V{st['end_v']} (⚠️ Fin SC · {f_tag})"
                    else:
                        pit_tag = f"➔ Box fin V{st['end_v']} ({f_tag})"
                else:
                    pit_tag = f"➔ Box fin V{st['end_v']}"
                st_header = f"Stint {st['stint_num']} (V{st['start_v']} ➔ Fin V{st['end_v']}, {st['laps']}v) · {comp_lbl} {pit_tag}"

            lbl_h.configure(text=st_header)

            delta_c = st["avg_cons"] - cons_base
            delta_str = f"Δ {delta_c:+.2f} L/v" if abs(delta_c) >= 0.005 else "Δ 0.00 L/v"
            val_str = f"Consumo: {st['avg_cons']:.2f} L/v ({delta_str}) | {st['mode_str']}"
            t_color = "#FFD60A" if "SC" in st["mode_str"] else ("#FFA94D" if "Ahorro" in st["mode_str"] else self.colors["success"])
            lbl_v.configure(text=val_str, text_color=t_color)

        # Verificar si hay oportunidad de ahorrar parada (por SC, Rebufo o combustible)
        self._check_stop_saving_opportunity()

        # ── 3. Renderizado en Matplotlib ──────────────────────
        self._ax_pace.clear()
        self._ax_bars.clear()

        self._ax_pace.set_facecolor("#141414")
        self._ax_bars.set_facecolor("#141414")

        laps_arr = np.arange(1, tot_laps + 1)
        times_arr = np.array(res["lap_times"])
        sc_laps_set = set(res["sc_laps"])

        # Calcular rango Y SOLO con vueltas de bandera verde (evita desescalar a 350s)
        green_times = [t for v, t in zip(laps_arr, times_arr) if v not in sc_laps_set]
        if green_times:
            y_min = min(green_times) - 0.9  # Margen inferior para alojar los badges de consumo
            y_max = max(green_times) + 0.6
        else:
            y_min = 100.0
            y_max = 130.0

        # Cuadrícula vertical de vueltas individual (cada vuelta discontinua, cada 5 más gruesa)
        for v in range(1, tot_laps + 1):
            if v % 5 == 0:
                self._ax_pace.axvline(x=v, color="#383838", linestyle="--", linewidth=1.1, alpha=0.6, zorder=1)
                self._ax_bars.axvline(x=v, color="#383838", linestyle="--", linewidth=1.1, alpha=0.5, zorder=1)
            else:
                self._ax_pace.axvline(x=v, color="#222222", linestyle=":", linewidth=0.6, alpha=0.45, zorder=1)
                self._ax_bars.axvline(x=v, color="#222222", linestyle=":", linewidth=0.6, alpha=0.35, zorder=1)

        # Sombreado de área por compuesto y curvas continuas
        plotted_h = False
        plotted_s = False

        for _, start_v, end_v, comp in res["stints_def"]:
            st_laps = laps_arr[start_v - 1 : end_v]
            st_times_raw = times_arr[start_v - 1 : end_v]

            # Reemplazar vueltas de SC por NaN en la curva para no disparar el eje Y
            st_times_plot = np.array([
                st_times_raw[i] if (start_v + i) not in sc_laps_set else np.nan
                for i in range(len(st_laps))
            ])

            if comp == "hard":
                c_line = "#FFFFFF"
                c_area = "#E8E8E8"
                alpha_v = 0.18
                label_txt = "Prime (Duro)" if not plotted_h else None
                plotted_h = True
            else:
                c_line = "#FF3B30"
                c_area = "#FF3B30"
                alpha_v = 0.22
                label_txt = "Alternative (Blando)" if not plotted_s else None
                plotted_s = True

            # Sombrear área y trazar ritmo solo en vueltas verdes válidas
            valid_mask = ~np.isnan(st_times_plot)
            if np.any(valid_mask):
                self._ax_pace.fill_between(st_laps, y_min, st_times_plot, where=valid_mask, color=c_area, alpha=alpha_v, zorder=2)
            self._ax_pace.plot(st_laps, st_times_plot, color=c_line, linewidth=2.3, label=label_txt, zorder=3)

        # Conexiones continuas entre stints (si ninguna es SC)
        for p_item in res["pit_info"]:
            pit_lap = p_item[0]
            if pit_lap < tot_laps and pit_lap not in sc_laps_set and (pit_lap + 1) not in sc_laps_set:
                self._ax_pace.plot([pit_lap, pit_lap + 1], [times_arr[pit_lap - 1], times_arr[pit_lap]], color="#FFA94D", linestyle=":", linewidth=1.8, zorder=3)

        # ── Franjas amarillas rayadas (hatch) de Safety Car en el gráfico superior (sin desescalar Y) ──
        sc_blocks = self._get_contiguous_blocks(res["sc_laps"])
        sc_fractions = res.get("sc_fractions", {})
        for b_start, b_end in sc_blocks:
            frac_start = sc_fractions.get(b_start, 1.0)
            x_start = b_start - 0.5 + (1.0 - frac_start)
            x_end = b_end + 0.5
            b_sc_laps = sum(sc_fractions.get(v, 1.0) for v in range(b_start, b_end + 1))
            b_txt = f"{b_sc_laps:.2f}".rstrip("0").rstrip(".")

            self._ax_pace.axvspan(
                x_start,
                x_end,
                facecolor="#FFD60A",
                alpha=0.18,
                hatch="//",
                edgecolor="#FFD60A",
                linewidth=1.4,
                zorder=2,
            )
            self._ax_pace.text(
                (x_start + x_end) / 2.0,
                y_min + (y_max - y_min) * 0.5,
                f"[SC] SAFETY CAR\n({b_txt} v)",
                color="#FFD60A",
                fontsize=8.5,
                fontweight="bold",
                ha="center",
                va="center",
                bbox=dict(boxstyle="round,pad=0.3", fc="#1C1800", ec="#FFD60A", lw=1.2),
                zorder=5,
            )

        # ── Anotaciones de parada en boxes (Resaltar parada al FINAL de la vuelta) ──
        for idx, p_item in enumerate(res["pit_info"]):
            pit_lap = p_item[0]
            pit_time = p_item[1]
            f_load = p_item[2]
            is_sc_g = p_item[3]
            is_closed = p_item[4] if len(p_item) > 4 else False
            is_sc_end = p_item[5] if len(p_item) > 5 else False

            if pit_lap <= tot_laps:
                x_pit = pit_lap + 0.5
                c_line = "#FF453A" if is_closed else ("#FFD60A" if is_sc_g else "#F26419")
                self._ax_pace.axvline(x=x_pit, color=c_line, linestyle="-.", linewidth=2.0, alpha=0.9, zorder=4)
                self._ax_bars.axvline(x=x_pit, color=c_line, linestyle="-.", linewidth=2.0, alpha=0.7, zorder=3)

                f_badge = f"PONER +{f_load:.1f} L" if f_load > 0.05 else "SOLO GOMAS (+0.0L)"
                if is_closed:
                    badge_txt = f"BOX {idx+1} · PARAR AL FINAL DE V{pit_lap}\n⛔ ¡PIT CERRADO! (+30s S&G)\n{f_badge}"
                    b_color = "#FF453A"
                    b_ec = "#FF453A"
                    b_fc = "#260B0B"
                elif is_sc_g:
                    badge_txt = f"BOX {idx+1} · PARAR AL FINAL DE V{pit_lap}\n🚨 GRATIS SC\n{f_badge}"
                    b_color = "#FFD60A"
                    b_ec = "#FFD60A"
                    b_fc = "#1C1800"
                elif is_sc_end:
                    badge_txt = f"BOX {idx+1} · PARAR AL FINAL DE V{pit_lap}\n⚠️ FIN SC (+{pit_time:.1f}s)\n{f_badge}"
                    b_color = "#FFA94D"
                    b_ec = "#FFA94D"
                    b_fc = "#201205"
                else:
                    badge_txt = f"BOX {idx+1} · PARAR AL FINAL DE V{pit_lap}\n+{pit_time:.1f}s\n{f_badge}"
                    b_color = "#FFA94D"
                    b_ec = "#F26419"
                    b_fc = "#1F1005"

                x_text = x_pit + 0.35 if pit_lap < tot_laps - 4 else x_pit - 4.2
                self._ax_pace.annotate(
                    badge_txt,
                    xy=(x_pit, y_max - 0.1),
                    xytext=(x_text, y_max - 0.35 - (idx * 0.32)),
                    arrowprops=dict(arrowstyle="->", color=b_ec, lw=1.4),
                    color=b_color,
                    fontsize=8.5,
                    fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.3", fc=b_fc, ec=b_ec, lw=1.2),
                    zorder=7,
                )

        # Etiquetas de Consumo por Stint dentro de la gráfica (justo debajo de cada stint con Delta)
        for idx, st in enumerate(res["stint_targets"]):
            start_v = st["start_v"]
            end_v = st["end_v"]
            avg_c = st["avg_cons"]
            delta_c = avg_c - cons_base
            comp_lbl = self._code_to_label(st["comp"])

            delta_str = f"Δ {delta_c:+.2f} L/v" if abs(delta_c) >= 0.005 else "Δ 0.00 L/v"
            badge_txt = f"Stint {st['stint_num']} ({comp_lbl})\n{avg_c:.2f} L/v ({delta_str})"

            x_center = (start_v + end_v) / 2.0
            y_badge = y_min + 0.35

            if "SC" in st["mode_str"]:
                b_color = "#FFD60A"
                b_fc = "#1E1700"
                b_ec = "#FFD60A"
            elif "AHORRO" in st["mode_str"] or delta_c < -0.05:
                b_color = "#FFA94D"
                b_fc = "#1F1200"
                b_ec = "#FFA94D"
            else:
                b_color = "#51CF66"
                b_fc = "#041F0A"
                b_ec = "#51CF66"

            self._ax_pace.text(
                x_center,
                y_badge,
                badge_txt,
                color=b_color,
                fontsize=8,
                fontweight="bold",
                ha="center",
                va="center",
                bbox=dict(boxstyle="round,pad=0.3", fc=b_fc, ec=b_ec, lw=1.0),
                zorder=6,
            )

        # Línea de Meta / Bandera a cuadros explícita
        self._ax_pace.axvline(x=tot_laps, color="#51CF66", linestyle="-", linewidth=2.2, alpha=0.9, zorder=3)
        self._ax_pace.annotate(
            f"META / FIN\nVuelta {tot_laps}",
            xy=(tot_laps, y_max - 0.05),
            xytext=(tot_laps - 0.35, y_max - 0.25),
            color="#51CF66",
            fontsize=8.5,
            fontweight="bold",
            ha="right",
            bbox=dict(boxstyle="round,pad=0.3", fc="#041F0A", ec="#51CF66", lw=1.2),
            zorder=6,
        )

        # ── Inspector interactivo de Telemetría al hacer clic ──
        if self._inspected_lap and 1 <= self._inspected_lap <= tot_laps:
            insp_lap = self._inspected_lap
            lap_time = times_arr[insp_lap - 1]
            fuel_rem = res["fuel_remaining"][insp_lap - 1]

            insp_comp = "hard"
            st_idx = 1
            for s_num, s_start, s_end, c in res["stints_def"]:
                if s_start <= insp_lap <= s_end:
                    insp_comp = c
                    st_idx = s_num
                    break
            c_name = "Prime (Duro)" if insp_comp == "hard" else "Alternative (Blando)"
            is_sc = insp_lap in sc_laps_set
            frac_v = sc_fractions.get(insp_lap, 1.0) if is_sc else 0.0
            is_df = insp_lap in set(res["draft_laps"])

            flags = []
            if is_sc:
                if frac_v < 0.99:
                    s_entry = 2 if frac_v > 0.5 else 3
                    flags.append(f"🚨 SC V0 (S{s_entry}➔ · {frac_v:.2f}v)")
                else:
                    flags.append("🚨 SC")
            if is_df:
                flags.append("💨 REBUFO")
            f_str = f" · {' '.join(flags)}" if flags else ""
            if not is_sc:
                t_str = f"{self._format_seconds(lap_time)} ({lap_time:.2f}s)"
            elif frac_v < 0.99:
                t_str = f"SC V0 ({self._format_seconds(lap_time)} · {lap_time:.1f}s)"
            else:
                t_str = f"SC ({lap_time:.1f}s)"

            pit_match = next((p for p in res["pit_info"] if p[0] == insp_lap), None)
            pit_msg = ""
            pit_callout = ""
            if pit_match:
                p_lap = pit_match[0]
                p_t = pit_match[1]
                p_f = pit_match[2]
                p_sc_g = pit_match[3]
                p_closed = pit_match[4] if len(pit_match) > 4 else False
                p_end = pit_match[5] if len(pit_match) > 5 else False
                f_txt = f"Poner +{p_f:.1f} L" if p_f > 0.05 else "Solo Gomas"
                f_short = f"+{p_f:.1f}L" if p_f > 0.05 else "0L"
                if p_closed:
                    pit_msg = f"  │  ⛔ PARADA BOX: ¡PIT CERRADO! (+30s S&G) · {f_txt}"
                    pit_callout = f"\n⛔ Pit Cerrado ({f_short})"
                elif p_sc_g:
                    pit_msg = f"  │  🚨 PARADA BOX: ¡GRATIS SC! · {f_txt}"
                    pit_callout = f"\n🚨 Gratis SC ({f_short})"
                elif p_end:
                    pit_msg = f"  │  ⚠️ PARADA BOX: Relanzamiento (+{p_t:.1f}s) · {f_txt}"
                    pit_callout = f"\n⚠️ Fin SC ({f_short})"
                else:
                    pit_msg = f"  │  ⛽ PARADA BOX: +{p_t:.1f}s · {f_txt}"
                    pit_callout = f"\n⛽ Box ({f_short})"

            fuel_start_v = res.get("lap_start_fuel", [fuel_rem] * tot_laps)[insp_lap - 1]
            w_delta_v = res.get("lap_weight_deltas", [0.0] * tot_laps)[insp_lap - 1]
            hud_msg = (
                f"🔍 Vuelta {insp_lap}/{tot_laps} (Stint {st_idx} · {c_name}){f_str}  │  "
                f"⏱️ Tiempo Vuelta: {t_str} (Δ Peso: {w_delta_v:+.3f}s)  │  "
                f"⛽ Combustible: Inicio {fuel_start_v:.2f}L ➔ Fin {fuel_rem:.2f}L{pit_msg}"
            )
            if hasattr(self, "_lbl_telemetry_hud"):
                self._lbl_telemetry_hud.configure(text=hud_msg)

            # Líneas del inspector en ritmo y barras
            self._ax_pace.axvline(x=insp_lap, color="#00E5FF", linestyle="-", linewidth=1.8, alpha=0.9, zorder=8)
            self._ax_bars.axvline(x=insp_lap, color="#00E5FF", linestyle="-", linewidth=1.5, alpha=0.8, zorder=5)

            # Punto y llamada flotante en el gráfico de ritmo
            annot_y = lap_time if not is_sc else (y_min + y_max) / 2.0
            if not is_sc:
                self._ax_pace.scatter([insp_lap], [lap_time], color="#00E5FF", s=65, edgecolors="#FFFFFF", linewidths=1.5, zorder=9)

            x_off = 0.5 if insp_lap <= tot_laps - 4 else -4.2
            y_off = 0.25 if annot_y <= y_max - 0.45 else -0.45
            self._ax_pace.annotate(
                f"V{insp_lap}: {t_str} (ΔPeso {w_delta_v:+.3f}s)\nComb: {fuel_start_v:.1f}L ➔ {fuel_rem:.1f}L{pit_callout}",
                xy=(insp_lap, annot_y),
                xytext=(insp_lap + x_off, annot_y + y_off),
                arrowprops=dict(arrowstyle="->", color="#00E5FF", lw=1.3),
                color="#00E5FF",
                fontsize=8.5,
                fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.3", fc="#071720", ec="#00E5FF", lw=1.2),
                zorder=10,
            )
        else:
            if hasattr(self, "_lbl_telemetry_hud"):
                self._lbl_telemetry_hud.configure(
                    text="💡 Haz clic en cualquier vuelta del gráfico para inspeccionar tiempo por vuelta, compuesto y combustible restante."
                )

        # Formato de Subplot Superior (Ritmo)
        self._ax_pace.set_title(f"Ritmo de Carrera Vuelta a Vuelta · {tot_laps} Vueltas Totales (Meta: V{tot_laps})", color="#FFFFFF", fontsize=11, fontweight="bold", pad=8)
        self._ax_pace.set_ylabel("Tiempo Vuelta", color="#A0A0A0", fontsize=9.5, labelpad=8)
        self._ax_pace.yaxis.set_major_formatter(FuncFormatter(lambda val, _: self._format_seconds(val)))
        self._ax_pace.set_xlim(0.5, tot_laps + 0.5)
        self._ax_pace.set_ylim(y_min, y_max + 0.3)
        self._ax_pace.tick_params(labelbottom=False, colors="#A0A0A0")

        # Leyenda de neumáticos en color blanco nítido
        leg = self._ax_pace.legend(loc="upper left", frameon=True, facecolor="#141414", edgecolor="#333333", fontsize=8.5, labelcolor="white")
        if leg:
            for text in leg.get_texts():
                text.set_color("#FFFFFF")

        # ── 4. Subplot Inferior: Barras de Safety Car y Rebufo ──
        self._ax_bars.set_ylim(-0.3, 2.3)
        self._ax_bars.set_yticks([0.6, 1.6])
        self._ax_bars.set_yticklabels(["Rebufo", "Safety Car"], color="#A0A0A0", fontsize=9, fontweight="bold")
        self._ax_bars.set_xlim(0.5, tot_laps + 0.5)
        self._ax_bars.set_xlabel("Vuelta de Carrera", color="#A0A0A0", fontsize=9.5, labelpad=6)
        self._ax_bars.tick_params(colors="#A0A0A0")

        # Ticks del eje X explícitos incluyendo siempre la vuelta de meta
        step = 5 if tot_laps > 15 else 2
        ticks = list(range(1, tot_laps + 1, step))
        if tot_laps not in ticks:
            ticks.append(tot_laps)
        self._ax_bars.set_xticks(ticks)
        self._ax_bars.axvline(x=tot_laps, color="#51CF66", linestyle="-", linewidth=2.2, alpha=0.7)

        # Dibujar barras amarillas de SC (por tramo contiguo respetando sector de despliegue)
        for b_start, b_end in sc_blocks:
            frac_start = sc_fractions.get(b_start, 1.0)
            x_start = b_start - 0.5 + (1.0 - frac_start)
            width = (b_end + 0.5) - x_start
            self._ax_bars.broken_barh(
                [(x_start, width)],
                (1.2, 0.8),
                facecolors="#FFD60A",
                edgecolors="#FFF066",
                linewidth=1,
            )

        # Dibujar barras naranjas de Rebufo (por tramo contiguo)
        draft_blocks = self._get_contiguous_blocks(res["draft_laps"])
        for d_start, d_end in draft_blocks:
            d_count = d_end - d_start + 1
            self._ax_bars.broken_barh(
                [(d_start - 0.5, d_count)],
                (0.2, 0.8),
                facecolors=self.colors["accent"],
                edgecolors="#FFA94D",
                linewidth=1,
            )

        # Actualizar etiquetas de sliders de parada con litros y estado de pitlane
        p1_val = self._var_p1.get()
        p1_info = next((p for p in res["pit_info"] if p[0] == p1_val), None)
        if hasattr(self, "_lbl_p1_val") and self._lbl_p1_val:
            if p1_info:
                p_f = p1_info[2]
                is_sc_g = p1_info[3]
                is_closed = p1_info[4] if len(p1_info) > 4 else False
                f_txt = f"+{p_f:.1f}L" if p_f > 0.05 else "0L"
                if is_closed:
                    self._lbl_p1_val.configure(text=f"Fin V{p1_val} ⛔ ({f_txt})", text_color="#FF453A")
                elif is_sc_g:
                    self._lbl_p1_val.configure(text=f"Fin V{p1_val} 🚨 ({f_txt})", text_color="#FFD60A")
                else:
                    self._lbl_p1_val.configure(text=f"Fin V{p1_val} ({f_txt})", text_color=self.colors["accent"])
            else:
                self._lbl_p1_val.configure(text=f"Fin V{p1_val}", text_color=self.colors["accent"])

        if num_stops == 2 and hasattr(self, "_lbl_p2_val") and self._lbl_p2_val:
            p2_val = self._var_p2.get()
            p2_info = next((p for p in res["pit_info"] if p[0] == p2_val), None)
            if p2_info:
                p_f = p2_info[2]
                is_sc_g = p2_info[3]
                is_closed = p2_info[4] if len(p2_info) > 4 else False
                f_txt = f"+{p_f:.1f}L" if p_f > 0.05 else "0L"
                if is_closed:
                    self._lbl_p2_val.configure(text=f"Fin V{p2_val} ⛔ ({f_txt})", text_color="#FF453A")
                elif is_sc_g:
                    self._lbl_p2_val.configure(text=f"Fin V{p2_val} 🚨 ({f_txt})", text_color="#FFD60A")
                else:
                    self._lbl_p2_val.configure(text=f"Fin V{p2_val} ({f_txt})", text_color=self.colors["accent"])
            else:
                self._lbl_p2_val.configure(text=f"Fin V{p2_val}", text_color=self.colors["accent"])

        if self._mpl_canvas:
            self._mpl_canvas.draw_idle()

        # ── 5. Actualizar Apunte de Tiempo Total de Carrera tras Safety Car ──
        post_sc_items = res.get("post_sc_info", [])
        if sc_en and post_sc_items and hasattr(self, "_sc_post_time_frame") and hasattr(self, "_lbl_sc_post_time"):
            lines_sc = []
            for item in post_sc_items:
                seg_i = item["segment_idx"]
                s_start = item["sc_start_lap"]
                s_end = item["sc_end_lap"]
                r_lap = item["restart_lap"]
                rem_l = item["rem_laps"]
                t_s = item["post_sc_time_s"]
                t_track = item.get("post_sc_track_s", t_s)
                t_pit = item.get("post_sc_pit_s", 0.0)
                n_pits = item.get("n_pits_post", 0)
                t_str = self._format_seconds_hh_mm_ss(t_s)

                if t_pit > 0.05:
                    pit_desc = f" + Boxes: {t_pit:.1f}s ({n_pits} parada{'s' if n_pits != 1 else ''} tras SC)"
                else:
                    pit_desc = " │ Boxes tras SC: 0.0s (Sin paradas o gratis en SC)"

                if rem_l > 0:
                    if len(post_sc_items) == 1:
                        line = (
                            f"🟡 TIEMPO TRAS SAFETY CAR (desde V{r_lap} hasta Meta V{tot_laps}, {rem_l}v):  "
                            f"⏱️ {t_str} ({t_s:.1f}s)  │  Pista: {t_track:.1f}s{pit_desc}"
                        )
                    else:
                        line = (
                            f"🟡 SC TRAMO {seg_i} (V{s_start}–V{s_end}) ➔ TIEMPO TRAS SC (desde V{r_lap} hasta Meta V{tot_laps}, {rem_l}v):  "
                            f"⏱️ {t_str} ({t_s:.1f}s)  │  Pista: {t_track:.1f}s{pit_desc}"
                        )
                else:
                    line = f"🟡 SC TRAMO {seg_i} (V{s_start}–V{s_end}): El SC finaliza en o tras la meta (0 vueltas restantes de carrera verde)."
                lines_sc.append(line)

            self._lbl_sc_post_time.configure(text="\n".join(lines_sc))
            self._sc_post_time_frame.pack(fill="x", padx=16, pady=(0, 14))
        else:
            if hasattr(self, "_sc_post_time_frame"):
                self._sc_post_time_frame.pack_forget()

    # ═══════════════════════════════════════════════════════════
    #  PERSISTENCIA CRUD Y CARGA DE ESTRATEGIAS GUARDADAS
    # ═══════════════════════════════════════════════════════════

    def _get_profile_path(self) -> Path | None:
        champ = self.session_data.get("championship_name")
        circuit = self.session_data.get("circuit")
        if not champ or not circuit:
            return None
        safe_champ = re.sub(r'[\\/*?:"<>|]', "_", champ)
        safe_circ = re.sub(r'[\\/*?:"<>|]', "_", circuit)
        return PROFILES_ROOT / safe_champ / f"{safe_circ}_strategies.json"

    def _load_saved_strategies_dict(self) -> dict:
        path = self._get_profile_path()
        if not path or not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _get_fuel_models_path(self) -> Path | None:
        champ = self.session_data.get("championship_name")
        circuit = self.session_data.get("circuit")
        if not champ or not circuit:
            return None
        safe_champ = re.sub(r'[\\/*?:"<>|]', "_", champ)
        safe_circ  = re.sub(r'[\\/*?:"<>|]', "_", circuit)
        return PROFILES_ROOT / safe_champ / f"{safe_circ}_fuel_models.json"

    def _get_tyre_models_path(self) -> Path | None:
        champ = self.session_data.get("championship_name")
        circuit = self.session_data.get("circuit")
        if not champ or not circuit:
            return None
        safe_champ = re.sub(r'[\\/*?:"<>|]', "_", champ)
        safe_circ  = re.sub(r'[\\/*?:"<>|]', "_", circuit)
        return PROFILES_ROOT / safe_champ / f"{safe_circ}_tyre_models.json"

    def _refresh_models_selectors(self):
        # 1. Combustible
        active_fuel = (self.fuel_data.get("active_model") if self.fuel_data else None) or "⭐ Modelo Base"
        fuel_models = []
        fm_path = self._get_fuel_models_path()
        if fm_path and fm_path.exists():
            try:
                data = json.loads(fm_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    fuel_models = list(data.keys())
            except Exception:
                pass
        if isinstance(self.session_data.get("fuel_models"), dict):
            for k in self.session_data["fuel_models"].keys():
                if k not in fuel_models:
                    fuel_models.append(k)
        fuel_vals = [active_fuel] + [m for m in fuel_models if m != active_fuel]
        if not fuel_vals:
            fuel_vals = ["⭐ Modelo Base"]
        if hasattr(self, "_cbo_strat_fuel"):
            self._cbo_strat_fuel.configure(values=fuel_vals)
            curr_f = self._var_strat_fuel_model.get()
            prev_active_f = getattr(self, "_last_synced_active_fuel", None)
            self._last_synced_active_fuel = active_fuel
            if (
                curr_f not in fuel_vals
                or "Modelo Activo" in curr_f
                or (prev_active_f != active_fuel and self._var_selected_strategy.get() == "⚡ Estrategia Óptima")
            ):
                self._var_strat_fuel_model.set(active_fuel)
                self._active_fuel_override = None
            else:
                self._on_strat_fuel_model_changed(curr_f, trigger_plot=False)

        # 2. Neumáticos
        active_tyre = (self.tyre_data.get("active_model") if self.tyre_data else None) or "⭐ Modelo Base"
        tyre_models = []
        tm_path = self._get_tyre_models_path()
        if tm_path and tm_path.exists():
            try:
                data = json.loads(tm_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    tyre_models = list(data.keys())
            except Exception:
                pass
        if isinstance(self.session_data.get("tyre_models"), dict):
            for k in self.session_data["tyre_models"].keys():
                if k not in tyre_models:
                    tyre_models.append(k)
        tyre_vals = [active_tyre] + [m for m in tyre_models if m != active_tyre]
        if not tyre_vals:
            tyre_vals = ["⭐ Modelo Base"]
        if hasattr(self, "_cbo_strat_tyre"):
            self._cbo_strat_tyre.configure(values=tyre_vals)
            curr_t = self._var_strat_tyre_model.get()
            prev_active_t = getattr(self, "_last_synced_active_tyre", None)
            self._last_synced_active_tyre = active_tyre
            if (
                curr_t not in tyre_vals
                or "Modelo Activo" in curr_t
                or (prev_active_t != active_tyre and self._var_selected_strategy.get() == "⚡ Estrategia Óptima")
            ):
                self._var_strat_tyre_model.set(active_tyre)
                self._active_tyre_override = None
            else:
                self._on_strat_tyre_model_changed(curr_t, trigger_plot=False)

    def _on_strat_fuel_model_changed(self, name: str, trigger_plot: bool = True):
        active_fuel = (self.fuel_data.get("active_model") if self.fuel_data else None) or "⭐ Modelo Base"
        if name == active_fuel or "Modelo Activo" in name:
            self._active_fuel_override = None
        else:
            self._active_fuel_override = None
            fm_path = self._get_fuel_models_path()
            if fm_path and fm_path.exists():
                try:
                    data = json.loads(fm_path.read_text(encoding="utf-8"))
                    self._active_fuel_override = data.get(name)
                except Exception:
                    self._active_fuel_override = None
            if self._active_fuel_override is None and isinstance(self.session_data.get("fuel_models"), dict):
                self._active_fuel_override = self.session_data["fuel_models"].get(name)
        if trigger_plot:
            self.recalculate_and_plot()

    def _on_strat_tyre_model_changed(self, name: str, trigger_plot: bool = True):
        active_tyre = (self.tyre_data.get("active_model") if self.tyre_data else None) or "⭐ Modelo Base"
        if name == active_tyre or "Modelo Activo" in name:
            self._active_tyre_override = None
        else:
            self._active_tyre_override = None
            tm_path = self._get_tyre_models_path()
            if tm_path and tm_path.exists():
                try:
                    data = json.loads(tm_path.read_text(encoding="utf-8"))
                    self._active_tyre_override = data.get(name)
                except Exception:
                    self._active_tyre_override = None
            if self._active_tyre_override is None and isinstance(self.session_data.get("tyre_models"), dict):
                self._active_tyre_override = self.session_data["tyre_models"].get(name)
        if trigger_plot:
            self.recalculate_and_plot()

    def _refresh_saved_strategies_list(self):
        self.saved_strategies = self._load_saved_strategies_dict()
        vals = ["⚡ Estrategia Óptima"] + list(self.saved_strategies.keys())
        self._cbo_saved.configure(values=vals)

    def load_optimal_strategy_action(self):
        """Calcula y aplica la estrategia óptima conservando los modelos seleccionados."""
        cfg, res = self.solve_optimal_strategy()
        if not cfg or not res:
            messagebox.showwarning("Aviso", "No se encontró una estrategia óptima viable con los datos actuales.")
            return

        self.optimal_config = cfg
        self.optimal_result = res
        self._inspected_lap = None

        self._is_updating = True
        self._var_num_stops.set("1 Parada" if cfg["num_stops"] == 1 else "2 Paradas")
        if hasattr(self, "_seg_stops"):
            self._seg_stops.set("1 Parada" if cfg["num_stops"] == 1 else "2 Paradas")
        self._var_p1.set(cfg["p1"])
        self._var_p2.set(cfg["p2"])

        # Los modelos de combustible y neumáticos seleccionados se mantienen intactos (sin resetear a Modelo Activo)

        # Usar conversión a etiquetas para asegurar que CTkOptionMenu muestre el texto correcto
        lbl_c1 = self._code_to_label(cfg["stint1_comp"])
        lbl_c2 = self._code_to_label(cfg["stint2_comp"])
        lbl_c3 = self._code_to_label(cfg["stint3_comp"])

        self._var_stint1_comp.set(lbl_c1)
        self._var_stint2_comp.set(lbl_c2)
        self._var_stint3_comp.set(lbl_c3)

        self._cbo_c1.set(lbl_c1)
        self._cbo_c2.set(lbl_c2)
        self._cbo_c3.set(lbl_c3)

        if cfg["num_stops"] == 1:
            self._s3_f.grid_remove()
            if hasattr(self, "_lbl_s2_hdr"):
                self._lbl_s2_hdr.configure(text="Stint 2 (Final)")
        else:
            self._s3_f.grid()
            if hasattr(self, "_lbl_s2_hdr"):
                self._lbl_s2_hdr.configure(text="Stint 2 (Intermedio)")

        self._var_selected_strategy.set("⚡ Estrategia Óptima")
        self._is_updating = False

        self._build_sliders_ui()
        self.recalculate_and_plot()

    def save_current_strategy_action(self):
        """Guarda la estrategia actual con un nombre en el JSON del circuito."""
        path = self._get_profile_path()
        if not path:
            messagebox.showwarning("Sin sesión", "Guarda primero un campeonato y circuito en el Módulo 1.")
            return

        dialog = ctk.CTkInputDialog(text="Nombre identificativo de la estrategia:", title="Guardar Estrategia")
        name = dialog.get_input()
        if not name or not name.strip():
            return
        name = name.strip()

        st_data = {
            "num_stops": 1 if "1" in self._var_num_stops.get() else 2,
            "p1": self._var_p1.get(),
            "p2": self._var_p2.get(),
            "fuel_model": self._var_strat_fuel_model.get(),
            "tyre_model": self._var_strat_tyre_model.get(),
            "stint1_comp": self._label_to_code(self._var_stint1_comp.get()),
            "stint2_comp": self._label_to_code(self._var_stint2_comp.get()),
            "stint3_comp": self._label_to_code(self._var_stint3_comp.get()),
            "forced_s1": self._var_forced_s1.get(),
            "forced_s2": self._var_forced_s2.get(),
            "forced_s3": self._var_forced_s3.get(),
            "forced_start_comp": self._var_forced_s1.get(),
            "sc_enabled": self._var_sc_enabled.get(),
            "sc_segments": [
                {
                    "enabled": seg["enabled"].get() if "enabled" in seg else True,
                    "lap": int(str(seg["lap"].get()).strip()) if str(seg["lap"].get()).strip().isdigit() else 8,
                    "sector": seg["sector"].get(),
                    "duration": int(str(seg["duration"].get()).strip()) if str(seg["duration"].get()).strip().isdigit() else 3,
                    "fuel_l": seg["fuel_l"].get(),
                }
                for seg in self.sc_segments
            ],
            "draft_enabled": self._var_draft_enabled.get(),
            "draft_segments": [
                {
                    "enabled": seg["enabled"].get() if "enabled" in seg else True,
                    "start": int(str(seg["start"].get()).strip()) if str(seg["start"].get()).strip().isdigit() else 5,
                    "end": int(str(seg["end"].get()).strip()) if str(seg["end"].get()).strip().isdigit() else 15,
                }
                for seg in self.draft_segments
            ],
            # Campos legacy para compatibilidad
            "sc_lap": int(str(self.sc_segments[0]["lap"].get()).strip()) if self.sc_segments and str(self.sc_segments[0]["lap"].get()).strip().isdigit() else 8,
            "sc_sector": self.sc_segments[0]["sector"].get() if self.sc_segments else "Sector 2",
            "sc_duration": int(str(self.sc_segments[0]["duration"].get()).strip()) if self.sc_segments and str(self.sc_segments[0]["duration"].get()).strip().isdigit() else 3,
            "sc_fuel_l": self.sc_segments[0]["fuel_l"].get() if self.sc_segments else "1.80",
            "draft_start": int(str(self.draft_segments[0]["start"].get()).strip()) if self.draft_segments and str(self.draft_segments[0]["start"].get()).strip().isdigit() else 5,
            "draft_end": int(str(self.draft_segments[0]["end"].get()).strip()) if self.draft_segments and str(self.draft_segments[0]["end"].get()).strip().isdigit() else 15,
            "draft_delta_l": f"{self._get_draft_saving_l():.2f}",
            "draft_delta_s": "0.00",
        }

        all_strats = self._load_saved_strategies_dict()
        all_strats[name] = st_data

        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.write_text(json.dumps(all_strats, ensure_ascii=False, indent=2), encoding="utf-8")
            self._refresh_saved_strategies_list()
            self._var_selected_strategy.set(name)
            messagebox.showinfo("Guardado", f"Estrategia '{name}' guardada exitosamente.")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar la estrategia: {e}")

    def _on_saved_strategy_selected(self, name: str):
        if name == "⚡ Estrategia Óptima":
            self.load_optimal_strategy_action()
            return
        data = self.saved_strategies.get(name)
        if not data:
            return

        self._is_updating = True
        self._inspected_lap = None

        # Restaurar modelos de combustible y neumáticos vinculados a la estrategia
        active_f = (self.fuel_data.get("active_model") if self.fuel_data else None) or "⭐ Modelo Base"
        active_t = (self.tyre_data.get("active_model") if self.tyre_data else None) or "⭐ Modelo Base"
        f_model = data.get("fuel_model", active_f)
        t_model = data.get("tyre_model", active_t)
        if "Modelo Activo" in str(f_model):
            f_model = active_f
        if "Modelo Activo" in str(t_model):
            t_model = active_t

        if hasattr(self, "_cbo_strat_fuel"):
            f_vals = list(self._cbo_strat_fuel.cget("values"))
            if f_model in f_vals:
                self._var_strat_fuel_model.set(f_model)
                self._on_strat_fuel_model_changed(f_model, trigger_plot=False)
            else:
                self._var_strat_fuel_model.set(active_f)
                self._active_fuel_override = None

        if hasattr(self, "_cbo_strat_tyre"):
            t_vals = list(self._cbo_strat_tyre.cget("values"))
            if t_model in t_vals:
                self._var_strat_tyre_model.set(t_model)
                self._on_strat_tyre_model_changed(t_model, trigger_plot=False)
            else:
                self._var_strat_tyre_model.set(active_t)
                self._active_tyre_override = None

        is_1stop = (data.get("num_stops", 1) == 1)
        self._var_num_stops.set("1 Parada" if is_1stop else "2 Paradas")
        if hasattr(self, "_seg_stops"):
            self._seg_stops.set("1 Parada" if is_1stop else "2 Paradas")
        self._var_p1.set(data.get("p1", 15))
        self._var_p2.set(data.get("p2", 25))

        lbl_c1 = self._code_to_label(data.get("stint1_comp", "hard"))
        lbl_c2 = self._code_to_label(data.get("stint2_comp", "soft"))
        lbl_c3 = self._code_to_label(data.get("stint3_comp", "hard"))

        self._var_stint1_comp.set(lbl_c1)
        self._var_stint2_comp.set(lbl_c2)
        self._var_stint3_comp.set(lbl_c3)

        self._cbo_c1.set(lbl_c1)
        self._cbo_c2.set(lbl_c2)
        self._cbo_c3.set(lbl_c3)

        # Compuestos forzados por stint (con retrocompatibilidad)
        def _norm_forced(val):
            if not val:
                return "Auto"
            v = str(val).lower()
            if "bland" in v or "alt" in v:
                return "Blando"
            if "dur" in v or "prime" in v:
                return "Duro"
            return "Auto"

        legacy_start = data.get("forced_start_comp", "Auto")
        f1 = _norm_forced(data.get("forced_s1", legacy_start))
        f2 = _norm_forced(data.get("forced_s2", "Auto"))
        f3 = _norm_forced(data.get("forced_s3", "Auto"))

        self._var_forced_s1.set(f1)
        self._var_forced_s2.set(f2)
        self._var_forced_s3.set(f3)

        if hasattr(self, "_seg_forced_s1"):
            self._seg_forced_s1.set(f1)
        if hasattr(self, "_seg_forced_s2"):
            self._seg_forced_s2.set(f2)
        if hasattr(self, "_seg_forced_s3"):
            self._seg_forced_s3.set(f3)

        # SC segments (con retrocompatibilidad)
        self._var_sc_enabled.set(data.get("sc_enabled", False))
        if "sc_segments" in data and isinstance(data["sc_segments"], list) and data["sc_segments"]:
            self.sc_segments.clear()
            for seg_d in data["sc_segments"]:
                self.sc_segments.append({
                    "enabled": ctk.BooleanVar(value=seg_d.get("enabled", True)),
                    "lap": ctk.StringVar(value=str(seg_d.get("lap", 8))),
                    "sector": ctk.StringVar(value=seg_d.get("sector", "Sector 2")),
                    "duration": ctk.StringVar(value=str(seg_d.get("duration", 3))),
                    "fuel_l": ctk.StringVar(value=str(seg_d.get("fuel_l", "1.80"))),
                })
        else:
            self.sc_segments = [{
                "enabled": ctk.BooleanVar(value=data.get("sc_enabled", False)),
                "lap": ctk.StringVar(value=str(data.get("sc_lap", 8))),
                "sector": ctk.StringVar(value=data.get("sc_sector", "Sector 2")),
                "duration": ctk.StringVar(value=str(data.get("sc_duration", 3))),
                "fuel_l": ctk.StringVar(value=str(data.get("sc_fuel_l", "1.80"))),
            }]
        self._render_sc_segments()

        # Draft segments (con retrocompatibilidad)
        self._var_draft_enabled.set(data.get("draft_enabled", False))
        if "draft_segments" in data and isinstance(data["draft_segments"], list) and data["draft_segments"]:
            self.draft_segments.clear()
            for seg_d in data["draft_segments"]:
                self.draft_segments.append({
                    "enabled": ctk.BooleanVar(value=seg_d.get("enabled", True)),
                    "start": ctk.StringVar(value=str(seg_d.get("start", 5))),
                    "end": ctk.StringVar(value=str(seg_d.get("end", 15))),
                })
        else:
            self.draft_segments = [{
                "enabled": ctk.BooleanVar(value=data.get("draft_enabled", False)),
                "start": ctk.StringVar(value=str(data.get("draft_start", 5))),
                "end": ctk.StringVar(value=str(data.get("draft_end", 15))),
            }]
        self._render_draft_segments()

        if is_1stop:
            self._s3_f.grid_remove()
            if hasattr(self, "_lbl_s2_hdr"):
                self._lbl_s2_hdr.configure(text="Stint 2 (Final)")
        else:
            self._s3_f.grid()
            if hasattr(self, "_lbl_s2_hdr"):
                self._lbl_s2_hdr.configure(text="Stint 2 (Intermedio)")

        self._is_updating = False
        self._build_sliders_ui()
        self.recalculate_and_plot()

    def delete_current_strategy_action(self):
        name = self._var_selected_strategy.get()
        if name == "⚡ Estrategia Óptima":
            messagebox.showinfo("Información", "La Estrategia Óptima es nativa y no se puede borrar.")
            return
        path = self._get_profile_path()
        if not path or not path.exists():
            return

        all_strats = self._load_saved_strategies_dict()
        if name in all_strats:
            del all_strats[name]
            path.write_text(json.dumps(all_strats, ensure_ascii=False, indent=2), encoding="utf-8")
            self._refresh_saved_strategies_list()
            self.load_optimal_strategy_action()
            messagebox.showinfo("Borrado", f"Estrategia '{name}' eliminada.")

    # ═══════════════════════════════════════════════════════════
    #  CONEXIONES CON EL ORQUESTADOR CENTRAL (MAIN.PY)
    # ═══════════════════════════════════════════════════════════

    def on_session_data_updated(self, session_data: dict):
        """Inyecta datos de sesión de campeonato y circuito."""
        if not session_data:
            return
        self.session_data = session_data

        circ = session_data.get("circuit", "Circuito")
        base_lap_s = float(session_data.get("lap_time_seconds", 84.5))

        self._lbl_sync_info.configure(
            text=f"🔗  Sincronizado con Circuito: {circ} · Vuelta Base: {self._format_seconds(base_lap_s)}"
        )
        self._refresh_saved_strategies_list()
        self._refresh_models_selectors()

    def on_fuel_strategy_updated(self, fuel_data: dict):
        """Inyecta datos calculados de combustible y viabilidad de paradas."""
        if not fuel_data:
            return
        self.fuel_data = fuel_data
        self._refresh_models_selectors()

        viable_modes = fuel_data.get("viable_modes", ["1 Parada", "2 Paradas"])
        if hasattr(self, "_seg_stops"):
            self._seg_stops.configure(values=viable_modes)

        # Si el modo actual no es viable, ajustar al primero viable
        if self._var_num_stops.get() not in viable_modes:
            self._var_num_stops.set(viable_modes[0])

        # Se programa recálculo con debounce para evitar doble renderizado simultáneo con neumáticos
        self._schedule_recalculate_and_plot()

    def on_tyre_strategy_updated(self, tyre_data: dict):
        """Inyecta datos de ritmo y degradación OLS de neumáticos."""
        if not tyre_data:
            return
        self.tyre_data = tyre_data
        self._refresh_models_selectors()

        # Con todos los módulos sincronizados, resolver y cargar la estrategia óptima solo si no hay una estrategia guardada activa
        if self._var_selected_strategy.get() == "⚡ Estrategia Óptima":
            self.load_optimal_strategy_action()
        else:
            self.recalculate_and_plot()

    # ─── Formateadores de Tiempo ──────────────────────────────
    @staticmethod
    def _format_seconds(seconds: float) -> str:
        if seconds <= 0:
            return "00:00.000"
        m = int(seconds // 60)
        s = seconds % 60
        return f"{m:02d}:{s:06.3f}"

    @staticmethod
    def _format_seconds_hh_mm_ss(seconds: float) -> str:
        if seconds <= 0:
            return "00:00:00.000"
        h = int(seconds // 3600)
        rem = seconds % 3600
        m = int(rem // 60)
        s = rem % 60
        if h > 0:
            return f"{h:02d}h {m:02d}m {s:06.3f}s"
        return f"{m:02d}m {s:06.3f}s"
