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

### Entrega y verificación

1. Rellenar `data/equipos_comerciales.json` (mantener `schema: 1`).
2. Correr `python -m unittest tests.test_equipos_comerciales -v` — valida
   esquema, eq_types, materiales, URLs, fechas y duplicados.
3. Commit en la rama `claude/fichas-tecnicas-equipo-tp1qw5` (o entregar el
   JSON a la sesión de Claude Code para que lo integre y corra la suite).

La UI del selector (dropdown por tipo, estado "sin equipo vs declarado") NO
es parte de este encargo: la especifica Claude Design (artboard 5f de
`docs/PROMPT_DESIGN_CICLO5_FICHAS.md`) y la monta Claude Code después.
