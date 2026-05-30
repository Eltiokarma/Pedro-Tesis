"""
ui_scaling.py — Auto-ajuste de ventanas a CUALQUIER tamaño de pantalla.

Las ventanas de la app traían tamaños hardcodeados (1400×820, 1280×800,
720×560) sin contemplar la resolución real del monitor.  En laptops o
pantallas chicas (p.ej. 1366×768, o monitores con escala 125/150 %) la
ventana quedaba más grande que el escritorio y parte se salía de cuadro.

Este módulo centraliza dos helpers:

  · enable_high_dpi()  — debe llamarse ANTES de crear la QApplication.
        Configura el redondeo de escala High-DPI a PassThrough para que
        en monitores con escala fraccionaria (125 %, 150 %) la UI use el
        factor exacto en vez de redondear a entero (que agranda todo).

  · fit_to_screen(win, pref_w, pref_h, frac=0.9) — clampa el tamaño
        deseado al `frac` del área disponible del monitor donde está la
        ventana y la centra.  En pantallas grandes mantiene el tamaño
        preferido; en chicas lo reduce para que SIEMPRE entre.

Ambos son defensivos (try/except): en entornos headless / sin pantalla
no rompen nada.
"""
from __future__ import annotations


def enable_high_dpi() -> None:
    """Configura High-DPI rounding ANTES de instanciar QApplication.

    En Qt6 el escalado High-DPI ya está activo por defecto; lo único que
    falta fijar es la política de redondeo, que debe setearse antes de
    crear la QApplication para tener efecto.
    """
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QGuiApplication
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    except Exception:
        pass


def _available_geometry(win):
    """QRect del área utilizable (sin barra de tareas) del monitor de la
    ventana, con fallback al monitor primario."""
    from PySide6.QtGui import QGuiApplication
    screen = None
    try:
        screen = win.screen()
    except Exception:
        screen = None
    if screen is None:
        screen = QGuiApplication.primaryScreen()
    return screen.availableGeometry() if screen else None


def fit_to_screen(win, pref_w: int, pref_h: int,
                  frac: float = 0.9, center: bool = True) -> None:
    """Redimensiona `win` al menor entre (pref_w, pref_h) y `frac` del
    área disponible del monitor, y la centra.

    Args:
        win:    QWidget / QMainWindow.
        pref_w: ancho preferido (el que tendría en una pantalla grande).
        pref_h: alto preferido.
        frac:   fracción máxima del área disponible a ocupar (0–1).
        center: si True, centra la ventana en el monitor.
    """
    try:
        avail = _available_geometry(win)
        if avail is None:
            win.resize(pref_w, pref_h)
            return
        max_w = int(avail.width()  * frac)
        max_h = int(avail.height() * frac)
        w = max(320, min(pref_w, max_w))
        h = max(240, min(pref_h, max_h))
        win.resize(w, h)
        if center:
            x = avail.x() + (avail.width()  - w) // 2
            y = avail.y() + (avail.height() - h) // 2
            win.move(x, y)
    except Exception:
        try:
            win.resize(pref_w, pref_h)
        except Exception:
            pass
