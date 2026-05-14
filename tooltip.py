# ======================================================
# TOOLTIP — burbujas flotantes sobre widgets Tkinter
# ======================================================
# Uso básico:
#
#     from tooltip import Tooltip
#     Tooltip(my_entry, "Descripción del campo.")
#
# O en lote desde un dict (más limpio cuando hay muchos):
#
#     adjuntar_tooltips({
#         entry_fc:       "Construction schedule...",
#         entry_vcop:     "Capacity ramp-up...",
#     })
# ======================================================

from tkinter import Toplevel, Label


class Tooltip:
    """Burbuja flotante amarilla suave que aparece al hover.

    Aparece con un delay configurable (default 450 ms) para
    no molestar cuando el cursor solo pasa por arriba.
    """

    BG = "#fff8d6"
    FG = "#202020"
    BORDER = "#9c9c9c"

    def __init__(self, widget, text, delay=450, wraplength=320):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.wraplength = wraplength
        self._tip = None
        self._after_id = None

        widget.bind("<Enter>",      self._on_enter)
        widget.bind("<Leave>",      self._on_leave)
        widget.bind("<ButtonPress>", self._on_leave)
        widget.bind("<Motion>",     self._on_motion)

    # --------------------------------------------------

    def _on_enter(self, _event=None):
        self._schedule()

    def _on_leave(self, _event=None):
        self._cancel()
        self._hide()

    def _on_motion(self, _event=None):
        # reset del timer para evitar que aparezca mientras
        # el cursor se mueve continuamente
        if self._tip is None:
            self._cancel()
            self._schedule()

    def _schedule(self):
        self._cancel()
        self._after_id = self.widget.after(self.delay, self._show)

    def _cancel(self):
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _show(self):
        if self._tip is not None or not self.text:
            return

        # Posición: a la derecha-abajo del widget
        x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6

        tw = Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        try:
            # En algunos WMs, transient evita robo de foco
            tw.wm_attributes("-topmost", True)
        except Exception:
            pass
        tw.wm_geometry(f"+{x}+{y}")

        Label(
            tw,
            text=self.text,
            background=self.BG,
            foreground=self.FG,
            highlightbackground=self.BORDER,
            highlightthickness=1,
            font=("Segoe UI", 9),
            justify="left",
            wraplength=self.wraplength,
            padx=10,
            pady=6,
        ).pack()

        self._tip = tw

    def _hide(self):
        if self._tip is not None:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None

    def actualizar(self, nuevo_texto):
        """Permite cambiar el texto del tooltip en runtime."""
        self.text = nuevo_texto


# ======================================================
# UTILIDAD: adjuntar muchos tooltips a la vez
# ======================================================

def adjuntar_tooltips(mapping):
    """Recibe un dict {widget: texto} y le pega Tooltip a
    cada widget.  Devuelve lista de los Tooltip creados
    (por si querés mantener referencia)."""
    tips = []
    for widget, texto in mapping.items():
        if widget is None or texto is None:
            continue
        tips.append(Tooltip(widget, texto))
    return tips
