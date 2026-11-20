# Continuous Trading Process — Engineering Plan

## Objective

Build an unattended, restart-safe trading process that can operate continuously and pursue positive risk-adjusted expectancy. Capital growth is a target, not a guaranteed outcome. The system must never increase risk merely to meet a daily or hourly profit target.

## Current verified baseline (2026-11-20)

- The repository is research-first and paper-only. No exchange orders are submitted.
- GitHub Actions runs the research pipeline on an hourly schedule. Scheduled Actions are not a continuously running trading daemon and may be delayed.
- The paper engine processes completed candles and persists a cursor/state between runs.
- The current venue-constrained paper portfolio has no fills because the 100 RUB starting balance is below the lowest configured minimum-order capital (about 118.58 RUB at the latest report).
- Fractional shadow results ignore venue minimums and are not executable.
- No tested strategy currently passes the 5% family-wise statistical significance threshold. ADX on ETH is a research candidate, not an approved strategy.

## Target architecture

### 1. Market-data service
- Prefer exchange WebSocket streams for live quotes/trades and a REST backfill path after disconnects.
- Persist raw events and normalized candles with exchange timestamps and receive timestamps.
- Detect stale feeds, sequence gaps, clock drift, malformed prices, duplicate events and incomplete candles.
- Never trade on an incomplete candle when a strategy is defined on candle closes.
- Reconcile the local market-data cursor with exchange history after every restart.

### 2. Strategy and signal service
- Run independent strategy instances per instrument and timeframe.
- Use only causal inputs available at decision time; record signal timestamp, source candle and strategy/config version.
- Apply market-regime and liquidity filters before a signal can become an order intent.
- Estimate fees, spread, slippage, funding and minimum order constraints before accepting an intent.
- Keep research candidates disabled until they pass out-of-sample and forward paper gates.

### 3. Portfolio and risk service
- Calculate quantity from equity, stop distance, volatility and a hard per-trade risk budget.
- Enforce limits for gross exposure, leverage, instrument concentration, daily loss, rolling drawdown and consecutive losses.
- Reserve margin and fees before order submission.
- Block entries when equity is below venue minimums or when market data, account state or risk inputs are stale.
- A kill switch must cancel open orders, prevent new entries and follow a separately tested position-reduction policy.
- No martingale, loss-chasing, or automatic leverage escalation.

### 4. Execution adapter
- Separate paper, exchange-demo and live adapters. They must have distinct configuration and credentials.
- Use client order IDs/idempotency keys to prevent duplicate orders after retries or restarts.
- Handle partial fills, rejects, rate limits, timeouts, cancel/replace and exchange maintenance.
- Reconcile orders, fills, positions, balances and margin against the exchange after every state transition.
- Live order submission remains disabled until a separate explicit approval and completed readiness checklist.

### 5. Durable state and recovery
- Persist strategy state, last processed market event, order intents, exchange order IDs, fills, positions, risk counters and last reconciliation time.
- Use atomic writes or a transactional database; never rely only on an in-memory process.
- On restart: pause new entries, backfill missing data, reconcile exchange state, rebuild risk, then resume only if all checks pass.
- Every event and state transition must be auditable.

### 6. Monitoring and alerts
- Monitor process heartbeat, data freshness, last successful reconciliation, order rejects, slippage, fees, funding, realized/unrealized PnL, equity and drawdown.
- Alert on stale data, missed heartbeat, unexpected position, repeated rejects, drawdown limit, state mismatch and kill-switch activation.
- Report actual fills separately from signals and simulated fills.

## Deployment stages and release gates

### Stage A — Reliable continuous paper
- Implement a persistent event loop and WebSocket-to-REST recovery.
- Keep all exchange actions read-only; simulate fills with conservative spread, slippage, fees, partial fills and minimum sizes.
- Run for at least 14 consecutive days without state loss, duplicate processing or unexplained gaps.
- Require zero unexplained reconciliation mismatches and passing automated restart/disconnect tests.

### Stage B — Strategy qualification
- Test candidates across multiple instruments, timeframes and market regimes.
- Use walk-forward evaluation, untouched holdout data, realistic costs and multiple-testing correction.
- Require positive net expectancy after costs, acceptable drawdown, sufficient trade count and stability across folds.
- A positive median fold alone is not sufficient. No strategy is promoted on in-sample return.

### Stage C — Exchange Demo
- Only after Stage A and B gates pass, enable a separate Demo adapter.
- Verify order lifecycle, idempotency, partial fills, restart recovery, balance/position reconciliation and kill switch.
- Run for at least 14 days or 100 completed round trips, whichever takes longer, without unresolved critical defects.
- Demo success is operational evidence, not proof of future profitability.

### Stage D — Live readiness review
- Requires separate explicit user approval.
- Confirm jurisdiction and exchange eligibility, account permissions, minimum capital, API permissions, key storage, risk limits, alert delivery and emergency shutdown.
- Start with the smallest venue-compliant size and conservative risk. Never use funds needed for living expenses or borrowed money.
- Increase size only after a predefined live sample and risk review. If a gate fails, revert to paper/demo.

## Initial risk policy for testing

These are conservative starting guardrails for simulation, not a promise of safety or a live-trading recommendation:
- Risk per trade: at most 0.25% of equity.
- Daily stop: 1% equity drawdown.
- Rolling peak-to-trough stop: 5% drawdown.
- Maximum leverage: 1x until a separate leverage validation is complete.
- No averaging down, martingale, or risk increase after losses.
- No new entries when data is stale, reconciliation is overdue, or minimum executable size exceeds available risk capital.

The risk limits must be configurable, tested against gap/slippage scenarios, and may be tightened. They must not be relaxed automatically to force trading.

## Success criteria

The process is considered operationally continuous only when it can run unattended, recover from disconnects/restarts, process each market event exactly once, reconcile all exchange state, enforce risk limits and alert on failures. Profitability is a separate empirical gate and must be demonstrated net of all costs over a meaningful forward sample.

**Non-goal:** guaranteeing a positive result every hour/day or promising rapid wealth. The system must be allowed to stay flat when no qualified opportunity exists.
