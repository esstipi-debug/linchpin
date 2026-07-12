# Linchpin 3.0 — Documento de desarrollo exhaustivo
**Versión:** 1.0 · **Fecha:** 12 jul 2026 · **Repo base:** [esstipi-debug/linchpin](https://github.com/esstipi-debug/linchpin)
**Objetivo:** implementar el plan por capas de 3.0 (Control Tower + Revenue Layer) **desde el código existente**, con la inteligencia de precios como capacidad insignia — el "titán del pricing scraping" (§4).
**Cómo usar este documento:** está escrito para ejecutarse PR por PR (§10), por un dev humano o un agente de código (Claude Code/Cursor — el repo ya trae skills en `.cursor/skills/`). Cada módulo declara: archivos a crear, interfaz, invariantes de QA, tests y criterio de aceptación. Convención de commits del repo: `feat: wire <tool> as an agent tool`.
---
## 1. Anatomía del repo (lo que ya existe y NO se cambia)
```
scm_agent/     Orquestador: brief → intent.classify → registry.get(tool) → prepare → run → qa → deliver
  types.py     JobResult, statuses: ok · needs_clarification · needs_data · qa_failed · error
  registry.py  register() — agregar capacidad = 1 llamada, sin editar ruteo
  tools.py     build_default_registry() — fuente de verdad (37 tools hoy)
  intent.py    clasificación reglas + LLM opcional
  llm.py       Claude opcional; fallback determinista
  knowledge.py L3: grounding — cada resultado cita concepto + módulo src/
  guided_bridge.py  contrato never-unprotected (via src/guided.py)
jobs/          Playbooks: intake.detect_columns → run → qa.verify → deliverables.write_all
  intake.py    esquema canónico: date, product_id, quantity, unit_cost, lead_time_days
  qa.py        invariantes numéricas — "QA fails ⇒ no se escribe nada"
src/           Motor: funciones puras (eoq, policies, safety_stock, forecasting, pricing, constraints…)
webapp/        FastAPI: dashboard 4 tabs + POST /api/jobs + consola del agente
examples/      CLIs (run_agent.py, run_pricing_job.py…)
tests/         1,100+ tests: ejemplos numéricos de referencia + agente + HTTP guards
```
**Reglas de oro heredadas (obligatorias en todo lo nuevo):**
1. `src/` = funciones puras auditables; los playbooks componen, el motor no se toca para casos especiales.
2. QA gate con veto central: si `qa()` falla, no hay entregable. Sin excepciones.
3. Todo resultado se ancla al knowledge graph (cita concepto + función).
4. Escritura a sistemas externos SOLO por safe-staging (dry-run → tier de riesgo → aprobación TTL → apply idempotente → rollback).
5. Dependencias pesadas en extras opcionales de `pyproject` con fallback al núcleo numpy/pandas/scipy.
6. Cada módulo nuevo llega con tests de ejemplos de referencia (números verificados a mano) — la cultura del repo.
---
## 2. Mapa de builds 3.0
| Bloque | Módulos | PRs (§10) |
| --- | --- | --- |
| Base común | estado del sistema, bus de eventos, scheduler, notificación | PR-1…PR-4 |
| **Titán pricing scraping** | `src/pricing_intel/` completo + tool `price_intelligence` | PR-5…PR-9 |
| Pricing P2–P5 | elasticidad, optimizador, guardrails, repricing writeback | PR-10…PR-13 |
| Track A | monitores, ruteo por evento, tiers de autonomía, verify, balance | PR-14…PR-18 |
| SEO S1–S5 | auditoría, schema/feeds, PDP, prioridad por inventario, GEO | PR-19…PR-22 |
---
## 3. Base común (F0)
### 3.1 `src/state/` — estado del sistema
- **Archivos:** `system_state.py` (snapshot versionado por ciclo: stock, precios propios y de competidores, forecast vigente, decisiones emitidas, outcomes), `store.py` (SQLite para índice/último estado + parquet particionado por fecha para historia).
- **Interfaz:** `snapshot(domain: str, payload: DataFrame, cycle_id: str)` / `latest(domain)` / `history(domain, window)`. Esquemas validados con contratos [unionai-oss/pandera](https://github.com/unionai-oss/pandera).
- **QA invariante:** un snapshot nunca sobreescribe historia (append-only); `cycle_id` monotónico.
- **Tests:** round-trip snapshot→latest→history; rechazo de esquema inválido.
### 3.2 `scm_agent/events.py` — bus de eventos
- **Modelo:** `Event(id, type, severity, sku, source, payload, dedup_key, ts)`. Ledger idempotente en SQLite (patrón Idempotency-Key): mismo `dedup_key` en ventana = no re-emite.
- **Suscripción:** mapa `event_type → (tool, param_builder, autonomy_tier)` en un YAML versionado (`config/event_routing.yaml`) — el ruteo es dato, no código.
- **Repos:** stdlib + [agronholm/apscheduler](https://github.com/agronholm/apscheduler) (cadencia) · [caronc/apprise](https://github.com/caronc/apprise) + [slackapi/python-slack-sdk](https://github.com/slackapi/python-slack-sdk) (notificación/aprobación).
### 3.3 `jobs/scheduler.py`
- APScheduler con jobstore SQLite: ciclos (diario 06:00 análisis, horario para sensores de precio tier alto) + digest narrado por LLM detrás del QA gate. Upgrade path documentado: [PrefectHQ/prefect](https://github.com/PrefectHQ/prefect).
**Criterio de aceptación F0:** un evento sintético `stock_below_rop` dispara `inventory_optimization` del SKU, produce entregable QA-gated y notifica por Slack con link de aprobación. Cero tools nuevas — solo plomería.
---
## 4. EL TITÁN DEL PRICING SCRAPING — `src/pricing_intel/`
> Objetivo de diseño: la inteligencia de precios más **robusta, legal y barata por dato** posible. Titán no significa fuerza bruta: significa que nunca se cae, nunca se envenena con datos malos, y saca el 70%+ de sus datos de fuentes estructuradas y APIs antes de tocar HTML frágil.
### 4.0 Principios no negociables
1. **API-first, structured-data-second, HTML-last** (jerarquía de adquisición §4.2).
2. **Cero PII.** Solo datos públicos de producto/precio/stock. Nunca cuentas de usuario para scrapear.
3. **robots.txt y ToS por sitio** en un registro versionado (`config/sites/*.yaml`) con decisión documentada por dominio.
4. **Todo dato lleva procedencia:** tier de adquisición, timestamp, extractor y confianza — el mismo estándar de citas del resto de Linchpin.
5. **Cortesía técnica:** rate limit por dominio, jitter, cache condicional (ETag/If-Modified-Since), user-agent identificable.
### 4.1 Árbol de archivos
```
src/pricing_intel/
  __init__.py
  models.py        CompetitorOffer, PricePoint, MatchCandidate, SiteConfig (dataclasses + pandera)
  ledger.py        PriceLedger: append-only parquet particionado + índice SQLite
  acquire/
    base.py        protocolo Fetcher (fetch(sku_ref) -> RawObservation) + circuit breaker
    amazon_api.py  L0: SP-API Product Pricing (competitive pricing legal)
    shopify_api.py L0: precios propios multicanal (baseline)
    structured.py  L1: extracción JSON-LD/microdata/OpenGraph de PDPs (extruct)
    watcher.py     L2: adaptador changedetection.io (webhook receiver)
    spiders/       L3: Scrapy por competidor crítico (1 spider = 1 clase, contrato común)
    browser.py     L3b: Playwright opcional para JS pesado (extra [browser])
  extract.py       cascada de extracción de precio (ver 4.4)
  normalize.py     moneda/FX, unit price, pack size, envío, impuestos, promo flags
  match/
    gtin.py        matching exacto por GTIN/EAN/UPC (check-digit con python-stdnum)
    probabilistic.py  Splink (Fellegi-Sunter) sobre título+marca+atributos
    fuzzy.py       RapidFuzz para blocking/candidatos
    adjudicate.py  desempate LLM opcional (budget cap) → sku_map con estado
  sanity.py        QA de datos scrapeados (ver 4.6) — cuarentena
  events.py        emisión a scm_agent.events (ver 4.8)
  metrics.py       cobertura, frescura, precisión, % por tier
config/sites/      1 YAML por dominio: ToS, robots, rate, selectores versionados, tier permitido
jobs/price_intelligence.py   playbook: intake refs → adquirir → matchear → sanity → entregable
tests/test_pricing_intel*.py fixtures HTML congeladas + golden parquet + property tests
```
### 4.2 Adquisición en 4 niveles (la jerarquía del titán)
| Tier | Fuente | Cobertura esperada | Costo/fragilidad | Repos |
| --- | --- | --- | --- | --- |
| **L0 — APIs oficiales** | Amazon SP-API `getCompetitivePricing`/`getItemOffers` (legal y en ToS para sellers); Shopify Admin (precios propios); feeds públicos de Merchant | Marketplaces: alta | Nulo/estable | [saleweaver/python-amazon-sp-api](https://github.com/saleweaver/python-amazon-sp-api) · [Shopify/shopify_python_api](https://github.com/Shopify/shopify_python_api) |
| **L1 — Datos estructurados** | JSON-LD `Product`/`Offer` (precio, moneda, availability) que la MAYORÍA de PDPs modernas expone para Google — se lee el schema, no el DOM | E-commerce moderno: 60–80% de PDPs | Muy bajo — el schema es estable porque el sitio lo necesita para SEO | [scrapinghub/extruct](https://github.com/scrapinghub/extruct) · [scrapinghub/price-parser](https://github.com/scrapinghub/price-parser) (parseo de "$1.234,56" en 40+ formatos) |
| **L2 — Watcher** | changedetection.io self-hosted con detección nativa de precio/restock; webhook → `acquire/watcher.py` | Cola larga (cientos de URLs baratas) | Bajo; frescura configurable | [dgtlmoon/changedetection.io](https://github.com/dgtlmoon/changedetection.io) |
| **L3 — Spiders dedicados** | Scrapy por competidor crítico (3–5 por cliente); Playwright solo si el precio se renderiza por JS | Los que mueven el mercado del cliente | El más frágil — por eso es el último y el más testeado | [scrapy/scrapy](https://github.com/scrapy/scrapy) · [microsoft/playwright-python](https://github.com/microsoft/playwright-python) |
**Regla de enrutamiento:** cada `SiteConfig` declara su tier máximo permitido. El scheduler asigna frescura por importancia: competidores críticos cada 2–6 h (SLA alineado al estándar de mercado de repricing ~4 h), cola larga diaria.
### 4.3 Modelo de datos (`models.py`, `ledger.py`)
```python
@dataclass(frozen=True)
class CompetitorOffer:
    observed_at: datetime      # UTC
    site: str                  # dominio normalizado
    competitor_sku_ref: str    # URL o ASIN/ID externo
    matched_product_id: str | None   # nuestro SKU (via match/)
    match_confidence: float    # 0-1; <umbral ⇒ no entra al ledger principal
    price: Decimal; currency: str; price_normalized: Decimal  # a moneda base, unit price
    shipping: Decimal | None; availability: str  # InStock/OutOfStock/Preorder
    promo_flag: bool; list_price: Decimal | None  # para detectar descuento
    acquisition_tier: str      # L0/L1/L2/L3 (procedencia)
    extractor: str; extractor_version: str        # auditoría
```
Ledger append-only (parquet particionado `site/fecha` + índice SQLite con última observación por par sku↔competidor). Nunca se edita una observación: las correcciones son nuevas filas con flag. Es la misma filosofía del safe-staging aplicada a datos.
### 4.4 Cascada de extracción (`extract.py`) — por qué el titán no se rompe
Orden estricto, cada nivel con su confianza; se detiene en el primero que produce precio válido:
1. **JSON-LD** `Offer.price` + `priceCurrency` + `availability` (extruct) — confianza 0.98.
2. **Microdata/RDFa/OpenGraph** (`product:price:amount`) — 0.9.
3. **Selector CSS/XPath versionado** del `SiteConfig` (con test fixture congelada) — 0.8.
4. **price-parser sobre texto candidato** (nodos con símbolo de moneda cerca del título) — 0.6.
5. **Extractor LLM** (HTML podado → Claude con esquema pydantic estricto) — 0.6, con budget cap diario y solo si 1–4 fallan; toda extracción LLM queda marcada para verificación cruzada en la siguiente lectura.
Si todo falla ⇒ evento `extraction_failed` (no un precio inventado). **Un precio dudoso es peor que ningún precio** — el optimizador P2 lo consumiría.
### 4.5 Matching de producto (`match/`) — el problema más difícil del scraping de precios
Pipeline con estados, no un match binario:
1. **GTIN/EAN/UPC exacto** (check-digit validado con [arthurdejong/python-stdnum](https://github.com/arthurdejong/python-stdnum)) → `confirmed` (0.99).
2. **Blocking barato** con [rapidfuzz/RapidFuzz](https://github.com/rapidfuzz/RapidFuzz) (título+marca) → candidatos.
3. **Fellegi-Sunter con [moj-analytical-services/splink](https://github.com/moj-analytical-services/splink)** sobre título/marca/atributos (talla, pack, modelo) → score probabilístico.
4. **Adjudicación LLM opcional** para la franja 0.5–0.85 (compara fichas, responde mismo/distinto/variante + razón) → propone, nunca confirma solo.
5. **Revisión humana T2** para confirmar la franja media: la tabla `sku_map` es versionada con estados `confirmed / suspect / rejected` y quién/qué confirmó.
**Invariante QA:** solo observaciones con match `confirmed` (o ≥0.9) alimentan P2/A5. La matriz de posición de precio muestra los `suspect` en sección aparte, marcados.
### 4.6 Sanidad de datos (`sanity.py`) — el QA gate del scraping
Reglas de cuarentena (todas con test):
- Precio ≤ 0, moneda desconocida, o availability contradictoria ⇒ descarta con evento.
- |Δ| > 40% intradía sin `promo_flag` ⇒ cuarentena hasta segunda lectura que confirme (relee en ≤1 h).
- Outliers por MAD sobre la ventana de 30 días del par sku↔competidor ⇒ cuarentena.
- Staleness: si un par crítico no se observa en 2× su SLA ⇒ evento `stale_feed` (el dato viejo se marca, no se borra).
- Sospecha de bloqueo/soft-ban (403/429/captcha/DOM vacío/precio idéntico 100% de lecturas por semanas) ⇒ circuit breaker del fetcher, degradar tier (L3→L2), evento `site_degraded`.
### 4.7 Cumplimiento (previo a onboarding de cada dominio)
`config/sites/<dominio>.yaml` obliga a llenar: robots.txt respetado (sí/no + fecha), resumen ToS y decisión (permitido/limitado/prohibido), rate acordado, PII (debe ser "ninguna"). Sin YAML aprobado, el fetcher se niega a correr — mismo patrón que el QA gate. Preferencia documentada por APIs (SP-API cubre Amazon legítimamente; jamás scrapear Amazon por HTML).
### 4.8 Eventos que emite → A1
`price_move(sku, competitor, old, new, %)` · `competitor_oos(sku)` (oportunidad: subir precio/empujar SEO) · `promo_detected` · `map_violation` (si el cliente es marca) · `new_competitor_listing` · `extraction_failed` / `site_degraded` / `stale_feed` (salud del propio titán).
### 4.9 Registro como capacidad (el patrón del repo, sin tocar el ruteo)
1. `jobs/price_intelligence.py`: intake de refs (CSV de URLs/ASINs del cliente o descubrimiento asistido) → adquirir → matchear → sanity → reporte.
2. Invariantes en `jobs/qa.py`: cobertura mínima de matching para shipear (p.ej. ≥60% de SKUs con ≥1 competidor confirmado), 0 filas de cuarentena en el entregable, frescura media dentro de SLA.
3. Entregables: `price_position_matrix.xlsx` (nuestro precio vs cada competidor, índice de posición, flags), `report.md` con narrativa + **Fuentes** (procedencia por dato), `ledger_export.csv`.
4. `register()` en `build_default_registry()` + frases de intent ("monitorea precios de la competencia", "dónde estoy caro").
5. CLI `examples/run_price_intel.py --refs competitors.csv --client "Acme"` + tests.
### 4.10 Tests del titán (cultura del repo: 1,100+ y subiendo)
Fixtures HTML congeladas por sitio (goldens de extracción); property tests del normalizador (price-parser: formatos "1.234,56 €", "US$ 1,234.56", "CLP 12.345"); golden parquet del ledger; tests de contrato del protocolo Fetcher; simulacro de bloqueo (403→circuit breaker→degradación); test end-to-end del playbook con sitio sintético servido por FastAPI en el test.
### 4.11 Métricas del titán (en el dashboard)
% SKUs con ≥1 competidor `confirmed` (cobertura) · frescura media por tier · precisión de extracción (muestreo semanal contra lectura manual) · **% de observaciones por tier — meta: ≥70% L0+L1** (barato, legal, estable) · tasa de cuarentena · costo por 1,000 observaciones.
---
## 5. Pricing P2–P5 (sobre el titán)
| Módulo | Archivos nuevos | Núcleo | QA invariantes | Repos |
| --- | --- | --- | --- | --- |
| P2 `price_optimization` | `src/elasticity.py`, `src/price_optimizer.py` (extienden `src/pricing.py`) | Elasticidad log-log por SKU; jerárquica bayesiana para SKUs con poca historia; optimización con restricciones (piso landed cost + MOQ de margen + bandas) | Precio propuesto ≥ costo landed; elasticidad con IC que no cruce 0 para mover precio; si no hay señal ⇒ `needs_data`, no un número inventado | [pymc-labs/pymc-marketing](https://github.com/pymc-labs/pymc-marketing) · [scipy/scipy](https://github.com/scipy/scipy) |
| P3 `repricing_multichannel` | `src/connectors/{shopify,amazon,odoo}_prices.py` + `jobs/repricing.py` | Changeset de precios (dry-run) → safe-staging → apply por canal → verificación post-apply (releer el canal) | Todo cambio pasa P5 antes del staging; apply sin verificación = incidente | [Shopify/shopify_python_api](https://github.com/Shopify/shopify_python_api) · [saleweaver/python-amazon-sp-api](https://github.com/saleweaver/python-amazon-sp-api) · [OCA/odoorpc](https://github.com/OCA/odoorpc) |
| P4 `promo_liquidation` | `jobs/promo_liquidation.py` (orquesta `excess_obsolete`+FEFO+elasticidad) | Calendario de liquidación con recuperación esperada de caja | Descuento propuesto respeta Omnibus (mín. 30 días del ledger propio) | tools existentes + [Nixtla/statsforecast](https://github.com/Nixtla/statsforecast) |
| P5 `pricing_guardrails` | `src/pricing_guardrails.py` (+ reglas declarativas) | Bandas por SKU/marca, MAP, frecuencia máx., coherencia multicanal, Omnibus UE, explicación obligatoria | Gate central: sin explicación legible + citas ⇒ el changeset no sale | propio + [unionai-oss/pandera](https://github.com/unionai-oss/pandera) |
---
## 6. Track A — Control Tower (archivos)
| Capa | Archivos | Contenido | Repos |
| --- | --- | --- | --- |
| A1 `sense` | `scm_agent/monitors.py` + `config/monitors.yaml` | Monitores puros sobre estado del sistema: ROP cruzado, σ_e fuera de banda, drift de lead time, señales del titán (§4.8) | base común + [Nixtla/statsforecast](https://github.com/Nixtla/statsforecast) |
| A2 `decide` | `scm_agent/event_intent.py` | Ruteo evento→tool por `event_routing.yaml`; reusa registry intacto | [anthropics/claude-agent-sdk-python](https://github.com/anthropics/claude-agent-sdk-python) · [modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk) |
| A3 `execute` | extiende `guided_bridge`/staging: `autonomy.py` (tiers T1/T2/T3 por tipo de acción + historial A4) | T1 auto dentro de bandas; T2 un click (Slack/FastAPI); T3 paquete de escalamiento | [fastapi/fastapi](https://github.com/fastapi/fastapi) · [slackapi/python-slack-sdk](https://github.com/slackapi/python-slack-sdk) |
| A4 `verify` | `src/verify/backtest.py`, `src/verify/reliability.py` | Predicho vs real por decisión; MAPE/WAPE/bias por SKU; reporte de confiabilidad por tool; recalibración de σ_e y umbrales | [Nixtla/utilsforecast](https://github.com/Nixtla/utilsforecast) · [unionai-oss/pandera](https://github.com/unionai-oss/pandera) |
| A5 `balance` | `src/sop_engine/` (demand_plan, supply_plan, coherence, tradeoffs) + `jobs/integrated_plan.py` | v1: pipeline secuencial con checks de coherencia explícitos y citables; v2: optimización conjunta CP-SAT | [google/or-tools](https://github.com/google/or-tools) · [Nixtla/hierarchicalforecast](https://github.com/Nixtla/hierarchicalforecast) · [OCA/ddmrp](https://github.com/OCA/ddmrp) |
**Invariante A5 v1 (evitar el error clásico):** no intentar el solver global primero. El plan integrado v1 es: forecast reconciliado → plan de demanda (con demand shaping de P2) → plan de inventario/compra (constraints.py generalizado) → checks de coherencia ("promo de SKU sin stock entrante = bloqueo") → entregable único. El solver conjunto llega cuando A4 acredite el pipeline secuencial.
---
## 7. Track B — SEO (archivos)
| Módulo | Archivos | Repos |
| --- | --- | --- |
| S1 `seo_audit` | `src/seo/crawl_audit.py` (envuelve advertools crawler + extruct + Lighthouse CLI vía subprocess) + `jobs/seo_audit.py` | [eliasdabbas/advertools](https://github.com/eliasdabbas/advertools) · [scrapinghub/extruct](https://github.com/scrapinghub/extruct) · [GoogleChrome/lighthouse](https://github.com/GoogleChrome/lighthouse) · [sethblack/python-seo-analyzer](https://github.com/sethblack/python-seo-analyzer) |
| S2 `schema_feeds` | `src/seo/schema_gen.py` (JSON-LD desde catálogo + stock del estado del sistema), `feeds.py` (Merchant/JSON), `llms_txt.py` | [google/schema-dts](https://github.com/google/schema-dts) (vocabulario) · [AnswerDotAI/llms-txt](https://github.com/AnswerDotAI/llms-txt) · [pydantic/pydantic](https://github.com/pydantic/pydantic) |
| S3 `pdp_content` | `src/seo/pdp_writer.py` — generación con esquema estricto de ficha verificable; QA: cada afirmación mapea a un campo del catálogo | [anthropics/anthropic-sdk-python](https://github.com/anthropics/anthropic-sdk-python) |
| S4 `inventory_aware_seo` | `jobs/seo_priority.py` — cruce `abc_xyz` + `excess_obsolete` + forecast + S1; plan mensual 301/push/cut | sin deps nuevas |
| S5 `geo_visibility` | `src/seo/geo_probe.py` — sondas de citación en motores AI, share of voice | [scrapy/scrapy](https://github.com/scrapy/scrapy) + propio |
---
## 8. Webapp y consola
Nuevas rutas FastAPI: `GET /api/events` (stream del bus), `POST /api/approvals/{id}` (aprobación TTL un click), `GET /api/price-position/{sku}` (matriz del titán), webhook `POST /api/watch` (changedetection.io). Nuevo tab del dashboard: **Pricing** (posición vs competidores, frescura, cuarentena) y **Tower** (eventos del día, acciones T1 ejecutadas, pendientes T2, confiabilidad A4 por tool). Mismo patrón del dashboard existente (estático + fetch a la API, sin build step).
## 9. `pyproject` — extras nuevos (todo con fallback)
```toml
pricing-intel = ["scrapy>=2.11", "extruct>=0.17", "price-parser>=0.3",
                 "rapidfuzz>=3.14", "splink>=4", "python-stdnum>=2.2",
                 "httpx>=0.28", "pandera>=0.32"]
browser       = ["playwright>=1.50"]                  # solo si un sitio crítico lo exige
repricing     = ["ShopifyAPI>=12.7", "python-amazon-sp-api>=2.1", "OdooRPC"]
elasticity    = ["pymc-marketing>=0.10"]              # fallback: log-log OLS propio
tower         = ["APScheduler>=3.11,<4", "apprise>=1.11", "slack-sdk>=3.42"]
seo           = ["advertools>=0.14", "pyarrow>=15"]
balance       = ["ortools>=9.15", "hierarchicalforecast>=1.5"]
```
## 10. Secuencia de PRs (cada uno shippeable, con tests verdes)
| PR | Alcance | Criterio de aceptación |
| --- | --- | --- |
| 1 | `src/state/` + tests | snapshot/latest/history round-trip |
| 2 | `scm_agent/events.py` + ledger idempotente | evento duplicado no re-emite |
| 3 | `jobs/scheduler.py` + digest diario | ciclo corre y notifica |
| 4 | `event_routing.yaml` + `event_intent.py` | evento sintético → tool → entregable QA-gated |
| 5 | `pricing_intel/models.py` + `ledger.py` | golden parquet estable |
| 6 | `acquire/structured.py` + `extract.py` cascada + `price-parser` | fixtures de 10 sitios reales extraen precio correcto; LLM extractor con cap |
| 7 | `match/` completo + `sku_map` versionada | precision ≥95% en set etiquetado a mano (crear `tests/fixtures/matching_labeled.csv`) |
| 8 | `sanity.py` + circuit breaker + `config/sites/` | simulacro de bloqueo degrada tier sin caerse; cuarentena funciona |
| 9 | tool `price_intelligence` + playbook + CLI + tab Pricing | brief "dónde estoy caro" → matriz + reporte con procedencia |
| 10 | `elasticity.py` + `price_optimizer.py` (P2) | ejemplo numérico de referencia reproducible; `needs_data` sin señal |
| 11 | `pricing_guardrails.py` (P5) | changeset sin explicación no sale; Omnibus validado contra ledger |
| 12 | conectores repricing + safe-staging (P3) | dry-run→approve→apply→verificación post-apply en sandbox de canal |
| 13 | `promo_liquidation` (P4) | calendario con recuperación esperada, Omnibus-safe |
| 14 | `monitors.py` (A1) | 5 monitores base emitiendo con dedup |
| 15 | `autonomy.py` tiers (A3) | acción T1 en banda se auto-ejecuta y audita; fuera de banda escala a T2 |
| 16 | `verify/` (A4) | reporte de confiabilidad mensual por tool; recalibración de σ_e demostrada en backtest |
| 17 | `sop_engine/` v1 (A5) | plan integrado con ≥3 checks de coherencia citables |
| 18 | promoción T2→T1 guiada por A4 | regla: N ciclos consecutivos con precisión ≥ umbral |
| 19–22 | S1→S4/S5 | auditoría entrega top-20 issues; schema válido en Rich Results; PDP 100% verificable; plan SEO mensual alineado a inventario |
## 11. Definition of done (global)
Cada módulo: función pura en `src/` + playbook + invariantes QA + entregable con Fuentes + tests de referencia + entrada en el knowledge graph (concepto↔módulo) + sección en el README correspondiente. El titán además: `config/sites/` aprobado por dominio, métricas §4.11 visibles en dashboard, y ≥70% de observaciones por L0+L1 en el primer cliente real.
## 12. Riesgos de implementación
1. **Matching es el cuello real** (no el fetching): presupuestar el set etiquetado del PR-7 desde el día 1; sin ≥95% de precisión, P2 optimiza contra fantasmas.
2. **Selectores L3 se pudren:** por eso la cascada JSON-LD-first y el circuit breaker; ningún selector sin fixture congelada.
3. **Tentación del solver global (A5):** v1 secuencial con checks; el solver espera a A4.
4. **LLM en el camino de datos:** siempre con esquema estricto, budget cap, y marca de procedencia — jamás silencioso.
5. **Windows/py3.11:** verificar wheels (splink/duckdb, playwright) — misma advertencia del plan 2.x.
## 13. Fuentes
Interfaces y patrones citados del repo real: [README](https://github.com/esstipi-debug/linchpin) · [scm_agent/README.md](https://github.com/esstipi-debug/linchpin/blob/main/scm_agent/README.md) · [jobs/README.md](https://github.com/esstipi-debug/linchpin/blob/main/jobs/README.md) · [Capability Expansion Plan](https://github.com/esstipi-debug/linchpin/blob/main/documentation/CAPABILITY_EXPANSION_PLAN.md). Contexto de industria y benchmarks: ver LINCHPIN_3.0_PLAN.md §5 y PITCH_AGENCIA_LINCHPIN.md (fuentes al pie de cada uno).
