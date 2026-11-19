# QuantLab 100

Research-first paper-trading lab for crypto and FX. **Paper mode only: no real orders are submitted.**

## Current capabilities
- Public historical market data: Kraken spot OHLCV through CCXT; Yahoo Finance FX proxy data through yfinance.
- A data-quality gate reports missing datasets, schema issues, duplicate timestamps, missing/invalid OHLCV rows and data freshness before research runs.
- EMA, RSI, Bollinger and Donchian signal families for baseline research.
- Long/flat historical backtest with configurable fees and slippage, buy-and-hold benchmark, drawdown, annualized rough Sharpe, bar-level profit factor and win rate.
- Rolling chronological out-of-sample test windows for fixed causal signals, plus an aggregated ranking by median fold return and positive-fold share; these are evaluation folds, not parameter optimization.
- Stateful cash-only virtual spot accounts for crypto and FX proxy datasets: buys, sells, cash, quantity, equity, realized and unrealized PnL.
- Paper execution is idempotent per completed candle and applies configurable fee, slippage and half-spread assumptions.
- GitHub Actions runs tests and research on pushes to main and hourly (UTC).

## Important model boundaries
- The 100 RUB to 10,000 RUB in 72 hours objective is an extreme experimental target, not a forecast or promise.
- Four sleeves are budgeted at 25 RUB each. Enabled crypto spot and EUR/USD + GBP/USD proxy accounts convert their RUB allocation to USD using the latest completed Yahoo Finance USD/RUB (RUB=X) daily close. Portfolio snapshots show USD balances and an estimated RUB equivalent. JPY=X (USD/JPY) is research-only because its quote currency differs. Futures and leveraged sleeves are explicitly disabled until a separately tested margin, funding, mark-price and liquidation model exists.
- The FX symbols from Yahoo Finance are research proxies, not broker-grade executable bid/ask data. In particular, JPY=X is not a broker-specific USD/JPY feed.
- Paper fills use completed-bar close as a reference price plus conservative fee/spread/slippage adjustments. They are not order-book fills and do not model latency or partial fills.
- Current paper strategy is EMA trend only. The other signal families are research candidates, not automatically traded.
- Walk-forward folds currently evaluate fixed strategy rules and do not optimize parameters. Bootstrap confidence intervals, multiple-testing correction and robust strategy-selection controls remain future work.
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

## Roadmap
1. Complete and validate the event-driven paper engine and its persistence (current implementation is initial spot-only version).
2. Improve data validation, source health checks and instrument metadata.
3. Add realistic futures funding, maintenance margin, mark-price and liquidation simulation before enabling leveraged sleeves.
4. Add chronological train/validation/test splits, walk-forward testing, benchmark comparisons, confidence intervals and multiple-testing controls.
5. Improve execution modelling with next-bar prices, spread sources, partial fills and venue constraints.
