from datetime import datetime, timezone

import pandas as pd

from quantlab.data.quality import analyze_dataset


def test_missing_dataset_is_reported(tmp_path):
    result = analyze_dataset(
        tmp_path / "missing.csv",
        "1h",
        "crypto",
        now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert result["status"] == "MISSING"
    assert result["rows"] == 0


def test_valid_dataset_passes_schema_and_ohlc_checks(tmp_path):
    path = tmp_path / "valid.csv"
    times = pd.date_range("2026-01-01", periods=60, freq="h", tz="UTC")
    frame = pd.DataFrame({
        "timestamp": times,
        "open": [100.0] * 60,
        "high": [102.0] * 60,
        "low": [99.0] * 60,
        "close": [101.0] * 60,
        "volume": [10.0] * 60,
    })
    frame.to_csv(path, index=False)
    result = analyze_dataset(
        path,
        "1h",
        "crypto",
        now=datetime(2026, 1, 4, tzinfo=timezone.utc),
    )
    assert result["status"] == "OK"
    assert result["rows"] == 60
    assert result["duplicate_timestamps"] == 0
    assert result["invalid_ohlc_rows"] == 0


def test_future_dated_candles_are_flagged(tmp_path):
    path = tmp_path / "future.csv"
    times = pd.date_range("2026-01-01", periods=60, freq="h", tz="UTC")
    frame = pd.DataFrame({
        "timestamp": times,
        "open": [100.0] * 60,
        "high": [102.0] * 60,
        "low": [99.0] * 60,
        "close": [101.0] * 60,
        "volume": [10.0] * 60,
    })
    frame.to_csv(path, index=False)
    result = analyze_dataset(
        path,
        "1h",
        "crypto",
        now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert result["status"] == "FUTURE_DATA"


def test_fx_volume_can_be_missing_without_invalidating_ohlc(tmp_path):
    path = tmp_path / "fx.csv"
    times = pd.date_range("2026-01-01", periods=60, freq="D", tz="UTC")
    frame = pd.DataFrame({
        "date": times,
        "open": [1.1] * 60,
        "high": [1.2] * 60,
        "low": [1.0] * 60,
        "close": [1.15] * 60,
        "volume": [float("nan")] * 60,
    })
    frame.to_csv(path, index=False)
    result = analyze_dataset(
        path,
        "1d",
        "forex",
        now=datetime(2026, 3, 5, tzinfo=timezone.utc),
    )
    assert result["status"] == "OK"
    assert result["missing_volume_rows"] == 60
