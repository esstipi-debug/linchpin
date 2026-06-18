"""Tests for gamma demand — Vandeput (2020), Chapter 9."""

import numpy as np
import pytest
from scipy.stats import gamma

from src.distributions import (
    DemandDistribution,
    fit_gamma,
    gamma_loss,
    gamma_skewness,
    safety_stock_gamma,
    select_distribution,
)


def test_gamma_skewness_formula():
    assert gamma_skewness(100, 50) == pytest.approx(1.0)


def test_fit_gamma_shape_scale():
    params = fit_gamma(mean=500, std=111.8, minimum=0)
    assert params.shape == pytest.approx(20.0, rel=0.01)
    assert params.scale == pytest.approx(25.0, rel=0.01)


def test_gamma_safety_stock_section_9_5():
    """High-CV demand: gamma Ss >> normal Ss (~785 vs ~658 at 95%)."""
    mu_x, sigma_x = 500.0, 400.0
    _, ss = safety_stock_gamma(mu_x, sigma_x, cycle_service_level=0.95)
    assert ss == pytest.approx(785, abs=30)
    ss_normal = 1.645 * sigma_x
    assert ss > ss_normal


def test_gamma_loss_non_negative():
    lost = gamma_loss(400, 500, 111.8)
    assert lost >= 0


def test_select_distribution_skewed_data():
    rng = np.random.default_rng(0)
    data = rng.gamma(shape=2, scale=50, size=200)
    fit = select_distribution(data)
    assert fit.recommended in (DemandDistribution.GAMMA, DemandDistribution.NORMAL)
    assert fit.gamma_params is not None


def test_gamma_ppf_matches_scipy():
    params = fit_gamma(500, 111.8)
    q = gamma.ppf(0.95, params.shape, loc=params.loc, scale=params.scale)
    _, ss = safety_stock_gamma(500, 111.8, 0.95)
    assert q - 500 == pytest.approx(ss, abs=1.0)
