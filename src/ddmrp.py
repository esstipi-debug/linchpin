"""DDMRP buffer sizing and net-flow planning (capability M5).

Demand-Driven MRP v3 (Ptak & Smith). Strategically-positioned buffers with three
zones, driven by the net-flow equation rather than a forecast-only reorder point:

  Yellow = ADU x DLT                       (covers demand over the decoupled lead time)
  Red    = ADU x DLT x LTF x (1 + VF)      (base + variability safety)
  Green  = max(ADU x DLT x LTF, MOQ, ADU x order_cycle_days)   (order frequency/lot)

  TOR = Red ;  TOY = Red + Yellow ;  TOG = Red + Yellow + Green

Net Flow Position (NFP) = on-hand + on-order - qualified (sales-order) demand.
Reorder when NFP enters yellow or red; order back up to Top of Green.

LTF (lead-time factor, ~0.2-1.0; longer LT -> smaller) and VF (variability factor,
~0.2-1.0; spikier demand -> larger) are buffer-profile inputs. Pure arithmetic,
auditable for the QA gate. Reference: Ptak & Smith, *DDMRP v3* (2019); Microsoft
Dynamics 365 SCM DDMRP buffer reference (2025).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def average_daily_usage(usage: list[float]) -> float:
    """ADU — mean usage over the supplied window (past, forward, or blended)."""
    arr = np.asarray(usage, dtype=float)
    return float(arr.mean()) if arr.size else 0.0


@dataclass(frozen=True)
class BufferZones:
    adu: float
    dlt: float
    red: float
    yellow: float
    green: float

    @property
    def tor(self) -> float:
        """Top of red."""
        return self.red

    @property
    def toy(self) -> float:
        """Top of yellow."""
        return self.red + self.yellow

    @property
    def tog(self) -> float:
        """Top of green."""
        return self.red + self.yellow + self.green


def size_buffer(
    adu: float,
    dlt: float,
    *,
    ltf: float,
    vf: float,
    moq: float = 0.0,
    order_cycle_days: float = 0.0,
) -> BufferZones:
    """Compute the red/yellow/green zones for one buffered part."""
    yellow = adu * dlt
    red_base = adu * dlt * ltf
    red = red_base * (1.0 + vf)
    green = max(red_base, moq, adu * order_cycle_days)
    return BufferZones(adu=adu, dlt=dlt, red=red, yellow=yellow, green=green)


def net_flow_position(on_hand: float, on_order: float, qualified_demand: float) -> float:
    """NFP = on-hand + on-order - qualified demand (the DDMRP execution signal)."""
    return on_hand + on_order - qualified_demand


@dataclass(frozen=True)
class PlanningSignal:
    nfp: float
    zone: str               # "red" | "yellow" | "green" | "over_green"
    order_recommended: bool
    order_qty: float
    priority: float         # NFP / TOG — lower is more urgent


def planning_signal(
    zones: BufferZones,
    on_hand: float,
    on_order: float,
    qualified_demand: float,
) -> PlanningSignal:
    """Decide what to do now from the net-flow position against the buffer."""
    nfp = net_flow_position(on_hand, on_order, qualified_demand)
    tog = zones.tog
    priority = nfp / tog if tog > 0 else float("inf")

    if nfp <= zones.tor:
        zone = "red"
    elif nfp <= zones.toy:
        zone = "yellow"
    elif nfp <= tog:
        zone = "green"
    else:
        zone = "over_green"

    reorder = nfp <= zones.toy  # in yellow or red
    order_qty = max(0.0, tog - nfp) if reorder else 0.0
    return PlanningSignal(
        nfp=nfp, zone=zone, order_recommended=reorder, order_qty=order_qty, priority=priority
    )
