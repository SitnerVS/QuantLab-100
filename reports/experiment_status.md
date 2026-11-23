# QuantLab 100 — experiment status

Updated (UTC): 2026-11-23T03:46:16.332869+00:00
Paper mode: CONTINUOUS_PAPER; 72h benchmark: COMPLETED
Window: 2026-11-19T13:31:09.436334+00:00 → 2026-11-22T13:31:09.436334+00:00
Elapsed: 86.25 h; remaining: 0.00 h

## Target

- Starting capital: 100.00 RUB
- Target equity: 10000.00 RUB
- Current venue-constrained equity: 100.1048 RUB
- Target progress: 1.0010%
- Required compound return to reach the target in 72 hours: 6.6050% per hour

## Venue-constrained paper portfolio

- Equity: 100.1048 RUB; total return: +0.10483%
- Active capital: 75.00 RUB; idle capital: 25.00 RUB
- Capital blocked by venue minimum lots: 50.00 RUB
- Lowest configured crypto minimum-order capital: 115.32 RUB; budget shortfall: 15.32 RUB
- Fills this run: 0; open positions: 0; closed trades: 0
- Cumulative rejected minimum-size orders: 222; new rejections this run: 30

## Fractional shadow portfolio — NON-EXECUTABLE

This separate research view deliberately ignores venue minimum order sizes. Its fractional fills cannot be placed at the exchange and must not be interpreted as executable trading results.

- Equity: 99.3030 RUB; total return: -0.69696%
- Active return: -0.92928%; fills this run: 0; open positions: 6; closed trades: 13
- Fees paid: 0.00141370 USD; funding paid (net sign as recorded): 0.00002316 USD
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
| futures_PF_XBTUSD_1h.csv | rsi_signal | +0.0044% | 55.6% | 9 |
| futures_PF_SOLUSD_1h.csv | rsi_signal | -0.1825% | 33.3% | 9 |
| futures_PF_ETHUSD_1h.csv | rsi_signal | -0.3225% | 33.3% | 9 |

### Long/short futures — baseline

| Dataset | Strategy | Median OOS return | Positive folds | Median OOS drawdown |
|---|---|---:|---:|---:|
| futures_PF_ETHUSD_1h.csv | ema_signal | +0.9973% | 55.6% | -5.61% |
| futures_PF_SOLUSD_1h.csv | sma_signal | +0.7822% | 66.7% | -4.90% |
| futures_PF_SOLUSD_1h.csv | rsi_signal | -0.1485% | 44.4% | -2.07% |

### Long/short futures — risk_controlled

| Dataset | Strategy | Median OOS return | Positive folds | Median OOS drawdown |
|---|---|---:|---:|---:|
| futures_PF_SOLUSD_1h.csv | sma_signal | +0.5274% | 66.7% | -4.94% |
| futures_PF_ETHUSD_1h.csv | ema_signal | +0.0888% | 55.6% | -5.38% |
| futures_PF_ETHUSD_1h.csv | rsi_signal | -0.7362% | 11.1% | -2.28% |

Minimum Holm-adjusted p-value across tested dataset/strategy combinations: 1.0000.
No tested strategy passes the 5% family-wise significance threshold.

---

Safety: paper mode only. Real order submission is disabled. No exchange credentials are used.
