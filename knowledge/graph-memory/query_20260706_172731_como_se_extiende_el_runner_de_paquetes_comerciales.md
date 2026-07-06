---
type: "query"
date: "2026-07-06T17:27:31.024053+00:00"
question: "Como se extiende el runner de paquetes comerciales para tools cuyo input real es un PARAMETRO, no un CSV (leadership_chain, warehouse_layout)?"
contributor: "graphify"
source_nodes: ["PackageStep", "run_package", "leadership_tool", "warehouse_layout_tool"]
---

# Q: Como se extiende el runner de paquetes comerciales para tools cuyo input real es un PARAMETRO, no un CSV (leadership_chain, warehouse_layout)?

## Answer

PackageStep gano un hook params_from_input: Callable[[Path], dict] (scm_agent/packages.py). En _run_step, justo despues de resolver el archivo/derive y ANTES de construir el JobRequest, si params_from_input esta seteado y hay un data_path resuelto, se llama y su dict resultante se mergea en params (extra values ganan) - envuelto en el mismo try/except Exception que ya protege el resto del paso, asi que cualquier excepcion (KeyError por columna faltante, ValueError por valor invalido) se convierte en un StepOutcome status=error limpio, nunca revienta el runner. Usado para leadership_chain: liderazgo.csv (una fila, columnas C,H,A,I,N cada 0-4) se convierte en params['scores'] que el tool ya sabe leer via coerce_scores() - _leadership_scores_from_csv() en scm_agent/package_specs.py valida ANTES de lanzar (columnas faltantes, valores fuera de 0-4, no-enteros) para dar un mensaje operable en vez de un KeyError crudo tipo "'N'". warehouse_layout es distinto: no usa params_from_input en absoluto - es puramente parametrico (generate_layout(dict) en warehouse/generator.py, sin CSV), asi que su PackageStep tiene input_slot=None (como odoo_replenishment) y sus dimensiones de sitio/edificio/racks/docks/gates van directo en PackageStep.params (un dict nesteado _WAREHOUSE_PROJECT_PARAMS) - el merge global run_package()'s {**step.params, **params} es un merge SHALLOW, asi que un params global con una key 'site' de nivel superior reemplazaria el dict entero, no lo mergearia campo a campo (documentado, no un bug real hoy porque ningun params global usa esas keys). Gotcha de reproducibilidad encontrado por review adversarial: un generador de datos demo que itera un set() de Python para construir filas de CSV NO es reproducible byte-a-byte entre procesos separados (el orden de iteracion de un set de strings depende de PYTHONHASHSEED, randomizado por proceso por defecto) aunque el CONTENIDO sea deterministico via un rng seedeado - la fix es usar list en vez de set para cualquier coleccion cuyo ORDEN de fila en el CSV importe para diffear demos entre corridas.

## Source Nodes

- PackageStep
- run_package
- leadership_tool
- warehouse_layout_tool