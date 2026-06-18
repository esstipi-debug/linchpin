"""Tests for batch multi-SKU analysis."""

from pathlib import Path

from src.batch import run_batch_analysis


def test_batch_all_skus(tmp_path: Path):
    out = tmp_path / "batch.csv"
    df = run_batch_analysis("data/sample_demand.csv", out)
    assert len(df) >= 2
    assert out.exists()
    assert "eoq_Q" in df.columns
    assert df["product_id"].nunique() == len(df)
