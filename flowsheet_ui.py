# ======================================================
# FLOWSHEET UI — block diagram editor for ISBL estimation
# ======================================================
# Toplevel modal con tres paneles:
#
#   [Library]  [Canvas (drag, drop, connect)]  [Properties]
#
# El user:
#   1) selecciona un tipo de equipo en Library y aprieta
#      "+ Add" (o doble-click) → aparece un bloque en el
#      centro del canvas.
#   2) arrastra el bloque a la posición que quiera.
#   3) crea un stream: click derecho sobre un bloque
#      origen → "Connect to..." → click sobre el destino.
#      (Drag de puerto a puerto sería ideal; lo hacemos así
#      en V1 por simplicidad.)
#   4) doble-click sobre un bloque o stream abre dialog
#      para editar S, material, mass flow.
#   5) "Compute": Σ Cp° × n × Lang factor → FCI → ISBL
#      implícito vía los % del proyecto.  Verifica mass
#      balance por bloque (warning si no cierra).
#   6) "Apply ISBL": inyecta el ISBL al df_capital.
#   7) "Save..." / "Open..." persiste a JSON.
#
# Refs: motor en equipment_costs.py (Turton Apx A + Lang).
# ======================================================

import json
import math

from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict

from tkinter import (
    Toplevel,
    Canvas,
    Frame,
    Label,
    Menu,
    Scrollbar,
    StringVar,
    DoubleVar,
    IntVar,
    END,
    BOTH,
    LEFT,
    RIGHT,
    TOP,
    BOTTOM,
    X,
    Y,
    W,
    E,
    N,
    S,
    NSEW,
    VERTICAL,
    HORIZONTAL,
)
from tkinter import ttk
from tkinter import messagebox
from tkinter import filedialog
from tkinter import simpledialog

import equipment_costs as eq


# ======================================================
# CONSTANTES DE LAYOUT Y ESTILO
# ======================================================

CANVAS_BG     = "#fafafc"
GRID_COLOR    = "#e8e8ee"
GRID_STEP     = 20

BLOCK_W       = 130
BLOCK_H       = 60
BLOCK_FILL    = "#ffffff"
BLOCK_BORDER  = "#5c6bc0"
BLOCK_BORDER_SEL = "#283593"
BLOCK_TEXT    = "#1a1a1a"
BLOCK_SUB     = "#6c6c70"

STREAM_COLOR     = "#37474f"
STREAM_COLOR_SEL = "#c62828"
STREAM_LABEL_BG  = "#fff8d6"

ZOOM_MIN      = 0.30
ZOOM_MAX      = 3.00
ZOOM_STEP     = 1.15        # factor por tecleo de zoom in/out
CANVAS_W_LOG  = 4000        # tamaño lógico del lienzo (modelo)
CANVAS_H_LOG  = 3000

ROUTING_GAP   = 30          # distancia mínima desde el bloque al codo


# ======================================================
# MODELO DE DATOS
# ======================================================

@dataclass
class Block:
    id:        int
    name:      str               # ej "HX-1"
    eq_type:   str               # nombre del catálogo eq.EQUIPMENT_DATA
    S:         float             # parámetro de tamaño
    n:         int = 1           # cantidad en paralelo
    x:         float = 0.0
    y:         float = 0.0

    # caches del canvas (no se serializan)
    canvas_rect: Optional[int] = field(default=None, repr=False)
    canvas_text: Optional[int] = field(default=None, repr=False)
    canvas_sub:  Optional[int] = field(default=None, repr=False)


@dataclass
class Stream:
    id:        int
    name:      str               # ej "S-1"
    src:       int               # id del bloque origen
    dst:       int               # id del bloque destino
    mass_flow: float = 0.0       # tm/year (signo +)
    role:      str = "internal"  # "internal" | "feed" | "product"

    canvas_line:  Optional[int] = field(default=None, repr=False)
    canvas_label: Optional[int] = field(default=None, repr=False)


STREAM_ROLE_COLORS = {
    "internal": "#37474f",
    "feed":     "#2e7d32",
    "product":  "#e65100",
}
STREAM_ROLE_COLORS_SEL = {
    "internal": "#c62828",
    "feed":     "#1b5e20",
    "product":  "#bf360c",
}


@dataclass
class Flowsheet:
    blocks:   Dict[int, Block]   = field(default_factory=dict)
    streams:  Dict[int, Stream]  = field(default_factory=dict)
    _next_id: int = 1

    def new_id(self):
        v = self._next_id
        self._next_id += 1
        return v

    # --- serialization ---
    def to_dict(self):
        return {
            "blocks":   {bid: {k: v for k, v in asdict(b).items() if not k.startswith("canvas_")}
                         for bid, b in self.blocks.items()},
            "streams":  {sid: {k: v for k, v in asdict(s).items() if not k.startswith("canvas_")}
                         for sid, s in self.streams.items()},
            "_next_id": self._next_id,
        }

    @staticmethod
    def from_dict(d):
        fs = Flowsheet()
        for bid, bdict in d.get("blocks", {}).items():
            b = Block(**{k: v for k, v in bdict.items() if k in Block.__annotations__})
            fs.blocks[int(bid)] = b
        for sid, sdict in d.get("streams", {}).items():
            s = Stream(**{k: v for k, v in sdict.items() if k in Stream.__annotations__})
            fs.streams[int(sid)] = s
        fs._next_id = d.get("_next_id", 1)
        return fs


# ======================================================
# DIALOGS DE EDICIÓN
# ======================================================

class BlockEditDialog:
    """Modal para editar S, n y nombre del bloque."""

    def __init__(self, parent, block):
        self.parent = parent
        self.block = block
        self.result = None

        dlg = Toplevel(parent)
        dlg.title(f"Edit block — {block.name}")
        dlg.geometry("360x260+300+200")
        dlg.transient(parent)
        dlg.grab_set()
        self.dlg = dlg

        spec = eq.EQUIPMENT_DATA.get(block.eq_type, {})

        frm = ttk.Frame(dlg, padding=14)
        frm.pack(fill=BOTH, expand=True)

        ttk.Label(frm, text="Block ID:").grid(row=0, column=0, sticky=W, pady=4)
        ttk.Label(frm, text=block.name, foreground="#555").grid(row=0, column=1, sticky=W, pady=4)

        ttk.Label(frm, text="Equipment type:").grid(row=1, column=0, sticky=W, pady=4)
        ttk.Label(frm, text=block.eq_type, foreground="#555").grid(row=1, column=1, sticky=W, pady=4)

        ttk.Label(frm, text=f"Size S ({spec.get('S_unit', '?')}) *:").grid(row=2, column=0, sticky=W, pady=4)
        self.entry_s = ttk.Entry(frm, justify="right", width=14)
        self.entry_s.insert(0, f"{block.S:g}")
        self.entry_s.grid(row=2, column=1, sticky=W, pady=4)

        s_min = spec.get("S_min")
        s_max = spec.get("S_max")
        if s_min is not None and s_max is not None:
            ttk.Label(
                frm,
                text=f"Turton valid range: [{s_min:g} – {s_max:g}] {spec.get('S_unit', '')}",
                foreground="#888",
                font=("Segoe UI", 8),
            ).grid(row=3, column=0, columnspan=2, sticky=W, pady=(0, 6))

        ttk.Label(frm, text="N° units in parallel:").grid(row=4, column=0, sticky=W, pady=4)
        self.entry_n = ttk.Entry(frm, justify="right", width=14)
        self.entry_n.insert(0, str(block.n))
        self.entry_n.grid(row=4, column=1, sticky=W, pady=4)

        ttk.Label(frm, text="Custom name:").grid(row=5, column=0, sticky=W, pady=4)
        self.entry_name = ttk.Entry(frm, width=22)
        self.entry_name.insert(0, block.name)
        self.entry_name.grid(row=5, column=1, sticky=W, pady=4)

        # buttons
        btns = ttk.Frame(frm)
        btns.grid(row=6, column=0, columnspan=2, pady=(10, 0), sticky=E)
        ttk.Button(btns, text="Cancel", command=dlg.destroy).pack(side=LEFT, padx=4)
        ttk.Button(btns, text="OK",     command=self._ok).pack(side=LEFT)

        self.entry_s.focus()
        dlg.wait_window()

    def _ok(self):
        try:
            S = float(self.entry_s.get())
            n = int(self.entry_n.get())
            if S <= 0 or n < 1:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid", "S > 0 y n ≥ 1 son requeridos.")
            return
        nombre = self.entry_name.get().strip() or self.block.name
        self.block.S = S
        self.block.n = n
        self.block.name = nombre
        self.result = "ok"
        self.dlg.destroy()


class StreamEditDialog:
    """Modal para editar mass flow + role del stream."""

    def __init__(self, parent, stream, fs):
        self.stream = stream
        self.result = None
        self.fs = fs

        dlg = Toplevel(parent)
        dlg.title(f"Edit stream — {stream.name}")
        dlg.geometry("400x270+320+220")
        dlg.transient(parent)
        dlg.grab_set()
        self.dlg = dlg

        src = fs.blocks[stream.src].name
        dst = fs.blocks[stream.dst].name

        frm = ttk.Frame(dlg, padding=14)
        frm.pack(fill=BOTH, expand=True)

        ttk.Label(frm, text=f"Stream {stream.name}").grid(row=0, column=0, columnspan=2, sticky=W, pady=4)
        ttk.Label(frm, text=f"{src}  →  {dst}", foreground="#555").grid(row=1, column=0, columnspan=2, sticky=W, pady=4)

        ttk.Label(frm, text="Mass flow (tm/yr):").grid(row=2, column=0, sticky=W, pady=8)
        self.entry_m = ttk.Entry(frm, justify="right", width=14)
        self.entry_m.insert(0, f"{stream.mass_flow:g}")
        self.entry_m.grid(row=2, column=1, sticky=W, pady=8)

        ttk.Label(frm, text="Role:").grid(row=3, column=0, sticky=W, pady=8)
        self.role_var = StringVar(value=stream.role)
        self.role_combo = ttk.Combobox(
            frm, textvariable=self.role_var,
            values=["internal", "feed", "product"],
            state="readonly", width=12,
        )
        self.role_combo.grid(row=3, column=1, sticky=W, pady=8)

        ttk.Label(
            frm,
            text="feed: materia prima externa (alimenta costos variables)\n"
                 "product: producto final (alimenta producción anual)\n"
                 "internal: stream entre bloques (mass balance)",
            foreground="#888", font=("Segoe UI", 8), justify="left",
        ).grid(row=4, column=0, columnspan=2, sticky=W, pady=(0, 6))

        ttk.Label(frm, text="Custom name:").grid(row=5, column=0, sticky=W, pady=4)
        self.entry_name = ttk.Entry(frm, width=22)
        self.entry_name.insert(0, stream.name)
        self.entry_name.grid(row=5, column=1, sticky=W, pady=4)

        btns = ttk.Frame(frm)
        btns.grid(row=6, column=0, columnspan=2, pady=(10, 0), sticky=E)
        ttk.Button(btns, text="Cancel", command=dlg.destroy).pack(side=LEFT, padx=4)
        ttk.Button(btns, text="OK",     command=self._ok).pack(side=LEFT)

        self.entry_m.focus()
        dlg.wait_window()

    def _ok(self):
        try:
            m = float(self.entry_m.get())
            if m < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid", "Mass flow ≥ 0 requerido.")
            return
        self.stream.mass_flow = m
        self.stream.role = self.role_var.get() or "internal"
        nombre = self.entry_name.get().strip() or self.stream.name
        self.stream.name = nombre
        self.result = "ok"
        self.dlg.destroy()


# ======================================================
# VENTANA PRINCIPAL — FlowsheetEditor
# ======================================================

class FlowsheetEditor:
    """Editor de block diagram para estimar ISBL desde un PFD.

    Modos:
      - mode="main": se monta sobre un Tk root (la ventana principal
        de la app).  El botón final es 'Análisis económico →'
        y dispara subprocess.Popen lanzando ANA.py con el ISBL
        ya inyectado.
      - mode="modal": se monta sobre un Toplevel hijo del análisis
        económico existente.  El botón final es 'Apply ISBL' y
        actualiza df_capital in-place (caso legacy: invocado desde
        ANA.py > Tools > Estimate Capital from PFD).
    """

    def __init__(self, container, df_capital=None, on_apply=None, mode="modal"):
        self.container = container
        self.df_capital = df_capital
        self.on_apply = on_apply
        self.mode = mode
        self.win = container        # cualquier widget que acepte .pack como hijo

        self.fs = Flowsheet()
        self.selected_block: Optional[int] = None
        self.selected_stream: Optional[int] = None

        # drag state
        self._drag_block: Optional[int] = None
        self._drag_offx = 0
        self._drag_offy = 0

        # pending connection (after right-click "Connect to...")
        self._connecting_from: Optional[int] = None

        # zoom y pan (modelo en unidades base; canvas se renderiza × zoom)
        self.zoom = 1.0
        self._panning = False

        # título y geometría sólo si el container es ventana
        if hasattr(container, "title"):
            container.title("Flowsheet Editor — Process design")
        if hasattr(container, "geometry"):
            try:
                container.geometry("1320x780+80+30")
            except Exception:
                pass

        # toolbar arriba
        toolbar = ttk.Frame(container, padding=4)
        toolbar.pack(side=TOP, fill=X)
        ttk.Button(toolbar, text="New",            command=self.new).pack(side=LEFT, padx=2)
        ttk.Button(toolbar, text="Open…",          command=self.open_json).pack(side=LEFT, padx=2)
        ttk.Button(toolbar, text="Save…",          command=self.save_json).pack(side=LEFT, padx=2)

        # menu "Examples" para cargar procesos preestablecidos
        examples_btn = ttk.Menubutton(toolbar, text="Examples ▾")
        ex_menu = Menu(examples_btn, tearoff=0)
        ex_menu.add_command(label="HDA — Hydrodealkylation of toluene",
                            command=lambda: self.load_example("hda"))
        ex_menu.add_command(label="Methanol synthesis (simplified)",
                            command=lambda: self.load_example("methanol"))
        ex_menu.add_command(label="Binary distillation (benzene/toluene)",
                            command=lambda: self.load_example("distillation"))
        examples_btn.configure(menu=ex_menu)
        examples_btn.pack(side=LEFT, padx=2)

        ttk.Separator(toolbar, orient=VERTICAL).pack(side=LEFT, fill=Y, padx=8, pady=4)
        ttk.Button(toolbar, text="Delete selected (Del)", command=self.delete_selected).pack(side=LEFT, padx=2)
        ttk.Separator(toolbar, orient=VERTICAL).pack(side=LEFT, fill=Y, padx=8, pady=4)

        # zoom controls
        ttk.Button(toolbar, text="−", width=3, command=self.zoom_out).pack(side=LEFT, padx=1)
        self.zoom_label_var = StringVar(value="100%")
        ttk.Button(toolbar, textvariable=self.zoom_label_var, width=6,
                   command=self.zoom_reset).pack(side=LEFT, padx=1)
        ttk.Button(toolbar, text="+", width=3, command=self.zoom_in).pack(side=LEFT, padx=1)
        ttk.Button(toolbar, text="Fit", width=5, command=self.zoom_fit).pack(side=LEFT, padx=2)

        ttk.Separator(toolbar, orient=VERTICAL).pack(side=LEFT, fill=Y, padx=8, pady=4)
        ttk.Button(toolbar, text="Compute",        command=self.compute).pack(side=LEFT, padx=2)

        # botón de transición distinto según modo
        if mode == "main":
            ttk.Button(
                toolbar, text="Análisis económico →",
                command=self.launch_analysis,
            ).pack(side=RIGHT, padx=2)
        else:
            ttk.Button(toolbar, text="Apply ISBL",     command=self.apply_isbl).pack(side=LEFT, padx=2)
            ttk.Button(toolbar, text="Close",          command=self._close).pack(side=RIGHT, padx=2)

        # body
        body = ttk.Frame(container)
        body.pack(side=TOP, fill=BOTH, expand=True)

        # library (left)
        self._build_library(body)

        # canvas (center)
        self._build_canvas(body)

        # properties (right)
        self._build_properties(body)

        # status bar
        self.status_var = StringVar(value="0 blocks · 0 streams")
        ttk.Label(
            container, textvariable=self.status_var,
            anchor=W, padding=6,
            relief="sunken",
        ).pack(side=BOTTOM, fill=X)

        # keyboard bindings (bind_all para que funcionen desde cualquier widget)
        container.bind_all("<Delete>",   lambda e: self.delete_selected())
        container.bind_all("<Escape>",   lambda e: self._clear_pending_connection())

        self._draw_grid()
        self._update_status()

    def _close(self):
        try:
            self.win.destroy()
        except Exception:
            pass

    # ==================================================
    # ZOOM Y PAN
    # ==================================================

    def _sc(self, v):
        """Modelo → canvas (multiplicar por zoom)."""
        return v * self.zoom

    def _unsc(self, v):
        """Canvas → modelo."""
        return v / self.zoom

    def _model_xy(self, event):
        """Coord del modelo a partir del event del mouse,
        respetando scroll del canvas y zoom."""
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        return self._unsc(cx), self._unsc(cy)

    def _refresh_zoom_label(self):
        self.zoom_label_var.set(f"{self.zoom * 100:.0f}%")

    def _redraw_all(self):
        """Borra todo y vuelve a dibujar desde el modelo.
        Se usa al cambiar el zoom."""
        # preservar selección
        sel_b = self.selected_block
        sel_s = self.selected_stream

        self.canvas.delete("all")
        self._draw_grid()
        for b in self.fs.blocks.values():
            self._render_block(b)
        for s in self.fs.streams.values():
            self._render_stream(s)

        # reanchear scrollregion al contenido + margen
        max_x = max((b.x + BLOCK_W for b in self.fs.blocks.values()),
                    default=CANVAS_W_LOG)
        max_y = max((b.y + BLOCK_H for b in self.fs.blocks.values()),
                    default=CANVAS_H_LOG)
        sr_w = max(self._sc(max_x) + 200, 800)
        sr_h = max(self._sc(max_y) + 200, 600)
        self.canvas.configure(scrollregion=(0, 0, sr_w, sr_h))

        # reaplicar selección visual
        if sel_b is not None and sel_b in self.fs.blocks:
            self._select_block(sel_b)
        elif sel_s is not None and sel_s in self.fs.streams:
            self._select_stream(sel_s)

        self._refresh_zoom_label()

    def _zoom_at(self, view_x, view_y, factor):
        """Zoom anclado al punto (view_x, view_y) del widget.
        El punto bajo el cursor queda quieto en pantalla."""
        new_zoom = self.zoom * factor
        new_zoom = max(ZOOM_MIN, min(ZOOM_MAX, new_zoom))
        if abs(new_zoom - self.zoom) < 1e-6:
            return

        # punto del modelo bajo el cursor (antes del zoom)
        cx_before = self.canvas.canvasx(view_x)
        cy_before = self.canvas.canvasy(view_y)
        mx = cx_before / self.zoom
        my = cy_before / self.zoom

        self.zoom = new_zoom
        self._redraw_all()

        # mover scroll para que (mx, my) quede en (view_x, view_y)
        cx_after = mx * self.zoom
        cy_after = my * self.zoom
        sr = self.canvas.cget("scrollregion").split()
        try:
            sr_w = float(sr[2])
            sr_h = float(sr[3])
        except (IndexError, ValueError):
            return
        self.canvas.xview_moveto(max(0.0, (cx_after - view_x) / sr_w))
        self.canvas.yview_moveto(max(0.0, (cy_after - view_y) / sr_h))

    def zoom_in(self):
        w = self.canvas.winfo_width()  or 800
        h = self.canvas.winfo_height() or 600
        self._zoom_at(w / 2, h / 2, ZOOM_STEP)

    def zoom_out(self):
        w = self.canvas.winfo_width()  or 800
        h = self.canvas.winfo_height() or 600
        self._zoom_at(w / 2, h / 2, 1 / ZOOM_STEP)

    def zoom_reset(self):
        self.zoom = 1.0
        self._redraw_all()
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)

    def zoom_fit(self):
        """Ajusta zoom para que todos los bloques entren en la vista."""
        if not self.fs.blocks:
            self.zoom_reset()
            return

        xs = [b.x for b in self.fs.blocks.values()]
        ys = [b.y for b in self.fs.blocks.values()]
        min_x, max_x = min(xs), max(xs) + BLOCK_W
        min_y, max_y = min(ys), max(ys) + BLOCK_H

        margin = 60
        w = (self.canvas.winfo_width()  or 800) - 2 * margin
        h = (self.canvas.winfo_height() or 600) - 2 * margin
        if w <= 0 or h <= 0:
            return

        fx = w / (max_x - min_x + 1)
        fy = h / (max_y - min_y + 1)
        self.zoom = max(ZOOM_MIN, min(ZOOM_MAX, min(fx, fy)))
        self._redraw_all()

        # centrar el contenido en la vista
        sr = self.canvas.cget("scrollregion").split()
        try:
            sr_w = float(sr[2])
            sr_h = float(sr[3])
        except (IndexError, ValueError):
            return
        cx = self._sc((min_x + max_x) / 2)
        cy = self._sc((min_y + max_y) / 2)
        view_w = self.canvas.winfo_width()  or 800
        view_h = self.canvas.winfo_height() or 600
        self.canvas.xview_moveto(max(0.0, (cx - view_w / 2) / sr_w))
        self.canvas.yview_moveto(max(0.0, (cy - view_h / 2) / sr_h))

    def _on_mousewheel_zoom(self, event):
        # Windows: event.delta múltiplo de 120
        factor = ZOOM_STEP if event.delta > 0 else 1 / ZOOM_STEP
        self._zoom_at(event.x, event.y, factor)

    def _on_mousewheel_scroll(self, event):
        self.canvas.yview_scroll(-int(event.delta / 120) or (-1 if event.delta > 0 else 1), "units")

    def _on_mousewheel_hscroll(self, event):
        self.canvas.xview_scroll(-int(event.delta / 120) or (-1 if event.delta > 0 else 1), "units")

    def _on_pan_start(self, event):
        self.canvas.scan_mark(event.x, event.y)
        self.canvas.configure(cursor="fleur")

    def _on_pan_drag(self, event):
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    def _on_pan_end(self, _event):
        self.canvas.configure(cursor="")

    # ==================================================
    # PANELES
    # ==================================================

    def _build_library(self, body):
        frame = ttk.LabelFrame(body, text=" Equipment library ", padding=6, width=240)
        frame.pack(side=LEFT, fill=Y, padx=(8, 4), pady=8)
        frame.pack_propagate(False)

        ttk.Label(
            frame,
            text="Click on an equipment, then 'Add'.\n"
                 "Double-click on a block to edit S/n.\n"
                 "Right-click a block → Connect to...",
            foreground="#666", font=("Segoe UI", 8),
            justify="left", wraplength=220,
        ).pack(fill=X, pady=(0, 6))

        # tree con categorías
        tree = ttk.Treeview(frame, show="tree", selectmode="browse", height=18)
        cats = eq.por_categoria()
        for cat, names in cats.items():
            parent = tree.insert("", END, text=cat, open=True, tags=("cat",))
            for nombre in names:
                tree.insert(parent, END, text=nombre, tags=("eq",))
        tree.pack(fill=BOTH, expand=True)
        self.lib_tree = tree

        # botón Add
        ttk.Button(frame, text="+ Add to canvas",
                   command=self.add_selected_equipment).pack(fill=X, pady=(6, 0))

        # doble-click también agrega
        tree.bind("<Double-1>", lambda e: self.add_selected_equipment())

    def _build_canvas(self, body):
        center = ttk.Frame(body)
        center.pack(side=LEFT, fill=BOTH, expand=True, padx=4, pady=8)

        # grid layout para canvas + scrollbars
        center.rowconfigure(0, weight=1)
        center.columnconfigure(0, weight=1)

        canvas = Canvas(
            center, bg=CANVAS_BG, highlightthickness=1,
            highlightbackground="#cccccc",
            scrollregion=(0, 0, CANVAS_W_LOG, CANVAS_H_LOG),
        )
        canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas = canvas

        hbar = Scrollbar(center, orient=HORIZONTAL, command=canvas.xview)
        hbar.grid(row=1, column=0, sticky="ew")
        vbar = Scrollbar(center, orient=VERTICAL,   command=canvas.yview)
        vbar.grid(row=0, column=1, sticky="ns")
        canvas.configure(xscrollcommand=hbar.set, yscrollcommand=vbar.set)

        # mouse: izquierdo selecciona/arrastra bloque
        canvas.bind("<Button-1>",       self._on_left_click)
        canvas.bind("<B1-Motion>",      self._on_left_drag)
        canvas.bind("<ButtonRelease-1>",self._on_left_release)
        canvas.bind("<Button-3>",       self._on_right_click)
        canvas.bind("<Double-1>",       self._on_double_click)

        # mouse middle (Button-2): pan
        canvas.bind("<ButtonPress-2>",   self._on_pan_start)
        canvas.bind("<B2-Motion>",       self._on_pan_drag)
        canvas.bind("<ButtonRelease-2>", self._on_pan_end)

        # Space + drag izquierdo también funciona como pan (laptops sin
        # middle button). Mantengo state en self._panning.
        canvas.bind("<KeyPress-space>",   lambda e: setattr(self, "_panning", True))
        canvas.bind("<KeyRelease-space>", lambda e: setattr(self, "_panning", False))
        canvas.focus_set()

        # rueda: zoom con Ctrl, scroll vertical sin Ctrl
        # Linux usa Button-4 / Button-5, Windows/Mac usa MouseWheel
        canvas.bind("<Control-MouseWheel>", self._on_mousewheel_zoom)
        canvas.bind("<Control-Button-4>",   lambda e: self._zoom_at(e.x, e.y, ZOOM_STEP))
        canvas.bind("<Control-Button-5>",   lambda e: self._zoom_at(e.x, e.y, 1 / ZOOM_STEP))
        canvas.bind("<MouseWheel>",         self._on_mousewheel_scroll)
        canvas.bind("<Button-4>",           lambda e: canvas.yview_scroll(-1, "units"))
        canvas.bind("<Button-5>",           lambda e: canvas.yview_scroll(1, "units"))
        canvas.bind("<Shift-MouseWheel>",   self._on_mousewheel_hscroll)
        canvas.bind("<Shift-Button-4>",     lambda e: canvas.xview_scroll(-1, "units"))
        canvas.bind("<Shift-Button-5>",     lambda e: canvas.xview_scroll(1, "units"))

    def _build_properties(self, body):
        frame = ttk.LabelFrame(body, text=" Properties ", padding=6, width=300)
        frame.pack(side=LEFT, fill=Y, padx=(4, 8), pady=8)
        frame.pack_propagate(False)

        self.prop_var = StringVar(value="(nothing selected)")
        self.prop_label = ttk.Label(
            frame, textvariable=self.prop_var,
            justify="left", wraplength=280, anchor="nw",
            font=("Consolas", 9),
        )
        self.prop_label.pack(fill=BOTH, expand=True)

        # área de resultados al final
        sep = ttk.Separator(frame, orient=HORIZONTAL)
        sep.pack(fill=X, pady=8)

        self.results_var = StringVar(value="(Compute to estimate ISBL)")
        ttk.Label(
            frame, textvariable=self.results_var,
            justify="left", wraplength=280, anchor="nw",
            font=("Consolas", 9), foreground="#1565c0",
        ).pack(fill=X)

    # ==================================================
    # ACCIONES
    # ==================================================

    def new(self):
        if self.fs.blocks and not messagebox.askyesno(
            "New flowsheet", "Discard current flowsheet and start empty?"
        ):
            return
        self.fs = Flowsheet()
        self.canvas.delete("all")
        self._draw_grid()
        self.selected_block = None
        self.selected_stream = None
        self._update_status()
        self._update_properties()
        self.results_var.set("(Compute to estimate ISBL)")

    # ==================================================
    # EXAMPLES — procesos preestablecidos
    # ==================================================

    def load_example(self, key):
        """Carga un proceso preestablecido (sobrescribe el actual).
        Sirve como smoke test del software end-to-end:
        bloques + streams con feeds/products + Compute + ISBL.
        """
        if self.fs.blocks and not messagebox.askyesno(
            "Load example",
            "Esto va a reemplazar el flowsheet actual. ¿Continuar?",
        ):
            return

        builders = {
            "hda":          self._example_hda,
            "methanol":     self._example_methanol,
            "distillation": self._example_distillation,
        }
        builder = builders.get(key)
        if builder is None:
            return

        self.fs = Flowsheet()
        builder()
        self._redraw_all()
        self.zoom_fit()
        self.selected_block = None
        self.selected_stream = None
        self._update_status()
        self._update_properties()
        self.results_var.set("(Compute to estimate ISBL)")

    def _add_example_block(self, name, eq_type, S, x, y, n=1):
        bid = self.fs.new_id()
        b = Block(id=bid, name=name, eq_type=eq_type, S=S, n=n, x=x, y=y)
        self.fs.blocks[bid] = b
        return bid

    def _add_example_stream(self, src, dst, name, mass_flow=0.0, role="internal"):
        sid = self.fs.new_id()
        s = Stream(id=sid, name=name, src=src, dst=dst,
                   mass_flow=mass_flow, role=role)
        self.fs.streams[sid] = s
        return sid

    def _example_hda(self):
        """HDA — Hydrodealkylation of toluene to benzene.
        Versión simplificada de Douglas / Turton.
        Toluene + H2 → Benzene + CH4
        100 kmol/h tolueno, conversión ~75%."""
        col_x = [120, 360, 600, 840, 1080, 1320]
        row_y = [240, 420]

        # row 0 — alimentación + reacción
        b_pre  = self._add_example_block("PRE-1", "Heat exch. — floating head", 250.0, col_x[0], row_y[0])
        b_fur  = self._add_example_block("F-1",  "Fired heater — non-reformer", 5000.0, col_x[1], row_y[0])
        b_rxn  = self._add_example_block("R-1",  "Reactor — jacketed non-agit.",   25.0, col_x[2], row_y[0])
        b_cool = self._add_example_block("E-1",  "Heat exch. — air cooler",       180.0, col_x[3], row_y[0])
        b_fls  = self._add_example_block("V-1",  "Vessel — vertical",              20.0, col_x[4], row_y[0])

        # row 1 — separación
        b_col  = self._add_example_block("T-1",  "Tower (column shell)",           45.0, col_x[2], row_y[1])
        b_reb  = self._add_example_block("E-2",  "Heat exch. — kettle reboiler",  150.0, col_x[3], row_y[1])
        b_cnd  = self._add_example_block("E-3",  "Heat exch. — floating head",    160.0, col_x[1], row_y[1])
        b_pmp  = self._add_example_block("P-1",  "Pump — centrifugal",             15.0, col_x[0], row_y[1])

        # streams
        self._add_example_stream(b_pmp,  b_pre,  "S-feed-tol", 11000, role="feed")
        self._add_example_stream(b_pre,  b_fur,  "S-1")
        self._add_example_stream(b_fur,  b_rxn,  "S-2")
        self._add_example_stream(b_rxn,  b_cool, "S-3")
        self._add_example_stream(b_cool, b_fls,  "S-4")
        self._add_example_stream(b_fls,  b_col,  "S-liq")
        self._add_example_stream(b_col,  b_reb,  "S-bot")
        self._add_example_stream(b_col,  b_cnd,  "S-vap")
        self._add_example_stream(b_cnd,  b_pmp,  "S-recyc")     # recycle
        # producto + subproducto
        b_prod = self._add_example_block("PROD", "Storage tank — cone roof", 500.0, col_x[5], row_y[1])
        self._add_example_stream(b_cnd, b_prod, "S-benzene", 8500, role="product")
        b_h2   = self._add_example_block("FH2",  "Storage tank — cone roof", 100.0, col_x[5], row_y[0])
        self._add_example_stream(b_fls, b_h2,   "S-H2-purge", 350, role="product")

    def _example_methanol(self):
        """Methanol synthesis (simplified).
        Syngas (CO + 2H2) → CH3OH
        Reactor + flash + column."""
        col_x = [120, 360, 600, 840, 1080]
        y_top = 240
        y_bot = 440

        b_comp = self._add_example_block("C-1",  "Compressor — centrifugal",      800.0, col_x[0], y_top)
        b_pre  = self._add_example_block("E-1",  "Heat exch. — floating head",    220.0, col_x[1], y_top)
        b_rxn  = self._add_example_block("R-1",  "Reactor — jacketed non-agit.",   30.0, col_x[2], y_top)
        b_cool = self._add_example_block("E-2",  "Heat exch. — air cooler",       200.0, col_x[3], y_top)
        b_fls  = self._add_example_block("V-1",  "Vessel — vertical",              15.0, col_x[4], y_top)

        b_col  = self._add_example_block("T-1",  "Tower (column shell)",           35.0, col_x[2], y_bot)
        b_reb  = self._add_example_block("E-3",  "Heat exch. — kettle reboiler",  130.0, col_x[3], y_bot)
        b_cnd  = self._add_example_block("E-4",  "Heat exch. — floating head",    140.0, col_x[1], y_bot)

        self._add_example_stream(b_comp, b_pre,  "S-syngas", 14000, role="feed")
        self._add_example_stream(b_pre,  b_rxn,  "S-1")
        self._add_example_stream(b_rxn,  b_cool, "S-2")
        self._add_example_stream(b_cool, b_fls,  "S-3")
        self._add_example_stream(b_fls,  b_col,  "S-crude")
        self._add_example_stream(b_col,  b_reb,  "S-bot")
        self._add_example_stream(b_col,  b_cnd,  "S-vap")

        b_meoh = self._add_example_block("PROD", "Storage tank — floating roof", 400.0, col_x[4], y_bot)
        self._add_example_stream(b_cnd, b_meoh, "S-MeOH", 9500, role="product")

        b_water = self._add_example_block("WW",  "Storage tank — cone roof", 50.0, col_x[0], y_bot)
        self._add_example_stream(b_reb, b_water, "S-water", 600, role="product")

    def _example_distillation(self):
        """Destilación binaria benceno/tolueno.
        Mezcla 50/50 → benceno por top, tolueno por fondo.
        Pre-heater + column + condenser + reboiler + pumps."""
        col_x = [120, 360, 600, 840, 1080]
        y_top = 220
        y_bot = 480

        b_feed = self._add_example_block("F-tank", "Storage tank — cone roof", 200.0, col_x[0], 350)
        b_pmp1 = self._add_example_block("P-1",    "Pump — centrifugal",         8.0, col_x[1], 350)
        b_pre  = self._add_example_block("E-1",    "Heat exch. — floating head", 120.0, col_x[2], 350)
        b_col  = self._add_example_block("T-1",    "Tower (column shell)",        20.0, col_x[3], 350)

        b_cnd  = self._add_example_block("E-2",    "Heat exch. — floating head",  90.0, col_x[3], y_top)
        b_reb  = self._add_example_block("E-3",    "Heat exch. — kettle reboiler", 85.0, col_x[3], y_bot)

        b_dist = self._add_example_block("PROD-D", "Storage tank — cone roof",    150.0, col_x[4], y_top)
        b_bot  = self._add_example_block("PROD-B", "Storage tank — cone roof",    150.0, col_x[4], y_bot)

        self._add_example_stream(b_feed, b_pmp1, "S-feed", 10000, role="feed")
        self._add_example_stream(b_pmp1, b_pre,  "S-1")
        self._add_example_stream(b_pre,  b_col,  "S-2")
        self._add_example_stream(b_col,  b_cnd,  "S-vap")
        self._add_example_stream(b_col,  b_reb,  "S-bot")
        self._add_example_stream(b_cnd,  b_dist, "S-benzene", 5000, role="product")
        self._add_example_stream(b_reb,  b_bot,  "S-toluene", 5000, role="product")

    def open_json(self):
        path = filedialog.askopenfilename(
            title="Open flowsheet",
            filetypes=[("JSON", "*.json")],
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.fs = Flowsheet.from_dict(data)
        except Exception as e:
            messagebox.showerror("Open error", f"{type(e).__name__}: {e}")
            return
        self.selected_block = None
        self.selected_stream = None
        self._redraw_all()
        self.zoom_fit()
        self._update_status()
        self._update_properties()

    def save_json(self):
        path = filedialog.asksaveasfilename(
            title="Save flowsheet",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.fs.to_dict(), f, indent=2)
        except Exception as e:
            messagebox.showerror("Save error", f"{type(e).__name__}: {e}")
            return
        messagebox.showinfo("Saved", f"Flowsheet saved to:\n{path}")

    def delete_selected(self):
        if self.selected_block is not None:
            self._delete_block(self.selected_block)
            self.selected_block = None
        elif self.selected_stream is not None:
            self._delete_stream(self.selected_stream)
            self.selected_stream = None
        self._update_status()
        self._update_properties()

    def add_selected_equipment(self):
        sel = self.lib_tree.selection()
        if not sel:
            messagebox.showinfo("Select equipment", "Click on an equipment first.")
            return
        item = sel[0]
        tags = self.lib_tree.item(item, "tags")
        if "eq" not in tags:
            messagebox.showinfo("Pick equipment", "Select a leaf, not a category.")
            return
        eq_type = self.lib_tree.item(item, "text")
        self._add_block(eq_type)

    # ==================================================
    # BLOCKS
    # ==================================================

    def _add_block(self, eq_type, x=None, y=None):
        spec = eq.EQUIPMENT_DATA.get(eq_type)
        if not spec:
            return

        bid = self.fs.new_id()
        S_default = (spec["S_min"] + spec["S_max"]) / 2
        # short name por categoría
        prefix_map = {
            "Heat exchangers": "HX",
            "Compressors":     "C",
            "Pumps":           "P",
            "Vessels":         "V",
            "Storage":         "TK",
            "Reactors":        "R",
            "Fired heaters":   "H",
            "Solids / sep.":   "F",
            "Fans / blowers":  "FAN",
            "Trays / packing": "T",
        }
        prefix = prefix_map.get(spec["categoria"], "EQ")
        # contar cuántos del mismo prefix ya hay
        same = [b for b in self.fs.blocks.values() if b.name.startswith(prefix + "-")]
        nombre = f"{prefix}-{len(same) + 1}"

        if x is None:
            # ubicar en el centro del viewport, evitando overlaps
            x = 200 + (len(self.fs.blocks) % 6) * 160
            y = 100 + ((len(self.fs.blocks) // 6) % 6) * 100

        b = Block(id=bid, name=nombre, eq_type=eq_type, S=S_default, n=1, x=x, y=y)
        self.fs.blocks[bid] = b
        self._render_block(b)
        self._select_block(bid)
        self._update_status()

    def _render_block(self, b):
        # texto principal + sub (S y eq type)
        spec = eq.EQUIPMENT_DATA.get(b.eq_type, {})
        unit = spec.get("S_unit", "")
        cat = spec.get("categoria", "")

        x0 = self._sc(b.x)
        y0 = self._sc(b.y)
        x1 = self._sc(b.x + BLOCK_W)
        y1 = self._sc(b.y + BLOCK_H)

        font_title = ("Segoe UI", max(7, int(10 * self.zoom)), "bold")
        font_sub   = ("Segoe UI", max(6, int(8  * self.zoom)))

        b.canvas_rect = self.canvas.create_rectangle(
            x0, y0, x1, y1,
            fill=BLOCK_FILL, outline=BLOCK_BORDER, width=2,
            tags=("block", f"b{b.id}"),
        )
        b.canvas_text = self.canvas.create_text(
            (x0 + x1) / 2, y0 + self._sc(18),
            text=b.name, fill=BLOCK_TEXT, font=font_title,
            tags=("block", f"b{b.id}"),
        )
        b.canvas_sub = self.canvas.create_text(
            (x0 + x1) / 2, y0 + self._sc(40),
            text=f"{cat}\nS = {b.S:g} {unit}" + (f"  × {b.n}" if b.n > 1 else ""),
            fill=BLOCK_SUB, font=font_sub, justify="center",
            tags=("block", f"b{b.id}"),
        )

    def _refresh_block_text(self, b):
        spec = eq.EQUIPMENT_DATA.get(b.eq_type, {})
        unit = spec.get("S_unit", "")
        cat = spec.get("categoria", "")
        self.canvas.itemconfigure(b.canvas_text, text=b.name)
        self.canvas.itemconfigure(
            b.canvas_sub,
            text=f"{cat}\nS = {b.S:g} {unit}" + (f"  × {b.n}" if b.n > 1 else ""),
        )

    def _delete_block(self, bid):
        b = self.fs.blocks.pop(bid, None)
        if b is None:
            return
        # remover sus streams
        for sid in [sid for sid, s in self.fs.streams.items()
                    if s.src == bid or s.dst == bid]:
            self._delete_stream(sid)
        for cid in (b.canvas_rect, b.canvas_text, b.canvas_sub):
            if cid is not None:
                self.canvas.delete(cid)

    def _select_block(self, bid):
        # deselect anteriores
        self._deselect_all_visual()
        self.selected_stream = None
        self.selected_block = bid
        b = self.fs.blocks.get(bid)
        if b and b.canvas_rect is not None:
            self.canvas.itemconfigure(b.canvas_rect,
                                      outline=BLOCK_BORDER_SEL, width=3)
        self._update_properties()

    def _deselect_all_visual(self):
        for b in self.fs.blocks.values():
            if b.canvas_rect is not None:
                self.canvas.itemconfigure(b.canvas_rect,
                                          outline=BLOCK_BORDER, width=2)
        for s in self.fs.streams.values():
            if s.canvas_line is not None:
                color = STREAM_ROLE_COLORS.get(s.role, STREAM_COLOR)
                self.canvas.itemconfigure(s.canvas_line, fill=color, width=2)

    # ==================================================
    # STREAMS
    # ==================================================

    def _add_stream(self, src_id, dst_id):
        if src_id == dst_id:
            return
        # evitar duplicado
        for s in self.fs.streams.values():
            if s.src == src_id and s.dst == dst_id:
                messagebox.showinfo("Stream exists",
                                    f"Stream {s.name} already connects these blocks.")
                return
        sid = self.fs.new_id()
        nombre = f"S-{len([s for s in self.fs.streams.values()]) + 1}"
        s = Stream(id=sid, name=nombre, src=src_id, dst=dst_id, mass_flow=0.0)
        self.fs.streams[sid] = s
        self._render_stream(s)
        self._update_status()

    # ---------- anchors distribuidos ----------
    # Si un bloque tiene N streams entrando por la izquierda,
    # se reparten en y = h*(i+1)/(N+1).  Lo mismo para outlets
    # por la derecha.  Esto evita superposiciones y da el
    # look de ingeniería precisa.

    def _stream_slot(self, s, side):
        """Devuelve (idx, total) para colocar el ancla de
        este stream en el lado `side` del bloque correspondiente.

        side: 'src_out' = salida del src (derecha del src)
              'dst_in'  = entrada del dst (izquierda del dst)
        """
        if side == "src_out":
            bid = s.src
            others = [t for t in self.fs.streams.values() if t.src == bid]
        else:
            bid = s.dst
            others = [t for t in self.fs.streams.values() if t.dst == bid]
        others.sort(key=lambda t: t.id)
        idx = others.index(s) if s in others else 0
        return idx, max(1, len(others))

    def _block_port(self, b, side, idx, total):
        """Coord (modelo) del puerto idx-ésimo de `total` en el
        lado `side` de un bloque."""
        frac = (idx + 1) / (total + 1)
        if side == "right":
            return b.x + BLOCK_W, b.y + BLOCK_H * frac
        if side == "left":
            return b.x,           b.y + BLOCK_H * frac
        if side == "top":
            return b.x + BLOCK_W * frac, b.y
        if side == "bottom":
            return b.x + BLOCK_W * frac, b.y + BLOCK_H
        return b.x, b.y

    def _ortho_path(self, x1, y1, x2, y2):
        """Devuelve la polyline ortogonal en coords del MODELO
        entre el puerto out (x1,y1, sale a derecha) y el puerto
        in (x2,y2, entra por izquierda).  Estilo PFD:

          1) sale horizontal del src una distancia mínima
          2) sube/baja vertical
          3) entra horizontal al dst

        Si están casi alineados (Δy pequeño), línea recta con
        leve offset para no pisar bordes."""
        gap = ROUTING_GAP
        # midpoint x — si dst está a la izquierda del src (loop),
        # rodeamos por arriba o abajo
        if x2 >= x1 + 2 * gap:
            mx = (x1 + x2) / 2
            if abs(y1 - y2) < 2:   # alineados → línea recta
                return [x1, y1, x2, y2]
            return [x1, y1,  mx, y1,  mx, y2,  x2, y2]
        # bucle de retroceso (recycle): salir derecha, bajar/subir
        # bordeando, volver
        out_x = x1 + gap
        in_x  = x2 - gap
        # ir hacia abajo o arriba — elegimos abajo para consistencia
        below = max(y1, y2) + 2 * gap
        return [x1, y1,  out_x, y1,  out_x, below,
                in_x,  below, in_x,  y2,  x2, y2]

    def _stream_endpoints(self, s):
        """Coords (modelo) del polyline ortogonal del stream."""
        b_src = self.fs.blocks.get(s.src)
        b_dst = self.fs.blocks.get(s.dst)
        if b_src is None or b_dst is None:
            return None

        # slot del puerto
        out_idx, out_n = self._stream_slot(s, "src_out")
        in_idx,  in_n  = self._stream_slot(s, "dst_in")

        x1, y1 = self._block_port(b_src, "right", out_idx, out_n)
        x2, y2 = self._block_port(b_dst, "left",  in_idx,  in_n)
        return self._ortho_path(x1, y1, x2, y2)

    def _label_xy(self, pts):
        """Punto medio del polyline para colocar el label."""
        if len(pts) >= 4:
            # punto medio del segmento horizontal más largo
            best_len = -1
            best = (pts[0], pts[1])
            for i in range(0, len(pts) - 2, 2):
                x1, y1 = pts[i], pts[i+1]
                x2, y2 = pts[i+2], pts[i+3]
                if y1 == y2:
                    L = abs(x2 - x1)
                    if L > best_len:
                        best_len = L
                        best = ((x1 + x2) / 2, y1 - 10)
            return best
        return (pts[0], pts[1])

    def _render_stream(self, s):
        pts = self._stream_endpoints(s)
        if pts is None:
            return
        canvas_pts = [self._sc(v) for v in pts]
        color = STREAM_ROLE_COLORS.get(s.role, STREAM_COLOR)

        s.canvas_line = self.canvas.create_line(
            *canvas_pts,
            fill=color, width=2, arrow="last",
            arrowshape=(12, 14, 5),
            tags=("stream", f"s{s.id}"),
        )
        lx, ly = self._label_xy(pts)
        role_tag = " [feed]" if s.role == "feed" else (" [product]" if s.role == "product" else "")
        s.canvas_label = self.canvas.create_text(
            self._sc(lx), self._sc(ly),
            text=s.name + role_tag + (f"  {s.mass_flow:g} tm/yr" if s.mass_flow else ""),
            fill="#444", font=("Segoe UI", max(6, int(8 * self.zoom))),
            tags=("stream", f"s{s.id}"),
        )

    def _refresh_stream(self, s):
        pts = self._stream_endpoints(s)
        if pts is None:
            return
        canvas_pts = [self._sc(v) for v in pts]
        if s.canvas_line is not None:
            self.canvas.coords(s.canvas_line, *canvas_pts)
            color = STREAM_ROLE_COLORS.get(s.role, STREAM_COLOR)
            self.canvas.itemconfigure(s.canvas_line, fill=color)
        if s.canvas_label is not None:
            lx, ly = self._label_xy(pts)
            self.canvas.coords(s.canvas_label, self._sc(lx), self._sc(ly))
            role_tag = " [feed]" if s.role == "feed" else (" [product]" if s.role == "product" else "")
            self.canvas.itemconfigure(
                s.canvas_label,
                text=s.name + role_tag + (f"  {s.mass_flow:g} tm/yr" if s.mass_flow else ""),
            )

    def _delete_stream(self, sid):
        s = self.fs.streams.pop(sid, None)
        if s is None:
            return
        for cid in (s.canvas_line, s.canvas_label):
            if cid is not None:
                self.canvas.delete(cid)

    def _select_stream(self, sid):
        self._deselect_all_visual()
        self.selected_block = None
        self.selected_stream = sid
        s = self.fs.streams.get(sid)
        if s and s.canvas_line is not None:
            color = STREAM_ROLE_COLORS_SEL.get(s.role, STREAM_COLOR_SEL)
            self.canvas.itemconfigure(s.canvas_line, fill=color, width=3)
        self._update_properties()

    @staticmethod
    def _block_anchor(b, side):
        # legacy: anchor centrado.  Hoy usamos _block_port para
        # distribuir múltiples puertos a lo largo del lado.
        if side == "right":
            return b.x + BLOCK_W, b.y + BLOCK_H / 2
        if side == "left":
            return b.x, b.y + BLOCK_H / 2
        if side == "top":
            return b.x + BLOCK_W / 2, b.y
        if side == "bottom":
            return b.x + BLOCK_W / 2, b.y + BLOCK_H

    # ==================================================
    # CANVAS EVENTS
    # ==================================================

    def _draw_grid(self):
        # grid en coords del CANVAS (ya escaladas), cubre el scrollregion
        sr = self.canvas.cget("scrollregion").split()
        try:
            w = float(sr[2]) if len(sr) >= 4 else CANVAS_W_LOG * self.zoom
            h = float(sr[3]) if len(sr) >= 4 else CANVAS_H_LOG * self.zoom
        except ValueError:
            w, h = CANVAS_W_LOG * self.zoom, CANVAS_H_LOG * self.zoom

        step = max(8, int(GRID_STEP * self.zoom))  # no spammear líneas a zoom bajo
        x = 0
        while x <= w:
            self.canvas.create_line(x, 0, x, h, fill=GRID_COLOR, tags=("grid",))
            x += step
        y = 0
        while y <= h:
            self.canvas.create_line(0, y, w, y, fill=GRID_COLOR, tags=("grid",))
            y += step
        self.canvas.tag_lower("grid")

    def _block_under_cursor(self, x, y):
        for b in self.fs.blocks.values():
            if (b.x <= x <= b.x + BLOCK_W and
                b.y <= y <= b.y + BLOCK_H):
                return b
        return None

    def _stream_under_cursor(self, mx, my):
        """mx, my en coords del MODELO."""
        cx, cy = self._sc(mx), self._sc(my)
        items = self.canvas.find_closest(cx, cy, halo=4)
        if not items:
            return None
        for item in items:
            for tag in self.canvas.gettags(item):
                if tag.startswith("s") and tag[1:].isdigit():
                    sid = int(tag[1:])
                    s = self.fs.streams.get(sid)
                    if s is not None:
                        bbox = self.canvas.bbox(item)
                        if bbox and bbox[0] - 6 <= cx <= bbox[2] + 6 and bbox[1] - 6 <= cy <= bbox[3] + 6:
                            return s
        return None

    def _on_left_click(self, event):
        # space+drag = pan
        if self._panning:
            self.canvas.scan_mark(event.x, event.y)
            self.canvas.configure(cursor="fleur")
            return
        mx, my = self._model_xy(event)
        self.canvas.focus_set()

        # pending connection
        if self._connecting_from is not None:
            b_dst = self._block_under_cursor(mx, my)
            if b_dst is not None:
                self._add_stream(self._connecting_from, b_dst.id)
            self._clear_pending_connection()
            return

        b = self._block_under_cursor(mx, my)
        if b is not None:
            self._select_block(b.id)
            self._drag_block = b.id
            self._drag_offx = mx - b.x
            self._drag_offy = my - b.y
            return

        s = self._stream_under_cursor(mx, my)
        if s is not None:
            self._select_stream(s.id)
            return

        self._deselect_all_visual()
        self.selected_block = None
        self.selected_stream = None
        self._update_properties()

    def _on_left_drag(self, event):
        if self._panning:
            self.canvas.scan_dragto(event.x, event.y, gain=1)
            return
        if self._drag_block is None:
            return
        mx, my = self._model_xy(event)
        b = self.fs.blocks.get(self._drag_block)
        if b is None:
            return
        nx = round((mx - self._drag_offx) / GRID_STEP) * GRID_STEP
        ny = round((my - self._drag_offy) / GRID_STEP) * GRID_STEP
        nx = max(0, nx)
        ny = max(0, ny)
        dx_c = self._sc(nx - b.x)
        dy_c = self._sc(ny - b.y)
        b.x = nx
        b.y = ny
        for cid in (b.canvas_rect, b.canvas_text, b.canvas_sub):
            if cid is not None:
                self.canvas.move(cid, dx_c, dy_c)
        for s in self.fs.streams.values():
            if s.src == b.id or s.dst == b.id:
                self._refresh_stream(s)

    def _on_left_release(self, event):
        if self._panning:
            self.canvas.configure(cursor="")
        self._drag_block = None

    def _on_right_click(self, event):
        mx, my = self._model_xy(event)
        b = self._block_under_cursor(mx, my)
        if b is None:
            return

        menu = Menu(self.canvas, tearoff=0)
        menu.add_command(label=f"{b.name}", state="disabled")
        menu.add_separator()
        menu.add_command(label="Connect to…",
                         command=lambda: self._start_connection(b.id))
        menu.add_command(label="Edit properties (Double-click)",
                         command=lambda: self._open_block_dialog(b))
        menu.add_command(label="Delete",
                         command=lambda: self._delete_and_refresh_block(b.id))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _on_double_click(self, event):
        mx, my = self._model_xy(event)
        b = self._block_under_cursor(mx, my)
        if b is not None:
            self._open_block_dialog(b)
            return
        s = self._stream_under_cursor(mx, my)
        if s is not None:
            d = StreamEditDialog(self.win, s, self.fs)
            if d.result == "ok":
                self._refresh_stream(s)
                self._update_properties()

    def _open_block_dialog(self, b):
        d = BlockEditDialog(self.win, b)
        if d.result == "ok":
            self._refresh_block_text(b)
            self._update_properties()

    def _delete_and_refresh_block(self, bid):
        self.selected_block = bid
        self.delete_selected()

    def _start_connection(self, bid):
        self._connecting_from = bid
        b = self.fs.blocks[bid]
        self.status_var.set(
            f"Connecting from {b.name}…  click on the destination block (Esc to cancel)"
        )

    def _clear_pending_connection(self):
        self._connecting_from = None
        self._update_status()

    # ==================================================
    # PROPERTIES PANEL
    # ==================================================

    def _update_properties(self):
        if self.selected_block is not None:
            b = self.fs.blocks[self.selected_block]
            spec = eq.EQUIPMENT_DATA.get(b.eq_type, {})

            ins = [s for s in self.fs.streams.values() if s.dst == b.id]
            outs = [s for s in self.fs.streams.values() if s.src == b.id]
            in_total  = sum(s.mass_flow for s in ins)
            out_total = sum(s.mass_flow for s in outs)
            bal = "(open source/sink)"
            if ins and outs:
                diff = abs(in_total - out_total)
                rel  = diff / max(in_total, out_total, 1e-9)
                if rel < 0.005:
                    bal = "✓ closed"
                else:
                    bal = f"✗ {diff:g} tm/yr ({rel*100:.1f}%)"

            txt = (
                f"BLOCK  {b.name}\n"
                f"Type   {b.eq_type}\n"
                f"Cat.   {spec.get('categoria', '?')}\n"
                f"S      {b.S:g} {spec.get('S_unit', '?')}\n"
                f"n      {b.n}\n"
                f"Range  [{spec.get('S_min', '?')} … {spec.get('S_max', '?')}]\n\n"
                f"Streams in:  {len(ins)}  ({in_total:g} tm/yr)\n"
                f"Streams out: {len(outs)} ({out_total:g} tm/yr)\n"
                f"Mass balance: {bal}"
            )
            self.prop_var.set(txt)
            return

        if self.selected_stream is not None:
            s = self.fs.streams[self.selected_stream]
            src = self.fs.blocks[s.src].name
            dst = self.fs.blocks[s.dst].name
            self.prop_var.set(
                f"STREAM  {s.name}\n"
                f"From    {src}\n"
                f"To      {dst}\n"
                f"Role    {s.role}\n"
                f"Mass    {s.mass_flow:g} tm/yr"
            )
            return

        self.prop_var.set(
            "(nothing selected)\n\n"
            "Click on a block or stream to see its properties.\n"
            "Right-click a block → Connect to… to draw arrows."
        )

    def _update_status(self):
        nb = len(self.fs.blocks)
        ns = len(self.fs.streams)
        if self._connecting_from is None:
            self.status_var.set(f"{nb} blocks · {ns} streams")

    # ==================================================
    # COMPUTE / APPLY
    # ==================================================

    def compute(self):
        if not self.fs.blocks:
            messagebox.showinfo("Compute", "Add at least one equipment block first.")
            return

        equipos = [
            {"nombre": b.eq_type, "S": b.S, "n": b.n}
            for b in self.fs.blocks.values()
        ]

        # tomar plant type y CEPCI year via prompts simples
        # (en una v2 estos serían parte de la UI persistente)
        from tkinter.simpledialog import askstring
        plant_type = askstring(
            "Plant type",
            "Plant type:\n  Fluid processing (default)\n  Solid-fluid processing\n  Solid processing",
            initialvalue="Fluid processing",
        )
        if not plant_type:
            return
        if plant_type not in eq.LANG_FACTORS:
            messagebox.showerror("Invalid", f"Unknown plant type: {plant_type}")
            return

        year_str = askstring("Target year (CEPCI)",
                             "Target year:", initialvalue="2026")
        try:
            year = int(year_str)
        except (TypeError, ValueError):
            return

        try:
            res = eq.lang_fci(equipos, plant_type=plant_type, year_target=year)
        except ValueError as e:
            messagebox.showerror("Compute error", str(e))
            return

        # mass balance global por bloque
        warnings_mb = []
        for b in self.fs.blocks.values():
            ins  = [s for s in self.fs.streams.values() if s.dst == b.id]
            outs = [s for s in self.fs.streams.values() if s.src == b.id]
            if not ins or not outs:
                continue  # source or sink — sin balance esperado
            in_t  = sum(s.mass_flow for s in ins)
            out_t = sum(s.mass_flow for s in outs)
            diff  = abs(in_t - out_t)
            rel   = diff / max(in_t, out_t, 1e-9)
            if rel >= 0.005:
                warnings_mb.append(
                    f"{b.name}: in={in_t:g}, out={out_t:g}, Δ={diff:g} tm/yr ({rel*100:.1f}%)"
                )

        # ISBL implícito
        if self.df_capital is not None and not self.df_capital.empty:
            try:
                osbl = float(self.df_capital.iloc[1, 2]) / (100.0 if self.df_capital.iloc[1, 2] > 1 else 1.0)
                eng  = float(self.df_capital.iloc[2, 2]) / (100.0 if self.df_capital.iloc[2, 2] > 1 else 1.0)
                cont = float(self.df_capital.iloc[3, 2]) / (100.0 if self.df_capital.iloc[3, 2] > 1 else 1.0)
                isbl_mm = eq.isbl_implicito(res["FCI_MMUSD"], osbl, eng, cont)
            except Exception:
                isbl_mm = None
        else:
            isbl_mm = None

        # feeds y products (para coupling con análisis económico)
        feeds    = [s for s in self.fs.streams.values() if s.role == "feed"]
        products = [s for s in self.fs.streams.values() if s.role == "product"]
        feed_total    = sum(s.mass_flow for s in feeds)
        product_total = sum(s.mass_flow for s in products)

        # mostrar resultados
        out_lines = [
            f"Plant type:   {plant_type}",
            f"Lang factor:  {res['lang_factor']:.2f}",
            f"Target year:  {res['year_target']}",
            "",
            f"Σ Cp°:   $ {res['sum_Cp']:>14,.0f}",
            f"FCI:     {res['FCI_MMUSD']:>10.2f} MM USD",
        ]
        if isbl_mm is not None:
            out_lines.append(f"ISBL:    {isbl_mm:>10.2f} MM USD  (back-out)")
        elif self.mode == "main":
            # en modo main, ISBL implícito requiere %OSBL/%ENG/%CONT
            # del análisis económico (defaults Turton)
            isbl_mm = eq.isbl_implicito(res["FCI_MMUSD"], 0.30, 0.10, 0.10)
            out_lines.append(f"ISBL:    {isbl_mm:>10.2f} MM USD  (defaults 30/10/10%)")
        else:
            out_lines.append("ISBL:    (need project loaded)")

        if feeds or products:
            out_lines.append("")
            out_lines.append("─ Mass flows ─")
            if products:
                out_lines.append(f"Annual production: {product_total:g} tm/yr  ({len(products)} stream{'s' if len(products)>1 else ''})")
            if feeds:
                out_lines.append(f"Feed total:        {feed_total:g} tm/yr  ({len(feeds)} stream{'s' if len(feeds)>1 else ''})")
                for s in feeds:
                    out_lines.append(f"  · {s.name}: {s.mass_flow:g} tm/yr")

        if res["warnings"]:
            out_lines.append("")
            out_lines.append("⚠ Cp° warnings:")
            out_lines += [f"  · {w}" for w in res["warnings"]]

        if warnings_mb:
            out_lines.append("")
            out_lines.append("⚠ Mass balance:")
            out_lines += [f"  · {w}" for w in warnings_mb]
        elif self.fs.streams:
            out_lines.append("")
            out_lines.append("✓ Mass balance OK on all internal blocks.")

        self.results_var.set("\n".join(out_lines))
        self._last_isbl = isbl_mm
        self._last_feed_total    = feed_total
        self._last_product_total = product_total
        self._last_feeds    = feeds
        self._last_products = products

    def apply_isbl(self):
        if not hasattr(self, "_last_isbl") or self._last_isbl is None:
            messagebox.showinfo("Apply ISBL", "Run Compute first.")
            return
        if self.df_capital is None or self.df_capital.empty:
            messagebox.showinfo(
                "Apply ISBL",
                "Para aplicar el ISBL al análisis, importá o creá un proyecto primero."
            )
            return
        if not messagebox.askyesno(
            "Apply ISBL",
            f"Apply ISBL = {self._last_isbl:.2f} MM USD to the project?"
        ):
            return
        self.df_capital.iat[0, 2] = float(self._last_isbl)
        if self.on_apply is not None:
            self.on_apply()
        messagebox.showinfo("Applied", "ISBL updated in the project.")

    # ==================================================
    # TRANSICIÓN AL ANÁLISIS ECONÓMICO (modo main)
    # ==================================================

    def launch_analysis(self):
        """Modo main: dispara el análisis económico como
        proceso separado, con el ISBL ya inyectado.

        Flujo:
          1. Si no hay Compute previo, lo corre con defaults.
          2. Pide al usuario un .xlsx base (o usa template default).
          3. Lanza:  python ANA.py [--import path.xlsx] [--isbl X]
        """
        import subprocess
        import sys
        import os

        if not self.fs.blocks:
            if not messagebox.askyesno(
                "Sin proceso modelado",
                "El flowsheet está vacío.  "
                "¿Abrir el análisis económico igual?",
            ):
                return
            isbl = None
        else:
            if not hasattr(self, "_last_isbl") or self._last_isbl is None:
                # corremos compute silencioso con defaults
                try:
                    equipos = [
                        {"nombre": b.eq_type, "S": b.S, "n": b.n}
                        for b in self.fs.blocks.values()
                    ]
                    res = eq.lang_fci(equipos, plant_type="Fluid processing", year_target=2026)
                    isbl = eq.isbl_implicito(res["FCI_MMUSD"], 0.30, 0.10, 0.10)
                except ValueError as e:
                    messagebox.showerror("Compute error", str(e))
                    return
            else:
                isbl = self._last_isbl

        # opción de xlsx base
        usar_xlsx = messagebox.askyesnocancel(
            "Análisis económico",
            "¿Usar un .xlsx base existente para el análisis?\n\n"
            "  Sí  → seleccionás el archivo\n"
            "  No  → análisis con template default Turton\n"
            "  Cancel → vuelvo al flowsheet",
        )
        if usar_xlsx is None:
            return

        cmd = [sys.executable, "ANA.py"]
        if usar_xlsx:
            path = filedialog.askopenfilename(
                title="Project xlsx",
                filetypes=[("Excel files", "*.xlsx *.xls")],
            )
            if not path:
                return
            cmd += ["--import", path]

        if isbl is not None:
            cmd += ["--isbl", f"{isbl:.4f}"]

        # nota de feeds/products no auto-inyectados (commit aparte)
        if (getattr(self, "_last_feeds", None) or
            getattr(self, "_last_products", None)):
            extras = []
            if self._last_products:
                extras.append(f"Annual production: {self._last_product_total:g} tm/yr")
            if self._last_feeds:
                extras.append("Feeds:")
                for s in self._last_feeds:
                    extras.append(f"  · {s.name}: {s.mass_flow:g} tm/yr")
            messagebox.showinfo(
                "Datos del flowsheet (copialos a mano)",
                "El ISBL se inyecta automáticamente en el análisis.\n"
                "Estos otros datos del flowsheet quedan disponibles para que "
                "los cargues a mano en el análisis económico:\n\n"
                + "\n".join(extras),
            )

        try:
            cwd = os.path.dirname(os.path.abspath(__file__))
            subprocess.Popen(cmd, cwd=cwd)
        except Exception as e:
            messagebox.showerror("Launch failed", f"{type(e).__name__}: {e}")


# ======================================================
# ENTRY POINT
# ======================================================

def AbrirVentanaFlowsheet(parent, df_capital=None, on_apply=None):
    """Modo legacy: abre el editor como Toplevel hijo del
    análisis económico.  Botón final 'Apply ISBL' actualiza
    df_capital in-place.  Usado desde ANA.py > Tools."""
    top = Toplevel(parent)
    top.transient(parent)
    FlowsheetEditor(top, df_capital=df_capital, on_apply=on_apply, mode="modal")
