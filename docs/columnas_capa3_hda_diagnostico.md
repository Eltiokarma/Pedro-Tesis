# Diagnóstico — intento de activación `hda/T-101` (Capa 3)

> **Veredicto: NECESITA FIX.** NO se activó la columna, NO se movió ningún
> golden, NO se tocó `hda.json`/`_golden.json`/solver/tests. El único cambio en
> el árbol es este documento. Gate `python gate_examples.py` → **41/41 verde**.
>
> **Modo:** audit-first con hard-stop. Toda la medición se hizo sobre copias
> scratch en memoria (no commiteadas). Base: rama viva con #102 (acetic/T-101
> capa 1) mergeado.

---

## 0. Qué se intentó (alcance estricto)

Activar la **única** columna de destilación real binaria que queda en un lazo
**simple**: `hda/T-101` (benceno/tolueno), con `V-101` **pasiva** (muro
congelado intencional, su activación es PR-3) y **sin tocar flow-locks ni el
tear**. Edits exactos sobre la copia scratch:

- `blocks.6` (T-101): `column_active=true`, `column_LK="benzene"`,
  `column_HK="toluene"`, `column_method="fug"`, `column_R_factor=1.5`,
  `column_x_D_LK=0.98`, `column_x_B_LK=0.02` (espejo de `distillation/T-101`,
  el mismo binario ya activo y validado).
- `streams.20` (S-7, reciclo de tolueno): `composition_locked=false`.
- `streams.21` (S-8, producto benceno): `composition_locked=false`.
- **Nada más:** S-6 (feed, id 19) sigue congelada; el tear `S-9-recic` (id 22)
  sigue pineado `[MCT]`; V-101 pasiva; ningún `mass_flow_locked` tocado.

`hda/T-101` = blk6, `eq_type="Tower (column shell)"`. Streams: S-6=19, S-7=20,
S-8=21, tear S-9-recic=22 (confirmado contra el JSON).

---

## 1. Paso 0 — baseline (sin tocar nada)

`solve(hda)` → `success=True`, mass_err=0, energy_err=0. Gate 41/41.

| stream | flujo | composición |
|---|---:|---|
| S-6 (feed col) | 9653.00 | benzene 0.7773 / toluene 0.2227 |
| S-7 (→ reciclo) | 2150.00 | **toluene 1.0** (split perfecto declarado) |
| S-8 (→ producto) | 7503.00 | **benzene 1.0** (split perfecto declarado) |
| S-9-recic (tear) | 2150.00 | toluene 1.0 (pineado) |
| S-benceno (prod) | 7503.00 | benzene 1.0 (pineado) |

`golden`: `sum_duty=-90.768789`, ISBL=9730653.53. **Pureza S-8 = 1.0.**

> El SS hand-tuned asume **separación perfecta**: el reciclo es tolueno puro
> (2150) y el producto benceno puro (7503). La conversión de R-101 (0.8045)
> está fijada para que el tolueno sin reaccionar (2150) = el reciclo.

---

## 2. Paso 2 — medición del intento

`solve(scratch)` → **`success=False`, mass_err=2**, energy_err=0.

`mass_balance_errors`:
```
E-104: ent=2038.19 sal=2150    Δ=111.809 (5.2%)
E-103: ent=7614.81 sal=7503    Δ=111.809 (1.5%)
```

| stream | base | activado | Δ |
|---|---:|---:|---|
| S-7 (reciclo) | 2150 (tol 1.0) | **2038.19** (benzene 0.02 / toluene 0.98) | −112, +2% benceno |
| S-8 (producto) | 7503 (bz 1.0) | **7614.81** (benzene 0.98 / toluene 0.02) | +112, +2% tolueno |
| S-9-recic (tear) | 2150 tol 1.0 | 2150 tol 1.0 (pineado, sin cambiar) | — |
| S-benceno | 7503 bz 1.0 | 7503 bz 1.0 (pineado, sin cambiar) | — |

- **Pureza S-8 = 0.98** (física, en rango — la columna separa bien).
- **Único warning nuevo:** `[W-ENERGY-BLOCK] T-101` — **intrínseco a toda
  columna activa** en este motor (las 6 activas existentes lo emiten); NO es
  regresión.
- `golden activ`: `overall_status="error"`, `sum_duty=15.018`.

### 2.1 El balance de la columna SÍ cierra; el de los nodos pineados NO

Balance por componente **en T-101** (in S-6 vs out S-7+S-8):

| comp | in | out | Δ |
|---|---:|---:|---:|
| benzene | 7503.28 | 7503.28 | **+0.00** |
| toluene | 2149.72 | 2149.72 | **+0.00** |

La columna conserva masa perfecto. **El error está aguas abajo**, en los nodos
pineados:

- **E-104** (S-7 → S-9-recic): entra 2038.19, sale **2150** (tear pineado) →
  se *crea* 111.8 de masa.
- **E-103** (S-8 → S-benceno): entra 7614.81, sale **7503** (producto pineado)
  → se *destruye* 111.8 de masa.

- **V-101 NO es el problema:** balancea exacto (in S-5=11481.35 = S-6 9653 +
  S-purga-H2 1828.35). La hipótesis "V-101 congelada no absorbe el arrastre"
  **no se confirma**: V-101 está consistente; el arrastre choca contra el
  **tear pineado y el producto pineado**, no contra V-101.

---

## 3. Root cause (exacto)

**Los pins aguas abajo codifican el split PERFECTO viejo; la columna real hace
un split IMPERFECTO (2% de cruce), y el lazo no puede absorber ese arrastre.**

1. La columna FUG, físicamente correcta, manda **2% de benceno al fondo**
   (reciclo) y **2% de tolueno al destilado** (producto). Eso son **111.8 t/a**
   de masa que se mueven distinto que en el split perfecto declarado.
2. El reciclo `S-9-recic` está **pineado** (mass+comp) en 2150 tolueno puro, y
   el producto `S-benceno` en 7503 benceno puro. Esos pins son el SS perfecto
   viejo → **no absorben** el arrastre del 2% → masa creada/destruida en
   E-104/E-103.
3. Para absorber el arrastre, el **lazo de reciclo de tolueno debe correr VIVO**
   (Wegstein), de modo que el benceno arrastrado recircule y el lazo encuentre
   un nuevo punto fijo. **Pero hda no converge vivo en el solver actual.**

### 3.1 Por qué el lazo no corre vivo (medido, independiente de la columna)

Al des-pinear el tear `S-9-recic` (probado con la columna **pasiva** también),
el lazo **colapsa**: `success=False`, S-1 cae de 11000 a **1866.27**,
S-6 de 9653 a 519, el reciclo a ~0. Causa exacta confirmada:

```
P-101 (nodo de mezcla feed+reciclo): ent=8959.64  sal=1866.27  Δ=7093 (79%)
S-1 (salida P-101) = 1866.27 = S-3(2347.62) − S-H2-makeup(481.35)
feed+recycle real  = 8850 + 109.64 = 8959.64   (≠ 1866.27)
```

→ El solver **back-deduce la salida del nodo de mezcla (S-1) desde aguas abajo**
(S-3 − makeup) en vez de calcularla como **Σ entradas (feed + reciclo)**. Es la
**back-deducción del tear** que el motor multi-tear (S2-B, `multitear_design.md`
§2.4/§3) resolvió para las anclas sintéticas pero que **no está cableada para la
topología "bomba-como-mezclador" de hda** (P-101 es un `Pump — centrifugal` con
2 entradas haciendo de mixer). Resultado: el lazo no puede iterar el tear y
colapsa. Esto **no depende de la columna** — es el mismo bloqueo de
"propagación en loop vivo" que `multitear_design.md` §3.1 dejó **diferido** y
que mantiene a hda_full/gas_sweet FROZEN.

---

## 4. Qué fix lo destraba

En orden:

1. **(Solver, primario) Nodo de mezcla del reciclo:** que P-101 (feed+reciclo)
   compute su salida como **Σ entradas** y **NO** se back-deduzca desde aguas
   abajo (extender la regla S2-B de no-deducción a esta topología, o insertar un
   `Mixer` explícito antes de la bomba). Sin esto, des-pinear el tear colapsa.
2. **(Solver, primario) Convergencia del tear vivo:** una vez que el nodo de
   mezcla propaga bien, correr Wegstein/Broyden sobre el tear. Probablemente
   **vectorial** (mass + composición), porque el reciclo ahora **lleva benceno**
   (ya no es tolueno puro) → el tear es {masa, comp}, no escalar.
3. **(JSON, trivial, recién DESPUÉS de 1+2) Des-pinear:**
   - `S-9-recic` (tear): pasar a calculado para que absorba el arrastre.
   - `S-benceno` (producto terminal): des-lockear comp para propagar 0.98
     benceno (mismo patrón que `S-livianos` en acetic/capa 1). Trivial pero
     inútil hasta que el lazo cierre.

**Cascada:** NO cascada a V-101 (balancea bien; S-6 frozen es consistente). Sí
cascada al **frente de reciclo-vivo / propagación de columnas en loop** (la
pieza profunda diferida del multi-tear), que es trabajo de **construir solver**,
explícitamente fuera del alcance "activar".

---

## 5. Decisión

- **NO ACTIVAR LIMPIO:** el balance de masa **no cierra** (5.2% en E-104, 1.5%
  en E-103); `overall_status=error`. No cumple el criterio de activación.
- **NECESITA FIX**, no DIFERIR-por-no-físico: la columna en sí es correcta
  (balance cierra, pureza 0.98 física, residual de la columna nulo); lo que
  falta es el **motor de reciclo vivo** que el SS perfecto-pineado evita hoy.
- **Regla de oro respetada:** no se movió el golden de hda desde un SS espurio
  (status=error). Cero cambios a la simulación.

### Próximo paso recomendado
Tratar el **reciclo-vivo de hda** como un mini-frente de SOLVER (no de
columnas): arreglar la propagación del nodo de mezcla P-101 (no back-deducir el
tear) + Wegstein vectorial del tear, validado contra el ancla sintética
multi-tear existente. Recién con eso, `hda/T-101` (y por extensión las clase-D)
se activan limpio. Esto **corrige** la suposición optimista de la Capa 3 del
plan (`columnas_activas_design.md` §4.5: "hda converge vivo") — medido: hda
**no** converge vivo hoy, por el solver, no por la columna.
