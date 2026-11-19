import math

import numpy as np
import pandas as pd


def block_bootstrap_validation(
    returns,
    block_size,
    n_bootstrap=500,
    confidence=0.95,
    seed=42,
):
    """Circular moving-block bootstrap for historical return uncertainty.

    The CI describes resampled historical path outcomes; it is not a forecast.
    The one-sided p-value tests whether the mean period return exceeds zero
    under a centered moving-block bootstrap null.
    """
    values = np.asarray(pd.Series(returns).dropna(), dtype=float)
    values = values[np.isfinite(values)]
    if len(values) < 2:
        return {
            "observations": int(len(values)),
            "mean_period_return_pct": None,
            "historical_total_return_pct": None,
            "bootstrap_ci_lower_pct": None,
            "bootstrap_ci_upper_pct": None,
            "block_bootstrap_p_value": None,
        }
    if block_size < 1 or n_bootstrap < 100:
        raise ValueError("block_size must be >= 1 and n_bootstrap >= 100")
    if np.any(values < -1):
        raise ValueError("period returns cannot be below -100%")

    n = len(values)
    block_size = min(int(block_size), n)
    blocks_needed = int(math.ceil(n / block_size))
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n, size=(n_bootstrap, blocks_needed))
    offsets = np.arange(block_size)
    indices = (starts[:, :, None] + offsets[None, None, :]) % n
    indices = indices.reshape(n_bootstrap, -1)[:, :n]
    samples = values[indices]

    bootstrap_total = np.prod(1.0 + samples, axis=1) - 1.0
    alpha = (1.0 - float(confidence)) / 2.0
    lower, upper = np.quantile(bootstrap_total, [alpha, 1.0 - alpha])

    observed_mean = float(values.mean())
    centered = values - observed_mean
    null_samples = centered[indices].mean(axis=1)
    p_value = (1.0 + float((null_samples >= observed_mean).sum())) / (n_bootstrap + 1.0)

    historical_total = float(np.prod(1.0 + values) - 1.0)
    return {
        "observations": int(n),
        "mean_period_return_pct": observed_mean * 100.0,
        "historical_total_return_pct": historical_total * 100.0,
        "bootstrap_ci_lower_pct": float(lower * 100.0),
        "bootstrap_ci_upper_pct": float(upper * 100.0),
        "block_bootstrap_p_value": float(p_value),
    }


def holm_adjust(p_values):
    """Holm-Bonferroni family-wise adjustment; preserves input order."""
    values = np.asarray(p_values, dtype=float)
    adjusted = np.full(values.shape, np.nan, dtype=float)
    valid_indices = np.where(np.isfinite(values))[0]
    if len(valid_indices) == 0:
        return adjusted.tolist()

    clipped = np.clip(values[valid_indices], 0.0, 1.0)
    order = np.argsort(clipped)
    m = len(clipped)
    running_max = 0.0
    for rank, sorted_index in enumerate(order):
        candidate = (m - rank) * clipped[sorted_index]
        running_max = max(running_max, candidate)
        adjusted[valid_indices[sorted_index]] = min(1.0, running_max)
    return adjusted.tolist()
