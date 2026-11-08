"""
============================================================
 MÓDULO 2: Estrategia de Combustible — NIX Esports (v2.4)
============================================================
 Arquitectura Ultra-Robusta:
   - Separación estricta entre construcción de UI y actualización
     de datos: los sliders NO se destruyen en tiempo de ejecución
     mientras el usuario los arrastra, evitando congelamientos,
     pérdida de eventos del ratón y parpadeos.
   - Protección contra división por cero interna en CTkSlider
     cuando el rango viable de parada es de una sola vuelta.
   - Doble Filtro Matemático de Viabilidad:
       1. -20% límite inferior: descarta estrategias que exijan
          más del 20% de ahorro en cualquier stint.
       2. +10% límite superior (Over-stopping): descarta paradas
          adicionales que fragmenten la carrera en stints absurdamente
          pequeños habiendo opción viable anterior.
   - Sliders acotados estrictamente en el rango viable.
   - Cálculo en tiempo real por stint y parada:
       * Target de consumo L/v y semáforo (🟢 PUSH / 🟡 LIFT & COAST)
       * Remanente al entrar a box
       * Litros a cargar con límite físico estricto: Box + Cargar <= 70L
       * Tiempo de box y factor limitante (manguera vs gomas)
   - Persistencia automática de la estrategia por Campeonato + Circuito:
       profiles/<campeonato>/<circuito>_fuel.json
============================================================
"""

import customtkinter as ctk
import math
import json
import re
import sys
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

from modules.ui_responsive import HeaderLayout, ResponsiveGrid, WidthModes, bind_wraplength
from modules.ui_responsive import widget_scaling as _s

# Número máximo de paradas que modelan todos los módulos (neumáticos, estrategias, live)
MAX_SUPPORTED_STOPS = 2

APP_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
PROFILES_ROOT = APP_ROOT / "profiles"


class FuelStrategyModule(ctk.CTkFrame):
    """
    Módulo 2 — Estrategia de Combustible.
    Gestión multi-stint con arquitectura robusta de sliders desacoplados,
    doble filtro de viabilidad y persistencia por circuito.
    """

    def __init__(self, parent, colors: dict, **kwargs):
        super().__init__(parent, fg_color=colors["bg_primary"], **kwargs)
        self.colors = colors
        self.session_data: dict = {}

        # ── StringVars: Parámetros del Ingeniero ───────────────
        self._var_fuel_lap     = ctk.StringVar(value="2.15")   # Consumo base L/vuelta
        self._var_safety_fuel  = ctk.StringVar(value="2.5")    # Margen seguridad en LITROS
        self._var_weight_sens  = ctk.StringVar(value="0.015")  # Sensibilidad peso s/L

        # Modo de paradas seleccionado
        self._var_num_stops    = ctk.IntVar(value=1)
        self._available_stops_modes: list[str] = ["1 Parada"]
        self._rendered_mode: int | None = None  # Para saber si la estructura de UI ya está montada

        # Vueltas de parada seleccionadas
        self._var_pit1_lap     = ctk.IntVar(value=22)
        self._var_pit2_lap     = ctk.IntVar(value=34)

        # Tablas dinámicas
        self.fuel_saving_rows = []
        self.draft_rows = []

        # Modelos de combustible por circuito
        self.saved_fuel_models: dict = {}
        self._var_selected_fuel_model = ctk.StringVar(value="⚡ Modelo Base")

        # Resultados de cálculo global
        self.calc_results: dict = {}

        self._build_ui()
        self.auto_populate_saving_tables()
        self.calculate_strategy()

    # ═══════════════════════════════════════════════════════════
    #  CONSTRUCCIÓN DE LA INTERFAZ BASE
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

        accent_bar = ctk.CTkFrame(header, width=4, height=44, fg_color=self.colors["accent"])
        accent_bar.grid(row=0, column=0, sticky="nsw", padx=(0, 16))

        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.grid(row=0, column=1, sticky="w", pady=10)

        title_lbl = ctk.CTkLabel(
            title_box,
            text="ESTRATEGIA DE COMBUSTIBLE",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=self.colors["text_primary"],
        )
        title_lbl.pack(anchor="w")

        subtitle_lbl = ctk.CTkLabel(
            title_box,
            text="Control dinámico de paradas, targets de consumo L/v y límite estricto de tanque (70L)",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=self.colors["text_secondary"],
        )
        subtitle_lbl.pack(anchor="w")

        # Botones de Acción y Selector de Modelo de Combustible
        btn_box = ctk.CTkFrame(header, fg_color="transparent")
        btn_box.grid(row=0, column=2, padx=16, pady=10, sticky="e")

        self._cbo_fuel_models = ctk.CTkComboBox(
            btn_box,
            variable=self._var_selected_fuel_model,
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
            command=self._on_fuel_model_selected,
        )
        self._cbo_fuel_models.pack(side="left", padx=(0, 8))

        self._btn_save_profile = ctk.CTkButton(
            btn_box,
            text="💾  Guardar",
            width=90,
            height=34,
            corner_radius=8,
            fg_color=self.colors["accent"],
            hover_color=self.colors.get("accent_hover", self.colors.get("accent", "#FF7A2F")),
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=self.save_fuel_profile,
        )
        self._btn_save_profile.pack(side="left", padx=(0, 6))

        self._btn_reload_profile = ctk.CTkButton(
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
            command=self.reload_fuel_profile,
        )
        self._btn_reload_profile.pack(side="left", padx=(0, 6))

        self._btn_delete_profile = ctk.CTkButton(
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
            command=self.delete_fuel_profile,
        )
        self._btn_delete_profile.pack(side="left")

        # Responsive: botonera bajo el título y subtítulo con salto de línea si no caben
        self._header_layout = HeaderLayout(header, accent_bar, title_lbl, subtitle_lbl, btn_box)

    def _build_scroll(self):
        self._scroll = ctk.CTkScrollableFrame(
            self,
            fg_color=self.colors["bg_primary"],
            scrollbar_button_color=self.colors["border"],
            scrollbar_button_hover_color=self.colors["accent_dim"],
        )
        self._scroll.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        self._scroll.grid_columnconfigure(0, weight=1)

        # 1. Banner de Sesión
        self._build_session_banner()

        # 2. Inputs de Telemetría
        self._build_inputs_section()

        # 3. Desglose del Algoritmo Iterativo
        self._build_iterative_breakdown()

        # 4. Selector de paradas viables, sliders de stint y tarjetas por parada
        self._build_stints_section()

        # 5. Tablas dinámicas (Fuel Saving y Rebufo)
        self._build_dynamic_tables_section()

        ctk.CTkFrame(self._scroll, height=30, fg_color="transparent").pack()

    # ─── 1. Banner de Sesión ─────────────────────────────────
    def _build_session_banner(self):
        self._banner_frame = ctk.CTkFrame(
            self._scroll,
            fg_color=self.colors["bg_secondary"],
            corner_radius=10,
            border_width=1,
            border_color=self.colors["border"],
        )
        self._banner_frame.pack(fill="x", padx=32, pady=(16, 12))
        self._banner_frame.grid_columnconfigure(0, weight=1)

        self._banner_label = ctk.CTkLabel(
            self._banner_frame,
            text="ℹ️  Cargando datos de sesión...",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=self.colors["text_secondary"],
            anchor="w",
            justify="left",
        )
        self._banner_label.pack(fill="x", padx=16, pady=12)
        # Texto largo: salto de línea al ancho del banner en lugar de cortarse
        bind_wraplength(self._banner_label, self._banner_frame, margin=36)

    # ─── 2. Inputs de Telemetría ──────────────────────────────
    def _build_inputs_section(self):
        box = ctk.CTkFrame(
            self._scroll,
            fg_color=self.colors["bg_secondary"],
            corner_radius=10,
            border_width=1,
            border_color=self.colors["border"],
        )
        box.pack(fill="x", padx=32, pady=(0, 16))
        box.grid_columnconfigure((0, 1, 2, 3), weight=1)

        ctk.CTkLabel(
            box,
            text="⚙️  Parámetros de Telemetría de Combustible",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self.colors["accent"],
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=20, pady=(14, 12))

        # Input 1: Consumo base
        f1 = ctk.CTkFrame(box, fg_color="transparent")
        f1.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 16))
        ctk.CTkLabel(f1, text="Consumo Base (L/vuelta)", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color=self.colors["text_primary"]).pack(anchor="w")
        e1 = ctk.CTkEntry(f1, textvariable=self._var_fuel_lap, height=36, corner_radius=8, fg_color=self.colors["input_bg"], border_color=self.colors["border"], font=ctk.CTkFont(family="Segoe UI Mono", size=13))
        e1.pack(fill="x", pady=(4, 0))
        e1.bind("<FocusOut>", lambda ev: self._on_params_changed())
        e1.bind("<Return>", lambda ev: self._on_params_changed())

        # Input 2: Margen seguridad en LITROS
        f2 = ctk.CTkFrame(box, fg_color="transparent")
        f2.grid(row=1, column=1, sticky="ew", padx=14, pady=(0, 16))
        ctk.CTkLabel(f2, text="Margen Seguridad (Litros)", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color=self.colors["text_primary"]).pack(anchor="w")
        e2 = ctk.CTkEntry(f2, textvariable=self._var_safety_fuel, height=36, corner_radius=8, fg_color=self.colors["input_bg"], border_color=self.colors["border"], font=ctk.CTkFont(family="Segoe UI Mono", size=13))
        e2.pack(fill="x", pady=(4, 0))
        ctk.CTkLabel(f2, text="Aplicado en cada box y meta", font=ctk.CTkFont(family="Segoe UI", size=10), text_color=self.colors["text_secondary"]).pack(anchor="w", pady=(2, 0))
        e2.bind("<FocusOut>", lambda ev: self._on_params_changed())
        e2.bind("<Return>", lambda ev: self._on_params_changed())

        # Input 3: Sensibilidad peso
        f3 = ctk.CTkFrame(box, fg_color="transparent")
        f3.grid(row=1, column=2, sticky="ew", padx=14, pady=(0, 16))
        ctk.CTkLabel(f3, text="Efecto Peso (s / L)", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color=self.colors["text_primary"]).pack(anchor="w")
        e3 = ctk.CTkEntry(f3, textvariable=self._var_weight_sens, height=36, corner_radius=8, fg_color=self.colors["input_bg"], border_color=self.colors["border"], font=ctk.CTkFont(family="Segoe UI Mono", size=13))
        e3.pack(fill="x", pady=(4, 0))
        ctk.CTkLabel(f3, text="Delta tiempo por litro consumido", font=ctk.CTkFont(family="Segoe UI", size=10), text_color=self.colors["text_secondary"]).pack(anchor="w", pady=(2, 0))
        e3.bind("<FocusOut>", lambda ev: self._on_params_changed())
        e3.bind("<Return>", lambda ev: self._on_params_changed())

        # Botón Recalcular
        btn_calc = ctk.CTkButton(
            box,
            text="⚡  Recalcular Estrategia",
            height=38,
            corner_radius=8,
            fg_color=self.colors["accent"],
            hover_color=self.colors["accent_hover"],
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            command=self._on_params_changed,
        )
        btn_calc.grid(row=1, column=3, sticky="ew", padx=14, pady=(16, 16))

        # Responsive: 4 columnas (3 parámetros + botón) o 2x2 en ventanas estrechas.
        # El botón conserva su margen superior para alinearse con las cajas de texto.
        def _inputs_mode(width):
            return "wide" if width >= max(f.winfo_reqwidth() for f in (f1, f2, f3)) * 4 + 8 * 14 * _s(box) else "narrow"

        def _apply_inputs(mode):
            cols = 4 if mode == "wide" else 2
            for idx, w in enumerate((f1, f2, f3, btn_calc)):
                r, c = divmod(idx, cols)
                pady = (16, 16) if w is btn_calc else (0, 16)
                w.grid(row=1 + r, column=c, sticky="ew", padx=14, pady=pady)
            for c in range(4):
                box.grid_columnconfigure(c, weight=1 if c < cols else 0)

        self._inputs_modes = WidthModes(box, _inputs_mode, _apply_inputs)

    def _on_params_changed(self):
        self.auto_populate_saving_tables()
        self.calculate_strategy()

    # ─── 3. Desglose del Algoritmo Iterativo ──────────────────
    def _build_iterative_breakdown(self):
        wrapper = ctk.CTkFrame(self._scroll, fg_color="transparent")
        wrapper.pack(fill="x", padx=32, pady=(0, 16))
        wrapper.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            wrapper,
            text="🔄  Algoritmo de Recálculo Iterativo con Pérdida en Boxes",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color=self.colors["text_primary"],
        ).pack(anchor="w", pady=(0, 8))

        self._cards_grid = ctk.CTkFrame(
            wrapper,
            fg_color=self.colors["bg_secondary"],
            corner_radius=10,
            border_width=1,
            border_color=self.colors["border"],
        )
        self._cards_grid.pack(fill="x")
        self._cards_grid.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self._step_labels: dict[str, ctk.CTkLabel] = {}
        card_defs = [
            ("1. Vueltas Brutas",       "step_raw_laps",     0, 0, "Carrera / T_vuelta"),
            ("2. Combustible Bruto",    "step_raw_fuel",     0, 1, "Litros con reserva"),
            ("3. Paradas Mínimas",      "step_stops",        0, 2, "Límite tanque 70L"),
            ("4. Pérdida en Boxes",     "step_pit_loss",     0, 3, "Pitlane + Levantar + max(fuel, tyres)"),
            ("5. Tiempo Efectivo Pista","step_eff_time",     1, 0, "Duración - Boxes"),
            ("6. Vueltas Corregidas",   "step_corr_laps",    1, 1, "T_efectivo / T_vuelta"),
            ("7. Vueltas Truncadas Base","step_trunc_laps",  1, 2, "White Flag (+1 lap)"),
            ("8. Efecto Peso Total",    "step_weight_gain",  1, 3, "Ganancia por vaciado"),
        ]

        step_cards = []
        for title, key, r, c, sub in card_defs:
            card = ctk.CTkFrame(
                self._cards_grid,
                fg_color=self.colors["bg_primary"],
                corner_radius=8,
                border_width=1,
                border_color=self.colors["border"],
            )
            step_cards.append(card)

            ctk.CTkLabel(
                card,
                text=title,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color=self.colors["text_secondary"],
            ).pack(anchor="w", padx=12, pady=(10, 2))

            val_lbl = ctk.CTkLabel(
                card,
                text="—",
                font=ctk.CTkFont(family="Segoe UI Mono", size=18, weight="bold"),
                text_color=self.colors["accent"],
            )
            val_lbl.pack(anchor="w", padx=12, pady=(0, 2))
            self._step_labels[key] = val_lbl

            ctk.CTkLabel(
                card,
                text=sub,
                font=ctk.CTkFont(family="Segoe UI", size=10),
                text_color=self.colors["text_secondary"],
            ).pack(anchor="w", padx=12, pady=(0, 10))

        # Responsive: 8 tarjetas en 4 columnas (2 filas) o en 2 columnas si no caben
        self._steps_grid = ResponsiveGrid(self._cards_grid, step_cards, max_cols=4, min_col_width=205,
                                          grid_kw=dict(padx=10, pady=10, sticky="nsew"))

    # ─── 4. Sección de Paradas y Sliders Interactivos ─────────
    def _build_stints_section(self):
        self._stints_card = ctk.CTkFrame(
            self._scroll,
            fg_color=self.colors["bg_secondary"],
            corner_radius=10,
            border_width=1,
            border_color=self.colors["accent"],
        )
        self._stints_card.pack(fill="x", padx=32, pady=(0, 16))
        self._stints_card.grid_columnconfigure(0, weight=1)

        # Header de la card
        header = ctk.CTkFrame(self._stints_card, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(16, 6))

        stints_title = ctk.CTkLabel(
            header,
            text="🏁  Control de Paradas y Targets de Consumo",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=self.colors["accent"],
        )
        stints_title.pack(side="left")

        # Selector de estrategias viables
        selector_frame = ctk.CTkFrame(header, fg_color="transparent")
        selector_frame.pack(side="right")

        ctk.CTkLabel(
            selector_frame,
            text="Estrategias Viables:",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=self.colors["text_secondary"],
        ).pack(side="left", padx=(0, 8))

        self._seg_stops = ctk.CTkSegmentedButton(
            selector_frame,
            values=["1 Parada"],
            command=self._on_segmented_stops_changed,
            selected_color=self.colors["accent"],
            selected_hover_color=self.colors["accent_hover"],
            unselected_color=self.colors["bg_primary"],
            unselected_hover_color=self.colors["border"],
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
        )
        self._seg_stops.set("1 Parada")
        self._seg_stops.pack(side="left")

        # Responsive: el selector de paradas pasa bajo el título si no caben en una fila
        def _stints_hdr_mode(width):
            need = stints_title.winfo_reqwidth() + selector_frame.winfo_reqwidth() + 24 * _s(header)
            return "wide" if width >= need else "narrow"

        def _apply_stints_hdr(mode):
            stints_title.pack_forget()
            selector_frame.pack_forget()
            if mode == "wide":
                stints_title.pack(side="left")
                selector_frame.pack(side="right")
            else:
                stints_title.pack(side="top", anchor="w")
                selector_frame.pack(side="top", anchor="w", pady=(8, 0))

        self._stints_hdr_modes = WidthModes(header, _stints_hdr_mode, _apply_stints_hdr)

        # Subtítulo resumen
        self._stint_subtitle_lbl = ctk.CTkLabel(
            self._stints_card,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=self.colors["text_primary"],
        )
        self._stint_subtitle_lbl.pack(anchor="w", padx=20, pady=(0, 6))

        # Indicador Destacado: Gasolina Gratis al Cambiar Ruedas
        self._free_fuel_card = ctk.CTkFrame(
            self._stints_card,
            fg_color=self.colors["bg_primary"],
            corner_radius=8,
            border_width=1,
            border_color="#1E4620",
        )
        self._free_fuel_card.pack(fill="x", padx=20, pady=(0, 10))
        self._free_fuel_card.grid_columnconfigure(1, weight=1)

        badge_left = ctk.CTkFrame(self._free_fuel_card, fg_color="transparent")
        badge_left.grid(row=0, column=0, padx=(14, 10), pady=7, sticky="w")

        ctk.CTkLabel(
            badge_left,
            text="⛽ GASOLINA GRATIS (CAMBIO DE RUEDAS):",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#51CF66",
        ).pack(side="left")

        self._lbl_free_fuel_val = ctk.CTkLabel(
            badge_left,
            text="48.0 L",
            font=ctk.CTkFont(family="Segoe UI Mono", size=13, weight="bold"),
            text_color="#FFFFFF",
        )
        self._lbl_free_fuel_val.pack(side="left", padx=(8, 0))

        self._lbl_free_fuel_desc = ctk.CTkLabel(
            self._free_fuel_card,
            text="Cargar hasta 48.0 L no añade tiempo extra de parada (repostaje simultáneo con neumáticos).",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=self.colors["text_secondary"],
            anchor="w",
        )
        self._lbl_free_fuel_desc.grid(row=0, column=1, padx=(0, 14), pady=7, sticky="w")
        # Responsive: la explicación salta de línea en ventanas estrechas (descontando la insignia)
        bind_wraplength(self._lbl_free_fuel_desc, self._free_fuel_card, margin=330)

        # Contenedor dinámico de los stints y paradas
        self._stints_container = ctk.CTkFrame(self._stints_card, fg_color="transparent")
        self._stints_container.pack(fill="x", padx=20, pady=(0, 16))

    def _on_segmented_stops_changed(self, value: str):
        try:
            num = int(value.split()[0])
            self._var_num_stops.set(num)
        except Exception:
            self._var_num_stops.set(1)
        self.calculate_strategy()

    # ─── 5. Tablas Dinámicas (Fuel Saving y Rebufo) ───────────
    def _build_dynamic_tables_section(self):
        tables_wrapper = ctk.CTkFrame(
            self._scroll,
            fg_color=self.colors["bg_secondary"],
            corner_radius=10,
            border_width=1,
            border_color=self.colors["border"],
        )
        tables_wrapper.pack(fill="x", padx=32, pady=(0, 16))
        tables_wrapper.grid_columnconfigure((0, 1), weight=1)

        header_row = ctk.CTkFrame(tables_wrapper, fg_color="transparent")
        header_row.grid(row=0, column=0, columnspan=2, sticky="ew", padx=20, pady=(16, 12))

        tables_title = ctk.CTkLabel(
            header_row,
            text="📊  Tablas de Sensibilidad Dinámica (Autocalculadas para +1 y +2 Vueltas)",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color=self.colors["text_primary"],
            justify="left",
        )
        tables_title.pack(side="left")

        btn_regen = ctk.CTkButton(
            header_row,
            text="🔄  Regenerar Escalones (+1v, +2v)",
            height=30,
            corner_radius=6,
            fg_color=self.colors["bg_primary"],
            hover_color=self.colors["border"],
            border_width=1,
            border_color=self.colors["accent"],
            text_color=self.colors["accent"],
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            command=self._on_params_changed,
        )
        btn_regen.pack(side="right")

        # Responsive: el botón pasa bajo el título (que salta de línea) si no caben juntos
        # (ancho natural = máximo reqwidth observado; con salto de línea solo puede ser menor)
        title_nat = {"w": 0}

        def _tables_hdr_mode(width):
            title_nat["w"] = max(title_nat["w"], tables_title.winfo_reqwidth())
            return "wide" if width >= title_nat["w"] + btn_regen.winfo_reqwidth() + 16 * _s(header_row) else "narrow"

        def _apply_tables_hdr(mode):
            tables_title.pack_forget()
            btn_regen.pack_forget()
            if mode == "wide":
                tables_title.pack(side="left")
                btn_regen.pack(side="right")
            else:
                tables_title.pack(side="top", anchor="w")
                btn_regen.pack(side="top", anchor="w", pady=(8, 0))

        self._tables_hdr_modes = WidthModes(header_row, _tables_hdr_mode, _apply_tables_hdr)
        bind_wraplength(tables_title, header_row, margin=8)

        self._tabview = ctk.CTkTabview(
            tables_wrapper,
            fg_color=self.colors["bg_primary"],
            segmented_button_fg_color=self.colors["bg_secondary"],
            segmented_button_selected_color=self.colors["accent"],
            segmented_button_selected_hover_color=self.colors["accent_hover"],
            segmented_button_unselected_color=self.colors["bg_secondary"],
            segmented_button_unselected_hover_color=self.colors["border"],
            text_color=self.colors["text_primary"],
        )
        self._tabview.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=20, pady=(0, 20))

        tab_saving = self._tabview.add("📉 Ahorro de Combustible (Fuel Saving)")
        tab_draft  = self._tabview.add("💨 Va a Rebufo (Draft)")

        self._build_table_ui(tab_saving, is_draft=False)
        self._build_table_ui(tab_draft, is_draft=True)

    def _build_table_ui(self, parent, is_draft: bool):
        parent.grid_columnconfigure(0, weight=1)

        desc_text = (
            "Deltas de consumo al rebufo. Modifica el tiempo perdido/ganado según la telemetría en pista."
            if is_draft else
            "Escalones de ahorro calculados analíticamente para ganar 1, 2 o más vueltas por stint de 70L."
        )
        ctk.CTkLabel(
            parent,
            text=desc_text,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=self.colors["text_secondary"],
        ).pack(anchor="w", padx=10, pady=(6, 12))

        rows_container = ctk.CTkFrame(parent, fg_color=self.colors["bg_secondary"], corner_radius=8)
        rows_container.pack(fill="x", padx=10, pady=(0, 10))
        rows_container.grid_columnconfigure((0, 1, 2, 3, 4, 5), weight=1)

        headers = [
            "Objetivo",
            "Delta Ahorro (L/v)",
            "Delta Tiempo (s)",
            "Nuevo Consumo",
            "Autonomía Max",
            "Acciones",
        ]
        for col_idx, h_text in enumerate(headers):
            ctk.CTkLabel(
                rows_container,
                text=h_text,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color=self.colors["accent"],
            ).grid(row=0, column=col_idx, padx=8, pady=8, sticky="w")

        if is_draft:
            self._draft_container = rows_container
        else:
            self._saving_container = rows_container

        btn_add = ctk.CTkButton(
            parent,
            text="＋ Añadir Fila Manual",
            width=160,
            height=32,
            corner_radius=6,
            fg_color=self.colors["bg_secondary"],
            hover_color=self.colors["border"],
            border_width=1,
            border_color=self.colors["accent"],
            text_color=self.colors["accent"],
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=lambda: self._add_table_row(is_draft),
        )
        btn_add.pack(anchor="w", padx=10, pady=(4, 10))

    # ═══════════════════════════════════════════════════════════
    #  AUTOCÁLCULO ANALÍTICO DE TABLAS (+1 Y +2 VUELTAS EXTRA)
    # ═══════════════════════════════════════════════════════════

    def auto_populate_saving_tables(self):
        cons_base = self._get_base_consumption()
        tank_cap = float(self.session_data.get("fuel_capacity_l", 70.0))
        safety_l = self._get_safety_fuel_litres()
        usable_fuel = max(1.0, tank_cap - safety_l)

        base_laps = math.floor(usable_fuel / cons_base)

        new_saving_rows = []
        new_draft_rows = []

        targets = [
            ("+1 Vuelta Extra", 1, 0.35, -0.15),
            ("+2 Vueltas Extra", 2, 0.80, -0.28),
            ("+3 Vueltas Extra", 3, 1.35, -0.40),
        ]

        for label, extra_v, def_time_loss, def_draft_time in targets:
            target_laps = base_laps + extra_v
            req_cons = usable_fuel / target_laps
            delta_l = round(req_cons - cons_base, 3)

            new_saving_rows.append({
                "label": label,
                "delta_l": delta_l,
                "delta_s": def_time_loss,
            })

            new_draft_rows.append({
                "label": f"Rebufo {label}",
                "delta_l": delta_l,
                "delta_s": def_draft_time,
            })

        self.fuel_saving_rows = new_saving_rows
        self.draft_rows = new_draft_rows

        self._render_table_rows(is_draft=False)
        self._render_table_rows(is_draft=True)

    def _render_table_rows(self, is_draft: bool):
        if not hasattr(self, "_saving_container") or not hasattr(self, "_draft_container"):
            return

        container = self._draft_container if is_draft else self._saving_container
        data_list = self.draft_rows if is_draft else self.fuel_saving_rows

        for w in container.winfo_children():
            info = w.grid_info()
            if info and int(info.get("row", 0)) > 0:
                w.destroy()

        base_cons = self._get_base_consumption()
        tank_cap = float(self.session_data.get("fuel_capacity_l", 70.0))
        safety_l = self._get_safety_fuel_litres()
        usable_fuel = max(1.0, tank_cap - safety_l)
        base_autonomy = math.floor(usable_fuel / base_cons)

        for idx, row_data in enumerate(data_list):
            row_num = idx + 1
            label = row_data.get("label", f"Escalón {idx+1}")
            delta_l = row_data["delta_l"]
            delta_s = row_data["delta_s"]

            # Etiqueta
            ctk.CTkLabel(
                container,
                text=label,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color=self.colors["accent"],
            ).grid(row=row_num, column=0, padx=8, pady=4, sticky="w")

            # Entry Delta L
            v_l = ctk.StringVar(value=f"{delta_l:+.3f}")
            e_l = ctk.CTkEntry(
                container, textvariable=v_l, width=105, height=32,
                font=ctk.CTkFont(family="Segoe UI Mono", size=12, weight="bold"),
                justify="center",
                fg_color=self.colors["input_bg"], border_color=self.colors["border"]
            )
            e_l.grid(row=row_num, column=1, padx=8, pady=4, sticky="w")
            e_l.bind("<FocusOut>", lambda ev, i=idx, var=v_l, d=is_draft: self._on_cell_edited(i, "delta_l", var.get(), d))

            # Entry Delta S
            v_s = ctk.StringVar(value=f"{delta_s:+.2f}")
            e_s = ctk.CTkEntry(
                container, textvariable=v_s, width=105, height=32,
                font=ctk.CTkFont(family="Segoe UI Mono", size=12, weight="bold"),
                justify="center",
                fg_color=self.colors["input_bg"], border_color=self.colors["border"]
            )
            e_s.grid(row=row_num, column=2, padx=8, pady=4, sticky="w")
            e_s.bind("<FocusOut>", lambda ev, i=idx, var=v_s, d=is_draft: self._on_cell_edited(i, "delta_s", var.get(), d))

            # Nuevo Consumo
            new_cons = max(0.1, base_cons + delta_l)
            ctk.CTkLabel(
                container,
                text=f"{new_cons:.3f} L/v",
                font=ctk.CTkFont(family="Segoe UI Mono", size=12, weight="bold"),
                text_color=self.colors["text_primary"],
            ).grid(row=row_num, column=3, padx=8, pady=4, sticky="w")

            # Autonomía Máxima
            max_laps = math.floor(usable_fuel / new_cons)
            gain = max_laps - base_autonomy
            gain_str = f" (+{gain}v)" if gain > 0 else ""
            ctk.CTkLabel(
                container,
                text=f"{max_laps} vueltas{gain_str}",
                font=ctk.CTkFont(family="Segoe UI Mono", size=12),
                text_color=self.colors["success"] if gain > 0 else self.colors["text_secondary"],
            ).grid(row=row_num, column=4, padx=8, pady=4, sticky="w")

            # Botón eliminar fila
            ctk.CTkButton(
                container,
                text="✕",
                width=32,
                height=32,
                corner_radius=6,
                fg_color="#331111",
                hover_color="#551111",
                text_color="#FF6B6B",
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                command=lambda i=idx, d=is_draft: self._delete_table_row(i, d),
            ).grid(row=row_num, column=5, padx=8, pady=4, sticky="w")

    def _on_cell_edited(self, row_idx: int, field: str, value: str, is_draft: bool):
        data_list = self.draft_rows if is_draft else self.fuel_saving_rows
        if row_idx >= len(data_list):
            return
        try:
            val = float(value.replace(",", "."))
            data_list[row_idx][field] = val
            self._render_table_rows(is_draft)
            self.calculate_strategy()
        except ValueError:
            pass

    def _add_table_row(self, is_draft: bool):
        data_list = self.draft_rows if is_draft else self.fuel_saving_rows
        if data_list:
            last_l = data_list[-1]["delta_l"]
            last_s = data_list[-1]["delta_s"]
            data_list.append({"label": f"Manual {len(data_list)+1}", "delta_l": round(last_l - 0.05, 3), "delta_s": round(last_s + 0.35, 2)})
        else:
            data_list.append({"label": "Manual 1", "delta_l": -0.05, "delta_s": 0.25})
        self._render_table_rows(is_draft)

    def _delete_table_row(self, row_idx: int, is_draft: bool):
        data_list = self.draft_rows if is_draft else self.fuel_saving_rows
        if 0 <= row_idx < len(data_list):
            data_list.pop(row_idx)
            self._render_table_rows(is_draft)

    # ═══════════════════════════════════════════════════════════
    #  CÁLCULO MATEMÁTICO ITERATIVO DE COMBUSTIBLE
    # ═══════════════════════════════════════════════════════════

    def _get_base_consumption(self) -> float:
        try:
            return float(self._var_fuel_lap.get().replace(",", "."))
        except ValueError:
            return 2.15

    def _get_safety_fuel_litres(self) -> float:
        try:
            return float(self._var_safety_fuel.get().replace(",", "."))
        except ValueError:
            return 2.5

    def _get_weight_sensitivity(self) -> float:
        try:
            return float(self._var_weight_sens.get().replace(",", "."))
        except ValueError:
            return 0.015

    def _evaluate_viable_stop_strategies(self, total_laps: int, tank_cap: float, cons_lap: float, safety_l: float) -> list[str]:
        """
        Doble filtro de viabilidad en ingeniería de carrera:
          1. Paradas necesarias a Ritmo Normal (k_base):
             Calcula cuántas paradas se necesitan conduciendo a fondo sin Lift & Coast.
          2. Paradas necesarias con Ahorro Máximo 20% (k_save):
             Calcula si haciendo ahorro se puede eliminar una parada.
             Ambas opciones [k_save ... k_base] son VIABLES y se ofrecen al piloto.
          3. Filtro de Over-stopping para paradas adicionales (k_base + 1):
             Para 2 o más paradas, NO evalúa el último stint (que es un splash/remanente
             a meta con short-fueling), sino la longitud de los stints principales.
        """
        usable_fuel = max(1.0, tank_cap - safety_l)
        c_min = 0.80 * cons_lap  # Ahorro máximo 20%
        c_max = 1.10 * cons_lap  # Límite de over-stopping (+10% del base)

        # Autonomía a ritmo normal (sin Lift & Coast)
        laps_base = math.floor(usable_fuel / cons_lap)
        if laps_base < 1:
            laps_base = 1

        # Autonomía con ahorro máximo del 20%
        laps_save = math.floor(usable_fuel / c_min)
        if laps_save < 1:
            laps_save = 1

        # Paradas mínimas con ahorro (k_save) y a ritmo normal (k_base)
        # OBLIGATORIEDAD REGLAMENTO: Mínimo 1 parada obligatoria para cambio de compuesto
        k_save = max(1, math.ceil(total_laps / float(laps_save)) - 1)
        k_base = max(1, math.ceil(total_laps / float(laps_base)) - 1)

        viable_k = []
        # Todas las paradas desde k_save hasta k_base son viables por definición
        for k in range(k_save, k_base + 1):
            viable_k.append(k)

        # Evaluar opción de parada extra al sprint (k_base + 1)
        k_sprint = k_base + 1
        num_stints = k_sprint + 1

        # Para 2 o más paradas (3 o más stints), NO evaluamos el último stint (splash),
        # sino los stints principales completos:
        if num_stints >= 3:
            l_main_stints = total_laps / float(num_stints - 1)
            c_teorico_burn = usable_fuel / l_main_stints
        else:
            c_teorico_burn = usable_fuel / (total_laps / float(num_stints))

        if c_teorico_burn <= c_max:
            if k_sprint not in viable_k:
                viable_k.append(k_sprint)

        # Filtrar forzando estrictamente k >= 1 (normativa de cambio de gomas obligatorio)
        viable_k = sorted(list(set([k for k in viable_k if k >= 1])))
        # Neumáticos, Gráficos de Estrategia y Control en Vivo solo modelan 1 o 2 paradas:
        # no ofrecer modos de 3+ paradas que ningún módulo puede simular correctamente.
        min_viable = min(viable_k) if viable_k else 1
        self._unsupported_min_stops = min_viable if min_viable > MAX_SUPPORTED_STOPS else 0
        viable_k = [k for k in viable_k if k <= MAX_SUPPORTED_STOPS]
        if not viable_k:
            # Ninguna opción soportada es viable: se muestra la de más paradas soportadas
            # y el banner avisa de que la carrera exige más paradas de las que se modelan.
            viable_k = [MAX_SUPPORTED_STOPS] if self._unsupported_min_stops else [1]
        format_name = lambda k: f"{k} Parada{'s' if k > 1 else ''}"
        return [format_name(k) for k in viable_k]

    def calculate_strategy(self):
        """
        Ejecuta el ciclo de cálculo iterativo completo con los datos actuales.
        """
        champ_name    = self.session_data.get("championship_name", "God League 2024")
        circuit_name  = self.session_data.get("circuit", "Watkins Glen Boot")
        lap_time_s    = float(self.session_data.get("lap_time_seconds", 84.5))
        race_dur_s    = float(self.session_data.get("race_duration_s", 3600.0))
        tank_capacity = float(self.session_data.get("fuel_capacity_l", 70.0))
        refuel_rate   = float(self.session_data.get("refuel_rate_ls", 12.0))
        tyre_change_s = float(self.session_data.get("tyre_change_time", 4.0))
        car_lift_s    = float(self.session_data.get("car_lift_s") or self.session_data.get("car_lift_time") or 2.0)
        pitlane_loss  = float(self.session_data.get("pitlane_loss", 22.5))

        cons_lap      = self._get_base_consumption()
        safety_fuel_l = self._get_safety_fuel_litres()
        weight_sens   = self._get_weight_sensitivity()

        # ── Gasolina Gratis (T_ruedas * Refuel_rate) ─────────
        free_fuel_l = tyre_change_s * refuel_rate

        # Actualizar banner de sesión
        self._banner_label.configure(
            text=(
                f"🏁  {champ_name} | {circuit_name}  ·  "
                f"Vuelta Base: {self._format_seconds(lap_time_s)}  ·  "
                f"Duración: {int(race_dur_s // 60)} min  ·  "
                f"Depósito: {tank_capacity:.0f} L  ·  "
                f"Pitlane: {pitlane_loss:.1f} s  ·  "
                f"Levantar: {car_lift_s:.1f} s  ·  "
                f"Repostaje: {refuel_rate:.1f} L/s  ·  "
                f"Ruedas: {tyre_change_s:.1f} s  ·  "
                f"⛽ Gasolina Gratis: {free_fuel_l:.1f} L"
            ),
            text_color=self.colors["accent"],
        )

        if hasattr(self, "_lbl_free_fuel_val"):
            self._lbl_free_fuel_val.configure(text=f"{free_fuel_l:.1f} L")
        if hasattr(self, "_lbl_free_fuel_desc"):
            delta_penalty = (1.0 / refuel_rate) if refuel_rate > 0 else 0.0
            self._lbl_free_fuel_desc.configure(
                text=(
                    f"Cargar hasta {free_fuel_l:.1f} L en box cuesta 0.0s de tiempo extra "
                    f"({tyre_change_s:.1f}s ruedas × {refuel_rate:.1f} L/s). "
                    f"Cada litro por encima penaliza +{delta_penalty:.2f}s/L."
                )
            )

        # ── PASO 1: Vueltas brutas iniciales ──────────────────
        raw_laps = race_dur_s / lap_time_s

        # ── PASO 2: Combustible bruto inicial ─────────────────
        raw_fuel = (raw_laps * cons_lap) + safety_fuel_l

        # ── PASO 3: Paradas mínimas teóricas ──────────────────
        stint_usable_fuel = max(1.0, tank_capacity - safety_fuel_l)
        fuel_stops_req = 0 if raw_fuel <= tank_capacity else math.ceil((raw_fuel - tank_capacity) / stint_usable_fuel)
        # Por reglamento deportivo, el cambio de compuesto es obligatorio (mínimo 1 parada)
        min_stops_req = max(1, fuel_stops_req)

        # ── PASO 4: Pérdida real en boxes según paradas mínimas
        stops_to_simulate = max(1, min_stops_req)
        fuel_needed_in_pits = max(0.0, raw_fuel - tank_capacity)

        total_pit_loss_s = 0.0
        if stops_to_simulate > 0:
            fuel_per_pit = fuel_needed_in_pits / stops_to_simulate
            refuel_time = fuel_per_pit / refuel_rate
            box_time = car_lift_s + max(refuel_time, tyre_change_s)
            stop_time = pitlane_loss + box_time
            total_pit_loss_s = stops_to_simulate * stop_time

        # ── PASO 5: Tiempo efectivo de carrera en pista ───────
        effective_race_time_s = max(0.0, race_dur_s - total_pit_loss_s)

        # ── PASO 6: Vueltas estimadas corregidas ──────────────
        corrected_laps = effective_race_time_s / lap_time_s

        # ── PASO 7: Vueltas truncadas base (White Flag) ───────
        truncated_laps = math.floor(corrected_laps) + 1

        # ── PASO 8: Recálculo final consolidado con vueltas truncadas
        final_race_fuel = (truncated_laps * cons_lap) + safety_fuel_l

        # Efecto peso
        fuel_consumed_stint = tank_capacity - safety_fuel_l
        sec_gained_end_stint = fuel_consumed_stint * weight_sens

        # ── EVALUAR ESTRATEGIAS VIABLES (-20% Ahorro / +10% Over-stopping)
        viable_modes = self._evaluate_viable_stop_strategies(truncated_laps, tank_capacity, cons_lap, safety_fuel_l)
        self._available_stops_modes = viable_modes

        # Actualizar SegmentedButton evitando reconfiguraciones redundantes si existe en la UI
        if hasattr(self, "_seg_stops") and self._seg_stops is not None:
            current_vals = list(self._seg_stops.cget("values")) if hasattr(self._seg_stops, "cget") else []
            if current_vals != viable_modes:
                self._seg_stops.configure(values=viable_modes)

            k_curr = self._var_num_stops.get()
            current_str = "0 Paradas" if k_curr == 0 else f"{k_curr} Parada{'s' if k_curr > 1 else ''}"
            if current_str not in viable_modes:
                selected_mode = viable_modes[0]
                self._seg_stops.set(selected_mode)
                try:
                    self._var_num_stops.set(int(selected_mode.split()[0]))
                except Exception:
                    self._var_num_stops.set(1)
            else:
                self._seg_stops.set(current_str)
        else:
            k_curr = self._var_num_stops.get()
            current_str = "0 Paradas" if k_curr == 0 else f"{k_curr} Parada{'s' if k_curr > 1 else ''}"
            if current_str not in viable_modes and viable_modes:
                try:
                    self._var_num_stops.set(int(viable_modes[0].split()[0]))
                except Exception:
                    self._var_num_stops.set(1)

        num_stops = self._var_num_stops.get()

        # Guardar en memoria
        self.calc_results = {
            "truncated_laps": truncated_laps,
            "final_race_fuel": final_race_fuel,
            "min_stops_req": min_stops_req,
            "num_stops": num_stops,
            "tank_capacity": tank_capacity,
            "refuel_rate": refuel_rate,
            "tyre_change_s": tyre_change_s,
            "car_lift_s": car_lift_s,
            "pitlane_loss": pitlane_loss,
            "weight_sens": weight_sens,
            "cons_lap": cons_lap,
            "safety_fuel_l": safety_fuel_l,
            "free_fuel_l": free_fuel_l,
            "max_laps_per_stint_20": math.floor(stint_usable_fuel / (0.80 * cons_lap)),
        }

        # Actualizar labels superiores
        self._step_labels["step_raw_laps"].configure(text=f"{raw_laps:.2f} v")
        self._step_labels["step_raw_fuel"].configure(text=f"{raw_fuel:.1f} L")
        reg_note = " (reglamento)" if fuel_stops_req == 0 else ""
        self._step_labels["step_stops"].configure(text=f"{min_stops_req} mín.{reg_note} ({num_stops} selec.)")
        self._step_labels["step_pit_loss"].configure(text=f"{total_pit_loss_s:.1f} s")
        self._step_labels["step_eff_time"].configure(text=self._format_seconds_mm_ss(effective_race_time_s))
        self._step_labels["step_corr_laps"].configure(text=f"{corrected_laps:.2f} v")
        self._step_labels["step_trunc_laps"].configure(text=f"{truncated_laps} vueltas")
        self._step_labels["step_weight_gain"].configure(text=f"-{sec_gained_end_stint:.2f} s/v")

        # Construir o actualizar UI de stints y paradas
        self._refresh_stints_view()

    # ═══════════════════════════════════════════════════════════
    #  ARQUITECTURA DESACOPLADA DE SLIDERS Y CARDS DE STINTS
    # ═══════════════════════════════════════════════════════════

    def _refresh_stints_view(self):
        """
        Monta la estructura visual si cambia de modo (0, 1 o 2 paradas)
        o actualiza los rangos y textos si ya está montada.
        """
        if not hasattr(self, "_stints_card") or not self._stints_card or not hasattr(self, "_stints_container"):
            return

        num_stops = self._var_num_stops.get()
        res = self.calc_results
        total_laps = res.get("truncated_laps", 43)
        final_fuel = res.get("final_race_fuel", 90.0)
        l_max_20   = res.get("max_laps_per_stint_20", 39)

        viable_str = ", ".join(self._available_stops_modes)
        subtitle = f"Total: {total_laps} Vueltas  ·  Combustible: {final_fuel:.1f} L  ·  Estrategias Viables: [{viable_str}]"
        unsupported = getattr(self, "_unsupported_min_stops", 0)
        if unsupported:
            subtitle += (f"\n⚠️  Esta carrera exige al menos {unsupported} paradas y la calculadora solo modela "
                         f"hasta {MAX_SUPPORTED_STOPS}: el plan mostrado NO llega a meta sin ahorro extremo.")
        self._stint_subtitle_lbl.configure(
            text=subtitle,
            text_color=self.colors["danger"] if unsupported else self.colors["text_primary"],
        )

        # Si el modo renderizado ha cambiado, reconstruir el esqueleto de la sección
        if self._rendered_mode != num_stops:
            for w in self._stints_container.winfo_children():
                w.destroy()
            self._rendered_mode = num_stops

            if num_stops == 0:
                card = ctk.CTkFrame(self._stints_container, fg_color=self.colors["bg_primary"], corner_radius=8)
                card.pack(fill="x", pady=6)
                ctk.CTkLabel(card, text="✅ Carrera directa sin paradas en boxes (1 solo stint). Ahorro < 20%.", font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"), text_color=self.colors["success"]).pack(padx=16, pady=12)
                return

            if num_stops == 1:
                self._build_1_stop_widgets(total_laps, l_max_20)
            else:
                self._build_2_stops_widgets(total_laps, l_max_20)

        # En cualquier caso, actualizar los datos y labels
        if num_stops == 1:
            self._update_1_stop_data()
        elif num_stops == 2:
            self._update_2_stops_data()

    # ─── 1 PARADA: ESTRUCTURA DE WIDGETS FIJA ─────────────────
    def _build_1_stop_widgets(self, total_laps: int, l_max_20: int):
        p1_min = max(1, total_laps - l_max_20)
        p1_max = min(total_laps - 1, l_max_20)
        if p1_min >= p1_max:
            slider_from = p1_min
            slider_to = p1_min + 1
            steps = 1
        else:
            slider_from = p1_min
            slider_to = p1_max
            steps = max(1, p1_max - p1_min)

        p1 = self._var_pit1_lap.get()
        p1 = max(p1_min, min(p1_max, p1))
        self._var_pit1_lap.set(p1)

        # Frame del Slider
        self._s1_frame = ctk.CTkFrame(self._stints_container, fg_color=self.colors["bg_primary"], corner_radius=8, border_width=1, border_color=self.colors["border"])
        self._s1_frame.pack(fill="x", pady=(0, 10))
        self._s1_frame.grid_columnconfigure(1, weight=1)

        lbl_box = ctk.CTkFrame(self._s1_frame, fg_color="transparent")
        lbl_box.grid(row=0, column=0, padx=14, pady=10, sticky="w")
        ctk.CTkLabel(lbl_box, text="🛑 Parada 1 (Vuelta):", font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), text_color=self.colors["accent"]).pack(anchor="w")
        self._lbl_s1_range = ctk.CTkLabel(lbl_box, text=f"Rango Viable: V{p1_min} ➔ V{p1_max} (Ahorro ≤ 20%)", font=ctk.CTkFont(family="Segoe UI", size=10), text_color=self.colors["text_secondary"])
        self._lbl_s1_range.pack(anchor="w")

        self._slider_p1 = ctk.CTkSlider(
            self._s1_frame, from_=slider_from, to=slider_to, number_of_steps=steps,
            variable=self._var_pit1_lap, button_color=self.colors["accent"], progress_color=self.colors["accent_dim"],
            command=self._on_p1_slider_event,
        )
        self._slider_p1.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

        self._lbl_p1_val = ctk.CTkLabel(self._s1_frame, text=f"V{p1}", font=ctk.CTkFont(family="Segoe UI Mono", size=14, weight="bold"), text_color=self.colors["accent"], width=50)
        self._lbl_p1_val.grid(row=0, column=2, padx=14, pady=10, sticky="w")

        # Cards Stints (2 columnas)
        self._stints_grid = ctk.CTkFrame(self._stints_container, fg_color="transparent")
        self._stints_grid.pack(fill="x")
        self._stints_grid.grid_columnconfigure((0, 1), weight=1)

        # Card Stint 1
        c1 = ctk.CTkFrame(self._stints_grid, fg_color=self.colors["bg_primary"], corner_radius=8, border_width=1, border_color=self.colors["border"])
        c1.grid(row=0, column=0, padx=(0, 6), sticky="nsew")
        ctk.CTkLabel(c1, text="STINT 1 (Salida)", font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"), text_color=self.colors["accent"]).pack(anchor="w", padx=14, pady=(10, 4))
        self._lbl_s1_laps   = ctk.CTkLabel(c1, text="", font=ctk.CTkFont(family="Segoe UI Mono", size=12), text_color=self.colors["text_primary"])
        self._lbl_s1_laps.pack(anchor="w", padx=14, pady=2)
        self._lbl_s1_target = ctk.CTkLabel(c1, text="", font=ctk.CTkFont(family="Segoe UI Mono", size=12, weight="bold"))
        self._lbl_s1_target.pack(anchor="w", padx=14, pady=2)
        self._lbl_s1_state  = ctk.CTkLabel(c1, text="", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"))
        self._lbl_s1_state.pack(anchor="w", padx=14, pady=2)
        self._lbl_s1_box    = ctk.CTkLabel(c1, text="", font=ctk.CTkFont(family="Segoe UI Mono", size=12, weight="bold"), text_color=self.colors["accent"])
        self._lbl_s1_box.pack(anchor="w", padx=14, pady=(2, 10))

        # Card Stint 2
        c2 = ctk.CTkFrame(self._stints_grid, fg_color=self.colors["bg_primary"], corner_radius=8, border_width=1, border_color=self.colors["border"])
        c2.grid(row=0, column=1, padx=(6, 0), sticky="nsew")
        ctk.CTkLabel(c2, text="STINT 2 (Hacia Meta)", font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"), text_color=self.colors["accent"]).pack(anchor="w", padx=14, pady=(10, 4))
        self._lbl_s2_laps   = ctk.CTkLabel(c2, text="", font=ctk.CTkFont(family="Segoe UI Mono", size=12), text_color=self.colors["text_primary"])
        self._lbl_s2_laps.pack(anchor="w", padx=14, pady=2)
        self._lbl_s2_target = ctk.CTkLabel(c2, text="", font=ctk.CTkFont(family="Segoe UI Mono", size=12, weight="bold"))
        self._lbl_s2_target.pack(anchor="w", padx=14, pady=2)
        self._lbl_s2_state  = ctk.CTkLabel(c2, text="", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"))
        self._lbl_s2_state.pack(anchor="w", padx=14, pady=2)
        self._lbl_s2_meta   = ctk.CTkLabel(c2, text="", font=ctk.CTkFont(family="Segoe UI Mono", size=12, weight="bold"), text_color=self.colors["success"])
        self._lbl_s2_meta.pack(anchor="w", padx=14, pady=(2, 10))

        # Card Parada 1 Resumen
        self._pit1_card = ctk.CTkFrame(self._stints_container, fg_color=self.colors["sidebar_bg"], corner_radius=8, border_width=1, border_color=self.colors["accent_dim"])
        self._pit1_card.pack(fill="x", pady=(10, 0))
        self._pit1_card.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        self._lbl_pit1_title = ctk.CTkLabel(self._pit1_card, text="", font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), text_color="#FFA94D")
        self._lbl_pit1_title.grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self._lbl_pit1_load  = ctk.CTkLabel(self._pit1_card, text="", font=ctk.CTkFont(family="Segoe UI Mono", size=12, weight="bold"), text_color=self.colors["text_primary"])
        self._lbl_pit1_load.grid(row=0, column=1, padx=10, pady=10, sticky="w")
        self._lbl_pit1_free  = ctk.CTkLabel(self._pit1_card, text="", font=ctk.CTkFont(family="Segoe UI Mono", size=11, weight="bold"))
        self._lbl_pit1_free.grid(row=0, column=2, padx=10, pady=10, sticky="w")
        self._lbl_pit1_tank  = ctk.CTkLabel(self._pit1_card, text="", font=ctk.CTkFont(family="Segoe UI Mono", size=11), text_color=self.colors["text_secondary"])
        self._lbl_pit1_tank.grid(row=0, column=3, padx=10, pady=10, sticky="w")
        self._lbl_pit1_loss  = ctk.CTkLabel(self._pit1_card, text="", font=ctk.CTkFont(family="Segoe UI Mono", size=11, weight="bold"), text_color=self.colors["accent"])
        self._lbl_pit1_loss.grid(row=0, column=4, padx=10, pady=10, sticky="w")

    def _on_p1_slider_event(self, val: float):
        p1 = int(round(val))
        self._var_pit1_lap.set(p1)
        if hasattr(self, "_lbl_p1_val"):
            self._lbl_p1_val.configure(text=f"V{p1}")
        self._update_1_stop_data()

    def _update_1_stop_data(self):
        res = self.calc_results
        total_laps   = res.get("truncated_laps", 43)
        tank_cap     = res.get("tank_capacity", 70.0)
        cons_lap     = res.get("cons_lap", 2.15)
        safety_l     = res.get("safety_fuel_l", 2.5)
        refuel_rate  = res.get("refuel_rate", 12.0)
        tyre_change  = res.get("tyre_change_s", 4.0)
        car_lift_s   = res.get("car_lift_s", 2.0)
        pitlane_loss = res.get("pitlane_loss", 22.5)
        free_fuel_l  = res.get("free_fuel_l", tyre_change * refuel_rate)

        p1 = self._var_pit1_lap.get()
        p1 = max(1, min(total_laps - 1, p1))

        # Stint 1
        laps1 = p1
        fuel_start1 = tank_cap
        target_cons1 = (fuel_start1 - safety_l) / laps1 if laps1 > 0 else cons_lap

        if target_cons1 >= cons_lap:
            state1_color = self.colors["success"]
            state1_text = "🟢 PUSH (Ritmo Normal)"
            fuel_in_box1 = max(0.0, fuel_start1 - (laps1 * cons_lap))
        else:
            delta_save = target_cons1 - cons_lap
            state1_color = "#FFA94D"
            state1_text = f"🟡 LIFT & COAST ({delta_save:+.2f} L/v)"
            fuel_in_box1 = safety_l

        # Stint 2
        laps2 = total_laps - p1
        fuel_needed2 = (laps2 * cons_lap) + safety_l
        fuel_to_add_short = max(0.0, fuel_needed2 - fuel_in_box1)
        max_loadable = max(0.0, tank_cap - fuel_in_box1)
        if fuel_to_add_short > max_loadable:
            fuel_to_add_short = max_loadable

        fuel_start2 = fuel_in_box1 + fuel_to_add_short
        target_cons2 = (fuel_start2 - safety_l) / laps2 if laps2 > 0 else cons_lap

        if target_cons2 >= cons_lap:
            state2_text = "🟢 PUSH (Hacia Meta)"
            state2_color = self.colors["success"]
            fuel_at_finish = fuel_start2 - (laps2 * cons_lap)
        else:
            delta_save2 = target_cons2 - cons_lap
            state2_text = f"🟡 LIFT & COAST ({delta_save2:+.2f} L/v)"
            state2_color = "#FFA94D"
            fuel_at_finish = safety_l

        # Tiempos
        refuel_t = fuel_to_add_short / refuel_rate
        box_t = car_lift_s + max(refuel_t, tyre_change)
        limiting = "REPOSTAJE" if refuel_t > tyre_change else "NEUMÁTICOS"
        tot_loss = pitlane_loss + box_t

        # Estado de Gasolina Gratis
        if fuel_to_add_short <= free_fuel_l:
            free_text = f"⛽ {fuel_to_add_short:.1f}L Gratis (0s extra)"
            free_color = "#51CF66"
        else:
            excess = fuel_to_add_short - free_fuel_l
            extra_s = excess / refuel_rate if refuel_rate > 0 else 0.0
            free_text = f"⛽ {free_fuel_l:.1f}L gratis + {excess:.1f}L (+{extra_s:.1f}s ⚠️)"
            free_color = "#FFA94D"

        # Actualizar labels existentes (sin destruir nada)
        self._lbl_s1_laps.configure(text=f"• Vueltas: 1 ➔ {p1} ({laps1} v)")
        self._lbl_s1_target.configure(text=f"• Target Consumo: {target_cons1:.3f} L/v", text_color=state1_color)
        self._lbl_s1_state.configure(text=f"• Estado: {state1_text}", text_color=state1_color)
        self._lbl_s1_box.configure(text=f"• Litros al llegar a box: {fuel_in_box1:.2f} L")

        self._lbl_s2_laps.configure(text=f"• Vueltas: {p1 + 1} ➔ {total_laps} ({laps2} v)")
        self._lbl_s2_target.configure(text=f"• Target Consumo: {target_cons2:.3f} L/v", text_color=state2_color)
        self._lbl_s2_state.configure(text=f"• Estado: {state2_text}", text_color=state2_color)
        self._lbl_s2_meta.configure(text=f"• Litros al cruzar meta: {fuel_at_finish:.2f} L (reserva)")

        self._lbl_pit1_title.configure(text=f"🛑 PARADA 1 (Vuelta {p1})")
        self._lbl_pit1_load.configure(text=f"Box: {fuel_in_box1:.1f} L ➔ Cargar: {fuel_to_add_short:.1f} L")
        if hasattr(self, "_lbl_pit1_free"):
            self._lbl_pit1_free.configure(text=free_text, text_color=free_color)
        self._lbl_pit1_tank.configure(text=f"Sale con: {fuel_start2:.1f} L (Límite: {tank_cap:.0f}L)")
        self._lbl_pit1_loss.configure(text=f"Box: {box_t:.1f}s ({limiting}) | Total: {tot_loss:.1f}s")

    # ─── 2 PARADAS: ESTRUCTURA DE WIDGETS FIJA ─────────────────
    def _build_2_stops_widgets(self, total_laps: int, l_max_20: int):
        p1_min = max(1, total_laps - 2 * l_max_20)
        p1_max = min(total_laps - 2, l_max_20)
        if p1_min >= p1_max:
            s1_from = p1_min
            s1_to = p1_min + 1
            s1_steps = 1
        else:
            s1_from = p1_min
            s1_to = p1_max
            s1_steps = max(1, p1_max - p1_min)

        p1 = max(p1_min, min(p1_max, self._var_pit1_lap.get()))
        self._var_pit1_lap.set(p1)

        p2_min = max(p1 + 1, total_laps - l_max_20)
        p2_max = min(total_laps - 1, p1 + l_max_20)
        if p2_min >= p2_max:
            s2_from = p2_min
            s2_to = p2_min + 1
            s2_steps = 1
        else:
            s2_from = p2_min
            s2_to = p2_max
            s2_steps = max(1, p2_max - p2_min)

        p2 = max(p2_min, min(p2_max, self._var_pit2_lap.get()))
        self._var_pit2_lap.set(p2)

        # Slider 1
        f_s1 = ctk.CTkFrame(self._stints_container, fg_color=self.colors["bg_primary"], corner_radius=8, border_width=1, border_color=self.colors["border"])
        f_s1.pack(fill="x", pady=(0, 6))
        f_s1.grid_columnconfigure(1, weight=1)
        self._lbl_p1_title = ctk.CTkLabel(f_s1, text=f"🛑 Parada 1 (V{p1_min} ➔ V{p1_max}):", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color=self.colors["accent"])
        self._lbl_p1_title.grid(row=0, column=0, padx=14, pady=8, sticky="w")
        self._slider_p1 = ctk.CTkSlider(f_s1, from_=s1_from, to=s1_to, number_of_steps=s1_steps, variable=self._var_pit1_lap, button_color=self.colors["accent"], progress_color=self.colors["accent_dim"], command=self._on_p1_2stops_event)
        self._slider_p1.grid(row=0, column=1, padx=10, pady=8, sticky="ew")
        self._lbl_p1_val = ctk.CTkLabel(f_s1, text=f"V{p1}", font=ctk.CTkFont(family="Segoe UI Mono", size=13, weight="bold"), text_color=self.colors["accent"], width=45)
        self._lbl_p1_val.grid(row=0, column=2, padx=14, pady=8, sticky="w")

        # Slider 2
        f_s2 = ctk.CTkFrame(self._stints_container, fg_color=self.colors["bg_primary"], corner_radius=8, border_width=1, border_color=self.colors["border"])
        f_s2.pack(fill="x", pady=(0, 10))
        f_s2.grid_columnconfigure(1, weight=1)
        self._lbl_p2_title = ctk.CTkLabel(f_s2, text=f"🛑 Parada 2 (V{p2_min} ➔ V{p2_max}):", font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color=self.colors["accent"])
        self._lbl_p2_title.grid(row=0, column=0, padx=14, pady=8, sticky="w")
        self._slider_p2 = ctk.CTkSlider(f_s2, from_=s2_from, to=s2_to, number_of_steps=s2_steps, variable=self._var_pit2_lap, button_color=self.colors["accent"], progress_color=self.colors["accent_dim"], command=self._on_p2_2stops_event)
        self._slider_p2.grid(row=0, column=1, padx=10, pady=8, sticky="ew")
        self._lbl_p2_val = ctk.CTkLabel(f_s2, text=f"V{p2}", font=ctk.CTkFont(family="Segoe UI Mono", size=13, weight="bold"), text_color=self.colors["accent"], width=45)
        self._lbl_p2_val.grid(row=0, column=2, padx=14, pady=8, sticky="w")

        # Cards 3 Columnas
        grid_3 = ctk.CTkFrame(self._stints_container, fg_color="transparent")
        grid_3.pack(fill="x")
        grid_3.grid_columnconfigure((0, 1, 2), weight=1)

        # Stint 1
        c1 = ctk.CTkFrame(grid_3, fg_color=self.colors["bg_primary"], corner_radius=8, border_width=1, border_color=self.colors["border"])
        c1.grid(row=0, column=0, padx=4, sticky="nsew")
        ctk.CTkLabel(c1, text="STINT 1", font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), text_color=self.colors["accent"]).pack(anchor="w", padx=10, pady=(8, 2))
        self._lbl_2s1_laps   = ctk.CTkLabel(c1, text="", font=ctk.CTkFont(family="Segoe UI Mono", size=11))
        self._lbl_2s1_laps.pack(anchor="w", padx=10)
        self._lbl_2s1_target = ctk.CTkLabel(c1, text="", font=ctk.CTkFont(family="Segoe UI Mono", size=11, weight="bold"))
        self._lbl_2s1_target.pack(anchor="w", padx=10)
        self._lbl_2s1_box    = ctk.CTkLabel(c1, text="", font=ctk.CTkFont(family="Segoe UI Mono", size=11))
        self._lbl_2s1_box.pack(anchor="w", padx=10, pady=(0, 8))

        # Stint 2
        c2 = ctk.CTkFrame(grid_3, fg_color=self.colors["bg_primary"], corner_radius=8, border_width=1, border_color=self.colors["border"])
        c2.grid(row=0, column=1, padx=4, sticky="nsew")
        ctk.CTkLabel(c2, text="STINT 2", font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), text_color=self.colors["accent"]).pack(anchor="w", padx=10, pady=(8, 2))
        self._lbl_2s2_laps   = ctk.CTkLabel(c2, text="", font=ctk.CTkFont(family="Segoe UI Mono", size=11))
        self._lbl_2s2_laps.pack(anchor="w", padx=10)
        self._lbl_2s2_target = ctk.CTkLabel(c2, text="", font=ctk.CTkFont(family="Segoe UI Mono", size=11, weight="bold"))
        self._lbl_2s2_target.pack(anchor="w", padx=10)
        self._lbl_2s2_box    = ctk.CTkLabel(c2, text="", font=ctk.CTkFont(family="Segoe UI Mono", size=11))
        self._lbl_2s2_box.pack(anchor="w", padx=10, pady=(0, 8))

        # Stint 3
        c3 = ctk.CTkFrame(grid_3, fg_color=self.colors["bg_primary"], corner_radius=8, border_width=1, border_color=self.colors["border"])
        c3.grid(row=0, column=2, padx=4, sticky="nsew")
        ctk.CTkLabel(c3, text="STINT 3", font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), text_color=self.colors["accent"]).pack(anchor="w", padx=10, pady=(8, 2))
        self._lbl_2s3_laps   = ctk.CTkLabel(c3, text="", font=ctk.CTkFont(family="Segoe UI Mono", size=11))
        self._lbl_2s3_laps.pack(anchor="w", padx=10)
        self._lbl_2s3_target = ctk.CTkLabel(c3, text="", font=ctk.CTkFont(family="Segoe UI Mono", size=11, weight="bold"))
        self._lbl_2s3_target.pack(anchor="w", padx=10)
        self._lbl_2s3_meta   = ctk.CTkLabel(c3, text="", font=ctk.CTkFont(family="Segoe UI Mono", size=11))
        self._lbl_2s3_meta.pack(anchor="w", padx=10, pady=(0, 8))

        # Paradas 1 y 2 resumen
        self._pit_summary = ctk.CTkFrame(self._stints_container, fg_color=self.colors["sidebar_bg"], corner_radius=8, border_width=1, border_color=self.colors["accent_dim"])
        self._pit_summary.pack(fill="x", pady=(10, 0))
        self._pit_summary.grid_columnconfigure((0, 1), weight=1)

        self._lbl_2pit1_info = ctk.CTkLabel(self._pit_summary, text="", font=ctk.CTkFont(family="Segoe UI Mono", size=11, weight="bold"), text_color="#FFA94D", justify="left")
        self._lbl_2pit2_info = ctk.CTkLabel(self._pit_summary, text="", font=ctk.CTkFont(family="Segoe UI Mono", size=11, weight="bold"), text_color="#FFA94D", justify="left")
        # Responsive: las dos paradas lado a lado o una debajo de otra si no caben
        self._pit_summary_grid = ResponsiveGrid(self._pit_summary, [self._lbl_2pit1_info, self._lbl_2pit2_info],
                                                max_cols=2, min_col_width=440,
                                                grid_kw=dict(padx=12, pady=8, sticky="w"))
        for _lbl in (self._lbl_2pit1_info, self._lbl_2pit2_info):
            bind_wraplength(_lbl, self._pit_summary, margin=40)

    def _on_p1_2stops_event(self, val: float):
        p1 = int(round(val))
        self._var_pit1_lap.set(p1)
        if hasattr(self, "_lbl_p1_val"):
            self._lbl_p1_val.configure(text=f"V{p1}")

        res = self.calc_results
        total_laps = res.get("truncated_laps", 43)
        l_max_20   = res.get("max_laps_per_stint_20", 39)

        # Ajustar slider 2 si p1 se acerca
        p2_min = max(p1 + 1, total_laps - l_max_20)
        p2_max = min(total_laps - 1, p1 + l_max_20)
        if p2_min >= p2_max:
            s2_from = p2_min
            s2_to = p2_min + 1
            s2_steps = 1
        else:
            s2_from = p2_min
            s2_to = p2_max
            s2_steps = max(1, p2_max - p2_min)

        if hasattr(self, "_slider_p2"):
            cur_bounds = getattr(self, "_p2_slider_bounds", None)
            new_bounds = (s2_from, s2_to, s2_steps)
            if cur_bounds != new_bounds:
                self._p2_slider_bounds = new_bounds
                self._slider_p2.configure(from_=s2_from, to=s2_to, number_of_steps=s2_steps)
            if hasattr(self, "_lbl_p2_title"):
                self._lbl_p2_title.configure(text=f"🛑 Parada 2 (V{p2_min} ➔ V{p2_max}):")

        p2 = self._var_pit2_lap.get()
        if p2 < p2_min:
            p2 = p2_min
            self._var_pit2_lap.set(p2)
            if hasattr(self, "_lbl_p2_val"):
                self._lbl_p2_val.configure(text=f"V{p2}")
        elif p2 > p2_max:
            p2 = p2_max
            self._var_pit2_lap.set(p2)
            if hasattr(self, "_lbl_p2_val"):
                self._lbl_p2_val.configure(text=f"V{p2}")

        self._update_2_stops_data()

    def _on_p2_2stops_event(self, val: float):
        p2 = int(round(val))
        self._var_pit2_lap.set(p2)
        if hasattr(self, "_lbl_p2_val"):
            self._lbl_p2_val.configure(text=f"V{p2}")
        self._update_2_stops_data()

    def _update_2_stops_data(self):
        res = self.calc_results
        total_laps = res.get("truncated_laps", 43)
        tank_cap   = res.get("tank_capacity", 70.0)
        cons_lap   = res.get("cons_lap", 2.15)
        safety_l   = res.get("safety_fuel_l", 2.5)

        p1 = self._var_pit1_lap.get()
        p2 = self._var_pit2_lap.get()

        # Stint 1
        laps1 = p1
        fuel_start1 = tank_cap
        target_cons1 = (fuel_start1 - safety_l) / laps1 if laps1 > 0 else cons_lap
        state1_color = self.colors["success"] if target_cons1 >= cons_lap else "#FFA94D"
        fuel_in_box1 = max(0.0, fuel_start1 - (laps1 * cons_lap)) if target_cons1 >= cons_lap else safety_l

        # Stint 2
        laps2 = max(1, p2 - p1)
        fuel_needed2 = (laps2 * cons_lap) + safety_l
        fuel_to_add1 = min(tank_cap - fuel_in_box1, max(0.0, fuel_needed2 - fuel_in_box1))
        fuel_start2 = fuel_in_box1 + fuel_to_add1
        target_cons2 = (fuel_start2 - safety_l) / laps2 if laps2 > 0 else cons_lap
        state2_color = self.colors["success"] if target_cons2 >= cons_lap else "#FFA94D"
        fuel_in_box2 = max(0.0, fuel_start2 - (laps2 * cons_lap)) if target_cons2 >= cons_lap else safety_l

        # Stint 3
        laps3 = max(1, total_laps - p2)
        fuel_needed3 = (laps3 * cons_lap) + safety_l
        fuel_to_add2 = min(tank_cap - fuel_in_box2, max(0.0, fuel_needed3 - fuel_in_box2))
        fuel_start3 = fuel_in_box2 + fuel_to_add2
        target_cons3 = (fuel_start3 - safety_l) / laps3 if laps3 > 0 else cons_lap
        state3_color = self.colors["success"] if target_cons3 >= cons_lap else "#FFA94D"

        refuel_rate  = res.get("refuel_rate", 12.0)
        tyre_change  = res.get("tyre_change_s", 4.0)
        free_fuel_l  = res.get("free_fuel_l", tyre_change * refuel_rate)

        # Tags de gasolina gratis para parada 1 y parada 2
        if fuel_to_add1 <= free_fuel_l:
            tag1 = f"Gratis ✅ ({fuel_to_add1:.1f}/{free_fuel_l:.1f}L)"
        else:
            ex1 = fuel_to_add1 - free_fuel_l
            t_ex1 = ex1 / refuel_rate if refuel_rate > 0 else 0.0
            tag1 = f"+{ex1:.1f}L penalizan (+{t_ex1:.1f}s ⚠️)"

        if fuel_to_add2 <= free_fuel_l:
            tag2 = f"Gratis ✅ ({fuel_to_add2:.1f}/{free_fuel_l:.1f}L)"
        else:
            ex2 = fuel_to_add2 - free_fuel_l
            t_ex2 = ex2 / refuel_rate if refuel_rate > 0 else 0.0
            tag2 = f"+{ex2:.1f}L penalizan (+{t_ex2:.1f}s ⚠️)"

        # Actualizar labels
        self._lbl_2s1_laps.configure(text=f"• 1 ➔ {p1} ({laps1} v)")
        self._lbl_2s1_target.configure(text=f"• Target: {target_cons1:.3f} L/v", text_color=state1_color)
        self._lbl_2s1_box.configure(text=f"• Box 1 con: {fuel_in_box1:.1f} L")

        self._lbl_2s2_laps.configure(text=f"• {p1+1} ➔ {p2} ({laps2} v)")
        self._lbl_2s2_target.configure(text=f"• Target: {target_cons2:.3f} L/v", text_color=state2_color)
        self._lbl_2s2_box.configure(text=f"• Box 2 con: {fuel_in_box2:.1f} L")

        self._lbl_2s3_laps.configure(text=f"• {p2+1} ➔ {total_laps} ({laps3} v)")
        self._lbl_2s3_target.configure(text=f"• Target: {target_cons3:.3f} L/v", text_color=state3_color)
        self._lbl_2s3_meta.configure(text=f"• Meta con: {safety_l:.1f} L")

        self._lbl_2pit1_info.configure(text=f"🛑 PIT 1 (V{p1}): Cargar {fuel_to_add1:.1f}L [{tag1}] ➔ Sale con {fuel_start2:.1f}L")
        self._lbl_2pit2_info.configure(text=f"🛑 PIT 2 (V{p2}): Cargar {fuel_to_add2:.1f}L [{tag2}] ➔ Sale con {fuel_start3:.1f}L")

    # ═══════════════════════════════════════════════════════════
    #  PERSISTENCIA POR CAMPEONATO + CIRCUITO (MODELOS DE COMBUSTIBLE)
    # ═══════════════════════════════════════════════════════════

    def _get_profile_path(self) -> Path | None:
        champ = self.session_data.get("championship_name")
        circuit = self.session_data.get("circuit")
        if not champ or not circuit:
            return None
        safe_champ = re.sub(r'[\\/*?:"<>|]', "_", champ)
        safe_circ  = re.sub(r'[\\/*?:"<>|]', "_", circuit)
        return PROFILES_ROOT / safe_champ / f"{safe_circ}_fuel.json"

    def _get_fuel_models_path(self) -> Path | None:
        champ = self.session_data.get("championship_name")
        circuit = self.session_data.get("circuit")
        if not champ or not circuit:
            return None
        safe_champ = re.sub(r'[\\/*?:"<>|]', "_", champ)
        safe_circ  = re.sub(r'[\\/*?:"<>|]', "_", circuit)
        return PROFILES_ROOT / safe_champ / f"{safe_circ}_fuel_models.json"

    def _load_saved_fuel_models_dict(self) -> dict:
        m_path = self._get_fuel_models_path()
        if m_path and m_path.exists():
            try:
                data = json.loads(m_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:
                pass

        # Retrocompatibilidad: si existe _fuel.json, importarlo como modelo
        f_path = self._get_profile_path()
        if f_path and f_path.exists():
            try:
                data = json.loads(f_path.read_text(encoding="utf-8"))
                model_name = data.get("active_model", "Modelo 1")
                legacy_models = {model_name: data}
                if m_path:
                    m_path.parent.mkdir(parents=True, exist_ok=True)
                    m_path.write_text(json.dumps(legacy_models, ensure_ascii=False, indent=2), encoding="utf-8")
                return legacy_models
            except Exception:
                pass
        return {}

    def _refresh_fuel_models_list(self):
        self.saved_fuel_models = self._load_saved_fuel_models_dict()
        vals = ["⚡ Modelo Base"] + list(self.saved_fuel_models.keys())
        if hasattr(self, "_cbo_fuel_models"):
            self._cbo_fuel_models.configure(values=vals)
            if self._var_selected_fuel_model.get() not in vals:
                self._var_selected_fuel_model.set(vals[0])

    def _apply_fuel_model_data(self, data: dict):
        self._var_fuel_lap.set(str(data.get("fuel_lap", "2.15")))
        self._var_safety_fuel.set(str(data.get("safety_fuel", "2.5")))
        self._var_weight_sens.set(str(data.get("weight_sens", "0.015")))
        self._var_num_stops.set(data.get("num_stops", 1))
        self._var_pit1_lap.set(data.get("pit1_lap", 20))
        self._var_pit2_lap.set(data.get("pit2_lap", 32))
        if "fuel_saving_rows" in data and data["fuel_saving_rows"]:
            self.fuel_saving_rows = data["fuel_saving_rows"]
            self._render_table_rows(is_draft=False)
        if "draft_rows" in data and data["draft_rows"]:
            self.draft_rows = data["draft_rows"]
            self._render_table_rows(is_draft=True)
        self.calculate_strategy()

    def _on_fuel_model_selected(self, name: str):
        if name == "⚡ Modelo Base":
            f_path = self._get_profile_path()
            if f_path and f_path.exists():
                try:
                    data = json.loads(f_path.read_text(encoding="utf-8"))
                    self._apply_fuel_model_data(data)
                    return
                except Exception:
                    pass
            circ_cons = str(self.session_data.get("fuel_per_lap_l", "2.15"))
            self._var_fuel_lap.set(circ_cons)
            self._var_safety_fuel.set("2.5")
            self._var_weight_sens.set("0.015")
            self._var_num_stops.set(1)
            self.auto_populate_saving_tables()
            self.calculate_strategy()
            return

        data = self.saved_fuel_models.get(name)
        if data:
            self._apply_fuel_model_data(data)

    def save_fuel_profile(self):
        """Guarda el modelo de combustible actual con un nombre."""
        m_path = self._get_fuel_models_path()
        if not m_path:
            messagebox.showwarning("Sin sesión", "Guarda primero un campeonato y circuito en el Módulo 1.")
            return

        curr = self._var_selected_fuel_model.get()
        default_name = curr if curr != "⚡ Modelo Base" else "Carrera Seco"
        dialog = ctk.CTkInputDialog(
            text=f"Nombre identificativo del modelo de combustible:\n(Circuito: {self.session_data.get('circuit')})",
            title="Guardar Modelo de Combustible"
        )
        name = dialog.get_input()
        if not name or not name.strip():
            return
        name = name.strip()

        data = {
            "fuel_lap": self._var_fuel_lap.get(),
            "safety_fuel": self._var_safety_fuel.get(),
            "weight_sens": self._var_weight_sens.get(),
            "num_stops": self._var_num_stops.get(),
            "pit1_lap": self._var_pit1_lap.get(),
            "pit2_lap": self._var_pit2_lap.get(),
            "fuel_saving_rows": self.fuel_saving_rows,
            "draft_rows": self.draft_rows,
        }

        self.saved_fuel_models[name] = data
        m_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            m_path.write_text(json.dumps(self.saved_fuel_models, ensure_ascii=False, indent=2), encoding="utf-8")
            # Sincronizar también _fuel.json como modelo activo
            f_path = self._get_profile_path()
            if f_path:
                active_data = dict(data)
                active_data["active_model"] = name
                f_path.write_text(json.dumps(active_data, ensure_ascii=False, indent=2), encoding="utf-8")

            self._refresh_fuel_models_list()
            self._var_selected_fuel_model.set(name)
            messagebox.showinfo("Guardado", f"Modelo de combustible '{name}' guardado correctamente para:\n{self.session_data.get('circuit')}")
        except Exception as e:
            messagebox.showerror("Error al guardar", str(e))

    def load_fuel_profile(self) -> bool:
        """Carga el modelo activo para el campeonato+circuito activo."""
        self._refresh_fuel_models_list()
        f_path = self._get_profile_path()
        if f_path and f_path.exists():
            try:
                data = json.loads(f_path.read_text(encoding="utf-8"))
                active_name = data.get("active_model")
                if active_name and active_name in self.saved_fuel_models:
                    self._var_selected_fuel_model.set(active_name)
                    self._apply_fuel_model_data(self.saved_fuel_models[active_name])
                    return True
                else:
                    self._apply_fuel_model_data(data)
                    return True
            except Exception:
                pass

        if self.saved_fuel_models:
            first_name = list(self.saved_fuel_models.keys())[0]
            self._var_selected_fuel_model.set(first_name)
            self._apply_fuel_model_data(self.saved_fuel_models[first_name])
            return True

        return False

    def reload_fuel_profile(self):
        """Recarga la configuración del modelo de combustible seleccionado desde disco."""
        m_path = self._get_fuel_models_path()
        f_path = self._get_profile_path()
        if (not m_path or not m_path.exists()) and (not f_path or not f_path.exists()):
            messagebox.showinfo("Sin modelos guardados", "No hay modelos de combustible guardados en disco para este circuito.")
            return

        self._refresh_fuel_models_list()
        curr = self._var_selected_fuel_model.get()
        self._on_fuel_model_selected(curr)
        messagebox.showinfo("Recargado", f"Modelo de combustible '{curr}' recargado desde disco.")

    def delete_fuel_profile(self):
        """Elimina el modelo de combustible seleccionado."""
        name = self._var_selected_fuel_model.get()
        if name == "⚡ Modelo Base":
            messagebox.showinfo("Aviso", "El 'Modelo Base' no se puede eliminar ya que representa los valores base del circuito.")
            return

        confirm = messagebox.askyesno(
            "Borrar Modelo",
            f"¿Estás seguro de que deseas eliminar el modelo de combustible '{name}'?",
            icon="warning"
        )
        if not confirm:
            return

        if name in self.saved_fuel_models:
            del self.saved_fuel_models[name]
            m_path = self._get_fuel_models_path()
            if m_path:
                m_path.write_text(json.dumps(self.saved_fuel_models, ensure_ascii=False, indent=2), encoding="utf-8")
            self._refresh_fuel_models_list()
            self._var_selected_fuel_model.set("⚡ Modelo Base")
            self._on_fuel_model_selected("⚡ Modelo Base")
            messagebox.showinfo("Eliminado", f"Modelo de combustible '{name}' eliminado exitosamente.")

    # ═══════════════════════════════════════════════════════════
    #  API PÚBLICA Y UTILIDADES
    # ═══════════════════════════════════════════════════════════

    def get_fuel_strategy_data(self) -> dict:
        """Retorna el estado de paradas y stints calculado por el Módulo de Combustible."""
        num_stops = self._var_num_stops.get()
        p1 = self._var_pit1_lap.get()
        p2 = self._var_pit2_lap.get()
        res = self.calc_results
        # Exportar siempre vueltas de parada dentro de la carrera (1 <= p1 < p2 < total)
        total = int(res.get("truncated_laps", 0) or 0)
        if total >= 2:
            p1 = max(1, min(total - 1, int(p1)))
        if total >= 3:
            p2 = max(p1 + 1, min(total - 1, int(p2)))
        return {
            "num_stops": num_stops,
            "pit1_lap": p1,
            "pit2_lap": p2,
            "truncated_laps": res.get("truncated_laps", 43),
            "pitlane_loss": res.get("pitlane_loss", 22.5),
            "refuel_rate": res.get("refuel_rate", 12.0),
            "tyre_change_s": res.get("tyre_change_s", 4.0),
            "car_lift_s": res.get("car_lift_s", 2.0),
            "cons_lap": self._get_base_consumption(),
            "safety_fuel_l": self._get_safety_fuel_litres(),
            "weight_sens": self._get_weight_sensitivity(),
            "lap_time_s": float(self.session_data.get("lap_time_seconds", 84.5)),
            "calc_results": res,
            "viable_modes": getattr(self, "_available_stops_modes", ["1 Parada", "2 Paradas"]),
            "active_model": self._var_selected_fuel_model.get(),
            "saved_models": list(self.saved_fuel_models.keys()),
            "fuel_saving_rows": list(self.fuel_saving_rows),
            "draft_rows": list(self.draft_rows),
        }

    def on_session_data_updated(self, session_data: dict):
        """Callback invocado por main.py cuando se actualizan los datos de sesión."""
        if not session_data:
            return
        last_champ = self.session_data.get("championship_name") if hasattr(self, "session_data") and self.session_data else None
        last_circ = self.session_data.get("circuit") if hasattr(self, "session_data") and self.session_data else None
        new_champ = session_data.get("championship_name")
        new_circ = session_data.get("circuit")

        self.session_data = session_data

        # Solo recargar de disco o repoblar si cambió el campeonato o circuito
        if (new_champ, new_circ) != (last_champ, last_circ):
            loaded = self.load_fuel_profile()
            if not loaded:
                self.auto_populate_saving_tables()

        self.calculate_strategy()

    @staticmethod
    def _format_seconds(seconds: float) -> str:
        if seconds <= 0:
            return "00:00.000"
        m = int(seconds // 60)
        s = seconds % 60
        return f"{m:02d}:{s:06.3f}"

    @staticmethod
    def _format_seconds_mm_ss(seconds: float) -> str:
        if seconds <= 0:
            return "00:00"
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m:02d}:{s:02d}"
