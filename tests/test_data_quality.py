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


def test_duplicate_timestamps_and_invalid_ohlc_are_flagged(tmp_path):
    path = tmp_path / "bad.csv"
    times = list(pd.date_range("2026-01-01", periods=60, freq="h", tz="UTC"))
    times[-1] = times[-2]
    frame = pd.DataFrame({
        "timestamp": times,
        "open": [100.0] * 60,
        "high": [102.0] * 60,
        "low": [99.0] * 60,
        "close": [101.0] * 60,
        "volume": [10.0] * 60,
    })
    frame.loc[0, "high"] = 98.0
    frame.to_csv(path, index=False)
    result = analyze_dataset(
        path,
        "1h",
        "crypto",
        now=datetime(2026, 1, 3, tzinfo=timezone.utc),
    )
    assert result["status"] == "WARN"
    assert result["duplicate_timestamps"] == 1
    assert result["invalid_ohlc_rows"] == 1


def test_futures_dataset_requires_funding_rate(tmp_path):
    path = tmp_path / "futures.csv"
    times = pd.date_range("2026-01-01", periods=60, freq="h", tz="UTC")
    frame = pd.DataFrame({
        "timestamp": times,
        "open": [100.0] * 60,
        "high": [102.0] * 60,
        "low": [99.0] * 60,
        "close": [101.0] * 60,
        "volume": [10.0] * 60,
        "funding_rate": [0.0001] * 60,
        "min_order_size": [0.0001] * 60,
    })
    frame.to_csv(path, index=False)
    result = analyze_dataset(
        path,
        "1h",
        "futures",
        now=datetime(2026, 1, 4, tzinfo=timezone.utc),
    )
    assert result["status"] == "OK"
    assert result["missing_funding_rows"] == 0
