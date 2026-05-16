"""
THERMO_DB — base de datos termodinámica rigurosa.

Carga lazy desde data/thermo_db.md (Antoine + DIPPR Cp + ΔH_f) y
expone una API estructurada.  La primera llamada parsea el archivo
(~100ms para 108 componentes); las siguientes leen del cache.

Capas cubiertas:
  · Capa 1 — Antoine: log10(P_sat/kPa) = A - B/(T_°C + C)
  · Capa 2a — Cp gas DIPPR-100: J/(kmol·K), polinomio cuártico en T_K
  · Capa 2b — Cp líquido DIPPR-100: idem
  · Capa 3 — ΔH_f° a 298.15 K, kJ/mol (gas/liq)

Funciones derivadas:
  · ΔH_vap(T) via Clausius-Clapeyron desde Antoine + Tb (no necesita
    valor tabulado; lo deriva).
  · Bubble point T de mezclas (vía Antoine de los componentes).

API:
  get(name)                      → ComponentThermo | None
  cp_kJ_kg_K(name, T_C, phase)   → float (compat con solver actual)
  cp_mix_kJ_kg_K(comp, T_C, ph)  → idem para mezclas (weighted avg)
  vapor_pressure_kPa(name, T_C)  → float
  bubble_T_C(comp, P_kPa=101.3)  → float
  delta_h_vap_kJ_kg(name, T_C)   → float
  has(name)                      → bool

Naming: los nombres del .md (e.g., 'Methanol') se normalizan a
lowercase con '_' (e.g., 'methanol') para coincidir con las claves
de components.py (catálogo viejo) y de los streams en flowsheet_model.
"""

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

R_GAS = 8.314         # J/(mol·K)
T_REF_K = 298.15      # K
P_ATM_KPA = 101.325


@dataclass
class ComponentThermo:
    name:    str                   # canónico: lowercase + underscores
    label:   str                   # del .md, ej "Methanol (CH4O)"
    cas:     str = ""
    formula: str = ""
    mw:      float = 0.0           # g/mol
    tb_c:    float = 0.0           # ebullición a 1 atm (°C)
    tc_c:    Optional[float] = None
    pc_bar:  Optional[float] = None
    omega:   Optional[float] = None
    # Antoine: log10(P_sat/kPa) = A - B/(T_°C + C)
    antoine_A: Optional[float] = None
    antoine_B: Optional[float] = None
    antoine_C: Optional[float] = None
    antoine_range_C: Tuple[float, float] = (0, 0)
    # Cp DIPPR-100: J/(kmol·K), T en K
    cp_gas_coefs:   Optional[Tuple[float, float, float, float, float]] = None
    cp_gas_range_K: Tuple[float, float] = (0, 0)
    cp_liq_coefs:   Optional[Tuple[float, float, float, float, float]] = None
    cp_liq_range_K: Tuple[float, float] = (0, 0)
    # ΔH_f° (kJ/mol)
    dh_f_gas_kJ_mol: Optional[float] = None
    dh_f_liq_kJ_mol: Optional[float] = None
    # Calidad de la data
    quality: str = ""              # 'NIST', 'DIPPR', 'FIT', 'Joback', 'estim'

    # ---- Métodos ----
    def cp_J_mol_K(self, T_K: float, phase: str = "liquid") -> Optional[float]:
        """Cp en J/(mol·K) a T en K para la fase indicada.
        Devuelve None si no hay coeficientes para esa fase."""
        if phase in ("vapor", "gas"):
            coefs = self.cp_gas_coefs
        else:
            coefs = self.cp_liq_coefs
        if coefs is None:
            return None
        c1, c2, c3, c4, c5 = coefs
        cp_kmol = c1 + c2*T_K + c3*T_K**2 + c4*T_K**3 + c5*T_K**4
        return cp_kmol / 1000.0   # J/(kmol·K) → J/(mol·K)

    def cp_kJ_kg_K(self, T_C: float, phase: str = "liquid") -> Optional[float]:
        """Cp en kJ/(kg·K) a T en °C — compat con solver."""
        if self.mw <= 0:
            return None
        T_K = T_C + 273.15
        cp_J_mol_K = self.cp_J_mol_K(T_K, phase)
        if cp_J_mol_K is None:
            return None
        # J/(mol·K) ÷ MW(g/mol) = J/(g·K) = kJ/(kg·K) (mismas unidades)
        return cp_J_mol_K / self.mw

    def vapor_pressure_kPa(self, T_C: float) -> Optional[float]:
        """Presión de vapor a T en °C, en kPa."""
        if self.antoine_A is None:
            return None
        denom = T_C + self.antoine_C
        if abs(denom) < 1e-9:
            return None
        log10_P = self.antoine_A - self.antoine_B / denom
        return 10.0 ** log10_P

    def delta_h_vap_kJ_mol(self, T_C: float) -> Optional[float]:
        """ΔH_vap a T (°C) via Clausius-Clapeyron desde Antoine.
        d(ln P)/dT = ΔH_vap / (R · T²)
        de Antoine: d(log10 P)/dT = B / (T_°C + C)²
        d(ln P)/dT = ln(10) · B / (T_°C + C)²
        ⇒ ΔH_vap = R · T_K² · ln(10) · B / (T_°C + C)²
        """
        if self.antoine_B is None or self.antoine_C is None:
            return None
        T_K = T_C + 273.15
        denom = (T_C + self.antoine_C) ** 2
        if denom < 1e-9:
            return None
        # R en J/(mol·K), T_K en K, B en °C-units → ΔH en J/mol
        dh_J_mol = R_GAS * T_K * T_K * math.log(10) * self.antoine_B / denom
        return dh_J_mol / 1000.0  # → kJ/mol

    def delta_h_vap_kJ_kg(self, T_C: float) -> Optional[float]:
        """ΔH_vap a T en °C, kJ/kg."""
        if self.mw <= 0:
            return None
        dh_kJ_mol = self.delta_h_vap_kJ_mol(T_C)
        if dh_kJ_mol is None:
            return None
        # kJ/mol ÷ MW(g/mol) = kJ/g = kJ/kg (el factor 1000 cancela)
        return dh_kJ_mol * 1000.0 / self.mw


# ======================================================
# PARSER DEL .md
# ======================================================

_DB: Optional[Dict[str, ComponentThermo]] = None
_DB_PATH = Path(__file__).parent / "data" / "thermo_db.md"


def _normalize_name(label: str) -> str:
    """'Methanol (CH4O)' → 'methanol'.  'o-Xylene' → 'xylene'."""
    base = label.split("(")[0].strip()
    base = base.lower().replace("-", " ")
    base = base.replace("o ", "")     # 'o xylene' → 'xylene'
    base = base.replace("n ", "")     # 'n hexane' → 'hexane'
    base = base.replace("iso", "iso") # mantener
    base = re.sub(r"\s+", "_", base.strip())
    return base


def _try_float(s: str) -> Optional[float]:
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _parse_db() -> Dict[str, ComponentThermo]:
    """Parsea data/thermo_db.md y devuelve dict {name: ComponentThermo}."""
    if not _DB_PATH.is_file():
        return {}
    text = _DB_PATH.read_text(encoding="utf-8")

    # Splittear por '## ' (componentes top-level).  Saltar 'Convenciones'
    # y secciones helpers al final ('## 1. ΔH_vap...', etc).
    sections = re.split(r"^## ", text, flags=re.MULTILINE)
    out: Dict[str, ComponentThermo] = {}

    for sec in sections[1:]:   # skip prefacio
        head = sec.split("\n", 1)[0].strip()
        # filtrar headers que no son componentes
        if head.startswith("Convenciones") or re.match(r"^\d+\.\s", head):
            continue
        if "Limitaciones" in head or "Ejemplo" in head:
            continue
        # nombre canónico
        name = _normalize_name(head)
        if not name:
            continue

        body = sec
        comp = ComponentThermo(name=name, label=head)

        # IDs
        m = re.search(r"CAS:\s*([A-Za-z0-9\-]+)", body)
        if m: comp.cas = m.group(1)
        m = re.search(r"Formula:\s*(\S+)", body)
        if m: comp.formula = m.group(1)
        m = re.search(r"MW:\s*([\d.]+)", body)
        if m: comp.mw = float(m.group(1))
        m = re.search(r"Tb \(1 atm\):\s*([\-\d.]+)", body)
        if m: comp.tb_c = float(m.group(1))
        m = re.search(r"Tc:\s*([\-\d.]+)", body)
        if m: comp.tc_c = float(m.group(1))
        m = re.search(r"Pc:\s*([\d.]+)", body)
        if m: comp.pc_bar = float(m.group(1))
        m = re.search(r"omega:\s*([\-\d.]+)", body)
        if m: comp.omega = float(m.group(1))

        # Antoine
        m_block = re.search(r"### Capa 1.*?(?=###|---|\Z)", body, re.DOTALL)
        if m_block:
            blk = m_block.group()
            mA = re.search(r"^A\s*=\s*([\-\de\.+]+)", blk, re.MULTILINE)
            mB = re.search(r"^B\s*=\s*([\-\de\.+]+)", blk, re.MULTILINE)
            mC = re.search(r"^C\s*=\s*([\-\de\.+]+)", blk, re.MULTILINE)
            mR = re.search(r"Range:\s*([\-\d.]+)\s*to\s*([\-\d.]+)\s*°?C", blk)
            if mA: comp.antoine_A = float(mA.group(1))
            if mB: comp.antoine_B = float(mB.group(1))
            if mC: comp.antoine_C = float(mC.group(1))
            if mR: comp.antoine_range_C = (float(mR.group(1)), float(mR.group(2)))

        # Cp gas (Capa 2a)
        m_block = re.search(r"### Capa 2a.*?(?=###|---|\Z)", body, re.DOTALL)
        if m_block:
            blk = m_block.group()
            coefs = []
            for k in ("C1", "C2", "C3", "C4", "C5"):
                m = re.search(rf"^{k}\s*=\s*([\-\de\.+]+)", blk, re.MULTILINE)
                coefs.append(float(m.group(1)) if m else 0.0)
            comp.cp_gas_coefs = tuple(coefs)
            mR = re.search(r"Range:\s*([\-\d.]+)\s*to\s*([\-\d.]+)\s*K", blk)
            if mR: comp.cp_gas_range_K = (float(mR.group(1)), float(mR.group(2)))

        # Cp liq (Capa 2b)
        m_block = re.search(r"### Capa 2b.*?(?=###|---|\Z)", body, re.DOTALL)
        if m_block:
            blk = m_block.group()
            coefs = []
            for k in ("C1", "C2", "C3", "C4", "C5"):
                m = re.search(rf"^{k}\s*=\s*([\-\de\.+]+)", blk, re.MULTILINE)
                coefs.append(float(m.group(1)) if m else 0.0)
            comp.cp_liq_coefs = tuple(coefs)
            mR = re.search(r"Range:\s*([\-\d.]+)\s*to\s*([\-\d.]+)\s*K", blk)
            if mR: comp.cp_liq_range_K = (float(mR.group(1)), float(mR.group(2)))

        # ΔH_f
        m = re.search(r"dH_f_gas_298K\s*=\s*([\-\d.]+)", body)
        if m: comp.dh_f_gas_kJ_mol = float(m.group(1))
        m = re.search(r"dH_f_liq_298K\s*=\s*([\-\d.]+)", body)
        if m: comp.dh_f_liq_kJ_mol = float(m.group(1))

        out[name] = comp

    return out


def _ensure_loaded() -> Dict[str, ComponentThermo]:
    global _DB
    if _DB is None:
        _DB = _parse_db()
    return _DB


# ======================================================
# API PÚBLICA
# ======================================================

def get(name: str) -> Optional[ComponentThermo]:
    """Devuelve el ComponentThermo por nombre (case-insensitive,
    underscore-tolerant).  None si no existe."""
    db = _ensure_loaded()
    if name in db:
        return db[name]
    # fallback: lowercase + underscores
    norm = name.lower().replace("-", "_").replace(" ", "_")
    return db.get(norm)


def has(name: str) -> bool:
    return get(name) is not None


def list_names() -> List[str]:
    return sorted(_ensure_loaded().keys())


def cp_kJ_kg_K(name: str, T_C: float, phase: str = "liquid") -> Optional[float]:
    """Cp del componente puro a T (°C) en kJ/(kg·K)."""
    c = get(name)
    if c is None:
        return None
    return c.cp_kJ_kg_K(T_C, phase)


def cp_mix_kJ_kg_K(comp_dict: Dict[str, float], T_C: float,
                    phase: str = "liquid") -> float:
    """Cp de la mezcla ponderado por fracción másica a T (°C)."""
    if not comp_dict:
        return 0.0
    cp = 0.0
    for name, w in comp_dict.items():
        if w <= 0:
            continue
        c = get(name)
        if c is None:
            continue
        cp_pure = c.cp_kJ_kg_K(T_C, phase)
        if cp_pure is None:
            continue
        cp += w * cp_pure
    return cp


def vapor_pressure_kPa(name: str, T_C: float) -> Optional[float]:
    c = get(name)
    if c is None:
        return None
    return c.vapor_pressure_kPa(T_C)


def vapor_pressure_bar(name: str, T_C: float) -> Optional[float]:
    p = vapor_pressure_kPa(name, T_C)
    return None if p is None else p / 100.0


def delta_h_vap_kJ_kg(name: str, T_C: float) -> Optional[float]:
    """ΔH_vap del componente a T (°C) en kJ/kg, via Clausius-Clapeyron
    desde Antoine."""
    c = get(name)
    if c is None:
        return None
    return c.delta_h_vap_kJ_kg(T_C)


def delta_h_vap_mix_kJ_kg(comp_dict: Dict[str, float], T_C: float) -> float:
    """ΔH_vap de mezcla, ponderado por fracción másica."""
    if not comp_dict:
        return 0.0
    dh = 0.0
    for name, w in comp_dict.items():
        if w <= 0: continue
        v = delta_h_vap_kJ_kg(name, T_C)
        if v is not None:
            dh += w * v
    return dh


def bubble_T_C(comp_dict: Dict[str, float], P_kPa: float = P_ATM_KPA,
                T_init_C: float = 50.0, max_iter: int = 50,
                tol: float = 0.01) -> Optional[float]:
    """Punto de burbuja de la mezcla a P (kPa) — bisección.

    Definición: T donde Σᵢ xᵢ · P_sat,ᵢ(T) = P (Raoult ideal).
    Las xᵢ acá son fracciones MÁSICAS (aproximación; estrictamente
    debería ser molar — para comparación rápida, la diferencia es
    chica para mezclas similares).

    Devuelve T en °C o None si no encuentra (componentes sin Antoine).
    """
    if not comp_dict:
        return None
    # convertir a molar (aproximadamente)
    total_mol = 0.0
    mol_frac = {}
    for name, w in comp_dict.items():
        c = get(name)
        if c is None or c.mw <= 0 or c.antoine_A is None:
            continue
        m = w / c.mw
        mol_frac[name] = m
        total_mol += m
    if total_mol <= 0:
        return None
    for n in mol_frac:
        mol_frac[n] /= total_mol

    def _residual(T_C: float) -> float:
        s = 0.0
        for n, x in mol_frac.items():
            p = vapor_pressure_kPa(n, T_C)
            if p is None: continue
            s += x * p
        return s - P_kPa

    # bisección
    lo, hi = -50.0, 500.0
    f_lo = _residual(lo)
    f_hi = _residual(hi)
    if f_lo * f_hi > 0:
        return None  # no hay raíz en el rango
    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        f_mid = _residual(mid)
        if abs(f_mid) < tol * P_kPa:
            return mid
        if f_lo * f_mid < 0:
            hi = mid
            f_hi = f_mid
        else:
            lo = mid
            f_lo = f_mid
    return (lo + hi) / 2.0
