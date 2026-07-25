# Backlog para la segunda auditoría de UI

**Fecha:** 2026-07-17 · Escaneo de cierre tras implementar el rediseño
(`docs/REDISENO_FRONTEND_2026-07.md`). Registro de lo que quedó FUERA del
primer ciclo auditoría→design→implementación, con evidencia, para arrancar
la próxima auditoría sin redescubrir nada.

> **CERRADO (2026-07-25).** Los ciclos 2 a 5 ejecutaron los ítems A-G de
> este backlog y los 11 de `AUDITORIA_UI_2.md` §H. La verificación ítem
> por ítem, con capturas nuevas y censo de código, está en
> `docs/AUDITORIA_UI_3.md`; la regresión que impide reabrirlos en
> silencio, en `tests/test_auditoria_ui3.py`. La pregunta abierta de §A
> («¿los puertos adoptan TOK o paleta técnica propia?») se decidió por
> **paleta técnica propia con par dark** (artboard 2a). El backlog vivo
> pasa a ser §2 de la auditoría 3.

---

## A. El lienzo no respira el tema (el hallazgo grande) — ALTA

Con tema oscuro activo, topbar/menús/paneles se oscurecen (tokens ✓) pero
el **canvas queda claro** y los **glifos toman el fill oscuro del tema**
(`bg_elev` dark) → bloques como manchas negras sobre papel claro, detalles
internos invisibles. Evidencia: captura `canvas_dark` del escaneo.

Causa: toda la paleta del lienzo está hardcodeada en `flowsheet_qt.py`
fuera del sistema de tokens (~96 hex):
- `COLOR_CANVAS_BG #fbfaf6`, `COLOR_GRID`, `COLOR_LABEL_BG` (blanco 220),
  `COLOR_BLOCK_TEXT #1a1a1a`, `COLOR_BLOCK_SUB` (flowsheet_qt.py:218-258).
- **Paleta de puertos aún Material** (`#2e7d32/#1565c0/#ef6c00/#bf360c/…`,
  :231-238) — el mismo problema de "dos sistemas de color" que la
  auditoría 1 mató para el semáforo, vivo para los puertos.
- Colores de servicio por temperatura (`#ef6c2b/#3fa9dd/…`, :274-284),
  duty badge (`#c41e3a/#1565c0`, ×8), handles/jumpers (`#1f6feb` ×6),
  roles de stream (`#2a9d4a/#9d2a8a/#d4691e/#f4b400`…).

Dirección: tokenizar la capa canvas (fondo, grilla, labels, puertos,
streams, badges) con variantes light/dark, o bloquear el tema oscuro a
solo-paneles hasta que exista. Decisión de diseño: ¿los puertos adoptan
la paleta TOK o se declaran paleta técnica propia con par dark?

## B. Tipografía: tokens declarados, adopción parcial — MEDIA

`tokens.FONT_TITLE/UI/VALUE/LABEL` (los 4 tamaños del artboard 1a) existen
pero casi ningún widget los consume: `econ_richview`/`inspector_widgets`/
`editor_chrome` siguen con `QFont(..., 7..16)` hardcodeados (los KPI
kickers de 7pt que la auditoría 1 marcó siguen en 7pt). Segunda pasada:
reemplazar QFont sueltos por los tokens.

## C. Íconos no se recolorean al cambiar tema — MEDIA

`make_qicon` colorea los SVG UNA vez al arranque con `TOK["ink_mute"]`
(`_build_shared_actions`, menús). Al pasar a dark los íconos conservan el
color del tema claro. Falta: regenerar íconos en `_PrefsBus.themeChanged`
(patrón ya usado por las figuras del panel económico).

## D. Superficies nunca auditadas — MEDIA

La auditoría 1 cubrió canvas/topbar/símbolos/economía. Quedaron sin pasada
formal (0 hex hardcodeados, pero sin revisión de UX):
- `welcome_qt.py` (pantalla de inicio),
- `streams_table.py` (dock tabla de corrientes),
- `stream_inspector.py` (5 hex: `PHASE_DOT` cobalto/etc. fuera de TOK),
- diálogos de edición de bloque/stream, Setpoints, DOF, Perfil económico,
  OPEX extras, Preferencias, exportación PDF/SVG/PNG (¿los exports
  respetan la regla ortogonal y el semáforo nuevo?).

## E. Leyenda del lenguaje visual — BAJA (pedagógico)

El canvas ya comunica mucho con color (semáforo de equipos, 8 clases de
puertos, servicio caliente/frío, roles de stream) pero **no existe una
leyenda** que lo explique. Candidato: card de leyenda colapsable o en el
Marco PFD (que ya tiene cuadro de título).

## F. Pendientes heredados del rediseño (sección ⚡ del artboard 1g)

Sin cambios desde `REDISENO_FRONTEND_2026-07.md`:
1. Q_reb y Q_cond por columna en el inspector (hoy solo `b.duty`).
2. `n_stages` + `Q_intercool` del compresor multi-etapa como dato visible.
3. Chip "átomos ✓" por bloque (auditoría elemental C/H/O, 41/41 limpia).
4. Implementar la herramienta de anotación (T) y devolverla a la paleta.
5. Migrar perfiles PFR/McCabe/tray del dock Propiedades al Inspector
   (habilita borrar el dock, ítem que la propuesta 1g dejó pendiente).

## G. Menores detectados en el escaneo

- Chip del solver de la topbar: `action_solve` no siempre reporta
  iter/tiempo al chip (`update_solver_chip` existe; verificar cableado
  en todos los caminos de solve).
- Anotación de payback en las figuras (token `spec`) queda tenue en dark.
- `inspector_widgets.py` tiene 1 hex suelto.
- El fill de estado (`green_bg/amber_bg/danger_bg`) sobre el canvas claro
  funciona; revisar contraste de esos tintes cuando exista canvas dark (A).

---

**Sugerencia de arranque para la auditoría 2:** A (canvas + tema oscuro +
puertos tokenizados) es el equivalente de "el cuadrado de colores" de la
primera: el hallazgo estructural del que cuelga el resto. B y C son
mecánicos; D define el alcance nuevo; E/F son features.
