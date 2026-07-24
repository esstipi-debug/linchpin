"""Stocky -> Shopify-native migration-readiness assessment (Kern catalog rung
#2, the "Chequeo de migracion Stocky" -- documentation/MONETIZATION_BRIEF.md).

Shopify is shutting Stocky down; a merchant exporting their Stocky data has to
answer one question before the deadline: **does Shopify's own native inventory
cover what Stocky did for me, or is there a gap I need to fill?** This module
answers it honestly.

The whole assessment is grounded in ONE explicit, auditable constant --
:data:`SHOPIFY_NATIVE_COVERAGE` -- so every "this migrates cleanly" / "this is
a gap" verdict traces to a stated fact about what Shopify native does and does
not do, never to prose invented per run. Shopify native tracks stock
quantities per location; it does NOT manage purchase orders, supplier records,
min/max reorder automation, or demand forecasting -- exactly the layer Stocky
added on top, and exactly the layer Kern replaces. The honest verdict is
therefore usually "native alone does not replace Stocky", which is precisely
the concrete hook to Starter / the full Diagnostico -- sold as a fact the
merchant can verify, never as a scare.

Pure functions over a parsed ``jobs.stocky_importer.StockyMigrationBatch``: no
IO, no network, no Shopify API. The merchant provides CSV exports; this reads
the already-parsed batch and returns a verdict object for the job layer to
render.
"""

from __future__ import annotations

from dataclasses import dataclass

from jobs.stocky_importer import StockyMigrationBatch

# The single source of truth for every verdict below: whether Shopify's OWN
# native inventory (no third-party app) covers a given Stocky data category,
# and the stated reason. Auditable and easy to correct in one place if
# Shopify's native feature set changes.
SHOPIFY_NATIVE_COVERAGE: dict[str, tuple[bool, str]] = {
    "reorder_points": (
        False,
        "Shopify nativo no automatiza puntos de reorden min/max: solo muestra la cantidad "
        "en stock. La logica de cuando/cuanto reponer es lo que agregaba Stocky.",
    ),
    "purchase_orders": (
        False,
        "Shopify nativo no gestiona ordenes de compra ni su historial (recibido vs pedido, "
        "costo por unidad). Esa capa la aportaba Stocky.",
    ),
    "suppliers": (
        False,
        "Shopify nativo no guarda registros de proveedor (lead time, MOQ, contacto) ligados "
        "al inventario. Se pierden en la migracion a nativo.",
    ),
    "demand_forecasting": (
        False,
        "Shopify nativo no pronostica demanda ni sugiere cantidades de reorden basadas en "
        "historial. Requiere una herramienta como Kern con tu historial de ventas.",
    ),
}

# Which parsed categories the assessment inspects, and how to count them.
_CATEGORY_COUNTERS = {
    "suppliers": lambda b: len(b.suppliers),
    "purchase_orders": lambda b: len(b.purchase_orders),
    "reorder_points": lambda b: len(b.reorder_points),
}


@dataclass(frozen=True)
class SkuMasterAudit:
    """Purpose-built structural check on the Stocky reorder/PO data BEFORE
    migration -- the honest "is this data clean enough to carry over?" audit.

    Deliberately NOT Kern's generic ``data_quality`` tool: that one fuzzy-dedups
    on product NAMES and validates GTINs, neither of which a Stocky reorder/PO
    export carries -- running it here would false-cluster every name-less SKU
    into one "duplicate" bucket and report a meaningless 0% score. These three
    checks are exactly the defects that actually break a reorder-point
    migration: the same SKU listed twice, a min above its max, and a
    non-positive reorder point."""

    n_skus: int
    duplicate_skus: tuple[str, ...]
    inconsistent_minmax: tuple[str, ...]
    nonpositive_reorder: tuple[str, ...]
    clean: bool
    summary: str


def audit_sku_master(batch: StockyMigrationBatch) -> SkuMasterAudit:
    """Structural pre-migration audit of the reorder-point master."""
    seen: dict[str, int] = {}
    for rp in batch.reorder_points:
        seen[rp.sku] = seen.get(rp.sku, 0) + 1
    duplicate = tuple(sorted(sku for sku, n in seen.items() if n > 1))
    inconsistent = tuple(
        sorted({rp.sku for rp in batch.reorder_points if rp.max_reorder_point and rp.min_reorder_point > rp.max_reorder_point})
    )
    nonpositive = tuple(sorted({rp.sku for rp in batch.reorder_points if rp.min_reorder_point <= 0}))

    n_skus = len({rp.sku for rp in batch.reorder_points} | {po.sku for po in batch.purchase_orders})
    n_issues = len(set(duplicate) | set(inconsistent) | set(nonpositive))
    clean = n_issues == 0 and bool(batch.reorder_points)
    if not batch.reorder_points:
        summary = "Sin puntos de reorden exportados -- no hay maestro de SKUs para auditar."
    elif clean:
        summary = f"{n_skus} SKUs: maestro de reorden limpio (sin duplicados, min<=max, reorden positivo)."
    else:
        summary = (
            f"{n_skus} SKUs, {n_issues} con defectos: {len(duplicate)} SKU duplicado(s), "
            f"{len(inconsistent)} con min>max, {len(nonpositive)} con reorden <=0. Limpiar antes de migrar."
        )
    return SkuMasterAudit(
        n_skus=n_skus,
        duplicate_skus=duplicate,
        inconsistent_minmax=inconsistent,
        nonpositive_reorder=nonpositive,
        clean=clean,
        summary=summary,
    )


@dataclass(frozen=True)
class CategoryVerdict:
    """One Stocky data category's migration verdict.

    ``verdict`` is ``"migrates_clean"`` (Shopify native covers it),
    ``"gap"`` (present in the export but no native home -> needs Kern), or
    ``"not_in_export"`` (the merchant did not export this category, so no
    claim is made -- golden rule "ningun cap silencioso": absence is reported,
    never assumed clean)."""

    category: str
    present: bool
    record_count: int
    shopify_native_covers: bool
    verdict: str
    detail: str


@dataclass(frozen=True)
class MigrationOption:
    label: str
    rationale: str


@dataclass(frozen=True)
class MigrationAssessment:
    """The honest answer to "does Shopify native replace Stocky for me?"."""

    categories: tuple[CategoryVerdict, ...]
    shopify_native_sufficient: bool
    headline: str
    gaps: tuple[str, ...]
    recommended_options: tuple[MigrationOption, ...]


def _category_verdict(category: str, count: int) -> CategoryVerdict:
    covered, reason = SHOPIFY_NATIVE_COVERAGE.get(
        category, (False, "Sin cobertura nativa conocida.")
    )
    present = count > 0
    if not present:
        return CategoryVerdict(
            category=category,
            present=False,
            record_count=0,
            shopify_native_covers=covered,
            verdict="not_in_export",
            detail="No incluido en los exports entregados -- no se evalua.",
        )
    verdict = "migrates_clean" if covered else "gap"
    return CategoryVerdict(
        category=category,
        present=True,
        record_count=count,
        shopify_native_covers=covered,
        verdict=verdict,
        detail=reason if not covered else "Cubierto por Shopify nativo.",
    )


def assess_migration(batch: StockyMigrationBatch) -> MigrationAssessment:
    """Classify each Stocky data category against Shopify-native coverage and
    return the overall verdict plus ranked next-step options.

    The verdict is data-driven: a category is a ``gap`` only when the merchant
    actually exported records for it AND Shopify native does not cover it.
    ``demand_forecasting`` is always evaluated as a gap-if-relevant signal --
    Stocky's migration exports never carry a sales history, so forecasting is
    inherently something the merchant loses on the move to native (surfaced
    whenever ANY inventory data was exported, since a catalog worth migrating
    is a catalog worth forecasting).
    """
    verdicts: list[CategoryVerdict] = [
        _category_verdict(cat, counter(batch)) for cat, counter in _CATEGORY_COUNTERS.items()
    ]

    # demand_forecasting has no direct Stocky export; treat it as "present"
    # (a real loss) whenever the merchant exported any inventory data at all.
    has_any_inventory = any(v.present for v in verdicts)
    forecasting_count = 1 if has_any_inventory else 0
    verdicts.append(_category_verdict("demand_forecasting", forecasting_count))

    gaps = tuple(v.category for v in verdicts if v.verdict == "gap")

    if not has_any_inventory:
        # Nothing to assess -- do NOT reassure the merchant that native "alcanza"
        # off zero data (that would be a silent cap on an empty input).
        return MigrationAssessment(
            categories=tuple(verdicts),
            shopify_native_sufficient=False,
            headline="No se exportaron datos de Stocky para evaluar. Entrega los CSV de proveedores, "
            "ordenes de compra y puntos de reorden para correr el chequeo.",
            gaps=(),
            recommended_options=(
                MigrationOption(
                    "Entrega tus exports de Stocky",
                    "El chequeo necesita al menos uno de: proveedores, ordenes de compra o puntos de reorden.",
                ),
            ),
        )

    sufficient = not gaps

    if sufficient:
        headline = (
            "Shopify nativo te alcanza: los datos exportados no dependen de capacidades "
            "que solo Stocky/Kern ofrecen."
        )
        options = (
            MigrationOption(
                "Quedate en Shopify nativo",
                "No se detectaron brechas: migra tus cantidades y segui operando en nativo.",
            ),
        )
    else:
        gap_labels = ", ".join(gaps)
        headline = (
            f"Shopify nativo NO te alcanza: {len(gaps)} brecha(s) sin hogar nativo "
            f"({gap_labels}). Ese trabajo lo hacia Stocky y lo reemplaza Kern."
        )
        options = (
            MigrationOption(
                "Kern Starter LatAm (USD 250-300/mes)",
                "Cubre las brechas detectadas (reorden, proveedores, forecasting) con revision "
                "humana; el escalon natural desde el chequeo.",
            ),
            MigrationOption(
                "Diagnostico de Arranque (USD 1.500-2.500, una vez)",
                "Si primero queres cuantificar el ahorro/riesgo antes de un retainer mensual.",
            ),
            MigrationOption(
                "Quedate en Shopify nativo (con las brechas asumidas)",
                "Viable solo si aceptas perder ordenes de compra, proveedores y automatizacion "
                "de reorden.",
            ),
        )

    return MigrationAssessment(
        categories=tuple(verdicts),
        shopify_native_sufficient=sufficient,
        headline=headline,
        gaps=gaps,
        recommended_options=options,
    )
