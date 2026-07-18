# Análisis de convergencia — Grupo 2: Reactores y solver avanzado (Capas 4-6)

**Fecha:** 2026-07-18
**Alcance:** los 6 ejemplos de la categoría *Reactores y solver avanzado*:
`smr_eq`, `ethane_pfr`, `haber_rec`, `dist_eth_az`, `rxn_flash_col`,
`hydraulic`.
**Criterio:** todo tiene que converger, incluso económico; si no,
encontrar el porqué. Misma metodología que el grupo 1 (headless
`simulate_cli --economics`, perfil PE_2024, sensibilidad verificada por
re-simulación, sin tocar goldens salvo re-export deliberado).

## Naturaleza del grupo

A diferencia del grupo 1 (procesos), el grupo 2 son **demostraciones de
capas del solver**. Cada ejemplo existe para probar una capacidad numérica
concreta, no para ser un caso de negocio:

| Ejemplo | Capacidad que demuestra |
|---|---|
| smr_eq | Reactor de **equilibrio** (Capa 4) — SMR + WGS |
| ethane_pfr | Reactor **PFR cinético** (Capa 5) — cracking de etano |
| haber_rec | **Loop de recycle reactivo** — Haber-Bosch con reciclo |
| dist_eth_az | **NRTL / azeótropo** (Capa 6) — etanol-agua |
| rxn_flash_col | **Tren automático** reactor + flash + columna |
| hydraulic | **Bomba auto-dimensionada** — propagación hidráulica |

## Resultado global

| Ejemplo | Solver | Balances M/E | Iters | ISBL | NPV (USD) | Veredicto |
|---|---|---|---|---:|---:|---|
| smr_eq | ✓ ok | 0 / 0 | 4 | 10.2 M | −25 981 757 | INVIABLE |
| ethane_pfr | ✓ ok | 0 / 0 | 3 | 6.4 M | −17 989 311 | INVIABLE |
| haber_rec | ✓ ok | 0 / 0 | 2 (recycle✓ 3it) | 13.9 M | −32 512 000 | INVIABLE |
| dist_eth_az | ✓ ok | 0 / 0 | 2 | 2.1 M | −9 653 699 | INVIABLE |
| rxn_flash_col | ✓ ok | 0 / 0 | 3 | 3.5 M | −14 257 603 | INVIABLE |
| hydraulic | ✓ ok | 0 / 0 | 2 | 1.0 M | −6 417 282 | INVIABLE |

**Convergencia numérica: 6/6 verde** — que es exactamente el propósito del
grupo. Reactor de equilibrio, PFR cinético, loop de recycle (converge en
3 iteraciones internas), NRTL azeotrópico, tren auto-construido y bomba
auto-sized: todas las capas resuelven sin errores de masa/energía.

**Convergencia económica: 0/6.** Y a diferencia del grupo 1, **acá escalar
los EMPEORA** (ver §Por qué no convergen).

## El porqué — común y demostrado

Estos flowsheets tienen **equipo sobredimensionado y energéticamente
intensivo** (hornos de fuego S=5 000–8 000, compresores, reactores de
reformado/síntesis) para una producción **simbólica** (1 000 t/yr de base
didáctica). El resultado: un ISBL que empequeñece al revenue, en TODOS los
casos.

Sensibilidad verificada (γ sectorial + escala física consistente, vigilando
rangos de costeo):

- **γ sectorial** (1.05–1.10 commodity) mueve la aguja de forma
  despreciable: el problema NO es el overhead sobre materiales (como en cdu
  del grupo 1), sino el capital+energía de conversión vs el producto
  diminuto.
- **Escalar los EMPEORA**: al escalar caudal y tamaño de equipo en
  proporción, el ISBL (con hornos y compresores grandes) crece más rápido
  que el revenue. Ejemplos (γ=1.10):

| Ejemplo | NPV x1 | NPV x10 | NPV x20 |
|---|---:|---:|---:|
| smr_eq | −25.9 M | −138.6 M | −285.1 M |
| ethane_pfr | −17.5 M | −76.8 M | −161.5 M |
| haber_rec | −32.3 M | −174.7 M | — |
| dist_eth_az | −9.0 M | −111.6 M | −312.8 M |
| rxn_flash_col | −13.6 M | −73.1 M | −151.8 M |

Esto confirma que la escala didáctica no es "pequeña y escalable" (como
hda/biodiesel del grupo 1) sino **sobredimensionada para su producción**:
el `S` del equipo es un tamaño de demostración, no está calibrado al caudal.
Forzar viabilidad económica distorsionaría su rol de demo mínima del solver.

### Notas estructurales por ejemplo

- **smr_eq** — El "producto" es syngas crudo (CO+CO₂+H₂+CH₄, 27% metano sin
  reformar) a 180 $/tm. El horno F-101 (S=8 000) domina el capital y quema
  fuel gas; producir 1 783 t/yr de syngas no lo paga. Reformador de aula.
- **ethane_pfr** — El "producto" es **49% etano sin convertir** + 47%
  etileno, vendido a 900 $/tm (precio de etileno) sin separación downstream.
  Legítimo como demo de cinética PFR de un solo paso, pero la economía
  vende feed sin reaccionar como producto.
- **haber_rec** — **Bug de datos corregido:** el feed `S-fresh` no tenía
  precio (crm = 0, feed gratis). Ver §Corrección. El loop de recycle es su
  logro (950/1 000 = 95% de conversión vs 14% del `ammonia` sin reciclo del
  grupo 1), pero 950 t/**año** de NH₃ con loop de síntesis completo
  (compresor + horno + reciclo) es absurdamente sub-escala (plantas reales:
  1 000+ t/**día**).
- **dist_eth_az** — Cerveza diluida (12% etanol) → 95.6% etanol: misma
  energética brutal de reboiler que el `ethanol` del grupo 1. Es el ISBL
  más chico del grupo (2.1 M) pero el margen de materiales (318 k) no cubre
  los costos fijos. Único sin warnings de rango de costeo.
- **rxn_flash_col** — El etanol producto sale al **50.5%** (medio agua),
  vendido a 900 $/tm; pierde etanol en ambos wastes. Es el demo del tren
  auto-construido (reactor+flash+columna), no de una separación fina. Margen
  de materiales 14 k — prácticamente nulo.
- **hydraulic** — Bombea agua de 80 a 120 $/tm. **No es un caso económico**:
  es la demostración de auto-dimensionado de bomba y propagación hidráulica.
  Su "veredicto" económico carece de sentido por diseño.

## Corrección aplicada (2026-07-18)

Una sola corrección legítima — el bug de datos flagged en el grupo 1:

- **haber_rec**: `S-fresh` precio 0 → **180 $/tm** (mezcla N₂/H₂ commodity,
  el mismo precio que el feed de `ammonia` en el grupo 1, de composición
  idéntica). Un feed de síntesis no es gratis; crm pasa de 0 a 180 000/yr.
  Sigue INVIABLE (correctamente, es una demo de 950 t/yr), pero su economía
  ahora es **honesta y comparable** con `ammonia`.

No afecta `_golden.json` (el precio no entra al golden). **Gate 41/41
verde.**

### Por qué NO se corrigieron los otros 5

Son demostraciones de capas del solver, no casos de negocio. Su convergencia
relevante es la **numérica** (6/6), que es su propósito. Económicamente son
inviables por escala/diseño didáctico, y **escalarlos los empeora** (tabla
arriba): no hay corrección honesta que los vuelva viables sin distorsionar
su rol. Repriceear los productos impuros (ethane_pfr, rxn_flash_col) solo
los haría *más* inviables, no menos, y ninguno cambiaría de veredicto.

## Contraste pedagógico ammonia ↔ haber_rec (grupos 1-2)

Con el fix de precio, el par queda listo para su lectura didáctica:

| | ammonia (G1, sin reciclo) | haber_rec (G2, con reciclo) |
|---|---|---|
| Conversión del feed | 14.4% (1 442/10 000) | **95%** (950/1 000) |
| Feed perdido por purga | 86% a 120 $/tm | 5% (purga 50 t/yr) |
| Loop de recycle | — | ✓ converge en 3 it |
| Veredicto económico | INVIABLE (topología) | INVIABLE (escala demo) |

El reciclo demuestra su valor **técnico** (conversión 14% → 95%); la
inviabilidad de ambos es real pero por causas distintas (topología incompleta
vs escala de demostración).

## Verificación

```
python gate_examples.py               # 41/41 verde
python simulate_cli.py data/examples/haber_rec.json --economics   # crm=180k honesto
```
