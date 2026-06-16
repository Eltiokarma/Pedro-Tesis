# Diagnóstico — `hda_full` vivo, lazo de tolueno: blocker = propagación de masa NO port-aware en HX de 4 puertos

> **Veredicto: NECESITA FIX / DIFERIR.** NO se activó nada, NO se movió ningún
> golden, `hda_full.json` / `_golden.json` / solver intactos. El único cambio en
> el árbol es este documento. Gate `python gate_examples.py` → **41/41 verde**.
>
> **Modo:** audit-first con hard-stop. Medición sobre copias scratch en memoria.
> Base: rama viva con #106 (ciclos port-aware). Prerrequisito rank(hda_full)=2 ✅.

---

## 0. Avance respecto del diagnóstico previo

El diagnóstico anterior (`hda_full vivo` ronda 1) dejó: flash V-101 físico ✅,
tears correctos ✅, y como blockers **#1 purga a masa fija** y **#3 propagación
de tolueno (re-test pendiente)**. Esta ronda **resolvió #1** y **aisló #3 a su
mecanismo exacto**.

### Lo que YA cierra (aplicado en scratch)
- **V-101 flash** (`flash_active`, 318.15 K, 25 bar): físico, EOS.
- **Purga → fracción**: `K-101 splitter_active` con fracciones → el **lazo de
  gas converge** (Broyden: tear S-gas-pre 28527→…→10603, estable).
- **T-101** (LK=methane/HK=benzene) y **T-102** (LK=benzene/HK=toluene) activas.
- **T-103**: es una columna **degenerada** (su feed es tolueno 0.986/benceno
  0.014 y ambas salidas son ~tolueno puro → no hay nada que destilar; el HDA
  real separaría tolueno de **pesados/difenilo** que este flowsheet NO modela).
  Modelada correctamente como **splitter** (split de paso, conserva masa/comp),
  no como FUG (que producía basura).

## 1. El blocker, aislado y confirmado

Con todo lo anterior, el lazo de **tolueno/líquido colapsa**: `S-10` (benceno
producto) = 0, `S-11` = 605 (vs 11996), `S-tol-recic` = 13.9. Broyden reporta
`converged=True` sobre un **SS espurio** (regla de oro: no se acepta).

**Causa raíz, aislada:** la **propagación de masa hacia adelante a través del HX
feed-efluente `E-101` (4 puertos) NO es port-aware.**

`E-101` (tube = feed S-1→S-2; shell = efluente R-101 S-4→S-4b). Test aislado
(resto en baseline/closure):

| streams des-lockeados | S-1 (tube_in) | S-2 (tube_out) | resultado |
|---|---:|---:|---|
| solo `S-2` | 80168 | **80168** | ✅ propaga (el otro lado lo ancla) |
| `S-2` + `S-4` + `S-4b` (ambos lados) | 80168 | **0** | ❌ **COLAPSA** |

Cuando **un solo lado** está libre, la propagación funciona (el lado anclado lo
fija). Cuando **ambos lados** están libres —la condición real del loop vivo— la
propagación **no parea inlet↔outlet por lado** (tube_in→tube_out,
shell_in→shell_out) y **ambas salidas colapsan a 0**. `mass_err=0` porque el
balance degenerado (0=0) "cierra".

**Cascada:** S-2=0 → F-101/R-101 sin feed → efluente 0 → flash sin feed → tren
líquido (T-101/T-102/T-103) hambriento → reciclo de tolueno → 0. El "converged"
de Broyden es falso (interior colapsado).

## 2. Por qué #106 no lo cubre

#106 hizo **port-aware la DETECCIÓN DE CICLOS** (`_decompose_scc_cycles` /
`_scc_circuit_rank`): la *estructura* del grafo ya no cruza lados (rank 2 ✓).
Pero la **PROPAGACIÓN DE MASA** del forward pass (`_solve_mass_iteration` /
`auto_propagate_compositions`) sigue tratando el HX como un nodo único: suma
todas las entradas y no sabe parear cada salida con la entrada de su lado.
Mientras un lado estuvo lockeado (todos los goldens, closure), nunca se ejerció;
hda_full vivo es el primer caso con **ambos lados libres**.

## 3. El fix (próximo sub-paso, bien acotado)

**Propagación de masa port-aware para HX de 4 puertos** — el análogo de #106
pero en el forward pass:
- En `_solve_mass_iteration` / la propagación, para un bloque HX de 4 puertos
  parear **inlet↔outlet por lado** (reusar `_stream_side` / `_portaware_nodes`
  de #106): `m(tube_out) = m(tube_in)`, `m(shell_out) = m(shell_in)`, y propagar
  la composición de cada entrada a la salida de su mismo lado.
- Es un cambio de **solver** (propagación), no de datos; fuera del scope
  "activar V-101 + keys + Broyden" de esta tarea.
- Riesgo gate: los 40 + hda no tienen HX de 4 puertos con ambos lados libres
  (sus tears están locked) → debería quedar byte-idéntico; verificar.

Con eso resuelto, re-medir el lazo de tolueno: el flash, la purga-fracción, las
columnas y Broyden YA funcionan; el HX es el único eslabón que rompe el forward
pass vivo.

## 4. Resumen

| pieza | estado |
|---|---|
| V-101 flash EOS | ✅ físico |
| Purga → fracción (K-101 splitter) | ✅ destraba el gas |
| T-101 / T-102 activas | ✅ |
| T-103 como splitter (degenerada) | ✅ (no hay pesados que separar) |
| Broyden multi-tear (gas + tolueno) | ✅ corre |
| **Propagación de masa en HX 4-puertos (forward pass)** | ❌ **BLOCKER** — no port-aware; con ambos lados libres colapsa |

**Decisión:** DIFERIR. El frente restante es **una** pieza de solver bien
acotada (propagación port-aware en HX de 4 puertos), no una reescritura amplia.
No se fuerza ni se congela a mano (Broyden da un converged falso → DIFERIR
honesto). Cero cambios a la simulación.
