# Spec — Sombreros N4 (tension) y N5 (settlement) sobre la decision de reabastecimiento

**Fecha:** 2026-07-20 · **Estado:** BORRADOR — pendiente de confirmacion del operador
**Disenado por:** Fable 5 (fase de lineamientos) · **Implementa:** Sonnet 5 (fase de codigo)
**Rama objetivo:** `feat/hats-n4-n5` desde `origin/main` (NO desde `feat/optimized-replenishment-targets`) -> draft PR -> CI verde py3.11/3.12/3.13 -> squash

---

## 1. Objetivo

Dos capacidades nuevas routables por el orquestador que corren EN PARALELO sobre la misma
decision de reabastecimiento (cuanto pedir Q + nivel de servicio SL para un SKU):

- **N4 `hat_tension`** — 4 sombreros puntuan la MISMA decision; salida = mapa de desacuerdo
  como guided `OPTIONS`. El humano resuelve. NO reconcilia. **Vende claridad.**
- **N5 `hat_settlement`** — mismos sombreros + motor de reconciliacion (suma ponderada de
  utilidades normalizadas) -> UN plan (Q*, SL*) + acta de concesiones, como guided `HANDOFF`.
  **Vende la decision ya tomada.**

Substrato compartido construido UNA vez: "cada sombrero puntua un candidato (Q, SL)".
N4 renderiza la tension; N5 agrega el settlement. Valor medido en $ contra el baseline actual.

## 2. Conceptos y contratos (dataclasses frozen, `src/`)

Direccion de dependencia respetada: todo vive en `src/` sin importar `scm_agent`
(D7). `Hat` NO envuelve `Mode`; lleva un soft-link opcional `mode_key: str | None`.

```
Hat            = {key, label, objetivo, kpis: tuple[str,...], tool_keys: frozenset[str],
                  mode_key: str|None}          # la utility es una funcion pura aparte, no un campo
HatInputs      = {sku, annual_demand, mean_weekly, std_weekly, lead_time_weeks,
                  unit_cost, price_breaks: tuple[PriceBreak,...], params_efectivos}
Candidate      = {order_quantity, service_level}
HatEvaluation  = {hat_key, candidate, utility_raw, utility_norm, kpis: dict}
TensionMap     = {sku, ideals: dict[hat_key, HatEvaluation], clashes: tuple[Clash,...],
                  candidates_evaluated: int}
Clash          = {hat_a, hat_b, delta_q, delta_capital_usd, delta_fill_rate}
Settlement     = {sku, chosen: Candidate, weights, acta: tuple[ActaEntry,...],
                  judge_cost_chosen, judge_cost_baseline, value_vs_baseline_usd}
ActaEntry      = {hat_key, ideal: Candidate, utility_norm_at_chosen,
                  concesion: float,           # 1 - utility_norm_at_chosen, en [0,1]
                  kpi_ideal, kpi_chosen}      # el KPI propio del sombrero en sus unidades
```

## 3. Decisiones de diseno (D1-D8) — cambiables por el operador

**D1 — Dominio del settlement: grilla 2D (Q x SL), no eleccion entre 4 ideales.**
El settlement elige sobre `SL_GRID = (0.90, 0.925, 0.95, 0.975, 0.99)` x 25 puntos de Q
lineales entre `[0.5 * min(Q_eoq, Q_disc), 1.25 * max(Q_eoq, Q_disc)]`, donde los DOS
anclajes analiticos cerrados son `Q_eoq` (`compute_eoq` clasico) y `Q_disc` (mejor Q de
`compute_eoq_volume_discount`) — se calculan ANTES de la grilla, sin circularidad. A la
grilla se agregan como candidatos obligatorios `Q_eoq`, `Q_disc` y el Q del baseline
(dedupe). El ideal de cada sombrero se define DESPUES como argmax de su utility sobre
la grilla (seccion 6); CFO y Comercial caen en esquinas de la grilla por diseno.
Alternativa rechazada: elegir solo entre 4 ideales — colapsa la reconciliacion en una
votacion y el acta pierde el punto medio genuino.

**D2 — Normalizacion: min-max por sombrero sobre el candidate set completo.**
`u_norm = (u - min) / (max - min)` sobre TODOS los candidatos evaluados; 1 = su ideal,
0 = su peor caso en esta grilla. Interpretable ("comprador esta al 73% de su ideal") y
la concesion del acta sale directa (`1 - u_norm`). Borde: `max == min` -> 0.5 constante.
Alternativas rechazadas: z-score (no acotado, acta ilegible), ratio-al-baseline (mezcla
la vara de medir con una de las opciones).

**D3 — Costo de quiebre: venta perdida a margen unitario.**
`p_short = precio - unit_cost` con `precio = unit_cost / (1 - gross_margin_rate)`;
`gross_margin_rate` inyectable, default **0.30** (el CSV no trae precio). Cortes
esperados/anio = `(D/Q) * sigma_L * L_N(z(SL))` usando `normal_loss_standard` +
`service_level_factor` ya existentes en `src/fill_rate.py` / `src/safety_stock.py`.
Alternativa rechazada: costo de backorder por unidad-tiempo (pide un dato que el
retailer chico no tiene).

**D4 — Pesos = POLITICA explicita, no consenso objetivo.**
`weights` inyectable (`cfo=0.4,planner=0.3,...`); default **iguales (0.25 c/u)**.
Validacion: solo los 4 keys conocidos, ninguno negativo, suma > 0 -> se renormaliza a 1.
"De quien son los pesos" se documenta como eleccion de politica del operador en el
docstring del motor Y en la salida impresa/entregable (residual del HandoffPacket).

**D5 — Sin doble conteo de capital: descomponer h_total.**
Repo default `h_total = 0.25`/anio (incluye capital). Se descompone:
`capital = WACC` (inyectable, default **0.12**) y `h_oop = h_total - WACC` (bodega,
seguro, merma). El costo juez usa `h_total` (equivalente al costo clasico); el sombrero
CFO usa SOLO el slice `WACC * valor_inventario_promedio`. Validacion: `0 < WACC < h_total`
o error claro. Asi el requisito "costo de capital = capital de trabajo x WACC" queda
como componente explicito sin sumar el capital dos veces.

**D6 — Dos tools registradas, UN modulo job compartido.**
`hat_tension` y `hat_settlement` en `scm_agent/tools.py` (el orquestador "rutea ambos"),
ambas sobre `jobs/hats_job.py` (un solo `prepare()` pandas — mismo CSV, mismos inputs —
y `run_tension()` / `run_settlement()`). El requisito de UN comando con ambas salidas
juntas lo cumple `examples/run_hats.py` (seccion 8). Alternativa rechazada: una sola
tool que devuelva `{"level4","level5"}` — pierde el ruteo por intencion diferenciado
("quiero ver el conflicto" vs "decidime").

**D7 — `Hat` vive al lado de `Mode`, nunca lo envuelve.**
`src/` no puede importar `scm_agent` (direccion de dependencia verificada). `modes.py`
queda intacto; `mode_key` es un string suelto como referencia blanda.

**D8 — Price breaks del comprador: inyectables, con default sintetico ETIQUETADO.**
El CSV no trae tarifario. `params["price_breaks"]` acepta `[(min_qty, unit_price), ...]`.
Default determinista para el testbed: breaks en `2x EOQ` (-2%) y `4x EOQ` (-4%) sobre
`unit_cost`. Toda salida que use el default lo marca `(assumed)` — en cliente real
vienen del tarifario del proveedor. Sin esto el comprador colapsa al EOQ clasico y la
tension del testbed se debilita.

## 4. Los 4 sombreros (testbed, motores existentes verificados)

Inputs por SKU desde `data/sample_demand_portfolio.csv` (semanal:
`date,product_id,quantity,unit_cost,lead_time_days`): `mu_w`, `sigma_w` (ddof=1),
`D = 52*mu_w`, `L_w = lead_time_days/7`, `SS(SL) = safety_stock(sigma_w, SL, risk_periods=L_w)`,
`sigma_L = sigma_w * sqrt(L_w)`, `c(Q)` por tramos de `price_breaks` (c base si no aplica).

Utility cruda por candidato (Q, SL) — mayor = mejor. Ideal de cada sombrero =
argmax sobre la grilla con tie-break global (seccion 6).

| Sombrero | key | Utility cruda | Ideal esperado | Motor |
|---|---|---|---|---|
| Comprador | `comprador` | `-(c(Q) + K/Q)` (costo unitario efectivo; plano en SL) | Q grande (break de descuento) | `compute_eoq_volume_discount`, `PriceBreak` (`src/eoq.py`) |
| Planner | `planner` | `-(K*D/Q + h_total*c(Q)*(Q/2 + SS(SL)))` si `SL >= sl_target` (0.95 default); si no: `u = u_min_valido - (sl_target - SL) * rango_valido` con `rango_valido = max(u_max_valido - u_min_valido, 1.0)` — finito, estrictamente peor que todo candidato valido, ordenado por deficit | Q moderado (~EOQ) a SL 0.95 | `continuous_review_sq` (`src/policies.py`), `safety_stock` |
| CFO | `cfo` | `-(WACC * c(Q) * (Q/2 + SS(SL)))` (cargo de capital sobre inventario promedio) | Q chico, SL bajo (esquina honesta) | `working_capital.py`; KPIs `gmroi`, `days_inventory_outstanding` (`src/financial_kpis.py`) |
| Comercial | `comercial` | `fill_rate_from_safety_stock(SS(SL), Q, sigma_L)` (beta) | SL alto, Q alto (esquina honesta) | `src/fill_rate.py` |

Las "esquinas honestas" de CFO y Comercial son el punto: son los egoistas puros; el
settlement existe para balancearlos y el acta muestra que cede cada uno.

## 5. Funcion de costo JUEZ (valuacion neutral, no es la utility de nadie)

```
C(Q, SL) = D*c(Q)                                  # compra anual (captura descuentos)
         + K*D/Q                                   # ordenar
         + h_total * c(Q) * (Q/2 + SS(SL))         # mantener (h_oop + WACC, sin doble conteo)
         + p_short * (D/Q) * sigma_L * L_N(z(SL))  # quiebre esperado (D3)
```

Defaults inyectables (coherentes con los genericos del repo): `K = 75`,
`h_total = 0.25`, `WACC = 0.12`, `sl_target = 0.95`, `gross_margin_rate = 0.30`.
Nota de honestidad documentada: minimizar C directamente seria una quinta politica
(pesos implicitos en los coeficientes); el modelo de sombreros hace el trade-off
explicito y auditable. El juez solo VALUA, no decide.

**Baseline (a) = lo que Kern hace hoy:** espejo puro de la politica actual de
`inventory_optimization` (`jobs/inventory_optimization.py`): `continuous_review_sq`
a `service_level = 0.95`, costo unitario constante (sin descuentos). Se implementa
`baseline_plan()` en `src/hats.py` (funcion pura, sin depender del job) y se documenta
la equivalencia; el plan de implementacion la verifica contra el job real con un test.

## 6. Determinismo

Grilla en orden fijo (SL asc, luego Q asc). Ideal por sombrero y settlement usan el
mismo tie-break: (1) menor `C` juez, (2) menor Q, (3) menor SL. Sin aleatoriedad en
ninguna parte. Mismos inputs -> bytes identicos en la salida.

## 7. Salidas guided (contrato never-unprotected intacto)

- **N4** -> `as_options(summary, [5 ExecutionOption])`: una opcion por ideal de sombrero
  + una por el baseline. `score` = juez normalizado (mejor costo = score mas alto),
  etiquetado "orden informativo por costo total — la eleccion es humana". Cada opcion
  lleva el trade-off explicito en su descripcion (los KPIs de los 4 sombreros evaluados
  en ESA opcion). Los `clashes` top-3 por magnitud $ van en el summary.
- **N5** -> `as_handoff(summary, [HandoffPacket])`: packet "Aplicar plan reconciliado
  (Q*, SL*)" con pasos, el acta como artefacto pre-llenado, y `Residual`: "los pesos
  son politica del operador, no consenso objetivo". Writeback FUERA de alcance; si un
  dia toca sistema de registro pasa por `src/writeback.py` (irreversible = humano).
- Ninguna de las dos tools emite `EXECUTED` jamas (test lo fija). Ambas salidas deben
  pasar `verify_guided` / `passed_guided`.

## 8. Runner paralelo (el requisito central)

`examples/run_hats.py` — UN comando, AMBAS salidas lado a lado, ASCII-only:

```
python examples/run_hats.py --sku SKU-A \
  [--csv data/sample_demand_portfolio.csv] \
  [--weights cfo=0.4,planner=0.3,comprador=0.2,comercial=0.1] \
  [--wacc 0.12] [--margin 0.30] [--sl-target 0.95] [--all]
```

Imprime: `== NIVEL 4: MAPA DE TENSION ==` (tabla ideales + KPIs + choques) y
`== NIVEL 5: SETTLEMENT ==` (Q*, SL*, acta de concesiones) y
`== VALOR ==` (tabla seccion 9). `--all` (sin `--sku`): todos los SKUs + fila TOTAL +
agreement@1. Sin args obligatorios mas alla del CSV default -> corre demo completa.

## 9. Medicion de valor agregado (el NUMERO)

Tabla impresa por el runner y reproducida por test:

| SKU | C_baseline (a) | C_comprador | C_planner | C_cfo | C_comercial (b) | C_N5 (c) | **Delta $ = a - c** |

- **Valor N5** = `C_baseline - C_N5` en $, por SKU y agregado (fila TOTAL). Con signo:
  puede ser negativo bajo pesos extremos — eso ES informacion (cuanto cuesta esa
  politica de pesos), se reporta sin maquillar.
- **Valor N4 (distinto, se reporta aparte):** `agreement@1` = % de SKUs donde la opcion
  top-1 de N4 (por juez) coincide con el settlement N5 (mismo candidato tras snap a
  grilla), + transparencia = los 4x KPIs expuestos por opcion. N4 vende claridad;
  N5 vende la decision ya tomada. La "eleccion humana" real no es simulable offline;
  agreement@1 es su proxy declarado.

## 10. Registro, routing y grounding

- `scm_agent/tools.py`: `hat_tension_tool()` y `hat_settlement_tool()` siguiendo el
  patron exacto de `launch_readiness_tool()` (prepare/run/qa/deliver/deck).
  `requires_data=True`.
- `intent_keywords` (multi-palabra, es/en):
  - tension: `"mapa de tension"`, `"tension entre areas"`, `"conflicto compras finanzas"`,
    `"trade-off entre roles"`, `"perspectivas de la decision"`, `"decision tension map"`,
    `"cuanto pedir segun cada area"`
  - settlement: `"plan reconciliado"`, `"reconciliar la decision"`, `"acta de concesiones"`,
    `"decision unica ponderada"`, `"reconciled order plan"`, `"consenso ponderado de compra"`
- `scm_agent/citation_gate.py`: dos entradas nuevas en `TOOL_CONCEPTS`, sembradas desde
  los anchors actuales de `inventory_optimization` (+ working-capital para settlement).
  Riesgo falso-amigo conocido ("settlement" financiero, leccion PR #164): la
  implementacion verifica el grounding contra el books graph y usa `EXCLUDED_CONCEPTS`
  si aparece un falso amigo. `test_every_anchor_concept_exists` protege.
- Titles groundables: `"Decision Tension Map (Replenishment)"` y
  `"Reconciled Replenishment Plan"` (terminos SCM anclables, no "settlement" a secas).

## 11. Archivos

| Archivo | Contenido | Tamano aprox |
|---|---|---|
| `src/hats.py` | Hat, HatInputs, grilla, 4 utilities, normalizacion, `baseline_plan()`, juez `decision_cost()` | ~350 lin |
| `src/hat_council.py` | `tension_map()` (N4), `settle()` + acta (N5), `agreement_at_1()`, datos de la tabla de valor | ~250 lin |
| `jobs/hats_job.py` | `prepare()` pandas-only (lee su CSV, NO intake.py), `run_tension/run_settlement`, `verify_*`, `write_operational`, `build_deck` | ~300 lin |
| `scm_agent/tools.py` | +2 `register()` (patron launch_readiness) | +~90 lin |
| `scm_agent/citation_gate.py` | +2 entradas `TOOL_CONCEPTS` | +~10 lin |
| `examples/run_hats.py` | runner paralelo N4+N5+valor | ~150 lin |
| `tests/test_hats.py`, `tests/test_hats_settlement.py`, `tests/test_hats_job.py`, `tests/test_hats_valuation.py` | seccion 12 | ~4 archivos |

## 12. Tests (TDD, ejemplos numericos a mano en comentarios)

1. `test_hats.py` — substrato: con breaks sinteticos, orden `Q_cfo <= Q_planner <= Q_comprador`;
   ideal comercial = SL max de grilla; `u_norm(ideal) == 1`; grilla determinista que
   contiene ideales + baseline; validaciones (pesos negativos/suma 0 -> ValueError;
   `WACC >= h_total` -> ValueError).
2. `test_hats_settlement.py` — `w_x = 1` colapsa al ideal del sombrero x (los 4 casos);
   pesos iguales -> Q* en `[min_ideal, max_ideal]`; tie-break determinista; acta:
   concesion en [0,1] y == 0 cuando chosen == ideal.
3. `test_hats_job.py` — sin CSV -> `needs_data`; weights malformados -> `needs_clarification`;
   tension -> `OPTIONS` + `passed_guided`; settlement -> `HANDOFF` + `passed_guided`;
   NUNCA `EXECUTED`; ruteo por intencion a cada tool.
4. `test_hats_valuation.py` — juez verificado con cuentas a mano sobre un SKU sintetico;
   `C_baseline - C_N5` reproducible sobre el sample CSV; `agreement@1` en [0,1];
   salida del runner es ASCII puro; baseline == politica de `inventory_optimization`
   (test de equivalencia).
5. Extension de `test_citation_gate.py` — anchors de ambos tools existen en el grafo.
   Cobertura >= 80% en los modulos nuevos.

## 13. Criterios de aceptacion (pass/fail)

1. `python examples/run_hats.py --sku SKU-A` imprime N4 y N5 juntos, ASCII, exit 0.
2. El orquestador rutea "mapa de tension entre areas" -> `hat_tension` y
   "plan reconciliado de compra" -> `hat_settlement` (test de intent).
3. Con `--weights cfo=1` el settlement == ideal CFO (idem los otros 3).
4. Delta $ por SKU y agregado impreso y reproducido por test.
5. Ambos outcomes pasan `verify_guided`; ninguno es `EXECUTED`.
6. CI verde en py3.11/3.12/3.13; `ruff check src tests examples` limpio.
7. `TOOL_CONCEPTS` cubre ambos tools y todos sus concept ids existen en el grafo.
8. Todos los defaults (K, h_total, WACC, margen, sl_target, pesos, price_breaks)
   inyectables via `params`; "pesos = politica" visible en salida y docstring.

## 14. Fuera de alcance

Writeback/ERP (N5 termina en HANDOFF); UI/Tower; modos nuevos en `modes.py`;
optimizacion conjunta multi-SKU (todo es per-SKU); pesos aprendidos/calibrados;
paquete comercial en `packages.py` (posible follow-up).

## 15. Riesgos y mitigaciones

| Riesgo | Mitigacion |
|---|---|
| Anchors falso-amigo ("settlement" financiero) | verificacion de grounding + `EXCLUDED_CONCEPTS` (leccion PR #164) |
| Breaks sinteticos leidos como dato real | etiqueta `(assumed)` en toda salida que use el default D8 |
| Doble conteo de capital | descomposicion D5 con validacion `WACC < h_total` |
| Min-max sensible a bordes de grilla | bordes anclados a cantidades analiticas (D1) |
| Sesiones concurrentes en el repo | rama nueva desde `origin/main`; re-chequear `git status` + HANDOFF.md justo antes de implementar |
| Delta $ negativo malinterpretado | se reporta con signo + nota de politica (seccion 9) |

## 16. Flujo despues de esta spec

1. Operador confirma/ajusta esta spec.
2. `superpowers:writing-plans` -> plan de implementacion en `docs/superpowers/plans/`
   (aun con Fable 5).
3. Cambio de modelo a Sonnet 5 -> implementacion TDD por tareas, parando en cada
   tarea terminada. Commit de spec + plan como primer commit de la rama.
