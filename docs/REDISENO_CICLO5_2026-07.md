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

## Qué sigue (tandas 3-4 del inventario)

Export XLSX (hoja por equipo) y PDF multipágina (QPdfWriter, cuadro de
revisiones △N).  El agregador ya entrega el dict completo por bloque;
los exports son consumidores puros.
