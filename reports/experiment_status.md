# QuantLab 100 — experiment status

Updated (UTC): 2026-11-25T05:30:14.298793+00:00
Paper mode: CONTINUOUS_PAPER; 72h benchmark: COMPLETED
Window: 2026-11-19T13:31:09.436334+00:00 → 2026-11-22T13:31:09.436334+00:00
Elapsed: 135.98 h; remaining: 0.00 h

## Target

- Starting capital: 100.00 RUB
- Target equity: 10000.00 RUB
- Current venue-constrained equity: 99.8864 RUB
- Target progress: 0.9989%
- Required compound return to reach the target in 72 hours: 6.6050% per hour

## Venue-constrained paper portfolio

- Equity: 99.8864 RUB; total return: -0.11358%
- Active capital: 75.00 RUB; idle capital: 25.00 RUB
- Capital blocked by venue minimum lots: 50.00 RUB
- Lowest configured crypto minimum-order capital: 112.57 RUB; budget shortfall: 12.57 RUB
- Fills this run: 0; open positions: 0; closed trades: 0
- Cumulative rejected minimum-size orders: 366; new rejections this run: 0

## Fractional shadow portfolio — NON-EXECUTABLE

This separate research view deliberately ignores venue minimum order sizes. Its fractional fills cannot be placed at the exchange and must not be interpreted as executable trading results.

- Equity: 99.0199 RUB; total return: -0.98014%
- Active return: -1.30685%; fills this run: 0; open positions: 0; closed trades: 19
- Fees paid: 0.00169878 USD; funding paid (net sign as recorded): 0.00001791 USD
- Liquidations: 0

## Historical out-of-sample research

The tables below are exploratory rankings of fixed strategy rules on chronological test folds. They are not forecasts and do not automatically activate a strategy.

### Spot / FX proxy

| Dataset | Strategy | Median OOS return | Positive folds | Folds |
|---|---|---:|---:|---:|
| forex_RUB=X_1d.csv | bb_signal | +2.0800% | 66.7% | 6 |
| forex_GBPUSD=X_1d.csv | adx_signal | +0.3266% | 100.0% | 6 |
| forex_JPY=X_1d.csv | rsi_signal | +0.1257% | 50.0% | 6 |

### Crypto futures

| Dataset | Strategy | Median OOS return | Positive folds | Folds |
|---|---|---:|---:|---:|
| futures_PF_XBTUSD_1h.csv | rsi_signal | -0.0021% | 44.4% | 9 |
| futures_PF_SOLUSD_1h.csv | rsi_signal | -0.0456% | 44.4% | 9 |
| futures_PF_ETHUSD_1h.csv | rsi_signal | -0.3225% | 33.3% | 9 |

### Long/short futures — baseline

| Dataset | Strategy | Median OOS return | Positive folds | Median OOS drawdown |
|---|---|---:|---:|---:|
| futures_PF_ETHUSD_1h.csv | ema_signal | +1.1355% | 55.6% | -5.28% |
| futures_PF_SOLUSD_1h.csv | sma_signal | +0.9402% | 55.6% | -4.79% |
| futures_PF_SOLUSD_1h.csv | rsi_signal | -0.2963% | 44.4% | -3.12% |

### Long/short futures — risk_controlled

| Dataset | Strategy | Median OOS return | Positive folds | Median OOS drawdown |
|---|---|---:|---:|---:|
| futures_PF_ETHUSD_1h.csv | ema_signal | +1.0396% | 55.6% | -5.37% |
| futures_PF_SOLUSD_1h.csv | sma_signal | +0.7823% | 55.6% | -4.95% |
| futures_PF_ETHUSD_1h.csv | rsi_signal | -0.3788% | 33.3% | -2.25% |

Minimum Holm-adjusted p-value across tested dataset/strategy combinations: 1.0000.
No tested strategy passes the 5% family-wise significance threshold.

---

Safety: paper mode only. Real order submission is disabled. No exchange credentials are used.
