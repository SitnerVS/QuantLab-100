# QuantLab 100 — experiment status

Updated (UTC): 2026-11-24T02:18:15.407738+00:00
Paper mode: CONTINUOUS_PAPER; 72h benchmark: COMPLETED
Window: 2026-11-19T13:31:09.436334+00:00 → 2026-11-22T13:31:09.436334+00:00
Elapsed: 108.78 h; remaining: 0.00 h

## Target

- Starting capital: 100.00 RUB
- Target equity: 10000.00 RUB
- Current venue-constrained equity: 99.5016 RUB
- Target progress: 0.9950%
- Required compound return to reach the target in 72 hours: 6.6050% per hour

## Venue-constrained paper portfolio

- Equity: 99.5016 RUB; total return: -0.49838%
- Active capital: 75.00 RUB; idle capital: 25.00 RUB
- Capital blocked by venue minimum lots: 50.00 RUB
- Lowest configured crypto minimum-order capital: 116.92 RUB; budget shortfall: 16.92 RUB
- Fills this run: 0; open positions: 0; closed trades: 0
- Cumulative rejected minimum-size orders: 360; new rejections this run: 72

## Fractional shadow portfolio — NON-EXECUTABLE

This separate research view deliberately ignores venue minimum order sizes. Its fractional fills cannot be placed at the exchange and must not be interpreted as executable trading results.

- Equity: 98.8876 RUB; total return: -1.11236%
- Active return: -1.48314%; fills this run: 0; open positions: 6; closed trades: 13
- Fees paid: 0.00141370 USD; funding paid (net sign as recorded): 0.00001852 USD
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
| futures_PF_SOLUSD_1h.csv | rsi_signal | -0.0456% | 44.4% | 9 |
| futures_PF_XBTUSD_1h.csv | sma_signal | -0.1840% | 44.4% | 9 |

### Long/short futures — baseline

| Dataset | Strategy | Median OOS return | Positive folds | Median OOS drawdown |
|---|---|---:|---:|---:|
| futures_PF_SOLUSD_1h.csv | sma_signal | +0.9384% | 55.6% | -4.88% |
| futures_PF_ETHUSD_1h.csv | ema_signal | +0.4470% | 55.6% | -5.00% |
| futures_PF_SOLUSD_1h.csv | rsi_signal | -0.0302% | 44.4% | -3.12% |

### Long/short futures — risk_controlled

| Dataset | Strategy | Median OOS return | Positive folds | Median OOS drawdown |
|---|---|---:|---:|---:|
| futures_PF_SOLUSD_1h.csv | sma_signal | +0.7806% | 66.7% | -4.94% |
| futures_PF_ETHUSD_1h.csv | ema_signal | -0.2579% | 44.4% | -5.00% |
| futures_PF_SOLUSD_1h.csv | rsi_signal | -0.8475% | 33.3% | -2.10% |

Minimum Holm-adjusted p-value across tested dataset/strategy combinations: 1.0000.
No tested strategy passes the 5% family-wise significance threshold.

---

Safety: paper mode only. Real order submission is disabled. No exchange credentials are used.
