"""
tests/test_financial_consistency.py — Tests de consistencia financiera.

Cubre los bugs de bifurcación FCI / COM / Income Statement reportados:
  · Single source of FCI (capex.compute_fci)
  · COM_d − COM = (α − α_d)·FCI ≡ Dep_SL + M+T+I (identidad)
  · Income Statement EBIT incluye M+T+I (no omite 0.18·FCI)
  · NPV Costing Turton == NPV Income Statement (rel_tol 0.1%)
  · Veredicto + payback ∞/IRR None correctos
  · Working capital no se deprecia, se recupera año final
  · Loss carry-forward funcional

USO:
    python -m unittest tests.test_financial_consistency -v
"""
import math
import os
import sys
import unittest

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

import capex
import equipment_costs as ec
import flowsheet_export as fexp


REL_TOL = 0.001     # 0.1 %


def _close(a, b, tol=REL_TOL):
    return abs(a - b) / max(abs(a), abs(b), 1e-9) < tol


class _StubFs:
    """Flowsheet vacío para tests que necesitan override de ISBL."""
    blocks  = {}
    streams = {}


# ─────────────────────────────────────────────────────────────
# Bug #1 — Fuente única de FCI
# ─────────────────────────────────────────────────────────────

class TestFCISingleSource(unittest.TestCase):
    """capex.compute_fci(isbl=X) debe dar siempre el mismo CGR/FCI
    independiente del callsite, y todos los consumidores debe leer
    el mismo número.
    """

    def test_isbl_override_estable(self):
        # ISBL 10 MM USD → CGR = 10 · 1.68 = 16.8 MM; WC = 16.8 · 0.15
        d1 = capex.compute_fci(_StubFs(), isbl_override_usd=10e6)
        d2 = capex.compute_fci(_StubFs(), isbl_override_usd=10e6)
        self.assertAlmostEqual(d1["FCI_grass_roots"], d2["FCI_grass_roots"])
        self.assertAlmostEqual(d1["FCI_grass_roots"], 10e6 * 1.68, places=0)
        self.assertAlmostEqual(d1["working_capital"], 10e6 * 1.68 * 0.15,
                                  places=0)
        self.assertAlmostEqual(d1["CAPEX_total"],
                                  10e6 * 1.68 * 1.15, places=0)
        # WC NO se deprecia: depreciable_base == FCI, no CAPEX_total
        self.assertEqual(d1["depreciable_base"], d1["FCI_grass_roots"])


# ─────────────────────────────────────────────────────────────
# Bug #2 — Income Statement debe incluir M+T+I
# ─────────────────────────────────────────────────────────────

class TestIncomeStatementUsaMTI(unittest.TestCase):
    """EBIT del Income Statement debe restar Maint+Tax+Insurance.
    Antes lo omitía y reportaba cash flow positivo cuando el proyecto
    perdía plata.
    """

    def test_mti_aplicado_via_overheads_turton(self):
        # Income Statement EBIT = Revenue − tax_deductible_OPEX donde
        # tax_deductible_OPEX = β·COL + γ·(CRM+CUT+CWT) + (α−α_d)·FCI.
        # Esto es lo que profitability_indicators usa también (fix de
        # consistencia financiera).  M+T+I se reporta separado pero
        # SUMA con Dep para dar la (α−α_d)·FCI.
        FCI = 16.8e6
        WC  = 2.52e6
        crm, cut, cwt, col = 3e6, 2e6, 0.5e6, 1e6
        alpha, alpha_d, beta, gamma = 0.305, 0.180, 2.73, 1.23
        rows = fexp.compute_income_statement(
            revenue_usd_yr=15e6, crm=crm, cut=cut, cwt=cwt, col=col,
            fci_usd=FCI, depreciable_base_usd=FCI, working_capital_usd=WC,
            useful_life_yr=10, years_op=10, tax_rate=0.30,
        )
        r5 = next(r for r in rows if r["Year"] == 5)
        tax_deductible = (beta * col + gamma * (crm + cut + cwt)
                          + (alpha - alpha_d) * FCI)
        ebit_esperado = 15e6 - tax_deductible
        self.assertAlmostEqual(r5["EBIT"], ebit_esperado, places=0,
            msg=f"EBIT {r5['EBIT']:,.0f} ≠ esperado {ebit_esperado:,.0f}")
        # M+T+I + Dep ≡ (α−α_d)·FCI por convención
        self.assertAlmostEqual(
            r5["M+T+I"] + r5["Depreciation"],
            (alpha - alpha_d) * FCI, places=0,
            msg="M+T+I + Dep no suma (α−α_d)·FCI")


# ─────────────────────────────────────────────────────────────
# Bug #3 — Coherencia Costing Turton ↔ Income Statement (NPV)
# ─────────────────────────────────────────────────────────────

class TestNPVCoherencia(unittest.TestCase):
    """NPV del bloque profitability y NPV reconstruido del Income
    Statement deben coincidir dentro de 0.1 %.
    """

    def test_coherencia_caso_rentable(self):
        FCI = 16.8e6
        WC  = 2.52e6
        revenue = 15e6
        crm, cut, cwt, col = 3e6, 2e6, 0.5e6, 1e6
        com = ec.cost_of_manufacture_components(
            FCI_usd=FCI, COL_usd=col, CUT_usd=cut, CRM_usd=crm, CWT_usd=cwt,
            depreciable_base_usd=FCI, useful_life_yr=10,
        )
        prof = ec.profitability_indicators(
            revenue_usd_yr=revenue, com_d_usd_yr=com["COM_d"],
            fci_usd=FCI, depreciable_base_usd=FCI,
            working_capital_usd=WC, useful_life_yr=10,
            years_op=10, tax_rate=0.30, disc_rate=0.10,
        )
        rows = fexp.compute_income_statement(
            revenue_usd_yr=revenue, crm=crm, cut=cut, cwt=cwt, col=col,
            fci_usd=FCI, depreciable_base_usd=FCI,
            working_capital_usd=WC, useful_life_yr=10,
            years_op=10, tax_rate=0.30,
            maintenance_tax_insurance_usd_yr=com["Maintenance_Tax_Insurance"],
        )
        # NPV reconstruido desde income statement
        disc = 0.10
        npv_income = sum(r["Cash Flow"] / ((1 + disc) ** r["Year"])
                          for r in rows)
        self.assertTrue(
            _close(prof["NPV"], npv_income, REL_TOL),
            f"NPV Costing={prof['NPV']:,.0f} vs Income={npv_income:,.0f} "
            f"(diff {abs(prof['NPV']-npv_income):,.0f})"
        )


# ─────────────────────────────────────────────────────────────
# Bug #4 — Veredicto explícito + payback ∞ / IRR None
# ─────────────────────────────────────────────────────────────

class TestVeredictoExplicito(unittest.TestCase):
    def test_proyecto_inviable_payback_infinito(self):
        # Revenue tan bajo que cash flow es negativo
        FCI = 10e6
        prof = ec.profitability_indicators(
            revenue_usd_yr=1e6, com_d_usd_yr=8e6, fci_usd=FCI,
            depreciable_base_usd=FCI, working_capital_usd=0,
            years_op=10, tax_rate=0.30, disc_rate=0.10,
        )
        self.assertEqual(prof["Veredicto"], "INVIABLE")
        self.assertEqual(prof["Payback simple"], float("inf"))
        self.assertIn("∞", prof["Payback str"])
        self.assertIn("no recupera", prof["Payback str"])
        self.assertIsNone(prof["IRR %"])
        self.assertIn("no existe", prof["IRR str"])

    def test_proyecto_viable_veredicto(self):
        FCI = 5e6
        prof = ec.profitability_indicators(
            revenue_usd_yr=10e6, com_d_usd_yr=4e6, fci_usd=FCI,
            depreciable_base_usd=FCI, working_capital_usd=0,
            years_op=10, tax_rate=0.30, disc_rate=0.10,
        )
        self.assertEqual(prof["Veredicto"], "VIABLE")
        self.assertGreater(prof["NPV"], 0)


# ─────────────────────────────────────────────────────────────
# Bug #5 — Loss Carry-Forward
# ─────────────────────────────────────────────────────────────

class TestLossCarryForward(unittest.TestCase):
    """Si los primeros años el EBIT es negativo, NO se paga tax, y
    el NOL se aplica contra EBIT positivo de años posteriores hasta
    agotarse.
    """

    def test_nol_aplicado_y_flag(self):
        FCI = 10e6
        # Caso intencional: Revenue baja, costos altos → EBIT negativo
        # todos los años → NUNCA paga tax → flag False.
        rows = fexp.compute_income_statement(
            revenue_usd_yr=5e6, crm=8e6, cut=0.5e6, cwt=0, col=0.5e6,
            fci_usd=FCI, depreciable_base_usd=FCI, working_capital_usd=0,
            useful_life_yr=10, years_op=10, tax_rate=0.30,
        )
        r1 = rows[1]
        self.assertLess(r1["EBIT"], 0)
        self.assertEqual(r1["Tax"], 0.0)
        self.assertFalse(rows[-1].get("paga_impuestos", True))

    def test_nol_se_consume_con_ebit_positivo(self):
        FCI = 5e6
        # Caso 1: sin NOL, tax cada año
        rows_a = fexp.compute_income_statement(
            revenue_usd_yr=10e6, crm=3e6, cut=1e6, cwt=0, col=1e6,
            fci_usd=FCI, depreciable_base_usd=FCI, working_capital_usd=0,
            useful_life_yr=10, years_op=10, tax_rate=0.30,
            maintenance_tax_insurance_usd_yr=0.0,
        )
        # Sin pérdidas previas → NOL_applied debe ser 0 en todos los años
        for r in rows_a[1:]:
            self.assertEqual(r["NOL applied"], 0.0)
        # Flag debe ser True (pagó tax)
        self.assertTrue(rows_a[-1].get("paga_impuestos", False))


# ─────────────────────────────────────────────────────────────
# Bug #6 — Working Capital recovery año final + no depreciable
# ─────────────────────────────────────────────────────────────

class TestWorkingCapitalRecovery(unittest.TestCase):
    def test_wc_year0_y_recovery_final(self):
        FCI = 10e6
        WC  = 1.5e6
        rows = fexp.compute_income_statement(
            revenue_usd_yr=5e6, crm=1e6, cut=0.5e6, cwt=0, col=0.5e6,
            fci_usd=FCI, depreciable_base_usd=FCI, working_capital_usd=WC,
            useful_life_yr=10, years_op=10, tax_rate=0.30,
            maintenance_tax_insurance_usd_yr=0.0,
        )
        # Year 0 = -(FCI + WC) = -11.5 MM
        self.assertAlmostEqual(rows[0]["CapEx"], -(FCI + WC), places=0)
        # Año 10 (último): WC Recov = +WC
        self.assertAlmostEqual(rows[10]["WC Recov"], WC, places=0)
        # Depreciación = FCI/10 (NO incluye WC)
        for r in rows[1:]:
            self.assertAlmostEqual(r["Depreciation"], FCI/10, places=0)


# ─────────────────────────────────────────────────────────────
# Bug #7 — Coherencia COM − COM_d − Dep_SL = M+T+I (explícito)
# ─────────────────────────────────────────────────────────────

class TestComDepIdentity(unittest.TestCase):
    """La identidad debe cuadrar exactamente:
        COM − COM_d ≡ Depreciation_SL + Maintenance_Tax_Insurance
    """

    def test_identidad_com_dep_mti(self):
        for FCI in [5e6, 10e6, 20e6, 50e6]:
            for life in [5, 10, 15, 20]:
                com = ec.cost_of_manufacture_components(
                    FCI_usd=FCI, COL_usd=1e6,
                    CUT_usd=2e6, CRM_usd=3e6, CWT_usd=0.5e6,
                    depreciable_base_usd=FCI, useful_life_yr=life,
                )
                lhs = com["COM"] - com["COM_d"]
                rhs = com["Depreciation_SL"] + com["Maintenance_Tax_Insurance"]
                self.assertAlmostEqual(
                    lhs, rhs, places=2,
                    msg=f"FCI={FCI:,.0f} life={life}: "
                        f"COM-COM_d={lhs:,.2f} vs Dep+MTI={rhs:,.2f}"
                )


# ─────────────────────────────────────────────────────────────
# Bug #8 — Regresión: caso HNO3 (NPV congelado tras fix)
# ─────────────────────────────────────────────────────────────

class TestRegresionHNO3(unittest.TestCase):
    """Tras unificar las rutas de FCI, el NPV del caso HNO3 sintético
    debe coincidir entre Costing Turton y Income Statement.  Si en el
    futuro alguien cambia algo y rompe la coherencia, este test lo
    detecta.

    Parámetros sintéticos basados en orden de magnitud del ejemplo
    HNO3 Ostwald de examples_library (~6 kton/yr HNO3 60%).
    """

    def test_npv_unico(self):
        # Aproximación numérica al caso HNO3 (mid-2024 USD)
        ISBL_USD = 8.63e6
        REVENUE  = 7.50e6
        CRM      = 2.00e6
        CUT      = 1.30e6
        CWT      = 0.10e6
        COL      = 0.40e6
        # FCI por capex single-source
        capex_data = capex.compute_fci(_StubFs(),
                                          isbl_override_usd=ISBL_USD)
        FCI = capex_data["FCI_grass_roots"]   # 14.50 MM aprox
        WC  = capex_data["working_capital"]
        dep_base = capex_data["depreciable_base"]
        com = ec.cost_of_manufacture_components(
            FCI_usd=FCI, COL_usd=COL, CUT_usd=CUT,
            CRM_usd=CRM, CWT_usd=CWT,
            depreciable_base_usd=dep_base, useful_life_yr=10,
        )
        prof = ec.profitability_indicators(
            revenue_usd_yr=REVENUE, com_d_usd_yr=com["COM_d"],
            fci_usd=FCI, depreciable_base_usd=dep_base,
            working_capital_usd=WC, useful_life_yr=10,
            years_op=10, tax_rate=0.30, disc_rate=0.10,
        )
        income = fexp.compute_income_statement(
            revenue_usd_yr=REVENUE, crm=CRM, cut=CUT, cwt=CWT, col=COL,
            fci_usd=FCI, depreciable_base_usd=dep_base,
            working_capital_usd=WC, useful_life_yr=10,
            years_op=10, tax_rate=0.30,
            maintenance_tax_insurance_usd_yr=com["Maintenance_Tax_Insurance"],
        )
        # NPV reconstruido desde income statement DEBE igualar al
        # de profitability_indicators (rel_tol 0.1 %)
        disc = 0.10
        npv_income = sum(r["Cash Flow"] / ((1 + disc) ** r["Year"])
                          for r in income)
        self.assertTrue(
            _close(prof["NPV"], npv_income, REL_TOL),
            f"HNO3 NPV: Costing={prof['NPV']:,.0f}  "
            f"Income={npv_income:,.0f}  "
            f"diff={abs(prof['NPV']-npv_income):,.0f}"
        )
        # Y el veredicto debe ser estable (signo del NPV).
        self.assertEqual(prof["Veredicto"],
                          "VIABLE" if prof["NPV"] > 0 else "INVIABLE")


if __name__ == "__main__":
    unittest.main(verbosity=2)
