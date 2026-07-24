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
  "marca": "Alfa Laval",
  "modelo": "M10",
  "eq_type": "Heat exch. — flat plate",
  "S": 72.5,
  "params": {
    "U_W_m2K": 4500,
    "material": "SS316",
    "P_max_bar": 16,
    "T_max_C": 180,
    "Q_max_m3_h": 180,
    "notas": "placas AISI 316, juntas NBR/EPDM"
  },
  "fuente": "https://www.alfalaval.com/...m10.pdf",
  "fecha_consulta": "2026-07-24"
}
```

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

### Modelos objetivo (3-5 por categoría basta para la tesis)

| Categoría (eq_type) | Candidatos |
|---|---|
| HX placas (`Heat exch. — flat plate`) | Alfa Laval M6 / M10 / T21; SWEP B-series; GEA VT-series |
| HX casco-tubo (`Heat exch. — fixed tube` / `floating head`) | Kelvion, HRS Funke — series estándar con área nominal |
| Bomba centrífuga (`Pump — centrifugal`) | Grundfos NK/NB (punto nominal Q/H/η); KSB Etanorm; Sulzer AHLSTAR |
| Bomba desplazamiento (+`Pump — positive displacement`) | NETZSCH NEMO; Viking gear |
| Compresor tornillo (`Compressor — rotary`) | Atlas Copco GA 30-90; Kaeser CSD |
| Agitador (`Mixer — impeller`) | EKATO, Chemineer serie 20, SPX Lightnin (kW de accionamiento) |
| Turbina vapor (`Turbine — steam`) | Siemens SST-040/060 (kW, presiones de entrada) |
| Caldera (`Boiler — fire tube`) | Cleaver-Brooks CB, Bosch UL-S (kg/h vapor, bar) |

### Entrega y verificación

1. Rellenar `data/equipos_comerciales.json` (mantener `schema: 1`).
2. Correr `python -m unittest tests.test_equipos_comerciales -v` — valida
   esquema, eq_types, materiales, URLs, fechas y duplicados.
3. Commit en la rama `claude/fichas-tecnicas-equipo-tp1qw5` (o entregar el
   JSON a la sesión de Claude Code para que lo integre y corra la suite).

La UI del selector (dropdown por tipo, estado "sin equipo vs declarado") NO
es parte de este encargo: la especifica Claude Design (artboard 5f de
`docs/PROMPT_DESIGN_CICLO5_FICHAS.md`) y la monta Claude Code después.
