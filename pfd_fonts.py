"""
PFD FONTS — carga las fuentes IBM Plex desde el directorio fonts/.

Las fuentes IBM Plex son MIT/OFL y se distribuyen junto con el código
(carpeta `fonts/`).  Este módulo las registra en Qt al iniciar la app
y expone los nombres de familia para usar en QFont.

Uso típico:
    import pfd_fonts
    pfd_fonts.load_all()    # llamar UNA vez al inicio (después de QApplication)

    f = QFont(pfd_fonts.SANS, 17, QFont.Bold)   # tag de equipo
    f = QFont(pfd_fonts.MONO, 11)               # specs, flujos

Si Qt no encuentra los archivos o no está instalado, log() y vuelve a
las fuentes del sistema sin romper.
"""

import os
from pathlib import Path
from typing import List

SANS = "IBM Plex Sans"
MONO = "IBM Plex Mono"

_FONT_FILES = [
    "IBMPlexSans-Regular.ttf",
    "IBMPlexSans-Bold.ttf",
    "IBMPlexMono-Regular.ttf",
    "IBMPlexMono-Medium.ttf",
]

_loaded = False


def fonts_dir() -> Path:
    return Path(__file__).parent / "fonts"


def load_all() -> List[int]:
    """Registra todas las fuentes en QFontDatabase. Devuelve la lista
    de IDs cargados (vacía si Qt no está disponible o falló todo).

    Idempotente: llamadas repetidas no recargan.
    """
    global _loaded
    if _loaded:
        return []
    try:
        from PySide6.QtGui import QFontDatabase
    except ImportError:
        return []

    ids: List[int] = []
    fdir = fonts_dir()
    for fname in _FONT_FILES:
        fpath = fdir / fname
        if not fpath.is_file():
            continue
        fid = QFontDatabase.addApplicationFont(str(fpath))
        if fid >= 0:
            ids.append(fid)

    _loaded = True
    return ids


def available() -> bool:
    """True si las fuentes están instaladas y se pueden usar."""
    try:
        from PySide6.QtGui import QFontDatabase
    except ImportError:
        return False
    families = QFontDatabase.families()
    return SANS in families and MONO in families
