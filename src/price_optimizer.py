"""Portfolio price optimization (Linchpin 3.0 PR-16, P2 `price_optimization`).

Turns a (possibly category-shrunk) :class:`~src.elasticity_batch.SkuElasticityFit`
into a concrete price recommendation, extending ``src/pricing.py``'s existing
``optimal_price_constant_elasticity`` (``p* = c*eps/(eps+1)``) with the batch
signal from ``src/elasticity_batch.py`` and a margin/price-band constraint
reused from ``src/constraints.py``.

**Pure function, no I/O** (repo rule: ``src/`` is pure, writeback/network I/O
stays in ``src/connectors/``/``acquire/``). Any competitor-price signal
(pricing_intel's ``PriceLedger``) must already be resolved by the caller --
this module never reads the ledger itself. See :class:`CompetitorPriceContext`.

**Constraint reuse.** ``src/constraints.py``'s ``InventoryItem``/
``allocate_under_budget`` machinery is about order-QUANTITY portfolio
budgets and does not map onto a per-unit price. ``apply_order_rules``,
however, is a generic "floor, round to a multiple, cap" composer that does
not care whether the number is a quantity or a price -- it is reused
verbatim here: the landed-cost-plus-margin floor as
``minimum_order_quantity``, an optional price-tick rounding as
``order_multiple``, and an optional price ceiling (e.g. a MAP/legal band)
as ``max_quantity``.

**needs_data, never a fabricated number** (plan QA invariant for P2): a
result is ``"needs_data"`` -- no ``proposed_price`` -- whenever
``sku_fit.identified`` is ``False``, or ``sku_fit.ci_excludes_zero`` is
``False``, or the SKU's own 95% CI does not exclude **-1** in the elastic
direction (``ci_high >= -1`` -- the markup ``p* = c*eps/(eps+1)`` explodes
as ``eps -> -1`` from below, e.g. ``eps = -1.05`` implies 21x cost, so a CI
merely excluding zero is not enough statistical ground to price off it; see
``src/elasticity_batch.py``'s module docstring for why the gate uses the
SKU's own CI, not a shrinkage-adjusted one), or the shrunk elasticity is
inelastic (``>= -1``, no interior profit-maximizing price -- mirrors
``src.pricing.optimal_price_constant_elasticity``'s own contract).

**Never a wild swing** (audit fix): an "ok" proposal is additionally clamped
to (a) at most ``max_move_pct`` (default +/-20%) away from ``current_price``
per step, and (b) ~1.3x the observed price range the elasticity was fitted
on (``SkuElasticityFit.price_low``/``price_high`` -- the same extrapolation
guard ``src.pricing.recommend_price`` applies to its ``confident`` flag).
Every clamp is disclosed on the result (``move_clamped``/``range_clamped``)
so deliverables can say so. The landed-cost/margin floor still wins over
both clamps -- a proposal is never below cost because the current price is.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from src.constraints import apply_order_rules
from src.elasticity_batch import SkuElasticityFit
from src.pricing import _MAX_EXTRAPOLATION as MAX_RANGE_EXTRAPOLATION
from src.pricing import optimal_price_constant_elasticity

if TYPE_CHECKING:  # pragma: no cover - typing only, no runtime coupling
    from src.pricing_intel.ledger import LedgerRecord

MIN_MARGIN_DEFAULT = 0.0  # no minimum margin fraction above landed cost unless the caller sets one

# Default per-step band vs current_price: a proposal never moves a live price
# by more than this fraction in one step, whatever the elasticity math says
# (None disables). Repricing is iterative -- re-fit and step again next cycle.
MAX_MOVE_PCT_DEFAULT = 0.2

STATUS_OK = "ok"
STATUS_NEEDS_DATA = "needs_data"


@dataclass(frozen=True)
class CompetitorPriceContext:
    """A competitor-price signal to surface alongside a recommendation --
    CONTEXT only, never a silent override of the elasticity-driven price
    (plan rule 7, total provenance: every externally-observed number carries
    its acquisition tier and timestamp). Callers resolve this from an
    already-fetched ``pricing_intel.ledger.PriceLedger`` record; this module
    performs no ledger I/O itself (see module docstring).
    """

    site: str
    competitor_price: float
    acquisition_tier: str  # "L0".."L3", cited verbatim (plan rule 7)
    observed_at: datetime
    currency: str = "USD"  # pricing_intel's price_normalized convention (BASE_CURRENCY)

    @staticmethod
    def from_ledger_record(record: "LedgerRecord") -> "CompetitorPriceContext":
        """Pure transform from an already-fetched pricing_intel ledger
        record. The ledger read itself is I/O and stays outside this module
        (see module docstring) -- callers fetch via
        ``PriceLedger.latest_for_product``/``latest_by_sku`` and hand the
        result in here."""
        offer = record.offer
        return CompetitorPriceContext(
            site=offer.site,
            competitor_price=float(offer.price_normalized),
            acquisition_tier=offer.acquisition_tier,
            observed_at=offer.observed_at,
        )


@dataclass(frozen=True)
class PriceOptimizationResult:
    """One SKU's price recommendation -- or, when there is not enough
    statistical signal, an explicit ``needs_data`` result with no price."""

    product_id: str
    status: str  # "ok" | "needs_data"
    reason: str | None  # populated when status == "needs_data"
    current_price: float | None
    proposed_price: float | None
    landed_cost: float
    elasticity_used: float | None  # the (shrunk) elasticity actually applied
    shrinkage_weight: float | None
    category: str | None
    floor_applied: bool  # True when the cost/margin floor overrode elasticity math
    price_capped: bool  # True when max_price overrode elasticity math
    competitor_context: CompetitorPriceContext | None
    # Disclosure flags for the two sanity clamps (audit fix) -- deliverables
    # must be able to say "this number was clamped, not the raw optimum".
    move_clamped: bool = False  # +/-max_move_pct band vs current_price engaged
    range_clamped: bool = False  # ~1.3x observed-price-range band engaged


def _needs_data(
    sku_fit: SkuElasticityFit,
    reason: str,
    *,
    current_price: float | None,
    landed_cost: float,
    competitor_context: CompetitorPriceContext | None,
) -> PriceOptimizationResult:
    return PriceOptimizationResult(
        product_id=sku_fit.product_id,
        status=STATUS_NEEDS_DATA,
        reason=reason,
        current_price=current_price,
        proposed_price=None,
        landed_cost=landed_cost,
        elasticity_used=None,
        shrinkage_weight=sku_fit.shrinkage_weight,
        category=sku_fit.category,
        floor_applied=False,
        price_capped=False,
        competitor_context=competitor_context,
        move_clamped=False,
        range_clamped=False,
    )


def optimize_sku_price(
    sku_fit: SkuElasticityFit,
    *,
    landed_cost: float,
    current_price: float | None = None,
    min_margin_pct: float = MIN_MARGIN_DEFAULT,
    price_increment: float = 0.0,
    max_price: float | None = None,
    max_move_pct: float | None = MAX_MOVE_PCT_DEFAULT,
    competitor_context: CompetitorPriceContext | None = None,
) -> PriceOptimizationResult:
    """Propose a margin-maximizing price for one SKU from its (shrunk)
    elasticity, never below ``landed_cost * (1 + min_margin_pct)``.

    ``price_increment`` rounds the proposed price up to the nearest multiple
    (e.g. ``0.05``); ``max_price`` is an optional ceiling (e.g. a MAP/legal
    band from ``src/pricing_guardrails.py``, P5 -- a later PR). Both reuse
    ``src.constraints.apply_order_rules`` verbatim (see module docstring).

    ``max_move_pct`` bounds a single step vs ``current_price`` (default
    +/-20%, ``None`` disables); the observed-price-range clamp engages
    whenever ``sku_fit`` carries ``price_low``/``price_high``. See the
    module docstring ("Never a wild swing") for both bands' semantics.
    """
    if landed_cost <= 0:
        raise ValueError("landed_cost must be > 0")
    if not (0.0 <= min_margin_pct < 1.0):
        raise ValueError("min_margin_pct must be within [0, 1)")
    if price_increment < 0:
        raise ValueError("price_increment must be >= 0")
    if max_price is not None and max_price <= 0:
        raise ValueError("max_price must be > 0 when given")
    if max_move_pct is not None and max_move_pct <= 0:
        raise ValueError("max_move_pct must be > 0 when given (None disables the move clamp)")

    if not sku_fit.identified:
        return _needs_data(
            sku_fit,
            "no price variation observed for this SKU (ElasticityFit.identified is False)",
            current_price=current_price, landed_cost=landed_cost, competitor_context=competitor_context,
        )
    if not sku_fit.ci_excludes_zero:
        return _needs_data(
            sku_fit,
            f"95% CI on elasticity crosses zero ({sku_fit.ci_low:.3f}, {sku_fit.ci_high:.3f}) "
            "-- not enough signal to move price",
            current_price=current_price, landed_cost=landed_cost, competitor_context=competitor_context,
        )

    elasticity = sku_fit.shrunk_elasticity if sku_fit.shrunk_elasticity is not None else sku_fit.elasticity
    if elasticity >= -1:
        return _needs_data(
            sku_fit,
            f"elasticity {elasticity:.3f} is inelastic (>= -1) -- no interior profit-maximizing price",
            current_price=current_price, landed_cost=landed_cost, competitor_context=competitor_context,
        )
    # The markup p* = c*eps/(eps+1) explodes as eps -> -1 from below (eps =
    # -1.05 implies 21x cost), so excluding zero is NOT enough: the SKU's own
    # CI must place the elasticity firmly in the elastic region (ci_high < -1)
    # before any price is derived from it (audit fix 1).
    if sku_fit.ci_high is None or sku_fit.ci_high >= -1.0:
        ci_low_txt = "n/a" if sku_fit.ci_low is None else f"{sku_fit.ci_low:.3f}"
        ci_high_txt = "n/a" if sku_fit.ci_high is None else f"{sku_fit.ci_high:.3f}"
        return _needs_data(
            sku_fit,
            f"95% CI on elasticity ({ci_low_txt}, {ci_high_txt}) does not exclude -1 -- the markup "
            "p* = c*eps/(eps+1) is unstable near -1, so this is not enough signal to price off elasticity",
            current_price=current_price, landed_cost=landed_cost, competitor_context=competitor_context,
        )

    p_star = optimal_price_constant_elasticity(landed_cost, elasticity)
    assert p_star is not None  # elasticity < -1 guaranteed above

    # Sanity clamps (audit fix 2), tightest-last so the operational band vs
    # the live price binds when the two conflict; the cost floor below still
    # wins over both. Each clamp is disclosed on the result.
    target = p_star
    range_clamped = False
    if sku_fit.price_low is not None and sku_fit.price_high is not None and sku_fit.price_low > 0:
        range_bound = min(max(target, sku_fit.price_low / MAX_RANGE_EXTRAPOLATION),
                          sku_fit.price_high * MAX_RANGE_EXTRAPOLATION)
        range_clamped = range_bound != target
        target = range_bound
    move_clamped = False
    if current_price is not None and current_price > 0 and max_move_pct is not None:
        move_bound = min(max(target, current_price * (1.0 - max_move_pct)),
                         current_price * (1.0 + max_move_pct))
        move_clamped = move_bound != target
        target = move_bound

    floor_price = landed_cost * (1.0 + min_margin_pct)
    floor_applied = target < floor_price
    pre_cap = apply_order_rules(target, minimum_order_quantity=floor_price, order_multiple=price_increment)
    proposed = pre_cap if max_price is None else min(pre_cap, max_price)
    price_capped = max_price is not None and pre_cap > max_price

    return PriceOptimizationResult(
        product_id=sku_fit.product_id,
        status=STATUS_OK,
        reason=None,
        current_price=current_price,
        proposed_price=float(proposed),
        landed_cost=landed_cost,
        elasticity_used=elasticity,
        shrinkage_weight=sku_fit.shrinkage_weight,
        category=sku_fit.category,
        floor_applied=floor_applied,
        price_capped=price_capped,
        competitor_context=competitor_context,
        move_clamped=move_clamped,
        range_clamped=range_clamped,
    )


def optimize_portfolio_prices(
    fits: dict[str, SkuElasticityFit],
    *,
    landed_costs: dict[str, float],
    current_prices: dict[str, float] | None = None,
    min_margin_pct: float = MIN_MARGIN_DEFAULT,
    price_increment: float = 0.0,
    max_prices: dict[str, float] | None = None,
    max_move_pct: float | None = MAX_MOVE_PCT_DEFAULT,
    competitor_contexts: dict[str, CompetitorPriceContext] | None = None,
) -> dict[str, PriceOptimizationResult]:
    """Optimize every SKU in ``fits`` (typically
    ``src.elasticity_batch.estimate_portfolio_elasticities``'s output). Some
    SKUs return a real price, others ``needs_data``, in the same call -- a
    missing ``landed_costs`` entry is itself a ``needs_data`` result rather
    than a ``KeyError``, matching the "no signal -> needs_data, never a
    fabricated number" invariant.
    """
    current_prices = current_prices or {}
    max_prices = max_prices or {}
    competitor_contexts = competitor_contexts or {}

    out: dict[str, PriceOptimizationResult] = {}
    for product_id, sku_fit in fits.items():
        landed_cost = landed_costs.get(product_id)
        if landed_cost is None:
            out[product_id] = _needs_data(
                sku_fit,
                "no landed cost supplied for this SKU",
                current_price=current_prices.get(product_id),
                landed_cost=0.0,
                competitor_context=competitor_contexts.get(product_id),
            )
            continue
        out[product_id] = optimize_sku_price(
            sku_fit,
            landed_cost=landed_cost,
            current_price=current_prices.get(product_id),
            min_margin_pct=min_margin_pct,
            price_increment=price_increment,
            max_price=max_prices.get(product_id),
            max_move_pct=max_move_pct,
            competitor_context=competitor_contexts.get(product_id),
        )
    return out
