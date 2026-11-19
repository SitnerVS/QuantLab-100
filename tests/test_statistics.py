import numpy as np
import pytest

from quantlab.backtest.statistics import block_bootstrap_validation, holm_adjust


def test_block_bootstrap_is_deterministic_and_returns_interval():
    returns = np.array([0.01, 0.02, -0.005, 0.01] * 30)
    first = block_bootstrap_validation(returns, block_size=4, n_bootstrap=200, seed=7)
    second = block_bootstrap_validation(returns, block_size=4, n_bootstrap=200, seed=7)
    assert first == second
    assert first["observations"] == 120
    assert first["bootstrap_ci_lower_pct"] <= first["historical_total_return_pct"]
    assert first["bootstrap_ci_upper_pct"] >= first["historical_total_return_pct"]


def test_positive_constant_returns_have_small_one_sided_bootstrap_p_value():
    result = block_bootstrap_validation([0.01] * 100, block_size=5, n_bootstrap=200)
    assert result["block_bootstrap_p_value"] < 0.01


def test_holm_adjustment_controls_familywise_error():
    adjusted = holm_adjust([0.01, 0.04, 0.03])
    assert adjusted == pytest.approx([0.03, 0.06, 0.06])


def test_holm_adjustment_preserves_missing_p_values():
    adjusted = holm_adjust([0.01, None, 0.04])
    assert adjusted[0] == pytest.approx(0.02)
    assert np.isnan(adjusted[1])
    assert adjusted[2] == pytest.approx(0.04)
