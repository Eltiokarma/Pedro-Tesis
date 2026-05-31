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
    # Override de densidad (Capa 7) — si vienen de la segunda db de
    # densidades experimentales, calibran Spencer-Danner-Yamada para
    # matchear un punto experimental.
    rho_ref_kg_m3: Optional[float] = None   # densidad experimental
    rho_ref_T_C:   Optional[float] = None   # T del punto experimental
    z_ra_override: Optional[float] = None   # Z_RA pre-calibrado

    # ---- Capa 4b (predictor) — campos cheminformaticos ----
    # SMILES canonico para el predictor. Si vacio, predictor cae a
    # lookup manual de grupos (functional_groups_db.md).
    smiles: str = ""
    # Grupos funcionales detectados (lista de strings, populada por
    # functional_groups.detect_groups() lazy on demand).
    functional_groups: List[str] = field(default_factory=list)
    # Procedencia del compuesto.
    #   'experimental' — del thermo_db curado (NIST/DIPPR/FIT)
    #   'estimated'    — estimado via Joback/Benson
    #   'predicted'    — producto generado por un template del predictor
    origin: str = "experimental"
    # Si origin in ('estimated', 'predicted'): cual metodo lo estimo.
    estimation_method: str = ""        # 'joback', 'benson', 'auto_combustion'
    # Bandas de incertidumbre por campo, en su escala natural.
    # Ej: {'dh_f': 12.0, 'cp_gas_298': 5.0} (en kJ/mol y J/(mol·K)).
    estimation_uncertainty: Dict[str, float] = field(default_factory=dict)
    # Si origin == 'predicted': el template T01..T20 que lo genero.
    parent_transformation: Optional[str] = None

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
        # Acotar el exponente: a T muy fuera del rango Antoine el valor
        # diverge y 10**log10_P desborda float (OverflowError).  Clamp a un
        # rango físico amplio (1e-30 .. 1e30 kPa) — no afecta valores válidos.
        if log10_P > 30.0:
            return 1e30
        if log10_P < -30.0:
            return 0.0
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

    # --- Capa 7: densidad líquida (Spencer-Danner-Rackett) ---
    def density_kg_m3(self, T_C: float) -> Optional[float]:
        """Densidad del líquido saturado a T (°C), en kg/m³.

        Ecuación de Spencer-Danner (Rackett modificada):
            V_sat = (R·Tc/Pc) · Z_RA ^ [1 + (1 - Tr)^(2/7)]
            ρ_L  = MW / V_sat
        Z_RA = 0.29056 - 0.08775·ω   (Spencer-Danner)

        Requiere Tc, Pc, ω, MW. Devuelve None si falta algo.

        Precisión típica:
          · Hidrocarburos no polares: 1-3% error.
          · Polares ligeros (alcoholes): 3-7% error.
          · Agua / ácidos / aminas (puente H fuerte): hasta 15% error
            — Rackett subestima por no capturar bien el puente H.

        Para T > Tc, devuelve None (no hay líquido saturado).

        Calibración Spencer-Danner-Yamada (cuando hay data experimental):
            Si rho_ref_kg_m3 + rho_ref_T_C están definidos (vienen de la
            segunda db de densidades experimentales), se recalcula un
            Z_RA "efectivo" que matchea ese punto exacto.  Esto baja
            errores de 12% → <2% para agua, alcoholes, etc.
        """
        if (self.tc_c is None or self.pc_bar is None
                or self.mw <= 0):
            return None
        T_K = T_C + 273.15
        Tc_K = self.tc_c + 273.15
        if T_K >= Tc_K:
            return None   # supercrítico, no hay líquido
        Pc_Pa = self.pc_bar * 1e5
        Tr = T_K / Tc_K

        # --- Determinar Z_RA: override, calibrado o calculado de ω ---
        if self.z_ra_override is not None:
            Z_RA = self.z_ra_override
        elif (self.rho_ref_kg_m3 is not None
                and self.rho_ref_T_C is not None
                and self.rho_ref_kg_m3 > 0):
            # Backsolve Z_RA del punto experimental (Spencer-Danner-Yamada)
            T_ref_K = self.rho_ref_T_C + 273.15
            Tr_ref = T_ref_K / Tc_K
            if Tr_ref >= 1.0:
                return None
            mw_kg_mol_ = self.mw / 1000.0
            V_ref = mw_kg_mol_ / self.rho_ref_kg_m3      # m³/mol
            base = V_ref * Pc_Pa / (R_GAS * Tc_K)
            exp_ref = 1.0 + (1.0 - Tr_ref) ** (2.0 / 7.0)
            if base <= 0 or exp_ref <= 0:
                return None
            Z_RA = base ** (1.0 / exp_ref)
        else:
            if self.omega is None:
                return None
            Z_RA = 0.29056 - 0.08775 * self.omega   # Spencer-Danner default
        if Z_RA <= 0:
            return None

        exponent = 1.0 + (1.0 - Tr) ** (2.0 / 7.0)
        V_sat = (R_GAS * Tc_K / Pc_Pa) * (Z_RA ** exponent)   # m³/mol
        mw_kg_mol = self.mw / 1000.0
        return mw_kg_mol / V_sat   # kg/m³


# ======================================================
# PARSER DEL .md
# ======================================================

_DB: Optional[Dict[str, ComponentThermo]] = None
_DB_PATH = Path(__file__).parent / "data" / "thermo_db.md"


def _normalize_name(label: str) -> str:
    """'Methanol (CH4O)' → 'methanol'.  'o-Xylene' → 'xylene'."""
    base = label.split("(")[0].strip()
    base = base.lower().replace("-", " ")
    # Anclar al inicio: si no, 'carbon dioxide' pierde 'n ' interno ('carbodioxide').
    # Afecta CO2/CO/H2S/HCl/HBr/HCN/HF/CS2/CCl4/CF4/NF3/DMF.
    base = re.sub(r"^[on]\s+", "", base)   # 'o xylene' / 'n hexane' → 'xylene' / 'hexane'
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

        # Capa 7 — densidad experimental opcional (segunda db).
        # Formato A (dos líneas):
        #     rho_ref_kg_m3 = 997.0
        #     rho_ref_T_C   = 25
        # Formato B (una línea, más compacto):
        #     rho_ref = 997.0 kg/m3 @ 25 °C
        # Formato C (Z_RA pre-calibrado):
        #     z_ra = 0.2374
        m = re.search(r"rho_ref_kg_m3\s*=\s*([\d.]+)", body)
        if m: comp.rho_ref_kg_m3 = float(m.group(1))
        m = re.search(r"rho_ref_T_C\s*=\s*([\-\d.]+)", body)
        if m: comp.rho_ref_T_C = float(m.group(1))
        # Formato compacto (sobrescribe si presente)
        m = re.search(r"rho_ref\s*=\s*([\d.]+)\s*kg/m[3³]?\s*@\s*([\-\d.]+)", body)
        if m:
            comp.rho_ref_kg_m3 = float(m.group(1))
            comp.rho_ref_T_C   = float(m.group(2))
        m = re.search(r"z_ra\s*=\s*([\d.]+)", body)
        if m: comp.z_ra_override = float(m.group(1))

        # Merge en lugar de overwrite. Si el nombre ya existe (compuesto
        # repetido con datos por capa: e.g. Perry da Cp_liq + ΔHf, otra
        # entrada da Antoine), conserva los campos previos no vacíos.
        # Sin esto, Perry sobrescribiría Antoine de methanol/water con
        # None y rompería Wang-Henke.
        if name in out:
            prev = out[name]
            for f, default in _DEFAULTS.items():
                old_v = getattr(prev, f)
                new_v = getattr(comp, f)
                if old_v == default and new_v != default:
                    setattr(prev, f, new_v)
            # label/quality: prefer the more specific (non-empty)
            if not prev.label and comp.label:
                prev.label = comp.label
        else:
            out[name] = comp

    return out


# Defaults por campo, para el merge. Cualquier campo que aún esté en
# default es "vacío" y puede ser rellenado por una entrada posterior.
_DEFAULTS: Dict[str, object] = {
    "cas": "", "formula": "", "mw": 0.0, "tb_c": 0.0,
    "tc_c": None, "pc_bar": None, "omega": None,
    "antoine_A": None, "antoine_B": None, "antoine_C": None,
    "antoine_range_C": (0, 0),
    "cp_gas_coefs": None, "cp_gas_range_K": (0, 0),
    "cp_liq_coefs": None, "cp_liq_range_K": (0, 0),
    "dh_f_gas_kJ_mol": None, "dh_f_liq_kJ_mol": None,
    "quality": "",
    "rho_ref_kg_m3": None, "rho_ref_T_C": None, "z_ra_override": None,
}


def _ensure_loaded() -> Dict[str, ComponentThermo]:
    global _DB
    if _DB is None:
        _DB = _parse_db()
    return _DB


# ======================================================
# API PÚBLICA
# ======================================================

# Alias de nombres pseudo legacy → molécula real equivalente.  Mantienen
# resolubles los flowsheets viejos (y ejemplos de aceite genérico) sin
# migración de schema: 'vegetable_oil' es modelado como triolein y
# 'biodiesel' como oleato de metilo (mismas fórmulas C57H104O6 / C19H36O2).
_ALIASES = {
    "vegetable_oil": "triolein",
    "biodiesel":     "methyl_oleate",
}


def get(name: str) -> Optional[ComponentThermo]:
    """Devuelve el ComponentThermo por nombre (case-insensitive,
    underscore-tolerant).  None si no existe."""
    db = _ensure_loaded()
    if name in db:
        return db[name]
    # fallback: lowercase + underscores
    norm = name.lower().replace("-", "_").replace(" ", "_")
    if norm in db:
        return db[norm]
    alias = _ALIASES.get(norm)
    if alias is not None:
        return db.get(alias)
    # Overlay de estimados (Capa 4b): el sourceado ya falló → consultar
    # el overlay DESPUÉS (sourceado gana siempre).  Aditivo, no muta el .md.
    try:
        import estimated_overlay as _ov
        comp = _ov.get(name)
        if comp is None and norm != name:
            comp = _ov.get(norm)
        if comp is not None:
            return comp
    except Exception:
        pass
    return None


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
    """Cp de la mezcla ponderado por fracción másica a T (°C).

    Filtra valores absurdos del polinomio DIPPR cuando se extrapola
    fuera del rango calibrado.  Cp físicamente posible:
       gases:  0.5 - 15 kJ/kg·K (H2 ~14, He ~5, CH4 ~2.5, aire ~1)
       líquidos / sólidos: 0.5 - 7 kJ/kg·K (agua 4.18 es el más alto
                                              razonable)
    Si el DIPPR liquid de un componente da > 50 o < 0 a T,P del stream,
    es señal de que el componente está super-crítico (e.g. H2, CO,
    CH4 a 40°C nunca son líquidos).  En ese caso se sustituye por su
    valor en fase gaseosa, que SÍ está dentro del rango DIPPR válido.
    """
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
        # Sanitize: si el polinomio extrapola a valor absurdo, intentar
        # con phase='gas' (probablemente el componente es super-crítico
        # a las condiciones del stream y no existe como líquido).
        if cp_pure is None or cp_pure < 0.1 or cp_pure > 50.0:
            cp_gas = c.cp_kJ_kg_K(T_C, "gas")
            if cp_gas is not None and 0.1 < cp_gas < 50.0:
                cp_pure = cp_gas
            else:
                continue   # skip silently — falta DB para este comp
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


def density_kg_m3(name: str, T_C: float) -> Optional[float]:
    """Densidad líquida del componente puro a T (°C), kg/m³.
    Spencer-Danner-Rackett. None si faltan Tc/Pc/ω."""
    c = get(name)
    if c is None:
        return None
    return c.density_kg_m3(T_C)


def density_mix_kg_m3(comp_dict: Dict[str, float], T_C: float,
                       phase: str = "liquid") -> Optional[float]:
    """Densidad de la mezcla líquida a T (°C), kg/m³.

    Usa la regla de volúmenes aditivos (Amagat — más rigurosa que
    promedio ponderado de densidades cuando las densidades difieren):

        1 / ρ_mix = Σᵢ wᵢ / ρᵢ

    donde wᵢ es la fracción MÁSICA del componente i.  El razonamiento:
    1 kg de mezcla ocupa Σᵢ wᵢ/ρᵢ m³, así ρ_mix = 1 / (Σᵢ wᵢ/ρᵢ).

    Para gases la cosa cambia (ley de gas ideal o EOS), así que si
    phase != 'liquid' devuelve None.  Densidad de gas se calcula en
    otra función si hace falta.

    Si algún componente no tiene Rackett (le faltan Tc/Pc/ω), se lo
    omite de la suma (sus wᵢ se redistribuyen implícitamente).
    """
    if phase != "liquid":
        return None
    if not comp_dict:
        return None
    inv_rho_sum = 0.0
    w_used = 0.0
    for name, w in comp_dict.items():
        if w <= 0:
            continue
        rho = density_kg_m3(name, T_C)
        if rho is None or rho <= 0:
            continue
        inv_rho_sum += w / rho
        w_used += w
    if w_used <= 0 or inv_rho_sum <= 0:
        return None
    # Si solo algunos componentes tenían data, normalizo a esos
    return w_used / inv_rho_sum


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
