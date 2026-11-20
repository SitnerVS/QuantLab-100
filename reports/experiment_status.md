# QuantLab 100 — experiment status

Updated (UTC): 2026-11-20T21:15:29.441346+00:00
Paper mode: CONTINUOUS_PAPER; 72h benchmark: RUNNING
Window: 2026-11-19T13:31:09.436334+00:00 → 2026-11-22T13:31:09.436334+00:00
Elapsed: 31.74 h; remaining: 40.26 h

## Target

- Starting capital: 100.00 RUB
- Target equity: 10000.00 RUB
- Current venue-constrained equity: 100.3169 RUB
- Target progress: 1.0032%
- Required compound return to reach the target in 72 hours: 6.6050% per hour

## Venue-constrained paper portfolio

- Equity: 100.3169 RUB; total return: +0.31687%
- Active capital: 75.00 RUB; idle capital: 25.00 RUB
- Capital blocked by venue minimum lots: 50.00 RUB
- Lowest configured crypto minimum-order capital: 111.09 RUB; budget shortfall: 11.09 RUB
- Fills this run: 0; open positions: 0; closed trades: 0
- Cumulative rejected minimum-size orders: 36; new rejections this run: 0

## Fractional shadow portfolio — NON-EXECUTABLE

This separate research view deliberately ignores venue minimum order sizes. Its fractional fills cannot be placed at the exchange and must not be interpreted as executable trading results.

- Equity: 99.8939 RUB; total return: -0.10607%
- Active return: -0.14142%; fills this run: 0; open positions: 0; closed trades: 6
- Fees paid: 0.00057215 USD; funding paid (net sign as recorded): -0.00000123 USD
- Liquidations: 0

## Historical out-of-sample research

The tables below are exploratory rankings of fixed strategy rules on chronological test folds. They are not forecasts and do not automatically activate a strategy.

### Spot / FX proxy

| Dataset | Strategy | Median OOS return | Positive folds | Folds |
|---|---|---:|---:|---:|
| forex_RUB=X_1d.csv | bb_signal | +1.9775% | 66.7% | 6 |
| forex_RUB=X_1d.csv | ema_signal | +0.8588% | 50.0% | 6 |
| forex_GBPUSD=X_1d.csv | adx_signal | +0.3833% | 100.0% | 6 |

### Crypto futures

| Dataset | Strategy | Median OOS return | Positive folds | Folds |
|---|---|---:|---:|---:|
| futures_PF_XBTUSD_1h.csv | rsi_signal | -0.0021% | 44.4% | 9 |
| futures_PF_SOLUSD_1h.csv | rsi_signal | -0.1825% | 33.3% | 9 |
| futures_PF_ETHUSD_1h.csv | rsi_signal | -0.3225% | 33.3% | 9 |

### Long/short futures — baseline

| Dataset | Strategy | Median OOS return | Positive folds | Median OOS drawdown |
|---|---|---:|---:|---:|
| futures_PF_ETHUSD_1h.csv | adx_signal | +0.4851% | 55.6% | -5.65% |
| futures_PF_SOLUSD_1h.csv | rsi_signal | +0.1897% | 55.6% | -2.44% |
| futures_PF_SOLUSD_1h.csv | sma_signal | -0.1836% | 44.4% | -4.80% |

### Long/short futures — risk_controlled

| Dataset | Strategy | Median OOS return | Positive folds | Median OOS drawdown |
|---|---|---:|---:|---:|
| futures_PF_ETHUSD_1h.csv | adx_signal | +0.4055% | 55.6% | -5.97% |
| futures_PF_SOLUSD_1h.csv | sma_signal | -0.2861% | 44.4% | -4.81% |
| futures_PF_SOLUSD_1h.csv | ema_signal | -1.0280% | 33.3% | -5.98% |

Minimum Holm-adjusted p-value across tested dataset/strategy combinations: 1.0000.
No tested strategy passes the 5% family-wise significance threshold.

---

Safety: paper mode only. Real order submission is disabled. No exchange credentials are used.
