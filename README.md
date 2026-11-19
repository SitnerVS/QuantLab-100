# QuantLab 100

Research-first paper-trading lab for crypto and FX. **Paper mode only: no real orders are submitted.**

## Current capabilities
- Public historical market data: Kraken spot OHLCV through CCXT; Kraken Futures linear perpetual mark-price candles and historical relative funding rates; Yahoo Finance FX proxy data through yfinance.
- A data-quality gate reports missing datasets, schema issues, duplicate timestamps, missing/invalid OHLCV rows and data freshness before research runs.
- EMA, RSI, Bollinger and Donchian signal families for baseline research.
- Long/flat historical backtest with configurable fees, slippage and half-spread per fill, buy-and-hold benchmark, drawdown, annualized rough Sharpe, bar-level profit factor and win rate.
- Rolling chronological out-of-sample test windows for fixed causal signals, plus an aggregated ranking by median fold return and positive-fold share; these are evaluation folds, not parameter optimization.
- Isolated-margin futures backtests for Kraken linear PF perpetuals using observed historical relative funding rates and mark-price candles; results are written separately from spot/FX reports.
- Stateful virtual spot accounts for crypto and FX proxy datasets, plus persistent isolated-margin futures accounts: buys/sells, wallet, margin, quantity, equity, realized/unrealized PnL, funding and liquidations. Position sizing is capped by a configurable fraction of available cash.
- Paper execution is idempotent per completed candle and applies configurable fee, slippage and half-spread assumptions.
- GitHub Actions runs tests and research on pushes to main and hourly (UTC). The paper summary tracks a 72-hour baseline experiment window and its elapsed/remaining time; paper executions stop automatically at the end of the window.

## Important model boundaries
- The 100 RUB to 10,000 RUB in 72 hours objective is an extreme experimental target, not a forecast or promise.
- Four sleeves are budgeted at 25 RUB each. Enabled crypto spot and EUR/USD + GBP/USD proxy accounts convert their RUB allocation to USD using the latest completed Yahoo Finance USD/RUB (RUB=X) daily close. Portfolio snapshots show USD balances and an estimated RUB equivalent. JPY=X (USD/JPY) is research-only because its quote currency differs. The crypto futures sleeve is enabled in persistent paper accounts with 2x leverage, observed hourly funding, mark-price candles and a fixed maintenance-margin approximation. Venue-specific tiered margin and exact liquidation execution are not yet reproduced. The leveraged FX sleeve remains inactive.
- The FX symbols from Yahoo Finance are research proxies, not broker-grade executable bid/ask data. In particular, JPY=X is not a broker-specific USD/JPY feed. Yahoo FX volume is not a centralized traded-volume feed; missing values are normalized to zero and volume is not used by the current signals. Malformed OHLC rows are filtered before research.
- Paper fills use completed-bar close as a reference price plus conservative fee/spread/slippage adjustments. They are not order-book fills and do not model latency or partial fills.
- Current paper strategy is EMA trend only. The other signal families are research candidates, not automatically traded.
- Walk-forward folds evaluate fixed causal strategy rules and do not optimize parameters. Historical return uncertainty is estimated with circular block bootstrap; one-sided exploratory p-values are adjusted across all tested dataset/strategy combinations with Holm-Bonferroni. These statistics are diagnostics, not forecasts or proof of future profitability.
- Small balances may be below real exchange minimum order sizes. All balances and fills are virtual.

## Run locally
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m quantlab.cli run --config config/settings.yaml
python -m pytest -q
```

## GitHub Actions
The workflow runs tests and the research pipeline on pushes to main, pull requests (tests and research without committing), manual dispatch, and hourly UTC schedule. Research artifacts are retained for 14 days. Scheduled GitHub Actions can be delayed and are not a continuous trading server.

## Reports
- `reports/data_quality.csv` — expected data sources, validity and freshness.
- `reports/backtest_summary.csv` — historical strategy metrics and buy-and-hold comparison.
- `reports/walk_forward_summary.csv` — each chronological out-of-sample test window.
- `reports/walk_forward_ranking.csv` — aggregated spot/FX ranking by out-of-sample folds.
- `reports/futures_backtest_summary.csv` — isolated-margin futures metrics including funding and liquidations.
- `reports/futures_walk_forward_summary.csv` — futures out-of-sample folds.
- `reports/futures_walk_forward_ranking.csv` — aggregated futures fold ranking.
- `reports/statistical_validation.csv` — block-bootstrap return intervals and Holm-adjusted p-values across the tested strategy set.
- `reports/paper_portfolio_latest.csv` — virtual account balances and mark-to-market snapshots.
- `reports/paper_portfolio_summary.csv` — active/inactive capital and total virtual performance.
- `reports/paper_events_latest.csv` — latest virtual fills and position events.


## Roadmap
1. Validate the persistent futures paper engine's funding and liquidation results against Kraken venue specifications and add more granular mark-price execution modelling.
2. Extend uncertainty analysis to out-of-sample fold returns and test sensitivity to block length, bootstrap count and market regime.
3. Improve execution realism with next-open fills, venue-specific spread data, partial fills and exchange constraints.
4. Extend paper-state recovery tests and run the spot-only paper system long enough to evaluate stability across changing market regimes.
5. Evaluate additional signals and risk controls only through chronological out-of-sample folds; do not select strategies from in-sample rankings.
