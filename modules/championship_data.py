"""
============================================================
 MÓDULO 1: Datos del Campeonato — Sistema de Perfiles v2
============================================================
 Arquitectura de dos niveles:

 NIVEL 1 — Campeonato (constantes del coche/reglamento):
   Car, capacidad depósito, ratio de repostaje,
   duración de carrera, compuestos obligatorios.
   → profiles/<campeonato>/_campeonato.json

 NIVEL 2 — Circuito (variables por trazado):
   Nombre del circuito, tiempo de vuelta, pitlane loss,
   tiempo de cambio de neumáticos.
   → profiles/<campeonato>/<circuito>.json

 Los circuitos están vinculados a cada campeonato.
 get_session_data() fusiona ambos niveles en un único dict
 para el consumo de los módulos de cálculo.
============================================================
"""

import customtkinter as ctk
import re
import json
import os
import sys
import shutil
from pathlib import Path
from tkinter import messagebox

# Raíz de perfiles dinámica (compatible con .py y con .exe compilado)
APP_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
PROFILES_ROOT = APP_ROOT / "profiles"
CHAMPIONSHIP_FILE = "_campeonato.json"


class ChampionshipDataModule(ctk.CTkFrame):
    """
    Módulo 1 — Datos del Campeonato.

    Flujo de uso:
      1. Seleccionar (o crear) un campeonato → carga constantes del coche.
      2. Seleccionar (o crear) un circuito del campeonato → carga variables.
      3. Pulsar "Guardar Sesión" → consolida session_data para los demás módulos.
    """

    RACE_DURATION_MINUTES = 60   # Duración estándar God League

    def __init__(self, parent, colors: dict, **kwargs):
        super().__init__(parent, fg_color=colors["bg_primary"], **kwargs)
        self.colors = colors
        self.session_data: dict = {}

        # ── StringVars: Campeonato (constantes) ──────────────
        self._var_champ_name      = ctk.StringVar(value="")
        self._var_car             = ctk.StringVar(value="Dallara IR-18")
        self._var_fuel_capacity   = ctk.StringVar(value="70")
        self._var_refuel_rate     = ctk.StringVar(value="12.0")
        self._var_race_duration   = ctk.StringVar(value=str(self.RACE_DURATION_MINUTES))
        self._var_tyre_change     = ctk.StringVar(value="4.0")
        self._var_car_lift        = ctk.StringVar(value="2.0")
        self._var_compound_1      = ctk.StringVar(value="Prime (Duro)")
        self._var_compound_2      = ctk.StringVar(value="Alternative (Blando)")

        # ── StringVars: Circuito (variables) ─────────────────
        self._var_circuit         = ctk.StringVar(value="")
        self._var_lap_time        = ctk.StringVar(value="01:30.000")
        self._var_pitlane_loss    = ctk.StringVar(value="22.5")
        self._var_track_length    = ctk.StringVar(value="5.47")
        self._var_sc_speed        = ctk.StringVar(value="72.0")

        # Estado de edición
        self._champ_form_visible  = False
        self._circuit_form_visible = False
        self._active_championship: str | None = None   # Nombre del campeonato activo

        # Error labels por campo
        self._error_labels: dict[str, ctk.CTkLabel] = {}

        PROFILES_ROOT.mkdir(parents=True, exist_ok=True)
        self._build_ui()

    # ═══════════════════════════════════════════════════════════
    #  CONSTRUCCIÓN DE LA UI
    # ═══════════════════════════════════════════════════════════

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_header()
        self._build_scroll()

    # ─── Header ──────────────────────────────────────────────
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

        # Barra de acento NIX
        ctk.CTkFrame(
            header, width=4, corner_radius=0, fg_color=self.colors["accent"]
        ).grid(row=0, column=0, sticky="ns", padx=(0, 16), pady=0)

        text_frame = ctk.CTkFrame(header, fg_color="transparent")
        text_frame.grid(row=0, column=1, sticky="w", pady=14)

        ctk.CTkLabel(
            text_frame,
            text="🏁  Datos del Campeonato",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=self.colors["text_primary"],
        ).pack(anchor="w")

        ctk.CTkLabel(
            text_frame,
            text="Selecciona campeonato y circuito · NIX Esports | Dallara IR-18",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=self.colors["text_secondary"],
        ).pack(anchor="w")

    # ─── Scroll principal ─────────────────────────────────────
    def _build_scroll(self):
        self._scroll = ctk.CTkScrollableFrame(
            self,
            fg_color=self.colors["bg_primary"],
            scrollbar_button_color=self.colors["border"],
            scrollbar_button_hover_color=self.colors["accent"],
        )
        self._scroll.grid(row=1, column=0, sticky="nsew")
        self._scroll.grid_columnconfigure(0, weight=1)

        self._build_step1_championship()
        self._build_step2_circuit()
        self._build_actions()

    # ═══════════════════════════════════════════════════════════
    #  PASO 1 — CAMPEONATO
    # ═══════════════════════════════════════════════════════════

    def _build_step1_championship(self):
        """Selector de campeonato + formulario inline colapsable."""

        # ── Cabecera del paso ────────────────────────────────
        step_header = self._make_step_header(
            self._scroll, row=0,
            number="01", title="Campeonato",
            subtitle="Constantes del reglamento y del coche",
        )

        # ── Barra de selector ────────────────────────────────
        bar = ctk.CTkFrame(self._scroll, fg_color=self.colors["bg_secondary"],
                           corner_radius=10, border_width=1, border_color=self.colors["border"])
        bar.grid(row=1, column=0, sticky="ew", padx=32, pady=(4, 0))
        bar.grid_columnconfigure(0, weight=1)

        inner = ctk.CTkFrame(bar, fg_color="transparent")
        inner.grid(row=0, column=0, padx=16, pady=12, sticky="ew")
        inner.grid_columnconfigure(0, weight=1)

        row_sel = ctk.CTkFrame(inner, fg_color="transparent")
        row_sel.grid(row=0, column=0, sticky="ew")
        row_sel.grid_columnconfigure(0, weight=1)

        # ComboBox campeonatos
        self._champ_combo_var = ctk.StringVar(value="— Selecciona o crea un campeonato —")
        self._champ_combo = ctk.CTkComboBox(
            row_sel,
            variable=self._champ_combo_var,
            values=self._list_championships(),
            height=40, corner_radius=8,
            fg_color=self.colors["input_bg"],
            border_color=self.colors["border"],
            button_color=self.colors["accent"],
            button_hover_color=self.colors["accent_hover"],
            dropdown_fg_color=self.colors["bg_secondary"],
            text_color=self.colors["text_primary"],
            font=ctk.CTkFont(family="Segoe UI", size=13),
            state="readonly",
            command=self._on_championship_selected,
        )
        self._champ_combo.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        # Botón editar (visible solo cuando hay campeonato activo)
        self._btn_edit_champ = ctk.CTkButton(
            row_sel, text="✏️ Editar", width=85, height=40, corner_radius=8,
            fg_color=self.colors["bg_primary"], hover_color=self.colors["border"],
            border_width=1, border_color=self.colors["border"],
            text_color=self.colors["text_primary"],
            font=ctk.CTkFont(family="Segoe UI", size=12),
            command=self._toggle_champ_form,
        )
        self._btn_edit_champ.grid(row=0, column=1, padx=(0, 6))
        self._btn_edit_champ.grid_remove()  # Oculto hasta que se seleccione campeonato

        # Botón borrar campeonato
        self._btn_delete_champ = ctk.CTkButton(
            row_sel, text="🗑️ Borrar", width=80, height=40, corner_radius=8,
            fg_color="#2A1010", hover_color="#5A1515",
            border_width=1, border_color="#FF453A",
            text_color="#FF6B6B",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=self._delete_championship,
        )
        self._btn_delete_champ.grid(row=0, column=2, padx=(0, 6))
        self._btn_delete_champ.grid_remove()  # Oculto hasta que se seleccione campeonato

        # Botón nuevo campeonato
        ctk.CTkButton(
            row_sel, text="＋ Nuevo", width=85, height=40, corner_radius=8,
            fg_color=self.colors["accent"], hover_color=self.colors["accent_hover"],
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=self._new_championship,
        ).grid(row=0, column=3)

        # ── Card de resumen del campeonato activo ─────────────
        self._champ_summary_frame = ctk.CTkFrame(inner, fg_color="transparent")
        self._champ_summary_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        # Vacío hasta que se cargue un campeonato

        # ── Formulario inline (colapsable) ───────────────────
        self._champ_form_frame = ctk.CTkFrame(
            self._scroll,
            fg_color=self.colors["bg_secondary"],
            corner_radius=10,
            border_width=1,
            border_color=self.colors["accent"],
        )
        # No se hace grid aún — se muestra/oculta con _toggle_champ_form()
        self._champ_form_row = 2   # Fila en el scroll donde aparece el formulario
        self._build_champ_form_content(self._champ_form_frame)

    def _build_champ_form_content(self, parent):
        """Campos del formulario de campeonato (dentro del frame colapsable)."""
        parent.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            parent,
            text="⚙️  Configuración del Campeonato",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=self.colors["accent"],
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(14, 6))

        fields = [
            ("Nombre del Campeonato",         "ej. God League 2024",       self._var_champ_name,    "champ_name",    None,                              ""),
            ("Coche / Vehículo",              "ej. Dallara IR-18",         self._var_car,           "car",           None,                              ""),
            ("Capacidad del Depósito",        "Litros totales del tanque", self._var_fuel_capacity, "fuel_capacity", self._validate_positive_float,     "L"),
            ("Ratio de Repostaje",            "Velocidad en litros/s",     self._var_refuel_rate,   "refuel_rate",   self._validate_positive_float,     "L/s"),
            ("Tiempo de Cambio de Ruedas",    "Tiempo del equipo en boxes",self._var_tyre_change,   "tyre_change",   self._validate_positive_float,     "s"),
            ("Tiempo de Levantar Coche",      "Elevación en gatos (jack time)", self._var_car_lift, "car_lift",     self._validate_positive_float,     "s"),
            ("Duración de la Carrera",        "En minutos",                self._var_race_duration, "race_duration", self._validate_positive_float,     "min"),
            ("Compuesto 1 (Duro/Prime)",      "Nombre del compuesto duro", self._var_compound_1,    "compound_1",    None,                              ""),
            ("Compuesto 2 (Blando/Alt.)",     "Nombre del compuesto blando",self._var_compound_2,   "compound_2",    None,                              ""),
        ]

        for i, (label, desc, var, fid, validate_fn, unit) in enumerate(fields):
            self._build_inline_field(parent, row=i + 1, label=label, desc=desc,
                                     var=var, field_id=fid, validate_fn=validate_fn, unit=unit)

        # Botones guardar / cancelar
        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.grid(row=len(fields) + 1, column=0, pady=(10, 16), padx=20, sticky="w")

        ctk.CTkButton(
            btn_row, text="💾 Guardar Campeonato", height=38, corner_radius=8,
            fg_color=self.colors["accent"], hover_color=self.colors["accent_hover"],
            text_color="#FFFFFF", font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            command=self._save_championship,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_row, text="✕ Cancelar", height=38, corner_radius=8, width=100,
            fg_color=self.colors["bg_primary"], hover_color=self.colors["border"],
            border_width=1, border_color=self.colors["border"],
            text_color=self.colors["text_secondary"],
            font=ctk.CTkFont(family="Segoe UI", size=13),
            command=lambda: self._toggle_champ_form(force_close=True),
        ).pack(side="left")

    # ═══════════════════════════════════════════════════════════
    #  PASO 2 — CIRCUITO
    # ═══════════════════════════════════════════════════════════

    def _build_step2_circuit(self):
        """Selector de circuito + formulario inline colapsable."""

        self._make_step_header(
            self._scroll, row=4,
            number="02", title="Circuito",
            subtitle="Variables específicas del trazado",
        )

        # ── Barra de selector ────────────────────────────────
        bar = ctk.CTkFrame(self._scroll, fg_color=self.colors["bg_secondary"],
                           corner_radius=10, border_width=1, border_color=self.colors["border"])
        bar.grid(row=5, column=0, sticky="ew", padx=32, pady=(4, 0))
        bar.grid_columnconfigure(0, weight=1)

        inner = ctk.CTkFrame(bar, fg_color="transparent")
        inner.grid(row=0, column=0, padx=16, pady=12, sticky="ew")
        inner.grid_columnconfigure(0, weight=1)

        row_sel = ctk.CTkFrame(inner, fg_color="transparent")
        row_sel.grid(row=0, column=0, sticky="ew")
        row_sel.grid_columnconfigure(0, weight=1)

        # ComboBox circuitos
        self._circuit_combo_var = ctk.StringVar(value="— Primero selecciona un campeonato —")
        self._circuit_combo = ctk.CTkComboBox(
            row_sel,
            variable=self._circuit_combo_var,
            values=[],
            height=40, corner_radius=8,
            fg_color=self.colors["input_bg"],
            border_color=self.colors["border"],
            button_color=self.colors["accent_dim"],
            button_hover_color=self.colors["accent"],
            dropdown_fg_color=self.colors["bg_secondary"],
            text_color=self.colors["text_secondary"],
            font=ctk.CTkFont(family="Segoe UI", size=13),
            state="disabled",
            command=self._on_circuit_selected,
        )
        self._circuit_combo.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        # Botón editar circuito
        self._btn_edit_circuit = ctk.CTkButton(
            row_sel, text="✏️ Editar", width=85, height=40, corner_radius=8,
            fg_color=self.colors["bg_primary"], hover_color=self.colors["border"],
            border_width=1, border_color=self.colors["border"],
            text_color=self.colors["text_primary"],
            font=ctk.CTkFont(family="Segoe UI", size=12),
            command=self._toggle_circuit_form,
            state="disabled",
        )
        self._btn_edit_circuit.grid(row=0, column=1, padx=(0, 6))

        # Botón borrar circuito
        self._btn_delete_circuit = ctk.CTkButton(
            row_sel, text="🗑️ Borrar", width=80, height=40, corner_radius=8,
            fg_color="#2A1010", hover_color="#5A1515",
            border_width=1, border_color="#FF453A",
            text_color="#FF6B6B",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=self._delete_circuit,
            state="disabled",
        )
        self._btn_delete_circuit.grid(row=0, column=2, padx=(0, 6))

        # Botón nuevo circuito
        self._btn_new_circuit = ctk.CTkButton(
            row_sel, text="＋ Nuevo", width=85, height=40, corner_radius=8,
            fg_color=self.colors["accent_dim"], hover_color=self.colors["accent"],
            text_color=self.colors["text_secondary"],
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=self._new_circuit,
            state="disabled",
        )
        self._btn_new_circuit.grid(row=0, column=3)

        # Card resumen circuito activo
        self._circuit_summary_frame = ctk.CTkFrame(inner, fg_color="transparent")
        self._circuit_summary_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))

        # Formulario inline del circuito (colapsable)
        self._circuit_form_frame = ctk.CTkFrame(
            self._scroll,
            fg_color=self.colors["bg_secondary"],
            corner_radius=10,
            border_width=1,
            border_color=self.colors["accent"],
        )
        self._circuit_form_row = 6
        self._build_circuit_form_content(self._circuit_form_frame)

    def _build_circuit_form_content(self, parent):
        """Campos del formulario de circuito (dentro del frame colapsable)."""
        parent.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            parent,
            text="🏎️  Configuración del Circuito",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=self.colors["accent"],
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(14, 6))

        fields = [
            ("Nombre del Circuito",                    "ej. Watkins Glen International — Boot",     self._var_circuit,      "circuit",      None,                            ""),
            ("Tiempo Medio de Vuelta",                 "Formato MM:SS.mmm  (ej. 01:24.500)",        self._var_lap_time,     "lap_time",     self._validate_lap_time,         ""),
            ("Pérdida por Pitlane",                    "Segundos perdidos al cruzar el pitlane",    self._var_pitlane_loss, "pitlane_loss", self._validate_positive_float,   "s"),
            ("Longitud del Trazado",                   "Longitud de la pista en kilómetros",        self._var_track_length, "track_length", self._validate_positive_float,   "km"),
            ("Velocidad Safety Car",                   "Velocidad reglamentaria del SC",            self._var_sc_speed,     "sc_speed",     self._validate_positive_float,   "km/h"),
        ]

        for i, (label, desc, var, fid, validate_fn, unit) in enumerate(fields):
            self._build_inline_field(parent, row=i + 1, label=label, desc=desc,
                                     var=var, field_id=fid, validate_fn=validate_fn, unit=unit)

        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.grid(row=len(fields) + 1, column=0, pady=(10, 16), padx=20, sticky="w")

        ctk.CTkButton(
            btn_row, text="💾 Guardar Circuito", height=38, corner_radius=8,
            fg_color=self.colors["accent"], hover_color=self.colors["accent_hover"],
            text_color="#FFFFFF", font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            command=self._save_circuit,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_row, text="✕ Cancelar", height=38, corner_radius=8, width=100,
            fg_color=self.colors["bg_primary"], hover_color=self.colors["border"],
            border_width=1, border_color=self.colors["border"],
            text_color=self.colors["text_secondary"],
            font=ctk.CTkFont(family="Segoe UI", size=13),
            command=lambda: self._toggle_circuit_form(force_close=True),
        ).pack(side="left")

    # ─── Área de acciones ─────────────────────────────────────
    def _build_actions(self):
        """Botón de guardar sesión + status al final del scroll."""
        ctk.CTkFrame(self._scroll, height=1, fg_color=self.colors["border"]).grid(
            row=8, column=0, sticky="ew", padx=32, pady=(28, 0)
        )

        actions = ctk.CTkFrame(self._scroll, fg_color="transparent")
        actions.grid(row=9, column=0, pady=(16, 8), sticky="ew")
        actions.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            actions,
            text="✔  Guardar Sesión",
            command=self._save_session_data,
            width=280, height=52, corner_radius=10,
            fg_color=self.colors["accent"], hover_color=self.colors["accent_hover"],
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
        ).grid(row=0, column=0, pady=(0, 10))

        self._status_label = ctk.CTkLabel(
            actions, text="",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=self.colors["success"], wraplength=900,
        )
        self._status_label.grid(row=1, column=0, pady=(0, 32))

    # ═══════════════════════════════════════════════════════════
    #  HELPERS DE CONSTRUCCIÓN
    # ═══════════════════════════════════════════════════════════

    def _make_step_header(self, parent, row: int, number: str, title: str, subtitle: str):
        """Cabecera numerada estilo 'paso 01 / paso 02'."""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", padx=32, pady=(28, 4))
        frame.grid_columnconfigure(2, weight=1)

        # Número grande
        ctk.CTkFrame(
            frame,
            fg_color=self.colors["accent"],
            corner_radius=6,
            width=36, height=36,
        ).grid(row=0, column=0, rowspan=2)

        ctk.CTkLabel(
            frame, text=number,
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color="#FFFFFF",
            width=36,
        ).grid(row=0, column=0, rowspan=2)

        ctk.CTkLabel(
            frame, text=title,
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color=self.colors["text_primary"],
        ).grid(row=0, column=1, sticky="sw", padx=(12, 12))

        ctk.CTkLabel(
            frame, text=subtitle,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=self.colors["text_secondary"],
        ).grid(row=1, column=1, sticky="nw", padx=(12, 12))

        ctk.CTkFrame(frame, height=1, fg_color=self.colors["border"]).grid(
            row=0, column=2, rowspan=2, sticky="ew", pady=(4, 0)
        )
        return frame

    def _build_inline_field(self, parent, row: int, label: str, desc: str,
                             var: ctk.StringVar, field_id: str,
                             validate_fn=None, unit: str = ""):
        """Campo compacto para usar dentro de los formularios inline."""
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.grid(row=row, column=0, sticky="ew", padx=20, pady=4)
        f.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            f, text=label, width=220, anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=self.colors["text_primary"],
        ).grid(row=0, column=0, sticky="w", padx=(0, 16))

        input_col = ctk.CTkFrame(f, fg_color="transparent")
        input_col.grid(row=0, column=1, sticky="w")

        entry = ctk.CTkEntry(
            input_col, textvariable=var,
            width=240, height=36, corner_radius=8,
            fg_color=self.colors["input_bg"],
            border_color=self.colors["border"], border_width=1,
            text_color=self.colors["text_primary"],
            placeholder_text_color=self.colors["text_secondary"],
            font=ctk.CTkFont(family="Segoe UI Mono", size=13),
        )
        entry.pack(side="left")

        if unit:
            ctk.CTkLabel(
                input_col, text=unit,
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color=self.colors["text_secondary"],
            ).pack(side="left", padx=(8, 0))

        # Descripción + error en columna 2
        info_col = ctk.CTkFrame(f, fg_color="transparent")
        info_col.grid(row=0, column=2, sticky="w", padx=(12, 0))

        ctk.CTkLabel(
            info_col, text=desc,
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=self.colors["text_secondary"],
        ).pack(anchor="w")

        err = ctk.CTkLabel(
            info_col, text="",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color="#FF6B6B",
        )
        err.pack(anchor="w")
        self._error_labels[field_id] = err

        if validate_fn:
            entry.bind(
                "<FocusOut>",
                lambda e, fid=field_id, v=var, fn=validate_fn: (
                    self._error_labels[fid].configure(
                        text=fn(v.get().strip()) or ""
                    )
                ),
            )

    def _build_summary_cards(self, parent, data: dict):
        """Mini-cards de resumen con los datos activos (solo lectura)."""
        for w in parent.winfo_children():
            w.destroy()

        for i, (k, v) in enumerate(data.items()):
            card = ctk.CTkFrame(
                parent,
                fg_color=self.colors["bg_primary"],
                corner_radius=6,
                border_width=1,
                border_color=self.colors["border"],
            )
            card.grid(row=0, column=i, padx=(0, 6), pady=0, sticky="ew")
            parent.grid_columnconfigure(i, weight=1)

            ctk.CTkLabel(
                card, text=k,
                font=ctk.CTkFont(family="Segoe UI", size=9),
                text_color=self.colors["text_secondary"],
            ).grid(row=0, column=0, padx=10, pady=(7, 1), sticky="w")

            ctk.CTkLabel(
                card, text=str(v),
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color=self.colors["accent"],
            ).grid(row=1, column=0, padx=10, pady=(0, 7), sticky="w")

    # ═══════════════════════════════════════════════════════════
    #  LÓGICA DE CAMPEONATO
    # ═══════════════════════════════════════════════════════════

    def _list_championships(self) -> list[str]:
        if not PROFILES_ROOT.exists():
            return []
        return sorted(
            d.name for d in PROFILES_ROOT.iterdir()
            if d.is_dir() and (d / CHAMPIONSHIP_FILE).exists()
        ) or []

    def _list_circuits(self, championship: str) -> list[str]:
        champ_dir = PROFILES_ROOT / championship
        if not champ_dir.exists():
            return []
        return sorted(
            p.stem for p in champ_dir.glob("*.json")
            if p.name != CHAMPIONSHIP_FILE
        )

    def _on_championship_selected(self, name: str):
        """Callback al seleccionar un campeonato en el ComboBox."""
        if not name or name.startswith("—"):
            return
        self._active_championship = name
        self._load_championship_data(name)

    def _load_championship_data(self, name: str):
        """Lee el JSON del campeonato y actualiza los StringVars + summary."""
        path = PROFILES_ROOT / name / CHAMPIONSHIP_FILE
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return

        self._var_champ_name.set(data.get("name", name))
        self._var_car.set(data.get("car", "Dallara IR-18"))
        self._var_fuel_capacity.set(str(data.get("fuel_capacity_l", 70)))
        self._var_refuel_rate.set(str(data.get("refuel_rate_ls", 12.0)))
        self._var_tyre_change.set(str(data.get("tyre_change_s", 4.0)))
        self._var_car_lift.set(str(data.get("car_lift_s", 2.0)))
        self._var_race_duration.set(str(data.get("race_duration_min", 60)))
        compounds = data.get("tyre_compounds", ["Prime (Duro)", "Alternative (Blando)"])
        self._var_compound_1.set(compounds[0] if len(compounds) > 0 else "")
        self._var_compound_2.set(compounds[1] if len(compounds) > 1 else "")

        # Actualizar resumen
        self._build_summary_cards(self._champ_summary_frame, {
            "🚗 Coche":       data.get("car", "—"),
            "⛽ Depósito":   f"{data.get('fuel_capacity_l', '—')} L",
            "🔧 Repostaje":  f"{data.get('refuel_rate_ls', '—')} L/s",
            "🔄 Ruedas":     f"{data.get('tyre_change_s', '—')} s",
            "⏱️ Levantar":   f"{data.get('car_lift_s', 2.0)} s",
            "⏳ Duración":   f"{data.get('race_duration_min', '—')} min",
            "🏆 Compuestos":  f"{compounds[0]} / {compounds[1] if len(compounds) > 1 else '—'}",
        })

        # Mostrar botones editar, borrar y activar paso 2
        self._btn_edit_champ.grid()
        self._btn_delete_champ.grid()
        self._activate_circuit_step(name)
        self._toggle_champ_form(force_close=True)

        self._status_label.configure(
            text=f"📂  Campeonato «{name}» cargado.",
            text_color=self.colors["success"],
        )

    def _new_championship(self):
        """Limpia los campos del campeonato y abre el formulario."""
        self._var_champ_name.set("")
        self._var_car.set("Dallara IR-18")
        self._var_fuel_capacity.set("70")
        self._var_refuel_rate.set("12.0")
        self._var_tyre_change.set("4.0")
        self._var_car_lift.set("2.0")
        self._var_race_duration.set("60")
        self._var_compound_1.set("Prime (Duro)")
        self._var_compound_2.set("Alternative (Blando)")
        self._toggle_champ_form(force_open=True)

    def _toggle_champ_form(self, force_open=False, force_close=False, _event=None):
        if force_close or (self._champ_form_visible and not force_open):
            self._champ_form_frame.grid_remove()
            self._champ_form_visible = False
        else:
            self._champ_form_frame.grid(
                row=self._champ_form_row, column=0, sticky="ew", padx=32, pady=(4, 0)
            )
            self._champ_form_visible = True

    def _save_championship(self):
        """Valida y guarda el JSON del campeonato."""
        name = self._var_champ_name.get().strip()
        if not name:
            self._error_labels["champ_name"].configure(text="⚠  Nombre obligatorio.")
            return
        self._error_labels["champ_name"].configure(text="")

        errs = {}
        for fid, var, fn in [
            ("fuel_capacity", self._var_fuel_capacity, self._validate_positive_float),
            ("refuel_rate",   self._var_refuel_rate,   self._validate_positive_float),
            ("tyre_change",   self._var_tyre_change,   self._validate_positive_float),
            ("car_lift",      self._var_car_lift,      self._validate_positive_float),
            ("race_duration", self._var_race_duration,  self._validate_positive_float),
        ]:
            e = fn(var.get().strip())
            self._error_labels[fid].configure(text=e or "")
            if e:
                errs[fid] = e
        if errs:
            return

        safe = re.sub(r'[\\/*?:"<>|]', "_", name)
        champ_dir = PROFILES_ROOT / safe
        champ_dir.mkdir(parents=True, exist_ok=True)

        data = {
            "name": name,
            "car": self._var_car.get().strip(),
            "fuel_capacity_l": float(self._var_fuel_capacity.get()),
            "refuel_rate_ls": float(self._var_refuel_rate.get()),
            "tyre_change_s": float(self._var_tyre_change.get()),
            "car_lift_s": float(self._var_car_lift.get()),
            "race_duration_min": float(self._var_race_duration.get()),
            "tyre_compounds": [
                self._var_compound_1.get().strip(),
                self._var_compound_2.get().strip(),
            ],
            "mandatory_compound_change": True,
        }
        (champ_dir / CHAMPIONSHIP_FILE).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # Refrescar selector y seleccionar el nuevo campeonato
        championships = self._list_championships()
        self._champ_combo.configure(values=championships)
        self._champ_combo_var.set(safe)
        self._active_championship = safe
        self._load_championship_data(safe)

        self._status_label.configure(
            text=f"💾  Campeonato «{name}» guardado correctamente.",
            text_color=self.colors["success"],
        )

    # ═══════════════════════════════════════════════════════════
    #  LÓGICA DE CIRCUITO
    # ═══════════════════════════════════════════════════════════

    def _activate_circuit_step(self, championship: str):
        """Habilita el selector de circuito para el campeonato dado."""
        circuits = self._list_circuits(championship)
        display = circuits if circuits else ["— Sin circuitos guardados —"]

        self._circuit_combo.configure(values=display, state="readonly",
                                      text_color=self.colors["text_primary"],
                                      button_color=self.colors["accent"])
        self._circuit_combo_var.set(display[0])
        self._btn_new_circuit.configure(state="normal",
                                        fg_color=self.colors["accent"],
                                        text_color="#FFFFFF")

        if circuits:
            self._btn_edit_circuit.configure(state="normal")
            self._btn_delete_circuit.configure(state="normal")
            self._on_circuit_selected(circuits[0])
        else:
            self._btn_edit_circuit.configure(state="disabled")
            self._btn_delete_circuit.configure(state="disabled")
            for w in self._circuit_summary_frame.winfo_children():
                w.destroy()

    def _on_circuit_selected(self, name: str):
        if not name or name.startswith("—"):
            return
        path = PROFILES_ROOT / self._active_championship / f"{name}.json"
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return

        self._var_circuit.set(data.get("circuit", name))
        self._var_lap_time.set(data.get("lap_time", "01:30.000"))
        self._var_pitlane_loss.set(str(data.get("pitlane_loss_s", "22.5")))
        trk_len = float(data.get("track_length_km", 5.47))
        sc_spd = float(data.get("sc_speed_kmh", 72.0))
        self._var_track_length.set(str(trk_len))
        self._var_sc_speed.set(str(sc_spd))

        sc_pace_s = (trk_len / sc_spd) * 3600.0 if sc_spd > 0 else 0.0
        sc_pace_str = self._format_seconds_to_lap(sc_pace_s)

        self._build_summary_cards(self._circuit_summary_frame, {
            "🏁 Circuito":    data.get("circuit", name),
            "⏱️ Vuelta":      data.get("lap_time", "—"),
            "🛣️ Pitlane":     f"{data.get('pitlane_loss_s', '—')} s",
            "📏 Longitud":    f"{trk_len:.3f} km",
            "🚨 Ritmo SC":    f"{sc_pace_str} ({sc_spd:.0f} km/h)",
        })

        self._btn_edit_circuit.configure(state="normal")
        self._btn_delete_circuit.configure(state="normal")
        self._toggle_circuit_form(force_close=True)

    def _new_circuit(self):
        self._var_circuit.set("")
        self._var_lap_time.set("01:30.000")
        self._var_pitlane_loss.set("22.5")
        self._var_track_length.set("5.47")
        self._var_sc_speed.set("72.0")
        self._toggle_circuit_form(force_open=True)

    def _toggle_circuit_form(self, force_open=False, force_close=False, _event=None):
        if force_close or (self._circuit_form_visible and not force_open):
            self._circuit_form_frame.grid_remove()
            self._circuit_form_visible = False
        else:
            self._circuit_form_frame.grid(
                row=self._circuit_form_row, column=0, sticky="ew", padx=32, pady=(4, 0)
            )
            self._circuit_form_visible = True

    def _save_circuit(self):
        """Valida y guarda el JSON del circuito dentro del campeonato activo."""
        if not self._active_championship:
            messagebox.showwarning("Sin campeonato", "Selecciona o crea un campeonato primero.")
            return

        errs = {}
        circuit_name = self._var_circuit.get().strip()
        if not circuit_name:
            self._error_labels["circuit"].configure(text="⚠  Nombre obligatorio.")
            errs["circuit"] = True
        else:
            self._error_labels["circuit"].configure(text="")

        for fid, var, fn in [
            ("lap_time",     self._var_lap_time,     self._validate_lap_time),
            ("pitlane_loss", self._var_pitlane_loss,  self._validate_positive_float),
            ("track_length", self._var_track_length,  self._validate_positive_float),
            ("sc_speed",     self._var_sc_speed,      self._validate_positive_float),
        ]:
            e = fn(var.get().strip())
            self._error_labels[fid].configure(text=e or "")
            if e:
                errs[fid] = e
        if errs:
            return

        safe = re.sub(r'[\\/*?:"<>|]', "_", circuit_name)
        champ_dir = PROFILES_ROOT / self._active_championship
        champ_dir.mkdir(parents=True, exist_ok=True)

        trk_len = float(self._var_track_length.get().replace(",", "."))
        sc_spd = float(self._var_sc_speed.get().replace(",", "."))
        sc_pace_s = (trk_len / sc_spd) * 3600.0 if sc_spd > 0 else 0.0
        sc_pace_str = self._format_seconds_to_lap(sc_pace_s)

        data = {
            "circuit":         circuit_name,
            "lap_time":        self._var_lap_time.get().strip(),
            "pitlane_loss_s":  float(self._var_pitlane_loss.get()),
            "track_length_km": trk_len,
            "sc_speed_kmh":    sc_spd,
            "sc_pace_s":       sc_pace_s,
            "sc_pace_str":     sc_pace_str,
        }
        (champ_dir / f"{safe}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        circuits = self._list_circuits(self._active_championship)
        self._circuit_combo.configure(values=circuits)
        self._circuit_combo_var.set(safe)
        self._on_circuit_selected(safe)

        self._status_label.configure(
            text=f"💾  Circuito «{circuit_name}» guardado en campeonato «{self._active_championship}».",
            text_color=self.colors["success"],
        )

    # ═══════════════════════════════════════════════════════════
    #  GUARDAR SESIÓN (fusión de los dos niveles)
    # ═══════════════════════════════════════════════════════════

    def _save_session_data(self):
        """Consolida campeonato + circuito en session_data."""
        if not self._active_championship:
            self._status_label.configure(
                text="⚠  Selecciona un campeonato antes de guardar la sesión.",
                text_color="#FF6B6B",
            )
            return

        circuit = self._var_circuit.get().strip()
        lap_raw = self._var_lap_time.get().strip()

        if not circuit:
            self._status_label.configure(
                text="⚠  Selecciona o crea un circuito antes de guardar la sesión.",
                text_color="#FF6B6B",
            )
            return

        lap_err = self._validate_lap_time(lap_raw)
        if lap_err:
            self._status_label.configure(text=f"❌  {lap_err}", text_color="#FF6B6B")
            return

        # Leer campeonato
        champ_path = PROFILES_ROOT / self._active_championship / CHAMPIONSHIP_FILE
        try:
            champ = json.loads(champ_path.read_text(encoding="utf-8"))
        except Exception:
            champ = {}

        compounds = champ.get("tyre_compounds", ["Prime", "Alternative"])

        trk_len = float(self._var_track_length.get().replace(",", ".")) if self._var_track_length.get().strip() else 5.47
        sc_spd = float(self._var_sc_speed.get().replace(",", ".")) if self._var_sc_speed.get().strip() else 72.0
        sc_pace_s = (trk_len / sc_spd) * 3600.0 if sc_spd > 0 else 0.0
        sc_pace_str = self._format_seconds_to_lap(sc_pace_s)

        self.session_data = {
            # ── Constantes del campeonato ──────────────────
            "championship_name":        champ.get("name", self._active_championship),
            "car":                      champ.get("car", "Dallara IR-18"),
            "fuel_capacity_l":          float(champ.get("fuel_capacity_l", 70)),
            "refuel_rate_ls":           float(champ.get("refuel_rate_ls", 12.0)),
            "tyre_change_time":         float(champ.get("tyre_change_s", 4.0)),
            "tyre_change_s":            float(champ.get("tyre_change_s", 4.0)),
            "car_lift_s":               float(champ.get("car_lift_s", 2.0)),
            "car_lift_time":            float(champ.get("car_lift_s", 2.0)),
            "race_duration_s":          float(champ.get("race_duration_min", 60)) * 60,
            "race_duration_min":        float(champ.get("race_duration_min", 60)),
            "race_duration_minutes":    float(champ.get("race_duration_min", 60)),
            "tyre_compounds":           compounds,
            "mandatory_compound_change":champ.get("mandatory_compound_change", True),
            # ── Variables del circuito ─────────────────────
            "circuit":                  circuit,
            "lap_time_str":             lap_raw,
            "lap_time_seconds":         self._lap_time_to_seconds(lap_raw),
            "pitlane_loss":             float(self._var_pitlane_loss.get()),
            "pitlane_loss_s":           float(self._var_pitlane_loss.get()),
            "track_length_km":          trk_len,
            "sc_speed_kmh":             sc_spd,
            "sc_pace_s":                sc_pace_s,
            "sc_pace_str":              sc_pace_str,
        }

        sd = self.session_data
        self._status_label.configure(
            text=(
                f"✔  Sesión lista — {sd['championship_name']} | {sd['circuit']}  ·  "
                f"Vuelta: {sd['lap_time_str']}  ·  "
                f"Pitlane: {sd['pitlane_loss']} s  ·  "
                f"Ruedas: {sd['tyre_change_time']} s  ·  "
                f"Levantar: {sd.get('car_lift_s', 2.0)} s  ·  "
                f"SC: {sd['sc_pace_str']}"
            ),
            text_color=self.colors["success"],
        )

    # ═══════════════════════════════════════════════════════════
    #  VALIDACIÓN
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _validate_lap_time(value: str) -> str:
        if not value:
            return "⚠  Obligatorio."
        if not re.match(r"^\d{2}:\d{2}\.\d{1,3}$", value):
            return "⚠  Usa MM:SS.mmm"
        if float(value[3:]) >= 60:
            return "⚠  Segundos < 60"
        if int(value[:2]) == 0 and float(value[3:]) == 0:
            return "⚠  No puede ser 0"
        return ""

    @staticmethod
    def _validate_positive_float(value: str) -> str:
        if not value:
            return "⚠  Obligatorio."
        try:
            if float(value.replace(",", ".")) <= 0:
                return "⚠  Debe ser > 0"
        except ValueError:
            return "⚠  Número inválido"
        return ""

    # ═══════════════════════════════════════════════════════════
    #  UTILIDADES
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _lap_time_to_seconds(s: str) -> float:
        return int(s[:2]) * 60 + float(s[3:])

    @staticmethod
    def _format_seconds_to_lap(seconds: float) -> str:
        if seconds <= 0:
            return "--:--.---"
        mins = int(seconds // 60)
        secs = seconds % 60
        return f"{mins:02d}:{secs:06.3f}"

    def get_session_data(self) -> dict:
        """API pública para los módulos 2, 3 y 4."""
        return self.session_data

    def load_session_by_names(self, champ_name: str, circuit_name: str | None = None) -> bool:
        """Carga programáticamente un campeonato y opcionalmente un circuito por su nombre."""
        champs = self._list_championships()
        if champ_name not in champs:
            return False
        self._champ_combo_var.set(champ_name)
        self._on_championship_selected(champ_name)
        if circuit_name:
            circuits = self._list_circuits(champ_name)
            if circuit_name in circuits:
                self._circuit_combo_var.set(circuit_name)
                self._on_circuit_selected(circuit_name)
                self._save_session_data()
                return True
        return False

    def _delete_championship(self):
        """Elimina el campeonato activo y todos sus circuitos tras confirmación."""
        if not self._active_championship:
            return
        champ_name = self._active_championship
        confirm = messagebox.askyesno(
            "Borrar Campeonato",
            f"¿Estás seguro de que deseas eliminar permanentemente el campeonato «{champ_name}» y TODOS sus circuitos y configuraciones?",
            icon="warning",
        )
        if not confirm:
            return

        champ_dir = PROFILES_ROOT / champ_name
        try:
            if champ_dir.exists():
                shutil.rmtree(champ_dir)
            self._active_championship = None
            self._champ_combo_var.set("— Selecciona o crea un campeonato —")
            self._champ_combo.configure(values=self._list_championships())
            self._btn_edit_champ.grid_remove()
            self._btn_delete_champ.grid_remove()
            for w in self._champ_summary_frame.winfo_children():
                w.destroy()
            self._circuit_combo_var.set("— Primero selecciona un campeonato —")
            self._circuit_combo.configure(values=[], state="disabled")
            self._btn_edit_circuit.configure(state="disabled")
            self._btn_delete_circuit.configure(state="disabled")
            self._btn_new_circuit.configure(state="disabled")
            for w in self._circuit_summary_frame.winfo_children():
                w.destroy()
            self._toggle_champ_form(force_close=True)
            self._toggle_circuit_form(force_close=True)
            self.session_data = {}
            self._status_label.configure(
                text=f"🗑️  Campeonato «{champ_name}» eliminado correctamente.",
                text_color="#FF6B6B",
            )
        except Exception as e:
            messagebox.showerror("Error al borrar", str(e))

    def _delete_circuit(self):
        """Elimina el circuito activo y sus perfiles de combustible y neumáticos tras confirmación."""
        if not self._active_championship:
            return
        circuit_name = self._var_circuit.get().strip()
        if not circuit_name:
            return
        confirm = messagebox.askyesno(
            "Borrar Circuito",
            f"¿Estás seguro de que deseas eliminar permanentemente el circuito «{circuit_name}» y sus configuraciones asociadas de combustible y neumáticos?",
            icon="warning",
        )
        if not confirm:
            return

        safe = re.sub(r'[\\/*?:"<>|]', "_", circuit_name)
        champ_dir = PROFILES_ROOT / self._active_championship
        try:
            for ext in [
                f"{safe}.json",
                f"{safe}_fuel.json",
                f"{safe}_tyres.json",
                f"{safe}_fuel_models.json",
                f"{safe}_tyre_models.json",
                f"{safe}_strategies.json",
            ]:
                f = champ_dir / ext
                if f.exists():
                    f.unlink()

            self._toggle_circuit_form(force_close=True)
            self._activate_circuit_step(self._active_championship)
            self._status_label.configure(
                text=f"🗑️  Circuito «{circuit_name}» eliminado correctamente.",
                text_color="#FF6B6B",
            )
        except Exception as e:
            messagebox.showerror("Error al borrar circuito", str(e))
