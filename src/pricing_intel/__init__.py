"""Pricing intelligence titan -- the data spine (Linchpin 3.0 PR-10).

See ``models`` for the frozen dataclasses (``CompetitorOffer``, ``PricePoint``,
``MatchCandidate``, ``SiteConfig``) and ``ledger`` for the append-only,
SQLite-indexed, parquet/CSV-partitioned ``PriceLedger`` store built on top of
them. Acquisition (``acquire/``), extraction (``extract.py``), normalization
(``normalize.py``) and matching (``match/``) are later PRs (11+) -- nothing in
this package performs network I/O.
"""

from __future__ import annotations

from .ledger import (
    AppendResult,
    BatchRecord,
    DuplicateBatchError,
    LedgerRecord,
    PriceLedger,
    default_ledger,
)
from .models import (
    ACQUISITION_TIERS,
    AVAILABILITY_VALUES,
    BASE_CURRENCY,
    MATCH_METHODS,
    MATCH_STATUSES,
    OFFER_COLUMNS,
    TOS_DECISIONS,
    CompetitorOffer,
    MatchCandidate,
    OfferFrameValidationError,
    PricePoint,
    SiteConfig,
    dataframe_to_offers,
    offers_to_dataframe,
    validate_offer_frame,
)

__all__ = [
    "ACQUISITION_TIERS",
    "AVAILABILITY_VALUES",
    "BASE_CURRENCY",
    "MATCH_METHODS",
    "MATCH_STATUSES",
    "OFFER_COLUMNS",
    "TOS_DECISIONS",
    "AppendResult",
    "BatchRecord",
    "CompetitorOffer",
    "DuplicateBatchError",
    "LedgerRecord",
    "MatchCandidate",
    "OfferFrameValidationError",
    "PriceLedger",
    "PricePoint",
    "SiteConfig",
    "dataframe_to_offers",
    "default_ledger",
    "offers_to_dataframe",
    "validate_offer_frame",
]
