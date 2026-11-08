"""
================================================================================
 Utilidades de diseño adaptable (responsive) para CustomTkinter
 Calculadora God League — Team NIX Esports
================================================================================
 Pequeños ayudantes SIN lógica de negocio para que las pantallas se adapten al
 ancho real de la ventana y al zoom de interfaz (85% / 100% / 115%):

   - ResponsiveGrid: recoloca una lista de widgets en N columnas según el ancho
     disponible (p. ej. 4 tarjetas -> 2x2 en ventanas estrechas).
   - WidthModes: ejecuta un callback cuando el ancho de un contenedor cruza un
     umbral (p. ej. pasar una botonera a una segunda fila).
   - bind_wraplength: ajusta el salto de línea de una etiqueta al ancho de su
     contenedor para que los textos largos no se corten.

 Nunca se destruyen ni recrean widgets: solo se cambia su colocación en el grid
 o el wraplength, de modo que es seguro llamarlos en cada <Configure>.
================================================================================
"""
from __future__ import annotations

import tkinter as tk

import customtkinter as ctk


def _bind_configure(widget, callback):
    # tkinter.Misc.bind directamente: CTkFrame.bind redirige al canvas interno.
    tk.Misc.bind(widget, "<Configure>", callback, "+")


def widget_scaling(widget) -> float:
    """Factor de zoom de interfaz de CustomTkinter aplicado al widget."""
    try:
        return float(ctk.ScalingTracker.get_widget_scaling(widget))
    except Exception:
        return 1.0


def _pad_sum(value) -> int:
    if isinstance(value, (tuple, list)):
        return sum(int(float(v)) for v in value)
    try:
        return 2 * int(float(value))
    except (TypeError, ValueError):
        return sum(int(float(v)) for v in str(value).split())


def _natural_width(widget) -> int:
    """
    Ancho natural de un contenedor según sus hijos gestionados por pack/grid
    (independiente de cuánto lo estire su padre). Si no tiene hijos, su reqwidth.
    """
    try:
        slaves = list(widget.pack_slaves()) + list(widget.grid_slaves())
    except Exception:
        slaves = []
    if not slaves:
        return widget.winfo_reqwidth()
    best = 0
    for s in slaves:
        mgr = s.winfo_manager()
        try:
            info = s.pack_info() if mgr == "pack" else s.grid_info()
            padx = _pad_sum(info.get("padx", 0)) + _pad_sum(info.get("ipadx", 0))
        except Exception:
            padx = 0
        best = max(best, s.winfo_reqwidth() + padx)
    if widget.grid_slaves():
        # En grid con varias columnas el ancho natural es la suma de columnas
        cols = {}
        for s in widget.grid_slaves():
            try:
                info = s.grid_info()
                c = int(info.get("column", 0))
                span = int(info.get("columnspan", 1))
                w = s.winfo_reqwidth() + _pad_sum(info.get("padx", 0))
            except Exception:
                continue
            if span == 1:
                cols[c] = max(cols.get(c, 0), w)
        best = max(best, sum(cols.values()))
    try:
        border = 2 * int(float(widget.cget("border_width")))
    except Exception:
        border = 0
    return best + border


class WidthModes:
    """
    Llama a ``apply_mode(modo)`` cada vez que ``compute_mode(ancho)`` cambia de valor.
    El ancho es el real (píxeles) del ``container`` en su evento <Configure>.
    """

    def __init__(self, container, compute_mode, apply_mode):
        self._container = container
        self._compute = compute_mode
        self._apply = apply_mode
        self._mode = None
        _bind_configure(container, self._on_configure)

    def _on_configure(self, event):
        if event.widget is not self._container or event.width <= 1:
            return
        try:
            self.refresh(event.width)
        except tk.TclError:
            # Widgets ya destruidos (cierre de la app o tarjetas reconstruidas): ignorar
            pass

    def refresh(self, width: int | None = None):
        if width is None:
            width = self._container.winfo_width()
        if width <= 1:
            return
        mode = self._compute(width)
        if mode != self._mode:
            self._mode = mode
            self._apply(mode)

    @property
    def mode(self):
        return self._mode


class ResponsiveGrid:
    """
    Coloca ``items`` (hijos de ``container``) en una rejilla de hasta ``max_cols``
    columnas. El número de columnas se elige para que cada columna tenga al menos
    ``min_col_width`` píxeles de diseño (se multiplican por el zoom de interfaz) o,
    si no se indica, el ancho natural (reqwidth) del item más ancho.

    ``grid_kw`` son las opciones comunes de grid (padx, pady, sticky...).
    ``first_row`` permite reservar filas superiores del contenedor (p. ej. un título).
    """

    def __init__(self, container, items, max_cols: int, min_col_width: int | None = None,
                 grid_kw: dict | None = None, first_row: int = 0, uniform: str | None = None,
                 item_grid_kw: list | None = None, equal_cols: bool = False):
        self.equal_cols = equal_cols
        self.container = container
        self.items = list(items)
        self.max_cols = max(1, int(max_cols))
        self.min_col_width = min_col_width
        self.grid_kw = dict(grid_kw or {})
        # Opciones de grid específicas por item (se combinan con grid_kw)
        self.item_grid_kw = list(item_grid_kw or [])
        self.first_row = first_row
        self.uniform = uniform or f"rg{id(self)}"
        self.cols = None
        self._layout(self.max_cols)
        self._watch = WidthModes(container, self._cols_for_width, self._layout)

    def _cols_for_width(self, width: int) -> int:
        visible = [w for w in self.items if w is not None and w.winfo_exists()]
        if not visible:
            return self.max_cols
        padx = self.grid_kw.get("padx", 0)
        if isinstance(padx, (tuple, list)):
            pad = sum(padx)
        else:
            pad = 2 * padx
        scale = widget_scaling(self.container)
        if self.min_col_width:
            need = self.min_col_width * scale + pad * scale
            cols = int(width // max(1.0, need))
            return max(1, min(self.max_cols, cols))
        # Sin ancho mínimo: mayor nº de columnas en el que cada fila cabe con el ancho
        # natural de sus items (calculado desde sus hijos: el reqwidth de un CTkFrame
        # estirado por el grid crece con el estiramiento y haría oscilar la disposición).
        reqs = [_natural_width(w) + pad * scale for w in visible]
        if self.equal_cols:
            # Columnas iguales: cada una debe admitir el item más ancho
            return max(1, min(self.max_cols, int(width // max(1.0, max(reqs)))))
        for cols in range(self.max_cols, 0, -1):
            rows = [reqs[i:i + cols] for i in range(0, len(reqs), cols)]
            if all(sum(r) <= width for r in rows):
                return cols
        return 1

    def _layout(self, cols: int):
        if cols == self.cols:
            return
        self.cols = cols
        for idx, w in enumerate(self.items):
            if not w.winfo_exists():
                continue
            r, c = divmod(idx, cols)
            kw = dict(self.grid_kw)
            if idx < len(self.item_grid_kw) and self.item_grid_kw[idx]:
                kw.update(self.item_grid_kw[idx])
            w.grid(row=self.first_row + r, column=c, **kw)
        for c in range(self.max_cols):
            if c < cols:
                self.container.grid_columnconfigure(c, weight=1, uniform=self.uniform if (self.min_col_width or self.equal_cols) else "")
            else:
                self.container.grid_columnconfigure(c, weight=0, uniform="", minsize=0)

    def refresh(self):
        self._watch.refresh()

    def set_items(self, items):
        """Sustituye los items (p. ej. tarjetas reconstruidas) y los recoloca."""
        self.items = list(items)
        self.cols = None
        width = self.container.winfo_width()
        self._layout(self._cols_for_width(width) if width > 1 else self.max_cols)
        self._watch._mode = self.cols


class HeaderLayout:
    """
    Cabecera de módulo [barra acento | título + subtítulo | botonera]:
      - Ancho suficiente: todo en una fila (como el diseño original).
      - Estrecho: la botonera baja a una segunda fila bajo el título.
      - En ambos casos el subtítulo salta de línea en lugar de cortarse.
    El modo depende solo del título principal y de la botonera (no del subtítulo),
    así que el salto de línea no puede provocar oscilaciones.
    """

    def __init__(self, header, accent_bar, title_label, subtitle_label, btn_box,
                 btn_padx: int = 16, accent_pad: int = 20):
        self.header = header
        self.accent_bar = accent_bar
        self.title_label = title_label
        self.subtitle_label = subtitle_label
        self.btn_box = btn_box
        self.btn_padx = btn_padx
        self.accent_pad = accent_pad
        self._mode = None
        self._wrap = None
        try:
            subtitle_label.configure(justify="left")
        except Exception:
            pass
        _bind_configure(header, self._on_configure)

    def _on_configure(self, event):
        if event.widget is not self.header or event.width <= 1:
            return
        try:
            self._relayout(event.width)
        except tk.TclError:
            pass

    def _relayout(self, width):
        s = widget_scaling(self.header)
        fixed = (4 + self.accent_pad) * s
        btn_w = self.btn_box.winfo_reqwidth() + 2 * self.btn_padx * s
        mode = "wide" if width - fixed - btn_w >= self.title_label.winfo_reqwidth() else "narrow"
        if mode != self._mode:
            self._mode = mode
            if mode == "wide":
                self.btn_box.grid(row=0, column=2, columnspan=1, padx=self.btn_padx, pady=10, sticky="e")
                self.accent_bar.grid_configure(rowspan=1)
            else:
                self.btn_box.grid(row=1, column=1, columnspan=2, padx=(0, self.btn_padx), pady=(0, 10), sticky="w")
                self.accent_bar.grid_configure(rowspan=2)
        avail = width - fixed - (btn_w if mode == "wide" else self.btn_padx * s)
        wrap = max(160, int(avail / s))
        if wrap != self._wrap:
            self._wrap = wrap
            try:
                self.subtitle_label.configure(wraplength=wrap)
            except Exception:
                pass


try:
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg as _FigureCanvasTkAgg
except Exception:  # pragma: no cover - matplotlib siempre está en requirements
    _FigureCanvasTkAgg = None


if _FigureCanvasTkAgg is not None:
    class ZoomAwareFigureCanvas(_FigureCanvasTkAgg):
        """
        FigureCanvasTkAgg cuya escala (device pixel ratio) sigue el ZOOM DE INTERFAZ
        de CustomTkinter en lugar del DPI de Windows.

        La app desactiva el escalado DPI automático de CustomTkinter, así que la UI se
        dibuja a 1 px = 1 px por el zoom elegido (85/100/115%). Matplotlib, en cambio,
        multiplicaba sus fuentes por el DPI del sistema (p. ej. x1.25 en Windows al 125%),
        con gráficos desproporcionados respecto al resto de la pantalla y títulos/ejes
        cortados en ventanas estrechas. Con esta clase ambos usan la misma escala.
        """

        def _ui_ratio(self) -> float:
            return round(widget_scaling(self._tkcanvas), 2)

        def _update_device_pixel_ratio(self, event=None):
            try:
                ratio = self._ui_ratio()
                if self._set_device_pixel_ratio(ratio):
                    w, h = self.get_width_height(physical=True)
                    self._tkcanvas.configure(width=w, height=h)
            except Exception:
                super()._update_device_pixel_ratio(event)

        def refresh_ui_scaling(self):
            """Re-aplica la escala tras cambiar el zoom de interfaz."""
            self._update_device_pixel_ratio()
            self.draw_idle()
else:  # pragma: no cover
    ZoomAwareFigureCanvas = None


def bind_wraplength(label, container=None, margin: int = 32, min_width: int = 120):
    """
    Mantiene ``label.wraplength`` igual al ancho del contenedor menos ``margin``
    (píxeles de diseño), para que los textos largos salten de línea en vez de
    cortarse. CTkLabel aplica el zoom de interfaz a wraplength por sí mismo.
    """
    container = container or label.master
    state = {"w": None}

    def _on_configure(event):
        if event.widget is not container or event.width <= 1:
            return
        try:
            if not label.winfo_exists():
                return
        except tk.TclError:
            return
        scale = widget_scaling(label)
        target = max(min_width, int(event.width / scale) - margin)
        if target != state["w"]:
            state["w"] = target
            try:
                label.configure(wraplength=target)
            except Exception:
                pass

    _bind_configure(container, _on_configure)
