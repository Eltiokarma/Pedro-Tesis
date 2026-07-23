# Casos de libro verificables (Frente 2) + decisión Perry (Frente 4)

**Sesión:** 2026-07-22 · Regresión: `tests/test_casos_libro.py` (7 tests) y
`tests/test_propiedades_mezcla.py` (14 tests).

## Método

Cada caso recomputa el valor de referencia **de forma independiente dentro
del test** — la ecuación del libro evaluada a mano, con coeficientes
copiados del libro al test (no leídos de los catálogos del repo). Si el
catálogo o la implementación se corrompen, el test falla contra el libro,
no contra sí mismo.

## Los 7 casos (test_casos_libro.py)

| # | Caso | Fuente | Qué verifica | Tolerancia |
|---|---|---|---|---|
| 1 | Bomba centrífuga S=10 kW | Turton, Tabla A.1 (base CEPCI 397) | `purchased_cost` dígito a dígito: log₁₀Cp = 3.3892 + 0.0536·log₁₀S + 0.1538·log₁₀²S → Cp ≈ 3 950 USD (2001) | 0.5 % |
| 2 | Compresor centrífugo S=1000 kW | Turton, Tabla A.1 | ídem con K = (2.2897, 1.3604, −0.1027) | 0.5 % |
| 3 | Fenske, split 95/95, α=2.5 | Seader/Henley cap. 9 | `distillation_fug.fenske` = ln[(x_D/x̄_D)(x̄_B/x_B)]/ln α ≈ 6.42 etapas | 1e-9 (fórmula), banda 6.3–6.6 |
| 4 | Underwood binario q=1 | Seader/Henley cap. 9 | raíz θ por bisección propia del test + R_min = Σαx_D/(α−θ) − 1 | 1e-3 en θ, 1e-2 en R_min |
| 5 | Bomba: W, head, NPSHr | Perry 8ª §10.4 / GPSA | W_hyd = m·ΔP/ρ; head = ΔP/ρg; NPSHr[ft] = (N√Q/N_ss)^{4/3} | exacta (identidades) |
| 6 | Compresor: T descarga | Turton §6.5 / Cengel | aire 1→5 bar, η=0.75: T_out = T·[1+((P₂/P₁)^{(k−1)/k}−1)/η] = 533.5 K; W_isen analítico | 0.1 K / 1e-6 |
| 7 | Flash isotérmico binario | Smith-Van Ness-Abbott | benceno/tolueno 50/50 a 98 °C, 1 atm: identidades V·y+(1−V)·x=z, Σx=Σy=1 (1e-6) y V_frac vs Rachford-Rice ideal resuelto por bisección propia | 0.05 en V |

Notas del caso 7: a 92 °C la mezcla está en su punto de burbuja y el flash
degenera a V=0 (el test usa 98 °C, entre burbuja y rocío, y el guard
`rr(0)>0>rr(1)` lo hace explícito). La referencia Raoult usa el MISMO
Antoine del repo (aísla la lógica Rachford-Rice/γ, no los datos).

## Frente 4 — Propiedades de mezclas y la decisión sobre Perry

### Hallazgo: la capa de calibración existía pero estaba despoblada

`thermo_db` ya estima ρ líquida por Spencer-Danner (Rackett modificada) con
**calibración experimental opcional** (`rho_ref` → backsolve de Z_RA,
"capa 7"). Pero solo 3/108 compuestos tenían `rho_ref` (glicerina, aceite
vegetal, uno más): el agua salía **876.5 kg/m³** (−12 %, el peor caso de
puente H que la propia docstring advierte), etanol 878 (+11 %).

### Acción tomada

Se poblaron `rho_ref` (CRC Handbook 97ª, tabla 3, 20 °C) para los 7
líquidos más usados de los 58 ejemplos: water 998.2, benzene 876.5,
toluene 866.9, methanol 791.8, ethanol 789.3, acetone 790.0,
acetic acid 1049.2. Con el punto calibrado, la extrapolación a 25 °C
queda <1 % (agua 993.4 vs 997.0).

**Impacto en goldens:** las densidades alimentan la hidráulica (duty de
bombas ∝ 1/ρ) → 27/58 goldens se movieron. Deltas: ≤0.6 % en ISBL, hasta
~12 % SOLO en duties sub-kW de bombas de agua (exactamente el error de ρ
corregido). Ningún status/error de bloque cambió y ningún veredicto
económico puede cambiar de signo con esos deltas (NPVs de ±millones).
Golden re-exportado con esta justificación (precedente: PR #132).

### Decisión: NO nace `perry_tables.py`

Criterio documentado, por propiedad:

| Propiedad | Estado | Decisión |
|---|---|---|
| Cp(T) líquido/gas | DIPPR-100 polinomial por compuesto, ya en `thermo_db.md` | **Suficiente** — es la misma familia de correlación de Perry cap. 2; verificado vs manual (agua 4.18, etanol 2.44) |
| ρ_liq(T) | Rackett + calibración `rho_ref` (capa 7) | **Suficiente con la capa poblada** — agregar compuestos = 1 línea `rho_ref = X kg/m3 @ T °C` en el .md, no una tabla nueva |
| ΔH_vap(T) | Clausius-Clapeyron desde Antoine (verificado: agua 2256.5 kJ/kg a 100 °C, <2 %) | **Suficiente** |
| Antoine | NIST por compuesto; no-volátiles con sentinela | **Suficiente** (excepción deliberada ya documentada) |
| Viscosidad μ(T) | **Capa 8 poblada (ciclo 4 C.1)**: `mu_ref = X mPa·s @ T °C` por compuesto en el .md (CRC 97ª, 25 °C, 10 líquidos) + Lewis-Squires desde el punto + mezcla de Arrhenius; `pressure_drop` la consume con fallback a la heurística documentada | **Suficiente con la capa poblada** — mismo patrón que `rho_ref`: agregar compuestos = 1 línea en el .md. Verificado vs CRC a 50 °C (agua +12 %, etanol +3.6 %, glicerina −2.6 % — dentro de la banda ±15 % de Lewis-Squires) |
| Conductividad k / Prandtl | **Capa 8 poblada (ciclo 4 C.1)**: `k_liq = X W/mK @ T °C` (punto CRC, sin pendiente inventada) + `prandtl_liq` (cp·μ/k) → `Pr_process` informativo en el diagnóstico del HX | **La U de sizing SIGUE saliendo de rangos por servicio** (decisión deliberada: un rating por coeficientes de película pide geometría que el alcance no modela); el Pr cierra el cross-check didáctico del inspector |

Razón de fondo: el formato `.md` por compuesto con capas (Antoine/Cp/
formación/ρ_ref) ya ES la "tabla de Perry" del proyecto, con procedencia
por línea. Un `perry_tables.py` paralelo duplicaría la fuente de verdad.
Lo que faltaba era **dato**, no infraestructura — y el dato se agrega
declarativamente al .md.
