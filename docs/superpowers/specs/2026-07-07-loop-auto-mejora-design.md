# Loop de auto-mejora de Linchpin — Design Spec

> Fecha: 2026-07-07
> Estado: aprobado para implementacion
> Autor: brainstorming colaborativo (usuario + agente)

## 0. Contexto y motivacion

El usuario pregunto por integrar `github.com/EvoMap/evolver` (un motor de
"auto-evolucion" de terceros para agentes de codigo) a Linchpin, con la idea
de que el agente "siga evolucionando". Revision del codigo fuente real de ese
repo encontro riesgos concretos que lo descartan para este proyecto:

- Lee los transcripts reales de sesiones de Claude Code (`~/.claude/projects`)
  y de otros IDEs.
- Tiene un componente de proxy que auto-inyecta variables de entorno para
  Claude Code/Codex/Cursor (`EVOMAP_PROXY_AUTO_INJECT`) — riesgo de
  interceptar trafico/API keys.
- Modo de red opcional ("worker pool") que acepta y ejecuta tareas
  despachadas por un Hub de terceros — un canal de ejecucion remota.
- Su logica de recovery corre `git checkout -- .` y `git clean -fd` sobre el
  repo objetivo — destructivo, y particularmente peligroso porque este repo
  corre sesiones concurrentes de Claude Code sobre worktrees compartidos
  (ver `HANDOFF.md` §5).
- Licencia GPL-3.0-or-later — riesgo de copyleft si se empaqueta junto con un
  producto que se vende comercialmente.

Decision: en vez de un motor de terceros con esas superficies de riesgo, se
construye un loop de auto-mejora **local, sin dependencias de red externas**,
que aprovecha exactamente la misma filosofia que Linchpin ya aplica a su
propio producto (`src/guided.py`: nunca dejar un resultado consecuente
desprotegido) — aplicada de forma reflexiva a su propio ciclo de desarrollo.

## 1. Problema y objetivo

Hoy Linchpin no tiene ningun mecanismo que aprenda de sus propias fallas
reales: los resultados `qa_failed`, `error`, y las escalaciones de
`GuidedOutcome` (`ESCALATED`/`HANDOFF`) se calculan, se devuelven al llamador,
y se pierden — no quedan loggeados en ningun lado. El unico mecanismo de
"aprendizaje entre sesiones" que existe hoy es el de `graphify`
(`knowledge/graph-memory/` + `documentation/GRAPH_LESSONS.md`), y es sobre
navegacion del *codigo*, no sobre comportamiento del *producto* en uso real.

**Objetivo:** un loop que mine senales de uso real (fallas de QA,
escalaciones, errores, fallas de CI) y las convierta en fixes revisables
(draft PRs) o en un reporte priorizado, sin intervencion humana continua,
pero sin nunca mergear nada solo ni tocar zonas sensibles sin supervision.

**No objetivo (fuera de alcance v1):** generar nuevas capacidades/tools
(el backlog de expansion offline ya esta agotado — ver memoria
`linchpin-coverage-roadmap`); reemplazar el trabajo de consecucion de
clientes (la prioridad explicita del proyecto sigue siendo ingresos, no mas
motor — ver `HANDOFF.md` y memoria `linchpin-priority-monetization`).

## 2. Decisiones tomadas (brainstorming)

1. **Fuente de senal:** uso real (QA failures, escalaciones, errores), no el
   backlog conocido de `HANDOFF.md` §3.4. El backlog §3.4 sigue existiendo
   como trabajo manual de baja prioridad, pero no es lo que este loop mina.
2. **Autonomia:** draft PR automatico por hallazgo (nunca auto-merge, nunca
   push directo a `main` — sigue la convencion ya existente del repo).
3. **Zonas excluidas del auto-PR:** `src/writeback.py`,
   `src/writeback_store.py`, `src/connectors/`, `src/mcp_keys.py`,
   `webapp/mcp_auth.py`, y cualquier cosa de pricing/billing/secrets. Ahi el
   loop solo reporta, nunca abre PR sin pedido explicito del usuario.
4. **Disparador:** umbral de senal acumulada desde la ultima corrida, con un
   tope maximo de inactividad para no quedar dormido para siempre si el
   trafico real es bajo (hoy: 0 clientes pagos).
5. **Arquitectura:** cron liviano (chequeo) + agente ejecutor + verificacion
   adversarial antes de convertir cualquier fix en PR (Opcion C de las 3
   evaluadas — ver §3 mas abajo para las otras dos y por que se descartaron).

## 3. Opciones evaluadas

- **A — Cron + agente ejecutor, sin verificacion extra.** Mas simple/barato,
  pero el unico control de calidad es el CI existente y la revision humana
  del PR — sin un paso que intente refutar el fix antes de abrirlo.
- **B — On-demand tipo `graphify reflect`.** Un comando que el usuario corre
  cuando quiere, como ya hace con `graphify reflect`. Cero infraestructura
  nueva de scheduling, pero cero autonomia de fondo — no calza con la
  decision de "draft PR automatico" tomada en brainstorming.
- **C — Cron + agente + verificacion adversarial (elegida).** Igual que A,
  pero cada fix propuesto pasa por verificadores que intentan refutar que
  realmente resuelve la causa raiz sin romper nada, antes de convertirse en
  PR. Un fix que no sobrevive cae a reporte. Es la unica de las tres que le
  pone un freno de calidad a algo que va a tocar codigo de un producto que ya
  genera ingresos — coherente con como este mismo repo ya trata sus propias
  revisiones de alto riesgo (el brief de monetizacion y el review de
  paquetes comerciales usaron el mismo patron de verificacion adversarial).

## 4. Arquitectura y componentes

```
corrida real (webapp / MCP / CLI)
        |
        v
scm_agent/orchestrator.py  --(status != ok, o GuidedOutcome ESCALATED/HANDOFF)-->  src/signals_store.py
                                                                                      (SQLite: data/signals.sqlite3)
                                                                                              |
                                                                          [best-effort: fly sftp get de produccion]
                                                                                              |
scripts/evolve/check_threshold.py  (cron diario, barato)  <---------------------------------+
        | cuenta eventos nuevos desde data/evolve_state.json (last_run_at, last_consumed_event_id)
        | + consulta `gh run list --status failure` para senal de CI
        v
  umbral superado o tope de inactividad vencido?
        | si                                            | no
        v                                                v
  Workflow `evolve` (mine -> cluster -> fix -> verify)   no hace nada, corrida gratis
        |
        v
  por cluster: zona excluida? (chequeo deterministico, ANTES de que un agente lo vea)
        |                                        |
       si                                        no
        v                                        v
  documentation/EVOLUTION_LOG.md         mecanico o judgment-heavy? (agente clasifica)
  (reporte, nunca PR)                            |                          |
                                            mecanico                  judgment-heavy
                                                  v                          v
                                    TDD: test que reproduce -> fix   EVOLUTION_LOG.md
                                                  v
                                    verificacion adversarial (paralelo)
                                        sobrevive?     no sobrevive?
                                            v                v
                                  rama evolve/<slug>-<fecha>   EVOLUTION_LOG.md
                                  commit, push,                ("intentado, needs
                                  gh pr create --draft           human")
```

**Componentes nuevos:**

| Componente | Rol |
|---|---|
| `src/signals_store.py` | `SignalStore` sobre SQLite (mismo patron que `src/writeback_store.py`). Tabla de eventos: `id, timestamp, kind, tool_name, reason, context_json, consumed_by_run_id`. Vive en `data/signals.sqlite3` (gitignored, igual que el resto de `data/*.sqlite3`). |
| hook en `scm_agent/orchestrator.py` | Al final de cada corrida, si el status terminal no es `ok` o el `GuidedOutcome` es `ESCALATED`/`HANDOFF`, llama `signals_store.record_event(...)`. Fire-and-forget. |
| `scripts/evolve/check_threshold.py` | Chequeo diario barato (invocado por la skill `schedule`/CronCreate). Pull best-effort de la DB de produccion via `fly sftp get`, cuenta eventos nuevos, decide si dispara el Workflow. |
| `scripts/evolve/excluded_paths.py` | Lista de prefijos de path excluidos del auto-PR. Funcion pura, sin logica de agente. |
| Workflow `evolve` (guardado en `.claude/workflows/evolve.js`) | Pipeline mine -> cluster -> classify -> fix -> verify -> PR/reporte. Se guarda como workflow con nombre (no inline) para que `check_threshold.py` lo invoque por nombre (`Workflow({name: "evolve"})`) y para poder re-invocarlo (`resumeFromRunId`) si se corta a mitad de camino. |
| `documentation/EVOLUTION_LOG.md` | Reporte append-only, mismo estilo que `HANDOFF.md`, para hallazgos en zonas excluidas, judgment-heavy, o que no sobrevivieron la verificacion. |
| `data/evolve_state.json` | Estado minimo: `last_run_at`, `last_consumed_event_id`. Gitignored (estado runtime, no codigo). |

**Por que no vive esto en `jobs/<x>_job.py`:** ese patron es para tools
agent-routable que un cliente invoca via brief (prepare/run/qa/deliver). El
loop de auto-mejora es un proceso de meta-desarrollo, no una capacidad que
Linchpin le vende a un cliente — por eso vive en `scripts/evolve/` +
un Workflow, fuera del registro de tools (`scm_agent/tools.py`).

## 5. Flujo de datos (detalle de la seccion 4 del brainstorming)

1. **Captura**: corrida real -> orchestrator termina -> status no-`ok` o
   escalacion -> `SignalStore.record_event()`. Como el mismo `Orchestrator`
   corre en local y en produccion (Fly, mismo mount `/data`), el store
   captura senal en ambos lados sin duplicar logica — no hace falta
   distinguir "modo produccion" en el codigo.
2. **Chequeo diario**: `check_threshold.py` mezcla la DB local + un pull
   best-effort de la DB de produccion + fallas de CI recientes via `gh` ->
   cuenta eventos nuevos desde `last_consumed_event_id` -> dispara el
   Workflow si cruza el umbral (default propuesto: 5 eventos nuevos) o si
   paso el tope de inactividad (default propuesto: 30 dias) desde
   `last_run_at`. Si ninguna condicion se cumple, termina sin costo.
3. **Mining**: agrupa eventos nuevos por `(kind, tool_name, razon
   normalizada)` — agrupamiento por string/hash, sin ML, alcanza a esta
   escala — y rankea por frecuencia x recencia.
4. **Por cluster** (pipeline, no barrera — cada cluster avanza a su propio
   ritmo mientras otros siguen en etapas previas):
   - Chequeo determinista de zona excluida (corre en codigo plano, antes de
     que cualquier agente vea el cluster).
   - Si excluido -> entrada en `EVOLUTION_LOG.md`, fin para ese cluster.
   - Si no excluido -> agente `classify`: mecanico (repro clara, 1-2
     archivos) vs. judgment-heavy (decision de diseno, alcance ambiguo).
   - Judgment-heavy -> `EVOLUTION_LOG.md`, fin.
   - Mecanico -> agente `propose-fix`: primero un test que reproduce el
     problema (TDD), despues el fix minimo.
   - Verificacion adversarial (varios agentes en paralelo intentando
     refutar que el fix resuelve la causa raiz sin regresiones) + suite
     completo + `ruff` corridos localmente dentro del workflow.
   - Sobrevive (mayoria) -> rama `evolve/<slug>-<fecha>`, commit, push,
     `gh pr create --draft` citando el cluster de origen (kind, tool,
     cantidad de eventos, ejemplo de razon).
   - No sobrevive -> `EVOLUTION_LOG.md` como "intentado, verificacion
     fallo, necesita humano", incluyendo el diff intentado para referencia.
5. **Cierre**: actualiza `data/evolve_state.json` y marca los eventos usados
   como consumidos en el `SignalStore` (no se re-minan en la proxima
   corrida).

## 6. Manejo de errores y seguridad

- **Captura fire-and-forget**: una falla en `record_event()` se loggea a
  stderr y se ignora — nunca puede tumbar una corrida real de un cliente.
- **Scrub de PII en la captura, no despues**: `context_json` solo guarda
  campos estructurados no identificables (nombre de tool, clase de error,
  keys de params — nunca valores que identifiquen a un cliente). Sigue la
  regla ya existente en `CLAUDE.md` ("Never read or surface PII").
- **Nunca auto-mergea, nunca toca `main` directo** — cada cambio de codigo
  es un draft PR, la convencion ya existente del repo (`gh pr create
  --draft` -> CI verde -> `gh pr ready` -> squash-merge manual).
- **Filtro de zonas excluidas determinista, no delegado al agente** — corre
  en codigo plano antes de que cualquier agente vea el cluster, para que no
  haya forma de que un agente lo "razone" para saltarselo.
- **Tope de PRs por corrida** (default propuesto: 3) — evita que una corrida
  abra una avalancha de PRs de golpe; `HANDOFF.md` §5 ya documenta friccion
  real de PRs concurrentes pisandose en archivos compartidos
  (`CHANGELOG.md`).
- **Chequeo de concurrencia antes de ramificar**: revisa `git status` y PRs
  abiertos antes de tocar un archivo — si un archivo objetivo ya esta siendo
  tocado por un PR abierto o un worktree sucio, ese cluster se salta esta
  corrida en vez de generar un conflicto, siguiendo la misma disciplina que
  `HANDOFF.md` §5 ya exige a sesiones humanas concurrentes.
- **Suite completo + `ruff` deben pasar localmente dentro del workflow antes
  de abrir el PR** — no depender solo del CI posterior para el primer
  chequeo de calidad.
- **Sin credenciales nuevas ni servicios de terceros** — todo corre con las
  herramientas ya disponibles en esta sesion de Claude Code (skill
  `schedule`/CronCreate, herramienta Workflow, `gh` CLI, `fly` CLI ya
  instalado en esta maquina).

## 7. Testing

- `SignalStore`: record/read/mark-consumed, y que el scrub de PII realmente
  filtra lo que no deberia guardarse en `context_json`.
- `check_threshold.py`: matematica de umbral y de tope de inactividad —
  funciones puras, testeables con archivos de estado de fixture, sin
  necesitar un cron real.
- `excluded_paths.py`: matcher de prefijos, funcion pura.
- Hook del orchestrator: una corrida `qa_failed` produce exactamente un
  evento; una corrida `ok` no produce ninguno; una corrida con
  `GuidedOutcome.ESCALATED` produce un evento con `kind="escalated"`.
- El Workflow en si (mine -> propose -> verify -> PR) no es testeable de
  forma tradicional (es un pipeline de agentes) — se valida con un modo
  `--dry-run` (mina + clasifica + imprime que haria, sin ramificar ni abrir
  PR), siguiendo el mismo patron que ya usan Odoo/decision-support/writeback
  en este repo. Se corre en modo canario manualmente un par de veces antes
  de confiar en el desatendido via cron.

## 8. Riesgos conocidos / trade-offs aceptados

- **Senal inicial escasa**: con 0 clientes pagos hoy, la mayoria de la senal
  real vendra de pruebas del propio usuario y de fallas de CI, no de uso de
  cliente. Aceptado — el umbral+tope de inactividad ya esta disenado para no
  desperdiciar corridas mientras el trafico es bajo, y la senal crece sola
  cuando haya clientes reales.
- **El pull de la DB de produccion depende de `fly sftp get` funcionando** —
  si falla (token vencido, VM caida), el mining sigue solo con senal local +
  CI; no bloquea la corrida, pero puede significar que se mina con menos
  datos de los que hay en produccion. Aceptado como best-effort explicito,
  no un requisito duro.
- **El agrupamiento por string/hash puede separar dos eventos que en
  realidad comparten causa raiz** si el mensaje de error varia. Aceptado
  para v1 (YAGNI: no se justifica ML de clustering a este volumen); si se
  vuelve un problema real con mas volumen, es una mejora incremental
  aislada al paso de `mine`.
