"""Histograms, KDE, discrete PMF — Vandeput (2020), Chapter 12."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import gaussian_kde


@dataclass(frozen=True)
class DiscretePMF:
    """Integer demand values and probabilities."""

    values: np.ndarray
    probabilities: np.ndarray

    def cdf(self, x: float) -> float:
        return float(np.sum(self.probabilities[self.values <= x]))

    def ppf(self, q: float) -> float:
        if not 0 <= q <= 1:
            raise ValueError("q must be in [0,1]")
        cumulative = np.cumsum(self.probabilities)
        idx = int(np.searchsorted(cumulative, q, side="left"))
        idx = min(idx, len(self.values) - 1)
        return float(self.values[idx])


def histogram_pmf(
    data: np.ndarray,
    bins: int | None = None,
    value_range: tuple[float, float] | None = None,
) -> DiscretePMF:
    """Density histogram discretized to bin centers (Section 12.1)."""
    values_arr = np.asarray(data, dtype=float)
    n = len(values_arr)
    if n == 0:
        raise ValueError("empty data")
    if bins is None:
        bins = max(int(n / 3), 5)
    if value_range is None:
        value_range = (values_arr.min() * 0.8, values_arr.max() * 1.2)
    counts, edges = np.histogram(values_arr, bins=bins, range=value_range, density=True)
    centers = (edges[:-1] + edges[1:]) / 2
    widths = np.diff(edges)
    probs = counts * widths
    probs = probs / probs.sum() if probs.sum() > 0 else probs
    return DiscretePMF(values=centers.astype(int), probabilities=probs)


def scott_bandwidth(data: np.ndarray, factor: float = 0.9) -> float:
    """Scott rule with optional 90% factor (Section 12.2.3, eq. 12.1)."""
    n = len(data)
    sigma = float(np.std(data, ddof=1)) if n > 1 else 1.0
    return factor * sigma * n ** (-1 / 5)


def kde_pmf(
    data: np.ndarray,
    bandwidth: float | None = None,
    lower_bound: float | None = None,
    upper_bound: float | None = None,
    step: int = 1,
) -> DiscretePMF:
    """
    Gaussian KDE discretized to integer PMF (Sections 12.2–12.3).
    """
    values_arr = np.asarray(data, dtype=float)
    if len(values_arr) == 0:
        raise ValueError("empty data")
    bw = bandwidth or scott_bandwidth(values_arr)
    kde = gaussian_kde(values_arr, bw_method=bw / np.std(values_arr, ddof=1))

    if lower_bound is None:
        lower_bound = values_arr.min() - 3 * bw * values_arr.std()
    if upper_bound is None:
        upper_bound = values_arr.max() + 3 * bw * values_arr.std()

    grid = np.arange(int(max(0, lower_bound)), int(upper_bound) + 1, step, dtype=float)
    density = kde(grid)
    density = np.maximum(density, 0)
    density = density / density.sum() if density.sum() > 0 else density
    return DiscretePMF(values=grid.astype(int), probabilities=density)


def rmse_percent(actual: np.ndarray, fitted: np.ndarray) -> float:
    """RMSE as percentage of mean fitted (Section 9.4.2)."""
    if len(actual) != len(fitted):
        raise ValueError("length mismatch")
    rmse = np.sqrt(np.mean((actual - fitted) ** 2))
    mean_fitted = np.mean(fitted)
    return float(rmse / mean_fitted * 100) if mean_fitted > 0 else 0.0
