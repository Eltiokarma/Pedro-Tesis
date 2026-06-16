# Diagnóstico — intento de `hda_full` vivo (V-101 flash + 3 columnas + Broyden)

> **Veredicto: NECESITA FIX / DIFERIR.** NO se activó nada, NO se movió ningún
> golden, `hda_full.json` / `_golden.json` / solver intactos. El único cambio en
> el árbol es este documento. Gate `python gate_examples.py` → **41/41 verde**.
>
> **Modo:** audit-first con hard-stop. Toda la medición sobre copias scratch en
> memoria (no commiteadas). Base: rama viva con #106 (ciclos port-aware).

---

## 0. Prerrequisito (#106) — OK

`_scc_circuit_rank(hda_full)` = **2**, back-edges `[S-gas-pre, S-tol-recic]` (sin
el ciclo falso S-3/S-4 del HX feed-efluente). #106 está en la rama viva.

## 1. Qué se intentó

Activar el lazo acoplado gas+tolueno de hda_full en vivo:
- **V-101** flash V/L: `flash_active=True`, condiciones físicas medidas del feed
  S-5 (sale del cooler E-102): **T=318.15 K (45 °C), P=25 bar** (no el
  placeholder 298/1.013).
- **3 columnas** con sus keys reales (medidos de feeds/outputs):
  - T-101 estabilizador: LK=**methane**, HK=**benzene** (saca gas ligero).
  - T-102 columna de benceno: LK=**benzene**, HK=**toluene**.
  - T-103 columna de tolueno: LK=benzene, HK=toluene (**split débil**).
- Reciclos `S-gas-recic`/`S-tol-recic` → role=recycle, des-lockeados; lazo
  interno des-lockeado (escenario vivo).

## 2. Resultado: el lazo COLAPSA

`solve()` → `success=False`, `energy_err=1`. **Broyden corre sobre los 2 tears**
(combinados `S-gas-pre+S-tol-recic`) — el wiring multi-tear funciona — pero el
tear **colapsa a 0**:

```
tear history: 28527 → 14263 → 7132 → 3566 → 1783 → 891 → … → 0   (decae ×0.5)
S-liq=0, S-8=0, S-10=0  → interior del loop colapsado
```

→ punto fijo espurio (regla de oro: NO se mueve el golden desde acá).

## 3. Descomposición del blocker (medido pieza por pieza)

### 3.1 Flash V-101 — ✅ FÍSICO (NO es el blocker)
Aislando el flash (solo V-101 activo, resto closure) sobre el feed real
S-5 (93305: methane 0.227 = 21143, H₂ 0.023 = 2109, benzene 0.622, toluene 0.129):

| salida | masa | composición |
|---|---:|---|
| S-gas-recic (vapor) | **25525** | methane 0.807 / H₂ 0.082 / benzene 0.103 / tol 0.008 |
| S-liq (líquido) | **67779** | benzene 0.818 / toluene 0.174 / methane 0.008 |

El flash captura ~todo el methane (20600/21143) + todo el H₂ + algo de benceno
(2629) al vapor. Es **físicamente correcto** y usa el path de flash. El vapor
real (25525) es **mayor** que el hardcode (21164) porque arrastra benceno.

### 3.2 Tears correctos — ✅ (#106)
Broyden se dispara sobre `{S-gas-pre, S-tol-recic}` (los 2 reciclos reales). La
selección de tear y el dispatch multi-tear funcionan.

### 3.3 BLOCKER #1 — **purga a masa fija** (`S-purga`)
`S-purga` (K-101 → TK-102, producto) está **lockeada a 10582** — un valor
calibrado para el vapor hardcodeado VIEJO (21164, split 50/50). El gas que
recicla es `S-gas-pre = S-gas-recic − S-purga`. Con el flash real (vapor 25525,
y variando al iterar) y la purga **fija** en 10582:
- mass error medido en **K-101: ent=25525, sal=21164, Δ=4360 (17 %)** y en
  **E-103: Δ=4360 (6 %)** — los locks downstream codifican el split viejo.
- al iterar el lazo vivo, cuando `S-gas-recic` baja, `S-gas-pre → 0` → el
  reciclo de gas se **estrangula** → colapso.

Es exactamente lo que `multitear_design.md` §3.1 anticipó: *"hda_full está
underdetermined por el lock de purga a masa fija; racionalizándolo a fracción
(φ = S-purga/S-gas-recic ≈ 0.5) el loop pasa a estar determinado."* La purga
debe ser una **fracción** del gas, no una masa fija.

### 3.4 BLOCKER #2 — locks downstream del flash codifican el split viejo
`S-gas-pre`, `S-purga`, `S-6` (y la cadena) están dimensionados para
vapor=21164 / líquido=72140. El flash real da 25525 / 67779 (+4360 de benceno
al vapor). Todos deben des-lockearse y re-derivarse del flash.

### 3.5 BLOCKER #3 (pendiente de re-test) — propagación del reciclo de tolueno
`multitear_design.md` §3.1 reportó que, aun con la purga racionalizada, *"el
reciclo de tolueno colapsa a 0 porque el tren de destilación no propaga el
reciclo de tolueno en la pasada viva"*. Ese reporte es **anterior** a #103/#104
(selección de tear) y #106 (ciclos port-aware), que ya limpiaron la estructura
(rank 2, tears correctos). **Hay que re-medir** tras resolver los blockers #1/#2:
puede que ya propague, o que persista como pieza profunda.

## 4. Por qué se difiere (regla de salida)

El scope era "activar V-101 + keys + Broyden". Medido: **el flash y los tears ya
funcionan**; lo que falta es **racionalizar la purga a fracción + des-lockear y
re-derivar los downstream del flash** (blockers #1/#2), y recién entonces
re-medir la propagación del tolueno (#3). Eso es trabajo de **racionalización de
locks + re-balanceo del split de gas**, fuera de "activar". No se fuerza ni se
congela a mano (Broyden no baja el residual real → es DIFERIR honesto).

## 5. Próximo sub-paso (descompuesto)

1. **Racionalizar la purga**: `S-purga` de masa fija → **fracción** del gas
   (splitter en K-101, φ≈0.5 medido), de modo que el split gas-pre/purga siga al
   vapor real del flash.
2. **Des-lockear y re-derivar** los downstream del flash (`S-gas-pre`, `S-6`,
   `S-gas-recic`, `S-liq`) — que el flash maneje el split V/L y la cadena
   propague.
3. **Re-medir Broyden** sobre los 2 tears con la purga ya racionalizada:
   - si converge y cierra masa → ACTIVAR (golden nuevo de hda_full).
   - si el reciclo de tolueno aún colapsa → blocker #3 (propagación de columnas
     en loop vivo), pieza profunda, sub-frente propio.
4. Revisar **T-103** (split débil casi trivial): confirmar si separa de verdad o
   conviene tratarla como splitter.

**Anclas que YA funcionan y no hay que reconstruir:** flash V/L EOS de V-101
(físico), selección de tear (#103/#104), ciclos port-aware (#106), dispatch
Broyden multi-tear. El frente restante es **racionalización de locks de la purga
+ re-balanceo del split de gas**, no motor nuevo.
