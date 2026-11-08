"""
================================================================================
 MÓDULO 5: Gestión de Carrera en Directo y Live Timing (Team NIX Esports)
 Suite Universal de Estrategia de Carrera — iRacing
 Archivo: modules/live_control.py
================================================================================
 Funcionalidades:
   - Panel de Control de Carrera (Race Control) con seguimiento del líder,
     reloj en cuenta regresiva y cálculo en caliente de la regla White Flag (+1 vuelta).
   - Muro paralelo de 3 pilotos visibles y gestionables simultáneamente en 3 columnas.
   - Por cada piloto:
     * Carga de estrategias guardadas o estrategia óptima.
     * "Vuelta Cero del Neumático" (vida inicial de la goma).
     * Barra de entrada rápida al cruzar por meta [V] [Litros] + <Return>.
     * Tabla rellenable interactiva de pasos por meta (Vuelta, Litros, Consumo L/v).
     * Cálculo de Delta de Combustible vs Plan (surplus/déficit en Litros).
     * Recálculo dinámico de Litros a Cargar en la próxima parada.
     * Semáforo HUD de consumo: 🟢 PUSH | 🟡 ON TARGET | 🔴 LIFT & COAST.
     * Timeline visual compacto de stints.
     * Sub-panel Optimizador Táctico en Vivo (SC, Rebufo, parada barata bajo SC).
     * Botón "🚀 Promover a Estrategia Activa" para adoptar la táctica en caliente.
   - Persistencia completa en profiles/<campeonato>/<circuito>_live.json.
================================================================================
"""

import json
import math
import re
import sys
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
import numpy as np

from modules.ui_responsive import ResponsiveGrid

APP_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
PROFILES_ROOT = APP_ROOT / "profiles"


def lap_time_to_seconds(time_str: str) -> float:
    """Convierte formato MM:SS.mmm o SS.mmm a segundos flotantes."""
    time_str = str(time_str).strip()
    if not time_str:
        return 84.5
    if ":" in time_str:
        parts = time_str.split(":")
        try:
            return float(parts[0]) * 60.0 + float(parts[1])
        except ValueError:
            return 84.5
    try:
        return float(time_str)
    except ValueError:
        return 84.5


def format_seconds_to_lap(seconds: float) -> str:
    """Convierte segundos a formato MM:SS.mmm."""
    if seconds < 0:
        return "00:00.000"
    mins = int(seconds // 60)
    secs = seconds % 60
    return f"{mins:02d}:{secs:06.3f}"


def format_seconds_to_clock(seconds: float) -> str:
    """Convierte segundos a formato HH:MM:SS."""
    if seconds <= 0:
        return "00:00:00"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def parse_clock_to_seconds(clock_str: str) -> float:
    """Convierte formato HH:MM:SS, MM:SS o número de minutos a segundos flotantes."""
    s = str(clock_str).strip()
    if not s:
        return 3600.0
    if ":" in s:
        parts = s.split(":")
        try:
            if len(parts) == 3:
                return float(parts[0]) * 3600.0 + float(parts[1]) * 60.0 + float(parts[2])
            elif len(parts) == 2:
                return float(parts[0]) * 60.0 + float(parts[1])
        except ValueError:
            return 3600.0
    try:
        val = float(s)
        if val <= 180:
            return val * 60.0
        return val
    except ValueError:
        return 3600.0


# ================================================================================
#  CLASE: RaceControlHeader (Reloj Global de Carrera y Proyección del Líder)
# ================================================================================
class RaceControlHeader(ctk.CTkFrame):
    """Panel superior con el estado general de la carrera y el ritmo del líder."""

    def __init__(self, parent, colors: dict, on_update_callback=None, **kwargs):
        super().__init__(parent, fg_color=colors["bg_secondary"], corner_radius=10, border_width=1, border_color=colors["border"], **kwargs)
        self.colors = colors
        self.on_update_callback = on_update_callback
        self.session_data: dict = {}

        self._var_leader_lap      = ctk.StringVar(value="0")
        self._var_leader_pace     = ctk.StringVar(value="01:24.500")
        self._var_leader_strategy = ctk.StringVar(value="1 Parada (Tanque Lleno)")
        self._var_race_dur_min    = ctk.StringVar(value="60")
        self._var_time_rem_str    = ctk.StringVar(value="01:00:00")

        self._build_ui()

    def update_session_params(self, session_data: dict):
        self.session_data = session_data or {}
        if "lap_time_str" in self.session_data:
            self._var_leader_pace.set(self.session_data["lap_time_str"])
        if "race_duration_s" in self.session_data:
            dur_m = int(float(self.session_data["race_duration_s"]) / 60.0)
            self._var_race_dur_min.set(str(dur_m))
            try:
                l_lap = int(str(self._var_leader_lap.get()).strip())
            except ValueError:
                l_lap = 0
            if l_lap == 0:
                self._var_time_rem_str.set(format_seconds_to_clock(float(self.session_data["race_duration_s"])))
        self._on_params_changed()

    def _get_leader_pit_loss_seconds(self) -> float:
        """Calcula el tiempo perdido en paradas por el líder según las paradas restantes configuradas."""
        pitlane_loss_s = float(self.session_data.get("pitlane_loss_s") or self.session_data.get("pitlane_loss") or 30.0)
        tank_cap = float(self.session_data.get("fuel_capacity_l", 70.0))
        refuel_rate = float(self.session_data.get("refuel_rate_ls", 12.0))
        tyre_change_s = float(self.session_data.get("tyre_change_s") or self.session_data.get("tyre_change_time") or 4.0)
        car_lift_s = float(self.session_data.get("car_lift_s") or self.session_data.get("car_lift_time") or 2.0)

        # 1ª Parada: Llenar tanque lleno (en paralelo con ruedas) + levantar coche + pérdida por pitlane
        refuel_time = tank_cap / max(0.1, refuel_rate)
        t_first = pitlane_loss_s + car_lift_s + max(refuel_time, tyre_change_s)

        # Última Parada: Solamente cambiar ruedas + levantar coche + pérdida por pitlane
        t_last = pitlane_loss_s + car_lift_s + tyre_change_s

        mode = self._var_leader_strategy.get()
        if "0" in mode:
            return 0.0
        elif "Solo Ruedas" in mode:
            return t_last
        elif "1 Parada" in mode:
            return t_first
        elif "2" in mode:
            return t_first + t_last
        return 0.0

    def _build_ui(self):
        self.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        # 1. Título y Estrategia del Líder (Paradas Restantes)
        f_strat = ctk.CTkFrame(self, fg_color="transparent")
        f_strat.grid(row=0, column=0, padx=14, pady=10, sticky="w")

        ctk.CTkLabel(
            f_strat,
            text="🏁 CONTROL DE CARRERA",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=self.colors["accent"],
        ).pack(anchor="w")

        ctk.CTkLabel(
            f_strat,
            text="Paradas Restantes Líder:",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=self.colors["text_secondary"],
        ).pack(anchor="w", pady=(2, 0))

        self._cbo_leader_strat = ctk.CTkComboBox(
            f_strat,
            values=[
                "0 Paradas (No para)",
                "1 Parada (Tanque Lleno)",
                "1 Parada (Solo Ruedas)",
                "2 Paradas (1ª Tanque + 2ª Ruedas)",
            ],
            variable=self._var_leader_strategy,
            width=190,
            height=26,
            font=ctk.CTkFont(family="Segoe UI", size=10),
            dropdown_font=ctk.CTkFont(family="Segoe UI", size=10),
            command=lambda val: self._on_params_changed(),
        )
        self._cbo_leader_strat.pack(anchor="w", pady=(2, 0))

        self._lbl_leader_pitloss = ctk.CTkLabel(
            f_strat,
            text="Boxes Líder: -28.3s en pista",
            font=ctk.CTkFont(family="Segoe UI Mono", size=10),
            text_color=self.colors["accent"],
        )
        self._lbl_leader_pitloss.pack(anchor="w", pady=(2, 0))

        # 2. Vuelta Consumida del Líder
        f_lap = ctk.CTkFrame(self, fg_color="transparent")
        f_lap.grid(row=0, column=1, padx=10, pady=10, sticky="w")

        ctk.CTkLabel(
            f_lap,
            text="VUELTA LÍDER / CONSUMIDA",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=self.colors["text_secondary"],
        ).pack(anchor="w")

        ctrl_lap = ctk.CTkFrame(f_lap, fg_color="transparent")
        ctrl_lap.pack(anchor="w", pady=(2, 0))

        ctk.CTkButton(
            ctrl_lap, text="◀", width=28, height=28, corner_radius=6,
            fg_color=self.colors["input_bg"], hover_color=self.colors["border"],
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=lambda: self._step_leader_lap(-1),
        ).pack(side="left")

        e_lap = ctk.CTkEntry(
            ctrl_lap, textvariable=self._var_leader_lap, width=58, height=30,
            font=ctk.CTkFont(family="Segoe UI Mono", size=14, weight="bold"),
            justify="center", fg_color=self.colors["input_bg"], border_color=self.colors["border"],
        )
        e_lap.pack(side="left", padx=4)
        e_lap.bind("<FocusOut>", lambda ev: self._on_params_changed())
        e_lap.bind("<Return>", lambda ev: self._on_params_changed())

        ctk.CTkButton(
            ctrl_lap, text="▶", width=28, height=30, corner_radius=6,
            fg_color=self.colors["input_bg"], hover_color=self.colors["border"],
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=lambda: self._step_leader_lap(1),
        ).pack(side="left")

        self._lbl_total_projected = ctk.CTkLabel(
            ctrl_lap,
            text=" / 31 V",
            font=ctk.CTkFont(family="Segoe UI Mono", size=13, weight="bold"),
            text_color=self.colors["text_secondary"],
        )
        self._lbl_total_projected.pack(side="left", padx=(4, 0))

        self._lbl_lap_clarification = ctk.CTkLabel(
            f_lap,
            text="(Fin V0 · Rodando V1)",
            font=ctk.CTkFont(family="Segoe UI", size=9),
            text_color=self.colors["text_secondary"],
        )
        self._lbl_lap_clarification.pack(anchor="w", pady=(2, 0))

        # 3. Ritmo Medio del Líder
        f_pace = ctk.CTkFrame(self, fg_color="transparent")
        f_pace.grid(row=0, column=2, padx=10, pady=10, sticky="w")

        ctk.CTkLabel(
            f_pace,
            text="RITMO MEDIO LÍDER",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=self.colors["text_secondary"],
        ).pack(anchor="w")

        e_pace = ctk.CTkEntry(
            f_pace, textvariable=self._var_leader_pace, width=110, height=30,
            font=ctk.CTkFont(family="Segoe UI Mono", size=12, weight="bold"),
            fg_color=self.colors["input_bg"], border_color=self.colors["border"],
        )
        e_pace.pack(anchor="w", pady=(2, 0))
        e_pace.bind("<FocusOut>", lambda ev: self._on_params_changed())
        e_pace.bind("<Return>", lambda ev: self._on_params_changed())

        self._lbl_pace_sec = ctk.CTkLabel(
            f_pace,
            text="(84.50 s/v)",
            font=ctk.CTkFont(family="Segoe UI Mono", size=10),
            text_color=self.colors["text_secondary"],
        )
        self._lbl_pace_sec.pack(anchor="w", pady=(2, 0))

        # 4. Tiempo que Falta de Carrera (Reloj Oficial)
        f_time = ctk.CTkFrame(self, fg_color="transparent")
        f_time.grid(row=0, column=3, padx=10, pady=10, sticky="w")

        ctk.CTkLabel(
            f_time,
            text="TIEMPO RESTANTE (RELOJ)",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=self.colors["text_secondary"],
        ).pack(anchor="w")

        clk_box = ctk.CTkFrame(f_time, fg_color="transparent")
        clk_box.pack(anchor="w", pady=(2, 0))

        e_clk = ctk.CTkEntry(
            clk_box, textvariable=self._var_time_rem_str, width=100, height=30,
            font=ctk.CTkFont(family="Segoe UI Mono", size=13, weight="bold"),
            justify="center", fg_color=self.colors["input_bg"], border_color=self.colors["border"],
        )
        e_clk.pack(side="left")
        e_clk.bind("<FocusOut>", lambda ev: self._on_params_changed())
        e_clk.bind("<Return>", lambda ev: self._on_params_changed())

        ctk.CTkButton(
            clk_box, text="↺", width=26, height=28, corner_radius=6,
            fg_color=self.colors["input_bg"], hover_color=self.colors["border"],
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            command=self._reset_clock_to_nominal,
        ).pack(side="left", padx=(3, 0))

        self._lbl_dur_nominal = ctk.CTkLabel(
            f_time,
            text="Duración: 60 min",
            font=ctk.CTkFont(family="Segoe UI", size=9),
            text_color=self.colors["text_secondary"],
        )
        self._lbl_dur_nominal.pack(anchor="w", pady=(2, 0))

        # 5. Estimación de Vueltas Restantes y Totales (Display Destacado)
        f_res = ctk.CTkFrame(self, fg_color=self.colors["bg_primary"], corner_radius=8, border_width=1, border_color=self.colors["border"])
        f_res.grid(row=0, column=4, padx=14, pady=10, sticky="e")

        ctk.CTkLabel(
            f_res,
            text="PROYECCIÓN WHITE FLAG (+1v)",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            text_color=self.colors["accent"],
        ).pack(anchor="e", padx=10, pady=(6, 0))

        self._lbl_laps_rem_big = ctk.CTkLabel(
            f_res,
            text="RESTAN: 31 VUELTAS",
            font=ctk.CTkFont(family="Segoe UI Mono", size=15, weight="bold"),
            text_color=self.colors["text_primary"],
        )
        self._lbl_laps_rem_big.pack(anchor="e", padx=10)

        self._lbl_total_proj_big = ctk.CTkLabel(
            f_res,
            text="TOTAL: 43 V (Meta V43)",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=self.colors["text_secondary"],
        )
        self._lbl_total_proj_big.pack(anchor="e", padx=10, pady=(0, 6))

        # Responsive: los 5 bloques de la cabecera pasan a varias filas si no caben en una
        self._layout_grid = ResponsiveGrid(
            self, [f_strat, f_lap, f_pace, f_time, f_res], max_cols=5,
            grid_kw=dict(padx=10, pady=10, sticky="w"),
            item_grid_kw=[dict(padx=14), None, None, None, dict(padx=14, sticky="e")],
        )

    def _step_leader_lap(self, delta: int):
        try:
            curr = int(str(self._var_leader_lap.get()).strip())
        except ValueError:
            curr = 0
        new_val = max(0, curr + delta)
        self._var_leader_lap.set(str(new_val))

        # Al avanzar/retroceder vueltas consumidas, ajustar automáticamente el reloj restante
        p_sec = lap_time_to_seconds(self._var_leader_pace.get())
        curr_rem_s = parse_clock_to_seconds(self._var_time_rem_str.get())
        new_rem_s = max(0.0, curr_rem_s - (delta * p_sec))
        self._var_time_rem_str.set(format_seconds_to_clock(new_rem_s))

        self._on_params_changed()

    def _reset_clock_to_nominal(self):
        try:
            dur_m = float(str(self._var_race_dur_min.get()).replace(",", "."))
        except ValueError:
            dur_m = 60.0
        try:
            l_lap = int(str(self._var_leader_lap.get()).strip())
        except ValueError:
            l_lap = 0
        p_sec = lap_time_to_seconds(self._var_leader_pace.get())
        total_race_s = dur_m * 60.0
        elapsed_s = l_lap * p_sec
        rem_s = max(0.0, total_race_s - elapsed_s)
        self._var_time_rem_str.set(format_seconds_to_clock(rem_s))
        self._on_params_changed()

    def _on_params_changed(self):
        try:
            dur_m = float(str(self._var_race_dur_min.get()).replace(",", "."))
        except ValueError:
            dur_m = 60.0

        p_sec = lap_time_to_seconds(self._var_leader_pace.get())
        if p_sec <= 0:
            p_sec = 84.5

        try:
            l_lap = int(str(self._var_leader_lap.get()).strip())
        except ValueError:
            l_lap = 0

        # 1. Tiempo restante del reloj oficial
        rem_s = parse_clock_to_seconds(self._var_time_rem_str.get())

        # 2. Pérdida en paradas del líder
        pit_loss = self._get_leader_pit_loss_seconds()
        self._lbl_leader_pitloss.configure(text=f"Boxes Líder: -{pit_loss:.1f}s en pista")

        # 3. Tiempo efectivo en pista antes de que el reloj marque 00:00
        track_s = max(0.0, rem_s - pit_loss)

        # 4. Estimación de vueltas restantes y totales según la regla White Flag (+1 vuelta)
        if p_sec > 0 and track_s > 0:
            rem_laps = math.floor(track_s / p_sec) + 1
        elif rem_s > 0:
            rem_laps = 1  # Última vuelta lanzada hacia cuadros
        else:
            rem_laps = 0

        total_projected = l_lap + rem_laps

        # 5. Actualizar UI
        self._lbl_total_projected.configure(text=f" / {total_projected} V")
        self._lbl_lap_clarification.configure(text=f"(Fin V{l_lap} · Rodando V{l_lap + 1})")
        self._lbl_pace_sec.configure(text=f"({p_sec:.2f} s/v)")
        self._lbl_dur_nominal.configure(text=f"Duración: {dur_m:.0f} min")

        self._lbl_laps_rem_big.configure(text=f"RESTAN: {rem_laps} VUELTAS")
        self._lbl_total_proj_big.configure(text=f"TOTAL: {total_projected} V (Meta V{total_projected})")

        # Notificar a los módulos dependientes
        if self.on_update_callback:
            self.on_update_callback({
                "leader_lap": l_lap,
                "leader_pace_s": p_sec,
                "leader_pace_str": self._var_leader_pace.get(),
                "leader_strategy": self._var_leader_strategy.get(),
                "leader_pit_loss_s": pit_loss,
                "race_dur_min": dur_m,
                "time_rem_str": self._var_time_rem_str.get(),
                "rem_seconds": rem_s,
                "track_seconds": track_s,
                "rem_laps": rem_laps,
                "total_projected_laps": total_projected,
            })

    def get_race_state(self) -> dict:
        try:
            dur_m = float(str(self._var_race_dur_min.get()).replace(",", "."))
        except ValueError:
            dur_m = 60.0
        p_sec = lap_time_to_seconds(self._var_leader_pace.get())
        try:
            l_lap = int(str(self._var_leader_lap.get()).strip())
        except ValueError:
            l_lap = 0

        rem_s = parse_clock_to_seconds(self._var_time_rem_str.get())
        pit_loss = self._get_leader_pit_loss_seconds()
        track_s = max(0.0, rem_s - pit_loss)

        if p_sec > 0 and track_s > 0:
            rem_laps = math.floor(track_s / p_sec) + 1
        elif rem_s > 0:
            rem_laps = 1
        else:
            rem_laps = 0

        total_projected = l_lap + rem_laps

        return {
            "leader_lap": l_lap,
            "leader_pace_s": p_sec,
            "leader_pace_str": self._var_leader_pace.get(),
            "leader_strategy": self._var_leader_strategy.get(),
            "leader_pit_loss_s": pit_loss,
            "race_dur_min": dur_m,
            "time_rem_str": self._var_time_rem_str.get(),
            "rem_seconds": rem_s,
            "track_seconds": track_s,
            "rem_laps": rem_laps,
            "total_projected_laps": total_projected,
        }

    def set_race_state(self, state: dict):
        if "leader_lap" in state:
            self._var_leader_lap.set(str(state["leader_lap"]))
        if "leader_pace_str" in state:
            self._var_leader_pace.set(str(state["leader_pace_str"]))
        if "leader_strategy" in state:
            self._var_leader_strategy.set(str(state["leader_strategy"]))
        if "race_dur_min" in state:
            self._var_race_dur_min.set(str(state["race_dur_min"]))
        if "time_rem_str" in state:
            self._var_time_rem_str.set(str(state["time_rem_str"]))
        self._on_params_changed()


# ================================================================================
#  CLASE: PilotLiveCard (Gestión Individual de Carrera para un Piloto)
# ================================================================================
class PilotLiveCard(ctk.CTkFrame):
    """Columna dedicada a la gestión de carrera en directo de un piloto."""

    def __init__(self, parent, pilot_id: int, colors: dict, parent_module, **kwargs):
        super().__init__(parent, fg_color=colors["bg_secondary"], corner_radius=10, border_width=1, border_color=colors["border"], **kwargs)
        self.pilot_id = pilot_id
        self.colors = colors
        self.parent_module = parent_module

        # Variables del piloto
        self._var_name = ctk.StringVar(value=f"Piloto {pilot_id} (NIX)")
        self._var_selected_strategy = ctk.StringVar(value="⚡ Estrategia Óptima")
        self._var_initial_tyre_lap  = ctk.StringVar(value="0")
        self._var_mounted_comp      = ctk.StringVar(value="Prime (Duro)")

        # Entrada rápida de meta
        self._var_quick_lap  = ctk.StringVar(value="1")
        self._var_quick_fuel = ctk.StringVar(value="")

        # Historial de cruce de meta: list[dict] -> [{"lap": int, "fuel": float, "cons": float}]
        self.meta_records: list[dict] = []

        # Estrategia de referencia activa
        self.active_strategy: dict = {
            "num_stops": 1,
            "p1": 15,
            "p2": 0,
            "stint1_comp": "hard",
            "stint2_comp": "soft",
            "stint3_comp": "soft",
            "target_cons": [5.65, 5.65],
            "refuel_litres": [30.0],
        }

        # Sub-panel táctico
        self._var_tac_sc        = ctk.BooleanVar(value=False)
        self._var_tac_sc_sector = ctk.StringVar(value="Sector 1")
        self._var_tac_sc_dur    = ctk.StringVar(value="3")
        self.tactical_result: dict | None = None

        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)

        # ── 1. Cabecera del Piloto ──────────────────────────────────────────
        head_f = ctk.CTkFrame(self, fg_color=self.colors["sidebar_bg"], corner_radius=8, border_width=1, border_color=self.colors["border"])
        head_f.pack(fill="x", padx=10, pady=(10, 6))
        head_f.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            head_f, text=f"P{self.pilot_id}",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=self.colors["accent"], width=28,
        ).grid(row=0, column=0, padx=(8, 4), pady=6, sticky="w")

        e_name = ctk.CTkEntry(
            head_f, textvariable=self._var_name, height=30,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color=self.colors["input_bg"], border_color=self.colors["border"],
        )
        e_name.grid(row=0, column=1, padx=(0, 8), pady=6, sticky="ew")

        # ── 2. Selector de Estrategia y Gomas ──────────────────────────────
        cfg_f = ctk.CTkFrame(self, fg_color="transparent")
        cfg_f.pack(fill="x", padx=10, pady=(0, 6))
        cfg_f.grid_columnconfigure((0, 1), weight=1)

        # Selector Estrategia
        c_strat = ctk.CTkFrame(cfg_f, fg_color="transparent")
        c_strat.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        ctk.CTkLabel(c_strat, text="Estrategia Asignada:", font=ctk.CTkFont(family="Segoe UI", size=10), text_color=self.colors["text_secondary"]).pack(anchor="w")

        strat_row = ctk.CTkFrame(c_strat, fg_color="transparent")
        strat_row.pack(fill="x", pady=(2, 0))
        strat_row.grid_columnconfigure(0, weight=1)

        self._cbo_strategy = ctk.CTkComboBox(
            strat_row,
            values=["⚡ Estrategia Óptima"],
            variable=self._var_selected_strategy,
            height=28,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            dropdown_font=ctk.CTkFont(family="Segoe UI", size=11),
            command=self._on_strategy_selected,
        )
        self._cbo_strategy.grid(row=0, column=0, sticky="ew")

        ctk.CTkButton(
            strat_row, text="↺", width=28, height=28, corner_radius=6,
            fg_color=self.colors["input_bg"], hover_color=self.colors["border"],
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=self._apply_selected_strategy,
        ).grid(row=0, column=1, padx=(4, 0))


        # ── 2b. Resumen del Plan Base Asignado ──────────────────────────────
        self._plan_box = ctk.CTkFrame(self, fg_color=self.colors["sidebar_bg"], corner_radius=8, border_width=1, border_color=self.colors["border"])
        self._plan_box.pack(fill="x", padx=6, pady=(0, 6))
        self._plan_box.grid_columnconfigure(0, weight=1)

        self._lbl_plan_title = ctk.CTkLabel(
            self._plan_box, text="📋 PLAN ASIGNADO",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            text_color=self.colors["accent"],
        )
        self._lbl_plan_title.pack(anchor="w", padx=8, pady=(4, 0))

        self._lbl_plan_details = ctk.CTkLabel(
            self._plan_box, text="Box: Fin V15  |  Echar: 30.0 L",
            font=ctk.CTkFont(family="Segoe UI Mono", size=10, weight="bold"),
            text_color=self.colors["text_primary"],
        )
        self._lbl_plan_details.pack(anchor="w", padx=8, pady=(0, 4))

        # ── 3. Panel de Estado en Vivo (HUD KPI Card) ──────────────────────
        self._hud_card = ctk.CTkFrame(self, fg_color=self.colors["bg_primary"], corner_radius=8, border_width=1, border_color=self.colors["border"])
        self._hud_card.pack(fill="x", padx=6, pady=(0, 6))
        self._hud_card.grid_columnconfigure((0, 1), weight=1)

        # Fila 1: Litros en Tanque y Delta de Combustible
        f_tanque = ctk.CTkFrame(self._hud_card, fg_color="transparent")
        f_tanque.grid(row=0, column=0, padx=8, pady=(8, 4), sticky="w")
        ctk.CTkLabel(f_tanque, text="TANQUE ACTUAL", font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"), text_color=self.colors["text_secondary"]).pack(anchor="w")
        self._lbl_curr_fuel = ctk.CTkLabel(f_tanque, text="70.0 L", font=ctk.CTkFont(family="Segoe UI Mono", size=16, weight="bold"), text_color=self.colors["text_primary"])
        self._lbl_curr_fuel.pack(anchor="w")

        f_delta = ctk.CTkFrame(self._hud_card, fg_color="transparent")
        f_delta.grid(row=0, column=1, padx=8, pady=(8, 4), sticky="e")
        ctk.CTkLabel(f_delta, text="DELTA COMBUSTIBLE", font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"), text_color=self.colors["text_secondary"]).pack(anchor="e")
        self._lbl_delta_fuel = ctk.CTkLabel(f_delta, text="±0.00 L", font=ctk.CTkFont(family="Segoe UI Mono", size=16, weight="bold"), text_color=self.colors["accent"])
        self._lbl_delta_fuel.pack(anchor="e")

        # Fila 2: Semáforo Dinámico y Consumo Medio
        f_semaforo = ctk.CTkFrame(self._hud_card, fg_color="transparent")
        f_semaforo.grid(row=1, column=0, padx=8, pady=2, sticky="w")
        self._lbl_hud_status = ctk.CTkLabel(
            f_semaforo, text="🟢 ON TARGET",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#51CF66",
        )
        self._lbl_hud_status.pack(anchor="w")

        f_cons = ctk.CTkFrame(self._hud_card, fg_color="transparent")
        f_cons.grid(row=1, column=1, padx=8, pady=2, sticky="e")
        self._lbl_cons_stint = ctk.CTkLabel(
            f_cons, text="Med: 5.65 L/v (Tgt 5.65)",
            font=ctk.CTkFont(family="Segoe UI Mono", size=10),
            text_color=self.colors["text_secondary"],
        )
        self._lbl_cons_stint.pack(anchor="e")

        # Fila 3: Próxima Parada y Litros a Cargar
        f_box_info = ctk.CTkFrame(self._hud_card, fg_color="transparent")
        f_box_info.grid(row=2, column=0, columnspan=2, padx=8, pady=(4, 8), sticky="ew")
        f_box_info.grid_columnconfigure((0, 1), weight=1)

        self._lbl_next_pit = ctk.CTkLabel(
            f_box_info, text="Box: Fin V15 (en 15v)",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=self.colors["text_primary"], anchor="w",
        )
        self._lbl_next_pit.grid(row=0, column=0, sticky="w")

        self._lbl_refuel_calc = ctk.CTkLabel(
            f_box_info, text="Cargar: 30.0 L",
            font=ctk.CTkFont(family="Segoe UI Mono", size=11, weight="bold"),
            text_color=self.colors["accent"], anchor="e",
        )
        self._lbl_refuel_calc.grid(row=0, column=1, sticky="e")

        # ── 4. Entrada Rápida de Meta ──────────────────────────────────────
        quick_f = ctk.CTkFrame(self, fg_color="transparent")
        quick_f.pack(fill="x", padx=10, pady=(2, 4))
        quick_f.grid_columnconfigure((0, 1, 2), weight=1)

        # Vuelta
        q_v = ctk.CTkFrame(quick_f, fg_color="transparent")
        q_v.grid(row=0, column=0, sticky="ew", padx=(0, 2))
        ctk.CTkLabel(q_v, text="V. Meta:", font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"), text_color=self.colors["text_secondary"]).pack(anchor="w")
        e_qv = ctk.CTkEntry(
            q_v, textvariable=self._var_quick_lap, width=50, height=28,
            font=ctk.CTkFont(family="Segoe UI Mono", size=11, weight="bold"),
            justify="center", fg_color=self.colors["input_bg"], border_color=self.colors["border"],
        )
        e_qv.pack(fill="x", pady=(1, 0))

        # Litros
        q_f = ctk.CTkFrame(quick_f, fg_color="transparent")
        q_f.grid(row=0, column=1, sticky="ew", padx=2)
        ctk.CTkLabel(q_f, text="Litros:", font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"), text_color=self.colors["text_secondary"]).pack(anchor="w")
        self._e_qfuel = ctk.CTkEntry(
            q_f, textvariable=self._var_quick_fuel, width=70, height=28,
            font=ctk.CTkFont(family="Segoe UI Mono", size=11, weight="bold"),
            justify="center", fg_color=self.colors["input_bg"], border_color=self.colors["border"],
            placeholder_text="ej: 34.2",
        )
        self._e_qfuel.pack(fill="x", pady=(1, 0))
        self._e_qfuel.bind("<Return>", lambda ev: self._submit_quick_meta())

        # Botón Registrar
        btn_reg = ctk.CTkButton(
            quick_f, text="⏱️ Registrar", height=28, corner_radius=6,
            fg_color=self.colors["accent"], hover_color=self.colors["accent_hover"],
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            command=self._submit_quick_meta,
        )
        btn_reg.grid(row=0, column=2, sticky="ew", padx=(2, 0), pady=(12, 0))

        # ── 5. Tabla Histórica de Pasos por Meta (Scrollable) ──────────────
        table_container = ctk.CTkFrame(self, fg_color=self.colors["bg_primary"], corner_radius=8, border_width=1, border_color=self.colors["border"])
        table_container.pack(fill="x", padx=10, pady=(2, 6))

        # Header de la tabla
        th = ctk.CTkFrame(table_container, fg_color="transparent")
        th.pack(fill="x", padx=6, pady=(4, 2))
        th.grid_columnconfigure((0, 1, 2, 3), weight=1)

        for c_idx, t_text in enumerate(["Vuelta", "Litros", "Cons L/v", ""]):
            ctk.CTkLabel(
                th, text=t_text,
                font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
                text_color=self.colors["text_secondary"],
            ).grid(row=0, column=c_idx, sticky="w" if c_idx < 3 else "e", padx=2)

        # Frame scrollable para los registros
        self._table_scroll = ctk.CTkScrollableFrame(table_container, height=105, fg_color="transparent")
        self._table_scroll.pack(fill="x", padx=2, pady=(0, 4))
        self._table_scroll.grid_columnconfigure((0, 1, 2, 3), weight=1)

        # ── 5b. Monitor Visual de Estrategia (Dual Timeline Gantt) ─────────
        self._strat_viz_container = ctk.CTkFrame(self, fg_color=self.colors["bg_primary"], corner_radius=8, border_width=1, border_color=self.colors["border"])
        self._strat_viz_container.pack(fill="x", padx=6, pady=(2, 6))

        head_viz = ctk.CTkFrame(self._strat_viz_container, fg_color="transparent")
        head_viz.pack(fill="x", padx=6, pady=(4, 2))

        ctk.CTkLabel(
            head_viz, text="📊 ESTRATEGIA COMPARADA",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            text_color=self.colors["accent"],
        ).pack(side="left")

        self._btn_viz_apply = ctk.CTkButton(
            head_viz, text="🚀 Aplicar", width=54, height=18, corner_radius=4,
            fg_color=self.colors["accent"], hover_color=self.colors["accent_hover"],
            font=ctk.CTkFont(family="Segoe UI", size=8, weight="bold"),
            command=self.promote_tactical_strategy,
        )

        self._btn_viz_discard = ctk.CTkButton(
            head_viz, text="✕", width=22, height=18, corner_radius=4,
            fg_color="#331515", hover_color="#552020", text_color="#FF8888",
            font=ctk.CTkFont(family="Segoe UI", size=8, weight="bold"),
            command=self.discard_tactical_strategy,
        )

        self._lbl_viz_laps = ctk.CTkLabel(
            head_viz, text="V0/20",
            font=ctk.CTkFont(family="Segoe UI Mono", size=9, weight="bold"),
            text_color=self.colors["text_secondary"],
        )
        self._canvas_strat = tk.Canvas(self._strat_viz_container, height=116, bg="#0E0E0E", highlightthickness=0)
        self._canvas_strat.pack(fill="x", padx=4, pady=(0, 6))
        self._canvas_strat.bind("<Configure>", lambda ev: self._render_strategy_timeline())
        self._canvas_strat.bind("<MouseWheel>", self._forward_mouse_wheel)

        # ── 6. Sub-Panel: Optimizador Táctico en Vivo ──────────────────────
        self._tac_box = ctk.CTkFrame(self, fg_color=self.colors["sidebar_bg"], corner_radius=8, border_width=1, border_color=self.colors["border"])
        self._tac_box.pack(fill="x", padx=6, pady=(2, 10))

        ctk.CTkLabel(
            self._tac_box, text="⚡ OPTIMIZADOR TÁCTICO RESTANTE",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=self.colors["accent"],
        ).pack(anchor="w", padx=10, pady=(6, 2))

        # Controles tácticos (Safety Car: Sector y Duración)
        tac_ctrls = ctk.CTkFrame(self._tac_box, fg_color="transparent")
        tac_ctrls.pack(fill="x", padx=6, pady=2)
        tac_ctrls.grid_columnconfigure((0, 1, 2, 3), weight=1)

        chk_sc = ctk.CTkCheckBox(
            tac_ctrls, text="Safety Car", variable=self._var_tac_sc,
            font=ctk.CTkFont(family="Segoe UI", size=10),
            checkbox_width=16, checkbox_height=16,
            command=self._on_tac_params_changed,
        )
        chk_sc.grid(row=0, column=0, sticky="w", padx=(2, 4))

        cbo_sc_sec = ctk.CTkComboBox(
            tac_ctrls, values=["Sector 1", "Sector 2", "Sector 3"],
            variable=self._var_tac_sc_sector, width=86, height=26,
            font=ctk.CTkFont(family="Segoe UI", size=9),
            dropdown_font=ctk.CTkFont(family="Segoe UI", size=9),
            command=lambda v: self._on_tac_params_changed(),
        )
        cbo_sc_sec.grid(row=0, column=1, sticky="w", padx=2)

        e_sc_dur = ctk.CTkEntry(
            tac_ctrls, textvariable=self._var_tac_sc_dur, width=36, height=26,
            font=ctk.CTkFont(family="Segoe UI Mono", size=10, weight="bold"),
            justify="center", fg_color=self.colors["input_bg"], border_color=self.colors["border"],
        )
        e_sc_dur.grid(row=0, column=2, sticky="e", padx=(4, 2))
        e_sc_dur.bind("<FocusOut>", lambda ev: self._on_tac_params_changed())

        ctk.CTkLabel(
            tac_ctrls, text="vueltas",
            font=ctk.CTkFont(family="Segoe UI", size=9),
            text_color=self.colors["text_secondary"],
        ).grid(row=0, column=3, sticky="w", padx=(0, 2))

        # Card de resultado táctico
        self._tac_res_card = ctk.CTkFrame(self._tac_box, fg_color=self.colors["bg_primary"], corner_radius=6, border_width=1, border_color=self.colors["border"])
        self._tac_res_card.pack(fill="x", padx=8, pady=(4, 6))

        self._lbl_tac_desc = ctk.CTkLabel(
            self._tac_res_card,
            text="Pulsa 'Recalcular' para proyectar estrategia óptima.",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=self.colors["text_secondary"], justify="left", wraplength=260,
        )
        self._lbl_tac_desc.pack(padx=8, pady=6, anchor="w")

        # Botones de acción táctica
        tac_btns = ctk.CTkFrame(self._tac_box, fg_color="transparent")
        tac_btns.pack(fill="x", padx=8, pady=(0, 8))
        tac_btns.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkButton(
            tac_btns, text="⚡ Recalcular", height=26, corner_radius=6,
            fg_color=self.colors["input_bg"], hover_color=self.colors["border"],
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            command=self.solve_tactical_strategy,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 2))

        self._btn_promote = ctk.CTkButton(
            tac_btns, text="🚀 Promover", height=26, corner_radius=6,
            fg_color=self.colors["accent"], hover_color=self.colors["accent_hover"],
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            command=self.promote_tactical_strategy,
            state="disabled",
        )
        self._btn_promote.grid(row=0, column=1, sticky="ew", padx=2)

        self._btn_discard = ctk.CTkButton(
            tac_btns, text="✕ Descartar", height=26, corner_radius=6,
            fg_color="#2A1010", hover_color="#441515", text_color="#FF8888",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            command=self.discard_tactical_strategy,
            state="disabled",
        )
        self._btn_discard.grid(row=0, column=2, sticky="ew", padx=(2, 0))

    # ─── Lógica de Paso por Meta ───────────────────────────────────────
    def _submit_quick_meta(self):
        v_str = str(self._var_quick_lap.get()).strip()
        f_str = str(self._var_quick_fuel.get()).strip().replace(",", ".")

        if not v_str or not f_str:
            return
        try:
            lap_num = int(v_str)
            fuel_val = float(f_str)
        except ValueError:
            return

        # Validación estricta: Solo se pueden registrar vueltas menores o iguales a la del líder
        leader_lap = int(self.parent_module.race_header.get_race_state()["leader_lap"])
        if lap_num > leader_lap:
            messagebox.showwarning(
                "Vuelta Superior al Líder",
                f"No es posible registrar la Vuelta {lap_num} para el {self._var_name.get()}.\n\n"
                f"El líder de carrera actualmente solo ha completado {leader_lap} vueltas.\n"
                f"Por favor, actualiza primero la vuelta del líder en el Control de Carrera (arriba) o introduce una vuelta ≤ {leader_lap}.",
            )
            return

        # Calcular consumo de la vuelta
        tank_cap = float(self.parent_module.session_data.get("fuel_capacity_l", 70.0))
        if not self.meta_records:
            # Primera vuelta registrada
            cons = max(0.0, tank_cap - fuel_val)
        else:
            prev = self.meta_records[-1]
            if lap_num > prev["lap"]:
                laps_diff = lap_num - prev["lap"]
                cons = max(0.0, (prev["fuel"] - fuel_val) / laps_diff)
            else:
                cons = 0.0

        # Guardar registro
        self.meta_records.append({
            "lap": lap_num,
            "fuel": fuel_val,
            "cons": cons,
        })

        # Preparar siguiente entrada rápida
        self._var_quick_lap.set(str(lap_num + 1))
        self._var_quick_fuel.set("")
        self._e_qfuel.focus_set()

        self._render_table_rows()
        self._recalculate_all()
        self.parent_module.auto_save()

    def _render_table_rows(self):
        for w in self._table_scroll.winfo_children():
            w.destroy()

        for idx, rec in enumerate(self.meta_records):
            row_f = ctk.CTkFrame(self._table_scroll, fg_color="transparent")
            row_f.pack(fill="x", pady=1)
            row_f.grid_columnconfigure((0, 1, 2, 3), weight=1)

            ctk.CTkLabel(
                row_f, text=f"V{rec['lap']}",
                font=ctk.CTkFont(family="Segoe UI Mono", size=10, weight="bold"),
                text_color=self.colors["text_primary"],
            ).grid(row=0, column=0, sticky="w", padx=2)

            ctk.CTkLabel(
                row_f, text=f"{rec['fuel']:.1f} L",
                font=ctk.CTkFont(family="Segoe UI Mono", size=10),
                text_color=self.colors["text_secondary"],
            ).grid(row=0, column=1, sticky="w", padx=2)

            ctk.CTkLabel(
                row_f, text=f"{rec['cons']:.2f} L/v",
                font=ctk.CTkFont(family="Segoe UI Mono", size=10),
                text_color=self.colors["accent"] if rec['cons'] > 0 else self.colors["text_secondary"],
            ).grid(row=0, column=2, sticky="w", padx=2)

            ctk.CTkButton(
                row_f, text="✕", width=18, height=18, corner_radius=3,
                fg_color="#331111", hover_color="#551111", text_color="#FF6B6B",
                font=ctk.CTkFont(family="Segoe UI", size=8, weight="bold"),
                command=lambda i=idx: self._delete_meta_record(i),
            ).grid(row=0, column=3, sticky="e", padx=2)

    def _delete_meta_record(self, idx: int):
        if 0 <= idx < len(self.meta_records):
            self.meta_records.pop(idx)
            # Recomputar consumos si quedan registros
            tank_cap = float(self.parent_module.session_data.get("fuel_capacity_l", 70.0))
            for i, r in enumerate(self.meta_records):
                if i == 0:
                    r["cons"] = max(0.0, tank_cap - r["fuel"])
                else:
                    prev = self.meta_records[i - 1]
                    d_laps = max(1, r["lap"] - prev["lap"])
                    r["cons"] = max(0.0, (prev["fuel"] - r["fuel"]) / d_laps)
            self._render_table_rows()
            self._recalculate_all()
            self.parent_module.auto_save()

    def get_current_mounted_compound(self) -> str:
        """Determina el compuesto de neumáticos montado actualmente según la vuelta y la estrategia activa."""
        if self.meta_records:
            curr_lap = self.meta_records[-1]["lap"]
        else:
            curr_lap = 0

        p1 = self.active_strategy.get("p1", 15)
        p2 = self.active_strategy.get("p2", 0)
        num_stops = self.active_strategy.get("num_stops", 1)

        if num_stops == 0 or curr_lap <= p1:
            return self.active_strategy.get("stint1_comp", "hard")
        elif num_stops == 2 and curr_lap <= p2:
            return self.active_strategy.get("stint2_comp", "soft")
        elif num_stops == 1 and curr_lap > p1:
            return self.active_strategy.get("stint2_comp", "soft")
        else:
            return self.active_strategy.get("stint3_comp", "soft")

    # ─── Recálculo Integral de KPIs y Delta ────────────────────────────
    def _recalculate_all(self):
        sdata = self.parent_module.session_data
        tank_cap = float(sdata.get("fuel_capacity_l", 70.0))
        safety_l = float(self.parent_module.fuel_data.get("safety_fuel_l", 2.5))
        base_cons = float(self.parent_module.fuel_data.get("cons_lap", 5.65))
        race_state = self.parent_module.race_header.get_race_state()
        tot_laps = race_state["total_projected_laps"]

        # Sincronizar compuesto de neumático montado según el stint actual
        c_now = self.get_current_mounted_compound()
        self._var_mounted_comp.set("Prime (Duro)" if c_now == "hard" else "Alternative (Blando)")

        # 1. Combustible actual
        if self.meta_records:
            last = self.meta_records[-1]
            curr_lap = last["lap"]
            curr_fuel = last["fuel"]
        else:
            curr_lap = 0
            curr_fuel = tank_cap

        self._lbl_curr_fuel.configure(text=f"{curr_fuel:.1f} L")

        # 2. Delimitación del stint actual y parámetros de objetivo
        p1 = self.active_strategy.get("p1", 15)
        p2 = self.active_strategy.get("p2", 0)
        num_stops = self.active_strategy.get("num_stops", 1)

        if num_stops == 0:
            st_start_lap = 0
            st_idx = 0
            is_last_stint = True
            next_box = tot_laps
            laps_to_target = max(0, tot_laps - curr_lap)
        elif curr_lap <= p1:
            st_start_lap = 0
            st_idx = 0
            is_last_stint = False
            next_box = p1
            laps_to_target = max(0, p1 - curr_lap)
        elif num_stops == 2 and curr_lap <= p2:
            st_start_lap = p1
            st_idx = 1
            is_last_stint = False
            next_box = p2
            laps_to_target = max(0, p2 - curr_lap)
        else:
            st_start_lap = p2 if num_stops == 2 else p1
            st_idx = 2 if num_stops == 2 else 1
            is_last_stint = True
            next_box = tot_laps
            laps_to_target = max(0, tot_laps - curr_lap)

        # Target de consumo planificado para este stint
        targets = self.active_strategy.get("target_cons", [base_cons, base_cons, base_cons])
        if st_idx < len(targets) and float(targets[st_idx]) > 0:
            tgt_cons = float(targets[st_idx])
        else:
            tgt_cons = base_cons

        # Calcular consumo observado en el stint actual sin contaminar con repostajes
        st_entries = [r for r in self.meta_records if r["lap"] > st_start_lap]
        if len(st_entries) >= 2:
            lap_diff = st_entries[-1]["lap"] - st_entries[0]["lap"]
            fuel_diff = st_entries[0]["fuel"] - st_entries[-1]["fuel"]
            if lap_diff > 0 and fuel_diff > 0:
                obs_cons = max(0.1, fuel_diff / lap_diff)
            else:
                obs_cons = tgt_cons
        else:
            # Si solo hay 0 o 1 paso por meta en este stint, usar telemetría limpia previa
            valid_past = [r["cons"] for r in self.meta_records if r.get("cons", 0) > 0.1 and r["lap"] <= st_start_lap]
            if valid_past:
                obs_cons = sum(valid_past) / len(valid_past)
            else:
                obs_cons = tgt_cons

        self._lbl_cons_stint.configure(text=f"Med: {obs_cons:.2f} L/v (Tgt {tgt_cons:.2f})")

        # 3. Delta de combustible vs plan / objetivo
        fuel_plan = self.active_strategy.get("fuel_plan")
        if fuel_plan and 0 < curr_lap <= len(fuel_plan):
            # Referencia exacta de combustible vuelta a vuelta de la simulación de la estrategia
            plan_fuel_lap = float(fuel_plan[curr_lap - 1])
            delta_f = curr_fuel - plan_fuel_lap
        elif is_last_stint:
            # En el último stint: objetivo es la meta (fin de carrera)
            # delta_f = combustible actual - combustible requerido para cruzar meta con margen de seguridad
            laps_to_meta = max(0, tot_laps - curr_lap)
            fuel_needed_target = (laps_to_meta * tgt_cons) + safety_l
            delta_f = curr_fuel - fuel_needed_target
        elif st_idx == 0:
            # En el primer stint: sale con tanque lleno (tank_cap) hacia Box 1
            laps_in_stint = curr_lap
            plan_fuel_lap = max(0.0, tank_cap - (laps_in_stint * tgt_cons))
            delta_f = curr_fuel - plan_fuel_lap
        else:
            # Stint 2 en estrategia de 2 paradas (hacia Box 2 en p2)
            laps_to_box2 = max(0, p2 - curr_lap)
            fuel_needed_target = (laps_to_box2 * tgt_cons) + safety_l
            delta_f = curr_fuel - fuel_needed_target

        # Semáforo de combustible y cálculo dinámico de objetivo si delta es negativo
        laps_to_eval = laps_to_target
        if delta_f < -0.5:
            self._lbl_delta_fuel.configure(text=f"{delta_f:.2f} L", text_color="#FF453A")
            if laps_to_eval > 0:
                tgt_recovery = max(0.1, tgt_cons + (delta_f / laps_to_eval))
                self._lbl_hud_status.configure(text=f"🔴 SAVE (OBJ: {tgt_recovery:.2f} L/v)", text_color="#FF453A")
                self._lbl_cons_stint.configure(
                    text=f"Med: {obs_cons:.2f} | Obj: {tgt_recovery:.2f} L/v",
                    text_color="#FF6B6B"
                )
            else:
                status_text = "🔴 FINAL DE CARRERA" if is_last_stint else "🔴 ENTRANDO A BOX"
                self._lbl_hud_status.configure(text=status_text, text_color="#FF453A")
                self._lbl_cons_stint.configure(
                    text=f"Med: {obs_cons:.2f} (Tgt {tgt_cons:.2f})",
                    text_color="#FF6B6B"
                )
        elif delta_f > 0.5:
            self._lbl_delta_fuel.configure(text=f"+{delta_f:.2f} L", text_color="#51CF66")
            self._lbl_hud_status.configure(text="🟢 PUSH (MARGEN +)", text_color="#51CF66")
            self._lbl_cons_stint.configure(
                text=f"Med: {obs_cons:.2f} L/v (Tgt {tgt_cons:.2f})",
                text_color=self.colors["text_secondary"]
            )
        else:
            self._lbl_delta_fuel.configure(text=f"{delta_f:+.2f} L", text_color=self.colors["accent"])
            self._lbl_hud_status.configure(text="🟡 ON TARGET", text_color=self.colors["accent"])
            self._lbl_cons_stint.configure(
                text=f"Med: {obs_cons:.2f} L/v (Tgt {tgt_cons:.2f})",
                text_color=self.colors["text_secondary"]
            )

        # 4. Próxima parada y cálculo dinámico de litros a echar / margen en meta
        if not is_last_stint:
            f_at_box = max(0.0, curr_fuel - (laps_to_target * obs_cons))
            if num_stops == 2 and curr_lap < p1:
                next_stint_laps = p2 - p1
                f_needed_next = (next_stint_laps * obs_cons) + safety_l
                litros_a_cargar = min(tank_cap - f_at_box, max(0.0, f_needed_next - f_at_box))
                self._lbl_next_pit.configure(text=f"Box 1: Fin V{p1} (en {laps_to_target}v)")
                self._lbl_refuel_calc.configure(text=f"Cargar: {litros_a_cargar:.1f} L", text_color=self.colors["accent"])
            elif num_stops == 2 and curr_lap < p2:
                next_stint_laps = tot_laps - p2
                f_needed_next = (next_stint_laps * obs_cons) + safety_l
                litros_a_cargar = min(tank_cap - f_at_box, max(0.0, f_needed_next - f_at_box))
                self._lbl_next_pit.configure(text=f"Box 2: Fin V{p2} (en {laps_to_target}v)")
                self._lbl_refuel_calc.configure(text=f"Cargar: {litros_a_cargar:.1f} L", text_color=self.colors["accent"])
            else:
                next_stint_laps = tot_laps - p1
                f_needed_next = (next_stint_laps * obs_cons) + safety_l
                litros_a_cargar = min(tank_cap - f_at_box, max(0.0, f_needed_next - f_at_box))
                self._lbl_next_pit.configure(text=f"Box: Fin V{p1} (en {laps_to_target}v)")
                self._lbl_refuel_calc.configure(text=f"Cargar: {litros_a_cargar:.1f} L", text_color=self.colors["accent"])
        else:
            # Último stint: destino Meta
            if curr_lap >= tot_laps:
                self._lbl_next_pit.configure(text=f"🏁 Meta Alcanzada (V{tot_laps})")
                self._lbl_refuel_calc.configure(text=f"Final: {curr_fuel:.1f} L", text_color="#51CF66")
            else:
                self._lbl_next_pit.configure(text=f"Fin de Carrera (Meta V{tot_laps})")
                if delta_f >= 0:
                    self._lbl_refuel_calc.configure(text=f"Margen: +{delta_f:.1f} L", text_color="#51CF66")
                else:
                    self._lbl_refuel_calc.configure(text=f"Falta: {abs(delta_f):.1f} L", text_color="#FF453A")

        # 5. Actualizar resumen del Plan Base Asignado
        self._update_plan_assigned_display()

        # 6. Actualizar monitor visual de estrategia (Dual Timeline Gantt)
        self._render_strategy_timeline()

    def _render_strategy_timeline(self):
        """Renderiza el monitor gráfico comparativo de stints (Plan Asignado vs Táctica / Real)."""
        if not hasattr(self, "_canvas_strat"):
            return

        self._canvas_strat.delete("all")
        W = self._canvas_strat.winfo_width()
        if W <= 10:
            W = 380

        x_start = 34
        x_end = W - 6
        w_avail = max(10, x_end - x_start)

        race_state = self.parent_module.race_header.get_race_state()
        tot_laps = max(1, int(race_state.get("total_projected_laps", 20)))

        if self.meta_records:
            curr_lap = min(tot_laps, int(self.meta_records[-1]["lap"]))
        else:
            curr_lap = 0

        self._lbl_viz_laps.configure(text=f"V{curr_lap}/{tot_laps}")

        # Mostrar o esconder botones de aplicar y descartar táctica en el encabezado
        tac = getattr(self, "tactical_result", None)
        has_unapplied_tac = bool(tac and str(self._btn_promote.cget("state")) != "disabled")
        if has_unapplied_tac:
            if hasattr(self, "_btn_viz_discard"):
                self._btn_viz_discard.pack(side="right", padx=(2, 0))
            if hasattr(self, "_btn_viz_apply"):
                self._btn_viz_apply.pack(side="right", padx=(4, 0))
        else:
            if hasattr(self, "_btn_viz_discard"):
                self._btn_viz_discard.pack_forget()
            if hasattr(self, "_btn_viz_apply"):
                self._btn_viz_apply.pack_forget()

        comp_colors = {
            "hard": {"fill": "#252C36", "border": "#ADB5BD", "text": "#FFFFFF", "name": "Duro"},
            "soft": {"fill": "#82181A", "border": "#FF6B6B", "text": "#FFFFFF", "name": "Blando"},
        }

        def get_stints(stops, p1, p2, c1, c2, c3):
            if stops == 0 or p1 <= 0 or p1 >= tot_laps:
                return [(0, tot_laps, c1)]
            elif stops == 1:
                p1_c = min(tot_laps, max(1, p1))
                return [(0, p1_c, c1), (p1_c, tot_laps, c2)]
            else:
                p1_c = min(tot_laps - 2, max(1, p1))
                p2_c = min(tot_laps, max(p1_c + 1, p2))
                return [(0, p1_c, c1), (p1_c, p2_c, c2), (p2_c, tot_laps, c3)]

        def get_stint_label(name: str, st_len: int, st_w: float) -> str:
            if st_w >= 56:
                return f"{name} ({st_len}v)"
            elif st_w >= 32:
                return f"{name[0]} · {st_len}v"
            elif st_w >= 18:
                return f"{name[0]}"
            return ""

        # ── 1. FILA SUPERIOR: PLAN ASIGNADO ─────────────────────────────
        # Etiqueta PLAN centrada verticalmente con su barra (y: 20..42)
        self._canvas_strat.create_text(4, 31, text="PLAN", anchor="w", fill="#888888", font=("Segoe UI", 8, "bold"))
        y1, y2 = 20, 42

        plan_stops = self.active_strategy.get("num_stops", 1)
        plan_p1 = self.active_strategy.get("p1", 15)
        plan_p2 = self.active_strategy.get("p2", 0)
        plan_c1 = self.active_strategy.get("stint1_comp", "hard")
        plan_c2 = self.active_strategy.get("stint2_comp", "soft")
        plan_c3 = self.active_strategy.get("stint3_comp", "soft")

        plan_stints = get_stints(plan_stops, plan_p1, plan_p2, plan_c1, plan_c2, plan_c3)
        for s_start, s_end, s_comp in plan_stints:
            xs = x_start + (s_start / tot_laps) * w_avail
            xe = x_start + (s_end / tot_laps) * w_avail
            cfg = comp_colors.get(s_comp, comp_colors["hard"])
            self._canvas_strat.create_rectangle(xs, y1, xe, y2, fill=cfg["fill"], outline=cfg["border"], width=1)
            mid_x = (xs + xe) / 2
            st_len = s_end - s_start
            label = get_stint_label(cfg["name"], st_len, xe - xs)
            if label:
                self._canvas_strat.create_text(mid_x, 31, text=label, fill=cfg["text"], font=("Segoe UI", 7, "bold"))

        # Marcas y badges de parada en Plan (zona superior dedicada y=2..18)
        stops_to_mark = []
        if plan_stops >= 1 and 0 < plan_p1 < tot_laps:
            stops_to_mark.append(plan_p1)
        if plan_stops == 2 and 0 < plan_p2 < tot_laps:
            stops_to_mark.append(plan_p2)

        bw = 40
        for p in stops_to_mark:
            xp = x_start + (p / tot_laps) * w_avail
            bx1 = max(x_start, min(x_end - bw, xp - bw / 2))
            bx2 = bx1 + bw
            self._canvas_strat.create_rectangle(bx1, 2, bx2, 17, fill="#2C0F10", outline="#FF453A", width=1)
            self._canvas_strat.create_text((bx1 + bx2) / 2, 9, text=f"🛑 V{p}", fill="#FF8888", font=("Segoe UI", 7, "bold"))
            self._canvas_strat.create_line(xp, 17, xp, 42, fill="#FF453A", width=2)

        # ── 2. FILA INFERIOR: TÁCTICA O REAL ────────────────────────────
        y3, y4 = 60, 82

        if has_unapplied_tac and tac:
            self._canvas_strat.create_text(4, 71, text="TÁCT", anchor="w", fill=self.colors["warning"], font=("Segoe UI", 8, "bold"))
            tac_stints = tac.get("full_stints")
            if not tac_stints:
                tac_stops = tac.get("num_stops", 1)
                tac_p1 = tac.get("p1", 15)
                tac_p2 = tac.get("p2", 0)
                tac_c1 = tac.get("stint1_comp", plan_c1)
                tac_c2 = tac.get("stint2_comp", plan_c2)
                tac_c3 = tac.get("stint3_comp", plan_c3)
                tac_stints = get_stints(tac_stops, tac_p1, tac_p2, tac_c1, tac_c2, tac_c3)

            for s_start, s_end, s_comp in tac_stints:
                xs = x_start + (s_start / tot_laps) * w_avail
                xe = x_start + (s_end / tot_laps) * w_avail
                cfg = comp_colors.get(s_comp, comp_colors["hard"])
                self._canvas_strat.create_rectangle(xs, y3, xe, y4, fill=cfg["fill"], outline=self.colors["warning"], width=1)
                # Shading tramo completado en el pasado
                if curr_lap > s_start:
                    comp_end = min(curr_lap, s_end)
                    xc_end = x_start + (comp_end / tot_laps) * w_avail
                    self._canvas_strat.create_rectangle(xs, y3, xc_end, y4, fill=cfg["fill"], outline=self.colors["success"], width=1)
                mid_x = (xs + xe) / 2
                st_len = s_end - s_start
                label = get_stint_label(cfg["name"], st_len, xe - xs)
                if label:
                    self._canvas_strat.create_text(mid_x, 71, text=label, fill=cfg["text"], font=("Segoe UI", 7, "bold"))

            # Franja de Safety Car si está activo
            sc_active = self._var_tac_sc.get()
            if sc_active:
                sc_dep_lap = curr_lap + 1
                try:
                    sc_dur = max(1, int(str(self._var_tac_sc_dur.get()).strip()))
                except ValueError:
                    sc_dur = 3
                sc_end = sc_dep_lap + sc_dur
                if sc_dep_lap < tot_laps:
                    x_sc_s = x_start + (sc_dep_lap / tot_laps) * w_avail
                    x_sc_e = x_start + (min(tot_laps, sc_end) / tot_laps) * w_avail
                    self._canvas_strat.create_rectangle(x_sc_s, y3 + 1, x_sc_e, y4 - 1, fill="#554400", outline="#FFD43B", width=1)
                    if (x_sc_e - x_sc_s) > 18:
                        self._canvas_strat.create_text((x_sc_s + x_sc_e) / 2, 71, text="SC", fill="#FFD43B", font=("Segoe UI", 7, "bold"))

            # Marcas y badges de parada Táctica (zona intermedia y=43..58)
            tac_stops_to_mark = tac.get("full_pit_laps")
            if tac_stops_to_mark is None:
                tac_stops_to_mark = []
                tac_stops = tac.get("num_stops", 1)
                tac_p1 = tac.get("p1", 15)
                tac_p2 = tac.get("p2", 0)
                if tac_stops >= 1 and 0 < tac_p1 < tot_laps:
                    tac_stops_to_mark.append(tac_p1)
                if tac_stops == 2 and 0 < tac_p2 < tot_laps:
                    tac_stops_to_mark.append(tac_p2)

            for tp in tac_stops_to_mark:
                if tp <= 0 or tp >= tot_laps:
                    continue
                xt = x_start + (tp / tot_laps) * w_avail
                tbx1 = max(x_start, min(x_end - bw, xt - bw / 2))
                tbx2 = tbx1 + bw
                is_future = (tp > curr_lap)
                is_sc_pit = bool(is_future and sc_active and sc_dep_lap <= tp <= sc_end)
                if is_future:
                    sc_icon = "🟡" if is_sc_pit else "⚡"
                    fill_c = "#2C2300"
                    out_c = "#FFD43B"
                    text_c = "#FFD43B"
                    line_c = self.colors["warning"]
                    lw = 2
                else:
                    sc_icon = "🛑"
                    fill_c = "#1E1E1E"
                    out_c = "#555555"
                    text_c = "#888888"
                    line_c = "#555555"
                    lw = 1

                self._canvas_strat.create_rectangle(tbx1, 43, tbx2, 58, fill=fill_c, outline=out_c, width=1)
                self._canvas_strat.create_text((tbx1 + tbx2) / 2, 50, text=f"{sc_icon} V{tp}", fill=text_c, font=("Segoe UI", 7, "bold"))
                self._canvas_strat.create_line(xt, 58, xt, 82, fill=line_c, width=lw)

        else:
            self._canvas_strat.create_text(4, 71, text="REAL", anchor="w", fill=self.colors["success"], font=("Segoe UI", 8, "bold"))
            for s_start, s_end, s_comp in plan_stints:
                xs = x_start + (s_start / tot_laps) * w_avail
                xe = x_start + (s_end / tot_laps) * w_avail
                cfg = comp_colors.get(s_comp, comp_colors["hard"])
                self._canvas_strat.create_rectangle(xs, y3, xe, y4, fill="#181818", outline="#333333", width=1)
                # Shading tramo completado
                if curr_lap > s_start:
                    comp_end = min(curr_lap, s_end)
                    xc_end = x_start + (comp_end / tot_laps) * w_avail
                    self._canvas_strat.create_rectangle(xs, y3, xc_end, y4, fill=cfg["fill"], outline=self.colors["success"], width=1)
                mid_x = (xs + xe) / 2
                st_len = s_end - s_start
                label = get_stint_label(cfg["name"], st_len, xe - xs)
                if label:
                    self._canvas_strat.create_text(mid_x, 71, text=label, fill="#AAAAAA", font=("Segoe UI", 7))

            # Marcador sutil de parada proyectada en la fila real
            for p in stops_to_mark:
                xp = x_start + (p / tot_laps) * w_avail
                self._canvas_strat.create_line(xp, y3, xp, y4, fill="#555555", width=1, dash=(2, 2))

        # ── 3. EJE INFERIOR DE VUELTAS ──────────────────────────────────
        y_axis = 94
        self._canvas_strat.create_line(x_start, y_axis, x_end, y_axis, fill="#2C2C2C", width=1)
        self._canvas_strat.create_line(x_start, y_axis - 2, x_start, y_axis + 2, fill="#444444", width=1)
        self._canvas_strat.create_line(x_end, y_axis - 2, x_end, y_axis + 2, fill="#444444", width=1)
        self._canvas_strat.create_text(x_start, y_axis + 10, text="0", anchor="nw", fill="#777777", font=("Segoe UI Mono", 7))
        self._canvas_strat.create_text(x_end, y_axis + 10, text=f"V{tot_laps}", anchor="ne", fill="#777777", font=("Segoe UI Mono", 7))

        if tot_laps >= 20:
            x_mid = (x_start + x_end) / 2
            self._canvas_strat.create_line(x_mid, y_axis - 2, x_mid, y_axis + 2, fill="#333333", width=1)
            self._canvas_strat.create_text(x_mid, y_axis + 10, text=f"V{tot_laps // 2}", anchor="n", fill="#555555", font=("Segoe UI Mono", 7))

        # ── 4. CURSOR DE VUELTA ACTUAL NEÓN ────────────────────────────
        if 0 <= curr_lap <= tot_laps:
            xc = x_start + (curr_lap / tot_laps) * w_avail
            self._canvas_strat.create_line(xc, 3, xc, y_axis + 2, fill=self.colors["accent"], width=2)
            self._canvas_strat.create_polygon(xc - 3, 3, xc + 3, 3, xc, 7, fill=self.colors["accent"])
            if curr_lap <= 2:
                self._canvas_strat.create_text(xc + 3, y_axis + 10, text=f"▲V{curr_lap}", anchor="nw", fill=self.colors["accent"], font=("Segoe UI Mono", 7, "bold"))
            elif curr_lap >= tot_laps - 2:
                self._canvas_strat.create_text(xc - 3, y_axis + 10, text=f"▲V{curr_lap}", anchor="ne", fill=self.colors["accent"], font=("Segoe UI Mono", 7, "bold"))
            else:
                self._canvas_strat.create_text(xc, y_axis + 10, text=f"▲V{curr_lap}", anchor="n", fill=self.colors["accent"], font=("Segoe UI Mono", 7, "bold"))

    def _update_plan_assigned_display(self):
        """Muestra en la tarjeta la vuelta de parada y litros a echar según la estrategia seleccionada."""
        num_stops = self.active_strategy.get("num_stops", 1)
        p1 = self.active_strategy.get("p1", 15)
        p2 = self.active_strategy.get("p2", 0)

        sdata = self.parent_module.session_data
        tank_cap = float(sdata.get("fuel_capacity_l", 70.0))
        safety_l = float(self.parent_module.fuel_data.get("safety_fuel_l", 2.5))
        cons_base = float(self.parent_module.fuel_data.get("cons_lap", 5.65))
        race_state = self.parent_module.race_header.get_race_state()
        tot_laps = race_state["total_projected_laps"]

        c2_label = "Blando" if self.active_strategy.get("stint2_comp") == "soft" else "Duro"

        if num_stops == 0:
            if self.meta_records:
                c_fuel = self.meta_records[-1]["fuel"]
                c_lap = self.meta_records[-1]["lap"]
            else:
                c_fuel = tank_cap
                c_lap = 0
            rem_l = max(0, tot_laps - c_lap)
            f_nd = (rem_l * cons_base) + safety_l
            m_l = c_fuel - f_nd
            self._lbl_plan_title.configure(text="📋 PLAN ASIGNADO (A META DIRECTO)")
            self._lbl_plan_details.configure(
                text=f"Sin paradas  |  Meta V{tot_laps}  |  Margen: {m_l:+.1f} L",
                justify="left",
            )
        elif num_stops == 1:
            st1_laps = max(1, p1)
            f_res1 = max(0.0, tank_cap - (st1_laps * cons_base))
            st2_laps = max(1, tot_laps - p1)
            f_needed_st2 = (st2_laps * cons_base) + safety_l
            litros_p1 = min(tank_cap - f_res1, max(0.0, f_needed_st2 - f_res1))

            self._lbl_plan_title.configure(text="📋 PLAN ASIGNADO (1 PARADA)")
            self._lbl_plan_details.configure(
                text=f"Box Fin V{p1}  |  Echar: {litros_p1:.1f} L  |  Goma: {c2_label}",
                justify="left",
            )
        else:
            st1_laps = max(1, p1)
            f_res1 = max(0.0, tank_cap - (st1_laps * cons_base))
            st2_laps = max(1, p2 - p1)
            f_needed2 = (st2_laps * cons_base) + safety_l
            litros_p1 = min(tank_cap - f_res1, max(0.0, f_needed2 - f_res1))

            f_res2 = max(0.0, (f_res1 + litros_p1) - (st2_laps * cons_base))
            st3_laps = max(1, tot_laps - p2)
            f_needed3 = (st3_laps * cons_base) + safety_l
            litros_p2 = min(tank_cap - f_res2, max(0.0, f_needed3 - f_res2))

            c3_label = "Blando" if self.active_strategy.get("stint3_comp") == "soft" else "Duro"
            self._lbl_plan_title.configure(text="📋 PLAN ASIGNADO (2 PARADAS)")
            self._lbl_plan_details.configure(
                text=(
                    f"• Parada 1: Fin V{p1}  ·  Echar {litros_p1:.1f} L ({c2_label})\n"
                    f"• Parada 2: Fin V{p2}  ·  Echar {litros_p2:.1f} L ({c3_label})"
                ),
                justify="left",
            )

    # ─── Estrategias Guardadas ─────────────────────────────────────────
    def _on_strategy_selected(self, strat_name: str):
        self._apply_selected_strategy()

    def _apply_selected_strategy(self):
        strat_name = self._var_selected_strategy.get()
        all_strats = self.parent_module.saved_strategies
        base_cons = float(self.parent_module.fuel_data.get("cons_lap", 5.65))

        if strat_name in all_strats:
            st = all_strats[strat_name]
            sim_res = self.parent_module.simulate_strategy_config(st)
            if sim_res and sim_res.get("stint_targets"):
                target_cons = [float(st_tgt["avg_cons"]) for st_tgt in sim_res["stint_targets"]]
                fuel_plan = sim_res.get("fuel_remaining")
                refuels = [p[2] for p in sim_res.get("pit_info", [])]
            else:
                target_cons = [base_cons] * 3
                fuel_plan = None
                refuels = [30.0]

            self.active_strategy = {
                "num_stops": int(st.get("num_stops", 1)),
                "p1": int(st.get("p1", 15)),
                "p2": int(st.get("p2", 0)),
                "stint1_comp": st.get("stint1_comp", "hard"),
                "stint2_comp": st.get("stint2_comp", "soft"),
                "stint3_comp": st.get("stint3_comp", "soft"),
                "target_cons": target_cons,
                "fuel_plan": fuel_plan,
                "refuel_litres": refuels,
            }
            # Sincronizar compuesto inicial
            c1 = st.get("stint1_comp", "hard")
            self._var_mounted_comp.set("Prime (Duro)" if c1 == "hard" else "Alternative (Blando)")
        elif strat_name == "⚡ Estrategia Óptima":
            opt = self.parent_module.get_optimal_strategy_data()
            sim_res = self.parent_module.simulate_strategy_config(opt) if opt else None
            if sim_res and sim_res.get("stint_targets"):
                target_cons = [float(st_tgt["avg_cons"]) for st_tgt in sim_res["stint_targets"]]
                fuel_plan = sim_res.get("fuel_remaining")
                refuels = [p[2] for p in sim_res.get("pit_info", [])]
            else:
                target_cons = [base_cons] * 3
                fuel_plan = None
                refuels = [30.0]

            if opt:
                self.active_strategy = {
                    "num_stops": int(opt.get("num_stops", 1)),
                    "p1": int(opt.get("p1", 15)),
                    "p2": int(opt.get("p2", 0)),
                    "stint1_comp": opt.get("stint1_comp", "hard"),
                    "stint2_comp": opt.get("stint2_comp", "soft"),
                    "stint3_comp": opt.get("stint3_comp", "soft"),
                    "target_cons": target_cons,
                    "fuel_plan": fuel_plan,
                    "refuel_litres": refuels,
                }
                c1 = opt.get("stint1_comp", "hard")
                self._var_mounted_comp.set("Prime (Duro)" if c1 == "hard" else "Alternative (Blando)")
            else:
                p1 = int(self.parent_module.fuel_data.get("pit1_lap", 15))
                self.active_strategy = {
                    "num_stops": 1,
                    "p1": p1,
                    "p2": 0,
                    "stint1_comp": "hard",
                    "stint2_comp": "soft",
                    "stint3_comp": "soft",
                    "target_cons": [base_cons] * 2,
                    "fuel_plan": None,
                    "refuel_litres": [30.0],
                }
        else:
            # Fallback a óptima o estándar si no hay datos de módulo 4
            p1 = int(self.parent_module.fuel_data.get("pit1_lap", 15))
            self.active_strategy = {
                "num_stops": 1,
                "p1": p1,
                "p2": 0,
                "stint1_comp": "hard",
                "stint2_comp": "soft",
                "stint3_comp": "soft",
                "target_cons": [base_cons] * 2,
                "fuel_plan": None,
                "refuel_litres": [30.0],
            }

        self._recalculate_all()
        self.parent_module.auto_save()

    def update_strategies_list(self, strat_names: list[str]):
        vals = ["⚡ Estrategia Óptima"] + strat_names
        self._cbo_strategy.configure(values=vals)
        if self._var_selected_strategy.get() not in vals:
            self._var_selected_strategy.set("⚡ Estrategia Óptima")

    # ─── Optimizador Táctico en Vivo (Horizonte Restante) ──────────────
    def _on_tac_params_changed(self):
        # Desactivar botones de acción hasta recalcular
        self._btn_promote.configure(state="disabled")
        if hasattr(self, "_btn_discard"):
            self._btn_discard.configure(state="disabled")
        self.tactical_result = None
        self._render_strategy_timeline()

    def _get_fuel_saving_curve(self) -> list[tuple[float, float]]:
        """
        Obtiene los puntos de calibración (delta_litros_ahorrados, delta_tiempo_perdido)
        de la tabla de combustible de la sesión para correlacionar en tiempo real.
        """
        try:
            top = self.winfo_toplevel()
            if hasattr(top, "_modules"):
                charts_mod = top._modules.get("charts")
                if charts_mod and hasattr(charts_mod, "_get_fuel_saving_curve"):
                    pts = charts_mod._get_fuel_saving_curve()
                    if pts and len(pts) > 1:
                        return pts
        except Exception:
            pass

        fdata = self.parent_module.fuel_data or {}
        rows = fdata.get("fuel_saving_rows", [])

        if not rows:
            sdata = self.parent_module.session_data or {}
            champ = sdata.get("championship_name")
            circuit = sdata.get("circuit")
            if champ and circuit:
                safe_champ = re.sub(r'[\\/*?:"<>|]', "_", champ)
                safe_circ = re.sub(r'[\\/*?:"<>|]', "_", circuit)
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
            cons_base = float(fdata.get("cons_lap", 5.65))
            pts = [(0.0, 0.0), (cons_base * 0.10, 0.35), (cons_base * 0.20, 0.80)]
        return pts

    def _interpolate_saving_penalty(self, save_per_l: float, pts: list[tuple[float, float]]) -> float:
        """
        Interpola en tiempo real la pérdida de tiempo por vuelta (s)
        para un ahorro objetivo de save_per_l (L/v), correlacionando con la tabla de combustible.
        """
        if save_per_l <= 0.001:
            return 0.0
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        if save_per_l <= xs[-1]:
            return float(np.interp(save_per_l, xs, ys))
        else:
            dx = xs[-1] - xs[-2] if len(xs) >= 2 else xs[-1]
            dy = ys[-1] - ys[-2] if len(ys) >= 2 else ys[-1]
            slope = dy / max(0.01, dx)
            return float(ys[-1] + slope * (save_per_l - xs[-1]))

    def _get_active_tyre_params(self) -> dict:
        """Obtiene parámetros activos OLS de neumáticos del Módulo 4 o fallback local."""
        try:
            top = self.winfo_toplevel()
            if hasattr(top, "_modules"):
                charts_mod = top._modules.get("charts")
                if charts_mod and hasattr(charts_mod, "_get_active_tyre_params"):
                    params = charts_mod._get_active_tyre_params()
                    if params:
                        return params
        except Exception:
            pass
        return self.parent_module.tyre_data or {}

    def solve_tactical_strategy(self):
        """
        Calcula la mejor estrategia táctica desde la vuelta actual del coche
        hasta la meta proyectada, teniendo en cuenta combustible restante,
        desgaste logarítmico OLS real de neumáticos, curvas de penalización por ahorro (Lift & Coast)
        y eventos de Safety Car (con sector de entrada y duración oficial).
        """
        sdata = self.parent_module.session_data
        fdata = self.parent_module.fuel_data
        tdata = self._get_active_tyre_params()

        base_lap_s = float(sdata.get("lap_time_seconds", 84.5))
        tank_cap = float(sdata.get("fuel_capacity_l", 70.0))
        refuel_rate = float(sdata.get("refuel_rate_ls", 12.0))
        tyre_change_s = float(sdata.get("tyre_change_time", 4.0))
        car_lift_s = float(sdata.get("car_lift_s") or sdata.get("car_lift_time") or 2.0)
        pitlane_loss_s = float(sdata.get("pitlane_loss") or sdata.get("pitlane_loss_s") or 22.5)
        weight_sens = float(fdata.get("weight_sens") or fdata.get("calc_results", {}).get("weight_sens") or 0.015)
        cons_base = float(fdata.get("cons_lap", 5.65))
        safety_l = float(fdata.get("safety_fuel_l", 2.5))
        try:
            top = self.winfo_toplevel()
            if hasattr(top, "_modules"):
                charts_mod = top._modules.get("charts")
                if charts_mod:
                    if hasattr(charts_mod, "_get_weight_sensitivity"):
                        weight_sens = float(charts_mod._get_weight_sensitivity())
                    if hasattr(charts_mod, "_get_base_consumption"):
                        cons_base = float(charts_mod._get_base_consumption())
                    if hasattr(charts_mod, "_get_safety_fuel"):
                        safety_l = float(charts_mod._get_safety_fuel())
        except Exception:
            pass
        mandatory_change = bool(sdata.get("mandatory_compound_change", True))

        race_state = self.parent_module.race_header.get_race_state()
        tot_laps = race_state["total_projected_laps"]

        # Vuelta y combustible actuales del coche
        if self.meta_records:
            curr_lap = self.meta_records[-1]["lap"]
            curr_fuel = self.meta_records[-1]["fuel"]
        else:
            curr_lap = 0
            curr_fuel = tank_cap

        if curr_lap >= tot_laps:
            self._lbl_tac_desc.configure(
                text="El coche ya ha alcanzado la bandera a cuadros.",
                text_color=self.colors["accent"],
            )
            return

        try:
            initial_tyre_lap = int(str(self._var_initial_tyre_lap.get()).strip())
        except ValueError:
            initial_tyre_lap = 0

        # Estado de la estrategia activa y progreso real en carrera
        plan_stops = self.active_strategy.get("num_stops", 1)
        plan_p1 = self.active_strategy.get("p1", 15)
        plan_p2 = self.active_strategy.get("p2", 0)
        plan_c1 = self.active_strategy.get("stint1_comp", "hard")
        plan_c2 = self.active_strategy.get("stint2_comp", "soft")
        plan_c3 = self.active_strategy.get("stint3_comp", "soft")

        # Determinar en qué stint está el coche y reconstruir fielmente el pasado
        past_stints = []
        past_stops = []
        if plan_stops == 0 or curr_lap <= plan_p1:
            st_current_idx = 0
            st_start_lap = 0
            curr_comp = plan_c1
            curr_tyre_age = curr_lap + initial_tyre_lap
        elif plan_stops == 1 and curr_lap > plan_p1:
            st_current_idx = 1
            st_start_lap = plan_p1
            past_stints = [(0, plan_p1, plan_c1)]
            past_stops = [plan_p1]
            curr_comp = plan_c2
            curr_tyre_age = max(0, curr_lap - plan_p1)
        elif plan_stops == 2:
            if curr_lap <= plan_p1:
                st_current_idx = 0
                st_start_lap = 0
                curr_comp = plan_c1
                curr_tyre_age = curr_lap + initial_tyre_lap
            elif curr_lap <= plan_p2:
                st_current_idx = 1
                st_start_lap = plan_p1
                past_stints = [(0, plan_p1, plan_c1)]
                past_stops = [plan_p1]
                curr_comp = plan_c2
                curr_tyre_age = max(0, curr_lap - plan_p1)
            else:
                st_current_idx = 2
                st_start_lap = plan_p2
                past_stints = [(0, plan_p1, plan_c1), (plan_p1, plan_p2, plan_c2)]
                past_stops = [plan_p1, plan_p2]
                curr_comp = plan_c3
                curr_tyre_age = max(0, curr_lap - plan_p2)
        else:
            st_current_idx = 1
            st_start_lap = plan_p1
            past_stints = [(0, plan_p1, plan_c1)]
            past_stops = [plan_p1]
            curr_comp = plan_c2
            curr_tyre_age = max(0, curr_lap - plan_p1)

        # Si el usuario forzó una goma diferente en _var_mounted_comp, respetarla para el stint actual
        if hasattr(self, "_var_mounted_comp") and self._var_mounted_comp.get():
            curr_comp = "hard" if "Duro" in self._var_mounted_comp.get() else "soft"

        # Parámetros OLS de neumáticos
        h_base = float(tdata.get("hard_base_lap", base_lap_s))
        h_warm = float(tdata.get("hard_warmup", 0.800))
        h_a = float(tdata.get("hard_a", 0.2223))
        h_n = float(tdata.get("hard_n", -0.1208))

        s_base = float(tdata.get("soft_base_lap", base_lap_s - 0.450))
        s_warm = float(tdata.get("soft_warmup", 0.400))
        s_a = float(tdata.get("soft_a", 0.5318))
        s_n = float(tdata.get("soft_n", -0.3968))

        # Evento Safety Car
        sc_active = self._var_tac_sc.get()
        sc_sec_str = self._var_tac_sc_sector.get()
        try:
            sc_dur = max(1, int(str(self._var_tac_sc_dur.get()).strip()))
        except ValueError:
            sc_dur = 3

        # Si el coche ha completado curr_lap, el incidente ocurre en la siguiente vuelta (curr_lap + 1)
        sc_dep_lap = curr_lap + 1
        sec_num = 1 if "1" in sc_sec_str else (2 if "2" in sc_sec_str else 3)
        frac_dep = 1.0 if sec_num == 1 else (2.0 / 3.0 if sec_num == 2 else 1.0 / 3.0)
        sc_end = sc_dep_lap + sc_dur

        saving_curve = self._get_fuel_saving_curve()
        usable_tank = max(1.0, tank_cap - safety_l)
        max_stint_save = math.floor(usable_tank / (cons_base * 0.80))

        def simulate_stint(start_v: int, end_v: int, comp: str, init_tyre_age: int, init_fuel: float, is_first: bool):
            """
            Simula un stint vuelta a vuelta sincronizado con la física del Módulo 4.
            Retorna:
                (time_total, fuel_remaining, save_per_l, time_penalty)
            o None si el stint es imposible (combustible insuficiente o ahorro > 20%).
            """
            if start_v > end_v:
                return 0.0, init_fuel, 0.0, 0.0, []

            st_len = end_v - start_v + 1
            f_needed = 0.0
            st_sc_count = 0.0
            for v in range(start_v, end_v + 1):
                if sc_active and sc_dep_lap <= v <= sc_end:
                    frac = frac_dep if v == sc_dep_lap else 1.0
                    st_sc_count += frac
                    f_needed += (1.0 - frac) * cons_base + frac * 1.80
                else:
                    f_needed += cons_base

            st_pure_green = max(0.0, st_len - st_sc_count)
            usable_f = max(0.0, init_fuel - safety_l)

            if f_needed > usable_f:
                excess = f_needed - usable_f
                if st_pure_green <= 0.001:
                    return None
                save_per_l = excess / st_pure_green
                if save_per_l > (0.20 * cons_base):
                    return None
                time_penalty = self._interpolate_saving_penalty(save_per_l, saving_curve)
            else:
                save_per_l = 0.0
                time_penalty = 0.0

            t_acc = 0.0
            f_sim = init_fuel
            tyre_x = init_tyre_age
            sc_pace_full = base_lap_s * 1.40
            f_sim_curve = []

            base_p = h_base if comp == "hard" else s_base
            warm = h_warm if comp == "hard" else s_warm
            a_val = h_a if comp == "hard" else s_a
            n_val = h_n if comp == "hard" else s_n

            for v in range(start_v, end_v + 1):
                delta_peso = min(0.0, (f_sim - tank_cap) * weight_sens)

                if tyre_x == 0:
                    t_deg = warm
                elif tyre_x == 1:
                    t_deg = 0.0
                else:
                    t_deg = max(0.0, a_val * math.log(max(1, tyre_x)) + n_val)

                t_green = base_p + t_deg + delta_peso + time_penalty

                if sc_active and sc_dep_lap <= v <= sc_end:
                    frac = frac_dep if v == sc_dep_lap else 1.0
                    t_lap = (1.0 - frac) * t_green + frac * sc_pace_full
                    cons_lap = (1.0 - frac) * cons_base + frac * 1.80
                    if (1.0 - frac) >= 0.5:
                        tyre_x += 1
                else:
                    t_lap = t_green
                    cons_lap = max(0.1, cons_base - save_per_l)
                    tyre_x += 1

                t_acc += t_lap
                f_sim = max(0.0, f_sim - cons_lap)
                f_sim_curve.append(f_sim)

            return t_acc, f_sim, save_per_l, time_penalty, f_sim_curve

        def calc_pit_time(p: int, fuel_to_load: float):
            refuel_t = fuel_to_load / max(0.1, refuel_rate)
            normal_t_box = pitlane_loss_s + car_lift_s + max(refuel_t, tyre_change_s)
            is_sc_free = False
            if sc_active and (sc_dep_lap < p < sc_end):
                t_box = 0.0
                is_sc_free = True
            elif sc_active and p == sc_dep_lap:
                t_box = normal_t_box + 30.0  # Pitlane cerrado
            else:
                t_box = normal_t_box
            return t_box, is_sc_free

        best_time = float("inf")
        best_plan = None
        comp_options = ["hard", "soft"]

        # Curva de combustible pasada hasta la vuelta actual
        if self.active_strategy.get("fuel_plan") and len(self.active_strategy["fuel_plan"]) >= curr_lap:
            past_curve = list(self.active_strategy["fuel_plan"][:curr_lap])
        else:
            past_curve = [max(0.0, tank_cap - (v * cons_base)) for v in range(1, curr_lap + 1)]

        # ── 0. Evaluar Opción a 0 Paradas Restantes (Directo a Meta) ──
        full_stints_0 = past_stints + [(st_start_lap, tot_laps, curr_comp)]
        all_comps_0 = {c for _, _, c in full_stints_0}
        if not (mandatory_change and len(all_comps_0) < 2):
            res_0 = simulate_stint(curr_lap + 1, tot_laps, curr_comp, curr_tyre_age, curr_fuel, is_first=True)
            if res_0 is not None:
                t_acc_0, f_end_0, save_l_0, pen_0, f_curve_0 = res_0
                best_time = t_acc_0
                margin_direct = f_end_0 - safety_l
                comp_name = "Prime (Duro)" if curr_comp == "hard" else "Alternative (Blando)"
                full_pit_0 = list(past_stops)

                best_plan = {
                    "rem_stops": 0,
                    "full_stops": len(full_pit_0),
                    "full_pit_laps": full_pit_0,
                    "full_stints": full_stints_0,
                    "past_stops": past_stops,
                    "num_stops": 0,
                    "p1": full_pit_0[0] if len(full_pit_0) >= 1 else 0,
                    "p2": full_pit_0[1] if len(full_pit_0) >= 2 else 0,
                    "stint1_comp": full_stints_0[0][2] if len(full_stints_0) >= 1 else curr_comp,
                    "stint2_comp": full_stints_0[1][2] if len(full_stints_0) >= 2 else curr_comp,
                    "stint3_comp": full_stints_0[2][2] if len(full_stints_0) >= 3 else curr_comp,
                    "fuel_to_load": 0.0,
                    "fuel_to_load2": 0.0,
                    "next_comp_label": f"Mantener {comp_name}",
                    "is_sc_free": False,
                    "total_rem_time": t_acc_0,
                    "margin_direct": margin_direct,
                    "save_st1": save_l_0,
                    "fuel_plan": past_curve + f_curve_0,
                    "target_cons": [cons_base - save_l_0] * 3,
                }

        # ── 1. Evaluar Opciones a 1 Parada Restante ──────────────────────
        if len(past_stops) <= 1:
            p_min_1stop = max(curr_lap + 1, tot_laps - max_stint_save)
            p_max_1stop = tot_laps - 1

            for p_cand in range(p_min_1stop, p_max_1stop + 1):
                st2_len = tot_laps - p_cand
                if st2_len > max_stint_save:
                    continue

                res_1 = simulate_stint(curr_lap + 1, p_cand, curr_comp, curr_tyre_age, curr_fuel, is_first=True)
                if res_1 is None:
                    continue
                t_st1, f_entry, save_l1, pen1, f_curve_1 = res_1

                # Combustible nominal para el stint hasta meta
                f_needed_st2 = 0.0
                for v in range(p_cand + 1, tot_laps + 1):
                    if sc_active and sc_dep_lap <= v <= sc_end:
                        frac = frac_dep if v == sc_dep_lap else 1.0
                        f_needed_st2 += (1.0 - frac) * cons_base + frac * 1.80
                    else:
                        f_needed_st2 += cons_base
                f_needed_st2 += safety_l

                fuel_to_load = min(tank_cap - f_entry, max(0.0, f_needed_st2 - f_entry))
                t_box, is_sc_free = calc_pit_time(p_cand, fuel_to_load)

                for next_comp in comp_options:
                    full_stints_1 = past_stints + [(st_start_lap, p_cand, curr_comp), (p_cand, tot_laps, next_comp)]
                    all_race_comps = {c for _, _, c in full_stints_1}
                    if mandatory_change and len(all_race_comps) < 2:
                        continue

                    res_2 = simulate_stint(p_cand + 1, tot_laps, next_comp, 0, f_entry + fuel_to_load, is_first=False)
                    if res_2 is None:
                        continue
                    t_st2, f_end, save_l2, pen2, f_curve_2 = res_2

                    t_acc = t_st1 + t_box + t_st2
                    if t_acc < best_time:
                        best_time = t_acc
                        full_pit_1 = past_stops + [p_cand]

                        if len(past_stops) == 0:
                            tgt_cons_list = [cons_base - save_l1, cons_base - save_l2, cons_base]
                        else:
                            past_tgt = self.active_strategy.get("target_cons", [cons_base])[0]
                            tgt_cons_list = [past_tgt, cons_base - save_l1, cons_base - save_l2]

                        best_plan = {
                            "rem_stops": 1,
                            "next_pit_lap": p_cand,
                            "full_stops": len(full_pit_1),
                            "full_pit_laps": full_pit_1,
                            "full_stints": full_stints_1,
                            "past_stops": past_stops,
                            "num_stops": 1,
                            "p1": full_pit_1[0] if len(full_pit_1) >= 1 else 0,
                            "p2": full_pit_1[1] if len(full_pit_1) >= 2 else 0,
                            "stint1_comp": full_stints_1[0][2] if len(full_stints_1) >= 1 else curr_comp,
                            "stint2_comp": full_stints_1[1][2] if len(full_stints_1) >= 2 else next_comp,
                            "stint3_comp": full_stints_1[2][2] if len(full_stints_1) >= 3 else "soft",
                            "fuel_to_load": fuel_to_load,
                            "fuel_to_load2": 0.0,
                            "next_comp_label": "Prime (Duro)" if next_comp == "hard" else "Alternative (Blando)",
                            "is_sc_free": is_sc_free,
                            "total_rem_time": t_acc,
                            "save_st1": save_l1,
                            "save_st2": save_l2,
                            "fuel_plan": past_curve + f_curve_1 + f_curve_2,
                            "target_cons": tgt_cons_list,
                        }

        # ── 2. Evaluar Opciones a 2 Paradas Restantes ────────────────────
        # Solo posible si NO hay paradas pasadas completadas (carrera de máx 2 paradas)
        if len(past_stops) == 0:
            p1_min_2stop = curr_lap + 1
            p1_max_2stop = tot_laps - 2

            for p1_cand in range(p1_min_2stop, p1_max_2stop + 1):
                res_1 = simulate_stint(curr_lap + 1, p1_cand, curr_comp, curr_tyre_age, curr_fuel, is_first=True)
                if res_1 is None:
                    continue
                t_st1, f_entry1, save_l1, pen1, f_curve_1 = res_1

                p2_min = p1_cand + 1
                p2_max = min(p1_cand + max_stint_save, tot_laps - 1)

                for p2_cand in range(p2_min, p2_max + 1):
                    st3_len = tot_laps - p2_cand
                    if st3_len > max_stint_save:
                        continue

                    f_needed_st2 = 0.0
                    for v in range(p1_cand + 1, p2_cand + 1):
                        if sc_active and sc_dep_lap <= v <= sc_end:
                            frac = frac_dep if v == sc_dep_lap else 1.0
                            f_needed_st2 += (1.0 - frac) * cons_base + frac * 1.80
                        else:
                            f_needed_st2 += cons_base
                    f_needed_st2 += safety_l

                    fuel_to_load1 = min(tank_cap - f_entry1, max(0.0, f_needed_st2 - f_entry1))
                    t_box1, is_sc_free1 = calc_pit_time(p1_cand, fuel_to_load1)

                    f_needed_st3 = 0.0
                    for v in range(p2_cand + 1, tot_laps + 1):
                        if sc_active and sc_dep_lap <= v <= sc_end:
                            frac = frac_dep if v == sc_dep_lap else 1.0
                            f_needed_st3 += (1.0 - frac) * cons_base + frac * 1.80
                        else:
                            f_needed_st3 += cons_base
                    f_needed_st3 += safety_l

                    for c_next in comp_options:
                        res_2 = simulate_stint(p1_cand + 1, p2_cand, c_next, 0, f_entry1 + fuel_to_load1, is_first=False)
                        if res_2 is None:
                            continue
                        t_st2, f_entry2, save_l2, pen2, f_curve_2 = res_2

                        fuel_to_load2 = min(tank_cap - f_entry2, max(0.0, f_needed_st3 - f_entry2))
                        t_box2, is_sc_free2 = calc_pit_time(p2_cand, fuel_to_load2)

                        for c_final in comp_options:
                            full_stints_2 = [(st_start_lap, p1_cand, curr_comp), (p1_cand, p2_cand, c_next), (p2_cand, tot_laps, c_final)]
                            all_race_comps = {curr_comp, c_next, c_final}
                            if mandatory_change and len(all_race_comps) < 2:
                                continue

                            res_3 = simulate_stint(p2_cand + 1, tot_laps, c_final, 0, f_entry2 + fuel_to_load2, is_first=False)
                            if res_3 is None:
                                continue
                            t_st3, f_end, save_l3, pen3, f_curve_3 = res_3

                            t_acc = t_st1 + t_box1 + t_st2 + t_box2 + t_st3

                            if t_acc < best_time:
                                best_time = t_acc
                                full_pit_2 = [p1_cand, p2_cand]

                                best_plan = {
                                    "rem_stops": 2,
                                    "next_pit_lap": p1_cand,
                                    "next_pit_lap2": p2_cand,
                                    "full_stops": 2,
                                    "full_pit_laps": full_pit_2,
                                    "full_stints": full_stints_2,
                                    "past_stops": [],
                                    "num_stops": 2,
                                    "p1": p1_cand,
                                    "p2": p2_cand,
                                    "stint1_comp": curr_comp,
                                    "stint2_comp": c_next,
                                    "stint3_comp": c_final,
                                    "fuel_to_load": fuel_to_load1,
                                    "fuel_to_load2": fuel_to_load2,
                                    "next_comp_label": "Prime (Duro)" if c_next == "hard" else "Alternative (Blando)",
                                    "is_sc_free": is_sc_free1,
                                    "total_rem_time": t_acc,
                                    "save_st1": save_l1,
                                    "save_st2": save_l2,
                                    "save_st3": save_l3,
                                    "fuel_plan": past_curve + f_curve_1 + f_curve_2 + f_curve_3,
                                    "target_cons": [cons_base - save_l1, cons_base - save_l2, cons_base - save_l3],
                                }

        if best_plan:
            self.tactical_result = best_plan
            sc_note = " 🟡 ¡PARADA GRATIS BAJO SC!" if best_plan["is_sc_free"] else ""
            rem_stops = best_plan.get("rem_stops", best_plan["num_stops"])
            past_count = len(best_plan.get("past_stops", []))
            next_box_num = past_count + 1

            if rem_stops == 0:
                m_txt = f"+{best_plan.get('margin_direct', 0.0):.1f} L" if best_plan.get('margin_direct', 0.0) >= 0 else f"{best_plan.get('margin_direct', 0.0):.1f} L"
                save_txt = f"  ·  Ahorro: {cons_base - best_plan.get('save_st1', 0.0):.2f} L/v" if best_plan.get('save_st1', 0.0) > 0.01 else ""
                desc = (
                    f"Sugerencia (0 Paradas restantes): Ir a meta directo sin parar más\n"
                    f"Gomas: {best_plan['next_comp_label']}  |  Margen: {m_txt}{save_txt}\n"
                    f"Tiempo restante est: {format_seconds_to_clock(best_time)}"
                )
            elif rem_stops == 1:
                next_pit = best_plan.get("next_pit_lap", best_plan["p1"])
                save1_txt = f" (S{next_box_num}: {cons_base - best_plan.get('save_st1', 0.0):.2f} L/v)" if best_plan.get('save_st1', 0.0) > 0.01 else ""
                save2_txt = f" (S{next_box_num + 1}: {cons_base - best_plan.get('save_st2', 0.0):.2f} L/v)" if best_plan.get('save_st2', 0.0) > 0.01 else ""
                save_note = f"\n• Lift & Coast requerido{save1_txt}{save2_txt}" if (save1_txt or save2_txt) else ""
                box_str = f"Box {next_box_num}" if past_count > 0 else "Box"
                desc = (
                    f"Sugerencia (1 Parada restante): {box_str} Fin V{next_pit}{sc_note}\n"
                    f"Compuesto: {best_plan['next_comp_label']}  |  Cargar: {best_plan['fuel_to_load']:.1f} L{save_note}\n"
                    f"Tiempo restante est: {format_seconds_to_clock(best_time)}"
                )
            else:
                p1_box = best_plan.get("next_pit_lap", best_plan["p1"])
                p2_box = best_plan.get("next_pit_lap2", best_plan["p2"])
                c2_lbl = "Prime (Duro)" if best_plan["stint2_comp"] == "hard" else "Alternative (Blando)"
                c3_lbl = "Prime (Duro)" if best_plan.get("stint3_comp", "soft") == "hard" else "Alternative (Blando)"
                sc_line = f" {sc_note}" if sc_note else ""
                load2_txt = "Solo Ruedas" if best_plan.get("fuel_to_load2", 0.0) <= 0.01 else f"+{best_plan.get('fuel_to_load2', 0.0):.1f}L"
                b1_str = f"Box {next_box_num}" if past_count > 0 else "Box 1"
                b2_str = f"Box {next_box_num + 1}" if past_count > 0 else "Box 2"
                s2_id = f"S{next_box_num + 1}" if past_count > 0 else "S2"
                s3_id = f"S{next_box_num + 2}" if past_count > 0 else "S3"
                desc = (
                    f"Sugerencia (2 Paradas restantes){sc_line}:\n"
                    f"• {b1_str}: Fin V{p1_box} (+{best_plan['fuel_to_load']:.1f}L · {s2_id} {c2_lbl})\n"
                    f"• {b2_str}: Fin V{p2_box} ({load2_txt} · {s3_id} {c3_lbl})\n"
                    f"Tiempo restante est: {format_seconds_to_clock(best_time)}"
                )
            self._lbl_tac_desc.configure(text=desc, text_color=self.colors["text_primary"])
            self._btn_promote.configure(state="normal")
            if hasattr(self, "_btn_discard"):
                self._btn_discard.configure(state="normal")
            self._render_strategy_timeline()
        else:
            self.tactical_result = None
            self._lbl_tac_desc.configure(
                text="No se encontró una ventana viable; revisa el combustible y paradas.",
                text_color="#FF6B6B",
            )
            self._btn_promote.configure(state="disabled")
            if hasattr(self, "_btn_discard"):
                self._btn_discard.configure(state="disabled")
            self._render_strategy_timeline()

    def promote_tactical_strategy(self):
        """Aplica la estrategia táctica recalculada como la nueva estrategia de referencia activa."""
        if not self.tactical_result:
            return

        full_stops = self.tactical_result.get("full_stops", self.tactical_result["num_stops"])
        full_pits = self.tactical_result.get("full_pit_laps", [])
        self.active_strategy["num_stops"] = min(2, full_stops)
        self.active_strategy["p1"] = full_pits[0] if len(full_pits) >= 1 else self.tactical_result.get("p1", 0)
        self.active_strategy["p2"] = full_pits[1] if len(full_pits) >= 2 else self.tactical_result.get("p2", 0)
        if "stint1_comp" in self.tactical_result:
            self.active_strategy["stint1_comp"] = self.tactical_result["stint1_comp"]
        self.active_strategy["stint2_comp"] = self.tactical_result["stint2_comp"]
        self.active_strategy["stint3_comp"] = self.tactical_result.get("stint3_comp", "soft")
        if "target_cons" in self.tactical_result:
            self.active_strategy["target_cons"] = self.tactical_result["target_cons"]
        if "fuel_plan" in self.tactical_result:
            self.active_strategy["fuel_plan"] = self.tactical_result["fuel_plan"]

        rem = self.tactical_result.get("rem_stops", self.tactical_result["num_stops"])
        if rem == 0:
            self._lbl_tac_desc.configure(
                text="✔ ¡Estrategia Promocionada! Mantener en pista hasta meta (0 paradas restantes).",
                text_color=self.colors["success"],
            )
        else:
            next_pit = self.tactical_result.get("next_pit_lap", self.tactical_result["p1"])
            self._lbl_tac_desc.configure(
                text=f"✔ ¡Estrategia Promocionada! Próxima parada fijada en Fin V{next_pit}.",
                text_color=self.colors["success"],
            )
        self._btn_promote.configure(state="disabled")
        if hasattr(self, "_btn_discard"):
            self._btn_discard.configure(state="disabled")
        self._render_strategy_timeline()
        self._recalculate_all()
        self.parent_module.auto_save()

    def discard_tactical_strategy(self):
        """Descarta la sugerencia táctica actual y restaura la vista en tiempo real."""
        self.tactical_result = None
        self._lbl_tac_desc.configure(
            text="Sugerencia descartada. Pulsa 'Recalcular' para nueva proyección.",
            text_color=self.colors["text_secondary"],
        )
        self._btn_promote.configure(state="disabled")
        if hasattr(self, "_btn_discard"):
            self._btn_discard.configure(state="disabled")
        self._render_strategy_timeline()

    # ─── Serialización y Persistencia ──────────────────────────────────
    def to_dict(self) -> dict:
        return {
            "name": self._var_name.get(),
            "strategy_name": self._var_selected_strategy.get(),
            "initial_tyre_lap": self._var_initial_tyre_lap.get(),
            "mounted_comp": self._var_mounted_comp.get(),
            "meta_records": self.meta_records,
            "active_strategy": self.active_strategy,
            "tac_sc": self._var_tac_sc.get(),
            "tac_sc_sector": self._var_tac_sc_sector.get(),
            "tac_sc_dur": self._var_tac_sc_dur.get(),
        }

    def from_dict(self, data: dict):
        if not data:
            return
        self._var_name.set(data.get("name", f"Piloto {self.pilot_id}"))
        self._var_selected_strategy.set(data.get("strategy_name", "⚡ Estrategia Óptima"))
        self._var_initial_tyre_lap.set(str(data.get("initial_tyre_lap", "0")))
        self._var_mounted_comp.set(data.get("mounted_comp", "Prime (Duro)"))
        self.meta_records = data.get("meta_records", [])
        self.active_strategy = data.get("active_strategy", self.active_strategy)
        if "tac_sc" in data:
            self._var_tac_sc.set(bool(data["tac_sc"]))
        if "tac_sc_sector" in data:
            self._var_tac_sc_sector.set(str(data["tac_sc_sector"]))
        if "tac_sc_dur" in data:
            self._var_tac_sc_dur.set(str(data["tac_sc_dur"]))

        if self.meta_records:
            last_lap = self.meta_records[-1]["lap"]
            self._var_quick_lap.set(str(last_lap + 1))
        else:
            self._var_quick_lap.set("1")

        self._render_table_rows()
        self._recalculate_all()

    def _forward_mouse_wheel(self, ev):
        """Reenvía el evento de rueda del ratón desde el Canvas al CTkScrollableFrame padre."""
        try:
            scroll = getattr(self.parent_module, "_scroll", None)
            if scroll is not None and hasattr(scroll, "_parent_canvas"):
                delta = getattr(ev, "delta", 0)
                if delta:
                    scroll._parent_canvas.yview("scroll", -int(delta / 6), "units")
        except Exception:
            pass


# ================================================================================
#  CLASE PRINCIPAL: LiveControlModule (Módulo 5)
# ================================================================================
class LiveControlModule(ctk.CTkFrame):
    """Módulo 5 — Control en Vivo y Live Timing de Carrera para Team NIX Esports."""

    def __init__(self, parent, colors: dict, **kwargs):
        super().__init__(parent, fg_color=colors["bg_primary"], **kwargs)
        self.colors = colors

        self.session_data: dict = {}
        self.fuel_data: dict = {}
        self.tyre_data: dict = {}
        self.saved_strategies: dict = {}
        self.optimal_strategy: dict = {}

        self._build_ui()

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

        # ── 1. Cabecera de Carrera (Race Control) ──────────────────────────
        self.race_header = RaceControlHeader(
            self._scroll, colors=self.colors,
            on_update_callback=self._on_race_control_updated,
        )
        self.race_header.pack(fill="x", padx=16, pady=(16, 10))

        # ── 2. Contenedor de las 3 Columnas de Pilotos ────────────────────
        self._pilots_container = ctk.CTkFrame(self._scroll, fg_color="transparent")
        self._pilots_container.pack(fill="x", padx=16, pady=(0, 10))
        self._pilots_container.grid_columnconfigure((0, 1, 2), weight=1)
        self._pilots_container.grid_rowconfigure(0, weight=1)

        self.pilots: list[PilotLiveCard] = []
        for i in range(1, 4):
            card = PilotLiveCard(self._pilots_container, pilot_id=i, colors=self.colors, parent_module=self)
            self.pilots.append(card)
        # Responsive: 3 pilotos en columnas; en ventanas estrechas 2 (o 1) por fila
        self._pilots_grid = ResponsiveGrid(self._pilots_container, self.pilots, max_cols=3, min_col_width=300,
                                           grid_kw=dict(padx=6, pady=(0, 10), sticky="nsew"))

        # ── 3. Barra de Acciones Globales (Inferior) ───────────────────────
        bar = ctk.CTkFrame(self._scroll, fg_color="transparent")
        bar.pack(fill="x", padx=16, pady=(0, 20))

        ctk.CTkButton(
            bar, text="💾 Guardar Sesión en Vivo", height=32, corner_radius=6,
            fg_color=self.colors["accent"], hover_color=self.colors["accent_hover"],
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=self.save_live_session,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            bar, text="🔄 Recargar", height=32, corner_radius=6,
            fg_color=self.colors["input_bg"], hover_color=self.colors["border"],
            font=ctk.CTkFont(family="Segoe UI", size=12),
            command=self.load_live_session,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            bar, text="🗑️ Resetear Todos los Datos", height=32, corner_radius=6,
            fg_color="#331111", hover_color="#551111", text_color="#FF6B6B",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=self.reset_all_data,
        ).pack(side="right")

    def _on_race_control_updated(self, race_info: dict):
        """Notifica a las tarjetas de los 3 pilotos cuando cambia el reloj o vuelta del líder."""
        for p in self.pilots:
            p._recalculate_all()
        self.auto_save()

    def get_optimal_strategy_data(self) -> dict | None:
        """Obtiene la configuración óptima calculada en el Módulo 4."""
        if getattr(self, "optimal_strategy", None):
            return self.optimal_strategy
        try:
            top = self.winfo_toplevel()
            if hasattr(top, "_modules"):
                charts_mod = top._modules.get("charts")
                if charts_mod and hasattr(charts_mod, "get_optimal_strategy_config"):
                    cfg = charts_mod.get_optimal_strategy_config()
                    if cfg:
                        self.optimal_strategy = cfg
                        return cfg
        except Exception:
            pass
        return None

    def simulate_strategy_config(self, st_data: dict) -> dict | None:
        """Invoca la simulación de estrategia del Módulo 4 para obtener fuel_remaining y targets."""
        try:
            top = self.winfo_toplevel()
            if hasattr(top, "_modules"):
                charts_mod = top._modules.get("charts")
                if charts_mod and hasattr(charts_mod, "simulate_strategy_for_config"):
                    return charts_mod.simulate_strategy_for_config(st_data)
        except Exception:
            pass
        return None

    # ─── Métodos de Enlace con el Orquestador main.py ──────────────────
    def on_session_data_updated(self, session_data: dict):
        self.session_data = session_data or {}
        # Sincronizar parámetros de cabecera del líder
        self.race_header.update_session_params(self.session_data)
        if not self.saved_strategies:
            try:
                top = self.winfo_toplevel()
                if hasattr(top, "_modules"):
                    charts_mod = top._modules.get("charts")
                    if charts_mod and hasattr(charts_mod, "_load_saved_strategies_dict"):
                        self.saved_strategies = charts_mod._load_saved_strategies_dict() or {}
            except Exception:
                pass
        self.load_live_session()

    def on_fuel_strategy_updated(self, fuel_data: dict):
        self.fuel_data = fuel_data or {}
        for p in self.pilots:
            p._recalculate_all()

    def on_tyre_strategy_updated(self, tyre_data: dict):
        self.tyre_data = tyre_data or {}

    def on_strategies_updated(self, strategies_dict: dict, optimal_config: dict | None = None):
        self.saved_strategies = strategies_dict or {}
        if optimal_config:
            self.optimal_strategy = optimal_config
        else:
            self.get_optimal_strategy_data()
        names = list(self.saved_strategies.keys())
        for p in self.pilots:
            p.update_strategies_list(names)
            p._recalculate_all()

    # ─── Persistencia en profiles/<campeonato>/<circuito>_live.json ────
    def _get_live_profile_path(self) -> Path | None:
        champ = self.session_data.get("championship_name")
        circuit = self.session_data.get("circuit")
        if not champ or not circuit:
            return None
        safe_champ = re.sub(r'[\\/*?:"<>|]', "_", champ)
        safe_circ  = re.sub(r'[\\/*?:"<>|]', "_", circuit)
        return PROFILES_ROOT / safe_champ / f"{safe_circ}_live.json"

    def save_live_session(self):
        path = self._get_live_profile_path()
        if not path:
            return
        state = {
            "race_header": self.race_header.get_race_state(),
            "pilots": [p.to_dict() for p in self.pilots],
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[save_live_session] Error: {e}")

    def auto_save(self):
        """Guardado silencioso sin alertas visuales."""
        self.save_live_session()

    def load_live_session(self):
        path = self._get_live_profile_path()
        if not path or not path.exists():
            return
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            if "race_header" in state:
                self.race_header.set_race_state(state["race_header"])
            if "pilots" in state and len(state["pilots"]) == 3:
                for i, p_data in enumerate(state["pilots"]):
                    self.pilots[i].from_dict(p_data)
        except Exception as e:
            print(f"[load_live_session] Error: {e}")

    def reset_all_data(self):
        confirm = messagebox.askyesno(
            "Resetear Sesión en Vivo",
            "¿Deseas reiniciar todas las tablas y cruces por meta de los 3 pilotos?",
        )
        if not confirm:
            return
        self.race_header._var_leader_lap.set("0")
        self.race_header._on_params_changed()
        for p in self.pilots:
            p.meta_records = []
            p._var_quick_lap.set("1")
            p._var_quick_fuel.set("")
            p._render_table_rows()
            p._recalculate_all()
        self.save_live_session()
