# QuantLab 100 — experiment status

Updated (UTC): 2026-11-27T12:41:09.526387+00:00
Paper mode: CONTINUOUS_PAPER; 72h benchmark: COMPLETED
Window: 2026-11-19T13:31:09.436334+00:00 → 2026-11-22T13:31:09.436334+00:00
Elapsed: 191.17 h; remaining: 0.00 h

## Target

- Starting capital: 100.00 RUB
- Target equity: 10000.00 RUB
- Current venue-constrained equity: 100.4325 RUB
- Target progress: 1.0043%
- Required compound return to reach the target in 72 hours: 6.6050% per hour

## Venue-constrained paper portfolio

- Equity: 100.4325 RUB; total return: +0.43246%
- Active capital: 75.00 RUB; idle capital: 25.00 RUB
- Capital blocked by venue minimum lots: 50.00 RUB
- Lowest configured crypto minimum-order capital: 120.61 RUB; budget shortfall: 20.61 RUB
- Fills this run: 0; open positions: 0; closed trades: 0
- Cumulative rejected minimum-size orders: 594; new rejections this run: 60

## Fractional shadow portfolio — NON-EXECUTABLE

This separate research view deliberately ignores venue minimum order sizes. Its fractional fills cannot be placed at the exchange and must not be interpreted as executable trading results.

- Equity: 100.0441 RUB; total return: +0.04409%
- Active return: +0.05878%; fills this run: 0; open positions: 6; closed trades: 19
- Fees paid: 0.00198333 USD; funding paid (net sign as recorded): 0.00005510 USD
- Liquidations: 0

## Historical out-of-sample research

The tables below are exploratory rankings of fixed strategy rules on chronological test folds. They are not forecasts and do not automatically activate a strategy.

### Spot / FX proxy

| Dataset | Strategy | Median OOS return | Positive folds | Folds |
|---|---|---:|---:|---:|
| forex_RUB=X_1d.csv | bb_signal | +2.0800% | 66.7% | 6 |
| forex_RUB=X_1d.csv | ema_signal | +0.4538% | 50.0% | 6 |
| forex_GBPUSD=X_1d.csv | adx_signal | +0.2853% | 83.3% | 6 |

### Crypto futures

| Dataset | Strategy | Median OOS return | Positive folds | Folds |
|---|---|---:|---:|---:|
| futures_PF_SOLUSD_1h.csv | sma_signal | +0.0995% | 55.6% | 9 |
| futures_PF_XBTUSD_1h.csv | rsi_signal | +0.0425% | 55.6% | 9 |
| futures_PF_SOLUSD_1h.csv | rsi_signal | -0.1825% | 33.3% | 9 |

### Long/short futures — baseline

| Dataset | Strategy | Median OOS return | Positive folds | Median OOS drawdown |
|---|---|---:|---:|---:|
| futures_PF_SOLUSD_1h.csv | rsi_signal | -0.4229% | 22.2% | -2.75% |
| futures_PF_SOLUSD_1h.csv | sma_signal | -0.4927% | 44.4% | -5.17% |
| futures_PF_XBTUSD_1h.csv | sma_signal | -0.7416% | 44.4% | -4.12% |

### Long/short futures — risk_controlled

| Dataset | Strategy | Median OOS return | Positive folds | Median OOS drawdown |
|---|---|---:|---:|---:|
| futures_PF_XBTUSD_1h.csv | sma_signal | -0.4008% | 44.4% | -4.58% |
| futures_PF_SOLUSD_1h.csv | ema_signal | -0.5540% | 44.4% | -6.21% |
| futures_PF_SOLUSD_1h.csv | sma_signal | -0.5800% | 44.4% | -5.08% |

Minimum Holm-adjusted p-value across tested dataset/strategy combinations: 1.0000.
No tested strategy passes the 5% family-wise significance threshold.

---

Safety: paper mode only. Real order submission is disabled. No exchange credentials are used.
