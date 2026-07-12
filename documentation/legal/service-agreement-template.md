# PLANTILLA — Acuerdo de Servicios

> ## ⚠️ BORRADOR — NO USAR CON UN CLIENTE PAGANDO SIN REVISIÓN LEGAL
>
> Este documento es un **punto de partida** redactado para reflejar con
> precisión cómo funciona Linchpin hoy (alcance, garantía de QA, manejo de
> datos, *writeback*) — no es asesoramiento legal ni un contrato listo para
> firmar. Cada cláusula marcada `[REVISAR CON ABOGADO: ...]` necesita el ojo
> de un abogado real, familiarizado con la jurisdicción donde operás, antes
> de usarse con un cliente que paga. Las cláusulas sin esa marca son
> mayormente descriptivas (qué hace el producto) y tienen menos riesgo legal,
> pero igual conviene que un abogado les pase una lectura completa la primera
> vez.
>
> Ver también [dpa-lite.md](dpa-lite.md) (el anexo de datos que complementa
> este acuerdo) y el ítem E7 en
> [09 · Checklist de Lanzamiento](../operator/09_checklist_lanzamiento.md).

---

## 1 · Partes

Este Acuerdo de Servicios ("**Acuerdo**") se celebra entre:

- **[NOMBRE DEL OPERADOR / RAZÓN SOCIAL]** ("**Linchpin**" o "**el
  Proveedor**"), `[REVISAR CON ABOGADO: definir si el operador contrata a
  título personal, como monotributista/autónomo, o bajo una sociedad — cambia
  quién firma y qué responsabilidad patrimonial aplica]`.
- **[NOMBRE DEL CLIENTE]** ("**el Cliente**"), representado por
  **[NOMBRE Y CARGO DEL FIRMANTE]**.

Fecha de inicio: **[FECHA]**. Paquete contratado: **[NOMBRE DEL PAQUETE —
ver documentation/paquetes/]**.

## 2 · Objeto y alcance del servicio

El Proveedor entrega al Cliente los análisis y entregables correspondientes
al paquete **[NOMBRE DEL PAQUETE]**, según el alcance publicado en su
one-pager comercial (`documentation/paquetes/[archivo].md`), incluyendo:

- Las herramientas específicas incluidas en el paquete (ver la tabla
  "Recibís" del one-pager correspondiente).
- La cadencia acordada (única, mensual, quincenal, etc. — ver el one-pager).
- Un documento ejecutivo consolidado más el entregable completo de cada
  herramienta individual del paquete (reporte + planilla de trabajo).

**Fuera de alcance**, salvo acuerdo escrito adicional: cualquier
herramienta o análisis no listado en el paquete contratado; asesoramiento
legal, aduanero, impositivo o regulatorio (ver la Sección 6); ejecución de
decisiones comerciales (negociar con proveedores, aprobar compras, fijar
precios) — el Proveedor entrega el análisis y la recomendación, **el
Cliente decide y ejecuta**.

`[REVISAR CON ABOGADO: confirmar que esta sección referencia correctamente
el paquete específico contratado antes de cada firma — copiar/pegar el
alcance exacto del one-pager en vez de solo linkearlo, para que el contrato
sea autocontenido]`

## 3 · Garantía de calidad (QA)

Cada análisis entregado pasa una compuerta de control de calidad (QA)
automática antes de emitirse. Si un solo análisis del paquete no la pasa,
el paquete completo no se entrega — el Proveedor nunca entrega números a
medias ni resultados parcialmente validados.

Esta garantía es sobre el **proceso** de validación (consistencia interna,
rangos plausibles, trazabilidad de cada cifra a su fuente), no una garantía
de resultado de negocio — ver la Sección 5 (Límite de responsabilidad).

## 4 · Honorarios y facturación

**Si el paquete es de precio fijo** (todos excepto Sprint de Liquidación):
el Cliente paga **[MONTO — ver el one-pager]** según la cadencia del
paquete (`[único / mensual / quincenal]`). `[REVISAR CON ABOGADO: definir
método de pago, moneda, tratamiento de mora, y si corresponde un anticipo
antes de empezar el sprint]`.

**Si el paquete es Sprint de Liquidación** (precio contingente): el Cliente
recibe una **estimación** de honorarios al arrancar el sprint — es una
proyección, no una factura. El honorario final se factura sobre el
**recupero real** de cash, nunca sobre la proyección inicial, a una tasa de
**[10–20]%** acordada por adelantado (piso de USD 1.500). Si el sprint no
recupera cash, no se cobra honorario sobre el resultado (el piso, si
aplica, se acuerda aparte). `[REVISAR CON ABOGADO: el piso de USD 1.500 —
¿aplica siempre o solo si el Cliente decide no ejecutar ninguna
recomendación? Definir el escenario exacto antes de firmar]`.

`[REVISAR CON ABOGADO: cláusula de mora, moneda de facturación si el
Cliente opera en un país distinto, y tratamiento impositivo (IVA/retenciones
según jurisdicción)]`

## 5 · Límite de responsabilidad

`[REVISAR CON ABOGADO — esta es la cláusula de mayor riesgo del documento]`

Los entregables del Proveedor son **recomendaciones analíticas** basadas en
los datos que el Cliente suministra. El Proveedor no garantiza un resultado
de negocio específico (ahorro, recupero de cash, nivel de servicio
alcanzado) — la garantía de la Sección 3 cubre el proceso de validación, no
el resultado comercial de seguir (o no seguir) la recomendación.

El Cliente es responsable de: (a) la exactitud de los datos que suministra
(el Proveedor no audita ni corrige datos fuente más allá de lo que la
auditoría de calidad de datos del paquete, si está incluida, detecta
explícitamente); (b) toda decisión comercial tomada a partir del análisis
(negociar, comprar, liquidar, fijar precio); (c) validar cualquier
recomendación contra su propio criterio de negocio antes de ejecutarla.

`[REVISAR CON ABOGADO: definir un tope de responsabilidad — la práctica
habitual en contratos de consultoría es limitar la responsabilidad total del
Proveedor a los honorarios efectivamente cobrados en los últimos
[N] meses/el ciclo en curso, excluyendo dolo o negligencia grave. Sin este
tope, la exposición del Proveedor es indefinida]`

## 6 · Fuera del alcance: asesoramiento legal, aduanero e impositivo

Linchpin señala explícitamente cuándo una decisión requiere asesoramiento
legal, aduanero o impositivo especializado (ver el enrutamiento a
`legal / agente aduanal licenciado` en `src/escalation.py`), pero **no
brinda ese asesoramiento**. Cualquier recomendación relacionada con
clasificación arancelaria, cumplimiento normativo, contratos con terceros o
implicancias impositivas debe ser validada por un profesional matriculado
antes de actuar sobre ella.

## 7 · Datos del Cliente y confidencialidad

El tratamiento de los datos que el Cliente suministra (qué se procesa, con
qué finalidad, dónde se envía, cuánto se retiene) está descrito en detalle
en el anexo [dpa-lite.md](dpa-lite.md), que forma parte integral de este
Acuerdo.

Ambas partes se comprometen a mantener confidencial la información
comercial no pública compartida en el marco de este Acuerdo (precios,
datos operativos, estrategia). `[REVISAR CON ABOGADO: definir plazo de la
obligación de confidencialidad — ¿sobrevive la terminación del contrato?
¿Por cuánto tiempo?]`

## 8 · Propiedad intelectual

El motor de análisis de Linchpin (el código fuente del repositorio) se
distribuye bajo licencia MIT (ver [LICENSE](../../LICENSE)) y no se
relicencia ni se transfiere por este Acuerdo. Los **entregables producidos
específicamente para el Cliente** (los reportes, planillas y
recomendaciones de su análisis) son propiedad del Cliente una vez
entregados y pagados en su totalidad.

`[REVISAR CON ABOGADO: confirmar que esta distinción entre "motor" (MIT,
no transferible) y "entregable" (propiedad del Cliente) es la intención
comercial correcta, y agregar una cláusula de licencia de uso si el
Proveedor quisiera retener algún derecho sobre los entregables — p. ej.
usarlos de forma anonimizada como caso de estudio]`

## 9 · Escritura sobre sistemas del Cliente (*writeback*)

Si el paquete contratado incluye *writeback* hacia el sistema del Cliente
(por ejemplo, reposición Odoo — ver `src/connectors/odoo.py`), aplica lo
siguiente, sin excepción:

- Ningún cambio se aplica directamente. Todo cambio propuesto se prepara
  primero como un *changeset* de solo lectura (dry-run) que el Cliente
  puede revisar antes de que exista cualquier efecto real.
- Los cambios se clasifican por nivel de riesgo: **de solo lectura**,
  **reversibles** (se pueden deshacer, p. ej. modificar un punto de
  reorden) e **irreversibles** (no se pueden deshacer de forma segura, p.
  ej. enviar una orden de compra).
- **Todo cambio irreversible requiere aprobación explícita y expresa del
  Cliente antes de aplicarse — sin excepción, sin importar el paquete o
  la cadencia contratada.**
- Todo cambio aplicado queda auditado y es reversible cuando es
  técnicamente posible (ver la Sección 5 de `src/writeback.py`).

`[REVISAR CON ABOGADO: definir quién es responsable si un cambio aprobado
por el Cliente resulta perjudicial una vez aplicado — el Proveedor aplicó
exactamente lo que el Cliente aprobó, pero conviene dejarlo explícito]`

## 10 · Vigencia y terminación

`[REVISAR CON ABOGADO: definir plazo inicial, renovación automática o no,
preaviso de terminación (sugerido: 30 días para paquetes mensuales), y
qué pasa con un ciclo ya facturado/en curso al momento de la terminación]`

## 11 · Ley aplicable y jurisdicción

`[REVISAR CON ABOGADO: completar según la jurisdicción real del Proveedor
y, si corresponde, negociar con el Cliente. No dejar en blanco al firmar]`

## 12 · Firmas

| | Nombre | Cargo | Fecha | Firma |
|---|---|---|---|---|
| **Proveedor** | | | | |
| **Cliente** | | | | |
