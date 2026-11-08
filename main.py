"""
============================================================
 CALCULADORA GOD LEAGUE - iRacing Strategy Tool
 Ingeniería de Pista: Team NIX Esports
 Vehículo: Dallara IR-18 | Combustible: 70L max
============================================================
 Arquitectura OOP | CustomTkinter UI | Matplotlib Charts
 Módulos:
   1. Datos del Campeonato
   2. Estrategia de Combustible
   3. Estrategia de Neumáticos
   4. Gráficos de Estrategia
   5. Control en Vivo
============================================================
"""

import warnings
import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageTk
import os
import sys
import json
from pathlib import Path

# Suprimir advertencias globales de fuentes para caracteres especiales/emojis en matplotlib
warnings.filterwarnings("ignore", message=r".*missing from font.*")

from modules.championship_data import ChampionshipDataModule
from modules.fuel_strategy import FuelStrategyModule
from modules.tyre_strategy import TyreStrategyModule
from modules.strategy_charts import StrategyChartsModule
from modules.live_control import LiveControlModule

APP_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
PROFILES_ROOT = APP_ROOT / "profiles"
STATE_FILE = PROFILES_ROOT / "_last_state.json"


# ─────────────────────────────────────────────
#  Configuración global de apariencia y DPI
# ─────────────────────────────────────────────
import ctypes
try:
    # 1. Configurar Windows como System DPI Aware:
    #    - Garantiza renderizado nítido nativo de fuentes y elementos gráficos en la pantalla principal.
    #    - Windows DWM gestiona el escalado por GPU al mover la ventana a monitores con diferente DPI (0ms lag).
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

# 2. Desactivar el bucle de escalado dinámico de CustomTkinter que ponía la ventana
#    al 15% de opacidad (-alpha 0.15) y congelaba la interfaz al arrastrar entre monitores.
ctk.deactivate_automatic_dpi_awareness()

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

# ── Paleta corporativa NIX Esports ────────────────────────
COLORS = {
    "bg_primary":    "#0A0A0A",   # Negro profundo (fondo principal)
    "bg_secondary":  "#131313",   # Gris carbón (cards / header)
    "sidebar_bg":    "#0D0D0D",   # Sidebar ligeramente más claro
    "accent":        "#F26419",   # Naranja NIX (principal)
    "accent_hover":  "#FF7A2F",   # Naranja más brillante (hover)
    "accent_dim":    "#3D2008",   # Naranja muy oscuro (selección activa sidebar)
    "accent_glow":   "#FF6B1A",   # Naranja neón (detalles, borde logo)
    "text_primary":  "#FFFFFF",
    "text_secondary":"#9A9A9A",
    "border":        "#222222",
    "input_bg":      "#1A1A1A",
    "success":       "#4CAF50",
    "warning":       "#F26419",
    "danger":        "#FF453A",
}

# IDs de los módulos para la navegación
MODULE_IDS = [
    ("championship",  "🏁  Datos del Campeonato"),
    ("fuel",          "⛽  Estrategia Combustible"),
    ("tyres",         "🔄  Estrategia Neumáticos"),
    ("charts",        "📊  Gráficos de Estrategia"),
    ("live",          "📡  Control en Vivo"),
]

# Ruta al logo e icono de NIX (compatible con ejecución normal y ejecutable compilado)
_RESOURCE_ROOT = APP_ROOT if (APP_ROOT / "images").exists() else Path(getattr(sys, "_MEIPASS", APP_ROOT))
LOGO_PATH = str(_RESOURCE_ROOT / "images" / "Logo_nix_transparent.png")
ICON_PATH = str(_RESOURCE_ROOT / "images" / "icon.ico")


class CalculadoraApp(ctk.CTk):
    """
    Clase principal de la aplicación.
    Gestiona la ventana raíz, la barra de navegación lateral
    y el contenedor central donde se cargan los módulos.
    """

    def __init__(self):
        super().__init__()
        self._active_module = "championship"
        # Aplicar el zoom guardado ANTES de crear los widgets: así cada widget nace ya
        # con su escala final y se evita re-renderizar toda la interfaz al arrancar.
        self._initial_zoom = self._read_initial_zoom()
        self._apply_zoom(self._initial_zoom, save=False)
        self._configure_window()
        self._build_layout()
        self._register_modules()
        self._restore_last_state()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    # ─── Configuración de la ventana principal ───────────────
    def _configure_window(self):
        self.title("Calculadora God League — NIX Esports Strategy Tool")
        try:
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            if sh <= 820 or sw <= 1366:
                # Pantallas pequeñas o laptops con DPI alto
                win_w = min(1200, max(960, sw - 60))
                win_h = min(720, max(560, sh - 70))
                self.geometry(f"{win_w}x{win_h}")
            else:
                self.geometry("1280x780")
        except Exception:
            self.geometry("1280x780")

        self.minsize(960, 560)
        self.configure(fg_color=COLORS["bg_primary"])
        try:
            if os.path.exists(ICON_PATH):
                self.iconbitmap(ICON_PATH)
            else:
                self.iconbitmap("assets/icon.ico")
        except Exception:
            pass

    # ─── Construcción del layout principal ───────────────────
    def _build_layout(self):
        """
        Layout de dos columnas:
          - Columna 0: Barra lateral (fija, 240px)
          - Columna 1: Área de contenido (expansible)
        """
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_content_area()

    def _build_sidebar(self):
        """Barra de navegación lateral con branding NIX."""
        self.sidebar = ctk.CTkFrame(
            self,
            width=240,
            corner_radius=0,
            fg_color=COLORS["sidebar_bg"],
            border_width=1,
            border_color=COLORS["border"],
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_rowconfigure(10, weight=1)

        # ── Logo NIX en la sidebar ───────────────────────────
        try:
            logo_img = Image.open(LOGO_PATH).convert("RGBA")
            logo_img = logo_img.resize((80, 80), Image.LANCZOS)
            self._sidebar_logo = ctk.CTkImage(light_image=logo_img, dark_image=logo_img, size=(80, 80))
            self._sidebar_logo_lbl = ctk.CTkLabel(
                self.sidebar,
                image=self._sidebar_logo,
                text="",
            )
            self._sidebar_logo_lbl.grid(row=0, column=0, pady=(20, 4))
        except Exception:
            self._sidebar_logo_lbl = None

        # Nombre del equipo
        ctk.CTkLabel(
            self.sidebar,
            text="NIX ESPORTS",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=COLORS["accent"],
        ).grid(row=1, column=0)

        ctk.CTkLabel(
            self.sidebar,
            text="Strategy Tool",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLORS["text_secondary"],
        ).grid(row=2, column=0, pady=(0, 4))

        # Separador
        ctk.CTkFrame(
            self.sidebar, height=1, fg_color=COLORS["border"]
        ).grid(row=3, column=0, sticky="ew", padx=12, pady=(8, 12))

        # Etiqueta de sección
        ctk.CTkLabel(
            self.sidebar,
            text="  MÓDULOS",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=COLORS["text_secondary"],
        ).grid(row=4, column=0, sticky="w", padx=16, pady=(0, 4))

        # ── Botones de navegación ────────────────────────────
        self._nav_buttons = {}
        for i, (module_id, label) in enumerate(MODULE_IDS):
            btn = ctk.CTkButton(
                self.sidebar,
                text=label,
                anchor="w",
                height=44,
                corner_radius=8,
                border_spacing=12,
                fg_color="transparent",
                hover_color=COLORS["accent_dim"],
                text_color=COLORS["text_secondary"],
                font=ctk.CTkFont(family="Segoe UI", size=13),
                command=lambda mid=module_id: self.navigate_to(mid),
            )
            btn.grid(row=i + 5, column=0, padx=10, pady=2, sticky="ew")

            # Garantizar captura de clic inmediata e inmune a pérdidas de foco o micro-movimientos
            btn.bind("<Button-1>", lambda e, mid=module_id: self.navigate_to(mid), add="+")
            if hasattr(btn, "_text_label") and btn._text_label:
                btn._text_label.bind("<Button-1>", lambda e, mid=module_id: self.navigate_to(mid), add="+")
            if hasattr(btn, "_canvas") and btn._canvas:
                btn._canvas.bind("<Button-1>", lambda e, mid=module_id: self.navigate_to(mid), add="+")

            self._nav_buttons[module_id] = btn

        # ── Footer de la sidebar ─────────────────────────────
        footer = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        footer.grid(row=11, column=0, padx=16, pady=16, sticky="sew")

        # Control de Escala / Zoom de Interfaz
        zoom_frame = ctk.CTkFrame(footer, fg_color="transparent")
        zoom_frame.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            zoom_frame,
            text="ZOOM INTERFAZ",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            text_color=COLORS["text_secondary"],
        ).pack(anchor="w", pady=(0, 3))

        self._seg_zoom = ctk.CTkSegmentedButton(
            zoom_frame,
            values=["85%", "100%", "115%"],
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            height=26,
            selected_color=COLORS["accent"],
            selected_hover_color=COLORS["accent_hover"],
            unselected_color=COLORS["bg_primary"],
            unselected_hover_color=COLORS["border"],
            command=self._on_zoom_changed,
        )
        self._seg_zoom.set("100%")
        self._seg_zoom.pack(fill="x")

        self._sidebar_car_lbl = ctk.CTkLabel(
            footer,
            text="Multi-Car | Team NIX",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=COLORS["text_secondary"],
        )
        self._sidebar_car_lbl.pack(anchor="w")

        ctk.CTkLabel(
            footer,
            text="v1.0 — Fase 1",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=COLORS["border"],
        ).pack(anchor="w")

        # Ventanas bajas (p. ej. 960x560 con zoom 115%): ocultar el logo para que el
        # selector de ZOOM del pie no quede fuera de la ventana.
        self._sidebar_compact = None
        tk.Misc.bind(self.sidebar, "<Configure>", self._on_sidebar_configure, "+")
        # Al cambiar el zoom cambia el alto del pie (no el de la sidebar): re-evaluar también
        tk.Misc.bind(footer, "<Configure>", lambda e: self._on_sidebar_configure(), "+")

    def _on_sidebar_configure(self, event=None):
        logo = getattr(self, "_sidebar_logo_lbl", None)
        if logo is None or (event is not None and event.widget is not self.sidebar):
            return
        height = self.sidebar.winfo_height()
        if height <= 1:
            return

        def _pad(v):
            if isinstance(v, (tuple, list)):
                return sum(int(x) for x in v)
            try:
                return 2 * int(v)
            except (TypeError, ValueError):
                return sum(int(x) for x in str(v).split())

        needed = 0
        for w in self.sidebar.grid_slaves():
            if w is logo:
                continue
            needed += w.winfo_reqheight() + _pad(w.grid_info().get("pady", 0))
        scale = ctk.ScalingTracker.get_widget_scaling(self.sidebar)
        logo_h = logo.winfo_reqheight() + int(24 * scale)
        compact = height < needed + logo_h
        if compact != self._sidebar_compact:
            self._sidebar_compact = compact
            if compact:
                logo.grid_remove()
            else:
                logo.grid()

    def _build_content_area(self):
        """
        Contenedor principal de alto rendimiento donde se cargan dinámicamente
        los módulos de la aplicación.
        """
        self.content_area = ctk.CTkFrame(
            self,
            corner_radius=0,
            fg_color=COLORS["bg_primary"],
        )
        self.content_area.grid(row=0, column=1, sticky="nsew")
        self.content_area.grid_columnconfigure(0, weight=1)
        self.content_area.grid_rowconfigure(0, weight=1)

    # ─── Registro de módulos ──────────────────────────────────
    def _register_modules(self):
        """
        Instancia todos los módulos. Solo se mapea en el grid el módulo activo
        a través de navigate_to() para optimizar el rendimiento y evitar
        conflictos de composición y transparencia en Windows DWM.
        """
        self._modules: dict[str, ctk.CTkFrame] = {
            "championship": ChampionshipDataModule(self.content_area, colors=COLORS),
            "fuel":         FuelStrategyModule(self.content_area, colors=COLORS),
            "tyres":        TyreStrategyModule(self.content_area, colors=COLORS),
            "charts":       StrategyChartsModule(self.content_area, colors=COLORS),
            "live":         LiveControlModule(self.content_area, colors=COLORS),
        }

    # ─── Persistencia de Estado de Sesión y Zoom ────────────
    _ZOOM_FACTORS = {"85%": 0.85, "100%": 1.0, "115%": 1.15}

    def _read_initial_zoom(self) -> str:
        """Zoom guardado en _last_state.json o, si no existe, detectado según la pantalla."""
        try:
            if STATE_FILE.exists():
                saved = json.loads(STATE_FILE.read_text(encoding="utf-8")).get("ui_zoom")
                if saved in self._ZOOM_FACTORS:
                    return saved
        except Exception:
            pass
        # Sin zoom guardado: en monitores grandes (>= 820 alto y > 1366 ancho) -> 100%,
        # en pantallas pequeñas o portátiles reducidos -> 85%
        try:
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            return "85%" if (sh < 820 or sw <= 1366) else "100%"
        except Exception:
            return "100%"

    def _apply_zoom(self, zoom_val: str, save: bool = True):
        """Aplica la escala global de CustomTkinter de forma reactiva."""
        factor = self._ZOOM_FACTORS.get(zoom_val, 1.0)
        self._current_zoom_factor = factor
        try:
            ctk.set_widget_scaling(factor)
        except Exception as e:
            print(f"[_apply_zoom] Aviso al aplicar scaling: {e}")
        # Los gráficos matplotlib no forman parte de CustomTkinter: avisar a los módulos
        for mod in getattr(self, "_modules", {}).values():
            if hasattr(mod, "on_ui_zoom_changed"):
                try:
                    mod.on_ui_zoom_changed()
                except Exception as e:
                    print(f"[_apply_zoom] Aviso al re-escalar gráficos: {e}")
        if hasattr(self, "sidebar"):
            self.after_idle(self._on_sidebar_configure)
        if save:
            self.save_app_state()

    def _on_zoom_changed(self, zoom_val: str):
        # Re-escalar toda la interfaz es costoso: no hacerlo si el zoom no cambia
        if self._ZOOM_FACTORS.get(zoom_val, 1.0) == getattr(self, "_current_zoom_factor", None):
            return
        self._apply_zoom(zoom_val, save=True)

    def save_app_state(self):
        """Guarda en _last_state.json la configuración activa, módulo visible y nivel de zoom."""
        try:
            champ_mod = self._modules.get("championship")
            sdata = champ_mod.get_session_data() if champ_mod else {}
            zoom_val = self._seg_zoom.get() if hasattr(self, "_seg_zoom") else "100%"
            state = {
                "last_module": getattr(self, "_active_module", "championship"),
                "championship": sdata.get("championship_name") or getattr(champ_mod, "_active_championship", None),
                "circuit": sdata.get("circuit") or (champ_mod._var_circuit.get() if champ_mod else None),
                "ui_zoom": zoom_val,
            }
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[save_app_state] Error: {e}")

    def _restore_last_state(self):
        """Restaura el campeonato, circuito, pantalla activa y nivel de zoom de la última sesión."""
        target_module = "championship"
        if STATE_FILE.exists():
            try:
                state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                champ_name = state.get("championship")
                circuit_name = state.get("circuit")
                last_mod = state.get("last_module", "championship")

                champ_mod = self._modules.get("championship")
                if champ_mod and champ_name:
                    champ_mod.load_session_by_names(champ_name, circuit_name)

                if last_mod in [m[0] for m in MODULE_IDS]:
                    target_module = last_mod
            except Exception as e:
                print(f"[_restore_last_state] Error: {e}")

        # El zoom ya se aplicó en __init__ antes de construir los widgets
        # (ver _read_initial_zoom); aquí solo se refleja en el selector.
        saved_zoom = getattr(self, "_initial_zoom", "100%")
        if hasattr(self, "_seg_zoom"):
            self._seg_zoom.set(saved_zoom)

        self.navigate_to(target_module)

    def on_closing(self):
        """Callback al cerrar la ventana: guarda el estado y destruye la app."""
        self.save_app_state()
        live_mod = self._modules.get("live")
        if live_mod and hasattr(live_mod, "save_live_session"):
            live_mod.save_live_session()
        self.destroy()

    # ─── Navegación ───────────────────────────────────────────
    def navigate_to(self, module_id: str):
        """Muestra el módulo solicitado y actualiza el estado visual del sidebar de forma inmediata."""
        target_mod = self._modules.get(module_id)
        if not target_mod:
            return

        # Si ya estamos en este módulo y ya está activo en pantalla, evitar trabajo redundante
        if getattr(self, "_active_module", None) == module_id and target_mod.winfo_ismapped():
            return

        self._active_module = module_id

        # 1. Actualizar el estado visual del sidebar INMEDIATAMENTE
        for mid, btn in self._nav_buttons.items():
            if mid == module_id:
                btn.configure(
                    fg_color=COLORS["accent_dim"],
                    text_color=COLORS["accent"],
                    font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    text_color=COLORS["text_secondary"],
                    font=ctk.CTkFont(family="Segoe UI", size=13, weight="normal"),
                )

        # 2. Conmutar visibilidad del módulo destino INMEDIATAMENTE (prioridad visual y de acceso)
        for mid, mod in self._modules.items():
            if mid != module_id:
                mod.grid_remove()

        target_mod.grid(row=0, column=0, sticky="nsew")
        target_mod.tkraise()

        # Forzar despacho de eventos para que la transición sea instantánea sin latencia
        self.update_idletasks()

        # 3. Transmitir datos de sesión frescos y sincronizar módulos de forma segura
        try:
            champ_mod = self._modules.get("championship")
            fuel_mod = self._modules.get("fuel")
            tyre_mod = self._modules.get("tyres")
            sdata = champ_mod.get_session_data() if champ_mod else {}

            if hasattr(self, "_sidebar_car_lbl") and sdata and sdata.get("car"):
                car_name = sdata.get("car", "Vehículo")
                cap = sdata.get("fuel_capacity_l", 70.0)
                self._sidebar_car_lbl.configure(text=f"{car_name}  |  {cap:.0f}L")

            # Asegurar que fuel_mod, tyre_mod y charts_mod tengan datos actualizados
            if fuel_mod and sdata and target_mod != fuel_mod:
                fuel_mod.on_session_data_updated(sdata)
            if tyre_mod and sdata and target_mod != tyre_mod:
                tyre_mod.on_session_data_updated(sdata)
            charts_mod = self._modules.get("charts")
            if charts_mod and sdata and target_mod != charts_mod:
                charts_mod.on_session_data_updated(sdata)

            if hasattr(target_mod, "on_session_data_updated") and champ_mod:
                target_mod.on_session_data_updated(sdata)

            if hasattr(target_mod, "on_fuel_strategy_updated") and fuel_mod:
                target_mod.on_fuel_strategy_updated(fuel_mod.get_fuel_strategy_data())

            if hasattr(target_mod, "on_tyre_strategy_updated") and tyre_mod:
                target_mod.on_tyre_strategy_updated(tyre_mod.get_tyre_strategy_data())

            charts_mod = self._modules.get("charts")
            if hasattr(target_mod, "on_strategies_updated") and charts_mod:
                saved_strats = charts_mod._load_saved_strategies_dict() if hasattr(charts_mod, "_load_saved_strategies_dict") else {}
                opt_cfg = charts_mod.get_optimal_strategy_config() if hasattr(charts_mod, "get_optimal_strategy_config") else None
                target_mod.on_strategies_updated(saved_strats, optimal_config=opt_cfg)

        except Exception as e:
            print(f"[navigate_to] Aviso no fatal al sincronizar '{module_id}': {e}")

        self.save_app_state()


# ─────────────────────────────────────────────
#  Entry Point
# ─────────────────────────────────────────────
if __name__ == "__main__":
    app = CalculadoraApp()
    app.mainloop()
