# SPEC.md — Algorithmic Trading Core Specification

> Project: `ml_trade`  
> Layer: Algorithmic Trading Core  
> Status: Refined production-oriented specification  
> Primary target: solo-developer, resume-ready, MT5-compatible quant trading platform  
> Default language for implementation: Python  
> Default broker interface: MetaTrader 5  

---

## 0. Review Outcome

This specification refines the original Algo Trade SPEC into a stricter engineering contract.

The major corrections are:

1. Separate **strategy logic** from **platform infrastructure**.
2. Add explicit **time semantics** to prevent lookahead bias.
3. Define stable **data contracts** for candles, features, signals, decisions, orders, positions, and trades.
4. Add **acceptance criteria** so the project can be tested instead of merely described.
5. Make execution safer through **idempotency**, **broker reconciliation**, and **live-mode gates**.
6. Convert vague production-readiness goals into concrete **promotion gates**.
7. Clarify that the platform is not production-grade because it is complex; it is production-oriented only when it is reproducible, observable, and difficult to fool.

### 0.1 Resolved Assumptions

The following assumptions are locked for this SPEC:

| Topic | Decision |
|---|---|
| Broker | MetaTrader 5 first; other brokers later through adapter interface |
| Execution style | Low-frequency / medium-frequency candle-based trading, not HFT |
| Primary mode | Backtest → walk-forward → shadow → paper → micro-live |
| Initial storage | SQLite locally; migration to PostgreSQL allowed later |
| Market data granularity | OHLCV candles; lower timeframe data optional for intrabar resolution |
| Live safety default | Halt new trades first; do not auto-close all positions unless explicitly configured |
| Same-bar TP/SL default | Conservative: assume stop loss first |
| Risk default | Fixed fractional risk; Kelly is research-only unless capped |
| Model internals | Out of scope; model output contract is in scope |

---

## 1. Purpose

The purpose of the Algo Trade Core is to provide a reliable, testable, observable, and extensible trading system that can:

1. Load and validate market data.
2. Build leak-safe feature sets.
3. Accept rule-based or model-based strategy signals.
4. Convert signals into risk-controlled trade decisions.
5. Simulate trade lifecycle realistically in backtests.
6. Execute or simulate orders through a broker adapter.
7. Reconcile local state with broker state.
8. Log every decision, rejection, order, fill, trade, error, and risk event.
9. Produce reproducible reports for research, debugging, and resume use.

The system must behave as a **trading platform**, not a prediction script.

A valid run must be able to answer:

```text
What data was used?
Which config was used?
Which model and feature schema were used?
Why did the system enter, reject, hold, or exit?
How much risk was allocated?
Where were SL, TP, and timeout exits?
What did the broker or simulator actually fill?
What happened after realistic costs?
Can the result be reproduced?
```

---

## 2. Requirement Levels

This SPEC uses the following requirement levels:

| Term | Meaning |
|---|---|
| MUST | Required for correctness or safety |
| SHOULD | Strongly recommended; can be postponed with justification |
| MAY | Optional extension |
| MUST NOT | Forbidden behavior |

A feature is not considered complete unless its MUST requirements are implemented and tested.

---

## 3. Scope

### 3.1 In Scope

```text
market data loading
market data validation
symbol metadata registry
feature pipeline contract
strategy signal interface
signal filtering
risk management
position sizing
order construction
backtest execution
walk-forward orchestration
live/shadow/paper loop
MT5 broker adapter
trade lifecycle tracking
state reconciliation
kill switches
logging
SQLite persistence
performance reporting
robustness testing
configuration management
promotion gates
```

### 3.2 Out of Scope

```text
deep ML architecture internals
model training theory
online learning in live trading
sentiment model internals
macro data provider implementation
high-frequency trading
order book market making
exchange co-location
latency arbitrage
guaranteed profitability
fully autonomous self-optimization in live mode
```

---

## 4. High-Level Architecture

The core architecture should follow a **ports-and-adapters** style.

```text
                ┌────────────────────┐
                │     Config Layer    │
                └─────────┬──────────┘
                          │
┌──────────────┐   ┌───────▼────────┐   ┌──────────────────┐
│ Market Data  │──▶│ Data Validator │──▶│ Feature Pipeline │
└──────────────┘   └────────────────┘   └────────┬─────────┘
                                                   │
                                           ┌───────▼────────┐
                                           │ Strategy Layer │
                                           └───────┬────────┘
                                                   │ Signal
                                           ┌───────▼────────┐
                                           │ Signal Filters │
                                           └───────┬────────┘
                                                   │
                                           ┌───────▼────────┐
                                           │  Risk Engine   │
                                           └───────┬────────┘
                                                   │ Decision
                                           ┌───────▼────────┐
                                           │ Order Builder  │
                                           └───────┬────────┘
                                                   │
                        ┌──────────────────────────┴──────────────────────────┐
                        │                                                     │
                ┌───────▼────────┐                                    ┌───────▼────────┐
                │ Backtest Engine │                                    │ Broker Adapter │
                └───────┬────────┘                                    └───────┬────────┘
                        │                                                     │
                ┌───────▼────────┐                                    ┌───────▼────────┐
                │ Trade Lifecycle│                                    │ Reconciliation │
                └───────┬────────┘                                    └───────┬────────┘
                        │                                                     │
                        └──────────────────────┬──────────────────────────────┘
                                               │
                                      ┌────────▼─────────┐
                                      │ Logs + Storage   │
                                      └────────┬─────────┘
                                               │
                                      ┌────────▼─────────┐
                                      │ Reports/Dashboard│
                                      └──────────────────┘
```

### 4.1 Architectural Rule

The strategy layer MUST NOT directly send broker orders.

Allowed flow:

```text
Strategy → Signal → Filters → Risk Engine → Order Builder → Execution Adapter
```

Forbidden flow:

```text
Strategy → Broker API
```

---

## 5. Operating Modes

| Mode | Description | Order Submission | Storage | Intended Use |
|---|---|---:|---:|---|
| `research` | Explore data/features | No | Optional | notebooks, diagnostics |
| `backtest` | Single historical simulation | Simulated | Required | strategy test |
| `walk_forward` | Rolling train/validation/test simulation | Simulated | Required | OOS validation |
| `shadow` | Live data + live signals, no orders | No | Required | live behavior observation |
| `paper` | Live signals with demo/paper orders | Demo/paper only | Required | execution rehearsal |
| `micro_live` | Small real-money test | Real | Required | final staged validation |
| `live` | Full allowed live mode | Real | Required | production use |

### 5.1 Mode Safety Rules

```text
research/backtest/walk_forward MUST NOT call broker order_send.
shadow MUST NOT submit orders.
paper MUST require a demo account or explicit paper broker adapter.
micro_live and live MUST require explicit confirmation.
live MUST NOT be the default mode.
```

Example CLI:

```bash
python run.py --mode backtest --config configs/backtest.yaml
python run.py --mode shadow --config configs/shadow.yaml
python run.py --mode paper --config configs/paper.yaml
python run.py --mode micro_live --live-confirm I_UNDERSTAND_RISK
python run.py --mode live --live-confirm I_UNDERSTAND_RISK
```

### 5.2 Live Confirmation Requirements

Live-capable modes MUST check:

```text
account_id == expected_account_id
server == expected_server
mode in [micro_live, live]
live_confirm == required phrase
risk profile is not research/paper
kill switch is not active
configuration hash is stored
```

If any check fails, the system MUST halt before order construction.

---

## 6. Time and Candle Semantics

Time semantics are mandatory because most trading bugs are hidden lookahead bugs wearing a fake mustache.

### 6.1 Timestamp Convention

Every candle MUST define whether `timestamp` means:

```text
candle_open_time
or
candle_close_time
```

Default convention:

```text
timestamp = candle_open_time in broker timezone
```

Each loaded dataset MUST store:

```text
source_timezone
broker_timezone
utc_offset_policy
session calendar
DST handling policy
```

### 6.2 Signal Timing Rule

For candle-based strategies:

```text
Features for candle t may use data up to candle t close.
A signal produced after candle t close may execute no earlier than candle t+1 open.
```

Valid:

```text
features[t] → signal[t] → execution_price[t+1 open]
```

Invalid:

```text
features[t+1] → signal[t]
close[t+1] → signal[t]
high[t+1]/low[t+1] → signal[t]
```

### 6.3 Live Candle Completion Rule

In live mode, the system MUST NOT generate candle-close signals from an unfinished candle unless the strategy explicitly declares it supports intrabar signals.

Default:

```text
use_closed_candles_only = true
```

---

## 7. Data Requirements

### 7.1 Candle Schema

Minimum candle schema:

| Field | Type | Required | Description |
|---|---|---:|---|
| `timestamp` | datetime | Yes | candle open time unless otherwise documented |
| `open` | float | Yes | opening price |
| `high` | float | Yes | highest price |
| `low` | float | Yes | lowest price |
| `close` | float | Yes | closing price |
| `volume` | float | Yes | tick or real volume |
| `spread` | float | Strongly recommended | spread in points or price units, declared in metadata |
| `symbol` | string | Recommended | required for multi-symbol datasets |
| `timeframe` | string | Recommended | required for multi-timeframe datasets |

### 7.2 Supported Timeframes

The system SHOULD support:

```text
M1, M5, M15, M30, H1, H4, D1
```

The primary trading timeframe MUST be configurable.

Example:

```yaml
timeframes:
  primary: M15
  confirmations: [H1, H4]
```

### 7.3 Multi-Timeframe Alignment

When using higher timeframe features:

```text
H4 feature values MUST only become available after the H4 candle closes.
Lower timeframe rows MUST NOT see future higher timeframe closes.
```

Implementation requirement:

```text
Use as-of joins with closed-candle timestamps only.
```

---

## 8. Symbol Registry

The symbol universe MUST be registry-driven.

Each symbol MUST define enough metadata for sizing, validation, execution, and reporting.

### 8.1 Required Symbol Metadata

```yaml
XAUUSDm:
  canonical_symbol: XAUUSD
  broker_symbol: XAUUSDm
  asset_class: metal
  base_currency: XAU
  quote_currency: USD
  profit_currency: USD
  margin_currency: USD
  pip_size: 0.01
  tick_size: 0.01
  tick_value: 1.0
  contract_size: 100
  min_lot: 0.01
  max_lot: 50.0
  lot_step: 0.01
  stop_level_points: 0
  freeze_level_points: 0
  average_spread_points: 18
  max_spread_points: 60
  trading_sessions:
    timezone: broker
    sessions:
      - day: monday
        open: "01:00"
        close: "23:59"
  filling_modes: [IOC, FOK]
  allowed_order_types: [MARKET, LIMIT, STOP]
  magic: 7001
  enabled: true
```

### 8.2 Symbol Registry Rules

```text
Missing symbol metadata MUST be a hard failure.
Position sizing MUST use symbol metadata.
Execution validation MUST use broker metadata when available.
Backtest assumptions MUST be derived from the same registry where possible.
```

---

## 9. Data Validation

Before any training, backtest, walk-forward run, shadow run, paper run, or live run, market data MUST pass validation.

### 9.1 Required Checks

The validator MUST check:

```text
required columns exist
timestamps are parseable
timestamps are sorted ascending
timestamps are unique per symbol/timeframe
OHLC values are positive
high >= max(open, close, low)
low <= min(open, close, high)
volume >= 0
spread >= 0 when spread exists
missing bars <= configured threshold
timezone metadata exists
symbol exists in registry
no unexpected duplicate bars
no infinite values
NaN policy is applied and logged
```

### 9.2 Missing Bar Policy

The system MUST support configurable missing-bar behavior:

| Policy | Behavior |
|---|---|
| `fail` | Stop if missing bars exceed threshold |
| `warn` | Continue but log warning |
| `fill_flat` | Fill OHLC with previous close and volume 0 |
| `drop` | Drop affected rows after feature generation |

Default for backtest:

```text
missing_bar_policy = warn
```

Default for live:

```text
missing_bar_policy = fail_if_recent_data_missing
```

### 9.3 Data Quality Report

Every data load MUST produce a report:

```text
run_id
symbol
timeframe
rows
start_time
end_time
duplicate_timestamps
missing_bars
invalid_candles
NaN_count
infinite_count
median_spread
p95_spread
timezone
source
validation_status
```

### 9.4 Hard Failure Conditions

The system MUST stop immediately if:

```text
OHLC structure is invalid
required columns are missing
symbol metadata is missing
feature schema does not match model schema
model checkpoint and scaler hashes are mismatched
live data is stale
latest candle is older than allowed threshold
account ID does not match expected live account
broker position state cannot be reconciled safely
```

---

## 10. Feature and Indicator Layer

The Algo Trade Core MUST NOT depend on a specific ML model.

It SHOULD accept features from:

```text
raw OHLCV
technical indicators
volatility features
return features
trend features
regime features
model probabilities
macro/sentiment upstream modules
custom strategy features
```

### 10.1 Minimum Technical Features

The system SHOULD provide reusable implementations for:

| Feature | Purpose |
|---|---|
| simple return | directional movement |
| log return | additive return representation |
| ATR | volatility and stop sizing |
| RSI | momentum / mean reversion |
| EMA fast/slow | trend direction |
| MACD | momentum confirmation |
| ADX | trend strength |
| Bollinger Bands | volatility bands |
| rolling high/low | breakout logic |
| realized volatility | volatility regime |
| session features | time/session behavior |
| spread features | cost-aware filtering |

### 10.2 Feature Schema Lock

For model-based signals, feature schema MUST be locked.

Example:

```python
FEATURE_SCHEMA = [
    "rsi_m15",
    "atr_m15",
    "ema_fast_m15",
    "ema_slow_m15",
    "adx_m15",
    "spread_points",
    "regime_trending_prob",
]
```

Inference MUST reject features if:

```text
feature count differs
feature names differ
feature order differs
feature dtype is invalid
NaN exists after allowed warmup period
infinite values exist
scaler hash does not match model metadata
schema version does not match model metadata
```

### 10.3 Leakage Guard

Feature functions MUST declare:

```text
lookback_window
required_columns
uses_future_data = false
output_columns
warmup_bars
```

Feature generation MUST drop or mark warmup rows before signal generation.

### 10.4 Multi-Symbol Feature Rule

For multi-symbol datasets:

```text
rolling indicators MUST be computed per symbol, not across the full DataFrame.
```

Forbidden:

```python
df["atr"] = atr(df)  # accidentally mixes symbols
```

Required:

```python
df.groupby("symbol").apply(compute_features)
```

---

## 11. Strategy Interface

A strategy is a signal generator. It MUST NOT own risk management, execution, or broker state.

### 11.1 Strategy Contract

Each strategy MUST implement:

```python
class Strategy:
    name: str
    version: str
    required_features: list[str]

    def generate_signal(self, context: StrategyContext) -> Signal:
        ...
```

### 11.2 Strategy Context

```json
{
  "timestamp": "2026-05-04T10:15:00+07:00",
  "symbol": "XAUUSDm",
  "timeframe": "M15",
  "features": {},
  "recent_candles": [],
  "current_positions": [],
  "mode": "backtest",
  "config_hash": "..."
}
```

### 11.3 Strategy Rules

```text
Strategy MAY output BUY, SELL, HOLD, CLOSE_LONG, or CLOSE_SHORT.
Strategy MUST include reason codes or metadata.
Strategy MUST be deterministic for the same input unless randomness is explicitly seeded and logged.
Strategy MUST NOT call broker APIs.
Strategy MUST NOT read future candles.
```

---

## 12. Signal Specification

A signal is an intermediate trading intent, not an executable order.

### 12.1 Signal Object

```json
{
  "signal_id": "sig_20260504_XAUUSDm_M15_000001",
  "run_id": "run_20260504_001",
  "timestamp": "2026-05-04T10:15:00+07:00",
  "symbol": "XAUUSDm",
  "timeframe": "M15",
  "side": "BUY",
  "confidence": 0.68,
  "expected_return": 0.0021,
  "source": "ml_model",
  "strategy_name": "triple_barrier_lstm",
  "strategy_version": "0.5.0",
  "model_version": "model_20260504_a",
  "feature_schema_version": "features_v3",
  "metadata": {
    "buy_prob": 0.68,
    "sell_prob": 0.21,
    "hold_prob": 0.11,
    "uncertainty": 0.07,
    "regime": "TRENDING"
  }
}
```

### 12.2 Valid Signal Sides

```text
BUY
SELL
HOLD
CLOSE_LONG
CLOSE_SHORT
```

### 12.3 Signal Validation

The system MUST reject malformed signals if:

```text
side is invalid
symbol is unknown
confidence is outside [0, 1]
timestamp is missing
strategy name/version is missing
feature schema version is missing for model-based signals
source is unknown
```

---

## 13. Signal Filtering

A raw signal MUST pass filters before becoming an approved trade decision.

### 13.1 Required Filters

```text
confidence threshold
spread filter
risk/reward filter
volatility filter
session filter
max position filter
symbol exposure filter
correlation exposure filter
daily risk budget filter
weekly risk budget filter
kill switch filter
regime blacklist filter
news/event filter if enabled
stale data filter
conflicting position filter
```

### 13.2 Filter Output Contract

Each filter MUST return:

```json
{
  "filter_name": "spread_filter",
  "passed": false,
  "reason_code": "spread_too_high",
  "observed_value": 58,
  "threshold": 45,
  "severity": "reject"
}
```

### 13.3 Spread Filter

Reject trade if:

```text
current_spread_points > max_allowed_spread_points
```

Dynamic version:

```text
current_spread_points > median_spread_points * spread_multiplier
```

Example:

```python
if current_spread_points > median_spread_points * 2.5:
    reject("spread_too_high")
```

### 13.4 Risk/Reward Filter

Reject trade if:

```text
reward / risk < min_rr
```

Default:

```yaml
signal:
  min_rr: 1.5
```

### 13.5 Regime Filter

Example behavior:

```text
BLACK_SWAN → reject all new trades
HIGH_VOLATILITY → reduce size or require higher confidence
LOW_LIQUIDITY → reject market orders or require wider cost model
```

### 13.6 Multi-Timeframe Confirmation Filter

For trend-following strategies:

```text
BUY allowed only if higher timeframe trend is bullish and lower timeframe momentum is not strongly bearish.
SELL allowed only if higher timeframe trend is bearish and lower timeframe momentum is not strongly bullish.
```

The exact rule MUST be configurable per strategy.

---

## 14. Trade Decision Specification

A trade decision is the result of signal validation, filtering, and risk evaluation.

### 14.1 Decision Types

```text
ENTER_LONG
ENTER_SHORT
EXIT_LONG
EXIT_SHORT
REJECT
HOLD
HALT
```

### 14.2 Approved Decision Object

```json
{
  "decision_id": "dec_20260504_XAUUSDm_000001",
  "signal_id": "sig_20260504_XAUUSDm_M15_000001",
  "run_id": "run_20260504_001",
  "timestamp": "2026-05-04T10:15:00+07:00",
  "symbol": "XAUUSDm",
  "decision": "ENTER_LONG",
  "side": "BUY",
  "entry_type": "MARKET",
  "entry_price_estimate": 2310.50,
  "stop_loss": 2304.00,
  "take_profit": 2323.50,
  "risk_pct": 0.0025,
  "risk_amount": 25.00,
  "position_size_lots": 0.03,
  "rr": 2.0,
  "status": "APPROVED",
  "reasons": [
    "buy_prob_above_threshold",
    "mtf_confirmed",
    "spread_ok",
    "rr_ok",
    "risk_budget_ok"
  ],
  "config_hash": "..."
}
```

### 14.3 Rejected Decision Object

```json
{
  "decision_id": "dec_20260504_XAUUSDm_000002",
  "signal_id": "sig_20260504_XAUUSDm_M15_000002",
  "run_id": "run_20260504_001",
  "timestamp": "2026-05-04T10:30:00+07:00",
  "symbol": "XAUUSDm",
  "decision": "REJECT",
  "side": "BUY",
  "status": "REJECTED",
  "reasons": [
    "spread_too_high",
    "rr_below_minimum"
  ],
  "filter_results": []
}
```

### 14.4 Decision Logging Rule

Every valid raw signal MUST produce exactly one of:

```text
APPROVED decision
REJECTED decision
HOLD decision
HALT decision
```

Silent signal disappearance is forbidden.

---

## 15. Risk Management

Risk management is mandatory. No signal may bypass the risk layer.

### 15.1 Risk Constraints

The risk engine MUST enforce:

```text
maximum risk per trade
maximum daily realized loss
maximum daily total loss including open PnL if configured
maximum weekly loss
maximum account drawdown
maximum open positions
maximum symbol exposure
maximum correlated exposure
maximum lot size
minimum lot size
broker lot step
required stop loss
minimum stop distance
maximum stop distance if configured
margin sufficiency
session-level risk cap if configured
```

### 15.2 Risk Profiles

| Profile | Risk Per Trade | Daily Loss Limit | Weekly Loss Limit | Use |
|---|---:|---:|---:|---|
| `research` | 0% | 0% | 0% | no execution |
| `backtest` | configurable | configurable | configurable | simulation only |
| `paper` | virtual only | virtual only | virtual only | demo/paper |
| `micro_live` | 0.10–0.25% | 0.5–1.0% | 1.0–2.0% | first real-money test |
| `conservative` | 0.25–0.50% | 1.0–1.5% | 2.0–3.0% | stable mode |
| `aggressive` | up to 1.0% | 2.0–3.0% | 4.0–6.0% | only after proven edge |

Important distinction:

```text
paper risk is virtual risk, not real capital risk.
```

### 15.3 Position Sizing

Base formula:

```text
risk_amount = account_equity × risk_per_trade
position_size_lots = risk_amount / loss_per_lot_if_stop_hit
```

The sizing function MUST account for:

```text
entry price
stop loss price
contract size
tick size
tick value
pip size
lot step
min lot
max lot
symbol profit currency
account currency
FX conversion if profit currency differs from account currency
```

### 15.4 Lot Rounding Rule

After calculating raw size:

```text
rounded_lot = floor(raw_lot / lot_step) × lot_step
```

If `rounded_lot < min_lot`, behavior MUST be configurable:

| Policy | Behavior |
|---|---|
| `reject` | reject trade |
| `min_lot` | use minimum lot only if risk remains below cap |

Default:

```text
reject
```

### 15.5 Kelly Sizing

Kelly sizing MAY be used in research.

Live-capable modes MUST NOT use uncapped full Kelly.

Allowed live formula:

```text
final_risk = min(fractional_kelly_risk, fixed_risk_cap, volatility_target_risk)
```

Recommended cap:

```yaml
risk:
  fractional_kelly: 0.25
  max_risk_per_trade: 0.005
```

### 15.6 Stop Loss Requirement

Every new position MUST have a stop loss.

If broker order is filled but SL is missing:

```text
1. attempt immediate SL modification
2. if modification fails, close position if configured safe
3. otherwise halt new trades and require manual review
4. log emergency risk event
```

---

## 16. Order Specification

### 16.1 Supported Order Types

```text
MARKET
LIMIT
STOP
STOP_LOSS
TAKE_PROFIT
CLOSE
MODIFY
```

### 16.2 Order Request Object

```json
{
  "order_id": "ord_20260504_XAUUSDm_000001",
  "decision_id": "dec_20260504_XAUUSDm_000001",
  "client_order_id": "ml_trade_run001_000001",
  "timestamp": "2026-05-04T10:15:01+07:00",
  "symbol": "XAUUSDm",
  "side": "BUY",
  "order_type": "MARKET",
  "volume_lots": 0.03,
  "price": null,
  "stop_loss": 2304.00,
  "take_profit": 2323.50,
  "deviation_points": 20,
  "magic": 7001,
  "comment": "ml_trade_v5",
  "time_in_force": "GTC"
}
```

### 16.3 Idempotency Requirement

Before submitting an order, the execution layer MUST check whether the same `client_order_id` has already been sent or filled.

The system MUST NOT accidentally duplicate orders after retry, crash, or reconnect.

---

## 17. Execution Specification

### 17.1 Broker Adapter Interface

The execution layer SHOULD be hidden behind an adapter:

```python
class BrokerAdapter:
    def connect(self) -> None: ...
    def get_account_info(self) -> AccountInfo: ...
    def get_symbol_info(self, symbol: str) -> SymbolInfo: ...
    def get_latest_rates(self, symbol: str, timeframe: str, count: int): ...
    def send_order(self, order: OrderRequest) -> OrderResult: ...
    def modify_position(self, request: ModifyRequest) -> OrderResult: ...
    def close_position(self, position_id: str) -> OrderResult: ...
    def get_open_positions(self) -> list[BrokerPosition]: ...
```

### 17.2 Pre-Trade Execution Checks

Before sending an order, the system MUST check:

```text
broker connected
account ID matches expected account
server matches expected server
symbol is visible
symbol is tradable
market is open
spread is acceptable
lot size is within min/max/step
SL/TP satisfy broker stop level
SL/TP satisfy freeze level if modifying
margin is sufficient
risk limits are not breached
position state is reconciled
client_order_id is not already used
```

### 17.3 Post-Trade Checks

After sending an order, the system MUST verify:

```text
broker return code
actual fill price
actual fill volume
partial fill status if supported
position exists if order filled
SL/TP are attached
actual slippage
commission if available
local state update succeeded
risk budget update succeeded
```

### 17.4 Execution Failure Policy

Execution failures MUST be classified:

| Class | Example | Default Behavior |
|---|---|---|
| transient | temporary disconnect | retry with cap |
| validation | invalid volume | reject and log |
| risk | margin insufficient | reject and log risk event |
| critical | filled without SL | emergency handling + halt |
| unknown | unexpected exception | halt new trades |

---

## 18. Trade Lifecycle

The system MUST track trades as stateful objects.

### 18.1 Trade States

```text
SIGNAL_CREATED
SIGNAL_REJECTED
DECISION_APPROVED
DECISION_REJECTED
ORDER_CREATED
ORDER_SENT
ORDER_FILLED
ORDER_PARTIALLY_FILLED
ORDER_REJECTED
POSITION_OPEN
POSITION_MODIFIED
POSITION_PARTIALLY_CLOSED
POSITION_CLOSED_TP
POSITION_CLOSED_SL
POSITION_CLOSED_TIMEOUT
POSITION_CLOSED_SIGNAL
POSITION_CLOSED_RISK
POSITION_CLOSED_MANUAL
POSITION_CLOSED_UNKNOWN
ERROR
```

### 18.2 Entry Rules

A trade may open only if:

```text
signal is valid
filters pass
risk checks pass
no conflicting position exists unless hedging is enabled
execution mode allows orders
market is open
symbol is tradable
spread is acceptable
order request is valid
state is reconciled
```

### 18.3 Exit Rules

A trade may close by:

```text
stop loss hit
take profit hit
time stop reached
opposite signal
strategy close signal
risk engine forced exit
kill switch action
manual close
broker-side close
system error protection
```

### 18.4 Time Stop

The system MUST support maximum holding period by bars or wall-clock time.

Example:

```yaml
exit:
  time_stop_bars: 24
  time_stop_action: close
```

Allowed actions:

```text
close
mark_for_close
notify_only
```

Default for backtest:

```text
close
```

Default for live:

```text
mark_for_close unless auto_close_enabled = true
```

---

## 19. Backtesting Specification

Backtesting MUST simulate trade lifecycle, not just vectorized signal returns.

### 19.1 Required Behavior

The backtester MUST:

```text
process candles in chronological order
process each symbol independently but share portfolio-level risk state
avoid lookahead bias
generate signals using available data only
execute candle-close signals no earlier than next candle open
open positions based on approved decisions
track positions across multiple bars
check TP/SL using high/low prices
apply same-bar ambiguity policy
apply time stop
apply spread
apply commission
apply slippage
apply swap/overnight cost if configured
update cash/equity/open PnL
log every signal, decision, order, fill, rejection, trade, and risk event
```

### 19.2 No-Lookahead Rule

Valid sequence:

```text
At close of candle t:
  compute features using data <= t
  generate signal[t]
  approve/reject decision[t]

At candle t+1:
  execute approved entry at open[t+1] or configured simulated price
```

Forbidden:

```text
using close[t+1] to decide signal[t]
using high[t+1]/low[t+1] to decide entry at t
fitting scaler on full dataset before train/test split
selecting thresholds on test data
```

### 19.3 TP/SL Resolution

For long positions:

```text
SL hit if low <= stop_loss
TP hit if high >= take_profit
```

For short positions:

```text
SL hit if high >= stop_loss
TP hit if low <= take_profit
```

### 19.4 Same-Bar TP/SL Ambiguity

If both TP and SL are touched in the same candle, the backtester MUST use a deterministic policy.

Allowed policies:

| Policy | Behavior |
|---|---|
| `conservative` | assume SL first |
| `optimistic` | assume TP first |
| `intrabar` | use lower timeframe data |
| `randomized` | probabilistic path simulation with seed |

Default:

```text
conservative
```

### 19.5 Cost Model

Backtests MUST include:

```text
spread
commission
slippage
swap or overnight cost if applicable
currency conversion cost if applicable
```

### 19.6 Slippage Model

| Scenario | Slippage Assumption |
|---|---|
| `none` | 0, research only |
| `base` | 0.5 × spread |
| `bad` | 1.0 × spread |
| `stress` | 2.0 × spread |
| `news` | 3.0–5.0 × spread |

Default production-candidate report MUST include at least:

```text
base
bad
stress
```

### 19.7 Backtest Outputs

Each backtest MUST produce:

```text
run metadata
trade log
decision log
rejected signal summary
equity curve
drawdown curve
monthly returns
symbol-level performance
strategy-level performance
cost analysis
risk event summary
configuration hash
model hash if applicable
```

---

## 20. Walk-Forward Testing

Walk-forward testing is required before paper, micro-live, or live deployment.

### 20.1 Default Split

```text
Train: 12 months
Validation: 3 months
Test: 3 months
Step forward: 3 months
```

Example:

```text
Round 1:
Train:      2021-01 → 2021-12
Validation: 2022-01 → 2022-03
Test:       2022-04 → 2022-06

Round 2:
Train:      2021-04 → 2022-03
Validation: 2022-04 → 2022-06
Test:       2022-07 → 2022-09
```

### 20.2 Walk-Forward Rules

```text
Test set MUST NOT be used for tuning.
Thresholds MUST be selected on train/validation only.
Scaler MUST be fit on train only.
Feature selection MUST be fit on train only.
Each round MUST log data range, model version, scaler hash, config hash, and feature schema version.
Final test results MUST be immutable unless rerun with a new run_id.
```

### 20.3 Aggregated Evaluation

Walk-forward report MUST include:

```text
per-round metrics
aggregate metrics
worst round
best round
stability of performance
parameter drift
trade count per round
cost impact per round
drawdown per round
```

---

## 21. Performance Metrics

The system MUST NOT rely on win rate alone.

### 21.1 Required Metrics

```text
total return
annualized return if applicable
win rate
average win
average loss
profit factor
expectancy
Sharpe ratio
Sortino ratio
max drawdown
Calmar ratio
average R multiple
median R multiple
longest losing streak
number of trades
exposure time
average holding time
cost as percentage of gross profit
return by symbol
return by regime
return by session
monthly returns
trade frequency
average slippage
```

### 21.2 Metric Formulas

```text
Expectancy = (Win Rate × Average Win) - (Loss Rate × Average Loss)
Profit Factor = Gross Profit / Absolute Gross Loss
Drawdown = (Equity - Running Peak Equity) / Running Peak Equity
R Multiple = Net PnL / Initial Risk Amount
```

### 21.3 Metric Validity Rules

```text
Sharpe and Sortino MUST disclose return frequency.
Annualized metrics MUST disclose annualization factor.
Profit factor MUST handle zero gross loss explicitly.
Metrics MUST be computed after costs.
Open trades MUST be handled consistently at report end.
```

---

## 22. Robustness Testing

Before paper, micro-live, or live deployment, a strategy MUST pass robustness checks.

### 22.1 Required Tests

```text
parameter sensitivity test
transaction cost stress test
spread stress test
slippage stress test
Monte Carlo trade shuffle
remove best N trades test
double worst N losses test
multi-symbol consistency test
regime-based performance analysis
session-based performance analysis
walk-forward stability analysis
```

### 22.2 Parameter Sensitivity

Example grid:

```yaml
confidence_threshold: [0.50, 0.55, 0.60, 0.65, 0.70]
atr_multiplier: [1.5, 2.0, 2.5, 3.0]
tp_r: [1.5, 2.0, 2.5, 3.0]
```

Production candidate should not depend on one magical parameter value.

### 22.3 Monte Carlo Trade Shuffle

Output MUST include:

```text
median max drawdown
p95 max drawdown
p99 max drawdown
probability of ruin
worst simulated losing streak
ending equity distribution
```

### 22.4 Minimum Robustness Gate

A strategy SHOULD be rejected as production candidate if:

```text
edge disappears under base cost model
profit depends on top 1-3 trades
stress slippage flips expectancy deeply negative
performance is positive in only one narrow parameter setting
walk-forward result is dominated by one lucky period
trade count is too low to infer anything useful
```

---

## 23. Baseline Strategy Requirements

The platform MUST include baseline strategies for comparison.

Required baselines:

```text
buy and hold where applicable
random entry with same exit rules
moving average crossover
RSI mean reversion
ATR breakout
always-hold / no-trade baseline
```

A model-based strategy is not considered validated unless it beats relevant baselines after realistic costs and risk constraints.

---

## 24. Live State Reconciliation

The system MUST NOT rely only on internal memory.

Every live loop MUST:

```text
fetch broker open positions
filter by known magic numbers
compare broker state with local state
detect missing, duplicated, or mismatched positions
update local state if safe
halt if unsafe
log reconciliation result
```

### 24.1 Mismatch Examples

```text
local state says no position, broker has open position
local state says position open, broker has none
position volume differs
position SL/TP differs
unknown position exists with system magic number
broker reports partial fill unknown locally
```

### 24.2 Required Behavior

If mismatch cannot be safely resolved:

```text
halt new orders
log critical event
alert user
require manual review
```

---

## 25. Kill Switch

The system MUST include multiple kill switch triggers.

### 25.1 Required Triggers

```text
daily loss limit breached
weekly loss limit breached
max drawdown breached
consecutive loss limit breached
data stale
broker disconnected
feature validation failed
model/scaler mismatch
position state mismatch
spread extreme
abnormal slippage
margin level too low
unexpected exception in live loop
manual emergency stop file exists
```

### 25.2 Kill Switch Actions

Allowed actions:

```text
HALT_NEW_TRADES
CLOSE_ALL_SYSTEM_POSITIONS
REDUCE_POSITION_SIZE
MANUAL_REVIEW_REQUIRED
NOTIFY_ONLY
```

Default behavior:

```text
HALT_NEW_TRADES
```

For critical safety failures:

```text
HALT_NEW_TRADES + MANUAL_REVIEW_REQUIRED
```

For filled-without-stop-loss events:

```text
attempt SL repair → if fail, close or halt according to emergency policy
```

---

## 26. Logging

Logging is mandatory.

### 26.1 Log Types

```text
system.log
signals.jsonl
decisions.jsonl
orders.jsonl
fills.jsonl
positions.jsonl
trades.jsonl
risk_events.jsonl
reconciliation.jsonl
errors.jsonl
```

### 26.2 Required Common Fields

Every structured log record MUST include:

```text
timestamp
run_id
mode
symbol if applicable
strategy_name if applicable
strategy_version if applicable
model_version if applicable
config_hash
schema_version
event_type
severity
```

### 26.3 Decision Log Fields

Every decision log MUST include:

```text
decision_id
signal_id
timestamp
symbol
timeframe
raw_signal
final_decision
confidence
expected_return
spread_points
ATR
regime
risk_reward
position_size_lots
risk_pct
risk_amount
filters_passed
filters_failed
reason_codes
model_version
config_hash
feature_schema_version
```

### 26.4 Trade Log Fields

Every completed trade MUST include:

```text
trade_id
run_id
symbol
side
entry_time
entry_price
exit_time
exit_price
position_size_lots
stop_loss
take_profit
exit_reason
gross_pnl
net_pnl
commission
spread_cost
slippage
swap
R_multiple
holding_bars
holding_time
model_version
strategy_version
config_hash
```

---

## 27. Storage

The system SHOULD persist state in SQLite for local production-oriented use.

Migration to PostgreSQL MAY be added later.

### 27.1 Required Tables

```text
runs
signals
decisions
orders
fills
positions
trades
risk_events
system_events
reconciliation_events
model_versions
config_versions
symbol_registry_snapshots
```

### 27.2 Reproducibility Metadata

Each run MUST store:

```text
run_id
git_commit
config_hash
config_path
model_version
model_hash
scaler_version
scaler_hash
feature_schema_version
data_range
symbol_universe
execution_mode
started_at
ended_at
status
```

### 27.3 State Recovery

On startup in live-capable modes, the system MUST:

```text
load last known local positions
fetch broker positions
run reconciliation
refuse new orders until reconciliation passes
```

---

## 28. Monitoring

The monitoring layer MUST answer:

```text
Is the system online?
Is MT5 connected?
Is market data fresh?
What mode is running?
What positions are open?
How much risk is currently used?
What was the latest signal?
Why were recent signals rejected?
Is the kill switch active?
What model/config version is running?
What is today's realized and unrealized PnL?
Are there reconciliation warnings?
```

### 28.1 Recommended Dashboard Panels

```text
System Health
Broker Connection
Market Data Status
Open Positions
Risk Budget
Latest Signals
Rejected Signals
Orders/Fills
Model Version
Config Hash
Kill Switch Status
Daily Performance
Reconciliation Status
```

### 28.2 Alert Conditions

The system SHOULD alert on:

```text
kill switch activated
broker disconnected
data stale
position mismatch
filled order without SL/TP
daily loss threshold near breach
abnormal slippage
unexpected exception
```

---

## 29. Configuration

All trading behavior MUST be configurable, not hardcoded.

### 29.1 Example Config

```yaml
mode:
  name: backtest
  live_confirm_required: true

account:
  expected_account_id: 12345678
  expected_server: Demo-Server
  account_currency: USD

symbols:
  enabled: [XAUUSDm, EURUSDm, USTECm]
  registry_path: configs/symbols.yaml

timeframes:
  primary: M15
  confirmations: [H1, H4]

data:
  source: csv
  timezone: broker
  timestamp_semantics: candle_open_time
  missing_bar_policy: warn
  max_missing_bar_ratio: 0.001

features:
  schema_version: features_v3
  use_closed_candles_only: true

strategy:
  name: triple_barrier_lstm
  version: 0.5.0
  source: ml_model

signal:
  buy_threshold: 0.60
  sell_threshold: 0.60
  min_rr: 1.5

risk:
  profile: conservative
  risk_per_trade: 0.0025
  daily_loss_limit: 0.01
  weekly_loss_limit: 0.02
  max_open_positions: 2
  max_symbol_exposure: 0.005
  max_correlation: 0.7
  max_lot: 0.10
  min_lot_policy: reject

execution:
  broker: mt5
  order_type: MARKET
  max_spread_multiplier: 2.5
  deviation_points: 20
  retry_count: 2
  require_sl: true
  auto_close_if_sl_missing: false

backtest:
  initial_equity: 10000
  commission_per_lot: 0
  same_bar_policy: conservative
  slippage_model: base
  execute_on_next_open: true

exit:
  time_stop_bars: 24
  time_stop_action: close

logging:
  output_dir: logs
  structured: true
  level: INFO

storage:
  type: sqlite
  path: data/ml_trade.sqlite
```

### 29.2 Config Hash

Each run MUST compute and store a config hash.

The hash MUST include:

```text
strategy config
risk config
execution config
symbol universe
timeframe config
feature schema version
model/scaler identifiers if applicable
```

---

## 30. Testing Requirements

### 30.1 Unit Tests

MUST cover:

```text
data validation
symbol registry loading
feature schema validation
position sizing
lot rounding
risk limit checks
signal validation
filter outputs
order construction
same-bar TP/SL resolution
metric calculation
config hashing
```

### 30.2 Integration Tests

MUST cover:

```text
CSV data → features → signals → decisions → backtest report
strategy signal → risk engine → order request
live startup → broker positions → reconciliation
paper order submission through broker adapter mock
kill switch activation
```

### 30.3 Regression Tests

MUST include at least one fixed historical dataset and config where:

```text
trade count is deterministic
equity curve hash is deterministic
report metrics are deterministic within tolerance
```

### 30.4 Acceptance Criteria

The Algo Trade Core is considered minimally complete when:

```text
[ ] one baseline strategy runs end-to-end in backtest
[ ] one model-based strategy can plug into the same interface
[ ] no-lookahead execution is tested
[ ] TP/SL/time-stop lifecycle is tested
[ ] costs are included
[ ] risk limits can reject trades
[ ] every signal produces a decision log
[ ] every completed trade produces a trade log
[ ] run metadata is persisted
[ ] backtest report is reproducible
```

---

## 31. Promotion Gates

A strategy/system version may advance only through these gates.

### 31.1 Gate 1 — Research Candidate

```text
[ ] data validation passes
[ ] feature schema is stable
[ ] baseline comparison exists
[ ] basic backtest completes
[ ] result is reproducible
```

### 31.2 Gate 2 — Backtest Candidate

```text
[ ] stateful backtest implemented
[ ] realistic costs included
[ ] no-lookahead test passes
[ ] TP/SL/time-stop tested
[ ] decision and trade logs complete
[ ] risk engine rejects invalid trades
```

### 31.3 Gate 3 — Walk-Forward Candidate

```text
[ ] walk-forward completed
[ ] OOS results locked
[ ] parameter tuning excludes test sets
[ ] scaler/model leakage prevented
[ ] aggregate report generated
```

### 31.4 Gate 4 — Shadow Candidate

```text
[ ] live data ingestion works
[ ] shadow decisions logged
[ ] no order submission possible
[ ] stale data detection works
[ ] broker connection health monitored
```

### 31.5 Gate 5 — Paper Candidate

```text
[ ] paper/demo order submission works
[ ] post-trade verification works
[ ] reconciliation works
[ ] kill switch tested
[ ] emergency stop tested
[ ] paper logs match expected lifecycle
```

### 31.6 Gate 6 — Micro-Live Candidate

```text
[ ] explicit live confirmation required
[ ] account ID/server checks pass
[ ] max risk per trade <= 0.25%
[ ] daily loss limit <= 1.0%
[ ] auto halt on critical mismatch
[ ] manual review process documented
```

### 31.7 Gate 7 — Live Candidate

```text
[ ] micro-live results reviewed
[ ] drawdown within expected range
[ ] execution slippage acceptable
[ ] reconciliation stable
[ ] monitoring and alerts active
[ ] rollback plan documented
```

---

## 32. Resume-Ready Requirements

To be resume-ready, the project SHOULD include:

```text
architecture diagram
clean README
reproducible backtest report
walk-forward report
baseline comparison
ablation study
realistic transaction cost testing
robustness testing
paper/shadow trading logs
risk management documentation
deployment instructions
screenshots or dashboard demo
```

Recommended documents:

```text
README.md
ARCHITECTURE.md
SPEC.md
BACKTESTING.md
RISK.md
DEPLOYMENT.md
RESEARCH_REPORT.md
RUNBOOK.md
```

Resume claim SHOULD be framed as:

```text
Built a production-oriented algorithmic trading research and execution platform with stateful backtesting, risk controls, walk-forward validation, MT5 integration, decision logging, and reproducible performance reporting.
```

Avoid claiming:

```text
Built profitable AI trading bot
Guaranteed trading system
Institutional-grade HFT platform
```

---

## 33. Development Priority

### Priority 1 — Correctness

```text
data validation
feature schema lock
model/scaler hash check
no-lookahead backtest
stateful TP/SL/timeout simulation
config hash
regression test
```

### Priority 2 — Risk Safety

```text
fixed fractional risk
risk caps
daily loss limit
max position limit
correlation cap
required SL
kill switch
```

### Priority 3 — Observability

```text
decision logs
rejected signal logs
order/fill logs
trade logs
risk event logs
system health logs
reconciliation logs
```

### Priority 4 — Realism

```text
spread model
slippage model
commission/swap
session filters
same-bar policy
news-time stress
```

### Priority 5 — Research Quality

```text
walk-forward testing
baseline comparison
ablation study
robustness testing
paper/shadow comparison
```

### Priority 6 — Live Readiness

```text
MT5 adapter hardening
state reconciliation
idempotent orders
emergency stop
monitoring dashboard
runbook
```

---

## 34. Non-Goals

The Algo Trade Core does not need to solve:

```text
predicting exact next candle OHLC
guaranteeing profit
fully autonomous online learning in live mode
high-frequency trading latency optimization
exchange co-location
institutional order book execution
market making
latency arbitrage
```

Immediate goal:

```text
A robust solo-developer quant trading platform that is reproducible, risk-controlled, observable, and honest about uncertainty.
```

---

## 35. Design Principles

The system should optimize for:

```text
reliability over complexity
reproducibility over beautiful backtests
risk control over high win rate
debuggability over magical AI behavior
survivability over aggression
boring correctness over clever failure
```

Final principle:

```text
Do not make the system smarter until it is harder for it to lie to you.
```
