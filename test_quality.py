"""Focused regression tests for the trend filter. Run: python test_quality.py"""
import pandas as pd
from main import _trend


def test_trend():
    idx = pd.date_range("2026-01-01", periods=150, freq="h", tz="UTC")
    up = pd.DataFrame({"close": [100+i for i in range(150)]}, index=idx)
    down = pd.DataFrame({"close": [250-i for i in range(150)]}, index=idx)
    assert _trend(up) == "up"
    assert _trend(down) == "down"


if __name__ == "__main__":
    test_trend()
    print("PASS trend filter")
