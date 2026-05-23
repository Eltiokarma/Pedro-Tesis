"""
examples_library.py — Biblioteca de flowsheets de ejemplo.

Provee la clase ExampleBuilder, que construye flowsheets de ejemplo
sobre un Flowsheet pasado. Es la única fuente de los 41 ejemplos del
proyecto, consumida por flowsheet_qt.py (acción "Cargar ejemplo").

Uso:
    from flowsheet_model import Flowsheet
    from examples_library import ExampleBuilder

    fs = Flowsheet()
    b = ExampleBuilder(fs)
    b._example_talara_refinery()  # construye Talara sobre fs

Los métodos _example_* son lógica pura sobre el modelo: agregan bloques,
streams, opex_extras y configuran labor — sin tocar UI.

NOTA SOBRE NOMBRES: Los métodos mantienen el prefijo `_example_` para
preservar exactamente la API que los builders del Tk legacy ya usaban
internamente (e.g., `self._add_example_block(...)`). Es deliberado:
migración byte-a-byte sin find-and-replace en los 41 builders.
"""

from flowsheet_model import Block, Stream, Flowsheet


class ExampleBuilder:
    """Constructor de flowsheets de ejemplo.

    Provee:
    - 5 helpers (`_add_example_block`, `_add_example_stream`,
      `_add_example_extra`, `_set_example_labor`, `_set_block_duty`).
    - 41 builders (`_example_hda`, `_example_methanol`, …,
      `_example_desalination`).

    Los helpers tienen una firma estable: 5 métodos para crear bloques,
    streams, extras de OPEX, configurar labor y forzar duties.  Los
    builders conservan sus comentarios y blank lines originales para
    documentar las decisiones de diseño de cada ejemplo.
    """

    def __init__(self, fs):
        self.fs = fs

    # ─── HELPERS ──────────────────────────────────────────────
    # Copiados verbatim del _ExampleBuilderShim de flowsheet_qt.py
    # (líneas 8927-8984).  No modificar firmas ni comentarios.

    def _add_example_block(self, name, eq_type, S, x, y, n=1):
        bid = self.fs.new_id()
        b = Block(id=bid, name=name, eq_type=eq_type, S=S, n=n, x=x, y=y)
        # NO llamar a apply_type_defaults aca: los ejemplos son
        # "carga" en espiritu (configuracion pre-curada), no creacion
        # interactiva de usuario. Multiples ejemplos usan
        # 'Reactor — autoclave' con .reactions=[...] esperando modo
        # equilibrium (default historico); apply_type_defaults los
        # pasaria silenciosamente a batch (Patch 3) y romperia el solve
        # por falta de reactor_volume_L. Los ejemplos que quieren
        # PFR/CSTR/batch setean reactor_mode explicitamente despues
        # del _add_example_block (ej. _example_ethane_cracker_pfr).
        self.fs.blocks[bid] = b
        return bid

    def _add_example_stream(self, src, dst, name, mass_flow=0.0,
                            role="internal", src_port="", dst_port="",
                            price=0.0, T=25.0, cp=0.0,
                            main_component="", phase="",
                            composition=None,
                            lock_mass=None, lock_T=None, lock_comp=None):
        """Shim Qt — Hallazgo 2: mismo contrato que FlowsheetEditor de Tk
        con lock_* opcionales (None = heurística vieja)."""
        sid = self.fs.new_id()
        s = Stream(
            id=sid, name=name, src=src, dst=dst,
            mass_flow=mass_flow, role=role,
            src_port=src_port, dst_port=dst_port,
            price_usd_per_tm=price,
            temperature=T, cp=cp,
            main_component=main_component,
            phase=phase,
            composition=dict(composition) if composition else {},
        )
        s.mass_flow_locked   = ((mass_flow > 0) if lock_mass is None
                                  else bool(lock_mass))
        s.temperature_locked = ((abs(T - 25.0) > 0.01) if lock_T is None
                                  else bool(lock_T))
        s.composition_locked = ((bool(composition) or bool(main_component))
                                  if lock_comp is None else bool(lock_comp))
        self.fs.streams[sid] = s
        return sid

    def _add_example_extra(self, name, flowrate, price, units="tm",
                           stream="Utilities"):
        self.fs.opex_extras.append({
            "name": name, "units": units, "time_basis": "year",
            "flowrate": float(flowrate), "price_usd_per_unit": float(price),
            "stream": stream,
        })

    def _set_example_labor(self, labor_usd_per_year):
        self.fs.fixed_overrides["Labor"] = float(labor_usd_per_year)

    def _set_block_duty(self, bid, duty_kw):
        if bid in self.fs.blocks:
            self.fs.blocks[bid].duty = float(duty_kw)
            self.fs.blocks[bid].duty_locked = (abs(duty_kw) > 1e-9)

    # ─── BUILDERS ─────────────────────────────────────────────
    # 41 ejemplos curados (HDA, refinería Talara, planta de cemento,
    # etc.).  Cada builder configura un flowsheet completo: bloques,
    # streams, opex extras y labor.  Todos llaman a los 5 helpers
    # de arriba — `self._add_example_block`, `_add_example_stream`,
    # `_add_example_extra`, `_set_example_labor`, `_set_block_duty`.

    def _example_hda(self):
        """HDA — Hidrodealquilación de tolueno (Douglas / Turton).
        Tolueno + H2 → Benceno + CH4. ~75% conversión.
        Tags ISA-5.1: E (HX), F (horno), R (reactor),
        V (separador), T (columna), P (bomba), TK (tanque)."""
        # Layout PFD industrial (1600×960 paper).
        # Top row: tren de reacción (left→right).  Bottom row: separación.
        # tren de reacción (fila superior, y centro ≈ 240)
        e101 = self._add_example_block("E-101", "Heat exch. — floating head", 250.0,  300, 220)
        f101 = self._add_example_block("F-101", "Fired heater — non-reformer", 5000.0, 480, 180)
        r101 = self._add_example_block("R-101", "Reactor — jacketed non-agit.",  25.0, 640, 180)
        self.fs.blocks[r101].P_op_bar = 25.0   # HDA ~25 bar
        e102 = self._add_example_block("E-102", "Heat exch. — air cooler",      180.0, 750, 200)
        v101 = self._add_example_block("V-101", "Vessel — vertical",             20.0, 930, 180)

        # separación (fila inferior, y centro ≈ 580)
        t101 = self._add_example_block("T-101", "Tower (column shell)",          45.0, 500, 480)
        e104 = self._add_example_block("E-104", "Heat exch. — kettle reboiler", 150.0, 620, 540)
        e103 = self._add_example_block("E-103", "Heat exch. — floating head",   160.0, 300, 560)
        p101 = self._add_example_block("P-101", "Pump — centrifugal",            15.0,  80, 555)
        tk1  = self._add_example_block("TK-101","Storage tank — cone roof",     500.0, 820, 540)   # benceno
        tk2  = self._add_example_block("TK-102","Storage tank — cone roof",     100.0,1060, 180)   # purga
        # tanque de tolueno fresco
        tk3  = self._add_example_block("TK-103","Storage tank — cone roof",     300.0,  80, 200)

        # Streams con composición + fase declarada (modelo extendido).
        # Reacción: C₇H₈ + H₂ → C₆H₆ + CH₄
        #   tolueno fresco (8850 tm/año, liquid) + reciclo de tolueno
        #   sin reaccionar (2150 tm/año) → 11000 nominal a través del
        #   tren → benceno (8500 tm/año) + purga H₂/CH₄ (350)

        # Feed fresco: tolueno líquido (catálogo: toluene)
        self._add_example_stream(tk3, p101, "S-feed-tol", 8850, role="feed",
                                 src_port="salida",   dst_port="succion",
                                 price=650.0, T=25,
                                 main_component="toluene", phase="liquid")
        # Post-bomba: mezcla con reciclo, mostly tolueno líquido
        self._add_example_stream(p101, e101, "S-1",  0.0,
                                 src_port="descarga",  dst_port="tube_in",
                                 T=27,
                                 main_component="toluene", phase="liquid")
        # Post-preheater: ya vaporizado, tolueno + H₂ mezcla (vapor)
        self._add_example_stream(e101, f101, "S-2",  0.0,
                                 src_port="tube_out",  dst_port="proceso_in",
                                 T=200,
                                 main_component="toluene", phase="vapor")
        # Post-horno: 600°C, listo para reaccionar
        self._add_example_stream(f101, r101, "S-3",  0.0,
                                 src_port="proceso_out", dst_port="alimentacion",
                                 T=600,
                                 main_component="toluene", phase="vapor")
        # Post-reactor: ahora con benceno + metano formados (~75% conv.)
        self._add_example_stream(r101, e102, "S-4",  0.0,
                                 src_port="producto",  dst_port="proceso_in",
                                 T=620,
                                 composition={"benzene": 0.77, "toluene": 0.18,
                                              "methane": 0.04, "hydrogen": 0.01},
                                 main_component="benzene", phase="vapor")
        # Post-cooler: parcial condensación (vapor + líquido)
        self._add_example_stream(e102, v101, "S-5",  0.0,
                                 src_port="proceso_out", dst_port="alimentacion",
                                 T=50,
                                 main_component="benzene", phase="liquid")
        # Líquido del flash: benceno + tolueno (sin H₂ ni metano)
        self._add_example_stream(v101, t101, "S-6",  0.0,
                                 src_port="liquido",   dst_port="alimentacion",
                                 T=80,
                                 composition={"benzene": 0.79, "toluene": 0.21},
                                 main_component="benzene", phase="liquid")
        # Fondo columna: tolueno (vuelve por reciclo)
        self._add_example_stream(t101, e104, "S-7",  0.0,
                                 src_port="liquido_fondo", dst_port="liq_in",
                                 T=110,
                                 main_component="toluene", phase="liquid")
        # Tope columna: benceno como vapor
        self._add_example_stream(t101, e103, "S-8",  0.0,
                                 src_port="vapor_tope", dst_port="tube_in",
                                 T=85,
                                 main_component="benzene", phase="vapor")
        # Reciclo del reboiler: tolueno líquido
        self._add_example_stream(e104, p101, "S-9-recic", 2150,
                                 src_port="cond_out", dst_port="succion",
                                 T=110,
                                 main_component="toluene", phase="liquid")
        # Producto: benceno líquido condensado
        self._add_example_stream(e103, tk1,  "S-benceno", 0.0, role="product",
                                 src_port="tube_out",  dst_port="entrada",
                                 price=1150.0, T=40,
                                 main_component="benzene", phase="liquid")
        # Purga: gas (H₂ + metano formado)
        self._add_example_stream(v101, tk2,  "S-purga-H2", 350, role="product",
                                 src_port="vapor",     dst_port="entrada",
                                 price=2000.0, T=50,
                                 composition={"hydrogen": 0.4, "methane": 0.6},
                                 main_component="hydrogen", phase="gas")

        # ---- Calor de reacción HDA: C₇H₈ + H₂ → C₆H₆ + CH₄ ----
        # ΔH ≈ -42 kJ/mol benceno formado; sobre kg input total ≈ -416 kJ/kg
        self.fs.blocks[r101].heat_of_reaction = -416.0

        # ---- Duties inferidos del balance termodinámico ----
        # T, fase, composición y mass_flow declarados arriba determinan
        # el duty; el solver lo computa y lo asigna a cada bloque térmico.
        from flowsheet_solver import auto_set_duties_from_thermo
        auto_set_duties_from_thermo(self.fs)
        self._set_block_duty(p101, +15)     # bomba: eléctrico, manual

        # ---- OPEX extras manuales: SOLO los no-térmicos ----
        # H2 makeup (raw material adicional)
        self._add_example_extra("H2 makeup",      flowrate=200,      price=1800.0,
                                stream="Raw Materials")
        # Catalizador Pt/alúmina (consumible)
        self._add_example_extra("Catalizador Pt", flowrate=0.5,      price=25_000.0,
                                stream="Consumables")
        # Las utilities (steam, cooling, fuel, electricity) se generan
        # automáticamente desde los duties — no hace falta declararlas
        # manualmente.  Labor se calcula con Turton.

    def _example_methanol(self):
        """Síntesis de metanol simplificada.
        Syngas (CO + 2H2) → CH3OH. Reactor + flash + columna.

        Layout: 2 filas alineadas para que el routing salga limpio.
          fila 1: K-101 → E-101 → R-101 → E-102 → V-101
          fila 2: TK-MeOH ← E-103 ← T-101 → E-104 → TK-agua
        El destilado va a TK-MeOH (izquierda), el agua de fondo va a TK-agua (derecha),
        sin que ninguna corriente cruce equipos.
        """
        # Layout PFD industrial 1600×960.
        # Top row: K-101 → E-101 → R-101 → E-102 → V-101 → TK-purga
        # Bottom row: separación con T-101 al centro
        k101 = self._add_example_block("K-101", "Compressor — centrifugal",      800.0,  80, 215)
        e101 = self._add_example_block("E-101", "Heat exch. — floating head",    220.0, 240, 220)
        r101 = self._add_example_block("R-101", "Reactor — jacketed non-agit.",   30.0, 420, 180)
        e102 = self._add_example_block("E-102", "Heat exch. — air cooler",       200.0, 540, 200)
        v101 = self._add_example_block("V-101", "Vessel — vertical",              15.0, 720, 180)
        tk3  = self._add_example_block("TK-103","Storage tank — cone roof",       30.0, 860, 180)   # purga

        # fila inferior
        tk1  = self._add_example_block("TK-101","Storage tank — floating roof",  400.0,  80, 540)   # crude meoh feed to T-101? no, era feed
        e103 = self._add_example_block("E-103", "Heat exch. — floating head",    140.0, 240, 560)
        t101 = self._add_example_block("T-101", "Tower (column shell)",           35.0, 460, 460)
        e104 = self._add_example_block("E-104", "Heat exch. — kettle reboiler",  130.0, 580, 540)
        tk2  = self._add_example_block("TK-102","Storage tank — cone roof",       50.0, 800, 540)   # agua
        # tanque metanol producto (lo dibujamos al lado derecho)
        # Nota: el flujo original de los streams sigue siendo igual

        # Streams con composición + fase declarada (modelo extendido).
        # El solver de energía usa Cp(T) del catálogo + ΔH_vap si hay
        # cambio de fase explícito.

        self._add_example_stream(k101, e101, "S-1", 14000, role="feed",
                                 src_port="descarga", dst_port="tube_in",
                                 price=150.0, T=40,
                                 main_component="syngas", phase="gas")
        self._add_example_stream(e101, r101, "S-2", 0.0,
                                 src_port="tube_out", dst_port="alimentacion",
                                 T=230,
                                 main_component="syngas", phase="gas")
        # post-reactor: gas con metanol formado en vapor
        self._add_example_stream(r101, e102, "S-3", 0.0,
                                 src_port="producto", dst_port="proceso_in",
                                 T=260,
                                 main_component="methanol", phase="vapor")
        # post-cooler: parcialmente condensado (two-phase)
        self._add_example_stream(e102, v101, "S-4", 0.0,
                                 src_port="proceso_out", dst_port="alimentacion",
                                 T=40,
                                 main_component="methanol", phase="liquid")
        # líquido del flash: crude methanol (líquido)
        self._add_example_stream(v101, t101, "S-5", 0.0,
                                 src_port="liquido",  dst_port="alimentacion",
                                 T=60,
                                 composition={"methanol": 0.94, "water": 0.06},
                                 main_component="methanol", phase="liquid")
        # vapor tope de columna: vapor (componente puro metanol)
        self._add_example_stream(t101, e103, "S-vap-tope", 0.0,
                                 src_port="vapor_tope", dst_port="shell_in",
                                 T=68,
                                 main_component="methanol", phase="vapor")
        # producto líquido condensado
        self._add_example_stream(e103, tk1,  "S-MeOH", 0.0, role="product",
                                 src_port="shell_out", dst_port="entrada",
                                 price=1100.0, T=40,
                                 main_component="methanol", phase="liquid")
        # fondo de columna: agua líquida
        self._add_example_stream(t101, e104, "S-fondo", 600,
                                 src_port="liquido_fondo", dst_port="liq_in",
                                 T=100,
                                 main_component="water", phase="liquid")
        self._add_example_stream(e104, tk2,  "S-agua", 0.0, role="product",
                                 src_port="cond_out", dst_port="entrada",
                                 price=5.0, T=40,
                                 main_component="water", phase="liquid")
        # venteo: gases no condensados (CO, H2)
        self._add_example_stream(v101, tk3, "S-purge", 3900, role="product",
                                 src_port="vapor", dst_port="entrada",
                                 price=0.0, T=40,
                                 main_component="syngas", phase="gas")

        # ---- Calor de reacción: CO + 2H2 → CH3OH, ΔH = -90 kJ/mol ----
        # = -2828 kJ/kg MeOH; con yield mass ~72%, sobre kg input syngas ≈ -2000
        self.fs.blocks[r101].heat_of_reaction = -2000.0  # kJ/kg input
        self.fs.blocks[r101].P_op_bar = 80.0   # MeOH loop ~80 bar industrial

        # ---- Duties inferidos del balance termodinámico ----
        from flowsheet_solver import auto_set_duties_from_thermo
        auto_set_duties_from_thermo(self.fs)
        self._set_block_duty(k101, +800)    # compresor: eléctrico, manual

        # ---- OPEX extras manuales: SOLO consumibles ----
        # Catalizador CuZnO/Al2O3 (~3 años de vida)
        self._add_example_extra("Catalizador CuZnO", flowrate=2, price=40_000.0,
                                stream="Consumables")
        # Utilities → auto desde duties.

    def _example_distillation(self):
        """Destilación binaria benceno/tolueno (50/50).
        Pre-calentador + columna + condensador + reboiler + bombas.
        Layout PFD 1600×960: feed entra desde izquierda al mid, columna
        central, productos a la derecha."""
        tk0  = self._add_example_block("TK-101","Storage tank — cone roof", 200.0,  80, 380)
        p101 = self._add_example_block("P-101", "Pump — centrifugal",         8.0, 220, 405)
        e101 = self._add_example_block("E-101", "Heat exch. — floating head",120.0, 340, 410)
        t101 = self._add_example_block("T-101", "Tower (column shell)",       20.0, 540, 340)

        e102 = self._add_example_block("E-102", "Heat exch. — floating head", 90.0, 700, 190)   # condensador top
        e103 = self._add_example_block("E-103", "Heat exch. — kettle reboiler", 85.0, 700, 600)  # reboiler bottom

        tk1  = self._add_example_block("TK-102","Storage tank — cone roof",  150.0, 900, 180)   # benceno
        tk2  = self._add_example_block("TK-103","Storage tank — cone roof",  150.0, 900, 590)   # tolueno

        # Streams con composición + fase (mezcla benzene+toluene).
        # Sin reacción química — pura separación física.

        # Feed: 50/50 benceno/tolueno líquido a 25°C
        self._add_example_stream(tk0,  p101, "S-1", 10000, role="feed",
                                 src_port="salida",   dst_port="succion",
                                 price=850.0, T=25,
                                 composition={"benzene": 0.5, "toluene": 0.5},
                                 main_component="benzene", phase="liquid")
        # Post-bomba: mismo líquido
        self._add_example_stream(p101, e101, "S-2", 0.0,
                                 src_port="descarga", dst_port="tube_in",
                                 T=26,
                                 composition={"benzene": 0.5, "toluene": 0.5},
                                 main_component="benzene", phase="liquid")
        # Post-preheater: cerca del punto de burbuja
        self._add_example_stream(e101, t101, "S-3", 0.0,
                                 src_port="tube_out", dst_port="alimentacion",
                                 T=85,
                                 composition={"benzene": 0.5, "toluene": 0.5},
                                 main_component="benzene", phase="liquid")
        # Vapor tope: ~98% benceno (más volátil)
        self._add_example_stream(t101, e102, "S-4", 0.0,
                                 src_port="vapor_tope",     dst_port="tube_in",
                                 T=82,
                                 composition={"benzene": 0.98, "toluene": 0.02},
                                 main_component="benzene", phase="vapor")
        # Líquido fondo: ~98% tolueno (menos volátil)
        self._add_example_stream(t101, e103, "S-5", 5000,
                                 src_port="liquido_fondo",  dst_port="liq_in",
                                 T=110,
                                 composition={"benzene": 0.02, "toluene": 0.98},
                                 main_component="toluene", phase="liquid")
        # Productos condensados al tanque (líquidos)
        self._add_example_stream(e102, tk1,  "S-benceno", 0.0, role="product",
                                 src_port="tube_out", dst_port="entrada",
                                 price=1050.0, T=40,
                                 composition={"benzene": 0.98, "toluene": 0.02},
                                 main_component="benzene", phase="liquid")
        self._add_example_stream(e103, tk2,  "S-tolueno", 0.0, role="product",
                                 src_port="vap_out",  dst_port="entrada",
                                 price=700.0, T=40,
                                 composition={"benzene": 0.02, "toluene": 0.98},
                                 main_component="toluene", phase="liquid")

        # ---- Duties inferidos del balance termodinámico ----
        from flowsheet_solver import auto_set_duties_from_thermo
        auto_set_duties_from_thermo(self.fs)
        self._set_block_duty(p101, +8)      # bomba: eléctrico, manual

    # ======================================================
    # EJEMPLOS NUEVOS
    # ======================================================

    def _example_ammonia(self):
        """Síntesis de amoníaco — Haber-Bosch simplificado (sin recycle).

        N₂ + 3H₂ → 2NH₃, ΔH = -92 kJ/mol NH₃ (muy exotérmica).
        ~15% conversión por paso; el resto se purga (en planta real
        habría recycle pero acá lo dejamos one-shot por claridad).

        Layout PFD 1600×960.  Feed entra como mezcla 3H₂+N₂.
        """
        tk_feed   = self._add_example_block("TK-101","Storage tank — cone roof", 200.0,  80, 200)
        k101      = self._add_example_block("K-101", "Compressor — centrifugal",1500.0, 230, 215)
        e101      = self._add_example_block("E-101", "Heat exch. — floating head",220.0, 360, 220)
        r101      = self._add_example_block("R-101", "Reactor — jacketed non-agit.", 50.0, 540, 180)
        e102      = self._add_example_block("E-102", "Heat exch. — floating head",300.0, 660, 220)
        v101      = self._add_example_block("V-101", "Vessel — vertical",          18.0, 850, 180)
        tk_nh3    = self._add_example_block("TK-102","Storage tank — cone roof", 150.0, 980, 540)
        tk_purge  = self._add_example_block("TK-103","Storage tank — cone roof",  50.0, 980, 180)

        # Composiciones (fracción másica).
        # Feed estequiométrico: 3 H₂ + N₂  ⇒  mass: 6 H₂ : 28 N₂ ⇒ 0.176/0.824
        feed_mix   = {"hydrogen": 0.176, "nitrogen": 0.824}
        # Post-reactor (15% conv): se forma 0.15 mass de NH₃, el resto sin reaccionar
        post_mix   = {"hydrogen": 0.150, "nitrogen": 0.700, "ammonia": 0.150}
        # Purga (gas no convertido, libre de NH₃)
        purge_mix  = feed_mix

        # Feed: 10000 t/yr de syngas (3H₂+N₂)
        self._add_example_stream(tk_feed, k101, "S-feed", 10000, role="feed",
                                 src_port="salida",   dst_port="succion",
                                 price=180.0, T=25,
                                 composition=feed_mix,
                                 main_component="nitrogen", phase="gas")
        # Post-compresor: gas comprimido, T sube por compresión adiabática
        self._add_example_stream(k101, e101, "S-1", 0.0,
                                 src_port="descarga", dst_port="tube_in",
                                 T=180,
                                 composition=feed_mix,
                                 main_component="nitrogen", phase="gas", lock_T=False)
        # Post-preheater: T de operación reactor ~450°C
        self._add_example_stream(e101, r101, "S-2", 0.0,
                                 src_port="tube_out", dst_port="alimentacion",
                                 T=450,
                                 composition=feed_mix,
                                 main_component="nitrogen", phase="gas")
        # Post-reactor: con NH₃ formado, T sube por exotermia
        self._add_example_stream(r101, e102, "S-3", 0.0,
                                 src_port="producto", dst_port="tube_in",
                                 T=500,
                                 composition=post_mix,
                                 main_component="nitrogen", phase="gas")
        # Post-cooler: enfriado a ~30°C, NH₃ se condensa parcialmente
        # (a la P alta del proceso 200 bar, NH₃ liq a 30°C).
        self._add_example_stream(e102, v101, "S-4", 0.0,
                                 src_port="tube_out", dst_port="alimentacion",
                                 T=30,
                                 composition=post_mix,
                                 main_component="nitrogen", phase="liquid")
        # NH₃ producto (liquido del flash)
        self._add_example_stream(v101, tk_nh3, "S-NH3", 1500, role="product",
                                 src_port="liquido",  dst_port="entrada",
                                 price=750.0, T=30,
                                 main_component="ammonia", phase="liquid")
        # Purga (gas del flash)
        self._add_example_stream(v101, tk_purge, "S-purga", 0.0, role="product",
                                 src_port="vapor",    dst_port="entrada",
                                 price=120.0, T=30,
                                 composition=purge_mix,
                                 main_component="nitrogen", phase="gas")

        # ---- Calor de reacción: N₂+3H₂→2NH₃, ΔH ≈ -2700 kJ/kg NH₃ ----
        # Sobre kg de input total con 15% mass yield NH₃: -2700 × 0.15 ≈ -405 kJ/kg input
        self.fs.blocks[r101].heat_of_reaction = -405.0
        self.fs.blocks[r101].P_op_bar = 200.0   # síntesis NH3 ~200 bar
        self.fs.blocks[r101].T_op_K = 700.0   # T_op declarada (silencia dof_audit)

        # ---- Duties auto ----
        from flowsheet_solver import auto_set_duties_from_thermo
        auto_set_duties_from_thermo(self.fs)
        self._set_block_duty(k101, +1200)   # compresor: eléctrico

        # ---- OPEX extras ----
        # Catalizador Fe-K2O (vida útil ~3-5 años)
        self._add_example_extra("Catalizador Fe-K2O", flowrate=1.0, price=18_000.0,
                                stream="Consumables")

    def _example_ethanol(self):
        """Producción de etanol — fermentación + destilación.

        C₆H₁₂O₆ → 2 C₂H₅OH + 2 CO₂  (fermentación alcohólica).
        ΔH ≈ -68 kJ/mol glucosa, mass yield 51% EtOH / 49% CO₂.

        Topología:
          TK-mosto → R-101 (fermentador) → V-101 (venteo CO₂) →
          P-101 → E-101 → T-101 (destilación)
          T-101 vap → E-102 (condensador) → TK-EtOH (producto 95%)
          T-101 liq → E-103 (reboiler) → TK-vinaza (residuo)

        Mosto al 12% glucosa (típico caña/maíz).
        """
        tk_mosto = self._add_example_block("TK-101","Storage tank — cone roof", 300.0,  80, 200)
        r101     = self._add_example_block("R-101", "Reactor — jacketed agitated", 80.0, 240, 180)  # fermentador
        v101     = self._add_example_block("V-101", "Vessel — vertical",            20.0, 360, 180)  # venteo CO₂
        tk_co2   = self._add_example_block("TK-102","Storage tank — cone roof",     30.0, 480, 60)   # CO₂ venteo
        p101     = self._add_example_block("P-101", "Pump — centrifugal",           10.0, 360, 460)
        e101     = self._add_example_block("E-101", "Heat exch. — floating head",  160.0, 480, 460)
        t101     = self._add_example_block("T-101", "Tower (column shell)",          40.0, 660, 380)
        e102     = self._add_example_block("E-102", "Heat exch. — floating head",  120.0, 820, 200)  # cond top
        e103     = self._add_example_block("E-103", "Heat exch. — kettle reboiler", 100.0, 820, 600)  # reboiler
        tk_eth   = self._add_example_block("TK-103","Storage tank — cone roof",    100.0,1000, 190)  # etanol
        tk_vin   = self._add_example_block("TK-104","Storage tank — cone roof",    200.0,1000, 580)  # vinaza

        # Composiciones (fracción másica).
        mosto_mix   = {"water": 0.88, "glucose": 0.12}
        # Post-fermentación: 12% glucosa → 6.1% etanol + 5.3% CO₂ + agua restante
        fermented   = {"water": 0.876, "ethanol": 0.061, "co2": 0.053, "glucose": 0.010}
        # Tras venteo CO₂: mismo líquido sin CO₂
        post_v      = {"water": 0.925, "ethanol": 0.065, "glucose": 0.010}
        # Tope columna: 95% etanol (azeotrópico)
        top         = {"ethanol": 0.95, "water": 0.05}
        # Fondo columna: agua + residuos (vinaza)
        bottom      = {"water": 0.995, "glucose": 0.005}

        # Feed: mosto azucarado
        self._add_example_stream(tk_mosto, r101, "S-mosto", 10000, role="feed",
                                 src_port="salida",   dst_port="alimentacion",
                                 price=80.0, T=25,
                                 composition=mosto_mix,
                                 main_component="water", phase="liquid")
        # Post-fermentador: vino fermentado
        self._add_example_stream(r101, v101, "S-1", 0.0,
                                 src_port="producto", dst_port="alimentacion",
                                 T=32,
                                 composition=fermented,
                                 main_component="water", phase="liquid")
        # Venteo CO₂
        self._add_example_stream(v101, tk_co2, "S-CO2", 528, role="product",
                                 src_port="vapor",    dst_port="entrada",
                                 price=0.0, T=32,
                                 main_component="co2", phase="gas")
        # Líquido fermentado a la bomba
        self._add_example_stream(v101, p101, "S-2", 0.0,
                                 src_port="liquido",  dst_port="succion",
                                 T=32,
                                 composition=post_v,
                                 main_component="water", phase="liquid")
        # Post-bomba
        self._add_example_stream(p101, e101, "S-3", 0.0,
                                 src_port="descarga", dst_port="tube_in",
                                 T=33,
                                 composition=post_v,
                                 main_component="water", phase="liquid")
        # Post-preheater al destilador
        self._add_example_stream(e101, t101, "S-4", 0.0,
                                 src_port="tube_out", dst_port="alimentacion",
                                 T=85,
                                 composition=post_v,
                                 main_component="water", phase="liquid")
        # Vapor de tope (etanol 95%)
        self._add_example_stream(t101, e102, "S-vap", 612,
                                 src_port="vapor_tope", dst_port="tube_in",
                                 T=79,
                                 composition=top,
                                 main_component="ethanol", phase="vapor")
        # Etanol producto (condensado)
        self._add_example_stream(e102, tk_eth, "S-EtOH", 0.0, role="product",
                                 src_port="tube_out", dst_port="entrada",
                                 price=950.0, T=40,
                                 composition=top,
                                 main_component="ethanol", phase="liquid")
        # Líquido de fondo (mostly water + glucose residual)
        self._add_example_stream(t101, e103, "S-fondo", 0.0,
                                 src_port="liquido_fondo", dst_port="liq_in",
                                 T=100,
                                 composition=bottom,
                                 main_component="water", phase="liquid")
        # Vinaza al tanque
        self._add_example_stream(e103, tk_vin, "S-vinaza", 0.0, role="product",
                                 src_port="cond_out", dst_port="entrada",
                                 price=2.0, T=60,
                                 composition=bottom,
                                 main_component="water", phase="liquid")

        # ---- Calor de reacción fermentación ----
        # ΔH ≈ -68 kJ/mol glucosa = -377 kJ/kg glucosa.
        # Por kg input total con 12% glucosa: -377 × 0.12 ≈ -45 kJ/kg input
        self.fs.blocks[r101].heat_of_reaction = -45.0

        # ---- Duties auto ----
        from flowsheet_solver import auto_set_duties_from_thermo
        auto_set_duties_from_thermo(self.fs)
        self._set_block_duty(p101, +10)   # bomba: eléctrico

        # ---- OPEX extras ----
        # Levadura (Saccharomyces cerevisiae) — consumible
        self._add_example_extra("Levadura (S. cerevisiae)", flowrate=15.0,
                                price=2_000.0, stream="Consumables")

    def _example_biodiesel(self):
        """Producción de biodiesel — transesterificación de aceite vegetal.

        Reacción:  triglicérido + 3 metanol → 3 FAME (biodiesel) + glicerina
        Catalizador: NaOH disuelto en metanol (catálisis homogénea alcalina).
        Conversión típica: >95% a 60°C, 1 atm, 1 h de residencia.

        Mass balance (basis 1000 kg aceite):
          1000 oil + 105 MeOH (estequiom × 1.05 exceso 5%) → 1000 FAME + 100 glycerin + 5 MeOH sin reaccionar
          (aprox; depende del peso molecular del aceite)

        Topología:
          TK-oil + TK-MeOH → MIX (R-101) → V-101 (decanter) →
            fase biodiesel → E-101 (vaporiza MeOH residual) → TK-biodiesel
            fase glicerina → TK-glicerina
        """
        tk_oil  = self._add_example_block("TK-101","Storage tank — cone roof",   200.0,  80, 180)
        tk_meoh = self._add_example_block("TK-102","Storage tank — cone roof",    50.0,  80, 420)
        r101    = self._add_example_block("R-101", "Reactor — jacketed agitated", 30.0, 280, 280)  # transesterificador
        v101    = self._add_example_block("V-101", "Vessel — horizontal",         15.0, 460, 280)  # decanter
        e101    = self._add_example_block("E-101", "Heat exch. — floating head",  60.0, 640, 200)  # secado biodiesel
        tk_bd   = self._add_example_block("TK-103","Storage tank — cone roof",   150.0, 840, 200)  # biodiesel
        tk_gly  = self._add_example_block("TK-104","Storage tank — cone roof",    50.0, 640, 480)  # glicerina

        # Composiciones (fracción másica) — basis 1000 kg input
        oil_in   = {"vegetable_oil": 1.0}
        meoh_in  = {"methanol": 1.0}
        # post-reactor: mezcla compleja (FAME + glicerina + MeOH residual + traces aceite)
        post_rxn = {"biodiesel": 0.905, "glycerin": 0.090, "methanol": 0.005}
        # fase biodiesel (decantación):  ~95% FAME + traces MeOH
        bio_phase = {"biodiesel": 0.985, "methanol": 0.015}
        # fase glicerina: glicerina + MeOH residual
        gly_phase = {"glycerin": 0.85, "methanol": 0.15}
        # biodiesel seco (post stripping de MeOH)
        bio_dry   = {"biodiesel": 1.0}

        # Feeds
        self._add_example_stream(tk_oil, r101, "S-oil", 1000, role="feed",
                                 src_port="salida",   dst_port="alimentacion",
                                 price=950.0, T=25,
                                 composition=oil_in,
                                 main_component="vegetable_oil", phase="liquid")
        self._add_example_stream(tk_meoh, r101, "S-meoh", 105, role="feed",
                                 src_port="salida",   dst_port="util_in",
                                 price=480.0, T=25,
                                 composition=meoh_in,
                                 main_component="methanol", phase="liquid")
        # Post-reactor: efluente bifásico (biodiesel/glicerina)
        self._add_example_stream(r101, v101, "S-1", 0.0,
                                 src_port="producto", dst_port="alimentacion",
                                 T=60,
                                 composition=post_rxn,
                                 main_component="biodiesel", phase="liquid")
        # Decanter: fase liviana (biodiesel, ~990 kg).  El MeOH residual
        # particiona preferencialmente a la fase polar (glicerina), por
        # eso esta fase ya sale seca y la pesada se lleva el MeOH.
        self._add_example_stream(v101, e101, "S-bio-wet", 0.0,
                                 src_port="vapor",    dst_port="tube_in",
                                 T=60,
                                 composition=bio_dry,
                                 main_component="biodiesel", phase="liquid")
        # Biodiesel cooled → tanque producto
        self._add_example_stream(e101, tk_bd, "S-biodiesel", 0.0, role="product",
                                 src_port="tube_out", dst_port="entrada",
                                 price=1350.0, T=50,
                                 composition=bio_dry,
                                 main_component="biodiesel", phase="liquid")
        # Decanter: fase pesada (glicerina + MeOH residual, ~115 kg)
        self._add_example_stream(v101, tk_gly, "S-glycerin", 115, role="product",
                                 src_port="liquido",  dst_port="entrada",
                                 price=350.0, T=60,
                                 composition={"glycerin": 0.78, "methanol": 0.22},
                                 main_component="glycerin", phase="liquid")

        # ---- Calor de reacción transesterificación ----
        # ΔH ≈ -7 kJ/mol triglicérido (levemente exotérmica)
        # = -8 kJ/kg aceite → muy chico
        self.fs.blocks[r101].heat_of_reaction = -8.0

        # ---- Duties auto ----
        from flowsheet_solver import auto_set_duties_from_thermo
        auto_set_duties_from_thermo(self.fs)

        # ---- OPEX extras ----
        # Catalizador NaOH (1% del feed total)
        self._add_example_extra("NaOH catalizador", flowrate=11, price=600.0,
                                stream="Consumables")
        # H2SO4 para neutralizar la glicerina
        self._add_example_extra("H2SO4 neutralizante", flowrate=2, price=300.0,
                                stream="Consumables")

    def _example_crude_distillation(self):
        """Refinería atmosférica simplificada (CDU — Crude Distillation Unit).

        Crudo medio (~30° API) se separa en 3 cortes:
          nafta (tope),  querosén (extracción lateral),  residuo atmosférico (fondo).
        Sin reacción química — separación física por torre de destilación
        con horno y reflujo.

        Mass balance (basis 100 t/h crudo = 876,000 t/año):
          100% feed → 25% nafta + 15% querosén + 60% residuo (aprox)
        Para no manejar números tan grandes, usamos basis 100,000 t/año (planta chica).
        """
        tk_crudo = self._add_example_block("TK-101","Storage tank — cone roof", 600.0,  80, 360)
        p101     = self._add_example_block("P-101", "Pump — centrifugal",        50.0, 240, 385)
        e101     = self._add_example_block("E-101", "Heat exch. — floating head",400.0, 340, 390)
        f101     = self._add_example_block("F-101", "Fired heater — non-reformer", 8000.0, 500, 360)
        t101     = self._add_example_block("T-101", "Tower (column shell)",       80.0, 680, 240)  # CDU column alta

        e102     = self._add_example_block("E-102", "Heat exch. — floating head",250.0, 820, 100)  # cond top (nafta)
        e103     = self._add_example_block("E-103", "Heat exch. — air cooler",   180.0, 820, 260)  # cooler kerosene
        e104     = self._add_example_block("E-104", "Heat exch. — air cooler",   220.0, 820, 420)  # cooler diésel
        e105     = self._add_example_block("E-105", "Heat exch. — air cooler",   200.0, 820, 580)  # cooler residue

        tk_n     = self._add_example_block("TK-102","Storage tank — cone roof", 200.0,1020, 100)  # nafta
        tk_k     = self._add_example_block("TK-103","Storage tank — cone roof", 150.0,1020, 260)  # querosén
        tk_d     = self._add_example_block("TK-104","Storage tank — cone roof", 200.0,1020, 420)  # diésel (NUEVO)
        tk_r     = self._add_example_block("TK-105","Storage tank — cone roof", 400.0,1020, 580)  # residuo

        # Composiciones (proxies de cortes), distribución típica crudo mediano:
        # 22% nafta + 18% kerosén + 28% diésel + 32% residuo = 100%
        crudo_mix  = {"crude_oil": 1.0}
        nafta_mix  = {"naphtha": 0.93, "kerosene": 0.07}
        kero_mix   = {"kerosene": 0.90, "naphtha": 0.05, "diesel": 0.05}
        diesel_mix = {"diesel": 0.88, "kerosene": 0.07, "atmospheric_residue": 0.05}
        res_mix    = {"atmospheric_residue": 0.82, "diesel": 0.18}

        # Feed: 100,000 t/yr crudo
        self._add_example_stream(tk_crudo, p101, "S-crudo", 100000, role="feed",
                                 src_port="salida",   dst_port="succion",
                                 price=600.0, T=25,
                                 composition=crudo_mix,
                                 main_component="crude_oil", phase="liquid")
        # Post-bomba
        self._add_example_stream(p101, e101, "S-1", 0.0,
                                 src_port="descarga", dst_port="tube_in",
                                 T=30,
                                 composition=crudo_mix,
                                 main_component="crude_oil", phase="liquid")
        # Post-preheater (intercambio con productos calientes)
        self._add_example_stream(e101, f101, "S-2", 0.0,
                                 src_port="tube_out", dst_port="proceso_in",
                                 T=180,
                                 composition=crudo_mix,
                                 main_component="crude_oil", phase="liquid")
        # Post-horno: T de flash zone ~360°C
        self._add_example_stream(f101, t101, "S-3", 0.0,
                                 src_port="proceso_out", dst_port="alimentacion",
                                 T=360,
                                 composition=crudo_mix,
                                 main_component="crude_oil", phase="vapor")
        # Tope: nafta vapor (22% del feed)
        self._add_example_stream(t101, e102, "S-nafta-v", 22000,
                                 src_port="vapor_tope", dst_port="tube_in",
                                 T=130,
                                 composition=nafta_mix,
                                 main_component="naphtha", phase="vapor")
        # Nafta producto (condensada)
        self._add_example_stream(e102, tk_n, "S-nafta", 0.0, role="product",
                                 src_port="tube_out", dst_port="entrada",
                                 price=780.0, T=40,
                                 composition=nafta_mix,
                                 main_component="naphtha", phase="liquid")
        # Corte alto: querosén (18% del feed, ~30% desde el tope de la columna)
        self._add_example_stream(t101, e103, "S-kero-h", 18000,
                                 src_port="extraccion_alta", dst_port="proceso_in",
                                 T=215,
                                 composition=kero_mix,
                                 main_component="kerosene", phase="liquid")
        # Querosén producto (enfriado)
        self._add_example_stream(e103, tk_k, "S-kero", 0.0, role="product",
                                 src_port="proceso_out", dst_port="entrada",
                                 price=850.0, T=40,
                                 composition=kero_mix,
                                 main_component="kerosene", phase="liquid")
        # Corte medio: diésel (28% del feed, ~50% del lado de la columna)
        self._add_example_stream(t101, e104, "S-diesel-h", 28000,
                                 src_port="extraccion_media", dst_port="proceso_in",
                                 T=290,
                                 composition=diesel_mix,
                                 main_component="diesel", phase="liquid")
        # Diésel producto (enfriado)
        self._add_example_stream(e104, tk_d, "S-diesel", 0.0, role="product",
                                 src_port="proceso_out", dst_port="entrada",
                                 price=920.0, T=50,
                                 composition=diesel_mix,
                                 main_component="diesel", phase="liquid")
        # Fondo: residuo atmosférico (32% del feed)
        self._add_example_stream(t101, e105, "S-res-h", 0.0,
                                 src_port="liquido_fondo", dst_port="proceso_in",
                                 T=350,
                                 composition=res_mix,
                                 main_component="atmospheric_residue", phase="liquid")
        # Residuo producto (enfriado)
        self._add_example_stream(e105, tk_r, "S-residuo", 0.0, role="product",
                                 src_port="proceso_out", dst_port="entrada",
                                 price=350.0, T=80,
                                 composition=res_mix,
                                 main_component="atmospheric_residue", phase="liquid")

        # No hay reacción química — sólo separación.

        # ---- Duties auto ----
        from flowsheet_solver import auto_set_duties_from_thermo
        auto_set_duties_from_thermo(self.fs)
        self._set_block_duty(p101, +50)    # bomba: eléctrico

    # ======================================================
    # EJEMPLOS INDUSTRIALES (escala real, recycles, > 15 equipos)
    # ======================================================

    def _example_hda_full(self):
        """HDA industrial completo (Douglas) — escala 110,000 t/año feed,
        producción ~85,000 t/año benceno.

        Topología completa con recycle de gas (compresor) + tren de 3
        columnas de destilación: estabilizadora (light ends),
        benceno (producto), y tolueno (reciclo).

        Reacción: C₇H₈ + H₂ → C₆H₆ + CH₄   (~75% conv)
        """
        # ============ Sección reacción (fila superior, y centro 240) ============
        tk_tol_fresh = self._add_example_block("TK-101","Storage tank — cone roof", 600.0,  60, 180)
        p101 = self._add_example_block("P-101", "Pump — centrifugal",                30.0, 180, 215)
        e101 = self._add_example_block("E-101", "Heat exch. — floating head",      1500.0, 290, 220)
        f101 = self._add_example_block("F-101", "Fired heater — non-reformer",    25000.0, 450, 180)
        r101 = self._add_example_block("R-101", "Reactor — jacketed non-agit.",    120.0, 600, 180)
        self.fs.blocks[r101].P_op_bar = 25.0   # HDA ~25 bar
        e102 = self._add_example_block("E-102", "Heat exch. — air cooler",         900.0, 720, 200)
        v101 = self._add_example_block("V-101", "Vessel — vertical",                50.0, 900, 180)
        # Recycle de gas (H₂ + CH₄ light)
        k101 = self._add_example_block("K-101", "Compressor — centrifugal",        300.0, 980, 60)
        # Purga de gas (10% del recycle, para evitar acumulación de CH₄)
        tk_purga = self._add_example_block("TK-102","Storage tank — cone roof",     50.0, 1100, 60)

        # ============ Tren de destilación (fila inferior + lado) ============
        # Estabilizadora: T-101 separa light ends (CH₄ disuelto, gas en el líquido)
        e103 = self._add_example_block("E-103", "Heat exch. — floating head",      400.0,  60, 460)
        t101 = self._add_example_block("T-101", "Tower (column shell)",             80.0, 220, 380)  # stabilizer
        e104 = self._add_example_block("E-104", "Heat exch. — floating head",      300.0, 360, 380)  # cond top T-101 (gas fuel)
        e105 = self._add_example_block("E-105", "Heat exch. — kettle reboiler",    300.0, 220, 620)  # reboiler T-101
        tk_fuel = self._add_example_block("TK-103","Storage tank — cone roof",      50.0, 500, 380)  # off-gas (fuel gas)
        # Columna de benceno: T-102 producto cabeza
        t102 = self._add_example_block("T-102", "Tower (column shell)",            100.0, 640, 440)
        e106 = self._add_example_block("E-106", "Heat exch. — floating head",      500.0, 760, 320)  # cond top T-102 (benceno)
        e107 = self._add_example_block("E-107", "Heat exch. — kettle reboiler",    400.0, 760, 660)  # reboiler T-102
        tk_bz = self._add_example_block("TK-104","Storage tank — cone roof",       500.0, 920, 320)  # benceno producto
        # Columna de tolueno: T-103 recupera tolueno para reciclo
        t103 = self._add_example_block("T-103", "Tower (column shell)",             80.0, 1080, 440)
        e108 = self._add_example_block("E-108", "Heat exch. — floating head",      300.0, 1200, 320)  # cond top
        e109 = self._add_example_block("E-109", "Heat exch. — kettle reboiler",    250.0, 1200, 660)  # reboiler
        tk_pesados = self._add_example_block("TK-105","Storage tank — cone roof",   60.0, 1360, 660)  # difenilo, etc

        # ============ Streams ============
        # Composiciones tipo Douglas (fracciones másicas).
        feed_tol  = {"toluene": 1.0}
        post_rxn  = {"benzene": 0.78, "toluene": 0.13, "methane": 0.06, "hydrogen": 0.03}
        v101_liq  = {"benzene": 0.81, "toluene": 0.13, "methane": 0.05, "hydrogen": 0.01}
        v101_gas  = {"hydrogen": 0.45, "methane": 0.50, "benzene": 0.05}
        t101_top  = {"methane": 0.70, "hydrogen": 0.20, "benzene": 0.10}  # off-gas a fuel
        t101_bot  = {"benzene": 0.86, "toluene": 0.14}    # benceno + tolueno mezcla
        bz_pure   = {"benzene": 0.998, "toluene": 0.002}
        tol_recyc = {"toluene": 0.99, "benzene": 0.01}
        pesados   = {"toluene": 0.20, "atmospheric_residue": 0.80}  # difenilo aprox

        # --- Sección reacción ---
        self._add_example_stream(tk_tol_fresh, p101, "S-feed-tol", 60000, role="feed",
                                 src_port="salida", dst_port="succion",
                                 price=650.0, T=25,
                                 composition=feed_tol,
                                 main_component="toluene", phase="liquid")
        # Post-bomba mezclado con tolueno reciclo
        self._add_example_stream(p101, e101, "S-1", 0.0,
                                 src_port="descarga", dst_port="tube_in",
                                 T=30,
                                 composition=feed_tol,
                                 main_component="toluene", phase="liquid")
        # Post-preheater (HX feed/effluent)
        # Post feed/effluent HX (cross-exchange): el feed pre-calentado
        # con el calor recuperado del efluente del reactor.  Ahorro
        # industrial típico HDA Douglas: ~50% de duty del horno.
        self._add_example_stream(e101, f101, "S-2", 80000,
                                 src_port="tube_out", dst_port="proceso_in",
                                 T=340,
                                 composition=feed_tol,
                                 main_component="toluene", phase="vapor")
        # Post-horno: T reacción ~620°C
        self._add_example_stream(f101, r101, "S-3", 0.0,
                                 src_port="proceso_out", dst_port="alimentacion",
                                 T=620,
                                 composition=feed_tol,
                                 main_component="toluene", phase="vapor")
        # Efluente del reactor → SHELL del feed/effluent HX (cede calor)
        self._add_example_stream(r101, e101, "S-4", 88000,
                                 src_port="producto", dst_port="shell_in",
                                 T=640,
                                 composition=post_rxn,
                                 main_component="benzene", phase="vapor")
        # Efluente ya pre-enfriado por el feed → al cooler final
        self._add_example_stream(e101, e102, "S-4b", 0.0,
                                 src_port="shell_out", dst_port="proceso_in",
                                 T=360,
                                 composition=post_rxn,
                                 main_component="benzene", phase="vapor")
        # Post-cooler: parcialmente condensado
        self._add_example_stream(e102, v101, "S-5", 0.0,
                                 src_port="proceso_out", dst_port="alimentacion",
                                 T=45,
                                 composition=post_rxn,
                                 main_component="benzene", phase="liquid")
        # Gas del flash (recycle a compresor)
        self._add_example_stream(v101, k101, "S-gas-recic", 8800,
                                 src_port="vapor", dst_port="succion",
                                 T=45,
                                 composition=v101_gas,
                                 main_component="hydrogen", phase="gas")
        # Post-compresor: gas comprimido al horno (se uniría con el feed antes de E-101)
        self._add_example_stream(k101, f101, "S-gas-pre", 0.0,
                                 src_port="descarga", dst_port="combustible",
                                 T=80,
                                 composition=v101_gas,
                                 main_component="hydrogen", phase="gas")
        # Purga: 10% del recycle se pierde a fuel gas
        self._add_example_stream(k101, tk_purga, "S-purga", 800, role="product",
                                 src_port="descarga", dst_port="entrada",
                                 price=120.0, T=80,
                                 composition=v101_gas,
                                 main_component="hydrogen", phase="gas")
        # Líquido del flash al pre-cooler antes de estabilizadora
        self._add_example_stream(v101, e103, "S-liq", 0.0,
                                 src_port="liquido", dst_port="tube_in",
                                 T=45,
                                 composition=v101_liq,
                                 main_component="benzene", phase="liquid")
        # Feed de la estabilizadora
        self._add_example_stream(e103, t101, "S-6", 0.0,
                                 src_port="tube_out", dst_port="alimentacion",
                                 T=80,
                                 composition=v101_liq,
                                 main_component="benzene", phase="liquid")

        # --- Estabilizadora T-101: separa light ends del benceno+tolueno ---
        self._add_example_stream(t101, e104, "S-7-light", 5000,
                                 src_port="vapor_tope", dst_port="tube_in",
                                 T=70,
                                 composition=t101_top,
                                 main_component="methane", phase="vapor")
        # Off-gas (a fuel del horno)
        self._add_example_stream(e104, tk_fuel, "S-fuel", 0.0, role="product",
                                 src_port="tube_out", dst_port="entrada",
                                 price=180.0, T=40,
                                 composition=t101_top,
                                 main_component="methane", phase="gas")
        # Fondo estabilizadora: benceno + tolueno al sig. paso
        self._add_example_stream(t101, e105, "S-8", 0.0,
                                 src_port="liquido_fondo", dst_port="liq_in",
                                 T=130,
                                 composition=t101_bot,
                                 main_component="benzene", phase="liquid")
        # Después del reboiler T-101 (su vapor sube; el líquido neto va al sig.)
        self._add_example_stream(e105, t102, "S-9", 0.0,
                                 src_port="cond_out", dst_port="alimentacion",
                                 T=125,
                                 composition=t101_bot,
                                 main_component="benzene", phase="liquid")

        # --- Columna benceno T-102: producto cabeza ---
        self._add_example_stream(t102, e106, "S-10", 0.0,
                                 src_port="vapor_tope", dst_port="tube_in",
                                 T=82,
                                 composition=bz_pure,
                                 main_component="benzene", phase="vapor")
        # Benceno producto
        self._add_example_stream(e106, tk_bz, "S-benceno", 0.0, role="product",
                                 src_port="tube_out", dst_port="entrada",
                                 price=1150.0, T=40,
                                 composition=bz_pure,
                                 main_component="benzene", phase="liquid")
        # Fondo T-102: tolueno (+ algo de benceno) al sig. paso
        self._add_example_stream(t102, e107, "S-11", 21400,
                                 src_port="liquido_fondo", dst_port="liq_in",
                                 T=125,
                                 composition=tol_recyc,
                                 main_component="toluene", phase="liquid")
        self._add_example_stream(e107, t103, "S-12", 0.0,
                                 src_port="cond_out", dst_port="alimentacion",
                                 T=120,
                                 composition=tol_recyc,
                                 main_component="toluene", phase="liquid")

        # --- Columna tolueno T-103: recupera tolueno para reciclo ---
        self._add_example_stream(t103, e108, "S-13", 0.0,
                                 src_port="vapor_tope", dst_port="tube_in",
                                 T=110,
                                 composition=tol_recyc,
                                 main_component="toluene", phase="vapor")
        # Tolueno reciclado al P-101 (mezclado con feed fresco)
        self._add_example_stream(e108, p101, "S-tol-recic", 20000,
                                 src_port="tube_out", dst_port="succion",
                                 T=40,
                                 composition=tol_recyc,
                                 main_component="toluene", phase="liquid")
        # Fondo T-103: difenilo + pesados (purga)
        self._add_example_stream(t103, e109, "S-14", 1400,
                                 src_port="liquido_fondo", dst_port="liq_in",
                                 T=180,
                                 composition=pesados,
                                 main_component="atmospheric_residue", phase="liquid")
        self._add_example_stream(e109, tk_pesados, "S-pesados", 0.0, role="product",
                                 src_port="cond_out", dst_port="entrada",
                                 price=80.0, T=60,
                                 composition=pesados,
                                 main_component="atmospheric_residue", phase="liquid")

        # ---- Calor de reacción HDA ----
        # ΔH ≈ -42 kJ/mol benceno; sobre kg input ≈ -416 kJ/kg
        self.fs.blocks[r101].heat_of_reaction = -416.0

        # ---- Duties auto ----
        from flowsheet_solver import auto_set_duties_from_thermo
        auto_set_duties_from_thermo(self.fs)
        self._set_block_duty(p101, +30)
        self._set_block_duty(k101, +300)

        # ---- OPEX extras ----
        self._add_example_extra("Catalizador Pt/alúmina", flowrate=5.0,
                                price=25_000.0, stream="Consumables")

    def _example_gas_sweetening(self):
        """Endulzamiento de gas natural con MDEA (clásico Camisea).

        Topología: absorber + flash + lean/rich HX + stripper + reflux
        + cooler.  Loop de amina cerrado por Wegstein (el solver
        resuelve el recycle automáticamente).

        Reacciones (gas-líquido, reversibles):
          CO₂ + MDEA + H₂O ⇌ MDEAH⁺ + HCO₃⁻
          H₂S + MDEA       ⇌ MDEAH⁺ + HS⁻
        En el stripper se invierten por calentamiento.
        """
        # Equipos
        t101 = self._add_example_block("T-101", "Tower (column shell)",         200.0,  340, 240)  # absorber
        self.fs.blocks[t101].P_op_bar = 50.0   # absorber MDEA ~50 bar
        v101 = self._add_example_block("V-101", "Vessel — horizontal",           30.0,  500, 460)  # rich flash
        e101 = self._add_example_block("E-101", "Heat exch. — floating head",   800.0,  680, 460)  # lean/rich HX
        t102 = self._add_example_block("T-102", "Tower (column shell)",         150.0,  840, 240)  # stripper
        e102 = self._add_example_block("E-102", "Heat exch. — air cooler",      400.0, 1000, 100)  # cond top stripper
        v102 = self._add_example_block("V-102", "Vessel — horizontal",           20.0, 1180, 100)  # reflux drum
        e103 = self._add_example_block("E-103", "Heat exch. — kettle reboiler", 600.0,  840, 660)  # reboiler stripper
        e104 = self._add_example_block("E-104", "Heat exch. — air cooler",      300.0,  680, 660)  # cooler amina pobre
        p101 = self._add_example_block("P-101", "Pump — centrifugal",            40.0,  500, 685)  # bomba amina recycle
        tk_makeup = self._add_example_block("TK-101","Storage tank — cone roof", 30.0,  100, 660)  # makeup amina
        # Productos off-page
        tk_gas_dulce = self._add_example_block("TK-102","Storage tank — cone roof", 100.0, 340, 60)   # gas dulce
        tk_acid      = self._add_example_block("TK-103","Storage tank — cone roof", 30.0, 1180, 300)  # gas ácido (a Claus)
        # Feed gas off-page
        tk_gas_acido = self._add_example_block("TK-104","Storage tank — cone roof", 200.0, 100, 320)

        # Composiciones (fracción másica)
        # Feed: gas ácido típico Camisea simplificado
        gas_acido = {"methane": 0.84, "ethane": 0.08, "co2": 0.05, "h2s": 0.03}
        gas_dulce = {"methane": 0.91, "ethane": 0.087, "co2": 0.002, "h2s": 0.001}
        # Lean amine: ~40% MDEA en agua (industrial estándar)
        lean_amine = {"mdea": 0.40, "water": 0.60}
        # Rich amine: amina cargada con gases ácidos
        rich_amine = {"mdea": 0.36, "water": 0.55, "co2": 0.06, "h2s": 0.03}
        # Vapor del flash V-101 (hidrocarburos disueltos)
        flash_vap  = {"methane": 0.80, "ethane": 0.15, "co2": 0.04, "h2s": 0.01}
        # Vapor tope stripper (CO₂ + H₂S + algo de agua)
        acid_gas   = {"co2": 0.65, "h2s": 0.30, "water": 0.05}
        water_back = {"water": 1.0}

        # --- Loop principal ---
        # Gas ácido entra al absorber por abajo
        self._add_example_stream(tk_gas_acido, t101, "S-gas-acido", 1000000, role="feed",
                                 src_port="salida", dst_port="liquido_fondo",
                                 price=180.0, T=40,
                                 composition=gas_acido,
                                 main_component="methane", phase="gas")
        # Gas dulce sale por arriba del absorber
        self._add_example_stream(t101, tk_gas_dulce, "S-gas-dulce", 900000, role="product",
                                 src_port="vapor_tope", dst_port="entrada",
                                 price=220.0, T=45,
                                 composition=gas_dulce,
                                 main_component="methane", phase="gas")
        # Amina rica sale por el fondo del absorber → V-101 flash
        self._add_example_stream(t101, v101, "S-rich-amine", 0.0,
                                 src_port="liquido_fondo", dst_port="alimentacion",
                                 T=55,
                                 composition=rich_amine,
                                 main_component="water", phase="liquid")
        # Flash V-101: vapor (HC disueltos) → fuel gas off-page
        # (lo unimos al tanque de gas ácido para simplificar, simbólicamente)
        self._add_example_stream(v101, tk_acid, "S-flash-vap", 50000, role="product",
                                 src_port="vapor", dst_port="entrada",
                                 price=80.0, T=55,
                                 composition=flash_vap,
                                 main_component="methane", phase="gas")
        # Líquido del flash a la HX lean/rich (lado frío de la amina rica)
        self._add_example_stream(v101, e101, "S-rich-cold", 0.0,
                                 src_port="liquido", dst_port="tube_in",
                                 T=55,
                                 composition=rich_amine,
                                 main_component="water", phase="liquid")
        # Pre-calentada por la HX → stripper
        self._add_example_stream(e101, t102, "S-rich-hot", 0.0,
                                 src_port="tube_out", dst_port="alimentacion",
                                 T=95,
                                 composition=rich_amine,
                                 main_component="water", phase="liquid")
        # Stripper T-102: vapor tope (acid gas) → E-102 cond → V-102
        self._add_example_stream(t102, e102, "S-top-strip", 100000,
                                 src_port="vapor_tope", dst_port="proceso_in",
                                 T=105,
                                 composition=acid_gas,
                                 main_component="co2", phase="vapor")
        # E-102 → V-102 reflux drum
        self._add_example_stream(e102, v102, "S-acid-cond", 0.0,
                                 src_port="proceso_out", dst_port="alimentacion",
                                 T=45,
                                 composition=acid_gas,
                                 main_component="co2", phase="liquid")
        # V-102 vapor: CO₂+H₂S a Claus / vent
        self._add_example_stream(v102, tk_acid, "S-acid-gas", 0.0, role="product",
                                 src_port="vapor", dst_port="entrada",
                                 price=0.0, T=45,
                                 composition=acid_gas,
                                 main_component="co2", phase="gas")
        # V-102 líquido (agua) vuelve al stripper como reflux
        self._add_example_stream(v102, t102, "S-reflux", 50000,
                                 src_port="liquido", dst_port="reflujo",
                                 T=45,
                                 composition=water_back,
                                 main_component="water", phase="liquid")
        # Fondo stripper: amina pobre regenerada → reboiler (heat) → HX
        self._add_example_stream(t102, e103, "S-lean-bot", 0.0,
                                 src_port="liquido_fondo", dst_port="liq_in",
                                 T=125,
                                 composition=lean_amine,
                                 main_component="water", phase="liquid")
        # Salida reboiler → lado caliente de la HX lean/rich
        self._add_example_stream(e103, e101, "S-lean-hot", 2500000,
                                 src_port="cond_out", dst_port="shell_in",
                                 T=125,
                                 composition=lean_amine,
                                 main_component="water", phase="liquid")
        # Salida HX (amina pobre tibia) → cooler final
        self._add_example_stream(e101, e104, "S-lean-warm", 2500000,
                                 src_port="shell_out", dst_port="proceso_in",
                                 T=70,
                                 composition=lean_amine,
                                 main_component="water", phase="liquid")
        # Cooler → bomba → top absorber
        self._add_example_stream(e104, p101, "S-lean-cold", 2500000,
                                 src_port="proceso_out", dst_port="succion",
                                 T=40,
                                 composition=lean_amine,
                                 main_component="water", phase="liquid")
        # Makeup de amina fresca (compensa pérdidas)
        self._add_example_stream(tk_makeup, p101, "S-makeup", 2000, role="feed",
                                 src_port="salida", dst_port="succion",
                                 price=2500.0, T=25,
                                 composition=lean_amine,
                                 main_component="mdea", phase="liquid")
        # Bomba → top del absorber (CIERRE DEL RECYCLE)
        self._add_example_stream(p101, t101, "S-lean-feed", 0.0,
                                 src_port="descarga", dst_port="vapor_tope",
                                 T=42,
                                 composition=lean_amine,
                                 main_component="water", phase="liquid")

        # ---- Calor de reacción absorción/regeneración ----
        # Absorber: la absorción de CO₂/H₂S es ligeramente exotérmica.
        # Stripper: la regeneración es endotérmica (igual magnitud, signo opuesto).
        # Para simplificar, lo asignamos al stripper (donde más cuenta).
        self.fs.blocks[t102].heat_of_reaction = +50.0   # +endotérmico (consume calor)

        # ---- Duties auto ----
        from flowsheet_solver import auto_set_duties_from_thermo
        auto_set_duties_from_thermo(self.fs)
        self._set_block_duty(p101, +40)

        # ---- OPEX extras ----
        self._add_example_extra("Antiespumante (silicona)", flowrate=0.5,
                                price=18_000.0, stream="Consumables")
        self._add_example_extra("Filtro de carbón activado", flowrate=2.0,
                                price=8_000.0, stream="Consumables")

    def _example_sugar_mill(self):
        """Planta de azúcar — caña → jugo → cristalización (proceso típico Latam).

        Sin reacción química: separaciones físicas (clarificación,
        evaporación múltiple efecto, cristalización, centrifugación).
        Basis: 100,000 t/año azúcar refino + 80,000 t/año melaza.
        """
        # ============ Sección clarificación + evaporación ============
        tk_jugo  = self._add_example_block("TK-101","Storage tank — cone roof",  800.0,  60, 200)  # jugo crudo
        r101     = self._add_example_block("R-101", "Reactor — jacketed agitated", 50.0, 240, 180)  # encalado
        v101     = self._add_example_block("V-101", "Vessel — vertical",          80.0, 400, 180)  # clarificador
        tk_cach  = self._add_example_block("TK-102","Storage tank — cone roof",  100.0, 240, 460)  # cachaza
        # Tanque de vapor de agua condensada (venteos de evaporadores + secador).
        tk_vap   = self._add_example_block("TK-105","Storage tank — cone roof", 1000.0, 540,  60)  # vapor recuperado
        # Tren de 4 evaporadores (en realidad serían 5, simplificamos a 4)
        ev1      = self._add_example_block("EV-101","Evaporator — vertical",     400.0, 540, 180)
        ev2      = self._add_example_block("EV-102","Evaporator — vertical",     350.0, 720, 180)
        ev3      = self._add_example_block("EV-103","Evaporator — vertical",     300.0, 900, 180)
        ev4      = self._add_example_block("EV-104","Evaporator — vertical",     250.0,1080, 180)
        # ============ Cristalización + centrífuga + secado ============
        r102     = self._add_example_block("R-102", "Crystallizer",              120.0, 380, 500)  # vacuum pan
        fl101    = self._add_example_block("FL-101","Filter — belt",              80.0, 560, 500)  # centrífuga (proxy)
        tk_miel  = self._add_example_block("TK-103","Storage tank — cone roof",  300.0, 560, 700)  # melaza
        dr101    = self._add_example_block("DR-101","Dryer — drum",              120.0, 740, 500)  # secador rotativo
        tk_az    = self._add_example_block("TK-104","Storage tank — cone roof",  400.0, 920, 500)  # azúcar producto

        # Composiciones (fracción másica)
        # Modo solver: fl101 y dr101 tienen separator_active / dryer_active
        # → el solver calcula azúcar húmedo, melaza, azúcar seco y vapor
        # automáticamente desde recovery + moisture (no se declaran acá).
        jugo_in     = {"water": 0.85, "sucrose": 0.135, "glucose": 0.015}
        clarificado = {"water": 0.85, "sucrose": 0.135, "glucose": 0.015}  # mismo (la cal no contabiliza acá)
        cachaza     = {"water": 0.70, "sucrose": 0.05, "glucose": 0.05,
                       "atmospheric_residue": 0.20}                          # bagacillo+impurezas (proxy)
        post_ev1    = {"water": 0.78, "sucrose": 0.198, "glucose": 0.022}
        post_ev2    = {"water": 0.65, "sucrose": 0.315, "glucose": 0.035}
        post_ev3    = {"water": 0.50, "sucrose": 0.45,  "glucose": 0.05}
        post_ev4    = {"water": 0.35, "sucrose": 0.585, "glucose": 0.065}   # miel madre
        # Cristales: azúcar + miel adherida (input al separator)
        masa_cocida = {"sucrose": 0.90, "water": 0.06, "glucose": 0.04}

        # Activar separator (centrífuga) y dryer con modelos internos.
        # FL-101: recovery 75 % de sólidos, 3 % humedad en torta.
        # DR-101: humedad final del azúcar refinado 0.5 %.
        self.fs.blocks[fl101].separator_active   = True
        self.fs.blocks[fl101].solids_recovery    = 0.75
        self.fs.blocks[fl101].cake_moisture      = 0.03
        self.fs.blocks[fl101].solid_components   = ["sucrose", "glucose"]
        self.fs.blocks[dr101].dryer_active       = True
        self.fs.blocks[dr101].final_moisture     = 0.005
        self.fs.blocks[dr101].moisture_component = "water"

        # --- Streams ---
        # Feed jugo crudo (basis 800,000 t/año caña, 85% es jugo)
        self._add_example_stream(tk_jugo, r101, "S-jugo", 680000, role="feed",
                                 src_port="salida", dst_port="alimentacion",
                                 price=15.0, T=30,
                                 composition=jugo_in,
                                 main_component="water", phase="liquid")
        # Encalado → clarificador
        self._add_example_stream(r101, v101, "S-1", 0.0,
                                 src_port="producto", dst_port="alimentacion",
                                 T=70,
                                 composition=clarificado,
                                 main_component="water", phase="liquid")
        # Clarificado (al evaporador)
        self._add_example_stream(v101, ev1, "S-2", 0.0,
                                 src_port="liquido", dst_port="alimentacion",
                                 T=70,
                                 composition=clarificado,
                                 main_component="water", phase="liquid")
        # Cachaza (residuo sólido al tanque)
        self._add_example_stream(v101, tk_cach, "S-cachaza", 20000, role="product",
                                 src_port="vapor", dst_port="entrada",
                                 price=5.0, T=70,
                                 composition=cachaza,
                                 main_component="water", phase="liquid")
        # Tren de 4 evaporadores en serie (cada uno concentra más)
        self._add_example_stream(ev1, ev2, "S-ev1", 0.0,
                                 src_port="producto", dst_port="alimentacion",
                                 T=110,
                                 composition=post_ev1,
                                 main_component="water", phase="liquid")
        self._add_example_stream(ev2, ev3, "S-ev2", 0.0,
                                 src_port="producto", dst_port="alimentacion",
                                 T=105,
                                 composition=post_ev2,
                                 main_component="water", phase="liquid")
        self._add_example_stream(ev3, ev4, "S-ev3", 0.0,
                                 src_port="producto", dst_port="alimentacion",
                                 T=95,
                                 composition=post_ev3,
                                 main_component="water", phase="liquid")
        # Miel madre (final del tren evaporadores)
        self._add_example_stream(ev4, r102, "S-miel-madre", 0.0,
                                 src_port="producto", dst_port="alimentacion",
                                 T=70,
                                 composition=post_ev4,
                                 main_component="sucrose", phase="liquid")
        # Masa cocida al cristalizador (entra al "filtro" = centrífuga proxy)
        self._add_example_stream(r102, fl101, "S-masa", 0.0,
                                 src_port="producto", dst_port="alimentacion",
                                 T=65,
                                 composition=masa_cocida,
                                 main_component="sucrose", phase="liquid")
        # Centrífuga: cristales (azúcar húmedo) → secador
        # mass_flow + composition CALCULADOS por solve_separators
        # (separator_active=True en fl101 con recovery=0.75, moist=0.03).
        self._add_example_stream(fl101, dr101, "S-az-humedo",
                                 src_port="producto", dst_port="alimentacion",
                                 T=60, phase="liquid")
        # Centrífuga: melaza (al tanque sub-producto) — comp calculada
        self._add_example_stream(fl101, tk_miel, "S-melaza", role="product",
                                 src_port="venteo", dst_port="entrada",
                                 price=180.0, T=60, phase="liquid")
        # Azúcar seco al tanque producto (comp calculada por dr101)
        self._add_example_stream(dr101, tk_az, "S-azucar", role="product",
                                 src_port="producto", dst_port="entrada",
                                 price=550.0, T=45, phase="liquid")

        # ---- Venteos de vapor (cierran el balance de masa de los EV) ----
        water_vap = {"water": 1.0}
        self._add_example_stream(ev1, tk_vap, "S-vap1", 200000,
                                 src_port="venteo", dst_port="entrada",
                                 T=110, composition=water_vap,
                                 main_component="water", phase="vapor")
        self._add_example_stream(ev2, tk_vap, "S-vap2", 170000,
                                 src_port="venteo", dst_port="entrada",
                                 T=105, composition=water_vap,
                                 main_component="water", phase="vapor")
        self._add_example_stream(ev3, tk_vap, "S-vap3", 90000,
                                 src_port="venteo", dst_port="entrada",
                                 T=95, composition=water_vap,
                                 main_component="water", phase="vapor")
        self._add_example_stream(ev4, tk_vap, "S-vap4", 45000,
                                 src_port="venteo", dst_port="entrada",
                                 T=70, composition=water_vap,
                                 main_component="water", phase="vapor")
        # S-vap-dry: vapor de agua del secador (mass+comp calculadas)
        self._add_example_stream(dr101, tk_vap, "S-vap-dry",
                                 src_port="venteo", dst_port="entrada",
                                 T=80, phase="vapor")

        # ---- Duties auto ----
        from flowsheet_solver import auto_set_duties_from_thermo
        auto_set_duties_from_thermo(self.fs)

        # ---- OPEX extras ----
        self._add_example_extra("Cal viva CaO (clarificación)", flowrate=200,
                                price=180.0, stream="Consumables")
        self._add_example_extra("Sacos de polipropileno", flowrate=500,
                                price=600.0, stream="Consumables")

    def _example_smr_equilibrium(self):
        """Reformado de metano con vapor (SMR + WGS) — REACTOR DE
        EQUILIBRIO Capa 4.  Demuestra el solver multi-reacción.

        Reacciones:
          R003: CH4 + H2O → CO + 3H2     (SMR, endotérmica fuerte)
          R002: CO + H2O → CO2 + H2      (Water-Gas Shift, exotérmica)

        Operación: T = 1100 K (827°C), P = 25 bar.  S/C = 3 (relación
        molar vapor/carbono típica industrial).  Conversión CH4 ≈ 49%
        a estas condiciones (Le Chatelier: P alta penaliza Δν=+2).

        Tren:  feed CH4 + vapor → mezclador → precalentador → reactor
               SMR+WGS → enfriador → knockout drum → syngas seco /
               agua condensada.

        Este ejemplo NO declara composición de salida del reactor —
        el solver Capa 4 la calcula automáticamente y la propaga
        downstream.  El user puede cambiar T_op_K/P_op_bar y ver
        cómo cambia todo el balance.
        """
        # Layout PFD industrial (1600×960 paper)
        # Top row y=200: TK-CH4 → M-101 → F-101 → R-101 → E-101 → V-101
        # Right side: TK-syngas (top), TK-agua (bottom)
        tk_ch4   = self._add_example_block("TK-101","Storage tank — cone roof",  500.0,  60, 220)
        tk_steam = self._add_example_block("TK-102","Storage tank — cone roof", 1000.0,  60, 460)
        m101     = self._add_example_block("M-101", "Mixer — static",              5.0, 240, 320)
        f101     = self._add_example_block("F-101", "Fired heater — non-reformer",
                                            8000.0, 400, 320)   # precalentador
        r101     = self._add_example_block("R-101", "Reactor — jacketed non-agit.",
                                            50.0, 600, 320)   # SMR+WGS reformer
        e101     = self._add_example_block("E-101", "Heat exch. — air cooler",
                                           400.0, 800, 320)   # syngas cooler
        v101     = self._add_example_block("V-101", "Vessel — vertical",
                                            25.0, 980, 320)   # KO drum
        tk_syn   = self._add_example_block("TK-103","Storage tank — cone roof",
                                           300.0,1180, 220)   # syngas seco producto
        tk_h2o   = self._add_example_block("TK-104","Storage tank — cone roof",
                                           400.0,1180, 460)   # agua condensada

        # ---- Configurar R-101 como REACTOR DE EQUILIBRIO Capa 4 ----
        # Las dos reacciones del SMR industrial: reformado + WGS.
        self.fs.blocks[r101].reactions = ["R003", "R002"]
        self.fs.blocks[r101].T_op_K   = 1100.0    # 827°C, típico tubo SMR
        self.fs.blocks[r101].P_op_bar = 25.0      # 25 bar, presión moderada

        # ---- Streams ----
        # Basis: 1000 tm/año CH4 puro.  Para S/C=3 molar:
        #   moles vapor = 3 · moles CH4
        #   masa  vapor = 3 · (18.015/16.04) · masa CH4 = 3.37 · masa CH4
        #   → vapor = 3370 tm/año
        # Total mix = 4370 tm/año (conservación a través del reactor).
        # Después del KO drum a ~40°C, el agua condensa y se separa.

        # Feed CH4 (asumimos gas natural ≈ 100% metano para el ejemplo)
        self._add_example_stream(tk_ch4, m101, "S-CH4", 1000, role="feed",
                                  src_port="salida", dst_port="entrada1",
                                  price=120.0, T=25,
                                  main_component="methane", phase="gas")
        # Vapor de proceso a alta T (sale de un boiler upstream, no
        # modelamos el boiler para no complicar)
        self._add_example_stream(tk_steam, m101, "S-vapor", 3370, role="feed",
                                  src_port="salida", dst_port="entrada2",
                                  price=12.0, T=200,
                                  main_component="water", phase="vapor")
        # Mezcla → precalentador
        self._add_example_stream(m101, f101, "S-mix",
                                  src_port="salida", dst_port="alimentacion",
                                  T=180,
                                  composition={"methane": 0.2289, "water": 0.7711},
                                  main_component="water", phase="vapor")
        # Mezcla precalentada → reactor (T elevada por el horno)
        self._add_example_stream(f101, r101, "S-precal",
                                  src_port="salida", dst_port="alimentacion",
                                  T=600,                  # 873 K, entra al reactor
                                  composition={"methane": 0.2289, "water": 0.7711},
                                  main_component="water", phase="vapor")
        # Salida del reactor: SYNGAS CRUDO.
        # NO declaramos composición ni mass_flow — el solver Capa 4
        # los computa.  T = T_op del reactor (1100 K = 827°C).
        self._add_example_stream(r101, e101, "S-syngas-hot",
                                  src_port="producto", dst_port="proceso_in",
                                  T=827,                  # = T_op_K - 273
                                  main_component="hydrogen", phase="gas")
        # Syngas enfriado (parcialmente condensado)
        self._add_example_stream(e101, v101, "S-syngas-cool",
                                  src_port="proceso_out", dst_port="alimentacion",
                                  T=40,                   # cerca del rocío del agua
                                  main_component="water", phase="two_phase")
        # KO drum: vapor (syngas seco) → tanque producto
        # A 1100K/25bar el equilibrio da ~59% mass de agua.  Después
        # del KO drum a 40°C ~todo el agua condensa.  Syngas seco
        # ≈ 4370 × 0.408 = 1783 tm/año (CH4 + CO + H2 + CO2).
        self._add_example_stream(v101, tk_syn, "S-syngas",  1783, role="product",
                                  src_port="vapor", dst_port="entrada",
                                  price=180.0, T=40,
                                  composition={"methane": 0.288, "co": 0.266,
                                                "hydrogen": 0.118, "co2": 0.330},
                                  main_component="hydrogen", phase="gas")
        # KO drum: líquido (agua) → tanque agua.  mass_flow se DEDUCE
        # del balance: 4370 - 1783 = 2587 tm/año.
        self._add_example_stream(v101, tk_h2o, "S-condensado", role="product",
                                  src_port="liquido", dst_port="entrada",
                                  price=2.0, T=40,
                                  main_component="water", phase="liquid",
                                  composition={"water": 1.0})

        # ---- Duties: el solver Capa 4 setea heat_of_reaction de R-101
        # automáticamente desde Σξ·ΔH(T).  El precalentador F-101 y
        # el cooler E-101 se infieren por balance de energía. ----
        from flowsheet_solver import auto_set_duties_from_thermo
        auto_set_duties_from_thermo(self.fs)

        # OPEX extras: catalizador NiO/Al2O3 (vida ~5 años)
        self._add_example_extra("Catalizador NiO/Al2O3 (SMR)",
                                 flowrate=3, price=25_000.0,
                                 stream="Consumables")
        self._add_example_extra("Catalizador Fe2O3/Cr2O3 (HT-WGS)",
                                 flowrate=2, price=8_000.0,
                                 stream="Consumables")

    def _example_ethane_cracker_pfr(self):
        """Cracker de etano (R011) — REACTOR PFR Capa 5 con cinética
        Arrhenius real.  Demuestra solve_pfr integrado al flowsheet.

        Reacción:
          R011: C2H6 → C2H4 + H2     (Δν=+1, endotérmica fuerte)

        Operación: T = 1100 K (~827 °C, horno típico), P = 2 bar.
        Cinética: k₀=4.65e13 s⁻¹, Ea=273 kJ/mol (Froment-Bischoff).
        Equilibrio termo a 1100K/2bar: conv_C2H6 ≈ 51%.

        Tren:  feed C2H6 → horno-precalentador F-101 → reactor PFR
               R-101 → enfriador rápido E-101 → tanque producto
               (mezcla C2H6 sin reaccionar + C2H4 + H2)

        El user puede cambiar V_reactor desde la UI y ver cómo varía
        la conversión hacia el límite de equilibrio termodinámico.
        """
        # Layout: línea horizontal
        tk_in   = self._add_example_block("TK-101","Storage tank — cone roof",  400.0,  60, 280)
        f101    = self._add_example_block("F-101", "Fired heater — non-reformer",
                                            3000.0, 260, 280)
        r101    = self._add_example_block("R-101", "Reactor — jacketed non-agit.",
                                             80.0, 460, 280)
        e101    = self._add_example_block("E-101", "Heat exch. — air cooler",
                                           300.0, 660, 280)
        tk_out  = self._add_example_block("TK-102","Storage tank — cone roof",
                                           400.0, 860, 280)

        # Configurar R-101 como REACTOR PFR Capa 5
        self.fs.blocks[r101].reactions = ["R011"]
        self.fs.blocks[r101].reactor_mode = "pfr"
        self.fs.blocks[r101].T_op_K = 1100.0          # 827°C
        self.fs.blocks[r101].P_op_bar = 2.0
        self.fs.blocks[r101].reactor_volume_L = 50.0   # 50 L típico horno chico

        # Streams.
        # Basis: 1000 tm/año C2H6 puro = 30.07 kg/h = 0.00836 kg/s
        # = 0.278 mol/s C2H6 entrante (MW C2H6 = 30.07 g/mol)
        # A 1100K/2bar, Q_in = 0.278·8.314·1100/2e5 = 0.0127 m³/s
        # τ con V=50L: τ = 0.050/0.0127 = 3.94 s
        # Conv esperada a 1100K, V=50L: ~50% (cerca del equilibrio termo)

        self._add_example_stream(tk_in, f101, "S-C2H6", 1000, role="feed",
                                  src_port="salida", dst_port="alimentacion",
                                  price=600.0, T=25,
                                  main_component="ethane", phase="gas",
                                  composition={"ethane": 1.0})
        # Precalentado al horno
        self._add_example_stream(f101, r101, "S-precal",
                                  src_port="salida", dst_port="alimentacion",
                                  T=600,
                                  main_component="ethane", phase="gas",
                                  composition={"ethane": 1.0})
        # Salida del reactor — composition se calcula automáticamente
        self._add_example_stream(r101, e101, "S-cracked",
                                  src_port="producto", dst_port="proceso_in",
                                  T=827,
                                  main_component="ethylene", phase="gas")
        # Producto enfriado
        self._add_example_stream(e101, tk_out, "S-product", 0.0, role="product",
                                  src_port="proceso_out", dst_port="entrada",
                                  price=900.0, T=40,
                                  main_component="ethylene", phase="gas")

        # OPEX: catalizador no aplica (cracking térmico sin catalizador)
        # pero sí gas natural para el horno:
        self._add_example_extra("Gas natural (F-101 horno)",
                                 flowrate=200, price=180.0,
                                 stream="Utilities")

    def _example_haber_recycle(self):
        """Síntesis de amoníaco (Haber-Bosch) con recycle real.

        El reactor industrial Haber convierte solo 15-20% por paso del
        N2 a NH3 (equilibrio termo a 700K/200bar es 58%, pero cinético
        en planta es menor).  Para alcanzar conv global 99% se usa
        recirculación masiva de gases sin reaccionar.

        Reacción:  N2 + 3 H2 → 2 NH3   (R004, Δν=-2, exotérmica)

        Tren:
          TK-fresh ──> M-101 <── recycle
                         │
                         ▼
                       F-101 (heater)
                         │
                         ▼
                       R-101 (Haber, 700K, 200 bar, equilibrium)
                         │
                         ▼
                       SEP-101 (separador NH3 — condensación)
                          │       │
                          ▼       ▼
                        TK-NH3  PSPLT (split purge/recycle)
                                │  │
                                ▼  ▼
                              TK-purge  → recycle ↩

        Demuestra el LOOP COMPOSICIONAL del solver — el reactor se
        re-resuelve en cada iteración hasta que la composición del
        recycle converge.  Cambiar recycle.mass_flow desde la UI
        ajusta la conversión por pasada (más recycle → mezcla más
        saturada de NH3 → menos conv por paso, signo Le Chatelier).
        """
        # Layout PFD industrial 1600×960
        tk_fresh = self._add_example_block("TK-101","Storage tank — cone roof", 500.0,  60, 260)
        m101     = self._add_example_block("M-101", "Mixer — static",            5.0, 240, 320)
        f101     = self._add_example_block("F-101", "Heat exch. — floating head",
                                            300.0, 400, 320)
        r101     = self._add_example_block("R-101", "Reactor — jacketed agitated",
                                             80.0, 580, 320)
        sep101   = self._add_example_block("V-101", "Vessel — vertical",         50.0, 780, 320)
        psplt    = self._add_example_block("V-102", "Vessel — vertical",         20.0, 780, 500)
        tk_nh3   = self._add_example_block("TK-102","Storage tank — cone roof", 300.0, 980, 260)
        tk_purge = self._add_example_block("TK-103","Storage tank — cone roof",  50.0, 980, 500)

        # Configurar R-101 como reactor de equilibrio Haber
        self.fs.blocks[r101].reactions = ["R004"]
        self.fs.blocks[r101].reactor_mode = "equilibrium"
        self.fs.blocks[r101].T_op_K = 700.0
        self.fs.blocks[r101].P_op_bar = 200.0

        # Basis: 1000 tm/año feed fresco N2+H2 estequiométrico
        # N2:H2 = 1:3 molar → mass = 28+6 = 34 g; mfrac N2=0.824, H2=0.176
        # NH3 producto ≈ feed − purge = 950 tm/año (95% conv global)
        # Recycle: 5000 tm/año (5× feed_fresh — ratio típico industrial)
        # to-rx = 6000 tm/año (M-101 mezcla)
        # rx-out = 6000 (conservación)
        # gases = rx-out − NH3 = 5050; gases = purge + recycle ✓

        # Feed fresco (única corriente con composición declarada — todo
        # lo demás se propaga por mixer + reactor + balance).  Por eso
        # NO declaramos main_component en streams intermedios: el flag
        # composition_locked se activaría y bloquearía la propagación.
        self._add_example_stream(tk_fresh, m101, "S-fresh", 1000, role="feed",
                                  src_port="salida", dst_port="entrada1",
                                  price=0.0, T=25,
                                  composition={"nitrogen": 0.824, "hydrogen": 0.176},
                                  main_component="nitrogen", phase="gas")
        # Mezcla → heater
        self._add_example_stream(m101, f101, "S-mix",
                                  src_port="salida", dst_port="tube_in",
                                  T=80, phase="gas")
        # Heater → Reactor
        self._add_example_stream(f101, r101, "S-precal",
                                  src_port="tube_out", dst_port="alimentacion",
                                  T=400, phase="gas")
        # Reactor → Separador (composición la setea solve_equilibrium_reactors)
        self._add_example_stream(r101, sep101, "S-rx-out",
                                  src_port="producto", dst_port="alimentacion",
                                  T=427, phase="gas")
        # Separador → NH3 producto (condensación: NH3 puro)
        self._add_example_stream(sep101, tk_nh3, "S-NH3", 950, role="product",
                                  src_port="liquido", dst_port="entrada",
                                  price=750.0, T=40,
                                  composition={"ammonia": 1.0},
                                  main_component="ammonia", phase="liquid")
        # Separador → splitter purge/recycle (gases sin reaccionar)
        self._add_example_stream(sep101, psplt, "S-gases",
                                  src_port="vapor", dst_port="alimentacion",
                                  T=40, phase="gas")
        # Splitter → purge (5% del feed_fresh)
        self._add_example_stream(psplt, tk_purge, "S-purge", 50, role="waste",
                                  src_port="vapor", dst_port="entrada",
                                  price=0.0, T=40, phase="gas")
        # Splitter → recycle ↩ a M-101 (SPEC clave: declara el ratio recycle)
        self._add_example_stream(psplt, m101, "S-recycle", 5000,
                                  src_port="liquido", dst_port="entrada2",
                                  T=40, phase="gas")

        # OPEX: catalizador Fe-K2O Haber
        self._add_example_extra("Catalizador Fe-K2O (Haber)",
                                 flowrate=5, price=15_000.0,
                                 stream="Consumables")

    def _example_distillation_ethanol_water(self):
        """Destilación etanol-agua — DEMO DEL AZEOTROPO (Capa 6).

        Sistema clásico no-ideal: etanol forma azeotropo positivo con
        agua a 89.4% mol etanol (95.6% peso) y 78.15°C @ 1 atm.  Una
        columna de destilación simple NO puede pasar de esa pureza.

        Tren:
          TK-feed (fermentación, 12% peso eth) → P-101 (bomba) →
          E-101 (precalentador) → T-101 (columna destilación) →
            ├─ E-102 (condensador) → TK-eth (azeo, 95.6% peso máx)
            └─ E-103 (reboiler)    → TK-water (residuo agua)

        El feed simula caldo de fermentación industrial (12% mass eth).
        El destilado sale al límite azeotrópico (95.6% mass eth) — NO
        se puede alcanzar etanol absoluto (99.5%+) sin destilación
        azeotrópica o extractive con benceno/glicol/MSP.

        Al seleccionar S-distillate verás en el panel '⚠ AZEOTROPO':
        el solver Capa 6 detecta y advierte.
        """
        # Layout
        tk_feed = self._add_example_block("TK-101","Storage tank — cone roof", 800.0,  60, 320)
        p101    = self._add_example_block("P-101", "Pump — centrifugal",         5.0, 240, 320)
        e101    = self._add_example_block("E-101", "Heat exch. — floating head", 80.0, 380, 320)
        t101    = self._add_example_block("T-101", "Tower (column shell)",       45.0, 540, 280)
        e102    = self._add_example_block("E-102", "Heat exch. — air cooler",   120.0, 720, 200)
        e103    = self._add_example_block("E-103", "Heat exch. — kettle reboiler", 110.0, 700, 460)
        tk_eth  = self._add_example_block("TK-102","Storage tank — cone roof",  200.0, 900, 200)
        tk_h2o  = self._add_example_block("TK-103","Storage tank — cone roof",  400.0, 900, 460)

        # Composiciones — TODAS multicomponente para que el análisis
        # NRTL del stream tenga 2 componentes.
        # Feed: caldo de fermentación industrial 12% mass eth (~5% mol)
        feed_comp = {"ethanol": 0.12, "water": 0.88}
        # Pre-calentado al BP del feed (~96°C, mezcla eth/water)
        # Distillate: límite azeotrópico = 95.6% mass eth = 89.4% mol
        # (mol→mass: x_mol_eth=0.894 · 46.07 / (0.894·46.07 + 0.106·18.015)
        #  = 41.2 / 43.1 = 0.956)
        # En este ejemplo declaramos en mol equivalente (Capa 6 trabaja en mol)
        # 95.6% mass eth para mantener consistencia con resto del flowsheet.
        distillate_comp = {"ethanol": 0.956, "water": 0.044}
        # Bottom: agua casi pura (residuos sólidos no modelados)
        bottom_comp = {"water": 0.998, "ethanol": 0.002}

        # Feed → bomba (asumimos 12% mass eth en caldo, 10000 tm/año)
        self._add_example_stream(tk_feed, p101, "S-caldo", 10000, role="feed",
                                  src_port="salida", dst_port="succion",
                                  price=80.0, T=30,
                                  composition=feed_comp, phase="liquid")
        # Bomba → pre-heater
        self._add_example_stream(p101, e101, "S-pumped",
                                  src_port="descarga", dst_port="tube_in",
                                  T=32, phase="liquid")
        # Pre-heater → columna
        self._add_example_stream(e101, t101, "S-feed-hot",
                                  src_port="tube_out", dst_port="alimentacion",
                                  T=85, phase="two_phase")
        # Columna tope → condensador
        self._add_example_stream(t101, e102, "S-vap-tope",
                                  src_port="vapor_tope", dst_port="shell_in",
                                  T=78,           # = T_az aprox
                                  composition=distillate_comp, phase="vapor")
        # Condensador → producto etanol (azeo)
        # Balance: feed 12% mass eth × 10000 = 1200 tm/año eth.
        # Si distillate = 95.6% mass eth y captura 99% del eth feed:
        # m_dist = (0.99 · 1200) / 0.956 = 1242 tm/año
        self._add_example_stream(e102, tk_eth, "S-distillate", 1242, role="product",
                                  src_port="shell_out", dst_port="entrada",
                                  price=900.0, T=40,
                                  composition=distillate_comp, phase="liquid")
        # Columna fondo → reboiler
        self._add_example_stream(t101, e103, "S-fondo-liq",
                                  src_port="liquido_fondo", dst_port="liq_in",
                                  T=100,
                                  composition=bottom_comp, phase="liquid")
        # Reboiler → bottom product (agua)
        # m_bottom = feed - distillate = 10000 - 1242 = 8758 tm/año
        self._add_example_stream(e103, tk_h2o, "S-bottom", 8758, role="waste",
                                  src_port="cond_out", dst_port="entrada",
                                  price=0.0, T=40,
                                  composition=bottom_comp, phase="liquid")

        # OPEX extras
        self._add_example_extra("Vapor MP (reboiler)",
                                 flowrate=5000, price=12.0,
                                 stream="Utilities")
        self._add_example_extra("Agua de enfriamiento (condensador)",
                                 flowrate=80000, price=0.05,
                                 stream="Utilities")

    def _example_hydraulic_plant(self):
        """Planta hidráulica completa — demo del solver acoplado.

        Demuestra:
          · Auto-sizing de bombas con P locked en producto
          · Pérdida de carga en tuberías con K_local (codos, válvulas)
          · ΔP en HX y columna (declarados)
          · Cálculo automático de W_elec por equipo rotativo

        Tren:
          TK-feed @ 1 bar 🔒
              ↓ (20 m, 4 codos = K=3)
          P-101 (auto-size)
              ↓ (15 m)
          E-101 HX (ΔP=-0.5)
              ↓ (30 m, válvula gate = K=0.17)
          T-101 columna (ΔP=-0.3)
              ↓ (10 m)
          TK-prod @ 4 bar 🔒
        """
        # Layout
        tk_feed = self._add_example_block("TK-101","Storage tank — cone roof",
                                            500.0,  60, 280)
        p101    = self._add_example_block("P-101","Pump — centrifugal",
                                            10.0, 240, 280)
        e101    = self._add_example_block("E-101","Heat exch. — floating head",
                                           250.0, 420, 280)
        t101    = self._add_example_block("T-101","Tower (column shell)",
                                            45.0, 620, 280)
        tk_prod = self._add_example_block("TK-102","Storage tank — cone roof",
                                            400.0, 840, 280)

        # Configurar bomba P-101 en modo AUTO (delta_p_bar=0 → solver
        # decide)
        self.fs.blocks[p101].delta_p_bar = 0.0
        self.fs.blocks[p101].efficiency = 0.75
        # Configurar HX y columna con ΔP declarado
        self.fs.blocks[e101].delta_p_bar = -0.5
        self.fs.blocks[t101].delta_p_bar = -0.3

        # Streams con tubería declarada
        s_feed = self._add_example_stream(tk_feed, p101, "S-feed", 5000,
                                            role="feed",
                                            src_port="salida", dst_port="succion",
                                            price=80.0, T=25,
                                            composition={"water": 1.0},
                                            phase="liquid")
        # Configurar P locked en feed (1 bar) y pipe
        feed_s = self.fs.streams[s_feed]
        feed_s.pressure_bar = 1.013
        feed_s.pressure_locked = True
        feed_s.pipe_length_m = 20.0
        feed_s.pipe_diameter_m = 0.050
        feed_s.pipe_K_local = 3.0   # 4 codos

        s_pumped = self._add_example_stream(p101, e101, "S-pumped",
                                              src_port="descarga", dst_port="tube_in",
                                              T=26,
                                              composition={"water": 1.0},
                                              phase="liquid")
        self.fs.streams[s_pumped].pipe_length_m = 15.0
        self.fs.streams[s_pumped].pipe_diameter_m = 0.050

        s_cooled = self._add_example_stream(e101, t101, "S-cooled",
                                              src_port="tube_out", dst_port="alimentacion",
                                              T=40,
                                              composition={"water": 1.0},
                                              phase="liquid")
        self.fs.streams[s_cooled].pipe_length_m = 30.0
        self.fs.streams[s_cooled].pipe_diameter_m = 0.050
        self.fs.streams[s_cooled].pipe_K_local = 0.17   # 1 válvula gate

        s_prod = self._add_example_stream(t101, tk_prod, "S-product", 0.0,
                                            role="product",
                                            src_port="liquido_fondo", dst_port="entrada",
                                            price=120.0, T=40,
                                            composition={"water": 1.0},
                                            phase="liquid")
        # P locked en el producto = target downstream
        prod_s = self.fs.streams[s_prod]
        prod_s.pressure_bar = 4.0
        prod_s.pressure_locked = True
        prod_s.pipe_length_m = 10.0
        prod_s.pipe_diameter_m = 0.050

    def _example_reactor_flash_column(self):
        """Tren completo AUTOMÁTICO: reactor + flash + columna —
        cada equipo calcula sus outputs sin que el user los declare.

        Ejemplo: producción de etanol via fermentación + destilación.
          TK-glucose → R-101 (fermentación, equilibrio)
                       → E-101 (cooler)
                       → V-101 (flash isotérmico — separa CO2 gas)
                       → T-101 (columna FUG — separa eth de water)
                              ├── distillate → TK-etanol (80% eth)
                              └── bottoms → TK-agua

        Demuestra:
          · Reactor escribe composición de salida via R007 (fermentación)
          · Flash separa CO2 vapor del líquido eth/water/glucose
          · Columna recibe líquido y diseña FUG automáticamente
          · TODOS los outputs se CALCULAN, ninguno declarado.
        """
        # Layout horizontal
        tk_glu = self._add_example_block("TK-101","Storage tank — cone roof", 500.0,  60, 280)
        r101   = self._add_example_block("R-101", "Reactor — jacketed agitated", 50.0, 260, 280)
        e101   = self._add_example_block("E-101", "Heat exch. — air cooler",    180.0, 460, 280)
        v101   = self._add_example_block("V-101", "Vessel — vertical",           25.0, 640, 280)
        tk_co2 = self._add_example_block("TK-102","Storage tank — cone roof",  100.0, 820, 140)
        t101   = self._add_example_block("T-101", "Tower (column shell)",        45.0, 840, 360)
        tk_eth = self._add_example_block("TK-103","Storage tank — cone roof",  300.0,1040, 240)
        tk_h2o = self._add_example_block("TK-104","Storage tank — cone roof",  500.0,1040, 480)

        # Configurar reactor R-101 (fermentación glucosa → etanol + CO2)
        # NOTA: R007 fermentación no está derivada de Capa 3 (no tiene
        # cinética/equilibrio formal), así que usamos heat_of_reaction
        # manual y declaramos composición de output del reactor.
        # En su lugar, hagamos un sistema con R002 WGS que sí tiene NRTL.
        # Mejor cambiar a algo válido en NRTL: ethanol-water destilación
        # ENT ya que no tenemos producción de ethanol en NRTL.
        # Vamos con un caso más simple: feed multicomp → flash → columna.

        # FEED: simulamos salida de un reactor de fermentación = caldo
        # con eth/water/glucose. Usamos el feed como mezcla ya hecha.
        # Esto demuestra el FLASH y la COLUMNA automáticos.

        # Configurar V-101 como flash automático
        self.fs.blocks[v101].flash_active = True
        self.fs.blocks[v101].flash_T_K = 360.0    # 87°C
        self.fs.blocks[v101].flash_P_bar = 1.013

        # Configurar T-101 como columna automática
        self.fs.blocks[t101].column_active = True
        self.fs.blocks[t101].column_LK = "ethanol"
        self.fs.blocks[t101].column_HK = "water"
        self.fs.blocks[t101].column_x_D_LK = 0.85   # 85% eth en distillate
        self.fs.blocks[t101].column_x_B_LK = 0.01   # 1% en bottom
        self.fs.blocks[t101].column_R_factor = 1.5

        # Feed: caldo de fermentación 10000 tm/año eth/water/glucose
        self._add_example_stream(tk_glu, r101, "S-mosto", 10000, role="feed",
                                  src_port="salida", dst_port="alimentacion",
                                  price=80.0, T=30,
                                  composition={"water": 0.85, "glucose": 0.12,
                                                 "ethanol": 0.03},
                                  phase="liquid")
        # Reactor → cooler (composición del reactor manual: declaramos
        # post-fermentación). Para no usar R007 que no tiene NRTL.
        self._add_example_stream(r101, e101, "S-fermentado",
                                  src_port="producto", dst_port="proceso_in",
                                  T=32,
                                  composition={"water": 0.815, "ethanol": 0.085,
                                                 "co2": 0.080, "glucose": 0.020},
                                  phase="liquid")
        # Cooler → flash
        self._add_example_stream(e101, v101, "S-cooled",
                                  src_port="proceso_out", dst_port="alimentacion",
                                  T=87, phase="two_phase")
        # Flash → CO2 vapor (calculado por flash_active)
        self._add_example_stream(v101, tk_co2, "S-CO2-vapor", role="waste",
                                  src_port="vapor", dst_port="entrada",
                                  price=0.0, T=87)
        # Flash → líquido (calculado, va a la columna)
        self._add_example_stream(v101, t101, "S-cleaned",
                                  src_port="liquido", dst_port="alimentacion",
                                  T=87)
        # Columna → distillate (calculado por column_active)
        self._add_example_stream(t101, tk_eth, "S-etanol", role="product",
                                  src_port="vapor_tope", dst_port="entrada",
                                  price=900.0, T=78)
        # Columna → bottoms (calculado)
        self._add_example_stream(t101, tk_h2o, "S-agua", role="waste",
                                  src_port="liquido_fondo", dst_port="entrada",
                                  price=0.0, T=100)

        # Calor de reacción de la fermentación (R007, exotérmica leve)
        # NOTA: R007 no está en NRTL pero usa heat_of_reaction declarado.
        self.fs.blocks[r101].heat_of_reaction = -100.0  # kJ/kg input

        self._add_example_extra("Levaduras (Saccharomyces)",
                                 flowrate=20, price=400.0, stream="Consumables")

    def _example_industrial_complete(self):
        """Planta industrial COMPLETA con servicios — flagship example.

        Síntesis de metanol con BOP (Balance of Plant) industrial real:
          · Sección 100: REACCIÓN (compresor + intercooler + mixer +
            preheater + reactor equilibrio Cu/ZnO + WHB)
          · Sección 200: SEPARACIÓN (flash flash NRTL + columna FUG MeOH/
            water + condensador + KO drum post-condensador + reboiler
            con steam-side)
          · Sección 300: SERVICIOS (boiler con BFW + steam drum + header
            MP + cooling water tower)
          · Sección 400: TRATAMIENTO (purge gas, vent gas KO, blowdown,
            water bottoms, condensate del ciclo de vapor)

        Demuestra:
          · RECYCLE DE SYNGAS: V-201 vapor → V-203 splitter (9% purga
            / 91% recycle) → K-202 compresor → M-101 (entrada2).
            Recycle ratio = 5× fresh, típico industrial.  Crea un
            SCC que el solver detecta y resuelve con Wegstein.
          · CICLO DE VAPOR CERRADO: BFW → P-301 → F-301 (boiler) →
            V-301 (drum) → TK-305 (header MP) → E-202 (reboiler shell
            side) → TK-306 (condensate) — utility como stream real.
          · KNOCK-OUT DRUM V-202 post-condensador para separar gases
            co-destilados del producto metanol (vent gas → flare).
          · Residuos visibles: S-purge, S-vent, S-blowdown, S-water.
          · Layout con spacing 300 px ≥ 2× tamaño de bloque para que
            los streams se vean bien separados y no se solapen.
        """
        # ============ SECCIÓN 100 — REACCIÓN ============
        # Coords: y=300, spacing 300 px ≥ 2× tamaño de bloque (≈100 default)
        # → streams largos y bien separados para lectura.
        tk_fresh = self._add_example_block("TK-101","Storage tank — cone roof",
                                              500.0,   60, 300)
        k101 = self._add_example_block("K-101","Compressor — centrifugal",
                                          1200.0,  360, 300)
        e101 = self._add_example_block("E-101","Heat exch. — air cooler",
                                          250.0,   660, 300)
        # Mixer (fresh + recycle de syngas)
        m101 = self._add_example_block("M-101","Mixer — static",
                                              5.0,  960, 300)
        # K-202 — compresor de RECYCLE (sube P de la corriente de
        # gases sin reaccionar después del flash hasta P de M-101).
        # Ubicado arriba del mixer, ruta de retorno por encima del
        # tren principal.
        k202 = self._add_example_block("K-202","Compressor — centrifugal",
                                          800.0,  960,  60)
        # Pre-heater (vapor LP)
        e102 = self._add_example_block("E-102","Heat exch. — floating head",
                                          180.0,  1260, 300)
        r101 = self._add_example_block("R-101","Reactor — jacketed non-agit.",
                                          35.0,   1560, 300)
        self.fs.blocks[r101].reactions = ["R005"]   # CO+2H2→CH3OH
        self.fs.blocks[r101].reactor_mode = "equilibrium"
        self.fs.blocks[r101].T_op_K = 525.0
        self.fs.blocks[r101].P_op_bar = 80.0
        # Post-reactor cooler (genera VAPOR HP en WHB)
        e103 = self._add_example_block("E-103","Heat exch. — kettle reboiler",
                                           95.0,  1860, 300)

        # ============ SECCIÓN 200 — SEPARACIÓN ============
        v201 = self._add_example_block("V-201","Vessel — vertical",
                                          50.0,   2160, 300)
        # Flash NRTL desactivado en este ejemplo: con recycle, la masa
        # circulante es ~10× fresh y NRTL no maneja super-críticos a
        # 80 bar.  V-201 actúa como drum estructural; locks en S-crude
        # y S-V201-vapor cierran el balance.
        # V-203 — splitter purge / recycle (arriba de V-201, en lugar
        # donde estaba el flare antes)
        v203 = self._add_example_block("V-203","Vessel — vertical",
                                          25.0,   2160,  60)
        self.fs.blocks[v203].splitter_active = True
        self.fs.blocks[v203].splitter_fractions = [0.0909, 0.9091]  # purge / recycle
        # Flare se corre a la derecha para dejar lugar a V-203
        tk_flare = self._add_example_block("TK-203","Storage tank — cone roof",
                                              100.0, 2460,  60)
        # Columna abajo de V-201
        t201 = self._add_example_block("T-201","Tower (column shell)",
                                          45.0,   2160, 720)
        self.fs.blocks[t201].column_active = True
        self.fs.blocks[t201].column_LK = "methanol"
        self.fs.blocks[t201].column_HK = "water"
        self.fs.blocks[t201].column_x_D_LK = 0.99
        self.fs.blocks[t201].column_x_B_LK = 0.005
        self.fs.blocks[t201].column_R_factor = 1.4
        # Condensador del tope
        e201 = self._add_example_block("E-201","Heat exch. — air cooler",
                                          200.0,  2460, 540)
        # Knock-out drum: separa gases co-destilados del MeOH líquido
        # (en planta real es un vessel vertical con demister)
        v202 = self._add_example_block("V-202","Vessel — vertical",
                                          25.0,   2760, 540)
        self.fs.blocks[v202].splitter_active = True
        self.fs.blocks[v202].splitter_fractions = [0.85, 0.15]
        # Producto metanol (líquido limpio post-KO)
        tk_meoh = self._add_example_block("TK-201","Storage tank — floating roof",
                                            800.0, 3060, 540)
        # Reboiler de la cola — tendrá 4 ports (proceso + steam side)
        e202 = self._add_example_block("E-202","Heat exch. — kettle reboiler",
                                           90.0,  2460, 900)
        # Producto agua (descarga)
        tk_h2o = self._add_example_block("TK-202","Storage tank — cone roof",
                                           300.0, 2760, 900)
        # Tanque de condensado (recupera el vapor que condensó en E-202;
        # en planta real se bombea de vuelta a TK-301 cerrando lazo BFW)
        tk_cond = self._add_example_block("TK-306","Storage tank — cone roof",
                                              400.0, 3060, 900)

        # ============ SECCIÓN 300 — SERVICIOS ============
        # Ciclo de vapor (y=1200, spacing 300 px)
        # TK-307 = make-up de agua tratada (compensa blowdown del loop)
        tk_makeup = self._add_example_block("TK-307","Storage tank — cone roof",
                                             100.0,  240,1440)
        tk_bfw = self._add_example_block("TK-301","Storage tank — cone roof",
                                            600.0,   60,1200)
        p301 = self._add_example_block("P-301","Pump — centrifugal",
                                          10.0,   360,1200)
        self.fs.blocks[p301].efficiency = 0.75
        boil = self._add_example_block("F-301","Fired heater — non-reformer",
                                          12000.0, 660,1200)
        v_steam = self._add_example_block("V-301","Vessel — horizontal",
                                              100.0, 960,1200)
        tk_blowdown = self._add_example_block("TK-302","Storage tank — cone roof",
                                                 100.0, 960,1440)
        # Header de vapor MP — alimenta a E-202 como utility (ciclo cerrado)
        tk_steam = self._add_example_block("TK-305","Storage tank — cone roof",
                                              200.0,1260,1200)

        # Cooling tower loop (y=1560)
        tk_cw = self._add_example_block("TK-303","Storage tank — cone roof",
                                            500.0,   60,1560)
        p302 = self._add_example_block("P-302","Pump — centrifugal",
                                          10.0,   360,1560)
        self.fs.blocks[p302].efficiency = 0.75
        tk_cwret = self._add_example_block("TK-304","Storage tank — cone roof",
                                              300.0, 660,1560)

        # ============ STREAMS — PROCESO PRINCIPAL ============
        # Feed fresh syngas
        # Syngas industrial real lleva ~5% vapor de agua (inyectado río
        # arriba para shift/WGS o como subproducto del reformado).  Se
        # comporta como inerte en R005 pero permite que T-201 separe
        # MeOH/H2O cuando el reactor alcanza equilibrio.
        self._add_example_stream(tk_fresh, k101, "S-fresh", 50000, role="feed",
                                  src_port="salida", dst_port="succion",
                                  price=180.0, T=25,
                                  composition={"co": 0.38, "hydrogen": 0.52,
                                                 "methane": 0.05,
                                                 "water": 0.05},
                                  phase="gas")
        # Post-compresor (T sube a 200°C, ΔP=80 bar)
        self._add_example_stream(k101, e101, "S-1", 0.0,
                                  src_port="descarga", dst_port="proceso_in",
                                  T=200, phase="gas")
        # Post-intercooler
        self._add_example_stream(e101, m101, "S-2", 0.0,
                                  src_port="proceso_out", dst_port="entrada1",
                                  T=40, phase="gas")
        # Mix → pre-heater
        self._add_example_stream(m101, e102, "S-3",
                                  src_port="salida", dst_port="tube_in",
                                  T=80, phase="gas")
        # Pre-heat → reactor
        self._add_example_stream(e102, r101, "S-4",
                                  src_port="tube_out", dst_port="alimentacion",
                                  T=200, phase="gas")
        # Reactor → WHB (waste heat boiler) — composición la calcula el solver
        self._add_example_stream(r101, e103, "S-5",
                                  src_port="producto", dst_port="liq_in",
                                  T=252, phase="vapor")
        # WHB → flash (enfriado)
        self._add_example_stream(e103, v201, "S-6",
                                  src_port="cond_out", dst_port="alimentacion",
                                  T=40, phase="two_phase")
        # V-201 → líquido crudo a columna.  Balance con recycle:
        #   M-101 in = 50000 fresh + 250000 recycle = 300000.
        #   V-201 in = 300000.  V-201 liquid (S-crude) = 25000.
        #   V-201 vapor (S-V201-vapor) = 275000 → V-203 splitter.
        self._add_example_stream(v201, t201, "S-crude", 25000,
                                  src_port="liquido", dst_port="alimentacion",
                                  T=40, phase="liquid")
        # V-201 vapor (gases sin reaccionar) → V-203 splitter
        self._add_example_stream(v201, v203, "S-V201-vapor", 0.0,
                                  src_port="vapor", dst_port="alimentacion",
                                  T=40, phase="gas")

        # Columna → tope → condensador
        self._add_example_stream(t201, e201, "S-vap",
                                  src_port="vapor_tope", dst_port="shell_in",
                                  T=65, phase="vapor")
        # Condensador → KO drum (masa heredada del FUG, ≈19000 kg/h
        # con gases co-destilados — el KO los separa)
        self._add_example_stream(e201, v202, "S-MeOH-mix",
                                  src_port="shell_out", dst_port="alimentacion",
                                  T=40, phase="liquid")
        # KO drum → tanque MeOH (líquido limpio, 85% del flujo)
        self._add_example_stream(v202, tk_meoh, "S-MeOH", role="product",
                                  src_port="liquido", dst_port="entrada",
                                  price=1100.0, T=40, phase="liquid",
                                  composition={"methanol": 0.98, "water": 0.02})
        # KO drum → flare (gases co-destilados, 15% del flujo)
        self._add_example_stream(v202, tk_flare, "S-vent", role="waste",
                                  src_port="vapor", dst_port="entrada",
                                  price=0.0, T=40, phase="gas",
                                  composition={"hydrogen": 0.55, "methane": 0.20,
                                                 "co": 0.15, "methanol": 0.10})
        # Columna → cola → reboiler (proceso side)
        self._add_example_stream(t201, e202, "S-bot",
                                  src_port="liquido_fondo", dst_port="liq_in",
                                  T=100, phase="liquid")
        # Reboiler proceso-side → tanque water (masa heredada del FUG,
        # ≈950 kg/h del bottom de T-201, mayormente water)
        self._add_example_stream(e202, tk_h2o, "S-water", role="waste",
                                  src_port="cond_out", dst_port="entrada",
                                  price=0.0, T=40, phase="liquid")

        # ── RECYCLE DE SYNGAS ────────────────────────────────
        # V-203 splitter: 9.1% al flare como purga (limita acumulación
        # de CH4 inerte), 90.9% se recicla.  Ratio recycle/fresh = 5×
        # — típico de plantas MeOH industriales (5-10×).
        # Orden de creación = orden de splitter_fractions [purge, recycle].
        self._add_example_stream(v203, tk_flare, "S-purge", 25000, role="waste",
                                  src_port="vapor", dst_port="entrada",
                                  price=0.0, T=40, phase="gas")
        # V-203 → K-202 (recycle frío, baja P por ΔP del flash)
        self._add_example_stream(v203, k202, "S-rec-cold", 0.0,
                                  src_port="liquido", dst_port="succion",
                                  T=40, phase="gas")
        # K-202 → M-101 (recycle comprimido, segunda entrada del mixer)
        self._add_example_stream(k202, m101, "S-recycle", 250000,
                                  src_port="descarga", dst_port="entrada2",
                                  T=80, phase="gas")

        # ============ STREAMS — SERVICIOS ============
        # Boiler feed water — recirculación interna (no costo Raw Material;
        # el make-up externo viene de S-BFW-makeup desde TK-307).
        self._add_example_stream(tk_bfw, p301, "S-BFW-feed", 0.0,
                                  role="utility",
                                  src_port="salida", dst_port="succion",
                                  price=1.5, T=25,
                                  composition={"water": 1.0}, phase="liquid")
        # BFW pumped to boiler
        self._add_example_stream(p301, boil, "S-BFW",
                                  src_port="descarga", dst_port="alimentacion",
                                  T=30, phase="liquid",
                                  composition={"water": 1.0})
        # Boiler → drum vapor
        self._add_example_stream(boil, v_steam, "S-steam-raw",
                                  src_port="salida", dst_port="alimentacion",
                                  T=250, phase="two_phase",
                                  composition={"water": 1.0})
        # Drum → blowdown (purga sólidos disueltos, ~2% del feed)
        self._add_example_stream(v_steam, tk_blowdown, "S-blowdown", 1500,
                                  role="waste",
                                  src_port="liquido_fondo", dst_port="entrada",
                                  price=0.0, T=100, phase="liquid",
                                  composition={"water": 1.0})
        # Drum → header MP (cierra V-301: 80000 = 1500 + 78500)
        self._add_example_stream(v_steam, tk_steam, "S-MP-steam", 0.0,
                                  role="utility",
                                  src_port="vapor", dst_port="entrada",
                                  price=18.0, T=250, phase="vapor",
                                  composition={"water": 1.0})
        # ── CICLO DE VAPOR CERRADO ────────────────────────────
        # Header MP → reboiler E-202 (utility, shell-side del kettle)
        self._add_example_stream(tk_steam, e202, "S-MP-supply", 78500,
                                  role="utility",
                                  src_port="salida", dst_port="steam_in",
                                  price=0.0, T=250, phase="vapor",
                                  composition={"water": 1.0})
        # Reboiler shell-side → tanque de condensado (intermedio
        # antes de retornar a TK-301 BFW — cierra el ciclo de vapor)
        self._add_example_stream(e202, tk_cond, "S-cond", 78500,
                                  role="utility",
                                  src_port="steam_out", dst_port="entrada",
                                  price=0.0, T=140, phase="liquid",
                                  composition={"water": 1.0})
        # ── CIERRE DEL CICLO DE VAPOR: condensate → BFW ──────
        # TK-301 balance: in = makeup (1500) + cond-return (78500) =
        #                  out = S-BFW-feed (80000) ✓
        # Solo el 1.9 % del agua del loop es makeup; el resto circula.
        self._add_example_stream(tk_cond, tk_bfw, "S-cond-return", 0.0,
                                  role="utility",
                                  src_port="salida", dst_port="entrada",
                                  price=0.0, T=140, phase="liquid",
                                  composition={"water": 1.0})
        # Make-up: agua tratada fresca para reponer las pérdidas por
        # blowdown del drum V-301 (1500 tm/yr).
        self._add_example_stream(tk_makeup, tk_bfw, "S-BFW-makeup", 1500,
                                  role="feed",
                                  src_port="salida", dst_port="entrada",
                                  price=2.0, T=25, phase="liquid",
                                  composition={"water": 1.0})

        # ── COOLING WATER LOOP (cerrado) ─────────────────────
        # TK-303 (basin) → P-302 → distribución a HX → TK-304
        # (return) → TK-303 con make-up por evap/blowdown.
        # CW basin → bomba — recirculación interna (loop cerrado por
        # torre de enfriamiento; no costo Raw Material).
        self._add_example_stream(tk_cw, p302, "S-CW-feed", 0.0,
                                  role="utility",
                                  src_port="salida", dst_port="succion",
                                  price=0.0, T=25,
                                  composition={"water": 1.0}, phase="liquid")
        # CW pumped → distribuye a HX (loop INTERNO sin tocar el
        # proceso — evita contaminar composición de S-2 vía solver
        # auto-propagation).  TK-303 → P-302 → TK-304 → TK-303.
        # El costo de CW para los coolers (E-101, E-201, E-301) lo
        # auto-calcula compute_utilities_from_duties desde block.duty.
        self._add_example_stream(p302, tk_cwret, "S-CW-supply", 0.0,
                                  role="utility",
                                  src_port="descarga", dst_port="entrada",
                                  T=30, phase="liquid",
                                  composition={"water": 1.0})
        # TK-304 → TK-303 cierra el loop (torre de enfriamiento implícita)
        self._add_example_stream(tk_cwret, tk_cw, "S-CW-cooled", 200000,
                                  role="utility",
                                  src_port="salida", dst_port="entrada",
                                  price=0.0, T=27, phase="liquid",
                                  composition={"water": 1.0})

        # ============ DUTIES INFERIDOS ============
        from flowsheet_solver import auto_set_duties_from_thermo
        auto_set_duties_from_thermo(self.fs)

        # ============ OPEX EXTRAS ============
        self._add_example_extra("Catalizador Cu/ZnO/Al2O3 (MeOH)",
                                 flowrate=5, price=22000.0,
                                 stream="Consumables")
        self._add_example_extra("Reposición de catalizador shift",
                                 flowrate=2, price=12000.0,
                                 stream="Consumables")
        self._add_example_extra("Make-up BFW chemicals",
                                 flowrate=200, price=80.0,
                                 stream="Utilities")
        self._add_example_extra("Tratamiento agua refrigeración",
                                 flowrate=50, price=200.0,
                                 stream="Utilities")
        self._add_example_extra("Fuel gas (combustible boiler)",
                                 flowrate=1500, price=150.0,
                                 stream="Utilities")

    def _example_quimpac_chloralkali(self):
        """QUIMPAC — Planta cloro-álcali estilo Oquendo/Paramonga (Perú).

        Electrólisis de sal en celda de membrana.  Producción de soda
        cáustica, cloro líquido e hidrógeno por electrólisis de NaCl(aq).

        Reacciones (placeholder R_CELDA en el block — la chemistry real
        del electrolizador no está en el DB de reacciones de Capa 4;
        se modela con outlets locked siguiendo estequiometría real):
            2 NaCl + 2 H2O  →  2 NaOH + Cl2 + H2

        Tres trenes paralelos post-celda:
          · Tren Cl2:  cooler → secador H2SO4 → compresor → condenser
            → Cl2 líquido (700 kPa, 20 °C).
          · Tren H2:   cooler → tanque H2 (a venta o quema).
          · Tren NaOH: evaporador 32% → 50% (vapor de agua a venteo).

        Recycle obligatorio de salmuera agotada (anolito sale a 17-21%
        NaCl, vuelve al saturador).  Ratio 5× fresh (basis 1000 tm/año
        NaCl fresco — small pilot, escalable linealmente).

        Reactivos auxiliares: NaOH+Na2CO3 (purificación de Ca/Mg),
        HCl (acidificación pH≈2.7), H2SO4 98% (secado de Cl2 húmedo).

        Basis: 1000 tm/año NaCl fresco (≈ 114 kg/h).  Layout 1.8×.

        ⚠ PILOT SCALE — NPV negativo esperado.  A 1000 tm/año NaCl
        la planta produce ~600 tm Cl₂ + ~2000 tm NaOH 50%, revenue
        ~$1.7M/año.  El FCI + COL absorben más que eso.  Para
        análisis de planta industrial real (Oquendo procesa miles
        de t/año), escalar caudales ×50-100 y re-correr.
        """
        # ============ FEEDS Y SATURADOR ============
        tk_sal   = self._add_example_block("TK-101","Storage tank — cone roof",
                                              500.0,   60, 360)
        tk_h2o   = self._add_example_block("TK-102","Storage tank — cone roof",
                                              500.0,   60, 660)
        # Reactivos de purificación (NaOH + Na2CO3)
        tk_reac  = self._add_example_block("TK-103","Storage tank — cone roof",
                                             100.0,    60, 960)
        # Saturador / mezclador: sal + agua + recycle
        m101     = self._add_example_block("M-101","Mixer — static",
                                                5.0,  360, 480)

        # ============ PURIFICACIÓN ============
        # R-101: Mg(2+) + 2 OH- → Mg(OH)2 ↓ ; Ca(2+) + CO3(2-) → CaCO3 ↓
        # Modelado como reactor con outputs locked (no R en DB,
        # placeholder R_PURIF para marcar como rxn block).
        r101     = self._add_example_block("R-101","Reactor — jacketed agitated",
                                              30.0,  660, 480)
        self.fs.blocks[r101].reactions = ["R_PURIF"]
        # Decantador: separa lodos de Mg(OH)2 + CaCO3
        v101     = self._add_example_block("V-101","Vessel — vertical",
                                              50.0,  960, 480)
        self.fs.blocks[v101].splitter_active = True
        self.fs.blocks[v101].splitter_fractions = [0.002, 0.998]  # lodos / clear
        # Lodos (residuo sólido)
        tk_lodos = self._add_example_block("TK-104","Storage tank — cone roof",
                                             100.0,  960, 720)
        # Intercambio iónico (pulido final Ca/Mg a ppb) — pass-through
        ix101    = self._add_example_block("IX-101","Filter — belt",
                                              30.0, 1260, 480)
        # Acidificación con HCl (pH ≈ 2.7 antes de celda)
        tk_hcl   = self._add_example_block("TK-105","Storage tank — cone roof",
                                             100.0, 1260, 240)
        m102     = self._add_example_block("M-102","Mixer — static",
                                                5.0, 1560, 480)

        # ============ CELDA DE ELECTRÓLISIS ============
        # R-201: 2 NaCl + 2 H2O → 2 NaOH + Cl2 + H2  (35% conv/pase,
        # 100% steady-state con recycle).  Cuatro salidas:
        #   - Anolito agotado (recycle a saturador)
        #   - Cl2 húmedo
        #   - H2 húmedo
        #   - NaOH 32% solución
        # S=14 m³ por celda (planta real tiene ~50 celdas en paralelo)
        r201     = self._add_example_block("R-201","Reactor — autoclave",
                                              14.0, 1860, 480)
        self.fs.blocks[r201].reactions = ["R_CELDA_CLORALCALI"]
        self.fs.blocks[r201].T_op_K = 358.15   # 85°C
        self.fs.blocks[r201].P_op_bar = 1.5

        # ============ TREN DE CL2 ============
        e301     = self._add_example_block("E-301","Heat exch. — air cooler",
                                              80.0, 2160, 180)
        # Secador con H2SO4 98% (tower estructural)
        tk_h2so4 = self._add_example_block("TK-106","Storage tank — cone roof",
                                             100.0, 2160,   0)
        abs301   = self._add_example_block("T-301","Tower (column shell)",
                                              30.0, 2460, 180)
        k301     = self._add_example_block("K-301","Compressor — centrifugal",
                                             500.0, 2760, 180)
        self.fs.blocks[k301].efficiency = 0.70   # auto-size a 7 bar (Cl2 licuef.)
        e302     = self._add_example_block("E-302","Heat exch. — floating head",
                                             120.0, 3060, 180)
        tk_cl2   = self._add_example_block("TK-201","Storage tank — floating roof",
                                             600.0, 3360, 180)
        # H2SO4 spent (residuo, baja a tanque debajo del secador)
        tk_acid_spent = self._add_example_block("TK-107","Storage tank — cone roof",
                                             100.0, 2460,   0)

        # ============ TREN DE H2 ============
        e401     = self._add_example_block("E-401","Heat exch. — air cooler",
                                              50.0, 2160, 480)
        tk_h2_prod = self._add_example_block("TK-202","Storage tank — cone roof",
                                             200.0, 2460, 480)

        # ============ TREN DE NAOH (evaporador 32% → 50%) ============
        e501     = self._add_example_block("E-501","Evaporator — vertical",
                                             400.0, 2160, 780)
        # Producto NaOH 50%
        tk_naoh  = self._add_example_block("TK-203","Storage tank — floating roof",
                                             800.0, 2460, 780)
        # Vapor de agua (waste — al sistema de condensado / atmosfera)
        tk_vapor = self._add_example_block("TK-108","Storage tank — cone roof",
                                             100.0, 2460,1020)

        # ============ STREAMS — PURIFICACIÓN ============
        # Sal fresca (sólido disuelto)
        self._add_example_stream(tk_sal, m101, "S-sal", 1000, role="feed",
                                  src_port="salida", dst_port="entrada1",
                                  price=80.0, T=25,
                                  composition={"sodium chloride": 1.0},
                                  phase="solid")
        # Agua fresca de saturador
        self._add_example_stream(tk_h2o, m101, "S-h2o", 3000, role="feed",
                                  src_port="salida", dst_port="entrada2",
                                  price=1.5, T=25,
                                  composition={"water": 1.0},
                                  phase="liquid")
        # Salmuera cruda al reactor de purificación
        self._add_example_stream(m101, r101, "S-cruda", 0.0,
                                  src_port="salida", dst_port="alimentacion",
                                  T=40, phase="liquid",
                                  composition={"sodium chloride": 0.20,
                                                 "water": 0.80})
        # Reactivos (NaOH + Na2CO3) para precipitar Mg, Ca
        self._add_example_stream(tk_reac, r101, "S-reactivos", 10, role="feed",
                                  src_port="salida", dst_port="aux_in",
                                  price=400.0, T=25,
                                  composition={"sodium hydroxide": 0.5,
                                                 "sodium carbonate": 0.5},
                                  phase="liquid")
        # Salida del reactor: salmuera con lodos en suspensión
        self._add_example_stream(r101, v101, "S-purif", 0.0,
                                  src_port="producto", dst_port="alimentacion",
                                  T=60, phase="liquid",
                                  composition={"sodium chloride": 0.205,
                                                 "water": 0.793,
                                                 "calcium carbonate": 0.0011,
                                                 "magnesium hydroxide": 0.001})
        # Decantador → lodos (waste sólido) + clear líquido
        self._add_example_stream(v101, tk_lodos, "S-lodos", 18, role="waste",
                                  src_port="liquido_fondo", dst_port="entrada",
                                  price=0.0, T=60, phase="liquid",
                                  composition={"calcium carbonate": 0.55,
                                                 "magnesium hydroxide": 0.45})
        self._add_example_stream(v101, ix101, "S-clear", 0.0,
                                  src_port="vapor", dst_port="alimentacion",
                                  T=60, phase="liquid",
                                  composition={"sodium chloride": 0.205,
                                                 "water": 0.795})
        # IX-101 pulido pass-through
        self._add_example_stream(ix101, m102, "S-ultrapur", 0.0,
                                  src_port="salida", dst_port="entrada1",
                                  T=60, phase="liquid",
                                  composition={"sodium chloride": 0.205,
                                                 "water": 0.795})
        # HCl para acidificación (pH 2.7)
        self._add_example_stream(tk_hcl, m102, "S-hcl", 8, role="feed",
                                  src_port="salida", dst_port="entrada2",
                                  price=120.0, T=25,
                                  composition={"hydrogen chloride": 1.0},
                                  phase="liquid")
        # Alimentación a celda
        self._add_example_stream(m102, r201, "S-cell-feed", 0.0,
                                  src_port="salida", dst_port="alimentacion",
                                  T=85, phase="liquid",
                                  composition={"sodium chloride": 0.205,
                                                 "water": 0.795})

        # ============ STREAMS — CELDA (4 outputs locked) ============
        # Anolito agotado (recycle) — NaCl 18%, vuelve a saturador
        self._add_example_stream(r201, m101, "S-anolito", 5000,
                                  src_port="liquido_fondo", dst_port="entrada3",
                                  T=85, phase="liquid",
                                  composition={"sodium chloride": 0.18,
                                                 "water": 0.82})
        # Cloro húmedo (con H2O saturada arrastrada)
        self._add_example_stream(r201, e301, "S-cl2-wet", 620,
                                  src_port="vapor", dst_port="proceso_in",
                                  T=85, phase="gas",
                                  composition={"chlorine": 0.97,
                                                 "water": 0.03})
        # Hidrógeno húmedo
        self._add_example_stream(r201, e401, "S-h2-wet", 28,
                                  src_port="aux_out", dst_port="proceso_in",
                                  T=85, phase="gas",
                                  composition={"hydrogen": 0.95,
                                                 "water": 0.05})
        # NaOH 32% solución
        self._add_example_stream(r201, e501, "S-naoh-32", 3352,
                                  src_port="liquido_tope", dst_port="proceso_in",
                                  T=85, phase="liquid",
                                  composition={"sodium hydroxide": 0.32,
                                                 "water": 0.68})

        # ============ STREAMS — TREN CL2 ============
        self._add_example_stream(e301, abs301, "S-cl2-cold", 0.0,
                                  src_port="proceso_out", dst_port="alimentacion",
                                  T=15, phase="gas",
                                  composition={"chlorine": 0.97,
                                                 "water": 0.03})
        # H2SO4 fresh al secador
        self._add_example_stream(tk_h2so4, abs301, "S-h2so4", 25, role="feed",
                                  src_port="salida", dst_port="reflujo",
                                  price=200.0, T=25,
                                  composition={"sulfuric acid": 0.98,
                                                 "water": 0.02},
                                  phase="liquid")
        # H2SO4 spent (drena con agua absorbida)
        self._add_example_stream(abs301, tk_acid_spent, "S-acid-spent", 43,
                                  role="waste",
                                  src_port="liquido_fondo", dst_port="entrada",
                                  price=0.0, T=15, phase="liquid",
                                  composition={"sulfuric acid": 0.55,
                                                 "water": 0.45})
        # Cl2 seco (>99% pureza, <50 ppm H2O)
        self._add_example_stream(abs301, k301, "S-cl2-dry", 0.0,
                                  src_port="vapor_tope", dst_port="succion",
                                  T=15, phase="gas",
                                  composition={"chlorine": 0.999,
                                                 "water": 0.001})
        # Compresión a 7 bar
        self._add_example_stream(k301, e302, "S-cl2-hp", 0.0,
                                  src_port="descarga", dst_port="tube_in",
                                  T=80, phase="gas",
                                  composition={"chlorine": 0.999,
                                                 "water": 0.001}, lock_T=False)
        # Condensación → Cl2 líquido (almacenado a 7 bar / 700 kPa).
        s_cl2liq = self._add_example_stream(e302, tk_cl2, "S-cl2-liq", 0.0, role="product",
                                  src_port="tube_out", dst_port="entrada",
                                  price=480.0, T=20, phase="liquid",
                                  composition={"chlorine": 0.999,
                                                 "water": 0.001})
        self.fs.streams[s_cl2liq].pressure_bar = 7.0
        self.fs.streams[s_cl2liq].pressure_locked = True

        # ============ STREAMS — TREN H2 ============
        self._add_example_stream(e401, tk_h2_prod, "S-h2", 0.0, role="product",
                                  src_port="proceso_out", dst_port="entrada",
                                  price=2500.0, T=25, phase="gas",
                                  composition={"hydrogen": 0.95,
                                                 "water": 0.05})

        # ============ STREAMS — TREN NaOH ============
        # NaOH 50% concentrado (producto comercial, mercado 2024)
        self._add_example_stream(e501, tk_naoh, "S-naoh-50", 0.0, role="product",
                                  src_port="liquido_fondo", dst_port="entrada",
                                  price=620.0, T=50, phase="liquid",
                                  composition={"sodium hydroxide": 0.50,
                                                 "water": 0.50})
        # Vapor de agua evaporado del concentrador NaOH.  En planta
        # real se condensa y recicla como agua del saturador (TK-102),
        # cerrando el balance hídrico.  Acá se marca como 'utility'
        # para no contarlo como waste cargable en el opex.
        # Para el modelo riguroso, agregar un condensador + retorno
        # a TK-102 (requiere rebalance del saturador).
        self._add_example_stream(e501, tk_vapor, "S-vapor-evap", 1207,
                                  role="utility",
                                  src_port="vapor_tope", dst_port="entrada",
                                  price=0.0, T=100, phase="vapor",
                                  composition={"water": 1.0})

        # ============ DUTIES INFERIDOS ============
        from flowsheet_solver import auto_set_duties_from_thermo
        auto_set_duties_from_thermo(self.fs)
        # Energía eléctrica de la celda: ~2500 kWh/t Cl2 × 0.602 t/h
        # = 1505 kW.  Reactor R-201 duty manual (no lo computa Capa 4
        # porque la rxn está fuera del DB).
        self.fs.blocks[r201].duty = 1505.0
        self.fs.blocks[r201].duty_locked = True

        # ============ OPEX EXTRAS ============
        self._add_example_extra("Membrana celda electrolítica (reposición)",
                                 flowrate=3, price=18000.0,
                                 stream="Consumables")
        self._add_example_extra("Energía eléctrica celda (kWh/t Cl2)",
                                 flowrate=12000, price=0.08,
                                 stream="Utilities")
        self._add_example_extra("Anodos DSA (reposición)",
                                 flowrate=1, price=25000.0,
                                 stream="Consumables")
        # Labor override: fórmula Turton sqrt(P²) con P=2 (filter
        # IX-101 + decantador V-101) da 53 operadores, irreal para
        # pilot scale 1000 tm/yr.  Override manual a 8 operadores ×
        # salario del perfil ≈ $200k/yr.
        self._set_example_labor(200_000)

    def _example_hno3_ostwald(self):
        """HNO3 — Proceso Ostwald dual-presión (estilo DuPont 1920s).

        Producción de ácido nítrico al 60% por oxidación catalítica de
        amoníaco.  Tres etapas químicas en serie + recuperación
        intensiva de calor + turbina de gas de cola.

        Reacciones (placeholders — chemistry vía outputs locked):
          1. 4 NH3 + 5 O2  → 4 NO + 6 H2O   (combustión Pt-Rh, 900°C)
          2. 2 NO  + O2    → 2 NO2          (oxidación gas, 40°C, 11 bar)
          3. 3 NO2 + H2O   → 2 HNO3 + NO    (absorción columna)

        Configuración dual-presión:
          · Combustión a 4.5 bar (más segura, menos parásitas)
          · Absorción a 11 bar (favorece reacción 3 NO2 + H2O)
          · Compresor NOx entre ambas etapas
          · Turbina de cola recupera energía del gas a baja P

        Basis: 1000 tm/año NH3 → ~6200 tm/año HNO3 60% (~3700 tm/año HNO3 puro).

        ⚠ PILOT SCALE — NPV negativo esperado.  El FCI fijo y el
        Labor mínimo no se amortizan a 6200 tm/año.  Para análisis
        de planta real (escala 80-300 kt/año), escalar todos los
        caudales 15-50× y re-correr Análisis económico.  FCI escala
        con S^0.6 (no linealmente) → ratio rev/CAPEX mejora ~2-3×.

        Layout 1.8× spacing.  Acceso: menú Examples → ⚗️ HNO3 Ostwald.
        """
        # ============ SECCIÓN 100 — ALIMENTACIÓN ============
        # NH3 líquido (12 bar, 25 °C)
        tk_nh3   = self._add_example_block("TK-101","Storage tank — cone roof",
                                              500.0,   60, 300)
        # Vaporizador NH3 (líq → vapor sobrecalentado)
        e101     = self._add_example_block("E-101","Heat exch. — floating head",
                                             200.0,  360, 300)
        # Fuente aire (atmósfera, fila inferior)
        tk_aire  = self._add_example_block("TK-102","Storage tank — cone roof",
                                            2000.0,   60, 600)
        # Compresor aire 1 → 4.8 bar
        k101     = self._add_example_block("K-101","Compressor — centrifugal",
                                            1500.0,  360, 600)
        # Mezclador NH3 + aire (10% NH3 molar)
        m101     = self._add_example_block("M-101","Mixer — static",
                                                5.0,  660, 450)

        # ============ SECCIÓN 200 — COMBUSTIÓN + RECUP CALOR ============
        # Reactor combustión catalítica (Pt-Rh malla, adiabático).
        # S=14 m³ — un quemador típico industrial es mayor; usamos el
        # max del rango de correlación de costos.
        r201     = self._add_example_block("R-201","Reactor — autoclave",
                                               14.0, 960, 450)
        self.fs.blocks[r201].reactions = ["R_OSTWALD_BURN"]
        self.fs.blocks[r201].T_op_K = 1173.15   # 900 °C
        self.fs.blocks[r201].P_op_bar = 4.5
        # WHB (waste heat boiler) — genera vapor AP.  S=95 m² (uno de
        # varios bancos paralelos en planta industrial real).
        e201     = self._add_example_block("E-201","Heat exch. — kettle reboiler",
                                               95.0, 1260, 450)
        # Economizador (gas 400 → 200 °C, calienta otra corriente)
        e202     = self._add_example_block("E-202","Heat exch. — fixed tube",
                                              300.0, 1560, 450)
        # Enfriador-condensador (200 → 50 °C, condensa H2O + HNO3 débil)
        e203     = self._add_example_block("E-203","Heat exch. — air cooler",
                                              250.0, 1860, 450)
        # Separador líquido/gas
        v201     = self._add_example_block("V-201","Vessel — vertical",
                                              60.0,  2160, 450)
        self.fs.blocks[v201].splitter_active = True
        self.fs.blocks[v201].splitter_fractions = [0.053, 0.947]  # cond / gas

        # ============ SECCIÓN 300 — COMPRESIÓN + OXIDACIÓN NOx ============
        # K-301 — compresor NOx (4 → 11 bar)
        k301     = self._add_example_block("K-301","Compressor — centrifugal",
                                            1200.0, 2160, 180)
        # R-301 — cámara de oxidación (NO + O2 → NO2)
        r301     = self._add_example_block("R-301","Reactor — jacketed non-agit.",
                                              30.0,  2460, 180)
        self.fs.blocks[r301].reactions = ["R_OXIDATION_NO"]
        self.fs.blocks[r301].T_op_K = 313.15   # 40 °C
        self.fs.blocks[r301].P_op_bar = 10.8

        # ============ SECCIÓN 400 — ABSORCIÓN ============
        # Agua desmin (tope columna)
        tk_h2o   = self._add_example_block("TK-103","Storage tank — cone roof",
                                            500.0,  2460, 540)
        # Aire bleaching secundario (re-oxida NO liberado en columna)
        tk_bleach = self._add_example_block("TK-104","Storage tank — cone roof",
                                            500.0,  2460, 750)
        # Columna de absorción reactiva
        t401     = self._add_example_block("T-401","Tower (column shell)",
                                              60.0, 2760, 540)
        self.fs.blocks[t401].reactions = ["R_ABSORB_NO2"]
        self.fs.blocks[t401].T_op_K = 308.15   # 35 °C, plate cooled
        self.fs.blocks[t401].P_op_bar = 11.0

        # ============ SECCIÓN 500 — PRODUCTO + TAIL GAS ============
        # Bleacher (strip de NOx disuelto del HNO3)
        v501     = self._add_example_block("V-501","Vessel — vertical",
                                              40.0, 3060, 720)
        self.fs.blocks[v501].splitter_active = True
        self.fs.blocks[v501].splitter_fractions = [0.984, 0.016]  # producto / vent
        # Producto HNO3 60%
        tk_hno3  = self._add_example_block("TK-201","Storage tank — floating roof",
                                            800.0, 3360, 720)
        # Vent del bleacher (NOx stripped, va a chimenea via expander)
        tk_vent  = self._add_example_block("TK-105","Storage tank — cone roof",
                                             100.0, 3060, 960)

        # Precalentador tail gas (calienta gas de cola con calor residual)
        e501     = self._add_example_block("E-501","Heat exch. — fixed tube",
                                             150.0, 3060, 360)
        # Turbina de expansión (recupera energía, 10 → 1 bar)
        t501     = self._add_example_block("K-501","Compressor — axial",
                                            1000.0, 3360, 360)
        # Chimenea (post-DeNOx, atmósfera)
        tk_stack = self._add_example_block("TK-301","Storage tank — cone roof",
                                             100.0, 3660, 360)

        # ============ STREAMS — ALIMENTACIÓN ============
        # NH3 líquido (12 bar, 25 °C)
        self._add_example_stream(tk_nh3, e101, "A1-NH3-liq", 1000, role="feed",
                                  src_port="salida", dst_port="tube_in",
                                  price=420.0, T=25,
                                  composition={"ammonia": 1.0},
                                  phase="liquid")
        # NH3 vapor sobrecalentado a mixer
        self._add_example_stream(e101, m101, "A2-NH3-vap", 0.0,
                                  src_port="tube_out", dst_port="entrada1",
                                  T=120, phase="gas",
                                  composition={"ammonia": 1.0})
        # Aire filtrado (gratis, atmósfera)
        self._add_example_stream(tk_aire, k101, "A3-aire", 14000, role="feed",
                                  src_port="salida", dst_port="succion",
                                  price=0.0, T=25,
                                  composition={"oxygen": 0.232,
                                                 "nitrogen": 0.768},
                                  phase="gas")
        # Aire comprimido
        self._add_example_stream(k101, m101, "A4-aire-hp", 0.0,
                                  src_port="descarga", dst_port="entrada2",
                                  T=200, phase="gas",
                                  composition={"oxygen": 0.232,
                                                 "nitrogen": 0.768}, lock_T=False)
        # Mezcla al reactor (10% NH3 molar ≈ 6.7% peso, dentro de
        # límites de inflamabilidad)
        self._add_example_stream(m101, r201, "A5-mix", 0.0,
                                  src_port="salida", dst_port="alimentacion",
                                  T=230, phase="gas",
                                  composition={"ammonia": 0.0667,
                                                 "oxygen": 0.217,
                                                 "nitrogen": 0.717})

        # ============ STREAMS — COMBUSTIÓN + RECUP ============
        # Gas post-quemador (NO, H2O, N2 inerte, O2 exceso, trazas N2O)
        self._add_example_stream(r201, e201, "A6-gas-hot", 0.0,
                                  src_port="producto", dst_port="liq_in",
                                  T=900, phase="gas",
                                  composition={"nitric oxide": 0.112,
                                                 "water": 0.106,
                                                 "nitrogen": 0.719,
                                                 "oxygen": 0.062,
                                                 "nitrous oxide": 0.001})
        # Gas tras WHB (900 → 400 °C, vapor recuperado en duty E-201)
        self._add_example_stream(e201, e202, "A7-gas-whb", 0.0,
                                  src_port="cond_out", dst_port="tube_in",
                                  T=400, phase="gas",
                                  composition={"nitric oxide": 0.112,
                                                 "water": 0.106,
                                                 "nitrogen": 0.719,
                                                 "oxygen": 0.062,
                                                 "nitrous oxide": 0.001})
        # Gas tras economizador (400 → 200 °C)
        self._add_example_stream(e202, e203, "A7b-gas-eco", 0.0,
                                  src_port="tube_out", dst_port="proceso_in",
                                  T=200, phase="gas",
                                  composition={"nitric oxide": 0.112,
                                                 "water": 0.106,
                                                 "nitrogen": 0.719,
                                                 "oxygen": 0.062,
                                                 "nitrous oxide": 0.001})
        # Gas tras enfriador (200 → 50 °C, parcialmente condensado)
        self._add_example_stream(e203, v201, "A8-gas-cool", 0.0,
                                  src_port="proceso_out", dst_port="alimentacion",
                                  T=50, phase="two_phase",
                                  composition={"nitric oxide": 0.080,
                                                 "nitrogen dioxide": 0.032,
                                                 "water": 0.106,
                                                 "nitrogen": 0.719,
                                                 "oxygen": 0.062,
                                                 "nitrous oxide": 0.001})
        # Separador → condensado ácido débil (HNO3 25-40%)
        self._add_example_stream(v201, t401, "A9-cond-debil", 795, role="internal",
                                  src_port="liquido_fondo", dst_port="alimentacion",
                                  T=50, phase="liquid",
                                  composition={"nitric acid": 0.32,
                                                 "water": 0.68})
        # Separador → gas NOx (al compresor)
        self._add_example_stream(v201, k301, "A9b-gas-NOx", 0.0,
                                  src_port="vapor", dst_port="succion",
                                  T=50, phase="gas",
                                  composition={"nitric oxide": 0.085,
                                                 "nitrogen dioxide": 0.034,
                                                 "water": 0.054,
                                                 "nitrogen": 0.760,
                                                 "oxygen": 0.066,
                                                 "nitrous oxide": 0.001})

        # ============ STREAMS — COMPRESIÓN + OXIDACIÓN ============
        # Gas comprimido a 11 bar
        self._add_example_stream(k301, r301, "A10-NOx-hp", 0.0,
                                  src_port="descarga", dst_port="alimentacion",
                                  T=120, phase="gas",
                                  composition={"nitric oxide": 0.085,
                                                 "nitrogen dioxide": 0.034,
                                                 "water": 0.054,
                                                 "nitrogen": 0.760,
                                                 "oxygen": 0.066,
                                                 "nitrous oxide": 0.001}, lock_T=False)
        # Gas oxidado (NO → NO2, 90% conv)
        self._add_example_stream(r301, t401, "A11-NOx-ox", 0.0,
                                  src_port="producto", dst_port="vapor_tope",
                                  T=40, phase="gas",
                                  composition={"nitric oxide": 0.009,
                                                 "nitrogen dioxide": 0.150,
                                                 "water": 0.054,
                                                 "nitrogen": 0.760,
                                                 "oxygen": 0.026,
                                                 "nitrous oxide": 0.001})

        # ============ STREAMS — ABSORCIÓN ============
        # Agua desmin al tope de columna
        self._add_example_stream(tk_h2o, t401, "A12-agua", 3000, role="feed",
                                  src_port="salida", dst_port="reflujo",
                                  price=1.5, T=30,
                                  composition={"water": 1.0},
                                  phase="liquid")
        # Aire bleaching (re-oxida NO en columna)
        self._add_example_stream(tk_bleach, t401, "A12b-bleach-air", 500,
                                  role="feed",
                                  src_port="salida", dst_port="aux_in",
                                  price=0.0, T=30,
                                  composition={"oxygen": 0.232,
                                                 "nitrogen": 0.768},
                                  phase="gas")
        # Fondo: HNO3 60% con NOx disuelto, al bleacher
        self._add_example_stream(t401, v501, "A13-HNO3-crudo", 6200,
                                  src_port="liquido_fondo", dst_port="alimentacion",
                                  T=60, phase="liquid",
                                  composition={"nitric acid": 0.60,
                                                 "water": 0.39,
                                                 "nitrogen dioxide": 0.01})
        # Tope: gas de cola (N2 mayor, O2, NOx residual <200 ppm)
        self._add_example_stream(t401, e501, "A14-tail-gas", 0.0,
                                  src_port="vapor_tope", dst_port="tube_in",
                                  T=25, phase="gas",
                                  composition={"nitrogen": 0.880,
                                                 "oxygen": 0.090,
                                                 "water": 0.029,
                                                 "nitric oxide": 0.0008,
                                                 "nitrogen dioxide": 0.0002})

        # ============ STREAMS — PRODUCTO + TAIL ============
        # Bleacher: HNO3 limpio (producto) + vent con NOx stripped
        self._add_example_stream(v501, tk_hno3, "A13b-HNO3-60", 0.0,
                                  role="product",
                                  src_port="liquido_fondo", dst_port="entrada",
                                  price=450.0, T=60, phase="liquid",
                                  composition={"nitric acid": 0.60,
                                                 "water": 0.40})
        self._add_example_stream(v501, tk_vent, "A13c-bleach-vent", 100,
                                  role="waste",
                                  src_port="vapor", dst_port="entrada",
                                  price=0.0, T=60, phase="gas",
                                  composition={"nitrogen dioxide": 0.60,
                                                 "water": 0.40})
        # Tail gas precalentado → expander → chimenea
        self._add_example_stream(e501, t501, "A14b-tail-hot", 0.0,
                                  src_port="tube_out", dst_port="succion",
                                  T=200, phase="gas",
                                  composition={"nitrogen": 0.880,
                                                 "oxygen": 0.090,
                                                 "water": 0.029,
                                                 "nitric oxide": 0.0008,
                                                 "nitrogen dioxide": 0.0002})
        self._add_example_stream(t501, tk_stack, "A15-stack", 0.0,
                                  role="waste",
                                  src_port="descarga", dst_port="entrada",
                                  price=0.0, T=-10, phase="gas",
                                  composition={"nitrogen": 0.880,
                                                 "oxygen": 0.090,
                                                 "water": 0.029,
                                                 "nitric oxide": 0.0008,
                                                 "nitrogen dioxide": 0.0002})

        # ============ DUTIES INFERIDOS ============
        from flowsheet_solver import auto_set_duties_from_thermo
        auto_set_duties_from_thermo(self.fs)
        # Reactor combustión: adiabático, libera ~226 kJ/mol NH3 ×
        # 58.8 kmol/h = 13290 MJ/h = 3692 kW.  Como adiabático,
        # ese calor calienta el gas (de 230 a 900 °C en una etapa).
        # No le seteamos duty; el reactor lo absorbe internamente.
        # K-501 (turbina expansión) consume W negativo (genera).
        self.fs.blocks[t501].duty = -700.0
        self.fs.blocks[t501].duty_locked = True
        self.fs.blocks[t501].delta_p_bar = -9.5   # turbina de expansión 10→0.5 bar
        self.fs.blocks[t501].duty_locked = True

        # ============ OPEX EXTRAS ============
        self._add_example_extra("Catalizador Pt-Rh (gauze, reposición)",
                                 flowrate=25, price=85000.0,
                                 stream="Consumables")
        self._add_example_extra("Agua desmineralizada (utility)",
                                 flowrate=24000, price=2.5,
                                 stream="Utilities")
        self._add_example_extra("Vapor AP recuperado (crédito WHB)",
                                 flowrate=4000, price=-25.0,  # negativo = ingreso
                                 stream="Utilities")

    def _example_talara_refinery(self):
        """Nueva Refinería Talara (PMRT — Petroperú) — esquema integrado.

        95 000 BPD de crudo pesado de selva (≈ 500 000 kg/h), conversión
        profunda, primera refinería de LatAm con Flexicoking.  Acceso:
        menú Examples → 🏭 REFINERÍA TALARA.

        Representación de las 16 unidades de proceso vía 28 bloques:
          · DESAL → DP1 (atm) → DV3 (vacío)
          · FCC + FCK Flexicoking (conversión profunda)
          · HTN + HTD + HTF (hidrotratamientos con H2 de planta SMR)
          · RCA reformación catalítica (gasolina 97 + H2 subproducto)
          · Planta H2 (SMR) auxiliar

        Reactores con placeholders (chemistry de refino fuera de DB):
          R_DESAL, R_FCC, R_FCK, R_HDS, R_REFORM, R_SMR
        Las columnas DP1/DV3 modeladas como splitters con fracciones
        típicas de cortes (TBP empírica).

        Caudales orientativos (basis 500 000 tm/año crudo ≈ 57 t/h).
        """
        # ============ ALIMENTACIÓN ============
        tk_crudo = self._add_example_block("TK-101","Storage tank — floating roof",
                                            1200.0,   60, 480)
        tk_agua  = self._add_example_block("TK-102","Storage tank — cone roof",
                                             500.0,   60, 720)
        m101     = self._add_example_block("M-101","Mixer — static",
                                                5.0,  360, 600)
        # Desaladora electrostática
        v101     = self._add_example_block("V-101","Vessel — horizontal",
                                              80.0,  660, 600)
        self.fs.blocks[v101].splitter_active = True
        self.fs.blocks[v101].splitter_fractions = [0.952, 0.048]  # crude / brine
        # Horno de carga DP1
        f101     = self._add_example_block("F-101","Fired heater — non-reformer",
                                          15000.0,  960, 480)
        # Brine descarga (residuo desalado)
        tk_brine = self._add_example_block("TK-103","Storage tank — cone roof",
                                             100.0,  660, 840)

        # ============ DESTILACIÓN PRIMARIA (DP1) ============
        # Columna atmosférica, modelada como splitter de 6 cortes
        t101     = self._add_example_block("T-101","Tower (column shell)",
                                             150.0, 1260, 480)
        self.fs.blocks[t101].splitter_active = True
        # Cortes típicos de crudo medio-pesado: gas, nafta, kero, diésel,
        # gasóleo atm, residuo atm
        self.fs.blocks[t101].splitter_fractions = [0.02, 0.18, 0.13,
                                                     0.22, 0.08, 0.37]
        # Tanques de cortes inmediatos (algunos van a downstream, otros directo)
        tk_fuel_gas = self._add_example_block("TK-201","Storage tank — cone roof",
                                              150.0, 1260, 120)
        tk_turbo = self._add_example_block("TK-202","Storage tank — floating roof",
                                            600.0, 1860, 660)

        # ============ HIDROTRATAMIENTOS ============
        # HTN — Hidrotratamiento de Nafta (a RCA).  S=12 m³ por reactor;
        # en planta real son 2-3 en paralelo (S total ≈ 40 m³).
        r_htn    = self._add_example_block("R-HTN","Reactor — autoclave",
                                              12.0, 1560, 300)
        self.fs.blocks[r_htn].reactions = ["R_HDS"]
        self.fs.blocks[r_htn].T_op_K = 623.15
        self.fs.blocks[r_htn].P_op_bar = 50.0
        # HTD — Hidrotratamiento de Diésel (a ULSD <50 ppm S)
        r_htd    = self._add_example_block("R-HTD","Reactor — autoclave",
                                              14.0, 1560, 840)
        self.fs.blocks[r_htd].reactions = ["R_HDS"]
        self.fs.blocks[r_htd].T_op_K = 653.15
        self.fs.blocks[r_htd].P_op_bar = 80.0
        # HTF — Hidrotratamiento de Nafta FCC
        r_htf    = self._add_example_block("R-HTF","Reactor — autoclave",
                                              10.0, 2460, 540)
        self.fs.blocks[r_htf].reactions = ["R_HDS"]
        self.fs.blocks[r_htf].T_op_K = 593.15
        self.fs.blocks[r_htf].P_op_bar = 40.0

        # ============ RCA — REFORMACIÓN CATALÍTICA ============
        # Cascada de reactores: aquí modelado como uno solo (S=30 m³,
        # en planta real son 3-4 reactores en serie con T~530 °C).
        r_rca    = self._add_example_block("R-RCA","Reactor — jacketed agitated",
                                              30.0, 1860, 300)
        self.fs.blocks[r_rca].reactions = ["R_REFORM"]
        self.fs.blocks[r_rca].T_op_K = 793.15
        self.fs.blocks[r_rca].P_op_bar = 10.0
        # Tanque gasolina 97 octano (producto final reformado)
        tk_gaso97 = self._add_example_block("TK-203","Storage tank — floating roof",
                                            800.0, 2160, 300)
        # Tanque ULSD (diésel limpio)
        tk_ulsd  = self._add_example_block("TK-204","Storage tank — floating roof",
                                            800.0, 1860, 840)

        # ============ DESTILACIÓN AL VACÍO (DV3) ============
        # Procesa el residuo atmosférico (~37% del crudo)
        t201     = self._add_example_block("T-201","Tower (column shell)",
                                             100.0, 1560,1080)
        self.fs.blocks[t201].splitter_active = True
        # LVGO+HVGO (45%) / residuo vacío (55%)
        self.fs.blocks[t201].splitter_fractions = [0.55, 0.45]

        # ============ FCC — CRAQUEO CATALÍTICO ============
        # 6 productos: gasolina FCC, LCO, GLP, gas seco, slurry, coque
        # S=15 m³ nominal (un FCC industrial real es ~80 m³ pero usamos
        # el max del rango de correlación de costos)
        r_fcc    = self._add_example_block("R-FCC","Reactor — autoclave",
                                              15.0, 1860,1080)
        self.fs.blocks[r_fcc].reactions = ["R_FCC"]
        self.fs.blocks[r_fcc].splitter_active = True
        self.fs.blocks[r_fcc].splitter_fractions = [0.48, 0.14, 0.18,
                                                     0.03, 0.07, 0.10]
        # Tanques productos FCC
        tk_naft_fcc_raw = self._add_example_block("TK-301","Storage tank — cone roof",
                                            150.0, 2160, 540)
        tk_lco   = self._add_example_block("TK-205","Storage tank — floating roof",
                                            400.0, 2160, 720)
        tk_glp_fcc = self._add_example_block("TK-206","Storage tank — cone roof",
                                            200.0, 2160, 900)
        tk_slurry = self._add_example_block("TK-207","Storage tank — cone roof",
                                            100.0, 2160,1080)
        tk_gasseco = self._add_example_block("TK-208","Storage tank — cone roof",
                                             100.0, 2160,1260)
        tk_coque_fcc = self._add_example_block("TK-209","Storage tank — cone roof",
                                             100.0, 2460,1080)

        # ============ FCK — FLEXICOKING ============
        # 4 productos: flexigas, nafta + gasóleos, coque neto.  S=15 m³.
        r_fck    = self._add_example_block("R-FCK","Reactor — autoclave",
                                              15.0, 1860,1440)
        self.fs.blocks[r_fck].reactions = ["R_FCK"]
        self.fs.blocks[r_fck].splitter_active = True
        self.fs.blocks[r_fck].splitter_fractions = [0.40, 0.25, 0.30, 0.05]
        tk_flexigas = self._add_example_block("TK-210","Storage tank — cone roof",
                                              100.0, 2160,1440)
        tk_naft_fck = self._add_example_block("TK-211","Storage tank — cone roof",
                                              150.0, 2160,1620)
        tk_gasoleo_fck = self._add_example_block("TK-212","Storage tank — cone roof",
                                              200.0, 2460,1620)
        tk_coque_neto = self._add_example_block("TK-213","Storage tank — cone roof",
                                              100.0, 2460,1440)

        # ============ PLANTA H2 (SMR) — auxiliar ============
        # CH4 + H2O → CO + 3 H2 ; CO + H2O → CO2 + H2  (PSA al final)
        tk_ch4   = self._add_example_block("TK-104","Storage tank — cone roof",
                                            200.0, 2760,  60)
        r_smr    = self._add_example_block("R-SMR","Reactor — autoclave",
                                              14.0, 3060,  60)
        self.fs.blocks[r_smr].reactions = ["R_SMR"]
        tk_h2_makeup = self._add_example_block("TK-214","Storage tank — cone roof",
                                            200.0, 3360,  60)
        tk_co2   = self._add_example_block("TK-215","Storage tank — cone roof",
                                             100.0, 3360, 240)
        # NOTA: el H2 de planta H2 + el H2 subproducto del RCA cubren la
        # demanda de HTD+HTN+HTF.  En este ejemplo no cerramos el balance
        # de H2 con recycle (ya el ejemplo es complejo); cada HT toma su
        # H2 makeup como feed local.

        # ============ STREAMS — Alimentación ============
        # Crudo pesado de selva (~21° API, 1.2% S)
        self._add_example_stream(tk_crudo, m101, "C0-crudo", 500000, role="feed",
                                  src_port="salida", dst_port="entrada1",
                                  price=470.0, T=25,
                                  composition={"crude_oil": 1.0},
                                  phase="liquid")
        # Agua de lavado (5% del crudo)
        self._add_example_stream(tk_agua, m101, "S-agua-lav", 25000, role="feed",
                                  src_port="salida", dst_port="entrada2",
                                  price=1.5, T=80,
                                  composition={"water": 1.0},
                                  phase="liquid")
        self._add_example_stream(m101, v101, "S-mix-desal", 0.0,
                                  src_port="salida", dst_port="alimentacion",
                                  T=130, phase="liquid",
                                  composition={"crude_oil": 0.952,
                                                 "water": 0.048})
        # Brine descarga (~5% del feed con sales)
        self._add_example_stream(v101, tk_brine, "S-brine", 25000, role="waste",
                                  src_port="liquido_fondo", dst_port="entrada",
                                  price=0.0, T=130, phase="liquid",
                                  composition={"water": 0.95,
                                                 "sodium chloride": 0.05})
        # Crudo desalado → horno
        self._add_example_stream(v101, f101, "C1-desalado", 500000,
                                  src_port="vapor", dst_port="alimentacion",
                                  T=130, phase="liquid",
                                  composition={"crude_oil": 1.0})
        # Carga DP1 (precalentada a 360°C)
        self._add_example_stream(f101, t101, "C1b-feed-DP1", 0.0,
                                  src_port="salida", dst_port="alimentacion",
                                  T=360, phase="two_phase",
                                  composition={"crude_oil": 1.0})

        # ============ STREAMS — Cortes DP1 ============
        # Orden = splitter_fractions: gas, naphtha, kero, diésel, gasóleo, residuo
        self._add_example_stream(t101, tk_fuel_gas, "C2a-gas", role="product",
                                  src_port="vapor_tope", dst_port="entrada",
                                  price=200.0, T=80, phase="gas",
                                  composition={"methane": 0.45,
                                                 "ethane": 0.30,
                                                 "propane": 0.15,
                                                 "hydrogen sulfide": 0.10})
        # Nafta → HTN
        self._add_example_stream(t101, r_htn, "C2-nafta",
                                  src_port="salida", dst_port="alimentacion",
                                  T=110, phase="liquid",
                                  composition={"naphtha": 0.97,
                                                 "hydrogen sulfide": 0.03})
        # Kerosene/Turbo A-1 (directo a tanque)
        self._add_example_stream(t101, tk_turbo, "C3-turbo", role="product",
                                  src_port="salida", dst_port="entrada",
                                  price=900.0, T=180, phase="liquid",
                                  composition={"kerosene": 0.99,
                                                 "hydrogen sulfide": 0.01})
        # Diésel → HTD
        self._add_example_stream(t101, r_htd, "C4-diesel",
                                  src_port="salida", dst_port="alimentacion",
                                  T=250, phase="liquid",
                                  composition={"diesel": 0.97,
                                                 "hydrogen sulfide": 0.03})
        # Gasóleo atmosférico → mezcla con LCO (a diésel pool)
        self._add_example_stream(t101, r_htd, "C5-gasoleo-atm",
                                  src_port="salida", dst_port="aux_in",
                                  T=300, phase="liquid",
                                  composition={"diesel": 0.90,
                                                 "hydrogen sulfide": 0.10})
        # Residuo atmosférico → DV3
        self._add_example_stream(t101, t201, "C6-residuo-atm",
                                  src_port="liquido_fondo", dst_port="alimentacion",
                                  T=350, phase="liquid",
                                  composition={"crude_oil": 1.0})

        # ============ STREAMS — DV3 cortes ============
        # LVGO+HVGO juntos → FCC
        self._add_example_stream(t201, r_fcc, "C7-VGO",
                                  src_port="salida", dst_port="alimentacion",
                                  T=320, phase="liquid",
                                  composition={"crude_oil": 1.0})
        # Residuo vacío → FCK
        self._add_example_stream(t201, r_fck, "C8-resid-vac",
                                  src_port="liquido_fondo", dst_port="alimentacion",
                                  T=360, phase="liquid",
                                  composition={"crude_oil": 1.0})

        # ============ STREAMS — FCC outputs (6) ============
        self._add_example_stream(r_fcc, tk_naft_fcc_raw, "C9-nafta-FCC",
                                  src_port="vapor", dst_port="entrada",
                                  T=120, phase="liquid",
                                  composition={"naphtha": 0.97,
                                                 "hydrogen sulfide": 0.03})
        self._add_example_stream(r_fcc, tk_lco, "C10-LCO", role="product",
                                  src_port="salida", dst_port="entrada",
                                  price=580.0, T=220, phase="liquid",
                                  composition={"diesel": 0.97,
                                                 "hydrogen sulfide": 0.03})
        self._add_example_stream(r_fcc, tk_glp_fcc, "C11-GLP-FCC",
                                  role="product",
                                  src_port="aux_out", dst_port="entrada",
                                  price=480.0, T=45, phase="gas",
                                  composition={"propane": 0.55,
                                                 "butane": 0.40,
                                                 "ethane": 0.05})
        self._add_example_stream(r_fcc, tk_gasseco, "C11b-gas-seco",
                                  role="product",
                                  src_port="vapor_tope", dst_port="entrada",
                                  price=180.0, T=45, phase="gas",
                                  composition={"methane": 0.50,
                                                 "ethane": 0.40,
                                                 "hydrogen": 0.10})
        self._add_example_stream(r_fcc, tk_slurry, "C11c-slurry",
                                  role="product",
                                  src_port="liquido_fondo", dst_port="entrada",
                                  price=320.0, T=200, phase="liquid",
                                  composition={"crude_oil": 1.0})
        self._add_example_stream(r_fcc, tk_coque_fcc, "C11d-coque-FCC",
                                  role="waste",
                                  src_port="cond_out", dst_port="entrada",
                                  price=0.0, T=600, phase="solid",
                                  composition={"carbon": 1.0})

        # Nafta FCC → HTF (limpieza S)
        self._add_example_stream(tk_naft_fcc_raw, r_htf, "C9b-naft-FCC-feed",
                                  src_port="salida", dst_port="alimentacion",
                                  T=120, phase="liquid",
                                  composition={"naphtha": 0.97,
                                                 "hydrogen sulfide": 0.03})

        # ============ STREAMS — FCK outputs (4) ============
        self._add_example_stream(r_fck, tk_flexigas, "C17-flexigas",
                                  role="product",
                                  src_port="vapor_tope", dst_port="entrada",
                                  price=80.0, T=200, phase="gas",
                                  composition={"methane": 0.10,
                                                 "carbon monoxide": 0.30,
                                                 "hydrogen": 0.20,
                                                 "nitrogen": 0.40})
        self._add_example_stream(r_fck, tk_naft_fck, "C17b-nafta-FCK",
                                  role="product",
                                  src_port="salida", dst_port="entrada",
                                  price=400.0, T=180, phase="liquid",
                                  composition={"naphtha": 1.0})
        self._add_example_stream(r_fck, tk_gasoleo_fck, "C17c-gasoleo-FCK",
                                  role="product",
                                  src_port="liquido_fondo", dst_port="entrada",
                                  price=450.0, T=260, phase="liquid",
                                  composition={"diesel": 1.0})
        self._add_example_stream(r_fck, tk_coque_neto, "C17d-coque-FCK",
                                  role="product",
                                  src_port="cond_out", dst_port="entrada",
                                  price=120.0, T=400, phase="solid",
                                  composition={"carbon": 1.0})

        # ============ STREAMS — HTN → RCA → gasolina 97 ============
        # H2 makeup a HTN (de planta H2)
        self._add_example_stream(tk_h2_makeup, r_htn, "C15a-H2-HTN", 800,
                                  src_port="salida", dst_port="aux_in",
                                  T=40, phase="gas",
                                  composition={"hydrogen": 0.999,
                                                 "methane": 0.001})
        # Nafta limpia → RCA
        self._add_example_stream(r_htn, r_rca, "C12-nafta-clean",
                                  src_port="producto", dst_port="alimentacion",
                                  T=130, phase="liquid",
                                  composition={"naphtha": 1.0})
        # Gasolina 97 RON + H2 subproducto → mezcla (modelado como
        # producto solo, el H2 se considera retornado al pool)
        self._add_example_stream(r_rca, tk_gaso97, "C13-gasolina97",
                                  role="product",
                                  src_port="producto", dst_port="entrada",
                                  price=1100.0, T=40, phase="liquid",
                                  composition={"gasoline_97": 0.96,
                                                 "hydrogen": 0.04})

        # ============ STREAMS — HTD → ULSD ============
        self._add_example_stream(tk_h2_makeup, r_htd, "C15b-H2-HTD", 0.0,
                                  src_port="salida", dst_port="aux_in",
                                  T=40, phase="gas",
                                  composition={"hydrogen": 0.999,
                                                 "methane": 0.001})
        self._add_example_stream(r_htd, tk_ulsd, "C14-ULSD", role="product",
                                  src_port="producto", dst_port="entrada",
                                  price=950.0, T=50, phase="liquid",
                                  composition={"diesel": 0.9995,
                                                 "hydrogen sulfide": 0.0005})

        # ============ STREAMS — HTF (limpia nafta FCC) ============
        self._add_example_stream(tk_h2_makeup, r_htf, "C15c-H2-HTF", 400,
                                  src_port="salida", dst_port="aux_in",
                                  T=40, phase="gas",
                                  composition={"hydrogen": 0.999,
                                                 "methane": 0.001})
        # Output HTF: mezcla al pool de gasolinas (al tanque gasolina 97)
        self._add_example_stream(r_htf, tk_gaso97, "C9c-naft-FCC-clean",
                                  src_port="producto", dst_port="entrada2",
                                  T=130, phase="liquid",
                                  composition={"naphtha": 0.9995,
                                                 "hydrogen sulfide": 0.0005})

        # ============ STREAMS — Planta H2 (SMR) ============
        # Gas natural feed
        self._add_example_stream(tk_ch4, r_smr, "C20-CH4", 3000, role="feed",
                                  src_port="salida", dst_port="alimentacion",
                                  price=180.0, T=350,
                                  composition={"methane": 1.0},
                                  phase="gas")
        # H2 purificado (post-PSA)
        self._add_example_stream(r_smr, tk_h2_makeup, "C15-H2-pure", 0.0,
                                  src_port="producto", dst_port="entrada",
                                  T=40, phase="gas",
                                  composition={"hydrogen": 0.999,
                                                 "methane": 0.001})
        # CO2 (subproducto venteado)
        self._add_example_stream(r_smr, tk_co2, "C20b-CO2", 300,
                                  role="waste",
                                  src_port="vapor_tope", dst_port="entrada",
                                  price=0.0, T=40, phase="gas",
                                  composition={"carbon dioxide": 1.0})

        # ============ DUTIES INFERIDOS ============
        # F-101 horno y R-RCA endotérmica: dejamos que el solver
        # calcule el duty desde el ΔT entre input y output (más
        # robusto que hardcodear y consistente con propiedades del DB).
        from flowsheet_solver import auto_set_duties_from_thermo
        auto_set_duties_from_thermo(self.fs)

        # ============ OPEX EXTRAS ============
        self._add_example_extra("Catalizador HDS CoMo/NiMo (3 HT)",
                                 flowrate=15, price=18000.0,
                                 stream="Consumables")
        self._add_example_extra("Catalizador RCA Pt-Re (reformado)",
                                 flowrate=2, price=120000.0,
                                 stream="Consumables")
        self._add_example_extra("Catalizador FCC zeolítico",
                                 flowrate=180, price=4500.0,
                                 stream="Consumables")
        self._add_example_extra("Energía eléctrica (cogen + red)",
                                 flowrate=720000, price=0.08,
                                 stream="Utilities")
        self._add_example_extra("Vapor proceso (cogen 606 t/h)",
                                 flowrate=4400000, price=15.0,
                                 stream="Utilities")

    # ==================================================================
    # CATÁLOGO EDUCATIVO E01–E24 (Lote 1: alimentaria simple Tier 1)
    # ==================================================================

    def _example_pasteurizer(self):
        """TIER 1 — Pasteurizador HTST de jugo.

        Operación térmica simple sin reacción química: jugo de fruta
        diluido en agua se calienta de 5 °C a 72 °C, se mantiene 15 s
        en el tubo de retención, y se enfría rápidamente a 4 °C antes
        del envasado.  Topología:

            TK-101  →  E-101  →  V-101  →  E-102  →  TK-102
            crudo     calent.   retened.  enfri.   pasteur.
            5°C       72°C      72°C/15s  4°C      product

        Basis 1000 tm/año, jugo = {water 0.88, sucrose 0.12}.  El
        retenedor es un Vessel vertical isotérmico (T constante,
        sin reacción).  Modo: sin reacciones químicas; el solver
        calcula los duties de calentador y enfriador desde Cp del
        mosto azucarado.  Los duties deben ser de signo opuesto y
        magnitud similar (no hay regeneración explícita en este
        modelo simple).
        """
        # Layout horizontal sencillo (5 bloques en línea)
        tk_in  = self._add_example_block("TK-101", "Storage tank — cone roof", 200.0,  80, 220)
        e101   = self._add_example_block("E-101",  "Heat exch. — floating head", 60.0, 260, 220)
        v101   = self._add_example_block("V-101",  "Vessel — vertical",          5.0,  440, 220)
        e102   = self._add_example_block("E-102",  "Heat exch. — floating head", 60.0, 620, 220)
        tk_out = self._add_example_block("TK-102", "Storage tank — cone roof", 200.0, 800, 220)

        juice = {"water": 0.88, "sucrose": 0.12}

        # Crudo a 5 °C
        self._add_example_stream(tk_in, e101, "S-jugo-crudo", 1000, role="feed",
                                 src_port="salida",   dst_port="tube_in",
                                 price=120.0, T=5,
                                 composition=juice,
                                 main_component="water", phase="liquid")
        # Intermedios: mass_flow=0 (el solver propaga 1000 desde el feed
        # vía Σin=Σout) y composición sin lock (se hereda del feed).  La T
        # SÍ queda locked: es el grado de libertad de diseño del problema
        # (calentar a 72 °C, enfriar a 4 °C) del que el solver deriva los
        # duties de E-101/E-102.
        # Calentado a 72 °C
        self._add_example_stream(e101, v101, "S-1", 0.0,
                                 src_port="tube_out", dst_port="alimentacion",
                                 T=72, phase="liquid")
        # Tras retenedor (T constante)
        self._add_example_stream(v101, e102, "S-2", 0.0,
                                 src_port="liquido",  dst_port="tube_in",
                                 T=72, phase="liquid")
        # Producto: mass_flow calculado; composición spec (locked).
        self._add_example_stream(e102, tk_out, "S-pasteurizado", 0.0, role="product",
                                 src_port="tube_out", dst_port="entrada",
                                 price=600.0, T=4,
                                 composition=juice,
                                 main_component="water", phase="liquid")

        # Duties auto desde Cp del mosto
        from flowsheet_solver import auto_set_duties_from_thermo
        auto_set_duties_from_thermo(self.fs)


    def _example_pineapple_juice(self):
        """TIER 1 — Jugo de piña concentrado por evaporación.

        Evapora agua de un jugo diluido 12 % sólidos hasta concentrado
        35 % sólidos.  Tren de doble efecto: el vapor de M-101 calienta
        al efecto 2.  Sin reacción química (operación física de
        concentración).

        Topología:
            TK-101 → E-101 → EV-101 → EV-102 → TK-102 (concentrado)
                                  ↓        ↓
                              vapor    vapor   (role=utility)

        Basis 1000 tm/año jugo diluido.  Balance:
            ST in:   120 tm/año (12 %)
            ST out:  120 tm/año (35 %)  → producto = 120/0.35 ≈ 342.9 tm/año
            Agua evaporada total ≈ 1000 − 342.9 = 657.1 tm/año
            (reparto 50/50 entre los dos efectos a fines didácticos).
        """
        tk_in  = self._add_example_block("TK-101", "Storage tank — cone roof", 200.0,  80, 240)
        e101   = self._add_example_block("E-101",  "Heat exch. — floating head", 30.0, 260, 240)
        ev101  = self._add_example_block("EV-101", "Evaporator — vertical",      40.0, 440, 220)
        ev102  = self._add_example_block("EV-102", "Evaporator — vertical",      30.0, 640, 220)
        tk_out = self._add_example_block("TK-102", "Storage tank — cone roof",   90.0, 840, 220)
        # tanques de vapor (utility) para visualizar el efluente
        tk_v1  = self._add_example_block("TK-V1",  "Storage tank — cone roof",  100.0, 440,  60)
        tk_v2  = self._add_example_block("TK-V2",  "Storage tank — cone roof",   90.0, 640,  60)

        # Composiciones por etapa
        diluted   = {"water": 0.880, "pineapple_solids": 0.120}    # 12 %
        mid       = {"water": 0.817, "pineapple_solids": 0.183}    # ~18 % tras efecto 1
        concen    = {"water": 0.650, "pineapple_solids": 0.350}    # 35 %

        # Feed: jugo diluido
        self._add_example_stream(tk_in, e101, "S-jugo-diluido", 1000, role="feed",
                                 src_port="salida",   dst_port="tube_in",
                                 price=200.0, T=20,
                                 composition=diluted,
                                 main_component="water", phase="liquid")
        # Pre-calentado al efecto 1
        self._add_example_stream(e101, ev101, "S-1", 0.0,
                                 src_port="tube_out", dst_port="alimentacion",
                                 T=80,
                                 composition=diluted,
                                 main_component="water", phase="liquid")
        # Producto efecto 1 → efecto 2 (masa deducida: 1000 − S-vap1; comp spec)
        self._add_example_stream(ev101, ev102, "S-2", 0.0,
                                 src_port="producto", dst_port="alimentacion",
                                 T=70,
                                 composition=mid,
                                 main_component="water", phase="liquid")
        # Vapor efecto 1 (~344 tm de agua)
        self._add_example_stream(ev101, tk_v1, "S-vap1", 344, role="utility",
                                 src_port="venteo",   dst_port="entrada",
                                 price=0.0, T=85,
                                 main_component="water", phase="vapor")
        # Producto efecto 2 = concentrado final  (342.9 tm: 120 sólidos / 35 %)
        self._add_example_stream(ev102, tk_out, "S-concentrado", 0.0, role="product",
                                 src_port="producto", dst_port="entrada",
                                 price=900.0, T=55,
                                 composition=concen,
                                 main_component="water", phase="liquid")
        # Vapor efecto 2 (~313 tm)
        self._add_example_stream(ev102, tk_v2, "S-vap2", 313, role="utility",
                                 src_port="venteo",   dst_port="entrada",
                                 price=0.0, T=60,
                                 main_component="water", phase="vapor")

        # Duties auto desde ΔH_vap del agua + Cp de la mezcla
        from flowsheet_solver import auto_set_duties_from_thermo
        auto_set_duties_from_thermo(self.fs)


    def _example_potato_chips(self):
        """TIER 1 — Papas fritas (freído industrial).

        Modo pseudo-reacción: la freidora evapora ~98 % del agua de
        la papa y la papa absorbe aceite hasta ~60 % p/p.  No es
        reacción química — es transferencia de masa simultánea.
        Se modela como Vessel con duty bloqueado (calor de freído
        = calor sensible + calor de evaporación del agua perdida).

        Topología:
            TK-101 (papas)  ┐
                            ├─→ FR-101 (freidora) ─→ TK-103 (chips)
            TK-102 (aceite) ┘            │
                                         └─→ TK-VAP (vapor agua, utility)

        Basis 1000 tm/año papa cruda {potato_solids 0.20, water 0.80}.
        Chip out: {potato_solids 0.38, water 0.02, vegetable_oil 0.60}.
        Sólidos conservan (200 tm/año) → chip = 200/0.38 ≈ 526.3 tm/año
        Agua en chip = 0.02·526.3 ≈ 10.5 tm/año
        Aceite absorbido = 0.60·526.3 ≈ 315.8 tm/año (feed adicional)
        Vapor de agua = 800 − 10.5 ≈ 789.5 tm/año (utility)
        Balance:  1000 + 315.8 = 526.3 + 789.5 = 1315.8 ✓
        """
        tk_papa  = self._add_example_block("TK-101", "Storage tank — cone roof", 200.0,  80, 200)
        tk_oil   = self._add_example_block("TK-102", "Storage tank — cone roof", 150.0,  80, 400)
        fr101    = self._add_example_block("FR-101", "Vessel — vertical",         20.0, 320, 300)  # freidora
        tk_chip  = self._add_example_block("TK-103", "Storage tank — cone roof", 200.0, 560, 300)  # chips
        tk_vap   = self._add_example_block("TK-VAP", "Storage tank — cone roof", 100.0, 320,  80)  # vapor agua

        papa_cruda = {"potato_solids": 0.20, "water": 0.80}
        chip_out   = {"potato_solids": 0.380, "water": 0.020, "vegetable_oil": 0.600}

        # Papa cruda (feed)
        self._add_example_stream(tk_papa, fr101, "S-papa-cruda", 1000, role="feed",
                                 src_port="salida",   dst_port="alimentacion",
                                 price=150.0, T=20,
                                 composition=papa_cruda,
                                 main_component="water", phase="liquid")
        # Aceite vegetal (feed, lo que se consume — el repuesto)
        self._add_example_stream(tk_oil, fr101, "S-aceite", 316, role="feed",
                                 src_port="salida",   dst_port="alimentacion",
                                 price=1200.0, T=180,
                                 main_component="vegetable_oil", phase="liquid")
        # Chips: salida sólida (Modo B: composición declarada)
        self._add_example_stream(fr101, tk_chip, "S-chips", 0.0, role="product",
                                 src_port="liquido",  dst_port="entrada",
                                 price=2500.0, T=170,
                                 composition=chip_out,
                                 main_component="vegetable_oil", phase="liquid")
        # Vapor de agua del freído (utility — recuperable como steam)
        self._add_example_stream(fr101, tk_vap, "S-vapor-agua", 790, role="utility",
                                 src_port="vapor",    dst_port="entrada",
                                 price=0.0, T=180,
                                 main_component="water", phase="vapor")

        # Duty de la freidora: calor sensible (papa 20→180 °C) +
        # ΔHvap·agua_evaporada.  Estimación rápida:
        #   sensible papa cruda  = 1000 tm × ~3.8 kJ/kg·K × 160 K = 608 GJ/año
        #   ΔHvap agua (789.5 tm × 2257 kJ/kg)              = 1782 GJ/año
        # Total ≈ 2390 GJ/año = 75.8 kW (continuo, 8760 h).
        # Se setea como duty bloqueado para que el solver no recalcule
        # y rompa el balance Modo B (los outlets ya están declarados).
        self._set_block_duty(fr101, +76)
        self.fs.blocks[fr101].duty_locked = True

        # Calor de "reacción" pseudo (evap del agua dominante)
        # ΔHvap·m_agua / m_in_total = 2257·(789.5/1316) ≈ +1354 kJ/kg input.
        # Signo + porque el sistema absorbe calor (endotérmico para el fluido).
        self.fs.blocks[fr101].heat_of_reaction = +1354.0

        from flowsheet_solver import auto_set_duties_from_thermo
        auto_set_duties_from_thermo(self.fs)


    # ==================================================================
    # Lote 2 — Bioproceso + química gratis (Tier 1, R006/R007 ya en DB)
    # ==================================================================

    def _example_beer_brewing(self):
        """TIER 1 — Cervecería (fermentación + venteo CO₂).

        ⏱ PROCESO BATCH MODELADO COMO CONTINUO EQUIVALENTE: en la
        industria la fermentación corre por lotes (cargas discretas
        de ~5–10 días).  Aquí se modela como flujo continuo usando
        el caudal promedio anual (producción/8760 h), técnica
        estándar de simulación en estado estacionario (Aspen/HYSYS
        steady-state).  El balance de masa y energía es correcto;
        NO se modela la dinámica temporal del lote.

        Química asociada (R007 en reactions_db.md, irreversible):
            1 Glucose(aq) → 2 C2H5OH(aq) + 2 CO2(g)
            ΔH ≈ −101.5 kJ/mol  (exotérmica suave)

        Modo B (composición declarada).  Justificación: el solver
        de equilibrio Gibbs no soporta reacciones irreversibles
        (Keq → ∞); por eso R007 se referencia como placeholder en
        block.reactions y la composición de salida se impone a mano
        respetando estequiometría con conversión 95 %.

        Topología:
            TK-mosto → R-101 (fermentador) → V-101 (venteo CO₂)
                                                 → E-101 (pasteur.) → TK-cerveza

        Basis 1000 tm/año mosto = {water 0.85, glucose 0.15}.
        Balance (95 % conv glucosa):
            150 g glucose × 0.95 = 142.5 reacted → 72.84 EtOH + 69.66 CO2
            CO2 venteado: 69.66 tm/año
            Cerveza fermentada: 850 H2O + 7.5 glucose + 72.84 EtOH ≈ 930.3 tm/año
            Total: 930.3 + 69.66 = 1000.0 ✓
        """
        tk_in   = self._add_example_block("TK-101", "Storage tank — cone roof", 250.0,  80, 240)
        r101    = self._add_example_block("R-101", "Reactor — jacketed agitated", 35.0, 260, 240)
        v101    = self._add_example_block("V-101", "Vessel — vertical",            12.0, 460, 240)
        tk_co2  = self._add_example_block("TK-102", "Storage tank — cone roof",    90.0, 460,  80)
        e101    = self._add_example_block("E-101", "Heat exch. — floating head",   50.0, 640, 240)
        tk_out  = self._add_example_block("TK-103", "Storage tank — cone roof",   200.0, 820, 240)

        # Modo B: placeholder R007 para marcar el bloque como reactor
        # de fermentación (educativo), pero los outlets se declaran a mano.
        self.fs.blocks[r101].reactions = ["R007_PLACEHOLDER"]
        self.fs.blocks[r101].T_op_K    = 295.0
        self.fs.blocks[r101].P_op_bar  = 1.0
        # Calor de reacción para que el solver calcule el duty del chaqueta:
        # ΔH = -101.52 kJ/mol_glucose × (142.5 g/y / 180.16 g/mol) = -80.32 GJ/y
        # = -2.55 kW (continuo).  Como heat_of_reaction es kJ/kg_input_total:
        # -80.32e6 / 1000e3 = -80.3 kJ/kg input.
        self.fs.blocks[r101].heat_of_reaction = -80.3

        mosto      = {"water": 0.85, "glucose": 0.15}
        fermented  = {"water": 0.850, "glucose": 0.0075,
                      "ethanol": 0.0728, "co2": 0.0697}
        beer_liq   = {"water": 0.9137, "glucose": 0.0081, "ethanol": 0.0783}

        # Feed: mosto azucarado (~15 °Brix)
        self._add_example_stream(tk_in, r101, "S-mosto", 1000, role="feed",
                                 src_port="salida",   dst_port="alimentacion",
                                 price=90.0, T=20,
                                 composition=mosto,
                                 main_component="water", phase="liquid")
        # Post-fermentador: composición declarada (Modo B)
        self._add_example_stream(r101, v101, "S-fermented", 0.0,
                                 src_port="producto", dst_port="alimentacion",
                                 T=22,
                                 composition=fermented,
                                 main_component="water", phase="liquid")
        # Venteo CO₂ (subproducto vendible — refrescos, secado, etc.)
        self._add_example_stream(v101, tk_co2, "S-CO2", 69.66, role="product",
                                 src_port="vapor",    dst_port="entrada",
                                 price=120.0, T=22,
                                 main_component="co2", phase="gas",
                                 composition={"co2": 1.0})
        # Líquido fermentado al pasteurizador (sin CO2 ya)
        self._add_example_stream(v101, e101, "S-vino", 0.0,
                                 src_port="liquido",  dst_port="tube_in",
                                 T=22,
                                 composition=beer_liq,
                                 main_component="water", phase="liquid")
        # Cerveza pasteurizada a 4 °C (producto envasado)
        self._add_example_stream(e101, tk_out, "S-cerveza", 0.0, role="product",
                                 src_port="tube_out", dst_port="entrada",
                                 price=1500.0, T=4,
                                 composition=beer_liq,
                                 main_component="water", phase="liquid")

        # Levadura (consumible)
        self._add_example_extra("Levadura (S. cerevisiae)",
                                flowrate=10.0, price=2_500.0,
                                stream="Consumables")

        from flowsheet_solver import auto_set_duties_from_thermo
        auto_set_duties_from_thermo(self.fs)


    def _example_sulfuric_acid(self):
        """TIER 1 — Ácido sulfúrico por proceso de contacto.

        Etapa 1 — Convertidor catalítico (R006 referenciada):
            2 SO2(g) + O2(g) → 2 SO3(g)   ΔH ≈ −198 kJ/mol O2
            T ≈ 770 K, P ≈ 1.2 bar, catalizador V₂O₅, conv ~98 %.
            R006 está derivada en Capa 3 pero SO3 no existe en
            thermo_db.md aún, por lo que se modela en Modo B con
            outputs declarados respetando estequiometría.

        Etapa 2 — Torre de absorción:
            SO3(g) + H2O(l) → H2SO4(l)
            Vessel Modo B (hidratación NO en DB), outlets declarados
            y duty bloqueado (reacción muy exotérmica).

        Topología:
            TK-SO2 + Aire → R-101 (Modo B) → E-101 → ABS-101 (Modo B) → TK-H2SO4
                                                          ↑
                                                       H2O (feed)

        Basis 1000 tm/año SO2 → ~1500 tm/año H2SO4 (con conv ~98 %).
        Balance R-101 (98 % conv de SO2):
            In:  1000 SO2 + 248 O2 + 817 N2 = 2065 tm/año
            React: 980 SO2 + 245 O2 → 1225 SO3
            Out: 20 SO2 + 3 O2 + 817 N2 + 1225 SO3 = 2065 ✓
        Balance ABS-101:  1225 SO3 + 276 H2O → 1501 H2SO4
            Venteos: 20 SO2 + 3 O2 + 817 N2 = 840 tm/año (waste)
            Total OUT: 1501 + 840 = 2341 vs IN 2065 + 276 = 2341 ✓
        """
        tk_so2  = self._add_example_block("TK-101", "Storage tank — cone roof",  90.0,  80, 200)
        tk_air  = self._add_example_block("TK-102", "Storage tank — cone roof",  90.0,  80, 380)
        m101    = self._add_example_block("M-101",  "Mixer — static",            2.0, 240, 290)
        r101    = self._add_example_block("R-101",  "Reactor — jacketed non-agit.", 35.0, 420, 290)
        e101    = self._add_example_block("E-101",  "Heat exch. — floating head", 80.0, 600, 290)
        tk_h2o  = self._add_example_block("TK-103", "Storage tank — cone roof",  90.0, 600, 480)
        abs101  = self._add_example_block("ABS-101","Vessel — vertical",          20.0, 780, 380)
        tk_acid = self._add_example_block("TK-104", "Storage tank — cone roof", 200.0, 980, 380)
        tk_vent = self._add_example_block("TK-105", "Storage tank — cone roof", 100.0, 980, 200)

        # Convertidor R-101 — Modo B con R006 como referencia educativa.
        self.fs.blocks[r101].reactions = ["R006_PLACEHOLDER"]
        self.fs.blocks[r101].T_op_K    = 770.0
        self.fs.blocks[r101].P_op_bar  = 1.2
        # Calor R006 ≈ -198 kJ/mol O2 reacted = -245/32 mol O2 = 7.66 kmol/y
        # × -198 kJ/mol = -1517 GJ/y = -48.1 kW continuo.  Por kg input
        # (2065 t/y): -1517e6/2065e3 = -734 kJ/kg.
        self.fs.blocks[r101].heat_of_reaction = -734.0

        # Composiciones (en thermo_db keys: so2, oxygen, nitrogen, water)
        air_comp = {"oxygen": 0.233, "nitrogen": 0.767}
        # Out R-101 (98 % conv SO2):  20 SO2 + 3 O2 + 817 N2 + 1225 SO3 = 2065
        conv_out = {"so2": 0.0097, "oxygen": 0.0015,
                    "nitrogen": 0.3956, "sulfur_trioxide": 0.5933}
        # Venteo absorción: 20 SO2 + 3 O2 + 817 N2 = 840  (sin SO3 residual)
        vent     = {"so2": 0.0238, "oxygen": 0.0036, "nitrogen": 0.9726}

        # Feed SO₂ puro (gas industrial, 1000 tm/año)
        self._add_example_stream(tk_so2, m101, "S-SO2", 1000, role="feed",
                                 src_port="salida",   dst_port="alimentacion_1",
                                 price=180.0, T=120,
                                 main_component="so2", phase="gas",
                                 composition={"so2": 1.0})
        # Aire para el convertidor (248 O2 + 817 N2 = 1065 tm/año)
        self._add_example_stream(tk_air, m101, "S-aire", 1065, role="feed",
                                 src_port="salida",   dst_port="alimentacion_2",
                                 price=0.0, T=25,
                                 composition=air_comp,
                                 main_component="nitrogen", phase="gas")
        # Mezcla al convertidor
        self._add_example_stream(m101, r101, "S-1", 0.0,
                                 src_port="producto", dst_port="alimentacion",
                                 T=420,
                                 composition={"so2": 0.484, **{k: v*(1-0.484) for k,v in air_comp.items()}},
                                 main_component="nitrogen", phase="gas")
        # Salida del convertidor — composición declarada (Modo B)
        self._add_example_stream(r101, e101, "S-conv", 0.0,
                                 src_port="producto", dst_port="tube_in",
                                 T=500,
                                 composition=conv_out,
                                 main_component="sulfur_trioxide", phase="gas")
        # Enfriado para absorción
        self._add_example_stream(e101, abs101, "S-cool", 0.0,
                                 src_port="tube_out", dst_port="alimentacion",
                                 T=80,
                                 composition=conv_out,
                                 main_component="sulfur_trioxide", phase="gas")
        # Agua de absorción (estequiométrica al SO3 producido)
        self._add_example_stream(tk_h2o, abs101, "S-H2O", 276, role="feed",
                                 src_port="salida",   dst_port="alimentacion",
                                 price=0.5, T=25,
                                 main_component="water", phase="liquid",
                                 composition={"water": 1.0})
        # H2SO4 producto 98 % (Modo B)
        self._add_example_stream(abs101, tk_acid, "S-H2SO4", 0.0, role="product",
                                 src_port="liquido", dst_port="entrada",
                                 price=140.0, T=70,
                                 composition={"sulfuric_acid": 0.98, "water": 0.02},
                                 main_component="sulfuric_acid", phase="liquid")
        # Venteo gases inertes (N2 + trazas SO2/O2)
        self._add_example_stream(abs101, tk_vent, "S-vent", 840, role="waste",
                                 src_port="vapor",   dst_port="entrada",
                                 price=0.0, T=70,
                                 composition=vent,
                                 main_component="nitrogen", phase="gas")

        # ABS-101: hidratación SO3+H2O→H2SO4 muy exotérmica ≈ -132 kJ/mol.
        # 1501 tm/año H2SO4 ≈ 15.30 kmol/h × -132 kJ/mol = -2020 GJ/y =
        # -64 kW continuo.
        self._set_block_duty(abs101, -64)
        self.fs.blocks[abs101].duty_locked = True

        # Catalizador V2O5 (consumible periódico)
        self._add_example_extra("Catalizador V₂O₅",
                                flowrate=0.4, price=15_000.0,
                                stream="Consumables")

        from flowsheet_solver import auto_set_duties_from_thermo
        auto_set_duties_from_thermo(self.fs)


    # ==================================================================
    # Lote 3 — Química fina + polímeros (Tier 1, R026/R027 Modo B)
    # ==================================================================

    def _example_acetic_acid(self):
        """TIER 1 — Ácido acético por carbonilación (Cativa/Monsanto).

        Química asociada (R026, NO DERIVADA DE CAPA 3):
            1 CH3OH(l) + 1 CO(g) → 1 CH3COOH(l)
            ΔH ≈ −133.8 kJ/mol  (exotérmica)
            T ≈ 458 K (185 °C), P ≈ 35 bar.
            Catalizador: Rh o Ir + promotor yoduro de metilo.
            Conversión por paso ~99 % selectiva (irreversible).
            IMPORTANTE: la carbonilación NO produce agua.

        Topología:
            TK-MeOH + TK-CO → K-101 (compresor CO) → M-101 → E-101
            → R-101 → V-101 (flash: purga CO no reaccionado)
                  → T-101 (columna producto) → TK-AcOH + TK-livianos

        Basis 1000 tm/año metanol → ~1856 tm/año ácido (99 % conv,
        MW 60.05/32.04 = 1.874).  Material esperado: Hastelloy
        (yoduro corrosivo).

        Modo B: R026 referenciada como placeholder (vant_Hoff no
        derivada en .md), composición de salida del reactor
        declarada respetando estequiometría con conversión 99 %.
        """
        # Layout 1.8× (planta industrial mediana)
        tk_meoh = self._add_example_block("TK-101", "Storage tank — cone roof", 200.0,  60, 200)
        tk_co   = self._add_example_block("TK-102", "Storage tank — cone roof", 150.0,  60, 400)
        k101    = self._add_example_block("K-101",  "Compressor — centrifugal", 450.0, 260, 400)
        m101    = self._add_example_block("M-101",  "Mixer — static",            2.0, 460, 300)
        e101    = self._add_example_block("E-101",  "Heat exch. — floating head", 80.0, 660, 300)
        r101    = self._add_example_block("R-101",  "Reactor — jacketed agitated", 35.0, 860, 300)
        v101    = self._add_example_block("V-101",  "Vessel — vertical",          25.0,1060, 300)
        tk_purg = self._add_example_block("TK-103", "Storage tank — cone roof",  90.0,1060,  80)
        t101    = self._add_example_block("T-101",  "Tower (column shell)",       45.0,1260, 380)
        e102    = self._add_example_block("E-102",  "Heat exch. — floating head", 60.0,1460, 200)
        e103    = self._add_example_block("E-103",  "Heat exch. — kettle reboiler", 80.0,1460, 560)
        tk_liv  = self._add_example_block("TK-104", "Storage tank — cone roof",   90.0,1640, 200)
        tk_ac   = self._add_example_block("TK-105", "Storage tank — cone roof",  300.0,1640, 560)

        # R-101 — Modo B con R026 referenciada
        self.fs.blocks[r101].reactions = ["R026_PLACEHOLDER"]
        self.fs.blocks[r101].T_op_K    = 458.0
        self.fs.blocks[r101].P_op_bar  = 35.0
        # ΔH = -133.8 kJ/mol_MeOH × (990 g/y / 32.04 g/mol) = -4135 GJ/y
        # = -131 kW continuo.  Por kg input total (1866 t/y): -2216 kJ/kg.
        self.fs.blocks[r101].heat_of_reaction = -2216.0

        # Composiciones (thermo_db keys: methanol, co, acetic_acid)
        # In R-101: 1000 MeOH + 866 CO = 1866 → MeOH 0.5357, CO 0.4643
        feed_mix = {"methanol": 0.5357, "co": 0.4643}
        # Out R-101 (99 % conv MeOH): 10 MeOH + 9 CO + 1855 AcOH = 1874
        # (un poco de CO en exceso queda; mass: 10 MeOH consume 10·(28/32)=8.75 CO)
        rxn_out  = {"methanol": 0.0053, "co": 0.0048, "acetic_acid": 0.9899}

        # Feed metanol líquido (1000 tm/año puro)
        self._add_example_stream(tk_meoh, m101, "S-MeOH", 1000, role="feed",
                                 src_port="salida",   dst_port="alimentacion_1",
                                 price=500.0, T=25,
                                 main_component="methanol", phase="liquid",
                                 composition={"methanol": 1.0})
        # CO succión (gas industrial)
        self._add_example_stream(tk_co, k101, "S-CO", 866, role="feed",
                                 src_port="salida",   dst_port="succion",
                                 price=400.0, T=25,
                                 main_component="co", phase="gas",
                                 composition={"co": 1.0})
        # CO comprimido a 35 bar
        self._add_example_stream(k101, m101, "S-CO-HP", 0.0,
                                 src_port="descarga", dst_port="alimentacion_2",
                                 T=120,
                                 main_component="co", phase="gas",
                                 composition={"co": 1.0}, lock_T=False)
        # Mezcla al precalentador
        self._add_example_stream(m101, e101, "S-1", 0.0,
                                 src_port="producto", dst_port="tube_in",
                                 T=80,
                                 composition=feed_mix,
                                 main_component="methanol", phase="liquid")
        # Pre-calentado al reactor
        self._add_example_stream(e101, r101, "S-2", 0.0,
                                 src_port="tube_out", dst_port="alimentacion",
                                 T=180,
                                 composition=feed_mix,
                                 main_component="methanol", phase="liquid")
        # Salida del reactor (Modo B)
        self._add_example_stream(r101, v101, "S-3", 0.0,
                                 src_port="producto", dst_port="alimentacion",
                                 T=185,
                                 composition=rxn_out,
                                 main_component="acetic_acid", phase="liquid")
        # Flash: purga de CO no reaccionado por vapor (9 t/y CO)
        self._add_example_stream(v101, tk_purg, "S-purga", 9, role="waste",
                                 src_port="vapor", dst_port="entrada",
                                 price=0.0, T=185,
                                 main_component="co", phase="gas",
                                 composition={"co": 1.0})
        # Líquido del flash a columna (1857: 10 MeOH + 1847 AcOH)
        self._add_example_stream(v101, t101, "S-4", 0.0,
                                 src_port="liquido",    dst_port="alimentacion",
                                 T=180,
                                 composition={"methanol": 0.0054, "acetic_acid": 0.9946},
                                 main_component="acetic_acid", phase="liquid")
        # Tope columna (livianos: metanol residual)
        self._add_example_stream(t101, e102, "S-vap", 10,
                                 src_port="vapor_tope", dst_port="tube_in",
                                 T=65,
                                 main_component="methanol", phase="vapor",
                                 composition={"methanol": 1.0})
        # Livianos condensados a TK (reciclables, role=waste por simplicidad)
        self._add_example_stream(e102, tk_liv, "S-livianos", 0.0, role="waste",
                                 src_port="tube_out", dst_port="entrada",
                                 price=0.0, T=45,
                                 main_component="methanol", phase="liquid",
                                 composition={"methanol": 1.0})
        # Fondos: ácido acético glacial al producto
        self._add_example_stream(t101, e103, "S-fondo", 0.0,
                                 src_port="liquido_fondo", dst_port="liq_in",
                                 T=118,
                                 main_component="acetic_acid", phase="liquid",
                                 composition={"acetic_acid": 1.0})
        # Ácido glacial al tanque (producto principal, ~1847 tm/año)
        self._add_example_stream(e103, tk_ac, "S-AcOH", 0.0, role="product",
                                 src_port="cond_out", dst_port="entrada",
                                 price=600.0, T=60,
                                 main_component="acetic_acid", phase="liquid",
                                 composition={"acetic_acid": 1.0})

        # Mano de obra y catalizador
        self._set_example_labor(200_000)
        self._add_example_extra("Catalizador Rh (carbonilación)",
                                flowrate=0.1, price=40_000.0,
                                stream="Consumables")
        self._add_example_extra("Yoduro de metilo (promotor)",
                                flowrate=3.0, price=8_000.0,
                                stream="Consumables")

        from flowsheet_solver import auto_set_duties_from_thermo
        auto_set_duties_from_thermo(self.fs)


    def _example_polyethylene(self):
        """TIER 1 — Polietileno LDPE (alta presión, autoclave).

        Química (R027, NO DERIVADA DE CAPA 3, conversión declarada):
            1 C2H4(g) → 1 (-C2H4-)n (polyethylene, sólido)
            ΔH ≈ -93 kJ/mol etileno (exotérmica fuerte)
            T ≈ 200-300 °C, P ≈ 1500-2500 bar, iniciador peróxido.
            Conv por paso 20-35 % (LDPE típico); resto recicla.

        Modo B: poliadición NO es equilibrio termodinámico, es
        cinética de cadena.  Composiciones de salida declaradas
        con conv 30 % por paso.  Sin reciclo cerrado (la purga
        de etileno se vende como fuel-gas, simplificación
        pedagógica vs. la planta real con compresor de reciclo).

        Topología:
            TK-etileno → K-101 (compresor alta P) → R-101 (autoclave
            Modo B) → V-101 (flash HP separa PE de etileno gas)
                  → TK-PE (producto)
                  → TK-purga (etileno no reaccionado, fuel-gas)

        Basis 1000 tm/año etileno → 300 PE + 700 etileno purga.
        Calor a extraer R-101: ΔH × n_PE = -93 × (300e3/28.05·1000)
        = -993 GJ/año = -31.5 kW continuo.
        """
        tk_eth  = self._add_example_block("TK-101", "Storage tank — cone roof", 200.0,  80, 280)
        k101    = self._add_example_block("K-101",  "Compressor — reciprocating", 450.0, 280, 280)
        r101    = self._add_example_block("R-101",  "Reactor — autoclave",         5.0, 480, 280)
        v101    = self._add_example_block("V-101",  "Vessel — vertical",          15.0, 680, 280)
        tk_pe   = self._add_example_block("TK-102", "Storage tank — cone roof", 200.0, 880, 380)
        tk_pur  = self._add_example_block("TK-103", "Storage tank — cone roof", 150.0, 880, 180)

        # R-101 — Modo B con R027 placeholder
        self.fs.blocks[r101].reactions = ["R027_PLACEHOLDER"]
        self.fs.blocks[r101].T_op_K    = 523.0       # ~250 °C
        self.fs.blocks[r101].P_op_bar  = 2000.0      # alta P LDPE
        # ΔH·n_PE = -93 kJ/mol × (300e3 kg/y / 28.05 kg/kmol) = -994 GJ/y
        # Por kg input total (1000 t/y): -994 kJ/kg.
        self.fs.blocks[r101].heat_of_reaction = -994.0

        # Out R-101: 30 % PE + 70 % etileno (másica)
        rxn_out = {"ethylene": 0.700, "polyethylene": 0.300}

        # Feed etileno gas (1000 tm/año puro)
        self._add_example_stream(tk_eth, k101, "S-eth", 1000, role="feed",
                                 src_port="salida",   dst_port="succion",
                                 price=900.0, T=25,
                                 main_component="ethylene", phase="gas",
                                 composition={"ethylene": 1.0})
        # Etileno comprimido alta P
        self._add_example_stream(k101, r101, "S-HP", 0.0,
                                 src_port="descarga", dst_port="alimentacion",
                                 T=80,
                                 main_component="ethylene", phase="gas",
                                 composition={"ethylene": 1.0}, lock_T=False)
        # Salida reactor: mezcla bifásica (PE sólido suspendido + etileno gas)
        self._add_example_stream(r101, v101, "S-mix", 0.0,
                                 src_port="producto", dst_port="alimentacion",
                                 T=250,
                                 composition=rxn_out,
                                 main_component="polyethylene", phase="two_phase")
        # Purga etileno no reaccionado (vapor, vendible como fuel)
        self._add_example_stream(v101, tk_pur, "S-purga-eth", 0.0, role="product",
                                 src_port="vapor", dst_port="entrada",
                                 price=600.0, T=80,
                                 main_component="ethylene", phase="gas",
                                 composition={"ethylene": 1.0})
        # PE sólido al tanque (producto principal)
        self._add_example_stream(v101, tk_pe, "S-PE", 300, role="product",
                                 src_port="liquido", dst_port="entrada",
                                 price=1400.0, T=80,
                                 main_component="polyethylene", phase="liquid",
                                 composition={"polyethylene": 1.0})

        # Mano de obra (planta de alta presión, complejidad media)
        self._set_example_labor(180_000)
        # Iniciador (peróxido) — consumible
        self._add_example_extra("Iniciador peróxido orgánico",
                                flowrate=2.5, price=12_000.0,
                                stream="Consumables")

        from flowsheet_solver import auto_set_duties_from_thermo
        auto_set_duties_from_thermo(self.fs)


    # ==================================================================
    # Lote 4a — Inorgánica + materiales (Tier 1, R028/R029)
    # ==================================================================

    def _example_chloralkali_hcl(self):
        """TIER 1 — Cloro-álcali + recuperación de HCl.

        Versión compacta (vs QUIMPAC, que es industrial pesado) con
        recuperación de HCl 33 % como subproducto.  Dos químicas:

        Celda (R_CELDA placeholder, Modo B):
            2 NaCl + 2 H2O → 2 NaOH + Cl2 + H2
            Electrólisis de membrana; el solver no resuelve
            electroquímica → outputs declarados como QUIMPAC.

        Quemador HCl (R028 placeholder, Modo B — irreversible):
            1 H2 + 1 Cl2 → 2 HCl
            Reacción explosivamente exotérmica con ignición UV/llama.
            Conv ≥99 %, T≈800 °C, ΔH = −184.6 kJ/mol_O2 equiv.

        Topología:
            TK-NaCl + TK-H2O → CELDA → {NaOH, Cl2×2, H2×2 streams}
            Cl2_split→ TK-Cl2 (producto)
                     → R-201 (quemador) → ABS-201 → TK-HCl
            H2_split → TK-H2 (producto, fuel-gas)
                     → R-201

        Basis 1000 tm/año NaCl → 685 NaOH + 407 Cl2 + 11.6 H2 +
        206 HCl 33 % (200 Cl2 + 5.7 H2 reaccionados con 138 H2O).
        Keys con guión bajo (chlorine, hydrogen_chloride, etc. de
        components.py Lote 0); QUIMPAC usa strings con espacio —
        deuda técnica documentada.
        """
        # Feeds
        tk_nacl = self._add_example_block("TK-101", "Storage tank — cone roof", 300.0,  60, 200)
        tk_h2o  = self._add_example_block("TK-102", "Storage tank — cone roof", 300.0,  60, 400)
        # Celda de electrólisis
        celda   = self._add_example_block("R-101",  "Reactor — autoclave",       12.0, 280, 300)
        # Productos directos de la celda
        tk_naoh = self._add_example_block("TK-103", "Storage tank — cone roof", 300.0, 480, 540)
        tk_cl2  = self._add_example_block("TK-104", "Storage tank — cone roof", 200.0, 480, 360)
        tk_h2p  = self._add_example_block("TK-105", "Storage tank — cone roof", 100.0, 480, 180)
        # Quemador HCl + absorción
        r201    = self._add_example_block("R-201",  "Reactor — jacketed non-agit.", 20.0, 720, 280)
        tk_h2o2 = self._add_example_block("TK-106", "Storage tank — cone roof", 100.0, 720, 480)
        abs201  = self._add_example_block("ABS-201","Vessel — vertical",          18.0, 920, 380)
        tk_hcl  = self._add_example_block("TK-107", "Storage tank — cone roof", 150.0,1120, 380)

        # Celda — Modo B (placeholder R_CELDA)
        self.fs.blocks[celda].reactions = ["R_CELDA_CLORALCALI"]
        self.fs.blocks[celda].T_op_K    = 358.15
        self.fs.blocks[celda].P_op_bar  = 1.5
        # Energía eléctrica de celda: ~2.5 kWh/kg Cl2 → 607 t·2.5e3 kWh
        # = 1.52e6 kWh/año = 173 kW continuo.  En convención block.duty
        # es CALOR; para celda eléctrica usamos OPEX extra en lugar.
        # Aquí setamos duty=0 y declaramos energía como utility-extra.

        # R-201 quemador HCl — Modo B
        self.fs.blocks[r201].reactions = ["R028_PLACEHOLDER"]
        self.fs.blocks[r201].T_op_K    = 1073.0
        self.fs.blocks[r201].P_op_bar  = 1.1
        # ΔH ≈ -184.6 kJ/mol_H2 × 5.69e3/2.016 kmol/y = -521 GJ/y
        # = -16.5 kW continuo.  Por kg input (205.7 t/y): -2534 kJ/kg.
        self.fs.blocks[r201].heat_of_reaction = -2534.0

        # Feed NaCl (sólido o salmuera; aquí líquido por simplicidad)
        self._add_example_stream(tk_nacl, celda, "S-NaCl", 1000, role="feed",
                                 src_port="salida", dst_port="alimentacion",
                                 price=80.0, T=25,
                                 main_component="sodium_chloride", phase="liquid",
                                 composition={"sodium_chloride": 1.0})
        # Feed H2O
        self._add_example_stream(tk_h2o, celda, "S-H2O", 308, role="feed",
                                 src_port="salida", dst_port="alimentacion",
                                 price=0.5, T=25,
                                 main_component="water", phase="liquid",
                                 composition={"water": 1.0})
        # NaOH 100 % (simplificado; planta real es solución 32-50 %)
        self._add_example_stream(celda, tk_naoh, "S-NaOH", 0.0, role="product",
                                 src_port="producto", dst_port="entrada",
                                 price=400.0, T=80,
                                 main_component="sodium_hydroxide", phase="liquid",
                                 composition={"sodium_hydroxide": 1.0})
        # Cl2 → producto (407 t/y)
        self._add_example_stream(celda, tk_cl2, "S-Cl2-prod", 407, role="product",
                                 src_port="producto", dst_port="entrada",
                                 price=350.0, T=80,
                                 main_component="chlorine", phase="gas",
                                 composition={"chlorine": 1.0})
        # Cl2 → R-201 (200 t/y para HCl)
        self._add_example_stream(celda, r201, "S-Cl2-rxn", 200,
                                 src_port="producto", dst_port="alimentacion",
                                 T=80,
                                 main_component="chlorine", phase="gas",
                                 composition={"chlorine": 1.0})
        # H2 → producto (11.6 t/y, fuel-gas)
        self._add_example_stream(celda, tk_h2p, "S-H2-prod", 11.57, role="product",
                                 src_port="producto", dst_port="entrada",
                                 price=1500.0, T=80,
                                 main_component="hydrogen", phase="gas",
                                 composition={"hydrogen": 1.0})
        # H2 → R-201 (5.69 t/y para HCl)
        self._add_example_stream(celda, r201, "S-H2-rxn", 5.69,
                                 src_port="producto", dst_port="alimentacion",
                                 T=80,
                                 main_component="hydrogen", phase="gas",
                                 composition={"hydrogen": 1.0})
        # Salida quemador: HCl gas (206 t/y)
        self._add_example_stream(r201, abs201, "S-HCl-gas", 0.0,
                                 src_port="producto", dst_port="alimentacion",
                                 T=400,
                                 main_component="hydrogen_chloride", phase="gas",
                                 composition={"hydrogen_chloride": 1.0})
        # Agua de absorción (estequiométrica para HCl 33 %)
        # HCl 33 % p/p: 206 HCl + 418 H2O = 624 → 33 %
        self._add_example_stream(tk_h2o2, abs201, "S-H2O-abs", 418, role="feed",
                                 src_port="salida", dst_port="alimentacion",
                                 price=0.5, T=25,
                                 main_component="water", phase="liquid",
                                 composition={"water": 1.0})
        # HCl 33 % solución producto
        self._add_example_stream(abs201, tk_hcl, "S-HCl-33", 0.0, role="product",
                                 src_port="liquido", dst_port="entrada",
                                 price=180.0, T=40,
                                 main_component="hydrogen_chloride", phase="liquid",
                                 composition={"hydrogen_chloride": 0.33, "water": 0.67})

        # OPEX
        self._set_example_labor(200_000)
        self._add_example_extra("Energía eléctrica celda (2.5 kWh/kg Cl₂)",
                                flowrate=1_520_000, price=0.08,
                                stream="Utilities")
        self._add_example_extra("Membrana ion-selectiva (replazo 5 años)",
                                flowrate=0.2, price=20_000.0,
                                stream="Consumables")
        self._add_example_extra("Ánodos DSA (Ti/RuO₂)",
                                flowrate=0.1, price=15_000.0,
                                stream="Consumables")

        from flowsheet_solver import auto_set_duties_from_thermo
        auto_set_duties_from_thermo(self.fs)


    def _example_cement(self):
        """TIER 1 — Cemento Portland por horno rotatorio.

        Química clave (R029, NO DERIVADA, Modo B):
            1 CaCO3(s) → 1 CaO(s) + 1 CO2(g)   ΔH ≈ +178 kJ/mol
            Calcinación endotérmica fuerte (T ≈ 1450 °C / 1723 K).
            Conv >99 % a T de horno.  La clinkerización (formación
            de silicatos C3S/C2S) se abstrae al pseudo-componente
            `clinker`.

        Topología:
            TK-caliza → FH-101 (precalentador) → R-101 (horno
            rotatorio Modo B) → E-101 (enfriador clínker) →
            TK-cemento
                              → TK-emisión (CO₂ waste)

        Basis 1000 tm/año caliza pura {limestone 1.0}.  Stoich:
            1000/100.09 = 9.99 kmol → 9.99 kmol CaO (≈560 t/y)
            + 9.99 kmol CO2 (≈440 t/y).  Modelado:
                clinker_out = 560 tm/año (CaO + silicatos abstraídos)
                co2_out     = 440 tm/año (emisión, punto educativo)
            La emisión inherente de CO₂ es ~0.44 kg CO₂ / kg CaO —
            huella de carbono crítica para la industria de cemento.
        """
        tk_in   = self._add_example_block("TK-101", "Storage tank — cone roof", 300.0,  60, 280)
        fh101   = self._add_example_block("FH-101", "Fired heater — non-reformer", 8000.0, 260, 280)
        r101    = self._add_example_block("R-101",  "Reactor — jacketed non-agit.", 25.0, 460, 280)
        e101    = self._add_example_block("E-101",  "Heat exch. — air cooler",   200.0, 660, 360)
        tk_cem  = self._add_example_block("TK-102", "Storage tank — cone roof", 300.0, 860, 360)
        tk_co2  = self._add_example_block("TK-103", "Storage tank — cone roof", 100.0, 460,  60)

        # R-101 — Modo B con R029 placeholder
        self.fs.blocks[r101].reactions = ["R029_PLACEHOLDER"]
        self.fs.blocks[r101].T_op_K    = 1723.0
        self.fs.blocks[r101].P_op_bar  = 1.0
        # ΔH = +178.3 kJ/mol_CaCO3 × 9.99 kmol/y = +1781 GJ/y
        # Por kg input (1000 t/y): +1781 kJ/kg (endotérmico fuerte).
        self.fs.blocks[r101].heat_of_reaction = +1781.0

        # Composición salida horno (mezcla sólido + gas)
        clk_mix = {"clinker": 0.560, "co2": 0.440}

        # Caliza al precalentador
        self._add_example_stream(tk_in, fh101, "S-caliza", 1000, role="feed",
                                 src_port="salida", dst_port="proceso_in",
                                 price=15.0, T=25,
                                 main_component="limestone", phase="liquid",
                                 composition={"limestone": 1.0})
        # Caliza precalentada (~900 °C, entrada al horno)
        self._add_example_stream(fh101, r101, "S-1", 0.0,
                                 src_port="proceso_out", dst_port="alimentacion",
                                 T=900,
                                 main_component="limestone", phase="liquid",
                                 composition={"limestone": 1.0})
        # Salida del horno: clínker + CO2 (Modo B)
        # Sólido (clínker) por el "liquido" port
        self._add_example_stream(r101, e101, "S-clinker", 0.0,
                                 src_port="producto", dst_port="proceso_in",
                                 T=1450,
                                 main_component="clinker", phase="liquid",
                                 composition={"clinker": 1.0})
        # CO2 emisión (por puerto distinto — usamos util_in/util_out
        # del REACTOR_PORTS para el venteo de gases)
        self._add_example_stream(r101, tk_co2, "S-CO2-emit", 440, role="waste",
                                 src_port="util_out", dst_port="entrada",
                                 price=0.0, T=1450,
                                 main_component="co2", phase="gas",
                                 composition={"co2": 1.0})
        # Clínker enfriado al silo (la molienda se abstrae)
        self._add_example_stream(e101, tk_cem, "S-cemento", 0.0, role="product",
                                 src_port="proceso_out", dst_port="entrada",
                                 price=85.0, T=60,
                                 main_component="clinker", phase="liquid",
                                 composition={"clinker": 1.0})

        self._set_example_labor(180_000)
        self._add_example_extra("Combustible horno (coque + biomasa)",
                                flowrate=120, price=160.0,
                                stream="Utilities")

        from flowsheet_solver import auto_set_duties_from_thermo
        auto_set_duties_from_thermo(self.fs)


    def _example_glass(self):
        """TIER 1 — Vidrio sodocálcico (horno de fusión).

        Sin reacción en DB — fusión a vidrio es proceso físico-químico
        complejo dominado por energía (calor de fusión ≈ 2200 MJ/t).
        Modo B con composición de salida declarada respetando balance
        de masa: la fusión libera CO₂ proveniente de soda ash y caliza
        (descarbonatación in-situ).

        Topología:
            TK-arena + TK-soda + TK-caliza → M-101 (mezcla batch) →
            R-101 (horno fusión Modo B, ~1500 °C) → E-101 (cooler) →
            TK-vidrio (producto) + TK-CO2 (emisión)

        Basis 1000 tm/año batch típico {silica 0.72, soda_ash 0.14,
        limestone 0.14}.  Cálculo de CO₂ liberado:
            Na2CO3 → Na2O + CO2:  0.14·(44/106) = 0.058 → 58 t/y CO₂
            CaCO3  → CaO  + CO2:  0.14·(44/100) = 0.062 → 62 t/y CO₂
        Vidrio formado = 1000 − 120 = 880 t/y.
        """
        tk_si   = self._add_example_block("TK-101", "Storage tank — cone roof", 200.0,  60, 200)
        tk_sd   = self._add_example_block("TK-102", "Storage tank — cone roof", 150.0,  60, 360)
        tk_lm   = self._add_example_block("TK-103", "Storage tank — cone roof", 150.0,  60, 520)
        m101    = self._add_example_block("M-101",  "Mixer — static",            2.0, 280, 360)
        r101    = self._add_example_block("R-101",  "Reactor — jacketed non-agit.", 30.0, 500, 360)
        e101    = self._add_example_block("E-101",  "Heat exch. — air cooler",   100.0, 720, 460)
        tk_gl   = self._add_example_block("TK-104", "Storage tank — cone roof", 250.0, 920, 460)
        tk_co2  = self._add_example_block("TK-105", "Storage tank — cone roof", 100.0, 500, 100)

        # R-101 — Modo B fusión vidrio (sin reacción en DB)
        self.fs.blocks[r101].reactions = ["R_FUSION_GLASS"]
        self.fs.blocks[r101].T_op_K    = 1773.0      # 1500 °C
        self.fs.blocks[r101].P_op_bar  = 1.0
        # Calor de fusión ≈ 2200 MJ/t × 1000 t/y = 2.2e6 GJ/y = 70 kW continuo.
        # Endotérmico: +2200 kJ/kg input.  Duty bloqueado.
        self._set_block_duty(r101, +250)
        self.fs.blocks[r101].duty_locked = True
        self.fs.blocks[r101].heat_of_reaction = +2200.0

        # Composición del batch al mixer
        batch_mix = {"silica": 0.72, "soda_ash": 0.14, "limestone": 0.14}

        # Feeds
        self._add_example_stream(tk_si, m101, "S-silica", 720, role="feed",
                                 src_port="salida", dst_port="alimentacion_1",
                                 price=30.0, T=25,
                                 main_component="silica", phase="liquid",
                                 composition={"silica": 1.0})
        self._add_example_stream(tk_sd, m101, "S-soda", 140, role="feed",
                                 src_port="salida", dst_port="alimentacion_2",
                                 price=350.0, T=25,
                                 main_component="soda_ash", phase="liquid",
                                 composition={"soda_ash": 1.0})
        self._add_example_stream(tk_lm, m101, "S-lime", 140, role="feed",
                                 src_port="salida", dst_port="alimentacion_2",
                                 price=15.0, T=25,
                                 main_component="limestone", phase="liquid",
                                 composition={"limestone": 1.0})
        # Mezcla batch al horno
        self._add_example_stream(m101, r101, "S-batch", 0.0,
                                 src_port="producto", dst_port="alimentacion",
                                 T=25,
                                 composition=batch_mix,
                                 main_component="silica", phase="liquid")
        # Vidrio fundido al cooler
        self._add_example_stream(r101, e101, "S-melt", 0.0,
                                 src_port="producto", dst_port="proceso_in",
                                 T=1500,
                                 main_component="glass", phase="liquid",
                                 composition={"glass": 1.0})
        # CO2 emisión (soda + caliza descarbonatadas)
        self._add_example_stream(r101, tk_co2, "S-CO2", 120, role="waste",
                                 src_port="util_out", dst_port="entrada",
                                 price=0.0, T=1500,
                                 main_component="co2", phase="gas",
                                 composition={"co2": 1.0})
        # Vidrio sólido (~25 °C tras conformado abstraído)
        self._add_example_stream(e101, tk_gl, "S-glass", 0.0, role="product",
                                 src_port="proceso_out", dst_port="entrada",
                                 price=400.0, T=200,
                                 main_component="glass", phase="liquid",
                                 composition={"glass": 1.0})

        self._set_example_labor(150_000)
        self._add_example_extra("Gas natural (horno)",
                                flowrate=180, price=180.0,
                                stream="Utilities")

        from flowsheet_solver import auto_set_duties_from_thermo
        auto_set_duties_from_thermo(self.fs)


    # ==================================================================
    # Lote 4b — Saponificación + urea (Tier 1, R030/R031 Modo B)
    # ==================================================================

    def _example_soap(self):
        """TIER 1 — Jabón por saponificación de triglicérido.

        Química (R030 placeholder Modo B):
            1 vegetable_oil + 3 NaOH → 3 soap + 1 glycerin
            ΔH ≈ −60 kJ/mol_oil (exotérmica suave).
            T ≈ 80 °C, conversión >99 %.  Subproducto glicerina
            valiosa.

        Topología:
            TK-oil + TK-NaOH → M-101 → R-101 saponif → V-101
                decanter → TK-soap (sólido) + TK-glycerin (subprod)

        Basis 1000 tm/año vegetable_oil + 136 tm/año NaOH →
        1032 tm/año soap + 104 tm/año glycerin (estequiométrico).
        Modo B con composición declarada (R030 NO DERIVADA, sin
        van't Hoff en .md).
        """
        tk_oil  = self._add_example_block("TK-101", "Storage tank — cone roof", 200.0,  60, 200)
        tk_naoh = self._add_example_block("TK-102", "Storage tank — cone roof",  90.0,  60, 400)
        m101    = self._add_example_block("M-101",  "Mixer — static",            2.0, 260, 300)
        r101    = self._add_example_block("R-101",  "Reactor — jacketed agitated", 30.0, 480, 300)
        v101    = self._add_example_block("V-101",  "Vessel — vertical",          15.0, 680, 300)
        tk_soap = self._add_example_block("TK-103", "Storage tank — cone roof", 250.0, 880, 180)
        tk_gly  = self._add_example_block("TK-104", "Storage tank — cone roof", 100.0, 880, 420)

        # R-101 — Modo B con R030 placeholder
        self.fs.blocks[r101].reactions = ["R030_PLACEHOLDER"]
        self.fs.blocks[r101].T_op_K    = 353.0
        self.fs.blocks[r101].P_op_bar  = 1.0
        # ΔH = -60 kJ/mol_oil × (1000e3 / 885) mol/y = -67.8 GJ/y
        # = -2.15 kW continuo.  Por kg input (1135.6 t/y): -59.7 kJ/kg.
        self.fs.blocks[r101].heat_of_reaction = -59.7

        # Composición mezcla pre-R101: 1000 oil + 135.6 NaOH = 1135.6
        feed_mix = {"vegetable_oil": 0.881, "sodium_hydroxide": 0.119}
        # Salida R-101 (Modo B): 1032 soap + 104 glycerin = 1136
        rxn_out  = {"soap": 0.908, "glycerin": 0.092}

        # Aceite (feed)
        self._add_example_stream(tk_oil, m101, "S-oil", 1000, role="feed",
                                 src_port="salida", dst_port="alimentacion_1",
                                 price=900.0, T=25,
                                 main_component="vegetable_oil", phase="liquid",
                                 composition={"vegetable_oil": 1.0})
        # NaOH (feed)
        self._add_example_stream(tk_naoh, m101, "S-NaOH", 135.6, role="feed",
                                 src_port="salida", dst_port="alimentacion_2",
                                 price=400.0, T=25,
                                 main_component="sodium_hydroxide", phase="liquid",
                                 composition={"sodium_hydroxide": 1.0})
        # Mezcla al reactor
        self._add_example_stream(m101, r101, "S-mix", 0.0,
                                 src_port="producto", dst_port="alimentacion",
                                 T=70,
                                 composition=feed_mix,
                                 main_component="vegetable_oil", phase="liquid")
        # Salida reactor a decanter
        self._add_example_stream(r101, v101, "S-rxn", 0.0,
                                 src_port="producto", dst_port="alimentacion",
                                 T=80,
                                 composition=rxn_out,
                                 main_component="soap", phase="liquid")
        # Jabón (fase superior, en realidad sólido pero declarado liquid
        # para flow conservation; el motor no maneja fase sólida explícita)
        self._add_example_stream(v101, tk_soap, "S-soap", 0.0, role="product",
                                 src_port="vapor", dst_port="entrada",
                                 price=1800.0, T=80,
                                 main_component="soap", phase="liquid",
                                 composition={"soap": 1.0})
        # Glicerina (fondo) — subproducto vendible
        self._add_example_stream(v101, tk_gly, "S-glycerin", 104.0, role="product",
                                 src_port="liquido", dst_port="entrada",
                                 price=800.0, T=80,
                                 main_component="glycerin", phase="liquid",
                                 composition={"glycerin": 1.0})

        self._set_example_labor(120_000)
        self._add_example_extra("Sal de salado / lavado",
                                flowrate=15.0, price=80.0,
                                stream="Consumables")

        from flowsheet_solver import auto_set_duties_from_thermo
        auto_set_duties_from_thermo(self.fs)


    def _example_urea(self):
        """TIER 1 — Urea por proceso Bosch-Meiser.

        Química (R031 placeholder Modo B):
            2 NH3(g) + 1 CO2(g) → 1 urea(l) + 1 H2O(l)
            ΔH ≈ −101 kJ/mol_urea (vía carbamato; exotérmica neta).
            T ≈ 180–200 °C, P ≈ 150 bar.  Conv por paso ~50–60 %
            (limitada por equilibrio del carbamato); aquí se asume
            conversión global ~95 % con purga simple (en planta
            real hay reciclo de carbamato a alta presión).

        Topología:
            TK-NH3 + TK-CO2 → M-101 → K-101 (compresor 150 bar) →
            R-101 → V-101 (flash purga NH3+CO2) → T-101 (evaporador
            separa urea del H2O) → TK-urea + TK-H2O waste

        Basis 1000 tm/año NH3 + 1292 CO2 → 1675 urea + 502 H2O.
        Purga (5 % no reacciona): 50 NH3 + 64.6 CO2 = 114.6 t/y waste.
        """
        tk_nh3  = self._add_example_block("TK-101", "Storage tank — cone roof", 200.0,  60, 200)
        tk_co2  = self._add_example_block("TK-102", "Storage tank — cone roof", 250.0,  60, 400)
        m101    = self._add_example_block("M-101",  "Mixer — static",            2.0, 260, 300)
        k101    = self._add_example_block("K-101",  "Compressor — centrifugal", 600.0, 460, 300)
        r101    = self._add_example_block("R-101",  "Reactor — autoclave",       12.0, 660, 300)
        v101    = self._add_example_block("V-101",  "Vessel — vertical",         18.0, 860, 300)
        tk_purg = self._add_example_block("TK-103", "Storage tank — cone roof", 100.0, 860, 100)
        t101    = self._add_example_block("EV-101", "Evaporator — vertical",     30.0,1060, 380)
        tk_h2o  = self._add_example_block("TK-104", "Storage tank — cone roof", 100.0,1060, 200)
        tk_urea = self._add_example_block("TK-105", "Storage tank — cone roof", 300.0,1260, 380)

        # R-101 — Modo B con R031 placeholder
        self.fs.blocks[r101].reactions = ["R031_PLACEHOLDER"]
        self.fs.blocks[r101].T_op_K    = 458.0
        self.fs.blocks[r101].P_op_bar  = 150.0
        # ΔH = -101 kJ/mol_urea × 1675e3/60.06 mol/y = -2817 GJ/y
        # = -89.4 kW.  Por kg input (2292 t/y): -1229 kJ/kg.
        self.fs.blocks[r101].heat_of_reaction = -1229.0

        # Composiciones (thermo_db keys: ammonia, co2, urea, water)
        feed_mix  = {"ammonia": 0.436, "co2": 0.564}      # 1000 + 1292 = 2292
        # Salida R-101: 50 NH3 + 64.6 CO2 + 1675 urea + 502 H2O = 2291.6
        rxn_out   = {"ammonia": 0.0218, "co2": 0.0282,
                     "urea": 0.7311, "water": 0.2191}
        # Líquido del V-101: 1675 urea + 502 H2O = 2177
        liq_mix   = {"urea": 0.7694, "water": 0.2306}

        # NH3 feed (gas → líquido a alta P)
        self._add_example_stream(tk_nh3, m101, "S-NH3", 1000, role="feed",
                                 src_port="salida", dst_port="alimentacion_1",
                                 price=350.0, T=25,
                                 main_component="ammonia", phase="liquid",
                                 composition={"ammonia": 1.0})
        # CO2 feed
        self._add_example_stream(tk_co2, m101, "S-CO2", 1292, role="feed",
                                 src_port="salida", dst_port="alimentacion_2",
                                 price=50.0, T=25,
                                 main_component="co2", phase="gas",
                                 composition={"co2": 1.0})
        # Mezcla → compresor
        self._add_example_stream(m101, k101, "S-mix", 0.0,
                                 src_port="producto", dst_port="succion",
                                 T=40,
                                 composition=feed_mix,
                                 main_component="co2", phase="gas")
        # Comprimida → reactor
        self._add_example_stream(k101, r101, "S-HP", 0.0,
                                 src_port="descarga", dst_port="alimentacion",
                                 T=180,
                                 composition=feed_mix,
                                 main_component="co2", phase="liquid", lock_T=False)
        # Salida reactor a flash (Modo B)
        self._add_example_stream(r101, v101, "S-rxn", 0.0,
                                 src_port="producto", dst_port="alimentacion",
                                 T=190,
                                 composition=rxn_out,
                                 main_component="urea", phase="liquid")
        # Purga vapor (NH3 + CO2 no reaccionados, ~114.6 t/y)
        self._add_example_stream(v101, tk_purg, "S-purga", 114.6, role="waste",
                                 src_port="vapor", dst_port="entrada",
                                 price=0.0, T=190,
                                 composition={"ammonia": 0.436, "co2": 0.564},
                                 main_component="co2", phase="gas")
        # Líquido al evaporador (urea + H2O)
        self._add_example_stream(v101, t101, "S-liq", 0.0,
                                 src_port="liquido", dst_port="alimentacion",
                                 T=150,
                                 composition=liq_mix,
                                 main_component="urea", phase="liquid")
        # Agua evaporada (subproducto / waste)
        self._add_example_stream(t101, tk_h2o, "S-H2O", 502, role="waste",
                                 src_port="venteo", dst_port="entrada",
                                 price=0.0, T=110,
                                 main_component="water", phase="vapor",
                                 composition={"water": 1.0})
        # Urea concentrada / prill (producto final)
        self._add_example_stream(t101, tk_urea, "S-urea", 0.0, role="product",
                                 src_port="producto", dst_port="entrada",
                                 price=550.0, T=130,
                                 main_component="urea", phase="liquid",
                                 composition={"urea": 1.0})

        self._set_example_labor(200_000)
        self._add_example_extra("Energía eléctrica (compresores)",
                                flowrate=480000, price=0.08,
                                stream="Utilities")
        self._add_example_extra("Inhibidor de corrosión",
                                flowrate=8.0, price=5_000.0,
                                stream="Consumables")

        from flowsheet_solver import auto_set_duties_from_thermo
        auto_set_duties_from_thermo(self.fs)


    # ==================================================================
    # Lote 4c — Leche Gloria (Tier 1, planta láctea integrada)
    # ==================================================================

    def _example_leche_gloria(self):
        """TIER 1 — Planta láctea integrada estilo Gloria S.A.

        ⏱ PROCESO MIXTO continuo + sub-pasos batch (churning,
        maduración).  Se modela como flujo continuo en estado
        estacionario usando el caudal promedio anual.  El balance
        de masa y energía es correcto; NO se modela dinámica
        temporal de los sub-pasos batch.

        Tres ramas de producto desde una sola leche cruda:
          1) Leche fluida pasteurizada y homogeneizada
          2) Mantequilla + buttermilk (rama de la crema)
          3) Leche evaporada en lata (producto estrella) — tren
             de evaporadores AL VACÍO (~50 °C, NO 100 °C)

        Sin reacciones químicas: TODAS las operaciones son físicas
        (separación, calentamiento, evaporación, churning).  Modo B
        con composiciones declaradas en TODOS los outlets (patrón
        QUIMPAC).

        Componentes (4 pseudo lácteos + agua):
            water, milk_fat, milk_protein, lactose, milk_ash

        Basis 10,000 tm/año leche cruda:
            water 8760, milk_fat 370, milk_protein 330,
            lactose 470, milk_ash 70

        Trampas (§8 del dossier — requisitos de aceptación):
          a) NO tratar leche como agua pura (4 pseudos separados)
          b) Separadora = Modo B Vessel por composición
          c) Churning = Modo B con balance impuesto
          d) Evaporador AL VACÍO (~50 °C)
          e) Regeneración térmica en pasteurizador (2 HX acoplados)
          f) Homogenizador NO es reactor (Pump, composición intacta)

        Balance global validado (mass=0, eng=0).
        """
        # ============ Layout: 4 filas, layout 1.8× extendido ============
        # Fila 1 (y=200): recepción + pretrat + separación
        tk_in   = self._add_example_block("TK-001", "Storage tank — cone roof", 800.0,  60, 200)
        clar    = self._add_example_block("CLAR-101","Vessel — vertical",        20.0, 240, 200)
        e101    = self._add_example_block("E-101", "Heat exch. — floating head", 80.0, 420, 200)
        sep     = self._add_example_block("SEP-101","Centrifuge — disc stack",  2.5, 600, 200)
        tk_clw  = self._add_example_block("TK-002","Storage tank — cone roof",   90.0, 240, 380)  # waste clar

        # Fila 2 (y=420): RAMA FLUIDA  (descremada → estandariza → past → homog)
        m_std   = self._add_example_block("M-101", "Mixer — static",             2.0, 800, 420)
        e102    = self._add_example_block("E-102", "Heat exch. — floating head", 60.0, 980, 420)
        p_hom   = self._add_example_block("P-101", "Pump — positive displacement", 25.0,1180, 420)
        e103    = self._add_example_block("E-103", "Heat exch. — floating head", 60.0,1380, 420)
        tk_flu  = self._add_example_block("TK-003","Storage tank — cone roof",  200.0,1580, 420)

        # Fila 3 (y=640): RAMA MANTEQUILLA  (crema → pasteur crema → maduración → churning)
        e104    = self._add_example_block("E-104", "Heat exch. — floating head", 30.0, 800, 640)
        e105    = self._add_example_block("E-105", "Heat exch. — floating head", 30.0, 980, 640)
        churn   = self._add_example_block("CHURN-101","Vessel — vertical",       40.0,1180, 640)
        tk_btr  = self._add_example_block("TK-004","Storage tank — cone roof",  100.0,1380, 580)
        tk_bml  = self._add_example_block("TK-005","Storage tank — cone roof",  100.0,1380, 740)

        # Fila 4 (y=860): RAMA EVAPORADA  (descremada → EV1+EV2 vacío → UHT → lata)
        ev1     = self._add_example_block("EV-101","Evaporator — vertical",     150.0, 800, 860)
        ev2     = self._add_example_block("EV-102","Evaporator — vertical",     120.0,1000, 860)
        tk_vap  = self._add_example_block("TK-006","Storage tank — cone roof",  200.0, 900,1040)  # vapor (utility)
        e_uht   = self._add_example_block("E-106", "Heat exch. — floating head", 50.0,1200, 860)
        tk_evp  = self._add_example_block("TK-007","Storage tank — cone roof",  500.0,1400, 860)

        # ============ COMPOSICIONES (mass fractions, suman 1.0) ============
        leche_cruda = {"water": 0.876, "milk_fat": 0.037,
                       "milk_protein": 0.033, "lactose": 0.047,
                       "milk_ash": 0.007}
        # Clarificada (igual composición, 0.2 % menos)
        clarified   = leche_cruda
        # Crema 40 % grasa
        crema       = {"water": 0.5904, "milk_fat": 0.400,
                       "milk_protein": 0.0055, "lactose": 0.0044,
                       "milk_ash": 0.0}
        # Descremada 0.05 % grasa
        descrem     = {"water": 0.9047, "milk_fat": 0.0005,
                       "milk_protein": 0.0358, "lactose": 0.0513,
                       "milk_ash": 0.0077}
        # Leche fluida estandarizada (3 % grasa)
        fluida      = {"water": 0.881, "milk_fat": 0.030,
                       "milk_protein": 0.034, "lactose": 0.048,
                       "milk_ash": 0.007}
        # Mantequilla (82 % grasa)
        manteq      = {"water": 0.165, "milk_fat": 0.820,
                       "milk_protein": 0.010, "lactose": 0.005,
                       "milk_ash": 0.0}
        # Buttermilk (residuo del churning, mostly water)
        buttermilk  = {"water": 0.986, "milk_fat": 0.009,
                       "milk_protein": 0.001, "lactose": 0.004,
                       "milk_ash": 0.0}
        # Concentrada intermedia (entre EV1 y EV2, ST ~15.4 %) —
        # SOLO se evapora agua: protein/lactose/ash/fat conservan masa
        # exacto desde la descremada (8048 t/y).  Frac recalculadas
        # exactas para evitar drift de componentes individuales.
        mid_evap    = {"water": 0.8463, "milk_fat": 0.0008,
                       "milk_protein": 0.0578, "lactose": 0.0828,
                       "milk_ash": 0.0124}
        # Leche evaporada final (ST 26 %) — masa conservada exacto
        leche_evap  = {"water": 0.7400, "milk_fat": 0.0014,
                       "milk_protein": 0.0977, "lactose": 0.1400,
                       "milk_ash": 0.0210}

        # ============ STREAMS ============
        # 1) Cruda → Clarificadora
        self._add_example_stream(tk_in, clar, "S-cruda", 10000, role="feed",
                                 src_port="salida", dst_port="alimentacion",
                                 price=600.0, T=4,
                                 composition=leche_cruda,
                                 main_component="water", phase="liquid")
        # 2) Clarif waste (0.2 % = 20 t/y de sólidos extraños)
        self._add_example_stream(clar, tk_clw, "S-clarif-waste", 20, role="waste",
                                 src_port="vapor", dst_port="entrada",
                                 price=0.0, T=4,
                                 composition=leche_cruda,
                                 main_component="water", phase="liquid")
        # 3) Clarif → Precalentador (9980 t/y)
        self._add_example_stream(clar, e101, "S-clar", 0.0,
                                 src_port="liquido", dst_port="tube_in",
                                 T=4,
                                 composition=clarified,
                                 main_component="water", phase="liquid")
        # 4) Precalentada (40 °C) → Separadora
        self._add_example_stream(e101, sep, "S-precal", 0.0,
                                 src_port="tube_out", dst_port="alimentacion",
                                 T=40,
                                 composition=clarified,
                                 main_component="water", phase="liquid")

        # ============ SALIDAS SEPARADORA ============
        # Crema (913 t/y, 40 % grasa) — port "solido"
        # Descremada (9067 t/y, 0.05 % grasa) — port "liquido"
        # Crema split: 81 a fluida estandarización, 832 a manteq rama
        # Descrem split: 1019 a fluida, 8048 a evaporada
        # Stream-level split: 4 streams desde SEP-101
        self._add_example_stream(sep, m_std, "S-crema-fluida", 81,
                                 src_port="solido", dst_port="alimentacion_1",
                                 T=40,
                                 composition=crema,
                                 main_component="milk_fat", phase="liquid")
        self._add_example_stream(sep, e104, "S-crema-manteq", 832,
                                 src_port="solido", dst_port="tube_in",
                                 T=40,
                                 composition=crema,
                                 main_component="milk_fat", phase="liquid")
        self._add_example_stream(sep, m_std, "S-desc-fluida", 1019,
                                 src_port="liquido", dst_port="alimentacion_2",
                                 T=40,
                                 composition=descrem,
                                 main_component="water", phase="liquid")
        self._add_example_stream(sep, ev1, "S-desc-evap", 0.0,
                                 src_port="liquido", dst_port="alimentacion",
                                 T=40,
                                 composition=descrem,
                                 main_component="water", phase="liquid")

        # ============ RAMA FLUIDA (1100 t/y at 3 % fat) ============
        # M-101 estandariza (81 crema + 1019 descrem = 1100)
        self._add_example_stream(m_std, e102, "S-std", 0.0,
                                 src_port="producto", dst_port="tube_in",
                                 T=40,
                                 composition=fluida,
                                 main_component="water", phase="liquid")
        # Pasteurizador HTST (40 → 72 °C) + regenerativo implícito en E-103
        self._add_example_stream(e102, p_hom, "S-past", 0.0,
                                 src_port="tube_out", dst_port="succion",
                                 T=72,
                                 composition=fluida,
                                 main_component="water", phase="liquid")
        # Homogenizador (sube P a ~150 bar; composición intacta — TRAMPA f)
        self._add_example_stream(p_hom, e103, "S-homog", 0.0,
                                 src_port="descarga", dst_port="tube_in",
                                 T=72,
                                 composition=fluida,
                                 main_component="water", phase="liquid")
        # Enfriador → TK leche fluida (regeneración 90 % captura calor, 4 °C final)
        self._add_example_stream(e103, tk_flu, "S-fluida", 0.0, role="product",
                                 src_port="tube_out", dst_port="entrada",
                                 price=900.0, T=4,
                                 composition=fluida,
                                 main_component="water", phase="liquid")

        # ============ RAMA MANTEQUILLA (832 crema → 401 manteq + 431 buttermilk) ============
        # Pasteur crema 40 → 85 °C
        self._add_example_stream(e104, e105, "S-crema-past", 0.0,
                                 src_port="tube_out", dst_port="tube_in",
                                 T=85,
                                 composition=crema,
                                 main_component="milk_fat", phase="liquid")
        # Maduración 85 → 12 °C (Cooler)
        self._add_example_stream(e105, churn, "S-crema-mad", 0.0,
                                 src_port="tube_out", dst_port="alimentacion",
                                 T=12,
                                 composition=crema,
                                 main_component="milk_fat", phase="liquid")
        # Churning (Modo B): 401 mantequilla por "vapor" + 431 buttermilk por "liquido"
        self._add_example_stream(churn, tk_btr, "S-manteq", 401, role="product",
                                 src_port="vapor", dst_port="entrada",
                                 price=4500.0, T=14,
                                 composition=manteq,
                                 main_component="milk_fat", phase="liquid")
        self._add_example_stream(churn, tk_bml, "S-buttermilk", 0.0, role="product",
                                 src_port="liquido", dst_port="entrada",
                                 price=200.0, T=14,
                                 composition=buttermilk,
                                 main_component="water", phase="liquid")

        # ============ RAMA EVAPORADA (8048 → 2950 evap + 5098 vapor) ============
        # Balance: ST=767 t/y conserva.  Reparto vapor: EV1 quita 60 % = 3059,
        # EV2 quita 40 % = 2039.  Total: 8048-5098=2950 (evap final).
        # Intermedio EV1→EV2: 8048-3059 = 4989 t/y at ~15 % ST.
        # Vapor EV1: 3059 t/y water, EV2: 2039 t/y water.  Ambos a TK-vap.
        # EV1 vapor → TK-vap
        self._add_example_stream(ev1, tk_vap, "S-vap-1", 3059, role="utility",
                                 src_port="venteo", dst_port="entrada",
                                 price=0.0, T=55,
                                 main_component="water", phase="vapor",
                                 composition={"water": 1.0})
        # EV1 → EV2 (concentrado intermedio)
        self._add_example_stream(ev1, ev2, "S-mid", 0.0,
                                 src_port="producto", dst_port="alimentacion",
                                 T=50,
                                 composition=mid_evap,
                                 main_component="water", phase="liquid")
        # EV2 vapor → TK-vap
        self._add_example_stream(ev2, tk_vap, "S-vap-2", 2039, role="utility",
                                 src_port="venteo", dst_port="entrada",
                                 price=0.0, T=50,
                                 main_component="water", phase="vapor",
                                 composition={"water": 1.0})
        # EV2 → UHT (2950 t/y at 26 % ST)
        self._add_example_stream(ev2, e_uht, "S-conc", 0.0,
                                 src_port="producto", dst_port="tube_in",
                                 T=50,
                                 composition=leche_evap,
                                 main_component="water", phase="liquid")
        # UHT (115 °C) → TK leche evaporada en lata
        self._add_example_stream(e_uht, tk_evp, "S-evap", 0.0, role="product",
                                 src_port="tube_out", dst_port="entrada",
                                 price=1100.0, T=25,
                                 composition=leche_evap,
                                 main_component="water", phase="liquid")

        # ============ OPEX ============
        self._set_example_labor(250_000)
        self._add_example_extra("Vapor de servicio (calderas)",
                                flowrate=1_500_000, price=15.0,
                                stream="Utilities")
        self._add_example_extra("Energía eléctrica (homog + bombas + frío)",
                                flowrate=900_000, price=0.08,
                                stream="Utilities")
        self._add_example_extra("Soluciones de limpieza CIP",
                                flowrate=20.0, price=400.0,
                                stream="Consumables")

        from flowsheet_solver import auto_set_duties_from_thermo
        auto_set_duties_from_thermo(self.fs)


    # ==================================================================
    # Lote 5 — Industrias adicionales (Tier 1, variedad de régimen)
    # ==================================================================

    def _example_ethylene_cracking(self):
        """TIER 1 — Etileno por cracking térmico de etano + separación.

        Petroquímica fundamental.  Reacción R011 ya en DB
        (derivable Capa 3): C2H6(g) → C2H4(g) + H2(g).  Modo A
        equilibrium a T=1100 K / P=2 bar → conv ~53 %.

        Diferencia con `_example_ethane_cracker_pfr`: este ejemplo
        agrega el TREN DE SEPARACIÓN downstream (compresor + columna
        fría) para separar productos finales — más cerca del PFD
        industrial completo.

        Topología:
            TK-etano → E-101 (precal) → F-101 (horno pirólisis, Modo A
            R011 equilibrium) → E-102 (quench) → K-101 (compresor) →
            T-101 (cold column criogénica) → TK-etileno (vapor_tope)
                                            + TK-offgas (liquido_fondo)

        Basis 1000 tm/año etano.  Conversión equilibrio ~53 % →
        ~470 t/y etileno + ~34 t/y H₂ + 496 t/y etano sin reaccionar.
        """
        tk_in   = self._add_example_block("TK-101", "Storage tank — cone roof", 200.0,  60, 260)
        e101    = self._add_example_block("E-101", "Heat exch. — floating head", 100.0, 240, 260)
        f101    = self._add_example_block("F-101", "Fired heater — non-reformer", 4000.0, 420, 260)
        r101    = self._add_example_block("R-101", "Reactor — jacketed non-agit.", 35.0, 600, 260)
        e102    = self._add_example_block("E-102", "Heat exch. — air cooler",   200.0, 780, 260)
        k101    = self._add_example_block("K-101", "Compressor — centrifugal", 600.0, 960, 260)
        t101    = self._add_example_block("T-101", "Tower (column shell)",      35.0,1140, 380)
        tk_eth  = self._add_example_block("TK-102","Storage tank — cone roof", 200.0,1340, 200)
        tk_off  = self._add_example_block("TK-103","Storage tank — cone roof", 100.0,1340, 540)

        # R-101 Modo A real: R011 (derivable, equilibrium converge)
        self.fs.blocks[r101].reactions   = ["R011"]
        self.fs.blocks[r101].T_op_K      = 1100.0
        self.fs.blocks[r101].P_op_bar    = 2.0

        # Feed etano (1000 t/y puro)
        self._add_example_stream(tk_in, e101, "S-etano", 1000, role="feed",
                                 src_port="salida", dst_port="tube_in",
                                 price=550.0, T=25,
                                 main_component="ethane", phase="gas",
                                 composition={"ethane": 1.0})
        # Precalentado al horno (intermedio: masa propagada; comp ethano puro
        # locked porque alimenta el reactor que la necesita para el equilibrio)
        self._add_example_stream(e101, f101, "S-precal", 0.0,
                                 src_port="tube_out", dst_port="proceso_in",
                                 T=400,
                                 main_component="ethane", phase="gas",
                                 composition={"ethane": 1.0})
        # Post-horno (~700 °C, entrada al reactor)
        self._add_example_stream(f101, r101, "S-hot", 0.0,
                                 src_port="proceso_out", dst_port="alimentacion",
                                 T=700,
                                 main_component="ethane", phase="gas",
                                 composition={"ethane": 1.0})
        # Salida reactor — solver Modo A calcula composición (no la declaramos)
        self._add_example_stream(r101, e102, "S-cracked",
                                 src_port="producto", dst_port="proceso_in",
                                 T=827,
                                 main_component="ethylene", phase="gas")
        # Quench al compresor
        self._add_example_stream(e102, k101, "S-quench",
                                 src_port="proceso_out", dst_port="succion",
                                 T=40,
                                 main_component="ethylene", phase="gas")
        # Comprimido a columna fría
        self._add_example_stream(k101, t101, "S-comp",
                                 src_port="descarga", dst_port="alimentacion",
                                 T=80,
                                 main_component="ethylene", phase="gas")
        # Tope: etileno purificado (composición tope criogénica declarada)
        self._add_example_stream(t101, tk_eth, "S-etileno", 470, role="product",
                                 src_port="vapor_tope", dst_port="entrada",
                                 price=950.0, T=-30,
                                 main_component="ethylene", phase="gas",
                                 composition={"ethylene": 0.985, "hydrogen": 0.015})
        # Fondo: etano + offgas (fuel-gas).  Masa deducida del balance de
        # T-101 (Σin − S-etileno); comp es spec de separación (locked).
        self._add_example_stream(t101, tk_off, "S-offgas", 0.0, role="product",
                                 src_port="liquido_fondo", dst_port="entrada",
                                 price=300.0, T=-50,
                                 main_component="ethane", phase="liquid",
                                 composition={"ethane": 0.92, "hydrogen": 0.06,
                                              "ethylene": 0.02})

        self._set_example_labor(200_000)
        self._add_example_extra("Gas natural (horno F-101)",
                                flowrate=240, price=180.0,
                                stream="Utilities")
        from flowsheet_solver import auto_set_duties_from_thermo
        auto_set_duties_from_thermo(self.fs)


    def _example_air_separation(self):
        """TIER 1 — Separación criogénica de aire (O₂/N₂).

        Gases industriales.  SIN reacción — separación física pura
        por destilación criogénica.  Didáctica para mostrar columna
        de destilación en condiciones extremas (~−180 °C).

        Topología:
            TK-aire → K-101 (compresor multietapa) → E-101 (cooler
            + purificación H2O/CO2 → Modo B simple) → E-102 (caja
            fría a −180 °C) → T-101 (columna criogénica) → TK-N2
            (tope, lighter component) + TK-O2 (fondo, heavier)

        Basis 1000 tm/año aire (composición real, fracciones másicas):
            N₂ 0.767, O₂ 0.233.  Trazas H₂O/CO₂ removidas como waste.

        Salidas:
            N₂ líquido 99.9 %: 765 t/y
            O₂ líquido 99.5 %: 230 t/y
            Waste (H₂O/CO₂):     5 t/y
        """
        tk_in   = self._add_example_block("TK-101", "Storage tank — cone roof", 300.0,  60, 280)
        k101    = self._add_example_block("K-101", "Compressor — centrifugal", 800.0, 240, 280)
        e101    = self._add_example_block("E-101", "Heat exch. — floating head", 150.0, 420, 280)
        purif   = self._add_example_block("V-101", "Vessel — vertical",          30.0, 600, 280)
        e102    = self._add_example_block("E-102", "Heat exch. — floating head", 250.0, 780, 280)
        t101    = self._add_example_block("T-101", "Tower (column shell)",       50.0, 960, 400)
        tk_n2   = self._add_example_block("TK-102","Storage tank — cone roof", 250.0,1160, 220)
        tk_o2   = self._add_example_block("TK-103","Storage tank — cone roof", 100.0,1160, 580)
        tk_wst  = self._add_example_block("TK-W",  "Storage tank — cone roof",  90.0, 600, 480)

        # Feed aire (1000 t/y, composición másica real)
        air_comp = {"nitrogen": 0.767, "oxygen": 0.233}
        # Sólo N2/O2 en el aire feed; el waste tiene trazas H2O+CO2 abstraídas
        # como pseudo-mix.
        self._add_example_stream(tk_in, k101, "S-aire", 1000, role="feed",
                                 src_port="salida", dst_port="succion",
                                 price=0.0, T=25,
                                 main_component="nitrogen", phase="gas",
                                 composition=air_comp)
        # Aire comprimido
        self._add_example_stream(k101, e101, "S-HP", 0.0,
                                 src_port="descarga", dst_port="tube_in",
                                 T=120,
                                 composition=air_comp,
                                 main_component="nitrogen", phase="gas")
        # Aire enfriado
        self._add_example_stream(e101, purif, "S-cool", 0.0,
                                 src_port="tube_out", dst_port="alimentacion",
                                 T=25,
                                 composition=air_comp,
                                 main_component="nitrogen", phase="gas")
        # Purif waste (trazas H2O+CO2 abstraídas, 5 t/y)
        self._add_example_stream(purif, tk_wst, "S-purif-waste", 5, role="waste",
                                 src_port="vapor", dst_port="entrada",
                                 price=0.0, T=25,
                                 main_component="water", phase="liquid",
                                 composition={"water": 1.0})
        # Aire purificado a caja fría
        self._add_example_stream(purif, e102, "S-pure", 0.0,
                                 src_port="liquido", dst_port="tube_in",
                                 T=25,
                                 composition=air_comp,
                                 main_component="nitrogen", phase="gas")
        # Aire criogénico a columna
        self._add_example_stream(e102, t101, "S-cryo", 0.0,
                                 src_port="tube_out", dst_port="alimentacion",
                                 T=-95,
                                 composition=air_comp,
                                 main_component="nitrogen", phase="liquid")
        # Tope: N2 ultra-puro (líquido criogénico)
        self._add_example_stream(t101, tk_n2, "S-N2", 0.0, role="product",
                                 src_port="vapor_tope", dst_port="entrada",
                                 price=120.0, T=-95,
                                 main_component="nitrogen", phase="liquid",
                                 composition={"nitrogen": 0.999, "oxygen": 0.001})
        # Fondo: O2 99.5 %
        self._add_example_stream(t101, tk_o2, "S-O2", 230, role="product",
                                 src_port="liquido_fondo", dst_port="entrada",
                                 price=180.0, T=-90,
                                 main_component="oxygen", phase="liquid",
                                 composition={"oxygen": 0.995, "nitrogen": 0.005})

        self._set_example_labor(160_000)
        self._add_example_extra("Energía eléctrica (compresores multietapa)",
                                flowrate=480_000, price=0.08,
                                stream="Utilities")
        from flowsheet_solver import auto_set_duties_from_thermo
        auto_set_duties_from_thermo(self.fs)


    def _example_water_treatment(self):
        """TIER 1 — Planta de tratamiento de agua potable.

        Servicios / ambiental.  SIN reacción de DB — operaciones
        físicas Modo B (coagulación-floculación-sedimentación-
        filtración-desinfección).  Relevante para todo ingeniero
        y bajo riesgo de validación.

        Topología:
            TK-cruda → M-101 (dosifica coag) → R-101 (floculador) →
            V-101 (sedimentador, separa lodos) → F-101 (filtro) →
            M-102 (cloración) → TK-potable + TK-lodos

        Basis 1000 tm/año agua cruda {water 0.998, raw_water_solids
        0.002}.  Lodos: 2 t/y (raw_water_solids concentrado + algo
        de agua).  Potable: 998 t/y agua pura.
        """
        tk_in   = self._add_example_block("TK-101", "Storage tank — cone roof", 300.0,  60, 240)
        m101    = self._add_example_block("M-101", "Mixer — static",            2.0, 240, 240)
        r101    = self._add_example_block("R-101", "Reactor — jacketed agitated", 30.0, 420, 240)
        v101    = self._add_example_block("V-101", "Vessel — vertical",          50.0, 600, 240)
        f101    = self._add_example_block("F-101", "Filter — belt",              40.0, 780, 240)
        m102    = self._add_example_block("M-102", "Mixer — static",            2.0, 960, 240)
        tk_pot  = self._add_example_block("TK-102","Storage tank — cone roof", 300.0,1140, 240)
        tk_lod  = self._add_example_block("TK-103","Storage tank — cone roof",  90.0, 600, 440)

        # Marcar como sin reacciones (operaciones físicas)
        self.fs.blocks[r101].reactions = ["R_FLOCULACION"]

        # Composiciones
        cruda     = {"water": 0.998, "raw_water_solids": 0.002}
        lodos     = {"water": 0.50,  "raw_water_solids": 0.50}     # lodos 50/50
        agua_clar = {"water": 1.0}
        potable   = {"water": 1.0}    # cloro trazas, no se modela

        # Cruda → dosificador (feed: mass/comp/T locked)
        self._add_example_stream(tk_in, m101, "S-cruda", 1000, role="feed",
                                 src_port="salida", dst_port="alimentacion_1",
                                 price=0.0, T=15,
                                 composition=cruda,
                                 main_component="water", phase="liquid")
        # M-101 → R-101 (floculador) — passthrough: mass y comp propagados
        self._add_example_stream(m101, r101, "S-coag", 0.0,
                                 src_port="producto", dst_port="alimentacion",
                                 T=15, phase="liquid")
        # R-101 → V-101 (sedimentador).  R-101 lleva reacción placeholder,
        # así que auto_propagate la salta → comp queda como spec (locked);
        # solo la masa se propaga.
        self._add_example_stream(r101, v101, "S-floc", 0.0,
                                 src_port="producto", dst_port="alimentacion",
                                 T=15,
                                 composition=cruda,
                                 main_component="water", phase="liquid")
        # V-101: separa 1000 → S-lodos (spec del separador, locked) +
        # S-clar (masa deducida 996; comp es resultado de separación, locked).
        self._add_example_stream(v101, tk_lod, "S-lodos", 4, role="waste",
                                 src_port="liquido", dst_port="entrada",
                                 price=0.0, T=15,
                                 composition=lodos,
                                 main_component="raw_water_solids", phase="liquid")
        self._add_example_stream(v101, f101, "S-clar", 0.0,
                                 src_port="vapor", dst_port="alimentacion",
                                 T=15,
                                 composition=agua_clar,
                                 main_component="water", phase="liquid")
        # F-101 → M-102 (cloración) — comp de separación (locked), masa deducida
        self._add_example_stream(f101, m102, "S-fil", 0.0,
                                 src_port="producto", dst_port="alimentacion_1",
                                 T=15,
                                 composition=agua_clar,
                                 main_component="water", phase="liquid")
        # M-102 → TK potable (producto: comp spec locked, masa calculada)
        self._add_example_stream(m102, tk_pot, "S-potable", 0.0, role="product",
                                 src_port="producto", dst_port="entrada",
                                 price=0.5, T=15,
                                 composition=potable,
                                 main_component="water", phase="liquid")

        self._set_example_labor(120_000)
        self._add_example_extra("Sulfato de aluminio (coagulante)",
                                flowrate=2.0, price=300.0,
                                stream="Consumables")
        self._add_example_extra("Cloro (desinfección)",
                                flowrate=0.5, price=400.0,
                                stream="Consumables")
        self._add_example_extra("Energía eléctrica (bombas)",
                                flowrate=80_000, price=0.08,
                                stream="Utilities")
        from flowsheet_solver import auto_set_duties_from_thermo
        auto_set_duties_from_thermo(self.fs)


    def _example_bread_baking(self):
        """TIER 1 — Panificación industrial.

        ⏱ PROCESO BATCH MODELADO COMO CONTINUO EQUIVALENTE: amasado,
        fermentación y horneado son batch en la industria.  Aquí se
        modela como flujo continuo en estado estacionario usando el
        caudal promedio anual (producción/8760 h).  El balance de
        masa y energía es correcto; NO se modela la dinámica
        temporal del lote.

        Sin reacción química explícita — la fermentación es trivial
        (~2 % de azúcar a CO2+EtOH, ambos casi totalmente evaporados
        en el horno → se abstrae para mantener foco en el balance
        energético del horneado, que domina).

        Topología:
            TK-masa → M-101 (amasadora) → R-101 (fermentador
            placeholder) → H-101 (horno 220 °C, evapora 12 % agua)
            → E-101 (enfriador) → TK-pan

        Basis 1000 tm/año masa cruda {starch 0.45, water 0.50,
        glucose 0.05}.  En el horno se evapora 120 t/y agua → pan
        880 t/y at {starch 0.51, water 0.43, glucose 0.057}.
        """
        tk_in   = self._add_example_block("TK-101", "Storage tank — cone roof", 200.0,  60, 280)
        m101    = self._add_example_block("M-101", "Mixer — static",            2.0, 240, 280)
        r101    = self._add_example_block("R-101", "Reactor — jacketed agitated", 30.0, 420, 280)
        h101    = self._add_example_block("H-101", "Heat exch. — floating head", 80.0, 600, 280)
        tk_vap  = self._add_example_block("TK-V",  "Storage tank — cone roof", 100.0, 600,  80)
        e101    = self._add_example_block("E-101", "Heat exch. — air cooler",   80.0, 780, 280)
        tk_pan  = self._add_example_block("TK-102","Storage tank — cone roof", 250.0, 960, 280)

        # R-101: fermentación placeholder (sin reacción real para mantener
        # el balance simple).  El alumno ve el bloque etiquetado como
        # fermentador pero composiciones de salida son ~iguales a entrada.
        self.fs.blocks[r101].reactions = ["R007_PLACEHOLDER"]
        self.fs.blocks[r101].T_op_K    = 305.0      # 32 °C leudado
        self.fs.blocks[r101].P_op_bar  = 1.0

        masa    = {"starch": 0.45, "water": 0.50, "glucose": 0.05}
        pan     = {"starch": 0.5114, "water": 0.4318, "glucose": 0.0568}

        # Masa cruda (feed: harina + agua + levadura abstraído)
        self._add_example_stream(tk_in, m101, "S-masa-cruda", 1000, role="feed",
                                 src_port="salida", dst_port="alimentacion_1",
                                 price=400.0, T=20,
                                 composition=masa,
                                 main_component="starch", phase="liquid")
        # Amasada → fermentador
        self._add_example_stream(m101, r101, "S-amasada", 0.0,
                                 src_port="producto", dst_port="alimentacion",
                                 T=25,
                                 composition=masa,
                                 main_component="starch", phase="liquid")
        # Leudada → horno (composición efectiva igual por simplificación
        # didáctica; la fermentación real produce trazas de CO2/EtOH)
        self._add_example_stream(r101, h101, "S-leudada", 0.0,
                                 src_port="producto", dst_port="tube_in",
                                 T=32,
                                 composition=masa,
                                 main_component="starch", phase="liquid")
        # Vapor de agua del horno (12 % de la masa, role=utility)
        self._add_example_stream(h101, tk_vap, "S-vapor", 120, role="utility",
                                 src_port="shell_out", dst_port="entrada",
                                 price=0.0, T=220,
                                 main_component="water", phase="vapor",
                                 composition={"water": 1.0})
        # Pan caliente al enfriador
        self._add_example_stream(h101, e101, "S-pan-cal", 0.0,
                                 src_port="tube_out", dst_port="proceso_in",
                                 T=220,
                                 composition=pan,
                                 main_component="starch", phase="liquid")
        # Pan enfriado al silo final
        self._add_example_stream(e101, tk_pan, "S-pan", 0.0, role="product",
                                 src_port="proceso_out", dst_port="entrada",
                                 price=2200.0, T=25,
                                 composition=pan,
                                 main_component="starch", phase="liquid")

        self._set_example_labor(140_000)
        self._add_example_extra("Levadura (S. cerevisiae)",
                                flowrate=15.0, price=2_500.0,
                                stream="Consumables")
        self._add_example_extra("Gas natural (horno H-101)",
                                flowrate=80, price=180.0,
                                stream="Utilities")
        from flowsheet_solver import auto_set_duties_from_thermo
        auto_set_duties_from_thermo(self.fs)


    def _example_penicillin(self):
        """TIER 1 — Penicilina por fermentación aeróbica.

        ⏱ PROCESO BATCH MODELADO COMO CONTINUO EQUIVALENTE: la
        fermentación de Penicillium chrysogenum dura 4–7 días por
        lote.  Aquí se modela como flujo continuo (producción/8760 h).

        Bioproceso: la biosíntesis enzimática de antibióticos NO es
        equilibrio termodinámico ni cinética simple — se modela
        Modo B con conversiones declaradas de literatura (cinética
        de Monod / Michaelis-Menten queda FUERA del alcance del
        motor).

        Topología:
            TK-medio → E-est (esterilizador 121 °C) → R-101
            (fermentador aireado Modo B) → V-101 (separa micelio
            sólido) → F-101 (extracción + secado abstraídos) →
            TK-penicilina (producto) + TK-biomasa (waste) +
            TK-residual + TK-CO2

        Basis 1000 tm/año medio cultivo {water 0.92, glucose 0.08}.
        Conversión global (literatura industrial):
            ~50 % glucosa → biomasa: 30 t/y biomass (micelio)
            ~5 % glucosa → antibiótico: 5 t/y penicillin (producto
                                              MUY caro, ~50,000 USD/t)
            resto a CO2 + agua de metabolismo: 5 t/y CO2 vent + agua
            in caldo
        """
        tk_med  = self._add_example_block("TK-101", "Storage tank — cone roof", 250.0,  60, 300)
        e_est   = self._add_example_block("E-EST",  "Heat exch. — floating head", 60.0, 240, 300)
        r101    = self._add_example_block("R-101",  "Reactor — jacketed agitated", 35.0, 420, 300)
        tk_co2  = self._add_example_block("TK-CO2", "Storage tank — cone roof",  90.0, 420,  80)
        v101    = self._add_example_block("V-101",  "Vessel — vertical",          40.0, 620, 300)
        tk_bio  = self._add_example_block("TK-102", "Storage tank — cone roof", 100.0, 620, 520)
        f101    = self._add_example_block("F-101",  "Filter — belt",              25.0, 820, 300)
        tk_pen  = self._add_example_block("TK-103", "Storage tank — cone roof",  90.0,1000, 240)
        tk_res  = self._add_example_block("TK-104", "Storage tank — cone roof", 150.0,1000, 380)

        # R-101: fermentador placeholder
        self.fs.blocks[r101].reactions = ["R_FERMENT_PEN"]
        self.fs.blocks[r101].T_op_K    = 297.0     # 24 °C
        self.fs.blocks[r101].P_op_bar  = 1.0

        # Composiciones
        medio    = {"water": 0.92, "glucose": 0.08}
        # Caldo R-101: 1000 in → 5 CO2 vent + 995 caldo (con biomass+pen+glucose+agua)
        # Caldo: 925 water + 35 glucose remaining + 30 biomass + 5 penicillin = 995
        caldo    = {"water": 0.9296, "glucose": 0.0352,
                    "biomass": 0.0302, "penicillin": 0.0050}
        # Liquido tras V-101 (sin biomass): 965 t
        # 925 water + 35 glucose + 5 penicillin = 965
        liquid   = {"water": 0.9585, "glucose": 0.0363, "penicillin": 0.0052}

        # Medio cultivo (feed)
        self._add_example_stream(tk_med, e_est, "S-medio", 1000, role="feed",
                                 src_port="salida", dst_port="tube_in",
                                 price=80.0, T=25,
                                 composition=medio,
                                 main_component="water", phase="liquid")
        # Esterilizado a 121 °C
        self._add_example_stream(e_est, r101, "S-est", 0.0,
                                 src_port="tube_out", dst_port="alimentacion",
                                 T=24,
                                 composition=medio,
                                 main_component="water", phase="liquid")
        # CO2 vent del fermentador (metabolismo)
        self._add_example_stream(r101, tk_co2, "S-CO2", 5, role="waste",
                                 src_port="util_out", dst_port="entrada",
                                 price=0.0, T=24,
                                 main_component="co2", phase="gas",
                                 composition={"co2": 1.0})
        # Caldo + biomasa al separador
        self._add_example_stream(r101, v101, "S-caldo", 0.0,
                                 src_port="producto", dst_port="alimentacion",
                                 T=24,
                                 composition=caldo,
                                 main_component="water", phase="liquid")
        # Biomasa sólida (micelio, waste / secado opcional)
        self._add_example_stream(v101, tk_bio, "S-biomass", 30, role="waste",
                                 src_port="liquido", dst_port="entrada",
                                 price=0.0, T=24,
                                 main_component="biomass", phase="liquid",
                                 composition={"biomass": 1.0})
        # Líquido a extracción
        self._add_example_stream(v101, f101, "S-liq", 0.0,
                                 src_port="vapor", dst_port="alimentacion",
                                 T=24,
                                 composition=liquid,
                                 main_component="water", phase="liquid")
        # Penicilina pura (producto)
        self._add_example_stream(f101, tk_pen, "S-pen", 5, role="product",
                                 src_port="producto", dst_port="entrada",
                                 price=50_000.0, T=25,
                                 main_component="penicillin", phase="liquid",
                                 composition={"penicillin": 1.0})
        # Caldo residual (waste)
        self._add_example_stream(f101, tk_res, "S-residual", 0.0, role="waste",
                                 src_port="venteo", dst_port="entrada",
                                 price=0.0, T=25,
                                 main_component="water", phase="liquid",
                                 composition={"water": 0.964, "glucose": 0.036})

        self._set_example_labor(300_000)
        self._add_example_extra("Aireación estéril (oxígeno + filtrado)",
                                flowrate=120, price=120.0,
                                stream="Utilities")
        self._add_example_extra("Solventes de extracción (acetato de butilo)",
                                flowrate=30, price=2_500.0,
                                stream="Consumables")
        self._add_example_extra("Energía eléctrica (agitación + frío)",
                                flowrate=200_000, price=0.08,
                                stream="Utilities")
        from flowsheet_solver import auto_set_duties_from_thermo
        auto_set_duties_from_thermo(self.fs)


    # ==================================================================
    # Lote 6 — Tier 2 ilustrativos (carteles de honestidad obligatorios)
    # ==================================================================

    def _example_rankine_cycle(self):
        """TIER 2 — Central térmica (ciclo Rankine).

        ⚠ MODELO ILUSTRATIVO (Tier 2): se modela el CICLO TERMODINÁMICO
        de vapor (bomba → caldera → turbina → condensador) con balance
        de energía real.  La FUENTE DE CALOR (combustión de carbón/gas
        o reactor nuclear) se ABSTRAE como un duty de entrada a la
        caldera.  Este ejemplo NO modela combustión ni física nuclear.

        Topología (loop "abierto" con makeup + blowdown 1 %):
            TK-makeup → P-101 (pump) → B-101 (caldera, duty grande) →
            TUR-101 (turbina, Heat exch con duty negativo = trabajo
            extraído) → CON-101 (condensador, duty extrae) → TK-blowdown
            + S-fuel (feed genérico representando el costo energético
            del combustible/calor abstraído).

        Basis 100 tm/año de makeup water (plant scale piloto).
        El "combustible abstraído" se mete como _add_example_extra
        utility con price para reflejar el OPEX energético.
        """
        tk_in   = self._add_example_block("TK-001", "Storage tank — cone roof",  90.0,  60, 260)
        p101    = self._add_example_block("P-101", "Pump — centrifugal",         10.0, 240, 260)
        b101    = self._add_example_block("B-101", "Boiler — water tube",     10.0, 420, 260)
        tur101  = self._add_example_block("TUR-101","Heat exch. — floating head", 150.0, 600, 260)
        con101  = self._add_example_block("CON-101","Heat exch. — air cooler",   180.0, 780, 260)
        tk_out  = self._add_example_block("TK-002", "Storage tank — cone roof",  90.0, 960, 260)

        # Makeup water 100 t/y (feed)
        self._add_example_stream(tk_in, p101, "S-makeup", 100, role="feed",
                                 src_port="salida", dst_port="succion",
                                 price=0.5, T=25,
                                 main_component="water", phase="liquid",
                                 composition={"water": 1.0})
        # Bombeada (HP)
        self._add_example_stream(p101, b101, "S-HP", 0.0,
                                 src_port="descarga", dst_port="proceso_in",
                                 T=30,
                                 main_component="water", phase="liquid",
                                 composition={"water": 1.0})
        # Vapor sobrecalentado (caldera +Q)
        self._add_example_stream(b101, tur101, "S-steam", 0.0,
                                 src_port="proceso_out", dst_port="tube_in",
                                 T=450,
                                 main_component="water", phase="vapor",
                                 composition={"water": 1.0})
        # Post-turbina (trabajo extraído → T baja drásticamente)
        self._add_example_stream(tur101, con101, "S-exp", 0.0,
                                 src_port="tube_out", dst_port="proceso_in",
                                 T=120,
                                 main_component="water", phase="vapor",
                                 composition={"water": 1.0})
        # Condensado (líquido a TK)
        self._add_example_stream(con101, tk_out, "S-cond", 0.0, role="product",
                                 src_port="proceso_out", dst_port="entrada",
                                 price=0.0, T=30,
                                 main_component="water", phase="liquid",
                                 composition={"water": 1.0})

        # OPEX: el combustible abstraído + agua de enfriamiento
        self._add_example_extra("Combustible abstraído (carbón/gas/nuclear)",
                                flowrate=15, price=200.0,
                                stream="Utilities")
        self._add_example_extra("Agua de enfriamiento (condensador)",
                                flowrate=50_000, price=0.05,
                                stream="Utilities")

        from flowsheet_solver import auto_set_duties_from_thermo
        auto_set_duties_from_thermo(self.fs)


    def _example_nuclear_steam(self):
        """TIER 2 — Isla convencional de central nuclear (circuito 2°).

        ⚠ MODELO ILUSTRATIVO (Tier 2): se modela el CIRCUITO SECUNDARIO
        de vapor (generador de vapor → turbina → condensador).  El
        núcleo del reactor, la fisión, la criticidad y la
        radiactividad NO se modelan: el calor del reactor entra como
        un duty fijo al generador de vapor.  Esto es,
        termodinámicamente, una central de vapor; la palabra "nuclear"
        refiere solo al origen abstraído del calor.

        Topología (igual a Rankine pero con un HX adicional simulando
        el generador de vapor que recibe calor del reactor abstraído):
            TK-makeup → P-101 (pump) → GV-101 (generador de vapor,
            recibe Q del "reactor") → TUR-101 (turbina) → CON-101
            (condensador) → TK-blowdown

        Basis 100 tm/año makeup water (plant scale piloto).
        """
        tk_in   = self._add_example_block("TK-001", "Storage tank — cone roof",  90.0,  60, 260)
        p101    = self._add_example_block("P-101", "Pump — centrifugal",         10.0, 240, 260)
        gv101   = self._add_example_block("GV-101","Heat exch. — kettle reboiler", 100.0, 420, 260)
        tur101  = self._add_example_block("TUR-101","Heat exch. — floating head", 150.0, 620, 260)
        con101  = self._add_example_block("CON-101","Heat exch. — air cooler",   180.0, 820, 260)
        tk_out  = self._add_example_block("TK-002", "Storage tank — cone roof",  90.0,1000, 260)

        # Makeup water
        self._add_example_stream(tk_in, p101, "S-makeup", 100, role="feed",
                                 src_port="salida", dst_port="succion",
                                 price=0.5, T=25,
                                 main_component="water", phase="liquid",
                                 composition={"water": 1.0})
        # Bombeada HP
        self._add_example_stream(p101, gv101, "S-HP", 0.0,
                                 src_port="descarga", dst_port="liq_in",
                                 T=30,
                                 main_component="water", phase="liquid",
                                 composition={"water": 1.0})
        # Vapor sobrecalentado del generador
        self._add_example_stream(gv101, tur101, "S-steam", 0.0,
                                 src_port="vap_out", dst_port="tube_in",
                                 T=280,
                                 main_component="water", phase="vapor",
                                 composition={"water": 1.0})
        # Post-turbina
        self._add_example_stream(tur101, con101, "S-exp", 0.0,
                                 src_port="tube_out", dst_port="proceso_in",
                                 T=100,
                                 main_component="water", phase="vapor",
                                 composition={"water": 1.0})
        # Condensado
        self._add_example_stream(con101, tk_out, "S-cond", 0.0, role="product",
                                 src_port="proceso_out", dst_port="entrada",
                                 price=0.0, T=30,
                                 main_component="water", phase="liquid",
                                 composition={"water": 1.0})

        # OPEX: calor del reactor + servicios
        self._add_example_extra("Calor reactor nuclear (abstraído)",
                                flowrate=12, price=400.0,
                                stream="Utilities")
        self._add_example_extra("Agua de enfriamiento (condensador)",
                                flowrate=50_000, price=0.05,
                                stream="Utilities")

        from flowsheet_solver import auto_set_duties_from_thermo
        auto_set_duties_from_thermo(self.fs)


    def _example_desalination(self):
        """TIER 2 — Desalinización por evaporación multi-efecto (MED).

        ⚠ MODELO ILUSTRATIVO (Tier 2): MED modelado como tren de
        evaporadores con balance de masa/energía real.  Se trata la
        sal como soluto no volátil (sodium_chloride).  No se modela
        la termodinámica de soluciones electrolíticas (elevación del
        punto de ebullición, ΔBPE, simplificada).

        Topología:
            TK-mar → E-101 (precal) → EV-101 (efecto 1) → EV-102
            (efecto 2) → EV-103 (efecto 3) → TK-salmuera (waste)
                                          ↓
                                       TK-destilada (vapor de cada
                                       efecto condensado en uno único)

        Basis 1000 tm/año agua de mar {water 0.965, sodium_chloride
        0.035} → 700 destilada + 300 salmuera concentrada (10 % sal).
        Sólidos NaCl conservan: 35 t/y en agua de mar, 35 t/y en
        salmuera concentrada (300 × 0.117 ≈ 35).
        """
        tk_in   = self._add_example_block("TK-001", "Storage tank — cone roof", 300.0,  60, 280)
        e101    = self._add_example_block("E-101",  "Heat exch. — floating head", 60.0, 240, 280)
        ev1     = self._add_example_block("EV-101", "Evaporator — vertical",     80.0, 420, 280)
        ev2     = self._add_example_block("EV-102", "Evaporator — vertical",     60.0, 600, 280)
        ev3     = self._add_example_block("EV-103", "Evaporator — vertical",     40.0, 780, 280)
        tk_brn  = self._add_example_block("TK-002", "Storage tank — cone roof", 100.0, 960, 380)
        tk_dst  = self._add_example_block("TK-003", "Storage tank — cone roof", 200.0, 600, 100)

        # Composiciones
        seawater  = {"water": 0.965, "sodium_chloride": 0.035}
        # ST conserva (35 t/y): después de EV1 (quita 250 t H2O) → 750 t,
        # ST_frac = 35/750 = 0.0467 (4.67 %)
        mid1      = {"water": 0.9533, "sodium_chloride": 0.0467}
        # Después de EV2 (quita 250 t más) → 500 t, ST = 35/500 = 0.07
        mid2      = {"water": 0.9300, "sodium_chloride": 0.0700}
        # Después de EV3 (quita 200 t) → 300 t, ST = 35/300 ≈ 0.117
        brine     = {"water": 0.883, "sodium_chloride": 0.117}

        # Agua de mar
        self._add_example_stream(tk_in, e101, "S-seawater", 1000, role="feed",
                                 src_port="salida", dst_port="tube_in",
                                 price=0.0, T=20,
                                 composition=seawater,
                                 main_component="water", phase="liquid")
        # Precalentada
        self._add_example_stream(e101, ev1, "S-precal", 0.0,
                                 src_port="tube_out", dst_port="alimentacion",
                                 T=60,
                                 composition=seawater,
                                 main_component="water", phase="liquid")
        # EV-101 vapor → destilada (250 t)
        self._add_example_stream(ev1, tk_dst, "S-dist1", 250, role="product",
                                 src_port="venteo", dst_port="entrada",
                                 price=2.0, T=70,
                                 main_component="water", phase="vapor",
                                 composition={"water": 1.0})
        # EV-101 producto → EV-102
        self._add_example_stream(ev1, ev2, "S-mid1", 0.0,
                                 src_port="producto", dst_port="alimentacion",
                                 T=65,
                                 composition=mid1,
                                 main_component="water", phase="liquid")
        # EV-102 vapor → destilada (250 t)
        self._add_example_stream(ev2, tk_dst, "S-dist2", 250, role="product",
                                 src_port="venteo", dst_port="entrada",
                                 price=2.0, T=60,
                                 main_component="water", phase="vapor",
                                 composition={"water": 1.0})
        # EV-102 producto → EV-103
        self._add_example_stream(ev2, ev3, "S-mid2", 0.0,
                                 src_port="producto", dst_port="alimentacion",
                                 T=55,
                                 composition=mid2,
                                 main_component="water", phase="liquid")
        # EV-103 vapor → destilada (200 t)
        self._add_example_stream(ev3, tk_dst, "S-dist3", 200, role="product",
                                 src_port="venteo", dst_port="entrada",
                                 price=2.0, T=50,
                                 main_component="water", phase="vapor",
                                 composition={"water": 1.0})
        # EV-103 producto → TK salmuera (waste concentrada)
        self._add_example_stream(ev3, tk_brn, "S-brine", 0.0, role="waste",
                                 src_port="producto", dst_port="entrada",
                                 price=0.0, T=50,
                                 composition=brine,
                                 main_component="water", phase="liquid")

        self._set_example_labor(180_000)
        self._add_example_extra("Vapor proceso (calderas + economía multi-efecto)",
                                flowrate=400_000, price=15.0,
                                stream="Utilities")
        self._add_example_extra("Electricidad (bombas alta P + vacío)",
                                flowrate=120_000, price=0.08,
                                stream="Utilities")

        from flowsheet_solver import auto_set_duties_from_thermo
        auto_set_duties_from_thermo(self.fs)


