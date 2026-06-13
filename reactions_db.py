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
    'SO2':       'so2',           # ya existe en thermo_db.md
    'SO3':       'sulfur_trioxide', # Perry 8th ed (Cmpd 327)
    'H2S':       'h2s',
    'MDEA':      'mdea',
    # Óxidos de nitrógeno / HNO3 (E14 ácido nítrico) — alinear con thermo_db
    'NO':        'nitric_oxide',
    'NO2':       'nitrogen_dioxide',
    'N2O':       'nitrous_oxide',
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
    'C7H8':            'toluene',        # R035 HDA (hidrodealquilación)
    'C8H10':           'ethylbenzene',
    'C2H5_C6H5':       'ethylbenzene',  # alias usado en R016 styrene
    'Triolein':        'triolein',      # R021 biodiesel (C57H104O6)
    'MeOleate':        'methyl_oleate', # R021 biodiesel (FAME, C19H36O2)
    'Glycerol':        'glycerin',      # nombre alternativo (R021 biodiesel)
    # Bioquímica
    'Glucose':         'glucose',
    'Sucrose':         'sucrose',
    'Fructose':        'fructose',
    # Inorgánicos / electrolitos (ejemplos E10, E06)
    'Cl2':             'chlorine',
    'HCl':             'hydrogen_chloride',
    'NaOH':            'sodium_hydroxide',
    'NaCl':            'sodium_chloride',
    'H2SO4':           'sulfuric_acid',
    'HNO3':            'nitric_acid',
    # Materiales / cemento / vidrio (E11, E12)
    'CaCO3':           'limestone',
    'CaO':             'quicklime',
    'SiO2':            'silica',
    'Na2CO3':          'soda_ash',
    # Pseudo-componentes (química asociada NO derivable de Capa 3)
    'polyethylene':    'polyethylene',
    'urea':            'urea',
    'soap':            'soap',
    'vegetable_oil':   'vegetable_oil',
    'glycerin':        'glycerin',
    # No mapeables (no están en thermo_db actual)
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

    # ---- Capa 4b (predictor) — procedencia + confianza ----
    # Tipo de reaccion:
    #   'curated'   — escrita a mano en reactions_db.md (literatura)
    #   'auto'      — generada por chemfx.auto_reactions (combustion, cracking)
    #   'predicted' — generada por templates T01-T20 + Joback/Benson
    origin: str = "curated"
    # Confianza del mecanismo (que la reaccion realmente puede ocurrir
    # con el set de reactantes dado).
    confidence_mechanism: str = "alta"   # 'alta' | 'media' | 'baja'
    # Confianza de la termodinamica (ΔH, ΔS, ΔG estimados).
    confidence_thermo: str = "alta"
    # Si origin in ('auto', 'predicted'): metodo usado para estimar ΔH.
    estimation_method: str = ""   # 'joback', 'benson', 'hess_from_exp', 'auto_combustion'
    estimation_uncertainty_kJ_mol: float = 0.0
    # Si origin == 'predicted': template T01..T20 que la genero.
    transformation_id: Optional[str] = None
    # Catalizador requerido (informativo, no afecta el solver).
    requires_catalyst: bool = False
    catalyst_hint: str = ""

    # ============================================================
    # CAPA 5 — CINÉTICA (Arrhenius)
    # ============================================================
    # Cargada desde data/kinetics_db.md.  Si kinetics_available=False
    # esta reacción no tiene cinética validada → usar mode='equilibrium'
    # en el reactor del flowsheet.
    kinetics_available: bool = False
    # Parámetros Arrhenius: k(T) = k0 · exp(-Ea/RT)
    # Unidades de k0 dependen del orden global y del basis (volumen vs
    # masa de catalizador).  Documentadas en data/kinetics_db.md.
    k0:           Optional[float] = None
    Ea_kJ_mol:    Optional[float] = None
    # Ley de velocidad: 'elemental' | 'first_order' | 'global' |
    # 'lh_xu_froment' | 'lh_bussche' | 'temkin_pyzhev' | etc.
    rate_law:     str = ""
    # Orden de reacción por especie (formula → exponente).  Por
    # ejemplo R002 WGS: {'CO': 1, 'H2O': 1}.  Si vacío, asume
    # estequiométrico (|νᵢ| para reactantes).
    orders:       Dict[str, float] = field(default_factory=dict)
    # Basis de la velocidad:
    #   'volume'  → r en mol/(m³_reactor·s)
    #   'cat_mass' → r en mol/(kg_cat·s); convertir a volume con ρ_b
    rate_basis:   str = "volume"
    # Densidad de empaque de catalizador (kg_cat/m³_reactor).
    # Solo aplica si rate_basis='cat_mass'.
    rho_b_cat:    Optional[float] = None
    # Rango T válido específico de la cinética (puede ser más
    # estrecho que el termo).
    kin_T_min_K:  Optional[float] = None
    kin_T_max_K:  Optional[float] = None
    # Concentraciones se expresan en mol/m³ por default. Algunas
    # cinéticas catalíticas usan presión parcial (bar) — flag aparte.
    uses_partial_pressure: bool = False
    # Catalizador típico (string descriptivo, no usado en cálculos)
    catalyst:     str = ""

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
    # CINÉTICA — Arrhenius forward + reversa por equilibrio detallado
    # ============================================================

    def k_arrhenius(self, T_K: float) -> Optional[float]:
        """Constante de velocidad k(T) = k₀ · exp(-Ea/RT).

        Unidades de retorno = unidades de k₀ (ver data/kinetics_db.md
        por reacción).  Devuelve None si no hay cinética cargada.
        """
        if not self.kinetics_available or self.k0 is None or self.Ea_kJ_mol is None:
            return None
        Ea_J = self.Ea_kJ_mol * 1000.0
        # Cap del exponente para evitar overflow numérico
        exponent = -Ea_J / (R_GAS * T_K)
        if exponent < -700:
            return 0.0
        if exponent > 700:
            return float('inf')
        return self.k0 * math.exp(exponent)

    def k_reverse(self, T_K: float) -> Optional[float]:
        """k_rev por equilibrio detallado: k_rev = k_fwd / Keq.

        Garantiza consistencia termo: en equilibrio r_fwd = r_rev.
        Devuelve None si falta cinética o Keq.  Devuelve 0 si la
        reacción es irreversible (Keq enorme).

        Detalle dimensional: Capa 4 reporta Keq como Kp (adimensional
        con P°=1 bar).  Si la cinética está en concentraciones
        (uses_partial_pressure=False) y Δν≠0, hay que convertir
        Kp → Kc = Kp / (RT/P°)^Δν, donde RT/P° = 8.314e-5·T·m³·bar/mol.
        Sin esta conversión, R011/R012/R004 plateauan lejos del
        equilibrio termodinámico real.
        """
        if self.irreversible:
            return 0.0
        k_fwd = self.k_arrhenius(T_K)
        keq_kp = self.keq_vant_hoff(T_K)
        if k_fwd is None or keq_kp is None or keq_kp <= 0:
            return None
        if math.isinf(keq_kp):
            return 0.0
        if self.uses_partial_pressure:
            # Cinética en bar: Kp directo
            return k_fwd / keq_kp
        # Cinética en concentraciones: convertir Kp → Kc
        # Kc [m³·mol⁻¹]^Δν = Kp [adim] / (RT/P°)^Δν
        # con R en m³·bar·mol⁻¹·K⁻¹ = 8.314e-5
        RT_per_Pstd = R_GAS * 1e-5 * T_K       # m³·bar/mol
        if self.delta_nu == 0:
            return k_fwd / keq_kp
        keq_kc = keq_kp / (RT_per_Pstd ** self.delta_nu)
        if keq_kc <= 0:
            return None
        return k_fwd / keq_kc

    def _orders_dict(self) -> Dict[str, float]:
        """Devuelve dict de órdenes de reacción por reactante.  Si
        self.orders está vacío, asume estequiométrico (|νᵢ|)."""
        if self.orders:
            return dict(self.orders)
        return {s.formula: float(abs(s.nu)) for s in self.reactants()}

    def _product_orders(self) -> Dict[str, float]:
        """Órdenes de productos (para el término reverso). Asume
        estequiométrico (|νⱼ|) — Capa 5 v1.0 no permite órdenes
        reversos personalizados (raramente reportados)."""
        return {s.formula: float(abs(s.nu)) for s in self.products()}

    def rate_forward(self, T_K: float,
                      concentrations: Dict[str, float]) -> Optional[float]:
        """Velocidad de reacción forward: r_fwd = k(T) · ∏ [Cᵢ]^nᵢ

        concentrations: dict {formula: valor}.  Las unidades deben
        coincidir con uses_partial_pressure: si True → bar, si False
        → mol/m³ (default).  Devuelve r en las unidades de k₀.
        Componentes faltantes se asumen [C]=0 → r_fwd=0.
        """
        k = self.k_arrhenius(T_K)
        if k is None:
            return None
        orders = self._orders_dict()
        r = k
        for formula, n in orders.items():
            c = concentrations.get(formula, 0.0)
            if c < 0:
                return None
            if c == 0 and n > 0:
                return 0.0
            r *= c ** n
        return r

    def rate_reverse(self, T_K: float,
                      concentrations: Dict[str, float]) -> Optional[float]:
        """Velocidad reversa via equilibrio detallado: r_rev =
        k_rev(T) · ∏ [Pⱼ]^|νⱼ|.  Devuelve 0 si irreversible."""
        if self.irreversible:
            return 0.0
        k_rev = self.k_reverse(T_K)
        if k_rev is None:
            return None
        orders = self._product_orders()
        r = k_rev
        for formula, n in orders.items():
            c = concentrations.get(formula, 0.0)
            if c < 0:
                return None
            if c == 0 and n > 0:
                return 0.0
            r *= c ** n
        return r

    def rate_net(self, T_K: float,
                  concentrations: Dict[str, float]) -> Optional[float]:
        """Velocidad neta: r_net = r_fwd - r_rev.  Positivo → la
        reacción avanza hacia productos; negativo → hacia reactantes
        (caso productos en exceso de equilibrio)."""
        rf = self.rate_forward(T_K, concentrations)
        if rf is None:
            return None
        rr = self.rate_reverse(T_K, concentrations)
        if rr is None:
            return rf      # irreversible o sin Keq → solo forward
        return rf - rr

    def is_kinetic_T_valid(self, T_K: float) -> bool:
        """True si T_K está dentro del rango de validez de la cinética
        publicada.  Fuera del rango la Arrhenius extrapolada puede ser
        irrealista — el caller decide qué hacer (warning, error)."""
        if not self.kinetics_available:
            return False
        if self.kin_T_min_K is not None and T_K < self.kin_T_min_K:
            return False
        if self.kin_T_max_K is not None and T_K > self.kin_T_max_K:
            return False
        return True

    def is_thermodynamically_consistent(self) -> bool:
        """True si los órdenes cinéticos coinciden con la estequiometría
        (|νᵢ| para reactantes).  Solo en ese caso el equilibrio
        detallado simple `k_rev = k_fwd/Keq` da r_net=0 en equilibrio.

        Falsea para cinéticas no-estequiométricas como Temkin-Pyzhev
        (R004 Haber: orden N2=1, H2=1.5 vs ν=1, 3) o Eley-Rideal con
        adsorción saturada.  En esos casos:
          · el modelo Arrhenius simple captura el ORDEN de magnitud
          · pero r_net en (cerca de) equilibrio tiene desvío sistemático
          · NO usar para diseño fino de reactores cerca de equilibrio
            (usar el modelo cinético completo publicado).

        El módulo solo lo marca como flag — no rechaza el cálculo.
        """
        if not self.kinetics_available or not self.orders:
            return False
        for sp in self.reactants():
            expected = float(abs(sp.nu))
            actual = self.orders.get(sp.formula, expected)
            if abs(actual - expected) > 1e-9:
                return False
        return True


# ============================================================
# Parser
# ============================================================
_DB: Optional[Dict[str, Reaction]] = None
_DB_PATH = Path(__file__).parent / "data" / "reactions_db.md"


_KINETICS_PATH = Path(__file__).parent / "data" / "kinetics_db.md"


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
    # Merge cinéticas Capa 5 si el archivo existe
    if _KINETICS_PATH.is_file():
        _merge_kinetics(out, _KINETICS_PATH.read_text(encoding="utf-8"))
    return out


def _merge_kinetics(reactions: Dict[str, Reaction], text: str) -> None:
    """Lee el .md de cinéticas y rellena los campos de cada Reaction
    (k0, Ea, orders, rate_law, etc).  Reacciones no listadas en el
    .md cinético quedan con kinetics_available=False."""
    sections = re.split(r"^## (R\d{3})", text, flags=re.MULTILINE)
    for i in range(1, len(sections), 2):
        rxn_id = sections[i].strip()
        body = sections[i + 1] if i + 1 < len(sections) else ""
        # Cortar body en la siguiente sección ## que NO sea Rxxx
        # (para que la última Rxxx no absorba texto explicativo del
        # final del .md, donde aparecen 'orden X=N' como ejemplos).
        next_section = re.search(r"^## ", body, flags=re.MULTILINE)
        if next_section:
            body = body[:next_section.start()]
        rxn = reactions.get(rxn_id)
        if rxn is None:
            continue
        _parse_kinetics_section(rxn, body)


def _parse_kinetics_section(rxn: Reaction, body: str) -> None:
    """Parsea una sección Rxxx del .md cinético y popula rxn."""
    # Catalizador
    m = re.search(r"\*\*Catalizador:\*\*\s*([^\n]+)", body)
    if m: rxn.catalyst = m.group(1).strip()

    # Tipo (rate_law), formato: **Tipo:** `elemental` ...
    m = re.search(r"\*\*Tipo:\*\*\s*`([^`]+)`", body)
    if m: rxn.rate_law = m.group(1).strip()

    # Rango T válido: '600–800 K' o '600-800 K'
    m = re.search(r"\*\*Rango T válido:\*\*\s*(\d+)\s*[-–]\s*(\d+)\s*K", body)
    if m:
        rxn.kin_T_min_K = float(m.group(1))
        rxn.kin_T_max_K = float(m.group(2))

    # k₀: bullet point '- k₀ = X.Y[e+N]  unit'
    # Captura número en notación científica y la unidad para detectar
    # rate_basis y uses_partial_pressure.
    m = re.search(r"-\s*k₀\s*=\s*([+-]?[\d.]+(?:[eE][+-]?\d+)?)\s*([^\n]*)", body)
    if m:
        rxn.k0 = float(m.group(1))
        unit_str = m.group(2).strip().lower()
        # Basis: 'kg_cat' en unidades → rate_basis='cat_mass'
        if 'kg_cat' in unit_str:
            rxn.rate_basis = 'cat_mass'
        else:
            rxn.rate_basis = 'volume'
        # uses_partial_pressure: 'bar' presente y no 'bar^0'
        if 'bar' in unit_str:
            rxn.uses_partial_pressure = True

    # Ea: '- Ea = Z kJ/mol'
    m = re.search(r"-\s*Ea\s*=\s*([+-]?[\d.]+)\s*kJ/mol", body)
    if m: rxn.Ea_kJ_mol = float(m.group(1))

    # Órdenes: '- orden XXX = N' (puede ser varios)
    # Acepta enteros y decimales. Múltiples en la misma línea separados
    # por coma: '- orden CO = 1, orden H2O = 1'
    orders = {}
    for om in re.finditer(r"orden\s+([A-Za-z0-9_()]+)\s*=\s*([+-]?[\d.]+)",
                           body, flags=re.IGNORECASE):
        formula = om.group(1).strip()
        order   = float(om.group(2))
        orders[formula] = order
    if orders:
        rxn.orders = orders

    # ρ_b: '- ρ_b = N kg_cat/m³_reactor' (o '≈' en vez de '=')
    m = re.search(r"ρ_b\s*[≈=]\s*([+-]?[\d.]+)\s*kg_cat", body)
    if m: rxn.rho_b_cat = float(m.group(1))

    # Marca como disponible si tiene al menos k0 y Ea
    rxn.kinetics_available = (rxn.k0 is not None and rxn.Ea_kJ_mol is not None)


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


# ============================================================
# REACCIONES CUSTOM (in-memory, definidas por el usuario)
# ============================================================
# Permite que el usuario defina una reacción nueva con su propia
# estequiometría + ΔH298 + (ΔS298 o Keq298), sin tocar el catálogo
# read-only data/reactions_db.md.  La instancia Reaction resultante
# es 100% compatible con solve_multi_reaction_equilibrium (que ya
# trabaja con cualquier objeto Reaction, no asume que venga del .md).
# ============================================================

import math as _math


def reaction_from_dict(d: dict) -> Reaction:
    """Construye un objeto Reaction in-memory desde un dict del usuario.

    Esquema del dict:
        {
          "id":                 "CUSTOM-1",
          "name":               "A + B -> C",
          "stoich":             [{"formula":"A","phase":"g","nu":-1}, ...],
          "dh_rxn_298_kJ_mol":  float (obligatorio),
          "ds_rxn_298_J_mol_K": float (opcional — uno de los dos),
          "keq_298":            float (opcional — uno de los dos),
          "T_min_K":            float (opcional, default 298.15),
          "T_max_K":            float (opcional, default 2000.0),
          "irreversible":       bool  (opcional, default False),
        }

    Deriva los coeficientes vant_hoff_A/B (ln Keq = A + B/T) desde:
        B = -ΔH / R                                      [K]
        A = ΔS / R                                       (si ΔS dado)
        A = ln(Keq298) + ΔH/(R·298.15)                   (si Keq298 dado)

    Sin requerir thermo_db (las especies pueden ser inventadas; cae a
    la forma 2-parámetros igual que R022-R025 NO derivadas).

    Validaciones (ValueError con mensaje claro, NO crashear):
      · stoich no vacía.
      · Al menos UN reactante (ν<0) y UN producto (ν>0).
      · ΔH numérico finito.
      · Exactamente UNO de {ds_rxn_298_J_mol_K, keq_298} provisto.
      · Estequiometría balanceada por elementos (best-effort: si
        las fórmulas son parseables como combinación de elementos,
        chequea Σ nᵢ·νᵢ = 0 por elemento; si los strings son
        pseudo-componentes no parseables, SOLO advierte en el msg).

    Returns:
        Reaction con vant_hoff_A/B derivados, derivable_capa3=False
        (es custom), kinetics_available=False (sin Arrhenius).
    """
    R = 8.314462618    # J/(mol·K)

    if not isinstance(d, dict):
        raise ValueError("reaction_from_dict: argumento debe ser dict.")

    stoich_raw = d.get("stoich") or []
    if not stoich_raw:
        raise ValueError("Estequiometría vacía: definir al menos un "
                          "reactante (ν<0) y un producto (ν>0).")
    stoich: List[StoichEntry] = []
    for e in stoich_raw:
        if not isinstance(e, dict):
            raise ValueError(f"Stoich entry inválida: {e!r}")
        try:
            nu = int(e.get("nu", 0))
        except (TypeError, ValueError):
            raise ValueError(f"ν no es entero: {e!r}")
        if nu == 0:
            raise ValueError(f"ν=0 no permitido en {e!r}.")
        formula = str(e.get("formula") or "").strip()
        phase   = str(e.get("phase")   or "g").strip().lower()
        if not formula:
            raise ValueError(f"Falta 'formula' en {e!r}.")
        if phase not in ("g", "l", "aq", "s"):
            raise ValueError(f"phase '{phase}' inválida (use g|l|aq|s).")
        stoich.append(StoichEntry(formula=formula, phase=phase, nu=nu))
    if not any(s.nu < 0 for s in stoich):
        raise ValueError("Falta reactante (ningún ν<0).")
    if not any(s.nu > 0 for s in stoich):
        raise ValueError("Falta producto (ningún ν>0).")

    # Balance por elementos (best-effort).  Si todas las fórmulas son
    # parseables → debe cuadrar; si alguna no, advertimos en el msg
    # del bloque global de validación (no crasheamos).
    _check_element_balance(stoich)

    # ΔH obligatorio
    try:
        dh = float(d["dh_rxn_298_kJ_mol"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("dh_rxn_298_kJ_mol obligatorio (kJ/mol, "
                          "numérico finito).")
    if not _math.isfinite(dh):
        raise ValueError("dh_rxn_298_kJ_mol debe ser finito.")

    # Uno de {ΔS, Keq298} mutuamente excluyentes
    has_ds  = ("ds_rxn_298_J_mol_K" in d and d["ds_rxn_298_J_mol_K"] is not None)
    has_keq = ("keq_298" in d and d["keq_298"] is not None)
    if has_ds and has_keq:
        raise ValueError("Provee ds_rxn_298_J_mol_K O keq_298, no ambos.")
    if not (has_ds or has_keq) and not d.get("irreversible", False):
        raise ValueError("Reacción reversible: indicar ds_rxn_298_J_mol_K "
                          "O keq_298.  (O usar irreversible=True para "
                          "conversión declarada.)")

    # Derivar vant_hoff_A, B (ln Keq = A + B/T)
    #   B = -ΔH / R                      en Kelvin
    #   ΔH viene en kJ/mol → pasar a J
    dh_J = dh * 1000.0
    B = -dh_J / R
    if has_ds:
        ds = float(d["ds_rxn_298_J_mol_K"])
        A = ds / R
        dg = dh - ds * 298.15 / 1000.0       # kJ/mol
    elif has_keq:
        keq298 = float(d["keq_298"])
        if keq298 <= 0:
            raise ValueError("keq_298 debe ser > 0 para tomar ln.")
        # ln(Keq298) = A + B/298.15  →  A = ln(K) - B/298.15
        A = _math.log(keq298) - B / 298.15
        ds_derived = A * R
        dg = dh - ds_derived * 298.15 / 1000.0
    else:
        # Irreversible: A/B no usados; calcular como Keq → ∞ a 298.
        A = 0.0
        ds_derived = None
        dg = None

    # Build Reaction
    rxn_id   = str(d.get("id")   or "CUSTOM-?")
    rxn_name = str(d.get("name") or f"Custom {rxn_id}")
    T_min    = float(d.get("T_min_K", 298.15))
    T_max    = float(d.get("T_max_K", 2000.0))
    irrev    = bool(d.get("irreversible", False))

    # delta_nu = Σ ν_i (cambio de moles totales)
    delta_nu = sum(s.nu for s in stoich)

    return Reaction(
        id=rxn_id, name=rxn_name,
        category="custom",
        stoich=stoich,
        delta_nu=delta_nu,
        phase_global=_global_phase_from_stoich(stoich),
        T_min_K=T_min, T_max_K=T_max,
        dh_rxn_298_kJ_mol=dh,
        ds_rxn_298_J_mol_K=(ds_derived if has_keq else (float(d["ds_rxn_298_J_mol_K"]) if has_ds else None)),
        dg_rxn_298_kJ_mol=dg,
        vant_hoff_A=A,
        vant_hoff_B=B,
        irreversible=irrev,
        derivable_capa3=False,
        comments=("Reacción custom in-memory.  Keq(T) usa forma 2-param "
                   "(ΔCp=0); error crece a T lejana de 298 K."),
        kinetics_available=False,
    )


_ELEMENT_RE = None
def _check_element_balance(stoich: List[StoichEntry]):
    """Best-effort: parsea fórmulas tipo C2H6, H2O, CaCO3 como dict
    {element: count} y verifica Σ nᵢ·νᵢ = 0 por elemento.  Si alguna
    fórmula no es parseable (pseudo-componente "polyethylene", etc.),
    saltea la validación silenciosamente (responsabilidad del user)."""
    global _ELEMENT_RE
    if _ELEMENT_RE is None:
        import re
        _ELEMENT_RE = re.compile(r"([A-Z][a-z]?)(\d*)")
    counts: Dict[str, float] = {}
    for s in stoich:
        # Solo parsear fórmulas que se parecen a química real
        f = s.formula
        if not f or not f[0].isupper():
            return     # no parseable → no validar
        elems = _ELEMENT_RE.findall(f)
        # findall siempre devuelve algo; verificar que TODO el string
        # se haya consumido por matches (sino hay caracteres raros).
        if "".join(e + n for e, n in elems) != f:
            return
        for el, n in elems:
            if not el:
                continue
            n_i = int(n) if n else 1
            counts[el] = counts.get(el, 0) + s.nu * n_i
    for el, total in counts.items():
        if abs(total) > 1e-9:
            raise ValueError(
                f"Estequiometría desbalanceada en {el}: Σ ν·n = {total} "
                f"(debe ser 0).  Revisar coeficientes."
            )


def _global_phase_from_stoich(stoich: List[StoichEntry]) -> str:
    phases = {s.phase for s in stoich}
    if phases == {"g"}: return "gas"
    if phases == {"l"}: return "líquido"
    if phases == {"aq"}: return "acuoso"
    if phases == {"s"}: return "sólido"
    return "heterogéneo"


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


def solve_stoichiometric_reactor(
        rxn_ids:           List[str],
        inlet_composition: Dict[str, float],
        inlet_mass_kg_s:   float,
        T_K:               float,
        P_bar:             float = 1.0,
        conversion:        float = 0.95) -> Optional[Dict]:
    """Aplica la PRIMERA reacción del set al reactivo limitante con la
    conversión declarada (0..1), sin Keq ni cinética.  Para reacciones
    irreversibles / biológicas / con termo estimada donde el equilibrio
    no aplica (R007 fermentación, R021 transesterificación).

    Mismo contrato de salida que solve_equilibrium_reactor_from_composition:
        outlet_composition, outlet_mass_kg_s, heat_of_reaction_kJ_per_kg,
        duty_kW, xi, unmapped.
    heat_of_reaction usa ΔH(T) (Kirchhoff vía Reaction.dh_rxn_kJ_mol, con
    fallback a ΔH_298).  None si falta thermo_db o no hay reactivos válidos.
    """
    try:
        import thermo_db as _td
    except ImportError:
        return None
    if not rxn_ids:
        return None
    rxn = get(rxn_ids[0])
    if rxn is None or not rxn.stoich:
        return None
    conv = max(0.0, min(1.0, float(conversion)))

    total_frac = sum(v for v in inlet_composition.values() if v > 0)
    if total_frac <= 0:
        return None
    norm_comp = {k: v / total_frac for k, v in inlet_composition.items() if v > 0}

    feed_moles: Dict[str, float] = {}
    inert_mass_per_s: Dict[str, float] = {}
    unmapped: List[str] = []
    for thermo_n, frac in norm_comp.items():
        m_kg_per_s = frac * inlet_mass_kg_s
        formula = formula_for(thermo_n)
        comp_obj = _td.get(thermo_n)
        if comp_obj is None or comp_obj.mw <= 0 or formula is None:
            inert_mass_per_s[thermo_n] = (inert_mass_per_s.get(thermo_n, 0.0)
                                          + m_kg_per_s)
            if formula is None:
                unmapped.append(thermo_n)
            continue
        feed_moles[formula] = (feed_moles.get(formula, 0.0)
                               + m_kg_per_s * 1000.0 / comp_obj.mw)
    if not feed_moles:
        return None

    # Reactivo limitante: min(moles_disponibles / |ν|) entre los reactivos
    # presentes en el feed.
    ratios = []
    for e in rxn.stoich:
        if e.nu < 0:
            avail = feed_moles.get(e.formula, 0.0)
            ratios.append(avail / float(-e.nu))
    if not ratios:
        return None
    xi = conv * min(ratios)        # extent [mol/s]
    if xi < 0:
        xi = 0.0

    moles_out: Dict[str, float] = dict(feed_moles)
    for e in rxn.stoich:
        moles_out[e.formula] = max(0.0, moles_out.get(e.formula, 0.0)
                                   + e.nu * xi)

    outlet_mass_per_s: Dict[str, float] = {}
    for formula, mol_per_s in moles_out.items():
        if mol_per_s < 1e-15:
            continue
        thermo_n = thermo_name(formula)
        if thermo_n is None:
            continue
        comp_obj = _td.get(thermo_n)
        if comp_obj is None or comp_obj.mw <= 0:
            continue
        outlet_mass_per_s[thermo_n] = (outlet_mass_per_s.get(thermo_n, 0.0)
                                       + mol_per_s * comp_obj.mw / 1000.0)
    for thermo_n, m in inert_mass_per_s.items():
        outlet_mass_per_s[thermo_n] = outlet_mass_per_s.get(thermo_n, 0.0) + m

    dh_T = rxn.dh_rxn_kJ_mol(T_K)
    if dh_T is None:
        dh_T = rxn.dh_rxn_298_kJ_mol
    dh_total_kW = dh_T * xi          # kJ/mol · mol/s = kW
    heat_of_reaction_kJ_per_kg = (dh_total_kW / inlet_mass_kg_s
                                  if inlet_mass_kg_s > 0 else 0.0)

    total_out = sum(outlet_mass_per_s.values())
    outlet_composition = ({k: v / total_out for k, v in outlet_mass_per_s.items()}
                          if total_out > 0 else {})

    return dict(
        outlet_composition=outlet_composition,
        outlet_mass_kg_s=total_out,
        heat_of_reaction_kJ_per_kg=heat_of_reaction_kJ_per_kg,
        duty_kW=dh_total_kW,
        xi={rxn.id: xi},
        unmapped=unmapped,
    )


# ============================================================
# CAPA 5 FASE B — Solvers PFR y CSTR (isothermal, isobaric)
# ============================================================
#
# Reactor PFR (plug flow):
#   ODE de balance molar:  dFᵢ/dV = Σⱼ νᵢⱼ · rⱼ(C(V))
#   Integración RK4 con paso fijo desde V=0 (F=F_in) hasta V=V_reactor.
#
# Reactor CSTR (perfectly mixed):
#   Algebraico:  Fᵢ_out - Fᵢ_in - Σⱼ νᵢⱼ · rⱼ(C_out) · V = 0
#   En términos de extents ξⱼ:  ξⱼ = rⱼ(C(ξ)) · V  para j=1..N_rxn
#   Sistema no-lineal resuelto por Newton-Raphson con Jacobiano FD.
#
# Hipótesis:
#   · Isothermal (T fija en todo el reactor)
#   · Isobaric (P fija; afecta solo conversión C↔p si la cinética
#     usa presiones parciales)
#   · Fase gas ideal (Q = F_total·RT/P para conversión F → C)
#   · Sin difusión, sin gradientes radiales
#   · Steady state
#
# Mezcla de cinéticas:
#   · Todas las reacciones del set deben usar el mismo basis
#     (todas en mol/m³, o todas en bar).  Si mezclás, lanza error.
#     (e.g. R003 SMR usa bar + R002 WGS usa mol/m³ → INCOMPATIBLE;
#     resolver SMR solo, o usar mode='equilibrium' para acoplar.)
#   · Si alguna reacción tiene rate_basis='cat_mass', el solver
#     espera además ρ_b (default toma el primer ρ_b no-None del set).
#     Convierte r [mol/(kg_cat·s)] · ρ_b [kg_cat/m³_R] = r [mol/(m³_R·s)].
#
# Limitations conocidas:
#   · PFR con RK4 paso fijo subestima conversión para cinéticas
#     extremadamente rápidas (stiff): R003 SMR @ 1100K, R004 Haber
#     @ 700K, R005 MeOH @ 525K.  Para estos casos usar CSTR
#     (algebraico, robusto) o mode='equilibrium' (Capa 4).
#   · Validado contra equilibrio termo Capa 4:
#       PFR  R002 WGS @700K V=5L:    conv=73.26% ≡ equilibrio ✓
#       PFR  R011 cracking @1100K V=50L: conv=50.84% ≡ equilibrio 50.85% ✓
#       PFR  R012 dehydro @870K V=50m³:  conv=36.08% ≡ equilibrio 36.10% ✓
#       CSTR R003 SMR @1100K V=10L: conv=47.83% ≡ equilibrio 47.84% ✓


def _check_kinetics_compatibility(rxn_ids: List[str]) -> Optional[str]:
    """Verifica que el set de reacciones tenga cinéticas compatibles
    (mismo basis, mismo uses_partial_pressure).  Devuelve mensaje
    de error o None si OK."""
    if not rxn_ids:
        return "Sin reacciones declaradas"
    use_pp = None
    for rid in rxn_ids:
        r = get(rid)
        if r is None:
            return f"Reacción {rid} no existe"
        if not r.kinetics_available:
            return f"Reacción {rid} sin cinética (Capa 5 FASE A no la cubre)"
        if use_pp is None:
            use_pp = r.uses_partial_pressure
        elif r.uses_partial_pressure != use_pp:
            return (f"Cinéticas mezclan unidades — {rid} usa "
                     f"{'bar' if r.uses_partial_pressure else 'mol/m³'} "
                     f"pero otras usan lo contrario")
    return None


def _concentrations(F: Dict[str, float], T_K: float, P_bar: float,
                    uses_pp: bool) -> Dict[str, float]:
    """Convierte flujos molares F [mol/s] a concentraciones (gas ideal).

    Si uses_pp=True: devuelve presiones parciales [bar].
       pᵢ = yᵢ · P_total = (Fᵢ/F_tot) · P_bar
    Si uses_pp=False: devuelve concentraciones [mol/m³].
       Cᵢ = Fᵢ / Q  donde Q = F_tot · RT/P  (gas ideal)
       Q [m³/s] = F_tot [mol/s] · 8.314 [J/(mol·K)] · T [K] / (P_bar · 1e5 [Pa])
    """
    F_tot = sum(max(v, 0.0) for v in F.values())
    if F_tot <= 0:
        return {k: 0.0 for k in F}
    if uses_pp:
        return {k: (max(v, 0.0) / F_tot) * P_bar for k, v in F.items()}
    # mol/m³ via Q = F·RT/P
    Q_m3_s = F_tot * R_GAS * T_K / (P_bar * 1e5)
    if Q_m3_s <= 0:
        return {k: 0.0 for k in F}
    return {k: max(v, 0.0) / Q_m3_s for k, v in F.items()}


def _net_generation_per_species(rxn_ids: List[str], F: Dict[str, float],
                                  T_K: float, P_bar: float,
                                  uses_pp: bool,
                                  rho_b: Optional[float]) -> Dict[str, float]:
    """Devuelve dG/dV [mol/(m³·s)] por especie: Σⱼ νᵢⱼ · rⱼ.

    Para reacciones con basis='cat_mass', multiplica r por ρ_b
    para llevar a base volumen del reactor.
    """
    conc = _concentrations(F, T_K, P_bar, uses_pp)
    species_set = set(F.keys())
    # Inicializo todas las especies en 0
    dG = {k: 0.0 for k in species_set}
    for rid in rxn_ids:
        rxn = get(rid)
        if rxn is None:
            continue
        r = rxn.rate_net(T_K, conc)
        if r is None:
            return None
        # Si la reacción está en base cat_mass, convertir con ρ_b
        if rxn.rate_basis == 'cat_mass':
            if rho_b is None:
                return None
            r = r * rho_b   # mol/(kg_cat·s) · kg_cat/m³ = mol/(m³·s)
        for sp in rxn.stoich:
            if sp.formula not in dG:
                dG[sp.formula] = 0.0
            dG[sp.formula] += sp.nu * r
    return dG


def _concentrations_batch(N: Dict[str, float], V_R_m3: float,
                          T_K: float, uses_pp: bool) -> Dict[str, float]:
    """Concentraciones/presiones parciales en un reactor BATCH a
    VOLUMEN CONSTANTE.

    A diferencia de _concentrations (flujo: C = F/Q con Q = F·RT/P),
    el batch tiene N moles encerrados en V_R fijo:
        Cᵢ = Nᵢ / V_R                         [mol/m³]
        pᵢ = Cᵢ·R·T = (Nᵢ/V_R)·R·T  →  bar   (gas ideal, P emergente)

    La presión total NO es constante: P(t) = N_tot(t)·R·T / V_R.
    Esto es lo que distingue físicamente un batch de un PFR/CSTR
    y por qué necesita su propio cálculo (no reinterpretar el PFR).
    """
    if V_R_m3 <= 0:
        return {k: 0.0 for k in N}
    C = {k: max(v, 0.0) / V_R_m3 for k, v in N.items()}     # mol/m³
    if not uses_pp:
        return C
    # cinética en presión parcial [bar]: pᵢ = Cᵢ·R·T  (Pa→bar)
    return {k: c * R_GAS * T_K / 1e5 for k, c in C.items()}


def _net_generation_batch(rxn_ids: List[str], N: Dict[str, float],
                          V_R_m3: float, T_K: float, uses_pp: bool,
                          rho_b: Optional[float]) -> Optional[Dict[str, float]]:
    """dNᵢ/dt [mol/s] = V_R · Σⱼ νᵢⱼ·rⱼ(C_batch).

    Igual estructura que _net_generation_per_species pero:
      · concentración batch (Nᵢ/V_R, no Fᵢ/Q)
      · multiplica por V_R para pasar de r [mol/(m³·s)] a dN/dt
        [mol/s] (el batch balancea moles totales, no densidad de flujo)
    """
    conc = _concentrations_batch(N, V_R_m3, T_K, uses_pp)
    dN = {k: 0.0 for k in N}
    for rid in rxn_ids:
        rxn = get(rid)
        if rxn is None:
            continue
        r = rxn.rate_net(T_K, conc)
        if r is None:
            return None
        if rxn.rate_basis == 'cat_mass':
            if rho_b is None:
                return None
            r = r * rho_b                 # mol/(m³·s)
        for sp in rxn.stoich:
            if sp.formula not in dN:
                dN[sp.formula] = 0.0
            dN[sp.formula] += sp.nu * r * V_R_m3    # · V_R → mol/s
    return dN


def solve_batch(rxn_ids:   List[str],
                N_in:       Dict[str, float],
                T_K:        float,
                P0_bar:     float,
                V_R_m3:     float,
                t_batch_s:  float,
                n_steps:    int = 500,
                rho_b:      Optional[float] = None,
                ) -> Optional[Dict]:
    """Reactor BATCH isotérmico, volumen constante, gas ideal.

    Integra dNᵢ/dt = V_R·Σⱼ νᵢⱼ·rⱼ con RK4 paso fijo desde t=0
    hasta t_batch_s.  La presión NO es constante: se reporta P(t)
    emergente de N_tot(t)·R·T/V_R.

    Args:
        rxn_ids:    reacciones (deben tener cinética disponible)
        N_in:       {formula: moles} carga inicial (NO flujo — moles)
        T_K:        temperatura isoterma
        P0_bar:     presión inicial (informativa; V_R fija la física.
                    Se usa solo para validar/registrar el estado t=0)
        V_R_m3:     volumen del reactor [m³] (constante)
        t_batch_s:  tiempo total de reacción [s]
        n_steps:    pasos RK4

    Returns dict:
        'N_out':       {formula: moles} al final
        'conversion':  {formula: frac} por reactante (solo positivo)
        't_batch_s':   tiempo total
        'P_final_bar': presión al final (emergente)
        'profile_t':   [t0, t1, ..., t_N] s
        'profile_N':   list de {formula: moles} en cada t
        'profile_P':   [P0, ..., P_final] bar  (presión emergente)
        None si cinética inválida / T fuera de rango / V<=0 / t<=0.
    """
    err = _check_kinetics_compatibility(rxn_ids)
    if err is not None:
        return None
    if V_R_m3 <= 0 or t_batch_s <= 0:
        return None
    if rho_b is None:
        for rid in rxn_ids:
            r = get(rid)
            if r and r.rho_b_cat:
                rho_b = r.rho_b_cat
                break
    species = set(N_in.keys())
    for rid in rxn_ids:
        r = get(rid)
        if r is None:
            return None
        for sp in r.stoich:
            species.add(sp.formula)
    N = {s: float(N_in.get(s, 0.0)) for s in species}
    rxns = [get(rid) for rid in rxn_ids]
    uses_pp = rxns[0].uses_partial_pressure

    def _P_bar(state):
        n_tot = sum(max(v, 0.0) for v in state.values())
        return n_tot * R_GAS * T_K / V_R_m3 / 1e5

    dt = t_batch_s / n_steps
    profile_t = [0.0]
    profile_N = [dict(N)]
    profile_P = [_P_bar(N)]

    def _deriv(state):
        return _net_generation_batch(rxn_ids, state, V_R_m3,
                                     T_K, uses_pp, rho_b)

    for step in range(n_steps):
        k1 = _deriv(N)
        if k1 is None:
            return None
        N2 = {k: max(N[k] + 0.5*dt*k1[k], 0.0) for k in species}
        k2 = _deriv(N2)
        if k2 is None:
            return None
        N3 = {k: max(N[k] + 0.5*dt*k2[k], 0.0) for k in species}
        k3 = _deriv(N3)
        if k3 is None:
            return None
        N4 = {k: max(N[k] + dt*k3[k], 0.0) for k in species}
        k4 = _deriv(N4)
        if k4 is None:
            return None
        N = {k: max(N[k] + dt/6.0*(k1[k] + 2*k2[k] + 2*k3[k] + k4[k]), 0.0)
             for k in species}
        profile_t.append((step + 1) * dt)
        profile_N.append(dict(N))
        profile_P.append(_P_bar(N))

    conv = {}
    for sp in species:
        Nin = N_in.get(sp, 0.0)
        if Nin > 1e-12:
            x = (Nin - N[sp]) / Nin
            if x > 1e-9:
                conv[sp] = x
    return dict(
        N_out=N,
        conversion=conv,
        t_batch_s=t_batch_s,
        P_final_bar=profile_P[-1],
        profile_t=profile_t,
        profile_N=profile_N,
        profile_P=profile_P,
    )


def solve_pfr(rxn_ids:    List[str],
              F_in:       Dict[str, float],
              T_K:        float,
              P_bar:      float,
              V_reactor:  float,
              n_steps:    int   = 200,
              rho_b:      Optional[float] = None,
              ) -> Optional[Dict]:
    """Resuelve un PFR isothermal, isobaric con cinética Arrhenius.

    Args:
        rxn_ids:    reacciones (e.g. ['R002', 'R003'])
        F_in:       {formula: mol/s} flujos molares de entrada
        T_K, P_bar: condiciones de operación
        V_reactor:  volumen total del reactor [m³]
        n_steps:    pasos de integración RK4 (default 200, sube si
                    la cinética es muy rápida y el paso causa
                    sobre-shoot)
        rho_b:      ρ_b [kg_cat/m³] si las cinéticas son 'cat_mass'.
                    Si None, se toma el primer rho_b_cat no-None
                    declarado en las reacciones.

    Returns:
        dict con:
          'F_out':       {formula: mol/s} salida
          'conversion':  {formula: float}  fracción reaccionada por
                          reactante (solo positivo)
          'tau_s':       tiempo de residencia τ = V / Q_in [s]
          'profile_V':   [V_0, V_1, ..., V_N] m³  (puntos de evaluación)
          'profile_F':   list de dict {formula: F} en cada V
          None si la cinética no es válida o T fuera de rango.
    """
    err = _check_kinetics_compatibility(rxn_ids)
    if err is not None:
        return None
    # Default rho_b
    if rho_b is None:
        for rid in rxn_ids:
            r = get(rid)
            if r and r.rho_b_cat:
                rho_b = r.rho_b_cat
                break

    # Coleccionar todas las especies involucradas
    species = set(F_in.keys())
    for rid in rxn_ids:
        r = get(rid)
        for sp in r.stoich:
            species.add(sp.formula)

    # Estado inicial
    F = {s: float(F_in.get(s, 0.0)) for s in species}
    rxns = [get(rid) for rid in rxn_ids]
    uses_pp = rxns[0].uses_partial_pressure

    # Q_in para τ
    F_tot_in = sum(F_in.values())
    Q_in_m3_s = F_tot_in * R_GAS * T_K / (P_bar * 1e5)
    tau_s = V_reactor / Q_in_m3_s if Q_in_m3_s > 0 else None

    # Integración RK4
    dV = V_reactor / n_steps
    profile_V = [0.0]
    profile_F = [dict(F)]

    def _deriv(F_state: Dict[str, float]) -> Optional[Dict[str, float]]:
        return _net_generation_per_species(rxn_ids, F_state,
                                            T_K, P_bar, uses_pp, rho_b)

    for step in range(n_steps):
        k1 = _deriv(F)
        if k1 is None:
            return None
        F_2 = {k: max(F[k] + 0.5 * dV * k1[k], 0.0) for k in species}
        k2 = _deriv(F_2)
        if k2 is None:
            return None
        F_3 = {k: max(F[k] + 0.5 * dV * k2[k], 0.0) for k in species}
        k3 = _deriv(F_3)
        if k3 is None:
            return None
        F_4 = {k: max(F[k] + dV * k3[k], 0.0) for k in species}
        k4 = _deriv(F_4)
        if k4 is None:
            return None
        F = {k: max(F[k] + dV/6.0 * (k1[k] + 2*k2[k] + 2*k3[k] + k4[k]), 0.0)
             for k in species}
        profile_V.append((step + 1) * dV)
        profile_F.append(dict(F))

    # Conversiones de reactantes
    conv = {}
    for sp in species:
        Fin = F_in.get(sp, 0.0)
        if Fin > 1e-12:
            x = (Fin - F[sp]) / Fin
            if x > 1e-9:    # solo conversiones positivas (= reactantes)
                conv[sp] = x
    return dict(
        F_out=F,
        conversion=conv,
        tau_s=tau_s,
        profile_V=profile_V,
        profile_F=profile_F,
    )


def solve_cstr(rxn_ids:    List[str],
                F_in:       Dict[str, float],
                T_K:        float,
                P_bar:      float,
                V_reactor:  float,
                max_iter:   int   = 100,
                tol:        float = 1e-8,
                rho_b:      Optional[float] = None,
                ) -> Optional[Dict]:
    """Resuelve un CSTR isothermal, isobaric con cinética Arrhenius.

    Sistema algebraico: para cada reacción j del set, encontrar ξⱼ
    tal que ξⱼ = rⱼ(F_out(ξ)) · V_reactor, donde
    Fᵢ_out = Fᵢ_in + Σⱼ νᵢⱼ ξⱼ.

    Newton-Raphson con Jacobiano por diferencias finitas + damping.

    Returns:
        dict con:
          'F_out': {formula: mol/s}
          'conversion': {formula: float}
          'tau_s': float (residencia nominal V/Q_in)
          'xi': {rxn_id: float (mol/s)}   extents
          'iterations': int
          'residual': float
        None si no converge.
    """
    err = _check_kinetics_compatibility(rxn_ids)
    if err is not None:
        return None
    if rho_b is None:
        for rid in rxn_ids:
            r = get(rid)
            if r and r.rho_b_cat:
                rho_b = r.rho_b_cat
                break

    rxns = [get(rid) for rid in rxn_ids]
    uses_pp = rxns[0].uses_partial_pressure
    N = len(rxns)

    species = set(F_in.keys())
    for r in rxns:
        for sp in r.stoich:
            species.add(sp.formula)
    species = list(species)
    sp_idx = {s: i for i, s in enumerate(species)}

    # Matriz estequiométrica ν[i, j]
    nu = [[0.0]*N for _ in species]
    for j, r in enumerate(rxns):
        for sp in r.stoich:
            nu[sp_idx[sp.formula]][j] = float(sp.nu)

    F_in_vec = [F_in.get(s, 0.0) for s in species]
    F_tot_in = sum(F_in_vec)
    Q_in_m3_s = F_tot_in * R_GAS * T_K / (P_bar * 1e5)
    tau_s = V_reactor / Q_in_m3_s if Q_in_m3_s > 0 else None

    def _F_from_xi(xi_vec):
        return {species[i]: max(F_in_vec[i] + sum(nu[i][j]*xi_vec[j]
                                                    for j in range(N)), 0.0)
                for i in range(len(species))}

    def _residual(xi_vec):
        """g_j(ξ) = ξⱼ - rⱼ(F(ξ)) · V"""
        F = _F_from_xi(xi_vec)
        conc = _concentrations(F, T_K, P_bar, uses_pp)
        g = []
        for j in range(N):
            r = rxns[j].rate_net(T_K, conc)
            if r is None:
                return None
            if rxns[j].rate_basis == 'cat_mass':
                if rho_b is None: return None
                r *= rho_b
            g.append(xi_vec[j] - r * V_reactor)
        return g

    # Initial guess: ξⱼ pequeño (~Q_in·tau·c_in_min)
    xi = [F_tot_in * 0.01 for _ in range(N)]

    last_norm = float('inf')
    iters = 0
    for it in range(max_iter):
        iters = it + 1
        g = _residual(xi)
        if g is None:
            return None
        norm = math.sqrt(sum(gi*gi for gi in g))
        last_norm = norm
        if norm < tol:
            break
        # Jacobiano por diferencias finitas
        eps_base = max(1e-4 * F_tot_in, 1e-10)
        J = [[0.0]*N for _ in range(N)]
        for k in range(N):
            xi_plus = list(xi)
            eps = max(eps_base, 1e-4 * abs(xi[k]))
            xi_plus[k] += eps
            g_plus = _residual(xi_plus)
            if g_plus is None:
                return None
            for j in range(N):
                J[j][k] = (g_plus[j] - g[j]) / eps
        rhs = [-gi for gi in g]
        dxi = _gauss_solve(J, rhs)
        if dxi is None:
            return None
        # Line search con damping
        alpha = 1.0
        for _ in range(30):
            xi_try = [xi[j] + alpha*dxi[j] for j in range(N)]
            # No permitir ξ que haga moles negativos
            F_try = _F_from_xi(xi_try)
            if any(v < -1e-9 for v in F_try.values()):
                alpha *= 0.5
                continue
            g_try = _residual(xi_try)
            if g_try is None:
                alpha *= 0.5
                continue
            norm_try = math.sqrt(sum(gi*gi for gi in g_try))
            if norm_try < norm * (1 - 1e-4*alpha) or alpha < 1e-8:
                xi = xi_try
                last_norm = norm_try
                break
            alpha *= 0.5
        else:
            break    # no mejora — devolver lo que haya

    if last_norm > 1.0:
        # Residuo grande — no convergió
        return None
    F_out = _F_from_xi(xi)
    conv = {}
    for i, s in enumerate(species):
        if F_in_vec[i] > 1e-12:
            x = (F_in_vec[i] - F_out[s]) / F_in_vec[i]
            if x > 1e-9:
                conv[s] = x
    return dict(
        F_out=F_out,
        conversion=conv,
        tau_s=tau_s,
        xi={rxn_ids[j]: xi[j] for j in range(N)},
        iterations=iters,
        residual=last_norm,
    )


# ============================================================
# Wrapper alto-nivel para PFR/CSTR desde composición másica
# ============================================================
# Paralelo a solve_equilibrium_reactor_from_composition().  Toma
# mass fractions + mass_kg/s + nombres canónicos thermo_db, hace
# las conversiones y devuelve mass fractions out + heat_of_reaction.
#
# El caller del flowsheet usa solve_reactor_from_composition() que
# despacha al modo correcto ('equilibrium' / 'pfr' / 'cstr').


def solve_kinetic_reactor_from_composition(
        mode:              str,             # 'pfr' | 'cstr'
        rxn_ids:           List[str],
        inlet_composition: Dict[str, float],
        inlet_mass_kg_s:   float,
        T_K:               float,
        P_bar:             float,
        V_reactor_L:       float,
        rho_b:             Optional[float] = None) -> Optional[Dict]:
    """Wrapper de solve_pfr/solve_cstr para usar desde el flowsheet.

    mode:               'pfr' o 'cstr'
    inlet_composition:  {thermo_name: mass_fraction}
    inlet_mass_kg_s:    kg/s
    V_reactor_L:        volumen en litros
    rho_b:              ρ_b cat (kg/m³_R), opcional

    Returns dict con la misma forma que
    solve_equilibrium_reactor_from_composition:
        outlet_composition: {thermo_name: mass_fraction}
        outlet_mass_kg_s
        heat_of_reaction_kJ_per_kg   (consistente con Block.heat_of_reaction)
        duty_kW
        xi
        unmapped
        tau_s                        (extra: residencia)
        conversion                   (extra: fracción reaccionada por especie)
    None si la cinética no se puede aplicar (T fuera de rango,
    inlets sin composition, mezcla incompatible de basis...).
    """
    if mode not in ("pfr", "cstr"):
        return None
    if V_reactor_L <= 0:
        return None
    try:
        import thermo_db as _td
    except ImportError:
        return None

    # Validar cinética disponible para todas las rxns
    err = _check_kinetics_compatibility(rxn_ids)
    if err is not None:
        return None
    # Validar T en rango
    for rid in rxn_ids:
        r = get(rid)
        if r and not r.is_kinetic_T_valid(T_K):
            return None

    # Convertir composición másica → flujos molares F_in [mol/s]
    F_in: Dict[str, float] = {}
    inert_mass_per_s: Dict[str, float] = {}
    unmapped: List[str] = []
    total_frac = sum(inlet_composition.values())
    if total_frac <= 0:
        return None
    norm_comp = {k: v/total_frac for k, v in inlet_composition.items() if v > 0}

    for thermo_n, frac in norm_comp.items():
        m_kg_per_s = frac * inlet_mass_kg_s
        formula = formula_for(thermo_n)
        comp_obj = _td.get(thermo_n)
        if comp_obj is None or comp_obj.mw <= 0 or formula is None:
            inert_mass_per_s[thermo_n] = m_kg_per_s
            if formula is None:
                unmapped.append(thermo_n)
            continue
        moles_per_s = m_kg_per_s * 1000.0 / comp_obj.mw    # mol/s
        F_in[formula] = F_in.get(formula, 0.0) + moles_per_s

    if not F_in:
        return None

    V_m3 = V_reactor_L / 1000.0
    if mode == "pfr":
        res = solve_pfr(rxn_ids, F_in, T_K, P_bar, V_m3,
                         n_steps=500, rho_b=rho_b)
    else:    # cstr
        res = solve_cstr(rxn_ids, F_in, T_K, P_bar, V_m3, rho_b=rho_b)
    if res is None:
        return None

    # Convertir F_out → mass kg/s + composition
    outlet_mass_per_s: Dict[str, float] = {}
    for formula, mol_per_s in res['F_out'].items():
        if mol_per_s < 1e-15:
            continue
        thermo_n = thermo_name(formula)
        if thermo_n is None:
            continue
        comp_obj = _td.get(thermo_n)
        if comp_obj is None or comp_obj.mw <= 0:
            continue
        outlet_mass_per_s[thermo_n] = mol_per_s * comp_obj.mw / 1000.0
    # Sumar inertes
    for thermo_n, m in inert_mass_per_s.items():
        outlet_mass_per_s[thermo_n] = outlet_mass_per_s.get(thermo_n, 0.0) + m

    total_out = sum(outlet_mass_per_s.values())
    outlet_composition = ({k: v/total_out for k, v in outlet_mass_per_s.items()}
                           if total_out > 0 else {})

    # Calcular dh_total: para cada reacción, ΔH(T) · ξ (en mol/s = kJ/s = kW)
    dh_total_kW = 0.0
    if mode == "pfr":
        # ξⱼ = ∫₀ᵛ rⱼ dV ≈ generación neta de productos clave
        # Simplificación: ΔF_i / νᵢ del primer producto puro
        for j, rid in enumerate(rxn_ids):
            rxn = get(rid)
            # ξ inferido: tomar la especie con mayor |ΔF|/|ν|
            xi_inferred = 0.0
            for sp in rxn.stoich:
                dF = res['F_out'].get(sp.formula, 0.0) - F_in.get(sp.formula, 0.0)
                if abs(sp.nu) > 0:
                    xi_inferred = dF / sp.nu
                    break
            dh = rxn.dh_rxn_kJ_mol(T_K) or rxn.dh_rxn_298_kJ_mol or 0.0
            dh_total_kW += xi_inferred * dh
        xi_dict = {}
    else:    # cstr: ξⱼ directo
        xi_dict = res['xi']
        for rid, xi in xi_dict.items():
            rxn = get(rid)
            dh = rxn.dh_rxn_kJ_mol(T_K) or rxn.dh_rxn_298_kJ_mol or 0.0
            dh_total_kW += xi * dh

    heat_of_reaction_kJ_per_kg = (dh_total_kW / inlet_mass_kg_s
                                   if inlet_mass_kg_s > 0 else 0.0)

    # ---- Perfil espacial del PFR (Capa 5) ----
    # solve_pfr devuelve profile_V [m³] y profile_F [{formula: mol/s}].
    # El CSTR no tiene perfil (mezcla perfecta) → profile=None.
    # Convertimos formula→thermo_name y agregamos la conversión por
    # especie en cada punto, para que la UI no necesite reactions_db.
    pfr_profile = None
    if mode == "pfr" and res.get("profile_V") and res.get("profile_F"):
        prof_V = res["profile_V"]                 # [m³] acumulado
        V_tot = prof_V[-1] if prof_V else 0.0
        F0 = res["profile_F"][0] if res["profile_F"] else {}
        species_thermo = {}                       # formula -> thermo_name
        for formula in (F0.keys() if F0 else []):
            tn = thermo_name(formula)
            species_thermo[formula] = tn if tn else formula
        points = []
        for Vk, Fk in zip(prof_V, res["profile_F"]):
            entry = {
                "V_m3":   Vk,
                "L_frac": (Vk / V_tot) if V_tot > 0 else 0.0,
                "F":      {},      # {thermo_name: mol/s}
                "X":      {},      # {thermo_name: conversión fracción}
            }
            for formula, Fval in Fk.items():
                tn = species_thermo.get(formula, formula)
                entry["F"][tn] = Fval
                F_in_sp = F0.get(formula, 0.0)
                if F_in_sp > 1e-12:
                    x = (F_in_sp - Fval) / F_in_sp
                    # solo conversión positiva (reactantes consumidos)
                    if x > 1e-9:
                        entry["X"][tn] = x
            points.append(entry)
        pfr_profile = {
            "V_total_m3": V_tot,
            "points":     points,
        }

    return dict(
        outlet_composition=outlet_composition,
        outlet_mass_kg_s=total_out,
        heat_of_reaction_kJ_per_kg=heat_of_reaction_kJ_per_kg,
        duty_kW=dh_total_kW,
        xi=xi_dict,
        unmapped=unmapped,
        tau_s=res.get('tau_s'),
        conversion=res.get('conversion', {}),
        pfr_profile=pfr_profile,
    )


def solve_batch_from_composition(
        rxn_ids:           List[str],
        inlet_composition: Dict[str, float],
        inlet_mass_kg_s:   float,
        T_K:               float,
        P_bar:             float,
        V_reactor_L:       float,
        t_batch_s:         float,
        rho_b:             Optional[float] = None) -> Optional[Dict]:
    """Wrapper batch para el flowsheet.  Convención: carga =
    ṁ_in · t_batch, resuelve el batch, devuelve caudal medio
    equivalente para cerrar el balance anual del PFD.

    Devuelve la misma forma que solve_kinetic_reactor_from_composition
    + 'batch_profile' (perfil temporal en nombres thermo)."""
    if V_reactor_L <= 0 or t_batch_s <= 0:
        return None
    try:
        import thermo_db as _td
    except ImportError:
        return None
    err = _check_kinetics_compatibility(rxn_ids)
    if err is not None:
        return None
    for rid in rxn_ids:
        r = get(rid)
        if r and not r.is_kinetic_T_valid(T_K):
            return None
    total_frac = sum(inlet_composition.values())
    if total_frac <= 0:
        return None
    norm = {k: v/total_frac for k, v in inlet_composition.items() if v > 0}

    # carga total de la tanda [kg] = ṁ · t_batch
    mass_charge_kg = inlet_mass_kg_s * t_batch_s

    N_in: Dict[str, float] = {}
    inert_moles: Dict[str, float] = {}
    unmapped: List[str] = []
    for thermo_n, frac in norm.items():
        m_kg = frac * mass_charge_kg
        formula = formula_for(thermo_n)
        comp_obj = _td.get(thermo_n)
        if comp_obj is None or comp_obj.mw <= 0 or formula is None:
            inert_moles[thermo_n] = inert_moles.get(thermo_n, 0.0)
            if formula is None:
                unmapped.append(thermo_n)
            continue
        N_in[formula] = N_in.get(formula, 0.0) + m_kg*1000.0/comp_obj.mw

    if not N_in:
        return None

    V_m3 = V_reactor_L / 1000.0
    res = solve_batch(rxn_ids, N_in, T_K, P_bar, V_m3, t_batch_s,
                      n_steps=500, rho_b=rho_b)
    if res is None:
        return None

    # N_out [mol tanda] → caudal medio equivalente kg/s
    outlet_mass_per_s: Dict[str, float] = {}
    for formula, moles in res['N_out'].items():
        if moles < 1e-15:
            continue
        tn = thermo_name(formula)
        if tn is None:
            continue
        co = _td.get(tn)
        if co is None or co.mw <= 0:
            continue
        kg_total = moles * co.mw / 1000.0
        outlet_mass_per_s[tn] = kg_total / t_batch_s     # caudal medio
    total_out = sum(outlet_mass_per_s.values())
    outlet_composition = ({k: v/total_out for k, v in outlet_mass_per_s.items()}
                          if total_out > 0 else {})

    # Calor de reacción: Σ ξ·ΔH, ξ inferido de ΔN del primer reactante
    dh_total_kW = 0.0
    for rid in rxn_ids:
        rxn = get(rid)
        xi_mol = 0.0
        for sp in rxn.stoich:
            dN = res['N_out'].get(sp.formula, 0.0) - N_in.get(sp.formula, 0.0)
            if abs(sp.nu) > 0:
                xi_mol = dN / sp.nu
                break
        dh = rxn.dh_rxn_kJ_mol(T_K) or rxn.dh_rxn_298_kJ_mol or 0.0
        dh_total_kW += (xi_mol * dh) / t_batch_s     # kJ tanda / s = kW medio
    heat_kJ_per_kg = (dh_total_kW / inlet_mass_kg_s
                      if inlet_mass_kg_s > 0 else 0.0)

    # perfil temporal en nombres thermo + conversión por especie
    profile = None
    if res.get("profile_t") and res.get("profile_N"):
        N0 = res["profile_N"][0]
        sp_thermo = {f: (thermo_name(f) or f) for f in N0.keys()}
        pts = []
        for tk, Nk, Pk in zip(res["profile_t"], res["profile_N"],
                              res["profile_P"]):
            e = {"t_s": tk, "P_bar": Pk, "N": {}, "X": {}}
            for f, val in Nk.items():
                tn = sp_thermo.get(f, f)
                e["N"][tn] = val
                n0 = N0.get(f, 0.0)
                if n0 > 1e-12:
                    x = (n0 - val) / n0
                    if x > 1e-9:
                        e["X"][tn] = x
            pts.append(e)
        profile = {"t_total_s": res["t_batch_s"], "points": pts}

    return dict(
        outlet_composition=outlet_composition,
        outlet_mass_kg_s=total_out,
        heat_of_reaction_kJ_per_kg=heat_kJ_per_kg,
        duty_kW=dh_total_kW,
        xi={},
        unmapped=unmapped,
        tau_s=t_batch_s,                 # para batch, "τ" = tiempo tanda
        conversion=res.get('conversion', {}),
        batch_profile=profile,
    )
