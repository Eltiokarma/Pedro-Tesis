# Rediseño del frontend — implementación (julio 2026)

Implementación de la propuesta de Design "Rediseño Frontend" (7 artboards,
respuesta a `docs/AUDITORIA_FRONTEND_UX.md`). Rama:
`claude/frontend-audit-design-k48oko`. Suite completa verde: **603 tests +
gates** (economics, simulate, examples 41/41, component balance, EOS,
pressure source, glyph coverage).

## Qué se implementó, por artboard

### 1a — `tokens.py` único
- `TOK`, temas/acentos/densidades, `_PrefsBus` y persistencia promovidos de
  `block_inspector.py` a **`tokens.py`** (block_inspector re-exporta por
  compatibilidad; headless-safe).
- **Semáforo tokenizado**: `STATUS_TOKEN`/`STATUS_FILL_TOKEN` — la paleta
  Material (`#2e7d32/#f9a825/#c62828/#1976d2/#7b1fa2`) murió; cada estado
  resuelve a un token del tema y se lee en caliente (`status_hex`).
- Selección: índigo `#283593` → acento del tema. Intrusos `#c0392b`/`#b9770e`
  del panel económico → `danger`/`amber`. `econ_figures` sin fallbacks hex.
- Tipografía 4 tamaños (`FONT_TITLE/UI/VALUE/LABEL`), strokes `1.6/1.0`, y el
  **formateador único** `fmt_musd`/`fmt_pct`/`fmt_years`.

### 1b — Estado en el cuerpo del símbolo, sin halo
- `_StatusHaloItem` (la caja de colores alrededor del equipo) **eliminado**.
- `IsaGlyphItem` separa dos ejes que antes se pisaban:
  - `set_status()` (solver) colorea el CUERPO: ok = trazo neutro + dot verde;
    warning/error = trazo + tinte de relleno + chip "!" (color y símbolo,
    daltónico-safe); stale = glifo atenuado; unrun = contorno punteado.
  - `set_state()` (idle/hover/selected/solving) dibuja anillos ALREDEDOR —
    seleccionar un equipo con error ya no borra el rojo ni apila 3 marcos.

### 1c — Topbar por zonas de tarea
- Las dos QToolBars legacy ocultas + el toggle "Toolbars legacy" **borradas**;
  `_build_shared_actions()` crea UNA QAction por concepto que consumen menú y
  topbar via `setDefaultAction` (checks nunca desincronizados, shortcuts
  reales en ↶↷).
- Topbar: identidad (nombre + **estado de guardado real** — adiós "v0.4"
  hardcodeado) · edición (undo/redo | Marco PFD — antes el botón mentiroso
  "▦ Toggle grid" — · Animación de flujo, ahora UNA QAction, antes dos
  desincronizables) · workflow (chip solver → Validar DOF → Resolver →
  **Economía**, el paso final por fin visible).
- Botón muerto ✦ Auto-arrange **eliminado**. "Biblioteca de equipos (vieja)"
  **borrada** (la paleta cubre catálogo/variantes/drag). Íconos únicos por
  acción en menú Simulación (`act-money` ya no se repite ×3).

### 1d — Glifos: seis parejas diferenciadas
Nuevos `_draw_*` (geometría de referencia: patch PFD-ICN-002 de
`pfd_symbols.py`): `splitter` (1→2 divergente — antes se dibujaba como mixer,
semántica invertida), `reactor_pfr` (serpentín vs CSTR agitado),
`compresor_recip` (pistón/biela vs centrífugo), `hx_whb` (steam drum vs
kettle), `empaque` (hatch vs platos), `torre_nat` (hiperboloide vs tiro
inducido). El gate `test_glyph_coverage` obliga a mantenerlos registrados.

### 1e/1f — Panel económico: una sola UI + Monte Carlo embebido
- `EconRichView` es LA UI del panel, montada desde el arranque (estado vacío
  → arranca en Parámetros). **Muertos**: dump ASCII con box-drawing, tab bar
  exterior, `_render_econ_legacy`, QTextEdit Consolas, `run_economics=True`
  visible (ahora: `proyecto · CEPCI año`), ventana ASCII de Monte Carlo y
  sus 3 botones de entrada, widget muerto `NpvHero`.
- Sidebar honesto: **7 ítems → 7 panes reales** (Resumen / CAPEX / OPEX /
  Cash flow / Monte Carlo / Contabilidad / Parámetros). KPIs UNA vez en el
  hero. Footer solo de acciones (Exportar Excel + Re-correr análisis).
- `MonteCarloPane` embebido cablea por fin `npv_density_figure` +
  `tornado_figure` (implementadas y nunca usadas), con resumen
  n/seed/P10-P50-P90/P(NPV<0).
- Cambio de tema → la vista se re-monta y las figuras re-leen tokens (el
  dark mode ya no queda incoherente).

### 1g — Limpieza
Además de lo anterior: badge correcto para los 2 WHB (`eq-boiler`; antes
ícono de mixer por fallback), docstring-patch de 540 líneas al final de
`equipment_icons.py` borrado, herramienta T (anotación) fuera de la paleta
mientras sea stub, emoji ✋/⚡ de la paleta → glifos de línea.

## Divergencias razonadas respecto a la propuesta

1. **Dock "Propiedades (viejo)" NO se borró** (la propuesta lo listaba en
   1g). Aloja funcionalidad viva sin reemplazo: perfiles PFR/batch/CSTR,
   McCabe-Thiele, perfil tray-by-tray y la salida de "Calcular costos"
   (`results_box`). Se renombró a "Propiedades y perfiles" (sin etiqueta
   "viejo") y quedó accesible desde Vista. Migrar esos perfiles al
   Inspector es trabajo futuro; recién entonces puede morir el dock.
2. **Los 43 símbolos no referenciados de `pfd_symbols.SYMBOLS` se
   conservan**: son la geometría de referencia citada por los glifos nuevos
   (PFD-ICN-002) y no pesan en runtime (dict de strings). Borrarlos
   destruiría la biblioteca de referencia que la propia propuesta usa.

## Pendientes sugeridos por la propuesta (sección ⚡ de 1g — no implementados)

- Q_reb y Q_cond por columna en el inspector (hoy solo `b.duty`).
- `n_stages` + `Q_intercool` del modelo multi-etapa de compresor como dato
  visible (hoy vive en un warning de texto).
- Chip "átomos ✓" por bloque desde la auditoría elemental C/H/O.
- Implementar la herramienta de anotación (T) de verdad y devolverla a la
  paleta.
- Migrar perfiles PFR/McCabe/etapas del dock de Propiedades al Inspector
  (habilita el borrado del dock).
