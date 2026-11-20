# QuantLab 100

Research-first paper-trading lab for crypto and FX. **Paper mode only: no real orders are submitted.**

## Current capabilities
- Public historical market data: Kraken spot OHLCV through CCXT; Kraken Futures linear perpetual mark-price candles and historical relative funding rates; Yahoo Finance FX proxy data through yfinance. Transient public-data request failures are retried with bounded exponential backoff.
- A data-quality gate reports missing datasets, schema issues, duplicate timestamps, missing/invalid OHLCV rows and data freshness before research runs.
- EMA/SMA crossovers, RSI, Bollinger, Donchian breakout, MACD and 12-bar momentum signal families for baseline research.
- Long/flat historical backtest with configurable fees, slippage and half-spread per fill, buy-and-hold benchmark, drawdown, annualized rough Sharpe, bar-level profit factor and win rate.
- Rolling chronological out-of-sample test windows for fixed causal signals, plus an aggregated ranking by median fold return and positive-fold share; these are evaluation folds, not parameter optimization.
- Isolated-margin futures backtests for Kraken linear PF perpetuals using observed historical relative funding rates and mark-price candles; results are written separately from spot/FX reports.
- Two separate virtual execution views: venue-constrained accounts reject orders below exchange minimums; a clearly labeled fractional shadow portfolio ignores lot minimums to study signal behavior at tiny balances and is explicitly non-executable. Both track spot/futures positions, wallet, margin, quantity, equity, realized/unrealized PnL, fees, funding and liquidations.
- Paper execution is idempotent per completed candle, processes missed completed candles in chronological order from the persisted cursor, and applies configurable fee, slippage and half-spread assumptions.
- GitHub Actions runs tests and research on pushes to main and hourly (UTC). The paper engine is configured for continuous processing beyond the initial 72-hour benchmark window; scheduled Actions are still periodic jobs, not a continuously running execution daemon.

## Important model boundaries
- Rapid or guaranteed wealth is not a valid system requirement. The objective is positive risk-adjusted expectancy over a meaningful sample, with strict drawdown limits; hourly/daily profit is never guaranteed.
- Four sleeves are budgeted at 25 RUB each. Enabled crypto spot and EUR/USD + GBP/USD proxy accounts convert their RUB allocation to USD using the latest completed Yahoo Finance USD/RUB (RUB=X) daily close. Portfolio snapshots show USD balances and an estimated RUB equivalent. JPY=X (USD/JPY) is research-only because its quote currency differs. The crypto futures sleeve is enabled in persistent paper accounts with 2x leverage, observed hourly funding, mark-price candles, minimum contract quantities and EEA Level-I maintenance margin. The model uses a fixed 5% maintenance rate and a 2.5% full-liquidation-fee assumption; it does not reproduce partial liquidation, portfolio-wide margin or tick-level execution. Kraken EEA minimum lots are 0.0001 BTC, 0.001 ETH and 0.01 SOL. At the current 100 RUB budget and allocation, crypto spot/futures orders are below venue minimums and are rejected rather than simulated as fills. The summary separates the 50 RUB crypto allocation blocked by minimum lots, the 25 RUB theoretical FX-proxy allocation, and the 25 RUB inactive leveraged-FX allocation. The leveraged FX sleeve remains inactive.
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
- `reports/paper_portfolio_summary.csv` — venue-constrained active/inactive capital, rejected orders and total virtual equity.
- `reports/experiment_status.md` — human-readable experiment status, fractional-shadow warning and out-of-sample research shortlist.
- `reports/paper_fractional_portfolio_latest.csv` and `reports/paper_fractional_portfolio_summary.csv` — non-executable fractional shadow balances and performance.
- `reports/paper_events_latest.csv` — latest virtual fills and position events.


## Continuous trading architecture

Run the unattended hourly paper supervisor on an always-on Mac/Linux host with:

`python -m quantlab.cli continuous --config config/settings.yaml`

On macOS, an optional LaunchAgent installer is available: `bash scripts/install_macos_paper_agent.sh`. It creates a Python virtual environment, installs dependencies, starts the service at login and uses `caffeinate -i` to keep the Mac awake while it runs. Stop it with `launchctl bootout gui/$UID ~/Library/LaunchAgents/com.quantlab.paper.plist`. The service polls public data, checks freshness, runs paper-only processing, records `reports/continuous_heartbeat.json`, and retries failed cycles. It does not stream ticks or submit Demo/live orders.


The target architecture, operating stages, risk guardrails and release gates are documented in [docs/CONTINUOUS_TRADING_PLAN.md](docs/CONTINUOUS_TRADING_PLAN.md). The current repository remains paper-only: there is no live order adapter enabled.

## Roadmap
1. Validate the persistent futures paper engine's funding and liquidation results against Kraken venue specifications and add more granular mark-price execution modelling.
2. Extend uncertainty analysis to out-of-sample fold returns and test sensitivity to block length, bootstrap count and market regime.
3. Improve execution realism with next-open fills, venue-specific spread data, partial fills and exchange constraints.
4. Extend paper-state recovery tests and run the spot-only paper system long enough to evaluate stability across changing market regimes.
5. Evaluate additional signals and risk controls only through chronological out-of-sample folds; do not select strategies from in-sample rankings.
