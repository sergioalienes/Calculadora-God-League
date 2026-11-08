"""
============================================================
 MÓDULO 3: Estrategia de Neumáticos — NIX Esports (v3.2)
============================================================
 Arquitectura & Física de Carrera:
   - Ritmo Base Directo en Vuelta 1 para cada compuesto:
       * Rueda Dura (Prime): ej. 01:24.500
       * Rueda Blanda (Alternative): ej. 01:24.050
   - Función a Tramos Estricta con indexación de vida de goma (x):
       * x = 0 (Vuelta de salida / gomas frías):
           Tiempo = Ritmo Base Vuelta 1 + Pérdida por Calentar Rueda
       * x = 1 (Vuelta en temperatura óptima de trabajo):
           Tiempo = Ritmo Base Vuelta 1  (Δdeg = 0.000s forzado)
       * x >= 2 (Degradación logarítmica según vida de la goma):
           Tiempo = Ritmo Base Vuelta 1 + a·ln(x) + n
   - Pérdida por calentar rueda configurable independientemente:
       * Rueda Dura: ej. +0.800s (mayor inercia térmica)
       * Rueda Blanda: ej. +0.400s (calentamiento más rápido)
   - Ajuste por Regresión Lineal OLS sobre u = ln(x) para
     maximizar matemáticamente el coeficiente de determinación R².
   - Sliders de boxes estrictamente acotados al rango viable
     de combustible (-20% límite de ahorro).
   - Tiempo de boxes variable y dinámico según la carga de litros
     real calculada para el stint: pitlane + max(fuel / rate, tyre_change).
   - Efecto peso del combustible en pista modelado vuelta a vuelta:
       Δt_peso(litros) = (Litros_actuales - Reserva) * Sensibilidad_peso
   - Gráfico Matplotlib embebido en CustomTkinter:
       * Eje X: Número de vuelta (1 ... N)
       * Eje Y: Tiempo por vuelta (formato MM:SS.ms)
       * Área coloreada por compuesto:
           ⚪ Blanco semitransparente: Rueda Dura (Prime)
           🔴 Rojo semitransparente: Rueda Blanda (Alternative)
       * Indicadores visuales en vueltas de parada con litros y tiempo exacto.
   - Persistencia automática: profiles/<champ>/<circuito>_tyres.json
============================================================
"""

import customtkinter as ctk
import numpy as np
import math
import json
import re
import sys
from pathlib import Path
from tkinter import messagebox

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.ticker as ticker

APP_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
PROFILES_ROOT = APP_ROOT / "profiles"


class TyreStrategyModule(ctk.CTkFrame):
    """
    Módulo 3 — Estrategia de Neumáticos y Simulación de Carrera.
    Modelado a tramos (x=0 calentamiento, x=1 delta cero, x>=2 logarítmico OLS),
    sliders con filtro estricto de viabilidad de combustible, boxes dinámicos
    por repostaje y visualización gráfica avanzada.
    """

    def __init__(self, parent, colors: dict, **kwargs):
        super().__init__(parent, fg_color=colors["bg_primary"], **kwargs)
        self.colors = colors
        self.session_data: dict = {}
        self.fuel_data: dict = {}

        # ── Puntos de test por defecto para regresión OLS (x >= 2) ──
        # Rueda Dura (Prime): Degradación contenida
        self.hard_test_points: list[dict] = [
            {"lap": 2,  "delta": 0.08},
            {"lap": 6,  "delta": 0.22},
            {"lap": 12, "delta": 0.38},
            {"lap": 18, "delta": 0.52},
            {"lap": 24, "delta": 0.65},
        ]

        # Rueda Blanda (Alternative): Mayor ritmo pico inicial pero mayor degradación
        self.soft_test_points: list[dict] = [
            {"lap": 2,  "delta": 0.12},
            {"lap": 5,  "delta": 0.32},
            {"lap": 9,  "delta": 0.58},
            {"lap": 14, "delta": 0.95},
            {"lap": 18, "delta": 1.38},
        ]

        # ── Parámetros del modelo por compuesto ───────────────────
        # Rueda Dura
        self._var_hard_base_lap = ctk.StringVar(value="01:24.500") # Ritmo base Vuelta 1
        self._var_hard_warmup   = ctk.StringVar(value="0.800")    # Pérdida calentar rueda en x=0 (s)
        self._var_hard_a        = ctk.StringVar(value="0.2223")   # Pendiente logarítmica
        self._var_hard_n        = ctk.StringVar(value="-0.1208")  # Constante
        self._var_hard_r2       = ctk.StringVar(value="0.9408")   # R²

        # Rueda Blanda
        self._var_soft_base_lap = ctk.StringVar(value="01:24.050") # Ritmo base Vuelta 1
        self._var_soft_warmup   = ctk.StringVar(value="0.400")    # Pérdida calentar rueda en x=0 (s)
        self._var_soft_a        = ctk.StringVar(value="0.5318")   # Pendiente logarítmica
        self._var_soft_n        = ctk.StringVar(value="-0.3968")  # Constante
        self._var_soft_r2       = ctk.StringVar(value="0.8634")   # R²

        # ── Asignación de compuestos por stint ────────────────────
        self._var_stint1_tyre = ctk.StringVar(value="soft")  # "soft" o "hard"
        self._var_stint2_tyre = ctk.StringVar(value="hard")
        self._var_stint3_tyre = ctk.StringVar(value="hard")

        # ── Modelos de neumáticos por circuito ────────────────────
        self.saved_tyre_models: dict = {}
        self._var_selected_tyre_model = ctk.StringVar(value="⚡ Modelo Base")

        # ── Paradas sincronizadas ─────────────────────────────────
        self._var_num_stops  = ctk.IntVar(value=1)
        self._var_pit1_lap   = ctk.IntVar(value=22)
        self._var_pit2_lap   = ctk.IntVar(value=34)
        self._var_total_laps = ctk.IntVar(value=43)

        # Matplotlib canvas reference
        self._fig = None
        self._ax = None
        self._mpl_canvas = None
        self._plot_job = None
        self._s1_slider_bounds = None
        self._s2_slider_bounds = None

        self._build_ui()

        # Ajuste inicial de regresión OLS
        self.fit_regression("hard", update_ui=False)
        self.fit_regression("soft", update_ui=False)
        self.recalculate_and_plot()

    # ═══════════════════════════════════════════════════════════
    #  CONSTRUCCIÓN DE LA INTERFAZ
    # ═══════════════════════════════════════════════════════════

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_scroll()

    def _build_header(self):
        header = ctk.CTkFrame(
            self,
            fg_color=self.colors["bg_secondary"],
            corner_radius=0,
            border_width=1,
            border_color=self.colors["border"],
        )
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkFrame(header, width=4, height=44, fg_color="#FF3B30").grid(
            row=0, column=0, sticky="nsw", padx=(0, 16)
        )

        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.grid(row=0, column=1, sticky="w", pady=10)

        ctk.CTkLabel(
            title_box,
            text="ESTRATEGIA DE NEUMÁTICOS",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=self.colors["text_primary"],
        ).pack(anchor="w")

        ctk.CTkLabel(
            title_box,
            text="Modelado logarítmico a tramos (x=0 salida, x=1 delta cero, x≥2 degradación) y telemetría de carrera",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=self.colors["text_secondary"],
        ).pack(anchor="w")

        # Botones de Acción y Selector de Modelo de Neumáticos
        btn_box = ctk.CTkFrame(header, fg_color="transparent")
        btn_box.grid(row=0, column=2, padx=16, pady=10, sticky="e")

        self._cbo_tyre_models = ctk.CTkComboBox(
            btn_box,
            variable=self._var_selected_tyre_model,
            values=["⚡ Modelo Base"],
            width=180,
            height=34,
            corner_radius=8,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color=self.colors["bg_primary"],
            border_color=self.colors["border"],
            button_color=self.colors["border"],
            button_hover_color=self.colors["accent"],
            dropdown_fg_color=self.colors["bg_secondary"],
            dropdown_text_color=self.colors["text_primary"],
            command=self._on_tyre_model_selected,
        )
        self._cbo_tyre_models.pack(side="left", padx=(0, 8))

        self._btn_save_tyres = ctk.CTkButton(
            btn_box,
            text="💾  Guardar",
            width=90,
            height=34,
            corner_radius=8,
            fg_color=self.colors["accent"],
            hover_color=self.colors["accent_hover"],
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=self.save_tyre_profile,
        )
        self._btn_save_tyres.pack(side="left", padx=(0, 6))

        self._btn_reload_tyres = ctk.CTkButton(
            btn_box,
            text="🔄  Recargar",
            width=90,
            height=34,
            corner_radius=8,
            fg_color=self.colors["bg_primary"],
            hover_color=self.colors["border"],
            border_width=1,
            border_color=self.colors["border"],
            text_color=self.colors["text_primary"],
            font=ctk.CTkFont(family="Segoe UI", size=12),
            command=self.reload_tyre_profile,
        )
        self._btn_reload_tyres.pack(side="left", padx=(0, 6))

        self._btn_delete_tyres = ctk.CTkButton(
            btn_box,
            text="🗑️  Borrar",
            width=80,
            height=34,
            corner_radius=8,
            fg_color="#2A1010",
            hover_color="#5A1515",
            border_width=1,
            border_color="#FF453A",
            text_color="#FF6B6B",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=self.delete_tyre_profile,
        )
        self._btn_delete_tyres.pack(side="left")

    def _build_scroll(self):
        self._scroll = ctk.CTkScrollableFrame(
            self,
            fg_color=self.colors["bg_primary"],
            scrollbar_button_color=self.colors["border"],
            scrollbar_button_hover_color=self.colors["accent_dim"],
        )
        self._scroll.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        self._scroll.grid_columnconfigure(0, weight=1)

        # 1. Banner de Sincronización con Combustible y Sesión
        self._build_sync_banner()

        # 2. Modelado de Neumáticos (Ritmo Base Vuelta 1, Calentamiento y Regresión OLS)
        self._build_regression_section()

        # 3. Control de Paradas Acotadas al Rango Viable y Asignación de Compuestos
        self._build_stints_and_tyres_section()

        # 4. Métricas de Telemetría & Gráfico Matplotlib
        self._build_chart_section()

        ctk.CTkFrame(self._scroll, height=30, fg_color="transparent").pack()

    # ─── 1. Banner de Sincronización ──────────────────────────
    def _build_sync_banner(self):
        self._sync_banner = ctk.CTkFrame(
            self._scroll,
            fg_color=self.colors["bg_secondary"],
            corner_radius=10,
            border_width=1,
            border_color=self.colors["border"],
        )
        self._sync_banner.pack(fill="x", padx=32, pady=(16, 12))
        self._sync_banner.grid_columnconfigure(0, weight=1)

        self._lbl_sync_info = ctk.CTkLabel(
            self._sync_banner,
            text="🔗  Sincronizado con Módulo 2 (Combustible) · Vueltas: 43 · Paradas: 1 (V22) · Rango Viable Combustible: V19 ➔ V26",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=self.colors["accent"],
            anchor="w",
        )
        self._lbl_sync_info.pack(fill="x", padx=16, pady=10)

    # ─── 2. Modelado de Neumáticos (Tablas de Regresión) ──────
    def _build_regression_section(self):
        reg_wrapper = ctk.CTkFrame(self._scroll, fg_color="transparent")
        reg_wrapper.pack(fill="x", padx=32, pady=(0, 16))
        reg_wrapper.grid_columnconfigure((0, 1), weight=1)

        # ── CARD IZQUIERDA: RUEDA DURA (PRIME) ────────────────
        self._hard_card = ctk.CTkFrame(
            reg_wrapper,
            fg_color=self.colors["bg_secondary"],
            corner_radius=10,
            border_width=1,
            border_color="#CCCCCC",
        )
        self._hard_card.grid(row=0, column=0, padx=(0, 8), sticky="nsew")
        self._hard_card.grid_columnconfigure(0, weight=1)
        self._build_compound_panel(self._hard_card, compound="hard")

        # ── CARD DERECHA: RUEDA BLANDA (ALTERNATIVE) ──────────
        self._soft_card = ctk.CTkFrame(
            reg_wrapper,
            fg_color=self.colors["bg_secondary"],
            corner_radius=10,
            border_width=1,
            border_color="#FF453A",
        )
        self._soft_card.grid(row=0, column=1, padx=(8, 0), sticky="nsew")
        self._soft_card.grid_columnconfigure(0, weight=1)
        self._build_compound_panel(self._soft_card, compound="soft")

    def _build_compound_panel(self, parent: ctk.CTkFrame, compound: str):
        is_hard = (compound == "hard")
        title_text = "⚪  RUEDA DURA (Prime)" if is_hard else "🔴  RUEDA BLANDA (Alternative)"
        accent_color = "#E0E0E0" if is_hard else "#FF453A"

        # Header del panel
        p_hdr = ctk.CTkFrame(parent, fg_color="transparent")
        p_hdr.pack(fill="x", padx=16, pady=(14, 8))

        ctk.CTkLabel(
            p_hdr,
            text=title_text,
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color=accent_color,
        ).pack(side="left")

        # Configuración de Ritmo Base Vuelta 1 y Pérdida por Calentar Rueda
        inputs_bar = ctk.CTkFrame(parent, fg_color=self.colors["bg_primary"], corner_radius=8, border_width=1, border_color=self.colors["border"])
        inputs_bar.pack(fill="x", padx=16, pady=(0, 8))
        inputs_bar.grid_columnconfigure((0, 1), weight=1)

        var_base = self._var_hard_base_lap if is_hard else self._var_soft_base_lap
        var_warmup = self._var_hard_warmup if is_hard else self._var_soft_warmup

        # Input 1: Ritmo Base (con 70L lleno, x=1)
        f_b = ctk.CTkFrame(inputs_bar, fg_color="transparent")
        f_b.grid(row=0, column=0, padx=10, pady=8, sticky="w")
        ctk.CTkLabel(f_b, text="⏱️ Ritmo Base (70L lleno, x=1):", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color=self.colors["text_primary"]).pack(anchor="w")
        e_base = ctk.CTkEntry(
            f_b, textvariable=var_base, width=115, height=32,
            font=ctk.CTkFont(family="Segoe UI Mono", size=12, weight="bold"),
            fg_color=self.colors["input_bg"], border_color=self.colors["border"]
        )
        e_base.pack(anchor="w", pady=(3, 0))
        e_base.bind("<FocusOut>", lambda ev: self.recalculate_and_plot())

        # Input 2: Pérdida Calentar Rueda (x=0)
        f_w = ctk.CTkFrame(inputs_bar, fg_color="transparent")
        f_w.grid(row=0, column=1, padx=10, pady=8, sticky="w")
        ctk.CTkLabel(f_w, text="🔥 Pérdida Calentar (x=0):", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color=self.colors["text_primary"]).pack(anchor="w")
        e_warm = ctk.CTkEntry(
            f_w, textvariable=var_warmup, width=100, height=32,
            font=ctk.CTkFont(family="Segoe UI Mono", size=12, weight="bold"),
            fg_color=self.colors["input_bg"], border_color=self.colors["border"]
        )
        e_warm.pack(anchor="w", pady=(3, 0))
        e_warm.bind("<FocusOut>", lambda ev: self.recalculate_and_plot())

        # Explicación de la función a tramos
        expl_lbl = ctk.CTkLabel(
            parent,
            text="Fórmula a tramos: x=0 ➔ Base + Calentar | x=1 ➔ Base (Δ=0) | x≥2 ➔ Base + a·ln(x) + n",
            font=ctk.CTkFont(family="Segoe UI", size=10, slant="italic"),
            text_color=self.colors["text_secondary"],
            anchor="w",
        )
        expl_lbl.pack(fill="x", padx=16, pady=(0, 6))

        # Contenedor de la tabla de puntos para regresión OLS
        table_container = ctk.CTkFrame(parent, fg_color=self.colors["bg_primary"], corner_radius=8, border_width=1, border_color=self.colors["border"])
        table_container.pack(fill="x", padx=16, pady=(0, 8))
        table_container.grid_columnconfigure((0, 1, 2), weight=1)

        if is_hard:
            self._hard_table_box = table_container
        else:
            self._soft_table_box = table_container

        # Header de la tabla
        for col_idx, text in enumerate(["Vuelta Test (x ≥ 2)", "Δ Deg vs V1 (s)", "Acción"]):
            ctk.CTkLabel(
                table_container,
                text=text,
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                text_color=self.colors["text_secondary"],
            ).grid(row=0, column=col_idx, padx=6, pady=4, sticky="w" if col_idx < 2 else "e")

        self._render_test_points(compound)

        # Barra de botones (+ punto y Ajustar OLS)
        btn_bar = ctk.CTkFrame(parent, fg_color="transparent")
        btn_bar.pack(fill="x", padx=16, pady=(0, 10))

        ctk.CTkButton(
            btn_bar,
            text="+ Añadir Vuelta Test",
            width=120,
            height=28,
            corner_radius=6,
            fg_color=self.colors["bg_primary"],
            hover_color=self.colors["border"],
            font=ctk.CTkFont(family="Segoe UI", size=11),
            command=lambda c=compound: self._add_test_point(c),
        ).pack(side="left")

        ctk.CTkButton(
            btn_bar,
            text="⚡ Ajustar Regresión OLS",
            width=160,
            height=28,
            corner_radius=6,
            fg_color=accent_color if is_hard else "#D92D20",
            text_color="#111111" if is_hard else "#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            command=lambda c=compound: self.fit_regression(c),
        ).pack(side="right")

        # Card de Resultados de la Regresión (a, n, R²)
        res_card = ctk.CTkFrame(parent, fg_color=self.colors["sidebar_bg"], corner_radius=8, border_width=1, border_color=self.colors["border"])
        res_card.pack(fill="x", padx=16, pady=(0, 14))
        res_card.grid_columnconfigure((0, 1, 2), weight=1)

        var_a = self._var_hard_a if is_hard else self._var_soft_a
        var_n = self._var_hard_n if is_hard else self._var_soft_n
        var_r2 = self._var_hard_r2 if is_hard else self._var_soft_r2

        # Param a
        c_a = ctk.CTkFrame(res_card, fg_color="transparent")
        c_a.grid(row=0, column=0, padx=8, pady=8, sticky="w")
        ctk.CTkLabel(c_a, text="Pendiente a:", font=ctk.CTkFont(family="Segoe UI", size=10), text_color=self.colors["text_secondary"]).pack(anchor="w")
        e_a = ctk.CTkEntry(c_a, textvariable=var_a, width=90, height=30, font=ctk.CTkFont(family="Segoe UI Mono", size=11, weight="bold"))
        e_a.pack(anchor="w", pady=(2, 0))
        e_a.bind("<FocusOut>", lambda ev: self.recalculate_and_plot())

        # Param n
        c_n = ctk.CTkFrame(res_card, fg_color="transparent")
        c_n.grid(row=0, column=1, padx=8, pady=8, sticky="w")
        ctk.CTkLabel(c_n, text="Constante n:", font=ctk.CTkFont(family="Segoe UI", size=10), text_color=self.colors["text_secondary"]).pack(anchor="w")
        e_n = ctk.CTkEntry(c_n, textvariable=var_n, width=90, height=30, font=ctk.CTkFont(family="Segoe UI Mono", size=11, weight="bold"))
        e_n.pack(anchor="w", pady=(2, 0))
        e_n.bind("<FocusOut>", lambda ev: self.recalculate_and_plot())

        # R²
        c_r2 = ctk.CTkFrame(res_card, fg_color="transparent")
        c_r2.grid(row=0, column=2, padx=8, pady=8, sticky="w")
        ctk.CTkLabel(c_r2, text="Bondad de Ajuste R²:", font=ctk.CTkFont(family="Segoe UI", size=10), text_color=self.colors["text_secondary"]).pack(anchor="w")
        lbl_r2 = ctk.CTkLabel(
            c_r2,
            textvariable=var_r2,
            font=ctk.CTkFont(family="Segoe UI Mono", size=13, weight="bold"),
            text_color="#51CF66",
        )
        lbl_r2.pack(anchor="w", pady=(2, 0))
        if is_hard:
            self._lbl_hard_r2 = lbl_r2
        else:
            self._lbl_soft_r2 = lbl_r2

    def _render_test_points(self, compound: str):
        is_hard = (compound == "hard")
        container = self._hard_table_box if is_hard else self._soft_table_box
        points = self.hard_test_points if is_hard else self.soft_test_points

        for w in container.winfo_children():
            info = w.grid_info()
            if info and int(info.get("row", 0)) > 0:
                w.destroy()

        for idx, pt in enumerate(points):
            row_idx = idx + 1

            vx = ctk.StringVar(value=str(pt["lap"]))
            ex = ctk.CTkEntry(
                container, textvariable=vx, width=75, height=30,
                font=ctk.CTkFont(family="Segoe UI Mono", size=11, weight="bold"),
                justify="center",
                fg_color=self.colors["input_bg"], border_color=self.colors["border"]
            )
            ex.grid(row=row_idx, column=0, padx=6, pady=3, sticky="w")
            ex.bind("<FocusOut>", lambda ev, i=idx, var=vx, c=compound: self._on_pt_edited(c, i, "lap", var.get()))

            vd = ctk.StringVar(value=f"{pt['delta']:.3f}")
            ed = ctk.CTkEntry(
                container, textvariable=vd, width=85, height=30,
                font=ctk.CTkFont(family="Segoe UI Mono", size=11, weight="bold"),
                justify="center",
                fg_color=self.colors["input_bg"], border_color=self.colors["border"]
            )
            ed.grid(row=row_idx, column=1, padx=6, pady=3, sticky="w")
            ed.bind("<FocusOut>", lambda ev, i=idx, var=vd, c=compound: self._on_pt_edited(c, i, "delta", var.get()))

            ctk.CTkButton(
                container,
                text="✕",
                width=28,
                height=28,
                corner_radius=6,
                fg_color="#331111",
                hover_color="#551111",
                text_color="#FF6B6B",
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                command=lambda i=idx, c=compound: self._delete_test_point(c, i),
            ).grid(row=row_idx, column=2, padx=6, pady=3, sticky="e")

    def _on_pt_edited(self, compound: str, idx: int, field: str, value: str):
        points = self.hard_test_points if compound == "hard" else self.soft_test_points
        if idx >= len(points):
            return
        try:
            val = float(value.replace(",", "."))
            if field == "lap":
                points[idx]["lap"] = max(2, int(val))
            else:
                points[idx]["delta"] = val
        except ValueError:
            pass

    def _add_test_point(self, compound: str):
        points = self.hard_test_points if compound == "hard" else self.soft_test_points
        if points:
            last_lap = points[-1]["lap"]
            last_delta = points[-1]["delta"]
            points.append({"lap": last_lap + 4, "delta": round(last_delta + 0.15, 3)})
        else:
            points.append({"lap": 4, "delta": 0.18})
        self._render_test_points(compound)

    def _delete_test_point(self, compound: str, idx: int):
        points = self.hard_test_points if compound == "hard" else self.soft_test_points
        if 0 <= idx < len(points):
            points.pop(idx)
            self._render_test_points(compound)

    def fit_regression(self, compound: str, update_ui: bool = True):
        """
        Calcula a y n mediante Mínimos Cuadrados Ordinarios (OLS) sobre u = ln(x)
        para x >= 2, garantizando el máximo R² matemáticamente posible.
        """
        points = self.hard_test_points if compound == "hard" else self.soft_test_points
        valid = [(pt["lap"], pt["delta"]) for pt in points if pt["lap"] >= 2]

        if len(valid) < 2:
            if update_ui:
                messagebox.showwarning("Puntos Insuficientes", "Se necesitan al menos 2 puntos con vuelta x ≥ 2 para ajustar la regresión.")
            return

        x_vals = np.array([float(p[0]) for p in valid])
        y_vals = np.array([float(p[1]) for p in valid])
        u_vals = np.log(x_vals)

        a, n = np.polyfit(u_vals, y_vals, 1)

        y_pred = a * u_vals + n
        ss_res = float(np.sum((y_vals - y_pred) ** 2))
        ss_tot = float(np.sum((y_vals - np.mean(y_vals)) ** 2))
        r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 1.0
        r2 = max(0.0, min(1.0, r2))

        if compound == "hard":
            self._var_hard_a.set(f"{a:.4f}")
            self._var_hard_n.set(f"{n:.4f}")
            self._var_hard_r2.set(f"{r2:.4f}")
            if hasattr(self, "_lbl_hard_r2"):
                color = "#51CF66" if r2 >= 0.90 else ("#FFA94D" if r2 >= 0.70 else "#FF6B6B")
                self._lbl_hard_r2.configure(text_color=color)
        else:
            self._var_soft_a.set(f"{a:.4f}")
            self._var_soft_n.set(f"{n:.4f}")
            self._var_soft_r2.set(f"{r2:.4f}")
            if hasattr(self, "_lbl_soft_r2"):
                color = "#51CF66" if r2 >= 0.90 else ("#FFA94D" if r2 >= 0.70 else "#FF6B6B")
                self._lbl_soft_r2.configure(text_color=color)

        if update_ui:
            self.recalculate_and_plot()

    # ─── 3. Control de Paradas y Asignación de Compuestos ─────
    def _build_stints_and_tyres_section(self):
        self._stints_card = ctk.CTkFrame(
            self._scroll,
            fg_color=self.colors["bg_secondary"],
            corner_radius=10,
            border_width=1,
            border_color=self.colors["border"],
        )
        self._stints_card.pack(fill="x", padx=32, pady=(0, 16))
        self._stints_card.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(self._stints_card, fg_color="transparent")
        hdr.pack(fill="x", padx=20, pady=(14, 8))

        ctk.CTkLabel(
            hdr,
            text="🏁  Asignación de Compuestos por Stint y Control de Paradas Viables",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color=self.colors["text_primary"],
        ).pack(side="left")

        seg_box = ctk.CTkFrame(hdr, fg_color="transparent")
        seg_box.pack(side="right")
        ctk.CTkLabel(seg_box, text="Paradas:", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color=self.colors["text_secondary"]).pack(side="left", padx=(0, 6))
        self._seg_stops = ctk.CTkSegmentedButton(
            seg_box,
            values=["1 Parada", "2 Paradas"],
            command=self._on_stops_mode_changed,
            selected_color=self.colors["accent"],
            selected_hover_color=self.colors["accent_hover"],
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
        )
        self._seg_stops.set("1 Parada")
        self._seg_stops.pack(side="left")

        # Slider Parada 1 (acotado al rango viable)
        self._s1_box = ctk.CTkFrame(self._stints_card, fg_color=self.colors["bg_primary"], corner_radius=8, border_width=1, border_color=self.colors["border"])
        self._s1_box.pack(fill="x", padx=20, pady=(0, 6))
        self._s1_box.grid_columnconfigure(1, weight=1)

        self._lbl_s1_title = ctk.CTkLabel(self._s1_box, text="🛑 Parada 1 (Vuelta):", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color=self.colors["accent"])
        self._lbl_s1_title.grid(row=0, column=0, padx=12, pady=6, sticky="w")

        self._slider_p1 = ctk.CTkSlider(
            self._s1_box, from_=10, to=30, number_of_steps=20, variable=self._var_pit1_lap,
            button_color=self.colors["accent"], progress_color=self.colors["accent_dim"],
            command=self._on_p1_slider_event,
        )
        self._slider_p1.grid(row=0, column=1, padx=10, pady=6, sticky="ew")

        self._lbl_s1_val = ctk.CTkLabel(self._s1_box, text=f"V{self._var_pit1_lap.get()}", font=ctk.CTkFont(family="Segoe UI Mono", size=13, weight="bold"), text_color=self.colors["accent"], width=45)
        self._lbl_s1_val.grid(row=0, column=2, padx=12, pady=6, sticky="w")

        # Slider Parada 2
        self._s2_box = ctk.CTkFrame(self._stints_card, fg_color=self.colors["bg_primary"], corner_radius=8, border_width=1, border_color=self.colors["border"])
        self._s2_box.grid_columnconfigure(1, weight=1)

        self._lbl_s2_title = ctk.CTkLabel(self._s2_box, text="🛑 Parada 2 (Vuelta):", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color=self.colors["accent"])
        self._lbl_s2_title.grid(row=0, column=0, padx=12, pady=6, sticky="w")

        self._slider_p2 = ctk.CTkSlider(
            self._s2_box, from_=20, to=38, number_of_steps=18, variable=self._var_pit2_lap,
            button_color=self.colors["accent"], progress_color=self.colors["accent_dim"],
            command=self._on_p2_slider_event,
        )
        self._slider_p2.grid(row=0, column=1, padx=10, pady=6, sticky="ew")

        self._lbl_s2_val = ctk.CTkLabel(self._s2_box, text=f"V{self._var_pit2_lap.get()}", font=ctk.CTkFont(family="Segoe UI Mono", size=13, weight="bold"), text_color=self.colors["accent"], width=45)
        self._lbl_s2_val.grid(row=0, column=2, padx=12, pady=6, sticky="w")

        # Selectores de compuesto por Stint
        self._stints_selector_grid = ctk.CTkFrame(self._stints_card, fg_color="transparent")
        self._stints_selector_grid.pack(fill="x", padx=20, pady=(6, 10))
        self._stints_selector_grid.grid_columnconfigure((0, 1, 2), weight=1)

        # Stint 1
        self._c_st1 = ctk.CTkFrame(self._stints_selector_grid, fg_color=self.colors["bg_primary"], corner_radius=8, border_width=1, border_color=self.colors["border"])
        self._c_st1.grid(row=0, column=0, padx=4, sticky="nsew")
        self._lbl_st1_title = ctk.CTkLabel(self._c_st1, text="STINT 1 (V1 ➔ V22)", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color=self.colors["text_primary"])
        self._lbl_st1_title.pack(anchor="w", padx=10, pady=(8, 4))
        self._seg_st1 = ctk.CTkSegmentedButton(self._c_st1, values=["⚪ Dura", "🔴 Blanda"], command=lambda v: self._on_stint_compound_changed(1, v), font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"))
        self._seg_st1.set("🔴 Blanda")
        self._seg_st1.pack(fill="x", padx=10, pady=(0, 8))

        # Stint 2
        self._c_st2 = ctk.CTkFrame(self._stints_selector_grid, fg_color=self.colors["bg_primary"], corner_radius=8, border_width=1, border_color=self.colors["border"])
        self._c_st2.grid(row=0, column=1, padx=4, sticky="nsew")
        self._lbl_st2_title = ctk.CTkLabel(self._c_st2, text="STINT 2 (V23 ➔ Meta)", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color=self.colors["text_primary"])
        self._lbl_st2_title.pack(anchor="w", padx=10, pady=(8, 4))
        self._seg_st2 = ctk.CTkSegmentedButton(self._c_st2, values=["⚪ Dura", "🔴 Blanda"], command=lambda v: self._on_stint_compound_changed(2, v), font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"))
        self._seg_st2.set("⚪ Dura")
        self._seg_st2.pack(fill="x", padx=10, pady=(0, 8))

        # Stint 3 (para 2 paradas)
        self._c_st3 = ctk.CTkFrame(self._stints_selector_grid, fg_color=self.colors["bg_primary"], corner_radius=8, border_width=1, border_color=self.colors["border"])
        self._c_st3.grid(row=0, column=2, padx=4, sticky="nsew")
        self._lbl_st3_title = ctk.CTkLabel(self._c_st3, text="STINT 3 (V35 ➔ Meta)", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color=self.colors["text_primary"])
        self._lbl_st3_title.pack(anchor="w", padx=10, pady=(8, 4))
        self._seg_st3 = ctk.CTkSegmentedButton(self._c_st3, values=["⚪ Dura", "🔴 Blanda"], command=lambda v: self._on_stint_compound_changed(3, v), font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"))
        self._seg_st3.set("⚪ Dura")
        self._seg_st3.pack(fill="x", padx=10, pady=(0, 8))

        # Alerta de reglamento
        self._lbl_reg_alert = ctk.CTkLabel(
            self._stints_card,
            text="✅ Cumple normativa de reglamento: ambos compuestos obligatorios utilizados.",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#51CF66",
        )
        self._lbl_reg_alert.pack(anchor="w", padx=20, pady=(0, 12))

    def _on_stops_mode_changed(self, value: str):
        try:
            num = int(value.split()[0])
            self._var_num_stops.set(max(1, num))
        except Exception:
            self._var_num_stops.set(1)
        self._update_slider_bounds()
        self.recalculate_and_plot()

    def _schedule_recalculate_and_plot(self):
        """Debounce de recálculo y renderizado para permitir interacción a 60 FPS sin tirones."""
        if hasattr(self, "_plot_job") and self._plot_job is not None:
            self.after_cancel(self._plot_job)
        self._plot_job = self.after(35, self.recalculate_and_plot)

    def _on_p1_slider_event(self, val: float):
        p1 = int(round(val))
        self._var_pit1_lap.set(p1)
        self._lbl_s1_val.configure(text=f"V{p1}")

        tot = self._var_total_laps.get()
        num_stops = max(1, self._var_num_stops.get())
        if num_stops == 1:
            self._lbl_st1_title.configure(text=f"STINT 1 (V1 ➔ V{p1})")
            self._lbl_st2_title.configure(text=f"STINT 2 (V{p1 + 1} ➔ Meta)")
        else:
            tank_cap = float(self.session_data.get("fuel_capacity_l", 70.0))
            safety_l = float(self.fuel_data.get("calc_results", {}).get("safety_fuel_l", 2.5))
            cons_lap = float(self.fuel_data.get("cons_lap", 2.15))
            usable_fuel = max(1.0, tank_cap - safety_l)
            c_min = 0.80 * cons_lap
            l_max_20 = max(1, math.floor(usable_fuel / c_min))

            p2_min = max(p1 + 1, tot - l_max_20)
            p2_max = min(tot - 1, p1 + l_max_20)
            if p2_min > p2_max:
                p2_min = p2_max
            s2_from = min(p2_min, p2_max)
            s2_to = max(p2_min, p2_max)
            s2_steps = max(1, s2_to - s2_from)
            if s2_from == s2_to:
                s2_to += 1

            new_bounds = (s2_from, s2_to, s2_steps)
            if getattr(self, "_s2_slider_bounds", None) != new_bounds:
                self._s2_slider_bounds = new_bounds
                self._slider_p2.configure(from_=s2_from, to=s2_to, number_of_steps=s2_steps)
                self._lbl_s2_title.configure(text=f"🛑 Parada 2 (V{p2_min} ➔ V{p2_max}):")

            p2 = self._var_pit2_lap.get()
            if p2 < p2_min:
                p2 = p2_min
                self._var_pit2_lap.set(p2)
                self._lbl_s2_val.configure(text=f"V{p2}")
            elif p2 > p2_max:
                p2 = p2_max
                self._var_pit2_lap.set(p2)
                self._lbl_s2_val.configure(text=f"V{p2}")

            self._lbl_st1_title.configure(text=f"STINT 1 (V1 ➔ V{p1})")
            self._lbl_st2_title.configure(text=f"STINT 2 (V{p1 + 1} ➔ V{p2})")
            self._lbl_st3_title.configure(text=f"STINT 3 (V{p2 + 1} ➔ Meta)")

        self._schedule_recalculate_and_plot()

    def _on_p2_slider_event(self, val: float):
        p2 = int(round(val))
        self._var_pit2_lap.set(p2)
        self._lbl_s2_val.configure(text=f"V{p2}")

        p1 = self._var_pit1_lap.get()
        self._lbl_st2_title.configure(text=f"STINT 2 (V{p1 + 1} ➔ V{p2})")
        self._lbl_st3_title.configure(text=f"STINT 3 (V{p2 + 1} ➔ Meta)")

        self._schedule_recalculate_and_plot()

    def _update_slider_bounds(self):
        """
        Ajusta los sliders según el filtro estricto de viabilidad de combustible
        (Ahorro máximo 20%). Se ejecuta solo al cambiar de modo de paradas o sesión.
        """
        tot = self._var_total_laps.get()
        num_stops = max(1, self._var_num_stops.get())

        tank_cap = float(self.session_data.get("fuel_capacity_l", 70.0))
        safety_l = float(self.fuel_data.get("calc_results", {}).get("safety_fuel_l", 2.5))
        cons_lap = float(self.fuel_data.get("cons_lap", 2.15))
        usable_fuel = max(1.0, tank_cap - safety_l)

        # Laps máximas posibles ahorrando 20%
        c_min = 0.80 * cons_lap
        l_max_20 = max(1, math.floor(usable_fuel / c_min))

        if num_stops == 1:
            self._s2_box.pack_forget()
            self._c_st3.grid_forget()

            p1_min = max(2, tot - l_max_20)
            p1_max = min(tot - 1, l_max_20)
            if p1_min > p1_max:
                p1_min = p1_max
            s1_from = min(p1_min, p1_max)
            s1_to = max(p1_min, p1_max)
            s1_steps = max(1, s1_to - s1_from)
            if s1_from == s1_to:
                s1_to += 1

            new_s1_bounds = (s1_from, s1_to, s1_steps)
            if getattr(self, "_s1_slider_bounds", None) != new_s1_bounds:
                self._s1_slider_bounds = new_s1_bounds
                self._slider_p1.configure(from_=s1_from, to=s1_to, number_of_steps=s1_steps)
            self._lbl_s1_title.configure(text=f"🛑 Parada 1 (V{p1_min} ➔ V{p1_max} · Ahorro ≤ 20%):")

            p1 = max(s1_from, min(s1_to, self._var_pit1_lap.get()))
            self._var_pit1_lap.set(p1)
            self._lbl_s1_val.configure(text=f"V{p1}")

            self._lbl_st1_title.configure(text=f"STINT 1 (V1 ➔ V{p1})")
            self._lbl_st2_title.configure(text=f"STINT 2 (V{p1 + 1} ➔ Meta)")

        else:
            if not self._s2_box.winfo_ismapped():
                self._s2_box.pack(fill="x", padx=20, pady=(0, 6), after=self._s1_box)
            if not self._c_st3.winfo_ismapped():
                self._c_st3.grid(row=0, column=2, padx=4, sticky="nsew")

            p1_min = max(2, tot - 2 * l_max_20)
            p1_max = min(tot - 2, l_max_20)
            if p1_min > p1_max:
                p1_min = p1_max
            s1_from = min(p1_min, p1_max)
            s1_to = max(p1_min, p1_max)
            s1_steps = max(1, s1_to - s1_from)
            if s1_from == s1_to:
                s1_to += 1

            new_s1_bounds = (s1_from, s1_to, s1_steps)
            if getattr(self, "_s1_slider_bounds", None) != new_s1_bounds:
                self._s1_slider_bounds = new_s1_bounds
                self._slider_p1.configure(from_=s1_from, to=s1_to, number_of_steps=s1_steps)
            self._lbl_s1_title.configure(text=f"🛑 Parada 1 (V{p1_min} ➔ V{p1_max}):")

            p1 = max(s1_from, min(s1_to, self._var_pit1_lap.get()))
            self._var_pit1_lap.set(p1)
            self._lbl_s1_val.configure(text=f"V{p1}")

            p2_min = max(p1 + 1, tot - l_max_20)
            p2_max = min(tot - 1, p1 + l_max_20)
            if p2_min > p2_max:
                p2_min = p2_max
            s2_from = min(p2_min, p2_max)
            s2_to = max(p2_min, p2_max)
            s2_steps = max(1, s2_to - s2_from)
            if s2_from == s2_to:
                s2_to += 1

            new_s2_bounds = (s2_from, s2_to, s2_steps)
            if getattr(self, "_s2_slider_bounds", None) != new_s2_bounds:
                self._s2_slider_bounds = new_s2_bounds
                self._slider_p2.configure(from_=s2_from, to=s2_to, number_of_steps=s2_steps)
            self._lbl_s2_title.configure(text=f"🛑 Parada 2 (V{p2_min} ➔ V{p2_max}):")

            p2 = max(s2_from, min(s2_to, self._var_pit2_lap.get()))
            self._var_pit2_lap.set(p2)
            self._lbl_s2_val.configure(text=f"V{p2}")

            self._lbl_st1_title.configure(text=f"STINT 1 (V1 ➔ V{p1})")
            self._lbl_st2_title.configure(text=f"STINT 2 (V{p1 + 1} ➔ V{p2})")
            self._lbl_st3_title.configure(text=f"STINT 3 (V{p2 + 1} ➔ Meta)")

    def _on_stint_compound_changed(self, stint_num: int, value: str):
        c_val = "soft" if "Blanda" in value else "hard"
        if stint_num == 1:
            self._var_stint1_tyre.set(c_val)
        elif stint_num == 2:
            self._var_stint2_tyre.set(c_val)
        else:
            self._var_stint3_tyre.set(c_val)
        self.recalculate_and_plot()

    # ─── 4. Métricas de Carrera y Gráfico Matplotlib ──────────
    def _build_chart_section(self):
        chart_wrapper = ctk.CTkFrame(
            self._scroll,
            fg_color=self.colors["bg_secondary"],
            corner_radius=10,
            border_width=1,
            border_color=self.colors["border"],
        )
        chart_wrapper.pack(fill="x", padx=32, pady=(0, 16))
        chart_wrapper.grid_columnconfigure(0, weight=1)

        metrics_bar = ctk.CTkFrame(chart_wrapper, fg_color="transparent")
        metrics_bar.pack(fill="x", padx=20, pady=(16, 8))
        metrics_bar.grid_columnconfigure((0, 1, 2, 3), weight=1)

        metric_cards = [
            ("⏱️ Tiempo Total Carrera", "_lbl_m_total_time",  0),
            ("🏎️ Tiempo Neto en Pista", "_lbl_m_track_time",  1),
            ("🛑 Pérdida en Boxes",      "_lbl_m_box_time",    2),
            ("📉 Degradación + Calent.", "_lbl_m_deg_loss",    3),
        ]

        for title, attr_name, col in metric_cards:
            card = ctk.CTkFrame(metrics_bar, fg_color=self.colors["bg_primary"], corner_radius=8, border_width=1, border_color=self.colors["border"])
            card.grid(row=0, column=col, padx=5, sticky="nsew")
            ctk.CTkLabel(card, text=title, font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"), text_color=self.colors["text_secondary"]).pack(anchor="w", padx=10, pady=(8, 2))
            val_lbl = ctk.CTkLabel(card, text="—", font=ctk.CTkFont(family="Segoe UI Mono", size=14, weight="bold"), text_color=self.colors["accent"])
            val_lbl.pack(anchor="w", padx=10, pady=(0, 8))
            setattr(self, attr_name, val_lbl)

        self._plot_frame = ctk.CTkFrame(chart_wrapper, fg_color=self.colors["bg_primary"], corner_radius=8, border_width=1, border_color=self.colors["border"])
        self._plot_frame.pack(fill="x", padx=20, pady=(0, 16))

        self._fig = Figure(figsize=(9, 4.4), dpi=100, facecolor="#0E0E0E")
        self._ax = self._fig.add_subplot(111)
        self._ax.set_facecolor("#141414")

        self._mpl_canvas = FigureCanvasTkAgg(self._fig, master=self._plot_frame)
        self._mpl_canvas.draw()
        self._mpl_canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=8)

    # ═══════════════════════════════════════════════════════════
    #  CÁLCULO DE LA CARRERA Y RENDERIZADO DEL GRÁFICO
    # ═══════════════════════════════════════════════════════════

    def _parse_time_str(self, text: str, default: float) -> float:
        text = text.strip()
        if not text:
            return default
        try:
            if ":" in text:
                parts = text.split(":")
                return float(parts[0]) * 60.0 + float(parts[1].replace(",", "."))
            return float(text.replace(",", "."))
        except Exception:
            return default

    def _get_hard_base_lap(self) -> float:
        circ_base = float(self.session_data.get("lap_time_seconds", 84.5))
        return self._parse_time_str(self._var_hard_base_lap.get(), circ_base)

    def _get_soft_base_lap(self) -> float:
        circ_base = float(self.session_data.get("lap_time_seconds", 84.5))
        return self._parse_time_str(self._var_soft_base_lap.get(), circ_base - 0.450)

    def _get_hard_warmup(self) -> float:
        try:
            return float(self._var_hard_warmup.get().replace(",", "."))
        except ValueError:
            return 0.800

    def _get_soft_warmup(self) -> float:
        try:
            return float(self._var_soft_warmup.get().replace(",", "."))
        except ValueError:
            return 0.400

    def _get_hard_a(self) -> float:
        try:
            return float(self._var_hard_a.get().replace(",", "."))
        except ValueError:
            return 0.2223

    def _get_hard_n(self) -> float:
        try:
            return float(self._var_hard_n.get().replace(",", "."))
        except ValueError:
            return -0.1208

    def _get_soft_a(self) -> float:
        try:
            return float(self._var_soft_a.get().replace(",", "."))
        except ValueError:
            return 0.5318

    def _get_soft_n(self) -> float:
        try:
            return float(self._var_soft_n.get().replace(",", "."))
        except ValueError:
            return -0.3968

    def get_tyre_pace(self, compound: str, x: int) -> float:
        """
        Función a tramos estricta:
          x = 0 ➔ Ritmo Base (70L) + Pérdida Calentar Rueda (vuelta de salida con gomas frías)
          x = 1 ➔ Ritmo Base (70L) (vuelta óptima de trabajo, Δdeg = 0.000s forzado)
          x >= 2 ➔ Ritmo Base (70L) + max(0.0, a·ln(x) + n)
        """
        is_hard = (compound == "hard")
        base_lap = self._get_hard_base_lap() if is_hard else self._get_soft_base_lap()
        warmup = self._get_hard_warmup() if is_hard else self._get_soft_warmup()

        if x == 0:
            return base_lap + warmup
        elif x == 1:
            return base_lap
        else:
            a = self._get_hard_a() if is_hard else self._get_soft_a()
            n = self._get_hard_n() if is_hard else self._get_soft_n()
            deg = a * math.log(x) + n
            return base_lap + max(0.0, deg)

    def _calculate_pit_box_time(self, fuel_to_load: float, tyre_change_s: float, refuel_rate: float, car_lift_s: float = 2.0) -> tuple[float, str]:
        """Calcula el tiempo de parada estacionaria en box y el factor limitante."""
        refuel_t = fuel_to_load / refuel_rate if refuel_rate > 0 else 0.0
        box_t = car_lift_s + max(refuel_t, tyre_change_s)
        limiting = "REPOSTAJE" if refuel_t > tyre_change_s else "RUEDAS"
        return box_t, limiting

    def recalculate_and_plot(self):
        """
        Simulación completa vuelta a vuelta:
          - x=0 vuelta 1 del stint (salida carrera o salida box)
          - x=1 vuelta 2 del stint (goma óptima)
          - x>=2 vuelta 3+ (degradación logarítmica)
          - Efecto peso de combustible en cada vuelta
          - Tiempo real en boxes según litros cargados
          - Gráfico Matplotlib con sombreado blanco/rojo
        """
        if not hasattr(self, "_ax") or self._ax is None:
            return

        total_laps = self._var_total_laps.get()
        num_stops  = self._var_num_stops.get()
        p1         = self._var_pit1_lap.get()
        p2         = self._var_pit2_lap.get()

        tank_cap     = float(self.session_data.get("fuel_capacity_l", 70.0))
        refuel_rate  = float(self.session_data.get("refuel_rate_ls", 12.0))
        tyre_change  = float(self.session_data.get("tyre_change_time", 4.0))
        car_lift     = float(self.session_data.get("car_lift_s") or self.session_data.get("car_lift_time") or 2.0)
        pitlane_loss = float(self.session_data.get("pitlane_loss", 22.5))
        cons_lap     = float(self.fuel_data.get("cons_lap", 2.15))
        safety_fuel  = float(self.fuel_data.get("safety_fuel_l") or self.fuel_data.get("calc_results", {}).get("safety_fuel_l", 2.5))
        weight_sens  = float(self.fuel_data.get("weight_sens") or self.fuel_data.get("calc_results", {}).get("weight_sens") or self.session_data.get("weight_sens", 0.015))

        st1_comp = self._var_stint1_tyre.get()
        st2_comp = self._var_stint2_tyre.get()
        st3_comp = self._var_stint3_tyre.get()

        # Actualizar títulos de stints
        if num_stops == 1:
            self._lbl_st1_title.configure(text=f"STINT 1 (V1 ➔ V{p1} · {p1}v)")
            self._lbl_st2_title.configure(text=f"STINT 2 (V{p1+1} ➔ V{total_laps} · {total_laps - p1}v)")
        else:
            self._lbl_st1_title.configure(text=f"STINT 1 (V1 ➔ V{p1} · {p1}v)")
            self._lbl_st2_title.configure(text=f"STINT 2 (V{p1+1} ➔ V{p2} · {p2 - p1}v)")
            self._lbl_st3_title.configure(text=f"STINT 3 (V{p2+1} ➔ V{total_laps} · {total_laps - p2}v)")

        # Comprobar normativa de ambos compuestos
        used_comps = {st1_comp, st2_comp}
        if num_stops == 2:
            used_comps.add(st3_comp)

        if "hard" in used_comps and "soft" in used_comps:
            self._lbl_reg_alert.configure(
                text="✅ Cumple normativa de reglamento: ambos compuestos obligatorios utilizados (Dura y Blanda).",
                text_color="#51CF66"
            )
        else:
            self._lbl_reg_alert.configure(
                text="⚠️ ALERTA DE REGLAMENTO: Debes montar ambos compuestos en carrera (Dura y Blanda).",
                text_color="#FFA94D"
            )

        # ── CÁLCULO FÍSICO DE COMBUSTIBLE EN PARADAS ───────────
        # Parada 1
        laps1 = p1
        fuel_in_box1 = max(0.0, tank_cap - (laps1 * cons_lap))
        if num_stops == 1:
            laps2 = total_laps - p1
            fuel_needed2 = (laps2 * cons_lap) + safety_fuel
            fuel_load1 = min(tank_cap - fuel_in_box1, max(0.0, fuel_needed2 - fuel_in_box1))
            box_t1, limit1 = self._calculate_pit_box_time(fuel_load1, tyre_change, refuel_rate, car_lift)
            total_pit_loss1 = pitlane_loss + box_t1

            fuel_load2 = 0.0
            total_pit_loss2 = 0.0
            fuel_start_stint2 = fuel_in_box1 + fuel_load1
            fuel_start_stint3 = 0.0
        else:
            laps2 = max(1, p2 - p1)
            fuel_needed2 = (laps2 * cons_lap) + safety_fuel
            fuel_load1 = min(tank_cap - fuel_in_box1, max(0.0, fuel_needed2 - fuel_in_box1))
            box_t1, limit1 = self._calculate_pit_box_time(fuel_load1, tyre_change, refuel_rate, car_lift)
            total_pit_loss1 = pitlane_loss + box_t1
            fuel_start_stint2 = fuel_in_box1 + fuel_load1

            # Parada 2
            fuel_in_box2 = max(0.0, fuel_start_stint2 - (laps2 * cons_lap))
            laps3 = max(1, total_laps - p2)
            fuel_needed3 = (laps3 * cons_lap) + safety_fuel
            fuel_load2 = min(tank_cap - fuel_in_box2, max(0.0, fuel_needed3 - fuel_in_box2))
            box_t2, limit2 = self._calculate_pit_box_time(fuel_load2, tyre_change, refuel_rate, car_lift)
            total_pit_loss2 = pitlane_loss + box_t2
            fuel_start_stint3 = fuel_in_box2 + fuel_load2

        # ── SIMULACIÓN VUELTA A VUELTA ─────────────────────────
        laps = list(range(1, total_laps + 1))
        on_track_times = []
        full_lap_times = []

        total_track_time_s = 0.0
        total_box_time_s = total_pit_loss1 + (total_pit_loss2 if num_stops == 2 else 0.0)
        total_deg_warmup_loss_s = 0.0

        for lap in laps:
            if lap <= p1:
                # Stint 1
                comp = st1_comp
                stint_lap = lap
                tyre_age = stint_lap - 1  # lap=1 (x=0), lap=2 (x=1), lap=3 (x=2)
                fuel_current = max(safety_fuel, tank_cap - (stint_lap - 1) * cons_lap)
                is_pit = False
                pit_time_this_lap = 0.0
            elif num_stops == 1 or lap <= p2:
                # Stint 2
                comp = st2_comp
                stint_lap = lap - p1
                tyre_age = stint_lap - 1  # stint_lap=1 (x=0), stint_lap=2 (x=1), stint_lap=3 (x=2)
                fuel_current = max(safety_fuel, fuel_start_stint2 - (stint_lap - 1) * cons_lap)
                is_pit = (stint_lap == 1)
                pit_time_this_lap = total_pit_loss1 if is_pit else 0.0
            else:
                # Stint 3
                comp = st3_comp
                stint_lap = lap - p2
                tyre_age = stint_lap - 1  # stint_lap=1 (x=0), stint_lap=2 (x=1), stint_lap=3 (x=2)
                fuel_current = max(safety_fuel, fuel_start_stint3 - (stint_lap - 1) * cons_lap)
                is_pit = (stint_lap == 1 and num_stops == 2)
                pit_time_this_lap = total_pit_loss2 if is_pit else 0.0

            # 1. Ritmo de neumático a tramos
            tyre_pace = self.get_tyre_pace(comp, tyre_age)

            # 2. Efecto peso gasolina (El ritmo base se define con tanque lleno = tank_cap = 70L).
            #    Al quemar combustible, el coche se aligera (delta negativo = más rápido).
            weight_delta = (fuel_current - tank_cap) * weight_sens

            track_time = tyre_pace + weight_delta
            lap_total = track_time + pit_time_this_lap

            on_track_times.append(track_time)
            full_lap_times.append(lap_total)

            total_track_time_s += track_time

            # Delta pérdida respecto al ritmo base óptimo
            base_opt = self._get_hard_base_lap() if comp == "hard" else self._get_soft_base_lap()
            total_deg_warmup_loss_s += max(0.0, tyre_pace - base_opt)

        total_race_time_s = total_track_time_s + total_box_time_s

        # Actualizar métricas UI
        if hasattr(self, "_lbl_m_total_time"):
            self._lbl_m_total_time.configure(text=self._format_seconds_hh_mm_ss(total_race_time_s))
            self._lbl_m_track_time.configure(text=self._format_seconds_hh_mm_ss(total_track_time_s))
            self._lbl_m_box_time.configure(text=f"{total_box_time_s:.1f} s ({num_stops} paradas)")
            self._lbl_m_deg_loss.configure(text=f"+{total_deg_warmup_loss_s:.1f} s")

        # ── RENDERIZADO DEL GRÁFICO MATPLOTLIB ───────────────────
        self._ax.clear()
        self._ax.set_facecolor("#141414")

        stints_def = []
        if num_stops == 1:
            stints_def = [
                (1, 1, p1, st1_comp),
                (2, p1 + 1, total_laps, st2_comp),
            ]
        else:
            stints_def = [
                (1, 1, p1, st1_comp),
                (2, p1 + 1, p2, st2_comp),
                (3, p2 + 1, total_laps, st3_comp),
            ]

        y_min_track = min(on_track_times) - 0.4
        y_max_track = max(on_track_times) + 0.6

        plotted_hard_label = False
        plotted_soft_label = False

        for _stint_id, start_v, end_v, comp in stints_def:
            st_laps = laps[start_v - 1 : end_v]
            st_times = on_track_times[start_v - 1 : end_v]

            if comp == "hard":
                color_line = "#FFFFFF"
                color_area = "#E8E8E8"
                alpha_val  = 0.18
                label_txt  = "Rueda Dura (Prime)" if not plotted_hard_label else None
                plotted_hard_label = True
            else:
                color_line = "#FF3B30"
                color_area = "#FF3B30"
                alpha_val  = 0.22
                label_txt  = "Rueda Blanda (Alternative)" if not plotted_soft_label else None
                plotted_soft_label = True

            # Sombreado de área del compuesto
            self._ax.fill_between(st_laps, y_min_track, st_times, color=color_area, alpha=alpha_val)
            # Línea de ritmo de vuelta en pista
            self._ax.plot(st_laps, st_times, color=color_line, linewidth=2.4, label=label_txt)

        # ── CONEXIONES CONTINUAS ENTRE STINTS (SIN CORTES) ──────
        # Conectar el final del Stint 1 (p1) con el inicio del Stint 2 (p1 + 1)
        if num_stops >= 1 and p1 < total_laps:
            c_conn1 = "#FFFFFF" if st2_comp == "hard" else "#FF3B30"
            self._ax.plot([p1, p1 + 1], [on_track_times[p1 - 1], on_track_times[p1]], color=c_conn1, linewidth=2.4)
            self._ax.fill_between([p1, p1 + 1], y_min_track, [on_track_times[p1 - 1], on_track_times[p1]], color=c_conn1, alpha=0.18)

        # Conectar el final del Stint 2 (p2) con el inicio del Stint 3 (p2 + 1)
        if num_stops == 2 and p2 < total_laps:
            c_conn2 = "#FFFFFF" if st3_comp == "hard" else "#FF3B30"
            self._ax.plot([p2, p2 + 1], [on_track_times[p2 - 1], on_track_times[p2]], color=c_conn2, linewidth=2.4)
            self._ax.fill_between([p2, p2 + 1], y_min_track, [on_track_times[p2 - 1], on_track_times[p2]], color=c_conn2, alpha=0.18)

        # Marcar las vueltas de pit stop en la out-lap (p1 + 1, p2 + 1) con anotación
        pit_info_list = []
        if p1 < total_laps:
            pit_info_list.append((p1 + 1, total_pit_loss1, fuel_load1))
        if num_stops == 2 and p2 < total_laps:
            pit_info_list.append((p2 + 1, total_pit_loss2, fuel_load2))

        for idx, (pit_v, pit_t, f_load) in enumerate(pit_info_list):
            self._ax.axvline(x=pit_v, color="#F26419", linestyle="--", linewidth=1.8, alpha=0.85)
            self._ax.annotate(
                f"BOX {idx+1}\n+{pit_t:.1f}s ({f_load:.1f}L)",
                xy=(pit_v, y_max_track - 0.1),
                xytext=(pit_v + 0.35, y_max_track - 0.25),
                color="#FFA94D",
                fontsize=8.5,
                fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.3", fc="#201005", ec="#F26419", lw=1),
            )

        # Formato de ejes y títulos
        self._ax.set_title("Evolución del Tiempo por Vuelta (Ritmo de Carrera con Desgaste, Peso y Boxes)", color="#FFFFFF", fontsize=11, fontweight="bold", pad=12)
        self._ax.set_xlabel("Vuelta de Carrera", color="#A0A0A0", fontsize=9.5, labelpad=8)
        self._ax.set_ylabel("Tiempo de Vuelta", color="#A0A0A0", fontsize=9.5, labelpad=8)
        self._ax.set_xlim(0.5, total_laps + 0.5)
        self._ax.set_ylim(y_min_track, y_max_track + 0.2)

        def time_formatter(val, _pos):
            return self._format_seconds(val)

        self._ax.yaxis.set_major_formatter(ticker.FuncFormatter(time_formatter))
        self._ax.xaxis.set_major_locator(ticker.MaxNLocator(integer=True, nbins=15))

        self._ax.grid(True, color="#222222", linestyle=":", linewidth=0.8)
        for spine in self._ax.spines.values():
            spine.set_color("#2E2E2E")
        self._ax.tick_params(colors="#888888", labelsize=8.5)

        self._ax.legend(facecolor="#181818", edgecolor="#333333", labelcolor="#FFFFFF", fontsize=8.5, loc="upper left")

        self._fig.tight_layout()
        if self._mpl_canvas:
            self._mpl_canvas.draw_idle()

    # ═══════════════════════════════════════════════════════════
    #  PERSISTENCIA DE MODELOS POR CIRCUITO (MODELOS DE NEUMÁTICOS)
    # ═══════════════════════════════════════════════════════════

    def _get_profile_path(self) -> Path | None:
        champ = self.session_data.get("championship_name")
        circuit = self.session_data.get("circuit")
        if not champ or not circuit:
            return None
        safe_champ = re.sub(r'[\\/*?:"<>|]', "_", champ)
        safe_circ  = re.sub(r'[\\/*?:"<>|]', "_", circuit)
        return PROFILES_ROOT / safe_champ / f"{safe_circ}_tyres.json"

    def _get_tyre_models_path(self) -> Path | None:
        champ = self.session_data.get("championship_name")
        circuit = self.session_data.get("circuit")
        if not champ or not circuit:
            return None
        safe_champ = re.sub(r'[\\/*?:"<>|]', "_", champ)
        safe_circ  = re.sub(r'[\\/*?:"<>|]', "_", circuit)
        return PROFILES_ROOT / safe_champ / f"{safe_circ}_tyre_models.json"

    def _load_saved_tyre_models_dict(self) -> dict:
        m_path = self._get_tyre_models_path()
        if m_path and m_path.exists():
            try:
                data = json.loads(m_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:
                pass

        # Retrocompatibilidad: si existe _tyres.json, importarlo como modelo
        t_path = self._get_profile_path()
        if t_path and t_path.exists():
            try:
                data = json.loads(t_path.read_text(encoding="utf-8"))
                model_name = data.get("active_model", "Modelo 1")
                legacy_models = {model_name: data}
                if m_path:
                    m_path.parent.mkdir(parents=True, exist_ok=True)
                    m_path.write_text(json.dumps(legacy_models, ensure_ascii=False, indent=2), encoding="utf-8")
                return legacy_models
            except Exception:
                pass
        return {}

    def _refresh_tyre_models_list(self):
        self.saved_tyre_models = self._load_saved_tyre_models_dict()
        vals = ["⚡ Modelo Base"] + list(self.saved_tyre_models.keys())
        if hasattr(self, "_cbo_tyre_models"):
            self._cbo_tyre_models.configure(values=vals)
            if self._var_selected_tyre_model.get() not in vals:
                self._var_selected_tyre_model.set(vals[0])

    def _apply_tyre_model_data(self, data: dict):
        self._var_hard_base_lap.set(data.get("hard_base_lap", "01:24.500"))
        self._var_hard_warmup.set(data.get("hard_warmup", "0.800"))
        self._var_hard_a.set(data.get("hard_a", "0.2223"))
        self._var_hard_n.set(data.get("hard_n", "-0.1208"))
        self._var_hard_r2.set(data.get("hard_r2", "0.9408"))
        if "hard_test_points" in data and data["hard_test_points"]:
            self.hard_test_points = [dict(p) for p in data["hard_test_points"]]
            self._render_test_points("hard")

        self._var_soft_base_lap.set(data.get("soft_base_lap", "01:24.050"))
        self._var_soft_warmup.set(data.get("soft_warmup", "0.400"))
        self._var_soft_a.set(data.get("soft_a", "0.5318"))
        self._var_soft_n.set(data.get("soft_n", "-0.3968"))
        self._var_soft_r2.set(data.get("soft_r2", "0.8634"))
        if "soft_test_points" in data and data["soft_test_points"]:
            self.soft_test_points = [dict(p) for p in data["soft_test_points"]]
            self._render_test_points("soft")

        s1 = data.get("stint1_tyre", "soft")
        s2 = data.get("stint2_tyre", "hard")
        s3 = data.get("stint3_tyre", "hard")
        self._var_stint1_tyre.set(s1)
        if hasattr(self, "_seg_st1"):
            self._seg_st1.set("🔴 Blanda" if s1 == "soft" else "⚪ Dura")
        self._var_stint2_tyre.set(s2)
        if hasattr(self, "_seg_st2"):
            self._seg_st2.set("🔴 Blanda" if s2 == "soft" else "⚪ Dura")
        self._var_stint3_tyre.set(s3)
        if hasattr(self, "_seg_st3"):
            self._seg_st3.set("🔴 Blanda" if s3 == "soft" else "⚪ Dura")

        self.recalculate_and_plot()

    def _on_tyre_model_selected(self, name: str):
        if name == "⚡ Modelo Base":
            t_path = self._get_profile_path()
            if t_path and t_path.exists():
                try:
                    data = json.loads(t_path.read_text(encoding="utf-8"))
                    self._apply_tyre_model_data(data)
                    return
                except Exception:
                    pass
            circ_base = float(self.session_data.get("lap_time_seconds", 84.5))
            self._var_hard_base_lap.set(self._format_seconds(circ_base))
            self._var_hard_warmup.set("0.800")
            self._var_hard_a.set("0.2223")
            self._var_hard_n.set("-0.1208")
            self._var_hard_r2.set("0.9408")
            self.hard_test_points = [
                {"lap": 2,  "delta": 0.08},
                {"lap": 6,  "delta": 0.22},
                {"lap": 12, "delta": 0.38},
                {"lap": 18, "delta": 0.52},
                {"lap": 24, "delta": 0.65},
            ]
            self._render_test_points("hard")

            self._var_soft_base_lap.set(self._format_seconds(max(0.1, circ_base - 0.450)))
            self._var_soft_warmup.set("0.400")
            self._var_soft_a.set("0.5318")
            self._var_soft_n.set("-0.3968")
            self._var_soft_r2.set("0.8634")
            self.soft_test_points = [
                {"lap": 2,  "delta": 0.12},
                {"lap": 5,  "delta": 0.32},
                {"lap": 9,  "delta": 0.58},
                {"lap": 14, "delta": 0.95},
                {"lap": 18, "delta": 1.38},
            ]
            self._render_test_points("soft")

            self._var_stint1_tyre.set("soft")
            if hasattr(self, "_seg_st1"):
                self._seg_st1.set("🔴 Blanda")
            self._var_stint2_tyre.set("hard")
            if hasattr(self, "_seg_st2"):
                self._seg_st2.set("⚪ Dura")
            self._var_stint3_tyre.set("hard")
            if hasattr(self, "_seg_st3"):
                self._seg_st3.set("⚪ Dura")

            self.recalculate_and_plot()
            return

        data = self.saved_tyre_models.get(name)
        if data:
            self._apply_tyre_model_data(data)

    def save_tyre_profile(self):
        """Guarda el modelo de neumáticos actual con un nombre."""
        m_path = self._get_tyre_models_path()
        if not m_path:
            messagebox.showwarning("Sin sesión", "Guarda primero un campeonato y circuito en el Módulo 1.")
            return

        curr = self._var_selected_tyre_model.get()
        dialog = ctk.CTkInputDialog(
            text=f"Nombre identificativo del modelo de neumáticos:\n(Circuito: {self.session_data.get('circuit')})",
            title="Guardar Modelo de Neumáticos"
        )
        name = dialog.get_input()
        if not name or not name.strip():
            return
        name = name.strip()

        data = {
            "hard_base_lap": self._var_hard_base_lap.get(),
            "hard_warmup": self._var_hard_warmup.get(),
            "hard_a": self._var_hard_a.get(),
            "hard_n": self._var_hard_n.get(),
            "hard_r2": self._var_hard_r2.get(),
            "hard_test_points": list(self.hard_test_points),
            "soft_base_lap": self._var_soft_base_lap.get(),
            "soft_warmup": self._var_soft_warmup.get(),
            "soft_a": self._var_soft_a.get(),
            "soft_n": self._var_soft_n.get(),
            "soft_r2": self._var_soft_r2.get(),
            "soft_test_points": list(self.soft_test_points),
            "stint1_tyre": self._var_stint1_tyre.get(),
            "stint2_tyre": self._var_stint2_tyre.get(),
            "stint3_tyre": self._var_stint3_tyre.get(),
        }

        self.saved_tyre_models[name] = data
        m_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            m_path.write_text(json.dumps(self.saved_tyre_models, ensure_ascii=False, indent=2), encoding="utf-8")
            # Sincronizar también _tyres.json como modelo activo
            t_path = self._get_profile_path()
            if t_path:
                active_data = dict(data)
                active_data["active_model"] = name
                t_path.write_text(json.dumps(active_data, ensure_ascii=False, indent=2), encoding="utf-8")

            self._refresh_tyre_models_list()
            self._var_selected_tyre_model.set(name)
            messagebox.showinfo("Guardado", f"Modelo de neumáticos '{name}' guardado correctamente para:\n{self.session_data.get('circuit')}")
        except Exception as e:
            messagebox.showerror("Error al guardar", str(e))

    def load_tyre_profile(self) -> bool:
        """Carga el modelo de neumáticos activo para el campeonato+circuito activo."""
        self._refresh_tyre_models_list()
        t_path = self._get_profile_path()
        if t_path and t_path.exists():
            try:
                data = json.loads(t_path.read_text(encoding="utf-8"))
                active_name = data.get("active_model")
                if active_name and active_name in self.saved_tyre_models:
                    self._var_selected_tyre_model.set(active_name)
                    self._apply_tyre_model_data(self.saved_tyre_models[active_name])
                    return True
                else:
                    self._apply_tyre_model_data(data)
                    return True
            except Exception:
                pass

        if self.saved_tyre_models:
            first_name = list(self.saved_tyre_models.keys())[0]
            self._var_selected_tyre_model.set(first_name)
            self._apply_tyre_model_data(self.saved_tyre_models[first_name])
            return True

        return False

    def reload_tyre_profile(self):
        """Recarga el modelo de neumáticos seleccionado desde disco."""
        m_path = self._get_tyre_models_path()
        t_path = self._get_profile_path()
        if (not m_path or not m_path.exists()) and (not t_path or not t_path.exists()):
            messagebox.showinfo("Sin modelos guardados", "No hay modelos de neumáticos guardados en disco para este circuito.")
            return

        self._refresh_tyre_models_list()
        curr = self._var_selected_tyre_model.get()
        self._on_tyre_model_selected(curr)
        messagebox.showinfo("Recargado", f"Modelo de neumáticos '{curr}' recargado desde disco.")

    def delete_tyre_profile(self):
        """Elimina el modelo de neumáticos seleccionado."""
        name = self._var_selected_tyre_model.get()
        if name == "⚡ Modelo Base":
            messagebox.showinfo("Aviso", "El 'Modelo Base' no se puede eliminar ya que representa los valores base del circuito.")
            return

        confirm = messagebox.askyesno(
            "Borrar Modelo",
            f"¿Estás seguro de que deseas eliminar el modelo de neumáticos '{name}'?",
            icon="warning"
        )
        if not confirm:
            return

        if name in self.saved_tyre_models:
            del self.saved_tyre_models[name]
            m_path = self._get_tyre_models_path()
            if m_path:
                m_path.write_text(json.dumps(self.saved_tyre_models, ensure_ascii=False, indent=2), encoding="utf-8")
            self._refresh_tyre_models_list()
            self._var_selected_tyre_model.set("⚡ Modelo Base")
            self._on_tyre_model_selected("⚡ Modelo Base")
            messagebox.showinfo("Eliminado", f"Modelo de neumáticos '{name}' eliminado exitosamente.")

    # ═══════════════════════════════════════════════════════════
    #  SINCRONIZACIÓN Y CALLBACKS DE MAIN
    # ═══════════════════════════════════════════════════════════

    def on_session_data_updated(self, session_data: dict):
        """Callback cuando cambian los datos de campeonato o circuito."""
        if not session_data:
            return
        last_champ = self.session_data.get("championship_name") if hasattr(self, "session_data") and self.session_data else None
        last_circ = self.session_data.get("circuit") if hasattr(self, "session_data") and self.session_data else None
        new_champ = session_data.get("championship_name")
        new_circ = session_data.get("circuit")

        self.session_data = session_data

        circ_name = session_data.get("circuit", "Watkins Glen")
        base_lap_s = float(session_data.get("lap_time_seconds", 84.5))

        # Si aún tienen el valor por defecto genérico, ajustar al tiempo del circuito
        if self._var_hard_base_lap.get() == "01:24.500":
            self._var_hard_base_lap.set(self._format_seconds(base_lap_s))
            self._var_soft_base_lap.set(self._format_seconds(max(0.1, base_lap_s - 0.450)))

        if (new_champ, new_circ) != (last_champ, last_circ):
            self.load_tyre_profile()
            self._update_slider_bounds()
        else:
            self._refresh_tyre_models_list()

        self._lbl_sync_info.configure(
            text=f"🔗  Sincronizado con Módulo 2 (Combustible) · Circuito: {circ_name} · Vuelta Base: {self._format_seconds(base_lap_s)}"
        )
        self.recalculate_and_plot()

    def on_fuel_strategy_updated(self, fuel_data: dict):
        """Callback invocado por main.py cuando se navega o se actualiza la estrategia de combustible."""
        if not fuel_data:
            return
        self.fuel_data = fuel_data

        trunc_laps = fuel_data.get("truncated_laps", 43)
        self._var_total_laps.set(trunc_laps)

        # 1. Transferir restricciones de combustible: modos de paradas viables (mínimo 1 por reglamento)
        raw_viable = fuel_data.get("viable_modes", ["1 Parada", "2 Paradas"])
        viable_modes = [m for m in raw_viable if not m.startswith("0")]
        if not viable_modes:
            viable_modes = ["1 Parada"]
        self._available_stops_modes = viable_modes

        curr_vals = list(self._seg_stops.cget("values")) if hasattr(self._seg_stops, "cget") else []
        if curr_vals != viable_modes:
            self._seg_stops.configure(values=viable_modes)

        # 2. Asignar número de paradas validando que pertenezca a los viables
        num_stops = fuel_data.get("num_stops", 1)
        mode_str = f"{num_stops} Parada{'s' if num_stops > 1 else ''}"
        if mode_str not in viable_modes:
            mode_str = viable_modes[0]
            try:
                num_stops = int(mode_str.split()[0])
            except Exception:
                num_stops = 1

        self._var_num_stops.set(num_stops)
        self._seg_stops.set(mode_str)

        p1 = fuel_data.get("pit1_lap", 22)
        p2 = fuel_data.get("pit2_lap", 34)
        self._var_pit1_lap.set(p1)
        self._var_pit2_lap.set(p2)

        self._update_slider_bounds()

        circ_name = self.session_data.get("circuit", "Watkins Glen")
        base_lap_s = float(self.session_data.get("lap_time_seconds", 84.5))
        viable_summary = ", ".join(viable_modes)
        self._lbl_sync_info.configure(
            text=(
                f"🔗  Sincronizado con Módulo 2 (Combustible) · "
                f"Circuito: {circ_name} · Vueltas: {trunc_laps} · "
                f"Estrategias Viables: [{viable_summary}] · "
                f"Paradas: {num_stops} (V{p1}{f', V{p2}' if num_stops >= 2 else ''}) · "
                f"Vuelta Base (70L): {self._format_seconds(base_lap_s)}"
            )
        )
        self.recalculate_and_plot()

    def get_tyre_strategy_data(self) -> dict:
        """Exporta los parámetros de ritmo y degradación de neumáticos para el Módulo 4."""
        return {
            "hard_base_lap": self._get_hard_base_lap(),
            "hard_warmup": self._get_hard_warmup(),
            "hard_a": self._get_hard_a(),
            "hard_n": self._get_hard_n(),
            "soft_base_lap": self._get_soft_base_lap(),
            "soft_warmup": self._get_soft_warmup(),
            "soft_a": self._get_soft_a(),
            "soft_n": self._get_soft_n(),
            "active_model": self._var_selected_tyre_model.get(),
            "saved_models": list(self.saved_tyre_models.keys()),
        }

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
