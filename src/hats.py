"""Four-hat decision substrate over one replenishment decision (Q, SL).

Spec: docs/superpowers/specs/2026-07-20-hats-n4-n5-design.md (D1-D8).
Four role "hats" (comprador / planner / cfo / comercial) score the SAME
candidate (order_quantity, service_level) with their own pure utility; a
neutral judge cost values any candidate in $ without deciding. `Hat` lives
BESIDE scm_agent.modes.Mode (D7): src/ never imports scm_agent; `mode_key`
is a soft string reference, never resolved here.

Weights are an explicit OPERATOR POLICY (D4), not an objective consensus:
`parse_weights` validates and renormalizes them, and every surface that
prints a settlement repeats that framing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.eoq import PriceBreak, compute_eoq, compute_eoq_volume_discount
from src.fill_rate import fill_rate_from_safety_stock, normal_loss_standard
from src.financial_kpis import days_inventory_outstanding
from src.safety_stock import safety_stock, service_level_factor

HAT_COMPRADOR = "comprador"
HAT_PLANNER = "planner"
HAT_CFO = "cfo"
HAT_COMERCIAL = "comercial"
HAT_KEYS: tuple[str, ...] = (HAT_COMPRADOR, HAT_PLANNER, HAT_CFO, HAT_COMERCIAL)

# D1: the settlement domain is a 2D grid, anchored on closed-form quantities.
SL_GRID: tuple[float, ...] = (0.90, 0.925, 0.95, 0.975, 0.99)
N_Q_POINTS = 25
Q_SPAN_LO = 0.5     # x min(Q_eoq, Q_disc)
Q_SPAN_HI = 1.25    # x max(Q_eoq, Q_disc)

# D8: synthetic default price breaks for the testbed (labeled "(assumed)").
ASSUMED_BREAK_TIERS: tuple[tuple[float, float], ...] = ((2.0, 0.98), (4.0, 0.96))

DEFAULT_WEIGHTS: dict[str, float] = {k: 0.25 for k in HAT_KEYS}


@dataclass(frozen=True)
class Hat:
    """A role profile over the replenishment decision. Descriptive only: the
    utility is a pure function elsewhere in this module, never a field, and
    `tool_keys`/`mode_key` are soft references (strings), never resolved."""

    key: str
    label: str
    objetivo: str
    kpis: tuple[str, ...]
    tool_keys: frozenset[str]
    mode_key: str | None


HATS: dict[str, Hat] = {
    HAT_COMPRADOR: Hat(
        key=HAT_COMPRADOR, label="Comprador",
        objetivo="minimizar el costo unitario efectivo de compra (capturar descuentos por volumen)",
        kpis=("costo unitario efectivo", "ordenes por anio"),
        tool_keys=frozenset({"inventory_optimization", "sourcing"}), mode_key="scm"),
    HAT_PLANNER: Hat(
        key=HAT_PLANNER, label="Planner",
        objetivo="minimizar costo de ordenar + mantener cumpliendo el nivel de servicio objetivo",
        kpis=("costo de politica", "nivel de servicio", "safety stock"),
        tool_keys=frozenset({"inventory_optimization", "forecast"}), mode_key="inventory"),
    HAT_CFO: Hat(
        key=HAT_CFO, label="CFO",
        objetivo="minimizar el cargo de capital sobre el inventario promedio (WACC)",
        kpis=("cargo de capital", "inventario promedio", "DIO"),
        tool_keys=frozenset({"financial_kpis", "cost_to_serve"}), mode_key="scm"),
    HAT_COMERCIAL: Hat(
        key=HAT_COMERCIAL, label="Comercial",
        objetivo="maximizar el fill rate (disponibilidad para vender)",
        kpis=("fill rate", "unidades cortas esperadas por anio"),
        tool_keys=frozenset({"inventory_optimization", "pricing"}), mode_key="scm"),
}


@dataclass(frozen=True)
class HatConfig:
    """Effective parameters (the spec's "params efectivos"), all injectable.

    D5 - no double counting of capital: `holding_rate` is the repo's h_total
    (0.25/yr, INCLUDING capital). It decomposes into `wacc` (capital slice,
    what the CFO hat charges) and `h_oop = holding_rate - wacc` (warehouse,
    insurance, shrink). The judge uses h_total; the CFO hat uses ONLY wacc.
    """

    order_cost: float = 75.0
    holding_rate: float = 0.25
    wacc: float = 0.12
    sl_target: float = 0.95
    gross_margin_rate: float = 0.30
    periods_per_year: float = 52.0

    def __post_init__(self) -> None:
        if self.order_cost <= 0:
            raise ValueError("order_cost must be > 0")
        if self.holding_rate <= 0:
            raise ValueError("holding_rate must be > 0")
        if not 0 < self.wacc < self.holding_rate:
            raise ValueError(
                f"wacc must satisfy 0 < wacc < holding_rate (got wacc={self.wacc}, "
                f"holding_rate={self.holding_rate}) - capital is a SLICE of h_total (D5)")
        if not 0 < self.sl_target < 1:
            raise ValueError("sl_target must be in (0, 1)")
        if not 0 <= self.gross_margin_rate < 1:
            raise ValueError("gross_margin_rate must be in [0, 1)")
        if self.periods_per_year <= 0:
            raise ValueError("periods_per_year must be > 0")

    @property
    def h_oop(self) -> float:
        """Out-of-pocket holding slice (h_total - WACC)."""
        return self.holding_rate - self.wacc


@dataclass(frozen=True)
class HatInputs:
    """One SKU's decision inputs. `price_breaks_assumed` marks the D8
    synthetic default so every output can carry the "(assumed)" label."""

    sku: str
    annual_demand: float
    mean_weekly: float
    std_weekly: float
    lead_time_weeks: float
    unit_cost: float
    price_breaks: tuple[PriceBreak, ...]
    price_breaks_assumed: bool
    config: HatConfig

    def __post_init__(self) -> None:
        if self.annual_demand <= 0:
            raise ValueError(f"{self.sku}: annual_demand must be > 0")
        if self.mean_weekly <= 0:
            raise ValueError(f"{self.sku}: mean_weekly must be > 0")
        if self.std_weekly < 0:
            raise ValueError(f"{self.sku}: std_weekly must be >= 0")
        if self.lead_time_weeks <= 0:
            raise ValueError(f"{self.sku}: lead_time_weeks must be > 0")
        if self.unit_cost <= 0:
            raise ValueError(f"{self.sku}: unit_cost must be > 0")


@dataclass(frozen=True)
class Candidate:
    """One point of the decision grid."""

    order_quantity: float
    service_level: float

    def __post_init__(self) -> None:
        if self.order_quantity <= 0:
            raise ValueError("order_quantity must be > 0")
        if not 0 < self.service_level < 1:
            raise ValueError("service_level must be in (0, 1)")


@dataclass(frozen=True)
class HatEvaluation:
    """One hat's score of one candidate."""

    hat_key: str
    candidate: Candidate
    utility_raw: float
    utility_norm: float
    kpis: dict = field(default_factory=dict)


def parse_weights(raw: str | dict | None) -> dict[str, float]:
    """Parse and validate the settlement weights (D4: an explicit operator
    POLICY, not an objective consensus). Missing hats weigh 0. Renormalized
    to sum 1. Raises ValueError on unknown keys, negatives, or sum <= 0."""
    if raw is None:
        return dict(DEFAULT_WEIGHTS)
    if isinstance(raw, str):
        pairs: dict[str, float] = {}
        for chunk in raw.split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            key, sep, value = chunk.partition("=")
            if not sep:
                raise ValueError(f"weights: expected 'hat=value', got {chunk!r}")
            try:
                pairs[key.strip().lower()] = float(value)
            except ValueError as exc:
                raise ValueError(f"weights: {value!r} is not a number for {key.strip()!r}") from exc
        raw = pairs
    unknown = set(raw) - set(HAT_KEYS)
    if unknown:
        raise ValueError(f"weights: unknown hat key(s) {sorted(unknown)}; valid: {list(HAT_KEYS)}")
    weights = {k: float(raw.get(k, 0.0)) for k in HAT_KEYS}
    if any(w < 0 for w in weights.values()):
        raise ValueError("weights: negative weights are not allowed")
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("weights: sum must be > 0")
    return {k: w / total for k, w in weights.items()}


# -- D8: price breaks ----------------------------------------------------------


def default_price_breaks(
    annual_demand: float, unit_cost: float, config: HatConfig,
) -> tuple[PriceBreak, ...]:
    """Deterministic synthetic tariff for the testbed (D8): -2% at 2x EOQ and
    -4% at 4x EOQ over the base unit cost. Every output that uses this default
    must label it "(assumed)" -- on a real client the breaks come from the
    supplier tariff via params["price_breaks"]."""
    q_eoq = compute_eoq(annual_demand, config.holding_rate * unit_cost, config.order_cost).order_quantity
    return (
        PriceBreak(min_quantity=0.0, unit_cost=unit_cost),
        PriceBreak(min_quantity=2.0 * q_eoq, unit_cost=round(unit_cost * (1 - 0.02), 10)),
        PriceBreak(min_quantity=4.0 * q_eoq, unit_cost=round(unit_cost * (1 - 0.04), 10)),
    )


def build_inputs(
    *,
    sku: str,
    annual_demand: float,
    mean_weekly: float,
    std_weekly: float,
    lead_time_weeks: float,
    unit_cost: float,
    config: HatConfig,
    price_breaks: tuple[PriceBreak, ...] | None = None,
) -> HatInputs:
    """Assemble one SKU's inputs; `price_breaks=None` -> D8 synthetic default."""
    assumed = price_breaks is None
    breaks = (
        default_price_breaks(annual_demand, unit_cost, config)
        if assumed else tuple(price_breaks)
    )
    return HatInputs(
        sku=sku, annual_demand=annual_demand, mean_weekly=mean_weekly,
        std_weekly=std_weekly, lead_time_weeks=lead_time_weeks, unit_cost=unit_cost,
        price_breaks=breaks, price_breaks_assumed=assumed, config=config,
    )


def unit_cost_at(inputs: HatInputs, order_quantity: float) -> float:
    """Piecewise c(Q): the unit cost of the highest tier whose min_quantity <= Q;
    base unit_cost when no tier covers Q (injected tariffs need no base tier)."""
    best = inputs.unit_cost
    for tier in sorted(inputs.price_breaks, key=lambda b: b.min_quantity):
        if order_quantity >= tier.min_quantity:
            best = tier.unit_cost
    return best


# -- Risk-period helpers ---------------------------------------------------------


def sigma_over_lead(inputs: HatInputs) -> float:
    """sigma_L = sigma_w * sqrt(L_w)."""
    return inputs.std_weekly * (inputs.lead_time_weeks ** 0.5)


def ss_units(inputs: HatInputs, service_level: float) -> float:
    """SS(SL) = z(SL) * sigma_w * sqrt(L_w) -- the engine's own safety_stock."""
    return safety_stock(
        inputs.std_weekly, service_level, risk_periods=inputs.lead_time_weeks,
    ).safety_stock


# -- D1: the deterministic 2D grid ----------------------------------------------


def anchor_quantities(inputs: HatInputs) -> tuple[float, float]:
    """(q_eoq, q_disc): the two closed-form anchors, computed BEFORE the grid.

    q_eoq  -- classic EOQ at the base unit cost.
    q_disc -- best Q across the price-break tariff (all-units discounts).
    """
    cfg = inputs.config
    q_eoq = compute_eoq(
        inputs.annual_demand, cfg.holding_rate * inputs.unit_cost, cfg.order_cost,
    ).order_quantity
    q_disc = compute_eoq_volume_discount(
        inputs.annual_demand, cfg.holding_rate, cfg.order_cost, list(inputs.price_breaks),
    ).order_quantity
    return q_eoq, q_disc


def candidate_grid(inputs: HatInputs) -> tuple[Candidate, ...]:
    """SL_GRID x 25 linear Q points on [0.5*min(anchors), 1.25*max(anchors)],
    plus the mandatory candidates q_eoq, q_disc and the baseline Q (== q_eoq,
    see baseline_plan) deduped in. Fixed order: SL asc outer, Q asc inner."""
    q_eoq, q_disc = anchor_quantities(inputs)
    lo = Q_SPAN_LO * min(q_eoq, q_disc)
    hi = Q_SPAN_HI * max(q_eoq, q_disc)
    qs = [lo + i * (hi - lo) / (N_Q_POINTS - 1) for i in range(N_Q_POINTS)]
    for mandatory in (q_eoq, q_disc):        # baseline Q == q_eoq (dedupe handles it)
        if not any(abs(q - mandatory) < 1e-12 for q in qs):
            qs.append(mandatory)
    qs.sort()
    return tuple(
        Candidate(order_quantity=q, service_level=sl) for sl in SL_GRID for q in qs
    )


# -- D3: shortage economics ------------------------------------------------------


def shortage_cost_per_unit(inputs: HatInputs) -> float:
    """p_short = precio - c_base with precio = c_base / (1 - gross_margin_rate):
    a stockout is a lost sale at unit margin (D3). Selling price derives from
    the BASE unit cost -- purchase discounts do not change the shelf price."""
    m = inputs.config.gross_margin_rate
    return inputs.unit_cost * m / (1.0 - m)


def _expected_units_short_per_year(inputs: HatInputs, cand: Candidate) -> float:
    """(D/Q) * sigma_L * L_N(z(SL)); zero when demand has no variability."""
    sigma_l = sigma_over_lead(inputs)
    if sigma_l <= 0:
        return 0.0
    z = service_level_factor(cand.service_level)
    cycles = inputs.annual_demand / cand.order_quantity
    return cycles * sigma_l * float(normal_loss_standard(z))


# -- The neutral judge (spec sec 5) -- values, never decides ------------------------


def decision_cost(inputs: HatInputs, cand: Candidate) -> float:
    """C(Q, SL) = D*c(Q) + K*D/Q + h_total*c(Q)*(Q/2 + SS(SL)) + p_short*E[short].

    Honesty note (spec sec 5): minimizing C directly would be a FIFTH policy with
    implicit weights baked into its coefficients. The hat model exists to make
    that trade-off explicit and auditable -- the judge only VALUES candidates so
    tension and settlements can be compared in $; it never picks the plan.
    """
    cfg = inputs.config
    c_q = unit_cost_at(inputs, cand.order_quantity)
    purchase = inputs.annual_demand * c_q
    ordering = cfg.order_cost * inputs.annual_demand / cand.order_quantity
    holding = cfg.holding_rate * c_q * (cand.order_quantity / 2.0 + ss_units(inputs, cand.service_level))
    shortage = shortage_cost_per_unit(inputs) * _expected_units_short_per_year(inputs, cand)
    return purchase + ordering + holding + shortage


def baseline_plan(inputs: HatInputs) -> Candidate:
    """What Kern ships today (jobs/inventory_optimization.py): (s,Q) via classic
    EOQ at holding_rate*unit_cost with cycle service level 0.95 (= sl_target)
    and a CONSTANT unit cost (no discounts). Pure mirror -- the equivalence
    against the real job is pinned by tests/test_hats_valuation.py."""
    cfg = inputs.config
    q = compute_eoq(
        inputs.annual_demand, cfg.holding_rate * inputs.unit_cost, cfg.order_cost,
    ).order_quantity
    return Candidate(order_quantity=q, service_level=cfg.sl_target)


# -- The four utilities (spec sec 4) -- higher is better -----------------------------


def _u_comprador(inputs: HatInputs, cand: Candidate) -> float:
    """-(c(Q) + K/Q): effective unit purchase cost. Flat in SL."""
    return -(unit_cost_at(inputs, cand.order_quantity)
             + inputs.config.order_cost / cand.order_quantity)


def _u_planner_valid(inputs: HatInputs, cand: Candidate) -> float:
    """-(K*D/Q + h_total*c(Q)*(Q/2 + SS)) -- only meaningful when SL >= sl_target."""
    cfg = inputs.config
    c_q = unit_cost_at(inputs, cand.order_quantity)
    return -(cfg.order_cost * inputs.annual_demand / cand.order_quantity
             + cfg.holding_rate * c_q * (cand.order_quantity / 2.0
                                         + ss_units(inputs, cand.service_level)))


def _u_cfo(inputs: HatInputs, cand: Candidate) -> float:
    """-(WACC * c(Q) * (Q/2 + SS)): the capital slice only (D5, no double count)."""
    c_q = unit_cost_at(inputs, cand.order_quantity)
    return -(inputs.config.wacc * c_q * (cand.order_quantity / 2.0
                                         + ss_units(inputs, cand.service_level)))


def _u_comercial(inputs: HatInputs, cand: Candidate) -> float:
    """Fill rate beta at (Q, SL); 1.0 when demand has no variability."""
    sigma_l = sigma_over_lead(inputs)
    if sigma_l <= 0:
        return 1.0
    return fill_rate_from_safety_stock(
        ss_units(inputs, cand.service_level), cand.order_quantity, sigma_l)


def utilities_raw(
    inputs: HatInputs, candidates: tuple[Candidate, ...],
) -> dict[str, tuple[float, ...]]:
    """Raw utilities per hat, aligned with `candidates`.

    Planner (spec sec 4): candidates below sl_target get a FINITE penalty strictly
    below every valid candidate, ordered by deficit:
        u = u_min_valid - (sl_target - SL) * range_valid,
        range_valid = max(u_max_valid - u_min_valid, 1.0).
    If NO candidate meets sl_target (injectable sl_target above the grid), the
    empty-valid-set convention u_min_valid=0.0, range_valid=1.0 keeps the
    deficit ordering and stays deterministic.
    """
    sl_target = inputs.config.sl_target
    planner_valid = [
        _u_planner_valid(inputs, c) for c in candidates if c.service_level >= sl_target
    ]
    if planner_valid:
        u_min_valid = min(planner_valid)
        range_valid = max(max(planner_valid) - u_min_valid, 1.0)
    else:
        u_min_valid, range_valid = 0.0, 1.0

    def planner(cand: Candidate) -> float:
        if cand.service_level >= sl_target:
            return _u_planner_valid(inputs, cand)
        return u_min_valid - (sl_target - cand.service_level) * range_valid

    return {
        HAT_COMPRADOR: tuple(_u_comprador(inputs, c) for c in candidates),
        HAT_PLANNER: tuple(planner(c) for c in candidates),
        HAT_CFO: tuple(_u_cfo(inputs, c) for c in candidates),
        HAT_COMERCIAL: tuple(_u_comercial(inputs, c) for c in candidates),
    }


# -- D2: min-max normalization ----------------------------------------------------


def normalize(values: tuple[float, ...]) -> tuple[float, ...]:
    """u_norm = (u - min) / (max - min) over the WHOLE candidate set; a flat
    hat (max == min) normalizes to 0.5 everywhere (D2 border)."""
    lo, hi = min(values), max(values)
    if hi == lo:
        return tuple(0.5 for _ in values)
    return tuple((v - lo) / (hi - lo) for v in values)


# -- Deterministic selection (spec sec 6) --------------------------------------------


def select_best_index(
    scores: tuple[float, ...],
    judge_costs: tuple[float, ...],
    candidates: tuple[Candidate, ...],
) -> int:
    """argmax(scores) with the shared tie-break: (1) lower judge C, (2) lower Q,
    (3) lower SL. Used by every ideal AND by the settlement -- same rule, so
    w_x=1 collapses exactly onto hat x's ideal."""
    best = 0
    for i in range(1, len(scores)):
        a, b = scores[i], scores[best]
        if a > b:
            best = i
        elif a == b:
            ka = (judge_costs[i], candidates[i].order_quantity, candidates[i].service_level)
            kb = (judge_costs[best], candidates[best].order_quantity, candidates[best].service_level)
            if ka < kb:
                best = i
    return best


# -- KPIs per hat at a candidate (frozen keys; council/job/tests rely on them) ---


def hat_kpis(inputs: HatInputs, hat_key: str, cand: Candidate) -> dict[str, float]:
    c_q = unit_cost_at(inputs, cand.order_quantity)
    ss = ss_units(inputs, cand.service_level)
    avg_inv_usd = c_q * (cand.order_quantity / 2.0 + ss)
    if hat_key == HAT_COMPRADOR:
        return {
            "effective_unit_cost": c_q + inputs.config.order_cost / cand.order_quantity,
            "unit_price": c_q,
            "orders_per_year": inputs.annual_demand / cand.order_quantity,
        }
    if hat_key == HAT_PLANNER:
        return {
            "policy_cost": -_u_planner_valid(inputs, cand),
            "service_level": cand.service_level,
            "safety_stock_units": ss,
        }
    if hat_key == HAT_CFO:
        return {
            "capital_charge_usd": inputs.config.wacc * avg_inv_usd,
            "avg_inventory_usd": avg_inv_usd,
            "dio_days": days_inventory_outstanding(avg_inv_usd, inputs.annual_demand * c_q),
        }
    if hat_key == HAT_COMERCIAL:
        return {
            "fill_rate": _u_comercial(inputs, cand),
            "expected_units_short_per_year": _expected_units_short_per_year(inputs, cand),
        }
    raise ValueError(f"unknown hat: {hat_key}")


_HEADLINE = {
    HAT_COMPRADOR: "effective_unit_cost",
    HAT_PLANNER: "policy_cost",
    HAT_CFO: "capital_charge_usd",
    HAT_COMERCIAL: "fill_rate",
}


def headline_kpi(hat_key: str) -> str:
    """The one KPI each hat's acta row is written in (its own units)."""
    return _HEADLINE[hat_key]


# -- One evaluation of the whole grid (shared by N4 and N5) -----------------------


@dataclass(frozen=True)
class GridEvaluation:
    """Everything both levels need, computed once per SKU."""

    candidates: tuple[Candidate, ...]
    judge_costs: tuple[float, ...]
    utilities_raw: dict[str, tuple[float, ...]]
    utilities_norm: dict[str, tuple[float, ...]]


def evaluate(inputs: HatInputs) -> GridEvaluation:
    cands = candidate_grid(inputs)
    raw = utilities_raw(inputs, cands)
    return GridEvaluation(
        candidates=cands,
        judge_costs=tuple(decision_cost(inputs, c) for c in cands),
        utilities_raw=raw,
        utilities_norm={k: normalize(v) for k, v in raw.items()},
    )
