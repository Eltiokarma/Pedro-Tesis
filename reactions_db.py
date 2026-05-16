"""
REACTIONS_DB — base de datos de reacciones químicas (Capa 4).

Carga lazy desde data/reactions_db.md (25 reacciones) y expone una
API estructurada.  Una reacción tiene:

  · estequiometría (especie, fase, coef ν)
  · ΔH, ΔS, ΔG @ 298.15 K (extraídos de la termodinámica de Capa 3)
  · coeficientes de Van't Hoff:  ln Keq(T) = A + B/T
  · Δν, fase global, rango de T válido
  · flag irreversible (Keq(298) > 10²⁰ ⇒ usar conversión declarada)
  · flag derivable_de_capa3 (False para R022-R025: almidón, MDEA, Boudouard)

API:
  list_ids()                              → ['R001', 'R002', ...]
  get(rxn_id)                             → Reaction | None
  find_by_species(canonical_name)         → list[Reaction]
  keq_vant_hoff(rxn_id, T_K)              → float
  dh_rxn_kJ_mol(rxn_id, T_K)              → float (ΔH a T usando Cp de thermo_db)
  equilibrium_conversion_gas(rxn_id, feed_moles, T_K, P_bar) → ξ_extent

Mapeo formula→nombre canónico (para conectar con thermo_db):
  'CH4' → 'methane', 'CO2' → 'co2', 'H2O' → 'water', etc.
  Componentes sin contraparte en thermo_db (SO3, triolein, starch,
  C(grafito)) se marcan como 'unmapped' y NO se les puede calcular
  ΔCp_rxn(T) — la reacción cae a la versión 2-parámetros.
"""

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

R_GAS = 8.314462618          # J/(mol·K)  — CODATA 2018
T_REF_K = 298.15
P_REF_BAR = 1.0


# ============================================================
# Mapeo formula química → nombre canónico de thermo_db
# ============================================================
# Las reacciones usan fórmulas (CH4, H2O, CO2...). El thermo_db
# usa nombres (methane, water, co2...). Este mapping conecta los dos.
FORMULA_TO_THERMO = {
    # Inorgánicos básicos
    'CH4':       'methane',
    'O2':        'oxygen',
    'H2O':       'water',
    'CO2':       'co2',
    'CO':        'co',
    'H2':        'hydrogen',
    'N2':        'nitrogen',
    'NH3':       'ammonia',
    'SO2':       'so2',
    'SO3':       None,            # no está en thermo_db
    'H2S':       'h2s',
    'MDEA':      'mdea',
    # Orgánicos
    'CH3OH':           'methanol',
    'C2H5OH':          'ethanol',
    'C2H4':            'ethylene',
    'C2H6':            'ethane',
    'C3H8':            'propane',
    'C3H6':            'propylene',
    'CH3OCH3':         'dme',
    'CH3COOH':         'acetic_acid',
    'CH3CHO':          'acetaldehyde',
    'C2H4O':           'acetaldehyde',
    'CH3COOC2H5':      'ethyl_acetate',
    'C6H6':            'benzene',
    'C8H10':           'ethylbenzene',
    # Bioquímica
    'Glucose':         'glucose',
    'Sucrose':         'sucrose',
    'Fructose':        'fructose',
    # No mapeables (no están en thermo_db actual)
    'Triolein':        None,
    'FAME':            None,
    'Starch_unit':     None,
    'C(s)':            None,
}


def thermo_name(formula: str) -> Optional[str]:
    """Devuelve el nombre canónico en thermo_db para una fórmula química.
    Si la fórmula no está mapeada, intenta lowercase directo.
    None si no hay forma de conectar."""
    if formula in FORMULA_TO_THERMO:
        return FORMULA_TO_THERMO[formula]
    # Fallback: intento lowercase directo (e.g. 'co' ya es 'co')
    return formula.lower()


# Mapeo inverso  thermo_name → formula  (auto-construido de FORMULA_TO_THERMO)
# Para conectar el flowsheet (que usa nombres canónicos en composition)
# con las reacciones (que usan fórmulas).  Si una thermo_name aparece
# como destino de varias formulas distintas, gana la primera (no debería
# pasar con FORMULA_TO_THERMO actual).
THERMO_TO_FORMULA: Dict[str, str] = {}
for _f, _n in FORMULA_TO_THERMO.items():
    if _n is not None and _n not in THERMO_TO_FORMULA:
        THERMO_TO_FORMULA[_n] = _f


def formula_for(thermo_name_str: str) -> Optional[str]:
    """Inverso de thermo_name(): devuelve la fórmula química para
    un nombre canónico de thermo_db.  Retorna None si no hay match
    (componente no participa en ninguna reacción del catálogo)."""
    return THERMO_TO_FORMULA.get(thermo_name_str)


# ============================================================
# Dataclass
# ============================================================
@dataclass
class StoichEntry:
    formula: str          # formula como aparece en el .md ('CH4')
    phase:   str          # 'g', 'l', 'aq', 's'
    nu:      int          # negativo reactante, positivo producto

    @property
    def thermo_name(self) -> Optional[str]:
        return thermo_name(self.formula)


@dataclass
class Reaction:
    id:          str                # 'R001'
    name:        str                # 'Combustión completa de metano'
    category:    str = ""           # 'combustión', 'syngas', etc.
    stoich:      List[StoichEntry] = field(default_factory=list)
    delta_nu:    int = 0
    phase_global: str = ""
    T_min_K:     float = 298.15
    T_max_K:     float = 2000.0
    # Termodinámica @ 298.15 K (de Capa 3)
    dh_rxn_298_kJ_mol: Optional[float] = None
    ds_rxn_298_J_mol_K: Optional[float] = None
    dg_rxn_298_kJ_mol: Optional[float] = None
    # Van't Hoff: ln Keq(T) = A + B/T
    vant_hoff_A: Optional[float] = None
    vant_hoff_B: Optional[float] = None     # K
    # Flags
    irreversible: bool = False
    derivable_capa3: bool = True
    # Notas y refs
    comments: str = ""

    def keq_vant_hoff(self, T_K: float) -> Optional[float]:
        """Keq(T) usando 2 parámetros (asume ΔCp_rxn = 0).
        Válido en rango cercano a 298 K, error crece a alta T."""
        if self.vant_hoff_A is None or self.vant_hoff_B is None:
            return None
        ln_keq = self.vant_hoff_A + self.vant_hoff_B / T_K
        # Cap para evitar overflow
        if ln_keq > 700:  return float('inf')
        if ln_keq < -700: return 0.0
        return math.exp(ln_keq)

    def dh_rxn_kJ_mol(self, T_K: float) -> Optional[float]:
        """ΔH_rxn(T) corregido por ΔCp_rxn integrado desde 298 K usando
        Cp de thermo_db (Capa 2):
            ΔH(T) = ΔH(298) + ∫_298^T ΔCp_rxn(T') dT'
        """
        if self.dh_rxn_298_kJ_mol is None:
            return None
        if abs(T_K - T_REF_K) < 1e-6:
            return self.dh_rxn_298_kJ_mol
        # Integración numérica de ΔCp_rxn(T) entre 298 y T
        try:
            import thermo_db as _td
        except ImportError:
            return self.dh_rxn_298_kJ_mol   # sin Cp, devuelvo el de 298
        # Σ νᵢ · ∫ Cp_i(T) dT  para todas las especies con Cp en thermo_db
        n_steps = max(20, int(abs(T_K - T_REF_K) / 25))
        dT = (T_K - T_REF_K) / n_steps
        integral_J_mol = 0.0
        for step in range(n_steps):
            T_a = T_REF_K + step * dT
            T_b = T_a + dT
            # ΔCp_rxn(T_mid) trapezoidal
            T_mid = 0.5 * (T_a + T_b)
            dcp = self._delta_cp_rxn_J_mol_K(T_mid, _td)
            if dcp is None:
                # No puedo integrar — devuelvo ΔH(298)
                return self.dh_rxn_298_kJ_mol
            integral_J_mol += dcp * dT
        return self.dh_rxn_298_kJ_mol + integral_J_mol / 1000.0   # kJ/mol

    def _delta_cp_rxn_J_mol_K(self, T_K: float, _td) -> Optional[float]:
        """ΔCp_rxn = Σ νᵢ · Cp_i(T) en J/(mol·K).  Devuelve None si
        algún componente no tiene Cp en thermo_db (Cp_gas ni Cp_liq
        según la fase de la reacción)."""
        total = 0.0
        for sp in self.stoich:
            tname = sp.thermo_name
            if tname is None:
                return None
            comp = _td.get(tname)
            if comp is None:
                return None
            phase = 'gas' if sp.phase == 'g' else 'liquid'
            cp = comp.cp_J_mol_K(T_K, phase)
            if cp is None:
                return None
            total += sp.nu * cp
        return total

    def reactants(self) -> List[StoichEntry]:
        return [s for s in self.stoich if s.nu < 0]

    def products(self) -> List[StoichEntry]:
        return [s for s in self.stoich if s.nu > 0]


# ============================================================
# Parser
# ============================================================
_DB: Optional[Dict[str, Reaction]] = None
_DB_PATH = Path(__file__).parent / "data" / "reactions_db.md"


def _parse_db() -> Dict[str, Reaction]:
    if not _DB_PATH.is_file():
        return {}
    text = _DB_PATH.read_text(encoding="utf-8")
    sections = re.split(r"^## (R\d{3})", text, flags=re.MULTILINE)
    out: Dict[str, Reaction] = {}
    # sections[0] es preamble, después pares (id, body)
    for i in range(1, len(sections), 2):
        rxn_id = sections[i].strip()
        body = sections[i + 1] if i + 1 < len(sections) else ""
        rxn = _parse_one(rxn_id, body)
        if rxn:
            out[rxn_id] = rxn
    return out


def _parse_one(rxn_id: str, body: str) -> Optional[Reaction]:
    # Header: '— Combustión completa de metano\n\n**Categoría:** combustión'
    head_m = re.match(r"\s*—\s*(.+?)(?:\n|$)", body)
    name = head_m.group(1).strip() if head_m else rxn_id

    rxn = Reaction(id=rxn_id, name=name)

    m = re.search(r"\*\*Categoría:\*\*\s*([^\n⚠]+)", body)
    if m: rxn.category = m.group(1).strip()

    rxn.derivable_capa3 = "NO DERIVADA DE CAPA 3" not in body

    # Estequiometría: tabla markdown con columnas Especie | Fase | ν
    # | CH4 | g | -1 |
    # Si no hay tabla (R022-R025 algunas), parsear de la línea reacción
    rows = re.findall(r"^\|\s*([A-Za-z0-9_()]+)\s*\|\s*([gqlas]+)\s*\|\s*([+-]?\d+)\s*\|",
                      body, re.MULTILINE)
    for formula, phase, nu in rows:
        rxn.stoich.append(StoichEntry(formula=formula, phase=phase, nu=int(nu)))

    # Δν
    m = re.search(r"\*\*Δν =\*\*\s*([+-]?\d+)", body)
    if m: rxn.delta_nu = int(m.group(1))

    # Fase global
    m = re.search(r"\*\*Fase global:\*\*\s*([^\n*]+)", body)
    if m: rxn.phase_global = m.group(1).strip()

    # Rango T válido: '300–2000 K' o '300-2000 K'
    m = re.search(r"\*\*Rango T válido:\*\*\s*(\d+)\s*[-–]\s*(\d+)\s*K", body)
    if m:
        rxn.T_min_K = float(m.group(1))
        rxn.T_max_K = float(m.group(2))

    # ΔH, ΔS, ΔG @ 298.15 K
    # | ΔH_rxn [kJ/mol] | -802.642 | -802.300 | -0.342 |
    m = re.search(r"\|\s*ΔH_rxn\s*\[kJ/mol\]\s*\|\s*([+-]?[\d.eE+-]+)\s*\|", body)
    if m: rxn.dh_rxn_298_kJ_mol = float(m.group(1))
    m = re.search(r"\|\s*ΔS_rxn\s*\[J/\(mol·K\)\]\s*\|\s*([+-]?[\d.eE+-]+)\s*\|", body)
    if m: rxn.ds_rxn_298_J_mol_K = float(m.group(1))
    m = re.search(r"\|\s*ΔG_rxn\s*\[kJ/mol\]\s*\|\s*([+-]?[\d.eE+-]+)\s*\|", body)
    if m: rxn.dg_rxn_298_kJ_mol = float(m.group(1))

    # Para reacciones no-derivables (R022-R025) los ΔH/ΔG están en bullet:
    #   - ΔH_rxn = -10.00 kJ/mol  *(...)
    if rxn.dh_rxn_298_kJ_mol is None:
        m = re.search(r"ΔH_rxn\s*=\s*([+-]?[\d.]+)\s*kJ/mol", body)
        if m: rxn.dh_rxn_298_kJ_mol = float(m.group(1))
    if rxn.dg_rxn_298_kJ_mol is None:
        m = re.search(r"ΔG_rxn\s*=\s*([+-]?[\d.]+)\s*kJ/mol", body)
        if m: rxn.dg_rxn_298_kJ_mol = float(m.group(1))

    # Coeficientes Van't Hoff: 'A = -0.6133' y 'B = +96535.64 K'
    m = re.search(r"^-?\s*A\s*=\s*([+-]?[\d.eE+-]+)", body, re.MULTILINE)
    if m: rxn.vant_hoff_A = float(m.group(1))
    m = re.search(r"^-?\s*B\s*=\s*([+-]?[\d.eE+-]+)\s*K", body, re.MULTILINE)
    if m: rxn.vant_hoff_B = float(m.group(1))

    # Irreversible
    rxn.irreversible = "Marcado irreversible" in body or "marcado irreversible" in body

    # Comentarios técnicos
    m = re.search(r"###\s*Comentarios técnicos\s*\n+(.*?)(?=###|---|$)",
                  body, re.DOTALL)
    if m: rxn.comments = m.group(1).strip()

    return rxn


def _ensure_loaded() -> Dict[str, Reaction]:
    global _DB
    if _DB is None:
        _DB = _parse_db()
    return _DB


# ============================================================
# API pública
# ============================================================
def list_ids() -> List[str]:
    return sorted(_ensure_loaded().keys())


def get(rxn_id: str) -> Optional[Reaction]:
    return _ensure_loaded().get(rxn_id)


def find_by_species(canonical_name: str) -> List[Reaction]:
    """Devuelve las reacciones donde aparece la especie (por nombre
    canónico thermo_db, e.g. 'methane').  Útil para encontrar qué
    reacciones aplican a un componente del flowsheet."""
    out = []
    for rxn in _ensure_loaded().values():
        if any(s.thermo_name == canonical_name for s in rxn.stoich):
            out.append(rxn)
    return out


def keq_vant_hoff(rxn_id: str, T_K: float) -> Optional[float]:
    rxn = get(rxn_id)
    return rxn.keq_vant_hoff(T_K) if rxn else None


def dh_rxn_kJ_mol(rxn_id: str, T_K: float) -> Optional[float]:
    rxn = get(rxn_id)
    return rxn.dh_rxn_kJ_mol(T_K) if rxn else None


# ============================================================
# Conversión de equilibrio (gas ideal, una reacción)
# ============================================================
def equilibrium_conversion_gas(rxn_id: str,
                                feed_moles: Dict[str, float],
                                T_K: float,
                                P_bar: float = 1.0,
                                xi_init: float = 0.5,
                                max_iter: int = 100,
                                tol: float = 1e-8) -> Optional[Dict]:
    """Resuelve el grado de avance ξ que satisface Kp(T) para una
    reacción única en fase gas ideal.

    feed_moles: dict {formula: moles_iniciales}.  Ejemplo:
        {'N2': 1.0, 'H2': 3.0}     para Haber con feed estequiométrico.

    Devuelve dict con:
        'xi': grado de avance (mol)
        'conversion_lim': conversión del reactante limitante (0-1)
        'moles_out': dict {formula: moles_finales}
        'y_out': dict {formula: fracción_molar_final}
        'Keq': Kp usado
        'limiting': formula del reactante limitante
        None si la reacción no existe, le faltan A/B, o algún
        reactante no está en el feed.

    Hipótesis:
      · Gas ideal (válido a P < 30 bar; a 200 bar (Haber) error ~30%)
      · Una sola reacción (no acoplada)
      · Sin inertes que afecten Kp (los inertes solo cambian y_i)

    Para sistemas multi-reacción acoplados (SMR+WGS, etc.) hace falta
    minimización de Gibbs — pendiente para v1.1.
    """
    rxn = get(rxn_id)
    if rxn is None or rxn.vant_hoff_A is None or rxn.vant_hoff_B is None:
        return None

    # Validar que todos los reactantes estén en el feed
    reactants = rxn.reactants()
    for r in reactants:
        if feed_moles.get(r.formula, 0.0) <= 0:
            return None

    # Determinar reactante limitante: el que llega a 0 primero
    # como (n_i / |ν_i|) mínimo
    lim = min(reactants, key=lambda r: feed_moles[r.formula] / abs(r.nu))
    xi_max = feed_moles[lim.formula] / abs(lim.nu) - 1e-12  # límite físico

    Keq = rxn.keq_vant_hoff(T_K)
    if Keq is None or Keq <= 0:
        return None

    # Si es irreversible (Keq enorme), retornar conversión completa
    if Keq > 1e30:
        moles = dict(feed_moles)
        for s in rxn.stoich:
            moles[s.formula] = moles.get(s.formula, 0.0) + s.nu * xi_max
        n_total = sum(moles.values())
        y = {k: v/n_total for k, v in moles.items()} if n_total > 0 else {}
        return dict(xi=xi_max, conversion_lim=1.0,
                    moles_out=moles, y_out=y,
                    Keq=Keq, limiting=lim.formula)

    n_feed = sum(feed_moles.values())

    def _residual(xi: float) -> float:
        """Kp_actual(ξ) - Keq.  Buscamos raíz."""
        moles = dict(feed_moles)
        for s in rxn.stoich:
            moles[s.formula] = moles.get(s.formula, 0.0) + s.nu * xi
        n_tot = sum(moles.values())
        if n_tot <= 0:
            return float('inf')
        # Kp = Π (y_i)^ν_i · (P/P°)^Δν
        log_kp = 0.0
        for s in rxn.stoich:
            y = moles[s.formula] / n_tot
            if y <= 0:
                # Si producto, ξ muy chico; si reactante, ξ muy grande
                return float('inf') if s.nu > 0 else float('-inf')
            log_kp += s.nu * math.log(y)
        log_kp += rxn.delta_nu * math.log(P_bar / P_REF_BAR)
        return log_kp - math.log(Keq)

    # Bisección segura
    lo, hi = 1e-12, xi_max
    f_lo, f_hi = _residual(lo), _residual(hi)
    if f_lo * f_hi > 0:
        # Sin cambio de signo: o no reacciona casi nada o conversión completa
        return dict(
            xi=(lo if abs(f_lo) < abs(f_hi) else hi),
            conversion_lim=(0.0 if abs(f_lo) < abs(f_hi) else 1.0),
            moles_out=dict(feed_moles),
            y_out={k: v/n_feed for k, v in feed_moles.items()},
            Keq=Keq, limiting=lim.formula)

    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        f_mid = _residual(mid)
        if abs(f_mid) < tol:
            break
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid

    xi = 0.5 * (lo + hi)
    moles = dict(feed_moles)
    for s in rxn.stoich:
        moles[s.formula] = moles.get(s.formula, 0.0) + s.nu * xi
    n_total = sum(moles.values())
    y = {k: v/n_total for k, v in moles.items()} if n_total > 0 else {}
    return dict(
        xi=xi,
        conversion_lim=xi / xi_max if xi_max > 0 else 0.0,
        moles_out=moles, y_out=y,
        Keq=Keq, limiting=lim.formula,
    )


# ============================================================
# Multi-reacción acoplada (Newton-Raphson con damping)
# ============================================================
#
# Resuelve simultáneamente N reacciones en fase gas ideal, dado un
# feed.  Variables: ξ = (ξ₁, ..., ξ_N) (grados de avance).
#
# Sistema de ecuaciones:
#   F_j(ξ) = Σᵢ νᵢⱼ · ln(yᵢ) + Δνⱼ · ln(P/P°) - ln Keq_j  = 0    ∀j
#
# donde:   nᵢ(ξ) = nᵢ⁰ + Σⱼ νᵢⱼ · ξⱼ
#          n_T(ξ) = n_T⁰ + Σⱼ Δνⱼ · ξⱼ
#          yᵢ    = nᵢ / n_T
#
# Jacobiano analítico:
#   ∂F_j/∂ξ_k = Σᵢ νᵢⱼ · νᵢ_k / nᵢ  -  Δνⱼ · Δν_k / n_T
#
# Restricciones:
#   nᵢ ≥ 0  ∀i  (enforced via line search backtracking)
#
# Limitaciones:
#   · Gas ideal (sin coef. de fugacidad); error ~30% a P>100 bar
#   · No descarta cinética; calcula el límite termodinámico
#   · Falla si una reacción es irreversible (Keq=∞) — usar el solver
#     single-reaction o declarar conversión a mano para esos casos


def _matrix_rank(M: List[List[float]], n_cols: int, tol: float = 1e-10) -> int:
    """Rango por eliminación gaussiana sobre las columnas de M (la
    matriz estequiométrica es n_species × N_rxns; rank=N significa
    reacciones independientes)."""
    n_rows = len(M)
    A = [row[:] for row in M]
    rank = 0
    pivot_row = 0
    for col in range(n_cols):
        piv = -1
        max_val = tol
        for r in range(pivot_row, n_rows):
            if abs(A[r][col]) > max_val:
                max_val = abs(A[r][col])
                piv = r
        if piv < 0:
            continue
        A[piv], A[pivot_row] = A[pivot_row], A[piv]
        for r in range(pivot_row + 1, n_rows):
            f = A[r][col] / A[pivot_row][col]
            for c in range(col, n_cols):
                A[r][c] -= f * A[pivot_row][c]
        rank += 1
        pivot_row += 1
        if pivot_row >= n_rows:
            break
    return rank


def _gauss_solve(A: List[List[float]], b: List[float]) -> Optional[List[float]]:
    """Eliminación gaussiana con pivoteo parcial.  Resuelve Ax = b.
    Devuelve None si la matriz es singular."""
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for i in range(n):
        # Pivoteo parcial
        piv = max(range(i, n), key=lambda r: abs(M[r][i]))
        if abs(M[piv][i]) < 1e-14:
            return None
        M[i], M[piv] = M[piv], M[i]
        for r in range(i+1, n):
            f = M[r][i] / M[i][i]
            for c in range(i, n+1):
                M[r][c] -= f * M[i][c]
    x = [0.0] * n
    for i in range(n-1, -1, -1):
        x[i] = (M[i][n] - sum(M[i][c] * x[c] for c in range(i+1, n))) / M[i][i]
    return x


def solve_multi_reaction_equilibrium(
        rxn_ids:    List[str],
        feed_moles: Dict[str, float],
        T_K:        float,
        P_bar:      float = 1.0,
        max_iter:   int   = 200,
        tol:        float = 1e-8,
        verbose:    bool  = False) -> Optional[Dict]:
    """Resuelve equilibrio multi-reacción acoplado en fase gas ideal.

    rxn_ids:    lista de IDs de reactions_db (e.g. ['R002', 'R003']).
    feed_moles: dict {formula: moles}, e.g. {'CH4': 1, 'H2O': 3}.
    T_K, P_bar: condiciones de operación.

    Devuelve dict con:
        'xi':         dict {rxn_id: grado de avance}
        'moles_out':  dict {formula: moles_finales}
        'y_out':      dict {formula: fracción molar}
        'dh_total_kJ': ΔH global de las reacciones acopladas a T (kJ)
                      = Σⱼ ξⱼ · ΔH_rxn_j(T)
                      < 0 exotérmico neto, > 0 endotérmico neto
        'Keq':        dict {rxn_id: Keq usado}
        'iterations': # iteraciones Newton
        'residual':   norma 2 final del residuo
        None si la solución no converge o el problema es mal puesto.
    """
    rxns = [get(rid) for rid in rxn_ids]
    if any(r is None for r in rxns):
        return None
    if any(r.vant_hoff_A is None or r.vant_hoff_B is None for r in rxns):
        return None
    if any(r.irreversible for r in rxns):
        # Irreversibles requieren conversión declarada
        return None

    N = len(rxns)
    Keq = [r.keq_vant_hoff(T_K) for r in rxns]
    if any(k is None or k <= 0 for k in Keq):
        return None
    log_Keq = [math.log(k) for k in Keq]

    # Construir lista de especies presentes (feed + cualquier especie
    # que aparezca en cualquier reacción)
    species: List[str] = list(feed_moles.keys())
    for r in rxns:
        for s in r.stoich:
            if s.formula not in species:
                species.append(s.formula)
    n_species = len(species)
    sp_idx = {f: i for i, f in enumerate(species)}

    # Matriz estequiométrica ν[i, j] (especies × reacciones)
    nu = [[0.0] * N for _ in range(n_species)]
    for j, r in enumerate(rxns):
        for s in r.stoich:
            nu[sp_idx[s.formula]][j] = float(s.nu)
    delta_nu = [r.delta_nu for r in rxns]

    # Check de independencia lineal de las reacciones.  Si rank(ν) < N
    # el sistema tiene combinaciones lineales nulas (e.g. SMR+DRM+WGS:
    # DRM = SMR + WGS_inverso → 3 ecuaciones, 2 grados de libertad).
    # La composición converge pero los ξ derivan al infinito en la
    # dirección espuria.  Mejor avisar y rechazar.
    if _matrix_rank(nu, N) < N:
        return None

    # Vector de moles iniciales
    n0 = [feed_moles.get(f, 0.0) for f in species]
    n_total_0 = sum(n0)
    if n_total_0 <= 0:
        return None

    # Initial guess: nudge MUY pequeño que no haga negativo a ningún nᵢ.
    # Estrategia: ε · n_total⁰ · sign(reacción favorable o desfavorable).
    # Si Keq_j ≫ 1, ξ_j > 0; si Keq_j ≪ 1 y hay productos en el feed,
    # podemos dejar ξ_j tendiendo a 0 (Newton lo manda a negativo si
    # toca).
    eps = 1e-6 * n_total_0
    xi = [eps if log_Keq[j] > 0 else 0.0 for j in range(N)]
    # Verificar que no produzca moles negativos.  Si lo hace, achicar.
    for _ in range(60):
        n_check = [n0[i] + sum(nu[i][j] * xi[j] for j in range(N))
                   for i in range(n_species)]
        if all(n >= 0 for n in n_check):
            break
        xi = [x * 0.5 for x in xi]
    else:
        xi = [0.0] * N

    def _compute_n(xi_vec: List[float]) -> Optional[Tuple[List[float], float]]:
        n_vec = [n0[i] + sum(nu[i][j] * xi_vec[j] for j in range(N))
                 for i in range(n_species)]
        if any(n < -1e-12 for n in n_vec):
            return None
        # Floor minúsculo para evitar log(0); productos puros que no se
        # forman generan singularidad numérica.
        n_vec = [max(n, 1e-30) for n in n_vec]
        return n_vec, sum(n_vec)

    def _residual_and_jacobian(xi_vec: List[float]):
        res = _compute_n(xi_vec)
        if res is None:
            return None
        n_vec, n_T = res
        log_y = [math.log(n_vec[i] / n_T) for i in range(n_species)]
        F = [0.0] * N
        for j in range(N):
            F[j] = (sum(nu[i][j] * log_y[i] for i in range(n_species))
                    + delta_nu[j] * math.log(P_bar / P_REF_BAR)
                    - log_Keq[j])
        # Jacobiano: J[j][k] = Σᵢ νᵢⱼ νᵢ_k / nᵢ - Δνⱼ Δν_k / n_T
        J = [[0.0] * N for _ in range(N)]
        for j in range(N):
            for k in range(N):
                term1 = sum(nu[i][j] * nu[i][k] / n_vec[i] for i in range(n_species))
                term2 = delta_nu[j] * delta_nu[k] / n_T
                J[j][k] = term1 - term2
        return F, J, n_vec, n_T

    last_norm = float('inf')
    iters_done = 0
    for it in range(max_iter):
        iters_done = it + 1
        rj = _residual_and_jacobian(xi)
        if rj is None:
            return None
        F, J, n_vec, n_T = rj
        norm = math.sqrt(sum(f*f for f in F))
        if verbose:
            print(f'  it={it:3} ||F||={norm:.3e}  ξ={[f"{x:.4f}" for x in xi]}')
        if norm < tol:
            last_norm = norm
            break
        # Resolver J · Δξ = -F
        rhs = [-f for f in F]
        dxi = _gauss_solve(J, rhs)
        if dxi is None:
            # Jacobiano singular — usar gradiente damped
            dxi = [-F[j] * 0.1 for j in range(N)]
        # Line search: max α tal que ningún nᵢ < 0 y norma decrece
        alpha = 1.0
        for _ in range(40):
            xi_try = [xi[j] + alpha * dxi[j] for j in range(N)]
            res = _compute_n(xi_try)
            if res is None:
                alpha *= 0.5
                continue
            rj2 = _residual_and_jacobian(xi_try)
            if rj2 is None:
                alpha *= 0.5
                continue
            F2 = rj2[0]
            norm2 = math.sqrt(sum(f*f for f in F2))
            if norm2 < norm * (1 - 1e-4 * alpha) or alpha < 1e-8:
                xi = xi_try
                last_norm = norm2
                break
            alpha *= 0.5
        else:
            # Línea no encontró mejora — abandonar
            return None

    if last_norm > 1e-3:
        # No convergió suficiente
        return None

    # Composición final
    moles_out = {species[i]: max(n0[i] + sum(nu[i][j]*xi[j] for j in range(N)), 0.0)
                 for i in range(n_species)}
    n_tot = sum(moles_out.values())
    y_out = {k: v/n_tot for k, v in moles_out.items()} if n_tot > 0 else {}

    # ΔH total de las reacciones (corregido por ΔCp_rxn vía Capa 2)
    dh_total = 0.0
    for j, r in enumerate(rxns):
        dh = r.dh_rxn_kJ_mol(T_K)
        if dh is None:
            dh = r.dh_rxn_298_kJ_mol or 0.0
        dh_total += xi[j] * dh

    return dict(
        xi={rxn_ids[j]: xi[j] for j in range(N)},
        moles_out=moles_out,
        y_out=y_out,
        dh_total_kJ=dh_total,
        Keq={rxn_ids[j]: Keq[j] for j in range(N)},
        iterations=iters_done,
        residual=last_norm,
    )


# ============================================================
# Wrapper alto-nivel para integrar con el flowsheet
# ============================================================
# El flowsheet usa composiciones por FRACCIÓN MÁSICA y nombres
# canónicos de thermo_db ('methane', 'water', ...).  Este wrapper:
#   1. Convierte mass fractions → moles via MW de thermo_db
#   2. Traduce nombres canónicos → fórmulas químicas
#   3. Llama solve_multi_reaction_equilibrium
#   4. Convierte de vuelta a mass fractions
#   5. Calcula heat_of_reaction en kJ/kg de input total
#
# Este es el punto de contacto entre Capa 4 (reacciones) y la Capa
# de flowsheet.  Aislado acá para que reactions_db quede agnóstico
# del modelo de Block/Stream.

def solve_equilibrium_reactor_from_composition(
        rxn_ids:           List[str],
        inlet_composition: Dict[str, float],   # {thermo_name: mass_fraction}
        inlet_mass_kg_s:   float,              # kg/s (usado para escalar)
        T_K:               float,
        P_bar:             float = 1.0) -> Optional[Dict]:
    """Resuelve un reactor de equilibrio dado el inlet en composición
    másica.  Devuelve dict con:
        'outlet_composition': {thermo_name: mass_fraction}
        'outlet_mass_kg_s':   kg/s totales (= inlet_mass_kg_s, ley conservación)
        'heat_of_reaction_kJ_per_kg':   kJ/kg de input
            > 0 endotérmico (consume calor del medio)
            < 0 exotérmico (libera calor al medio)
            Compatible directo con Block.heat_of_reaction
        'duty_kW': dh_total · inlet_mass_kg_s  (= calor a entregar/extraer)
        'xi':       dict {rxn_id: ξ_mol_per_s}
        'unmapped': lista de nombres del inlet que no se pudieron
                    traducir a fórmula química (no participan en
                    ninguna reacción).  Pasan como inertes.
        None si solve_multi_reaction_equilibrium falla o si falta
        thermo_db, o si NINGÚN componente del inlet puede mapearse
        a fórmula química (no hay reactantes válidos).
    """
    try:
        import thermo_db as _td
    except ImportError:
        return None

    # Construir feed en moles por fórmula química
    feed_moles: Dict[str, float] = {}
    inert_mass_per_s: Dict[str, float] = {}
    unmapped: List[str] = []
    total_frac = sum(inlet_composition.values())
    if total_frac <= 0:
        return None

    # Renormalizar por seguridad
    norm_comp = {k: v/total_frac for k, v in inlet_composition.items() if v > 0}

    for thermo_n, frac in norm_comp.items():
        m_kg_per_s = frac * inlet_mass_kg_s
        formula = formula_for(thermo_n)
        comp_obj = _td.get(thermo_n)
        if comp_obj is None or comp_obj.mw <= 0 or formula is None:
            # No puedo convertirlo a moles o no tiene fórmula → inerte
            inert_mass_per_s[thermo_n] = m_kg_per_s
            if formula is None:
                unmapped.append(thermo_n)
            continue
        # mass_kg/s × (1000 g/kg) ÷ MW (g/mol) = mol/s
        moles_per_s = m_kg_per_s * 1000.0 / comp_obj.mw
        feed_moles[formula] = feed_moles.get(formula, 0.0) + moles_per_s

    if not feed_moles:
        return None

    res = solve_multi_reaction_equilibrium(rxn_ids, feed_moles, T_K, P_bar)
    if res is None:
        return None

    # Convertir moles_out → mass_kg/s por componente
    outlet_mass_per_s: Dict[str, float] = {}
    for formula, mol_per_s in res['moles_out'].items():
        if mol_per_s < 1e-15:
            continue
        thermo_n = thermo_name(formula)
        if thermo_n is None:
            continue
        comp_obj = _td.get(thermo_n)
        if comp_obj is None or comp_obj.mw <= 0:
            continue
        # mol/s × MW (g/mol) ÷ 1000 = kg/s
        outlet_mass_per_s[thermo_n] = mol_per_s * comp_obj.mw / 1000.0

    # Sumar inertes (que pasan sin reaccionar)
    for thermo_n, m in inert_mass_per_s.items():
        outlet_mass_per_s[thermo_n] = outlet_mass_per_s.get(thermo_n, 0.0) + m

    # ΔH viene en kJ pero los ξ ya están en mol/s → kJ/s = kW
    dh_total_kW = res['dh_total_kJ']
    heat_of_reaction_kJ_per_kg = (dh_total_kW / inlet_mass_kg_s
                                   if inlet_mass_kg_s > 0 else 0.0)

    total_out = sum(outlet_mass_per_s.values())
    outlet_composition = ({k: v/total_out for k, v in outlet_mass_per_s.items()}
                           if total_out > 0 else {})

    return dict(
        outlet_composition=outlet_composition,
        outlet_mass_kg_s=total_out,
        heat_of_reaction_kJ_per_kg=heat_of_reaction_kJ_per_kg,
        duty_kW=dh_total_kW,
        xi=res['xi'],
        unmapped=unmapped,
    )
