# Rediseño ciclo 5 — implementación de la Ficha Técnica (julio 2026)

Implementación del artboard 5f (`docs/design_ciclo5/Selector equipo
comercial 5f.dc.html`, respuesta a `docs/PROMPT_DESIGN_CICLO5_FICHAS.md`)
+ la tanda 1 del plan del inventario (`datasheet.py`).  Regresión:
`tests/test_datasheet.py` (16 tests: contrato, catálogo, 6 estados de
verificación, restricción de Block.S, smoke Qt de los 3 escenarios del
selector).  Suite 799 · gate 64/64.

## datasheet.py — agregador Qt-free (tanda 1)

- `datasheet_spec(block, fs)`: la ficha del contrato §4 (identidad,
  condiciones, corrientes, diseño, materiales, auxiliares, costos, notas
  + verificación), toda desde resultados YA calculados.  Fallback
  genérico garantizado para los 60 tipos — test de cobertura recorre
  TODOS los bloques de TODOS los ejemplos.
- Catálogo comercial: `entradas_para(eq_type)` / `entrada_de(block)`
  (clave `marca|modelo` + eq_type del propio Block).
- `verificacion(block, fs)`: los seis estados — no_aplica /
  sin_declarar / desconocido / escalar / envolvente_modelo /
  debil_familia — con utilización, AND de envolvente (P/T efectivas del
  solver; Q y head solo donde el motor ya los computa: no se inventa el
  requerido) y `apto=None` SIEMPRE en familia.

## Sección «Ficha técnica» del inspector (5f)

Nueva clave `ficha` (sidebar ▤, entre Sizing y Utility).  Decisiones del
bundle encarnadas:

- **5f.1** tipo sin catálogo → afirmación tranquila («Ingeniería a
  pedido…»), sin control deshabilitado ni campo vacío.
- **5f.2** selector activo con placeholder «Seleccionar equipo…»,
  ítems «Marca · Modelo — S unit» (o «— envolvente del modelo/de
  familia» para las entradas sin S).
- **5f.3** veredicto escalar: APTO/NO ENTRA con Requerido / Instalado /
  Utilización % y el aviso de sobredimensionamiento grosero (<35% de
  utilización).
- **5f.4** envolvente de modelo: DENTRO/FUERA DE ENVOLVENTE, filas
  «✓ Presión 8 ≤ 16 bar», «Sin ratio de utilización» como propiedad.
- **5f.5** débil de familia: borde punteado atenuado, filas con tag
  FAMILIA, nunca verde macizo, nunca rojo.
- **Trazabilidad no negociable**: fuente del fabricante (link) +
  fecha_consulta al pie de todo veredicto.
- El combo escribe `Block.equipo_comercial` EN VIVO y refresca el
  veredicto; el pase de apply del inspector lo repite idempotente.
- **Restricción dura respetada y testeada**: el S del catálogo jamás
  toca `Block.S` (test explícito + docstrings en los 3 niveles).

## Desvíos del bundle (⚡ para el próximo ciclo de Design)

1. **Agrupación por fabricante**: el bundle agrupa con headers de
   sección dentro del desplegable; el QComboBox nativo va plano con el
   fabricante como prefijo del ítem.  Grupos reales = delegate custom,
   se pospone.
2. **5f.2b (modelo único)**: el bundle pide afirmación directa con botón
   «Declarar» sin desplegable; la implementación usa el mismo combo (2
   ítems) por uniformidad del pase de apply.  Pendiente de la pasada
   visual.
3. Los tres puntos del artboard sobre tipografías/píxeles exactos se
   heredan del kit existente (FONT_HINT/VALUE/LABEL, tokens green/
   danger/ink_mute) en lugar de valores propios de la ficha.

## Tandas 3-4 del inventario — HECHAS (2026-07-25)

`datasheet_export.py`, Qt-free salvo el PDF.  Regresión:
`tests/test_datasheet_export.py` (15 tests).  Menú *Archivo → Exportar*:
«Fichas técnicas — PDF (legajo)…» y «Fichas técnicas — Excel…».

- **XLSX** (tanda 3): hoja «Índice» (tag, tipo, categoría, marca/modelo,
  estado de verificación, CBM) + una hoja por equipo.  Nombres de hoja
  saneados — Excel rechaza `[]:*?/\` y >31 caracteres, y no admite dos
  hojas iguales.
- **PDF** (tanda 4): una ficha por página A4, encabezado
  proyecto · rev △N · fecha, pie con numeración y la leyenda «diseño
  conceptual — no apto para construcción».  Una ficha que no entra en una
  página sigue en la siguiente ROTULADA `(cont.)`, en vez de recortarse en
  silencio.  Si el flowsheet registró revisiones, cierra con una página de
  historial △N — el mismo cuadro del Marco PFD, en formato de legajo; sin
  revisiones no se emite la página (el plano tampoco dibuja un cuadro
  vacío).

**La decisión que sostiene las dos:** qué se imprime y en qué orden se
decide UNA vez, en `datasheet_rows()`.  Los renderers solo deciden cómo
pintar esas filas.  Con un recorrido del spec por formato, divergirían al
primer campo nuevo y la ficha dejaría de ser el mismo documento en dos
formatos; `TestParidad` congela esa igualdad.

El rótulo del proyecto sale del **cuadro de título del Marco PFD**, no de
un nombre nuevo: plano y legajo son dos documentos del mismo trabajo.

### Lo que el export destapó

Escribir la ficha a papel encontró un bug que la UI ya no mostraba:
`datasheet.verificacion()` seguía devolviendo, para los tipos sin
catálogo, la frase *«Ingeniería a pedido: ningún fabricante publica
tamaños de catálogo para este tipo»* — la misma afirmación que la cosecha
2026-07 había corregido en el callout del inspector **por ser falsa** para
varios de esos tipos (Solar Turbines publica potencia por modelo, Andritz
publica área de filtros de banda).  El callout quedó honesto y el veredicto
no, así que cualquier consumidor nuevo del agregador heredaba la mentira.
Ahora el mensaje se arma con `motivo_a_pedido()`: título + razón de
ingeniería verificada, o el genérico débil con su aviso de alcance.
