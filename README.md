# QuantLab 100

Research-first paper-trading lab for crypto and FX. **Paper mode only: no real orders are submitted.**

## Scope of this starter
- Public historical market data: Binance spot OHLCV through CCXT; Yahoo Finance FX proxy data through yfinance.
- Four signal families: EMA trend, RSI oversold, Bollinger reversion, Donchian breakout.
- Long/flat backtest with next-bar signal execution, configurable fees and slippage.
- Hourly GitHub Actions run, reports and paper-signal snapshots.
- No API keys, exchange credentials, or real-order execution code.

## Important limitations
- The 100 RUB to 10,000 RUB in 72 hours objective is a high-risk experimental target, not a forecast or promise.
- Four virtual sleeves start at 25 RUB each. This is a simulation; actual exchange minimum order sizes may make 100 RUB untradeable.
- Yahoo Finance FX symbols are research proxies, not broker-grade executable bid/ask ticks.
- The initial futures/leveraged sleeves are **not yet implemented as realistic margin simulations**. Funding, rollover, maintenance margin, liquidation and mark prices must be added and validated before futures results are meaningful.
- The initial backtester is a research baseline, not a production-grade execution simulator. It does not yet implement full walk-forward validation or multiple-testing corrections.
- Backtests do not guarantee future results.

## Local setup (Mac)
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m quantlab.cli run --config config/settings.yaml
pytest -q
```

## GitHub setup
1. Create a public repository named `QuantLab-100`.
2. Upload this project to the `main` branch.
3. Open **Settings → Actions → General** and allow read/write workflow permissions.
4. Open **Actions → QuantLab scheduled research → Run workflow** for a manual run.
5. The workflow is scheduled hourly (UTC). GitHub scheduled workflows can be delayed during high load; do not treat them as a continuous trading server.

## Commands
```bash
python -m quantlab.cli download --config config/settings.yaml
python -m quantlab.cli backtest --config config/settings.yaml
python -m quantlab.cli paper --config config/settings.yaml
python -m quantlab.cli run --config config/settings.yaml
```

## Roadmap before a 72-hour experiment
1. Implement stateful virtual positions, entry/exit fills, equity and realized/unrealized PnL.
2. Add separate fee, spread, slippage and financing models per venue/instrument.
3. Implement futures funding, mark price, maintenance margin and liquidation; otherwise exclude futures from performance claims.
4. Add strict chronological train/validation/test splits and walk-forward testing.
5. Add confidence intervals, bootstrap, multiple-testing controls and a benchmark.
6. Validate data freshness, missing bars, duplicate timestamps and source outages.
