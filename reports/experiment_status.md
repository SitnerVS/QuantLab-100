# QuantLab 100 — experiment status

Updated (UTC): 2026-11-19T20:16:30.037932+00:00
Experiment: quantlab-100-paper-72h-v1 — RUNNING
Window: 2026-11-19T13:31:09.436334+00:00 → 2026-11-22T13:31:09.436334+00:00
Elapsed: 6.76 h; remaining: 65.24 h

## Target

- Starting capital: 100.00 RUB
- Target equity: 10000.00 RUB
- Current venue-constrained equity: 100.0000 RUB
- Target progress: 1.0000%
- Required compound return to reach the target in 72 hours: 6.6050% per hour

## Venue-constrained paper portfolio

- Equity: 100.0000 RUB; total return: +0.00000%
- Active capital: 75.00 RUB; idle capital: 25.00 RUB
- Capital blocked by venue minimum lots: 50.00 RUB
- Lowest configured crypto minimum-order capital: 120.64 RUB; budget shortfall: 20.64 RUB
- Fills this run: 0; open positions: 0; closed trades: 0
- Cumulative rejected minimum-size orders: 36; new rejections this run: 0

## Fractional shadow portfolio — NON-EXECUTABLE

This separate research view deliberately ignores venue minimum order sizes. Its fractional fills cannot be placed at the exchange and must not be interpreted as executable trading results.

- Equity: 99.6316 RUB; total return: -0.36843%
- Active return: -0.49125%; fills this run: 0; open positions: 2; closed trades: 4
- Fees paid: 0.00047821 USD; funding paid (net sign as recorded): -0.00000078 USD
- Liquidations: 0

## Historical out-of-sample research

The tables below are exploratory rankings of fixed strategy rules on chronological test folds. They are not forecasts and do not automatically activate a strategy.

### Spot / FX proxy

| Dataset | Strategy | Median OOS return | Positive folds | Folds |
|---|---|---:|---:|---:|
| forex_RUB=X_1d.csv | bb_signal | +1.9775% | 66.7% | 6 |
| forex_JPY=X_1d.csv | rsi_signal | +0.1257% | 50.0% | 6 |
| forex_GBPUSD=X_1d.csv | donchian_signal | +0.0000% | 16.7% | 6 |

### Crypto futures

| Dataset | Strategy | Median OOS return | Positive folds | Folds |
|---|---|---:|---:|---:|
| futures_PF_SOLUSD_1h.csv | rsi_signal | +0.4107% | 55.6% | 9 |
| futures_PF_XBTUSD_1h.csv | rsi_signal | +0.0159% | 55.6% | 9 |
| futures_PF_XBTUSD_1h.csv | donchian_signal | +0.0000% | 0.0% | 9 |

Minimum Holm-adjusted p-value across tested dataset/strategy combinations: 1.0000.
No tested strategy passes the 5% family-wise significance threshold.

---

Safety: paper mode only. Real order submission is disabled. No exchange credentials are used.
