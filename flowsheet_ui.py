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
        ttk.Separator(toolbar, orient=VERTICAL).pack(side=LEFT, fill=Y, padx=8, pady=4)
        ttk.Button(toolbar, text="Delete selected (Del)", command=self.delete_selected).pack(side=LEFT, padx=2)
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

        canvas = Canvas(center, bg=CANVAS_BG, highlightthickness=1,
                        highlightbackground="#cccccc")
        canvas.pack(fill=BOTH, expand=True)
        self.canvas = canvas

        canvas.bind("<Button-1>",       self._on_left_click)
        canvas.bind("<B1-Motion>",      self._on_left_drag)
        canvas.bind("<ButtonRelease-1>",self._on_left_release)
        canvas.bind("<Button-3>",       self._on_right_click)
        canvas.bind("<Double-1>",       self._on_double_click)

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
        self.canvas.delete("all")
        self._draw_grid()
        for b in self.fs.blocks.values():
            self._render_block(b)
        for s in self.fs.streams.values():
            self._render_stream(s)
        self.selected_block = None
        self.selected_stream = None
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

        x0 = b.x
        y0 = b.y
        x1 = x0 + BLOCK_W
        y1 = y0 + BLOCK_H

        b.canvas_rect = self.canvas.create_rectangle(
            x0, y0, x1, y1,
            fill=BLOCK_FILL, outline=BLOCK_BORDER, width=2,
            tags=("block", f"b{b.id}"),
        )
        b.canvas_text = self.canvas.create_text(
            (x0 + x1) / 2, y0 + 18,
            text=b.name, fill=BLOCK_TEXT, font=("Segoe UI", 10, "bold"),
            tags=("block", f"b{b.id}"),
        )
        b.canvas_sub = self.canvas.create_text(
            (x0 + x1) / 2, y0 + 40,
            text=f"{cat}\nS = {b.S:g} {unit}" + (f"  × {b.n}" if b.n > 1 else ""),
            fill=BLOCK_SUB, font=("Segoe UI", 8), justify="center",
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

    def _render_stream(self, s):
        b_src = self.fs.blocks[s.src]
        b_dst = self.fs.blocks[s.dst]

        x1, y1 = self._block_anchor(b_src, "right")
        x2, y2 = self._block_anchor(b_dst, "left")

        color = STREAM_ROLE_COLORS.get(s.role, STREAM_COLOR)
        s.canvas_line = self.canvas.create_line(
            x1, y1, x2, y2,
            fill=color, width=2, arrow="last", arrowshape=(12, 14, 5),
            tags=("stream", f"s{s.id}"),
        )
        role_tag = ""
        if s.role == "feed":
            role_tag = " [feed]"
        elif s.role == "product":
            role_tag = " [product]"
        s.canvas_label = self.canvas.create_text(
            (x1 + x2) / 2, (y1 + y2) / 2 - 10,
            text=s.name + role_tag + (f"  {s.mass_flow:g} tm/yr" if s.mass_flow else ""),
            fill="#444", font=("Segoe UI", 8),
            tags=("stream", f"s{s.id}"),
        )

    def _refresh_stream(self, s):
        b_src = self.fs.blocks.get(s.src)
        b_dst = self.fs.blocks.get(s.dst)
        if b_src is None or b_dst is None:
            return
        x1, y1 = self._block_anchor(b_src, "right")
        x2, y2 = self._block_anchor(b_dst, "left")
        if s.canvas_line is not None:
            self.canvas.coords(s.canvas_line, x1, y1, x2, y2)
            color = STREAM_ROLE_COLORS.get(s.role, STREAM_COLOR)
            self.canvas.itemconfigure(s.canvas_line, fill=color)
        if s.canvas_label is not None:
            self.canvas.coords(s.canvas_label, (x1 + x2) / 2, (y1 + y2) / 2 - 10)
            role_tag = ""
            if s.role == "feed":
                role_tag = " [feed]"
            elif s.role == "product":
                role_tag = " [product]"
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
        w = self.canvas.winfo_reqwidth() or 800
        h = self.canvas.winfo_reqheight() or 600
        # dibujamos grid grande para que no se note el border
        for x in range(0, 2000, GRID_STEP):
            self.canvas.create_line(x, 0, x, 1500, fill=GRID_COLOR, tags=("grid",))
        for y in range(0, 1500, GRID_STEP):
            self.canvas.create_line(0, y, 2000, y, fill=GRID_COLOR, tags=("grid",))
        self.canvas.tag_lower("grid")

    def _block_under_cursor(self, x, y):
        for b in self.fs.blocks.values():
            if (b.x <= x <= b.x + BLOCK_W and
                b.y <= y <= b.y + BLOCK_H):
                return b
        return None

    def _stream_under_cursor(self, x, y):
        # buscar elementos cercanos al click
        items = self.canvas.find_closest(x, y, halo=4)
        if not items:
            return None
        for item in items:
            for tag in self.canvas.gettags(item):
                if tag.startswith("s") and tag[1:].isdigit():
                    sid = int(tag[1:])
                    s = self.fs.streams.get(sid)
                    if s is not None:
                        # confirm click realmente sobre la línea
                        bbox = self.canvas.bbox(item)
                        if bbox and bbox[0] - 6 <= x <= bbox[2] + 6 and bbox[1] - 6 <= y <= bbox[3] + 6:
                            return s
        return None

    def _on_left_click(self, event):
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

        # pending connection: si hay origen, este click es el destino
        if self._connecting_from is not None:
            b_dst = self._block_under_cursor(x, y)
            if b_dst is not None:
                self._add_stream(self._connecting_from, b_dst.id)
            self._clear_pending_connection()
            return

        b = self._block_under_cursor(x, y)
        if b is not None:
            self._select_block(b.id)
            self._drag_block = b.id
            self._drag_offx = x - b.x
            self._drag_offy = y - b.y
            return

        s = self._stream_under_cursor(x, y)
        if s is not None:
            self._select_stream(s.id)
            return

        # click en vacío: deselect
        self._deselect_all_visual()
        self.selected_block = None
        self.selected_stream = None
        self._update_properties()

    def _on_left_drag(self, event):
        if self._drag_block is None:
            return
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        b = self.fs.blocks.get(self._drag_block)
        if b is None:
            return
        # snap a grid
        nx = round((x - self._drag_offx) / GRID_STEP) * GRID_STEP
        ny = round((y - self._drag_offy) / GRID_STEP) * GRID_STEP
        nx = max(0, nx)
        ny = max(0, ny)
        dx = nx - b.x
        dy = ny - b.y
        b.x = nx
        b.y = ny
        for cid in (b.canvas_rect, b.canvas_text, b.canvas_sub):
            if cid is not None:
                self.canvas.move(cid, dx, dy)
        # refrescar streams conectados
        for s in self.fs.streams.values():
            if s.src == b.id or s.dst == b.id:
                self._refresh_stream(s)

    def _on_left_release(self, event):
        self._drag_block = None

    def _on_right_click(self, event):
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        b = self._block_under_cursor(x, y)
        if b is None:
            return

        # context menu
        from tkinter import Menu
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
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        b = self._block_under_cursor(x, y)
        if b is not None:
            self._open_block_dialog(b)
            return
        s = self._stream_under_cursor(x, y)
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
