# Brief — Catálogo de equipos comerciales (para Claude Desktop / Cowork)

**Contexto:** el simulador (esta repo) va a soportar "modo selección" en las
Fichas Técnicas: el usuario trae un equipo comercial real — marca, modelo —
y el motor verifica requerido vs instalado (ver
`docs/FICHAS_TECNICAS_INVENTARIO.md` §4.1). El selector de la UI se alimenta
de `data/equipos_comerciales.json`, que hoy está VACÍO a propósito.

**Por qué esta tarea va en Desktop/Cowork:** la sesión de Claude Code del
repo tiene política de red restringida (el proxy bloquea los sitios de
fabricantes con 403 en CONNECT — verificado 2026-07-24), así que la cosecha
de PDFs oficiales debe hacerse desde un entorno con navegación abierta.

## Encargo

Para cada modelo objetivo (lista abajo): localizar el **PDF/página oficial
del fabricante** (no distribuidores, no marketplaces), extraer los campos, y
agregar una entrada al array `equipos` de `data/equipos_comerciales.json`.

### Esquema de entrada (validado por `tests/test_equipos_comerciales.py`)

```json
{
  "marca": "Atlas Copco",
  "modelo": "GA 30+",
  "eq_type": "Compressor — rotary",
  "S": 30,
  "params": {
    "P_max_bar": 13,
    "Q_max_m3_h": 366,
    "notas": "Tornillo lubricado. S = potencia de motor instalada (kW). ..."
  },
  "fuente": "https://www.atlascopco.com/...GA30-90_Wuxi_EN.pdf",
  "fecha_consulta": "2026-07-23"
}
```

(Entrada real del catálogo, abreviada. El ejemplo anterior usaba un PHE
`Heat exch. — flat plate` — retirado: esa categoría no admite un S
defendible, ver "Categorías sin S publicado".)

Reglas duras (cultura del repo):
- `eq_type` debe ser una clave EXACTA de `equipment_costs.EQUIPMENT_DATA`
  (el modelo comercial parametriza un tipo genérico existente).
- `S` en la unidad del tipo (`S_unit` del catálogo): área m² para HX,
  kW eje para bombas/compresores/turbinas/agitadores, m³ para tanques…
  Si el fabricante da un RANGO, usar un tamaño representativo del modelo
  y anotar el rango en `params.notas`.
- `fuente` = URL del documento oficial; `fecha_consulta` AAAA-MM-DD.
- **Ningún número inventado ni interpolado**: si un campo no está en el
  PDF, se omite (los `params` son todos opcionales).
- `material` con las claves del repo: CS, SS304, SS316, Ni, Monel,
  Hastelloy, Inconel, Titanium, Cu, Glass-lined, Tantalum, CS galv.

### Qué significa S en una entrada comercial

`S` es la **capacidad nominal o máxima publicada del modelo** en la
`S_unit` de su `eq_type` — la ENVOLVENTE, no un punto de operación.
La verificación del modo selección es `S_requerido <= S_modelo`, y el
cociente `S_requerido / S_modelo` es el ratio de utilización.
`S` no basta: `P_max_bar`, `T_max_C`, `Q_max_m3_h`, `head_max_m` son
dimensiones adicionales de la misma envolvente. La verificación completa
es un AND de desigualdades.

### Categorías sin S publicado — esquema v2 (`S_no_publicado`)

Desde el esquema v2, una entrada sin S escalar publicado **SÍ entra** al
catálogo declarando el motivo (vocabulario CERRADO) y aportando al menos
una dimensión de envolvente (`Q_max_m3_h`, `head_max_m`, `P_max_bar`,
`T_max_C`, `n_placas_max`). Los tres motivos, con su ejemplo:

- **`"configurable"`** — el tamaño se arma por pedido y no hay techo por
  modelo. Ejemplo: `Heat exch. — flat plate` (Alfa Laval M10): el área se
  configura por número de placas y la fija el ingeniero térmico según el
  duty; la entrada verifica la envolvente P/T del bastidor (FM 10 bar /
  FG 16 bar / FD 26.8 bar). **Ya NO está vetada.**
- **`"punto_de_operacion"`** — el escalar existe pero depende del duty
  point, no del modelo. Ejemplo: `Pump — centrifugal` / `Pump — positive
  displacement`: el kW al eje sale de la curva en el punto de operación;
  la entrada verifica `Q_max_m3_h` / `head_max_m` / `P_max_bar` del
  modelo. **Ya NO están vetadas.**
- **`"otra_magnitud"`** — el fabricante publica su capacidad en una base
  que no mapea a la S_unit del tipo genérico. Ejemplo hipotético: un
  ciclón especificado por diámetro de cuerpo en vez de caudal.

Sigue vigente la regla dura: **no cargar un "tamaño representativo" ni un
número de distribuidor** — sin S publicado, la entrada va por
`S_no_publicado` + envolvente, nunca por un S inventado.

**Granularidad de la envolvente** (campo `granularidad`, obligatorio en
toda entrada sin S; prohibido con S — un S escalar ya es de un modelo
nombrado). Vocabulario cerrado:

- `"modelo"` — los límites son del tamaño/bastidor concreto (los M10
  FM/FG/FD: cada bastidor con su P/T propia).
- `"familia"` — los límites son del RANGO COMPLETO de la serie. Modo de
  fallo, con caso vivo: **NETZSCH NEMO L.Cap** publica 1000 m³/h y
  20 bar, pero son la envolvente de la familia entera (versiones simple,
  doble y vertical), no de un tamaño — la fija el miembro más grande,
  así que casi cualquier duty la satisface y la verificación es DÉBIL:
  un APTO contra esa entrada no confirma nada. Por eso `"familia"` exige
  `params.notas` explicando por qué no se consiguió la envolvente del
  tamaño, y la entrada debe sustituirse en cuanto se consiga.

**Entre dos fabricantes equivalentes, preferir el que publica en la
unidad del repo.** Bosch publica vapor en kg/h → conversión limpia a
kg/s. Cleaver-Brooks publica en BHP → convertir a kg/s reales a presión
de operación exige corrección de entalpía, o sea una estimación donde no
había ninguna. La conversión indirecta mete suposiciones.

**`Mixer — impeller`: sigue vetado, con motivo nuevo.** Su envolvente
natural es el PAR (N·m), y `_PARAMS_OK` no tiene campo de par. No le
falta S: le falta vocabulario. Habilitarlo requiere un param nuevo, y eso
es otro ciclo.

### Modelos objetivo (3-5 por categoría basta para la tesis)

| Categoría (eq_type) | Candidatos |
|---|---|
| HX placas (`Heat exch. — flat plate`) | Vía `S_no_publicado: "configurable"` + envolvente P/T del bastidor. Cargados: Alfa Laval M10 FM/FG/FD. Candidatos: SWEP B-series; GEA VT-series |
| HX casco-tubo (`Heat exch. — fixed tube` / `floating head`) | Kelvion, HRS Funke — series estándar con área nominal |
| Bomba centrífuga (`Pump — centrifugal`) | Vía `S_no_publicado: "punto_de_operacion"` + envolvente (`Q_max_m3_h`, `head_max_m`). Candidatos: Grundfos NK/NB; KSB Etanorm; Sulzer AHLSTAR |
| Bomba desplazamiento (+`Pump — positive displacement`) | NETZSCH NEMO; Viking gear |
| Compresor tornillo (`Compressor — rotary`) | Atlas Copco GA 30-90; Kaeser CSD |
| Agitador (`Mixer — impeller`) | ⛔ **Vetado** — su envolvente natural es el PAR (N·m) y `_PARAMS_OK` no tiene campo de par; habilitar requiere param nuevo (otro ciclo) |
| Turbina vapor (`Turbine — steam`) | Siemens SST-040/060 (kW, presiones de entrada) |
| Caldera (`Boiler — fire tube`) | Cleaver-Brooks CB, Bosch UL-S — **S en kg/s** (S_unit del tipo). Las designaciones del fabricante vienen en kg/h (UL-S 1250 = 1250 kg/h): **dividir por 3600**. Sin la conversión, un UL-S 28000 entra 1400× fuera de rango y el costeo devuelve basura. |

### PLAN 6× — «que se sienta y viva la ingeniería» (lote 4+)

Objetivo pedagógico (2026-07): **≥6 opciones por tipo catalogable**, de
≥2 fabricantes por tipo, para que el estudiante compare proveedores
reales al declarar. La economía de la cosecha es POR SERIE, no por
modelo: un leaflet de Atlas Copco rindió 10 entradas, el portfolio
Siemens 7, una hoja Kaeser 4. Meta total ≈ 60-80 entradas ≈ **15-25
documentos** de fabricante.

**Completar los 5 tipos existentes hasta ≥6 y ≥2 marcas:**

| Tipo (hoy) | Falta | Fuentes objetivo |
|---|---|---|
| Compressor — rotary (14 ✓) | 2ª marca ya hay (AC+Kaeser) — completo | — |
| Turbine — steam (7, 1 marca) | +1 marca | Elliott (serie YR, PDF único), TGM, Howden/KK&K |
| Boiler — fire tube (3, 1 marca) | +3, +1 marca | Viessmann Vitomax (serie completa en 1 doc), Bono/Cannon; Cleaver-Brooks solo con la conversión BHP documentada |
| Heat exch. — flat plate (3, 1 marca) | +3, +1 marca | SWEP B-series (rangos P/T por bastidor), GEA VT/NT, Kelvion NX — todos vía `S_no_publicado: "configurable"` |
| Pump — positive displacement (1, 1 marca) | +5, +1 marca | SEEPEX BN (envolventes POR TAMAÑO — reemplaza la NEMO de familia), Viking gear (Q/P por modelo), Verder Verderflex |

**Categorías NUEVAS que honestamente tienen catálogo** (abrirlas suma
selectores en muchos ejemplos):

| Tipo nuevo | Vía | Fuentes objetivo | Ejemplos que ganan selector |
|---|---|---|---|
| `Valve — control globe` | `S_no_publicado: "otra_magnitud"` + envolvente (el fabricante publica Cv por tamaño; Cv no mapea a S=m³/h) o S por Cv→caudal documentado | Samson 241/3241 (tabla Cv completa en 1 hoja), Fisher easy-e ED | letdown, cw_natural |
| `Centrifuge — disc stack` | S (m³?) o envolvente Q_max | GEA (separadores leche — ¡leche_gloria!), Alfa Laval | leche_gloria |
| `Centrifuge — decanter` | envolvente Q_max | Flottweg C-series, GEA | — |
| `Fan — centrifugal radial` / `axial` | S = m³/s publicado por modelo | Sodeca, S&P, Greenheck (curvas con caudal máx.) | blower, cw_natural |
| `Compressor — reciprocating` | S kW por modelo | Ariel JG (serie en 1 doc), Ingersoll Rand | ldpe |
| `Cooling tower — induced draft` (paquete) | envolvente duty/caudal | Evapco AT, Baltimore Aircoil | cooling, cw_loop |
| `Pump — centrifugal` | `"punto_de_operacion"` + envolvente Q/H | Grundfos NK/NB (rangos por modelo), KSB Etanorm | ~30 bombas en todo el set |

Con esto, la cobertura de instancias con selector en los 64 ejemplos
pasa de 5 bloques a decenas (todas las bombas centrífugas, fans,
válvulas de control, torres). Sigue honestamente a pedido: reactores,
columnas, vessels, casco-tubo, hornos — y eso también es lección.

**Reglas del lote (sin cambios)**: solo documentos oficiales, esquema
v2 + granularidad (preferir SIEMPRE envolvente por tamaño; familia solo
con nota y para reemplazar), unidad del repo, sin números de
distribuidor. El gate valida todo lo que entre.

### Entrega y verificación

1. Rellenar `data/equipos_comerciales.json` (mantener `schema: 1`).
2. Correr `python -m unittest tests.test_equipos_comerciales -v` — valida
   esquema, eq_types, materiales, URLs, fechas y duplicados.
3. Commit en la rama `claude/fichas-tecnicas-equipo-tp1qw5` (o entregar el
   JSON a la sesión de Claude Code para que lo integre y corra la suite).

La UI del selector (dropdown por tipo, estado "sin equipo vs declarado") NO
es parte de este encargo: la especifica Claude Design (artboard 5f de
`docs/PROMPT_DESIGN_CICLO5_FICHAS.md`) y la monta Claude Code después.
