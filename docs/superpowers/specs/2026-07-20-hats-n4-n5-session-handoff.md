# SESSION HANDOFF — Sombreros N4/N5: fase de PLAN en ventana nueva

**Para:** una sesion nueva de Claude Code con modelo **Fable 5** (`claude-fable-5`).
**Fecha de origen:** 2026-07-20 · **Repo:** `C:\Users\Gamer\Music\scm\supply-chain-optimization` (cwd de la sesion suele ser el padre `...\scm` — el repo es el subdirectorio).

---

## 1. Estado exacto al momento del handoff

- La **spec esta ESCRITA, auto-revisada y aprobada por el operador** (ordeno avanzar a
  la fase de plan sin pedir cambios):
  `docs/superpowers/specs/2026-07-20-hats-n4-n5-design.md`
  Contiene: objetivo N4/N5, contratos (dataclasses), decisiones D1-D8 cerradas,
  los 4 sombreros con sus utilities exactas, costo juez, grilla determinista,
  salidas guided, runner paralelo, medicion de valor en $, tests, criterios de
  aceptacion, fuera de alcance, riesgos.
- **Nada de codigo escrito todavia. Ningun commit hecho.** La spec y este handoff
  estan UNTRACKED a proposito: la rama checked-out del repo es
  `feat/optimized-replenishment-targets` (de OTRA sesion concurrente, limpia y
  pusheada). No ensuciar esa rama; no tocar `HANDOFF.md` raiz por la misma razon.
- No existe `PIPELINE.md` en la raiz (regla de prioridad del repo: si existiera,
  ese trabajo manda — re-chequear al arrancar).

## 2. Tu accion inmediata en esta ventana (fase PLAN, modelo Fable 5)

1. Lee la spec completa (`docs/superpowers/specs/2026-07-20-hats-n4-n5-design.md`).
2. Invoca el skill **`superpowers:writing-plans`** y seguilo al pie de la letra.
3. Escribi el plan de implementacion en `docs/superpowers/plans/`
   (nombre estilo `2026-07-20-hats-n4-n5-plan.md`, o el que dicte el skill).
4. **PARA y pedile al operador que revise el plan.** No escribas codigo.

## 3. Protocolo de modelos y paradas (orden explicita del operador)

- **Fable 5 disena** (spec [hecha] + plan [tu tarea]). **Sonnet 5 implementa.**
  El operador cambia el modelo con `/model` cuando apruebe el plan.
- En la implementacion: **TDD y PARAR en cada tarea terminada** para revision del
  operador. No encadenar tareas sin parar.
- Primer commit de la rama nueva = spec + handoffs + plan (los untracked de hoy).

## 4. Reglas del repo que aplican (verificadas hoy, no re-derivar)

- Rama nueva **`feat/hats-n4-n5` desde `origin/main`** (NUNCA desde
  `feat/optimized-replenishment-targets`). Flujo: rama feature -> draft PR ->
  CI verde py3.11/3.12/3.13 -> squash. **Nunca push a main.**
- Tests: `pytest tests/ -q` con `PYTHONPATH=.` · Lint: `ruff check src tests examples`.
- **ASCII-only en prints de consola** (Windows cp1252). Markdown utf-8 ok.
- Sesiones concurrentes reales en este repo: re-chequear `git status` y el
  `HANDOFF.md` raiz JUSTO antes de crear la rama / commitear, no solo al inicio.
- Convencion de tool nueva: funciones puras `src/<x>.py` -> `jobs/<x>_job.py`
  (prepare pandas-only que lee su propio CSV, NO `intake.py`) -> `register()` en
  `scm_agent/tools.py` con `intent_keywords` multi-palabra -> ancla en
  `citation_gate` -> tests con ejemplos numericos.
- Gotcha prod: jamas un import module-level de deps de extras opcionales en la
  cadena de boot (`webapp.app -> scm_agent -> tools -> jobs -> src`). N4/N5 solo
  usa numpy/scipy/pandas (ya core), pero el plan debe recordarlo.

## 5. Hechos del codigo YA VERIFICADOS hoy (con paths — el plan puede citarlos directo)

| Que | Donde | Detalle |
|---|---|---|
| Patron de registro de tool | `scm_agent/tools.py:903-946` | `launch_readiness_tool()` (tool #41, el mas nuevo): Tool(key, title, description, intent_keywords, requires_data, prepare, run, qa, deliver, deck) |
| Anclas de citas | `scm_agent/citation_gate.py:49-162` | mapa `TOOL_CONCEPTS[tool_key] -> concept ids`; `filter_citations()`; test guardian `test_every_anchor_concept_exists` |
| Contrato guided | `src/guided.py:162-215` | `as_options(summary, options)`, `as_handoff(summary, packets)`, `recommend()`, `verify_guided()/passed_guided()`; dataclasses `ExecutionOption`, `HandoffPacket`, `Residual`, `GuidedOutcome` |
| EOQ + descuentos | `src/eoq.py` | `compute_eoq(annual_demand, holding_cost_per_unit, fixed_order_cost)`, `total_cost(...)`, `compute_eoq_volume_discount(annual_demand, holding_cost_rate, fixed_order_cost, ...)`, `PriceBreak(min_quantity, ...)` |
| Safety stock | `src/safety_stock.py` | `service_level_factor(csl)` = z, `safety_stock(demand_std_per_period, cycle_service_level, risk_periods=1.0)` |
| Politicas | `src/policies.py` | `continuous_review_sq(annual_demand, mean_demand_per_period, demand_std_per_period, ...)` -> `PolicyResult`; `periodic_review_rs(...)` |
| Fill rate + perdida normal | `src/fill_rate.py` | `normal_loss_standard(x)` = L_N(z) (linea 42), `fill_rate_from_safety_stock(safety_stock, cycle_demand, demand_std_risk)`, `safety_stock_for_fill_rate`, `inverse_standard_loss` |
| KPIs financieros | `src/financial_kpis.py` | `gmroi(gross_margin_value, average_inventory_cost)`, `days_inventory_outstanding`, `inventory_turns`, `cash_to_cash` |
| Working capital | `src/working_capital.py` | `working_capital(*, revenue, cogs, dio, dso, dpo)`, `cash_release_plan(...)` |
| Baseline actual | `scm_agent/tools.py:53,80-131` + `jobs/inventory_deliverable.py:29` | tool `inventory_optimization` -> `jobs/inventory_optimization.run`; `service_level` default **0.95**; (s,Q) clasico sin descuentos |
| Mode (no tocar) | `scm_agent/modes.py:42-56` | frozen dataclass {key,label,persona,tool_keys,deliverables,kpis}; direccion de dependencia `scm_agent -> src` (Hat vive en `src/` sin importar scm_agent) |
| CSV testbed | `data/sample_demand_portfolio.csv` | semanal: `date,product_id,quantity,unit_cost,lead_time_days` — SIN precio ni tarifario (origen de D3/D8) |

## 6. Decisiones cerradas D1-D8 (detalle en la spec; NO re-abrir salvo que el operador lo pida)

1. **D1** grilla 2D (Q x SL) anclada en `Q_eoq`/`Q_disc` analiticos + candidatos obligatorios.
2. **D2** normalizacion min-max por sombrero sobre la grilla; concesion = `1 - u_norm`.
3. **D3** quiebre = venta perdida a margen; `gross_margin_rate` default 0.30.
4. **D4** pesos inyectables, default iguales; "pesos = politica del operador" visible.
5. **D5** `h_total 0.25 = h_oop + WACC 0.12`; juez usa h_total, CFO solo el slice WACC; validar `0 < WACC < h_total`.
6. **D6** dos tools (`hat_tension`, `hat_settlement`) sobre UN `jobs/hats_job.py`; comando unico = `examples/run_hats.py`.
7. **D7** `Hat` en `src/hats.py` al lado de `Mode`, sin importarlo; `mode_key` soft-link.
8. **D8** `price_breaks` inyectable; default sintetico -2%@2xEOQ / -4%@4xEOQ etiquetado `(assumed)`.

## 7. Riesgos que el PLAN debe convertir en tareas explicitas

- Grounding de anchors nuevos contra el books graph + `EXCLUDED_CONCEPTS` si hay
  falso amigo ("settlement" financiero) — leccion PR #164.
- Test de equivalencia `baseline_plan()` (espejo puro) == politica real de
  `jobs/inventory_optimization`.
- Nunca `EXECUTED` en ninguna de las dos tools (test).
- Salida del runner: N4 y N5 JUNTOS, ASCII puro, delta $ con signo + fila TOTAL + agreement@1.
- Cobertura >= 80% en modulos nuevos.
