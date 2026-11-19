# QuantLab 100 — experiment status

Updated (UTC): 2026-11-19T13:55:58.413700+00:00
Experiment: quantlab-100-paper-72h-v1 — RUNNING
Window: 2026-11-19T13:31:09.436334+00:00 → 2026-11-22T13:31:09.436334+00:00
Elapsed: 0.41 h; remaining: 71.59 h

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
- Lowest configured crypto minimum-order capital: 122.71 RUB; budget shortfall: 22.71 RUB
- Fills this run: 0; open positions: 0; closed trades: 0
- Cumulative rejected minimum-size orders: 6; new rejections this run: 0

## Fractional shadow portfolio — NON-EXECUTABLE

This separate research view deliberately ignores venue minimum order sizes. Its fractional fills cannot be placed at the exchange and must not be interpreted as executable trading results.

- Equity: 99.9651 RUB; total return: -0.03494%
- Active return: -0.04659%; fills this run: 0; open positions: 6; closed trades: 0
- Fees paid: 0.00028895 USD; funding paid (net sign as recorded): 0.00000000 USD
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
| futures_PF_SOLUSD_1h.csv | bb_signal | +0.0231% | 55.6% | 9 |
| futures_PF_SOLUSD_1h.csv | ema_signal | +0.0000% | 11.1% | 9 |

Minimum Holm-adjusted p-value across tested dataset/strategy combinations: 1.0000.
No tested strategy passes the 5% family-wise significance threshold.

---

Safety: paper mode only. Real order submission is disabled. No exchange credentials are used.
