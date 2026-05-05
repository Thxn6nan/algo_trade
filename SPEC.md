# SPEC.md — Algorithmic Trading Core Specification

> Scope: Core algorithmic trading system specification for `ml_trade`.
> This document focuses on the **Algo Trade layer**: market data, feature preparation, signal generation, trade lifecycle, risk management, backtesting, execution, logging, and performance evaluation.
>
> Out of scope: deep ML architecture internals, model training theory, online learning design, sentiment model internals, and external macro API implementation details.

---

## 1. Purpose

The purpose of this module is to define a reliable, testable, and extensible algorithmic trading core that can:

1. Read and validate market data.
2. Generate trading signals from rule-based or model-based inputs.
3. Convert signals into risk-controlled trade decisions.
4. Backtest strategies using realistic trade lifecycle simulation.
5. Execute orders through MetaTrader 5 in live or paper mode.
6. Log every trade decision for debugging and performance analysis.
7. Enforce safety mechanisms such as position limits, drawdown limits, spread filters, and kill switches.

The system must behave as a **trading system**, not merely a prediction script.

A valid trading system must answer:

```text
What data was used?
Why did the system enter or reject a trade?
How much was risked?
Where are SL/TP/timeout exits?
What happened after execution?
How did the system perform after realistic costs?
```

---

## 2. High-Level Architecture

```text
Market Data
    ↓
Data Validation
    ↓
Feature / Indicator Pipeline
    ↓
Signal Generation
    ↓
Signal Filtering
    ↓
Risk Management
    ↓
Order Construction
    ↓
Execution / Backtest Engine
    ↓
Trade State Tracking
    ↓
Performance Report
    ↓
Decision & Trade Logs
```

The core system should support both:

```text
Backtest Mode:
Historical data → simulated orders → performance report

Live Mode:
MT5 live data → signals → risk checks → real/paper orders → monitoring
```

---

## 3. Operating Modes

The Algo Trade layer must support the following modes.

| Mode | Description | Order Execution |
|---|---|---|
| `research` | Data exploration and feature inspection | Disabled |
| `backtest` | Historical strategy simulation | Simulated |
| `walk_forward` | Multiple train/test historical windows | Simulated |
| `shadow` | Live signals, no order submission | Disabled |
| `paper` | Live signals with demo/paper execution | Demo / paper |
| `live` | Real account execution | Real broker |

### 3.1 Mode Safety Rules

- `research`, `backtest`, and `walk_forward` must never send live orders.
- `shadow` must generate and log trade decisions but must not send orders.
- `paper` must use demo account or paper execution only.
- `live` must require explicit confirmation and strict risk caps.

Example CLI behavior:

```bash
python run.py --mode backtest
python run.py --mode shadow
python run.py --mode paper
python run.py --mode live --live-confirm I_UNDERSTAND_RISK
```

---

## 4. Data Requirements

### 4.1 Required Market Data

The minimum market data format is OHLCV:

| Field | Description |
|---|---|
| `timestamp` | Candle timestamp |
| `open` | Opening price |
| `high` | Highest price in candle |
| `low` | Lowest price in candle |
| `close` | Closing price |
| `volume` | Tick volume or real volume |
| `spread` | Broker spread if available |

### 4.2 Supported Timeframes

The system should support multi-timeframe data, for example:

```text
M5
M15
M30
H1
H4
D1
```

The primary trading timeframe should be configurable.

Example:

```python
PRIMARY_TIMEFRAME = "M15"
CONFIRMATION_TIMEFRAMES = ["M15", "H4"]
```

### 4.3 Supported Symbols

The symbol universe must be registry-driven.

Each symbol must define:

```text
symbol name
asset class
pip size
pip value
contract size
min lot
max lot
lot step
average spread
trading session
broker suffix if any
magic number
```

Example:

```yaml
XAUUSDm:
  asset_class: metal
  magic: 7001
  pip_size: 0.01
  min_lot: 0.01
  lot_step: 0.01
```

---

## 5. Data Validation Specification

Before any backtest, live signal generation, or training run, OHLCV data must pass validation.

### 5.1 Required Checks

The system must reject or flag data if:

```text
- timestamps are duplicated
- timestamps are not sorted
- required OHLCV columns are missing
- high < open, close, or low
- low > open, close, or high
- close <= 0
- open <= 0
- high <= 0
- low <= 0
- volume < 0
- spread < 0
- missing bars exceed configured threshold
- timezone is unknown or inconsistent
```

### 5.2 Data Quality Report

Each data load should generate a summary:

```text
Symbol: XAUUSDm
Timeframe: M15
Rows: 250000
Start: 2021-01-01
End: 2026-05-01
Duplicate timestamps: 0
Missing bars: 132
Invalid candles: 0
Median spread: 18 points
P95 spread: 42 points
Timezone: Broker time / UTC offset documented
```

### 5.3 Hard Failure Conditions

The system must stop immediately if:

```text
- OHLC values are structurally invalid
- feature schema does not match model schema
- model checkpoint and scaler are mismatched
- live data is stale
- symbol metadata is missing
```

---

## 6. Feature / Indicator Layer

The Algo Trade layer should not depend on a specific model. It should accept any valid feature source.

Feature sources may include:

```text
- raw OHLCV values
- technical indicators
- volatility measures
- return features
- trend features
- regime features
- model probabilities
- macro/sentiment features from upstream modules
```

### 6.1 Minimum Technical Features

The system should support these common indicators:

| Feature | Purpose |
|---|---|
| Return | Measures price change |
| Log Return | Stable additive return representation |
| ATR | Volatility and stop sizing |
| RSI | Momentum / mean reversion |
| EMA fast / slow | Trend direction |
| MACD | Momentum confirmation |
| ADX | Trend strength |
| Bollinger Bands | Volatility band / mean reversion |
| Rolling High / Low | Breakout logic |

### 6.2 Feature Schema Lock

For any model-based signal, the feature order must be locked.

```python
FEATURE_SCHEMA = [
    "rsi_m15",
    "atr_m15",
    "ema_fast_m15",
    "ema_slow_m15",
    "adx_m15",
    "spread",
    "regime_trending_prob",
]
```

At inference time:

```python
assert list(features.columns) == FEATURE_SCHEMA
```

The system must reject inference if:

```text
- feature count differs
- feature names differ
- feature order differs
- NaN or infinite values exist
```

---

## 7. Signal Specification

A signal is an intermediate trading intent, not an executable order.

### 7.1 Signal Format

Each signal should contain:

```json
{
  "timestamp": "2026-05-04T10:15:00",
  "symbol": "XAUUSDm",
  "side": "BUY",
  "confidence": 0.68,
  "expected_return": 0.0021,
  "source": "ml_model",
  "timeframe": "M15",
  "metadata": {
    "buy_prob": 0.68,
    "sell_prob": 0.21,
    "uncertainty": 0.07,
    "regime": "TRENDING"
  }
}
```

### 7.2 Valid Signal Sides

```text
BUY
SELL
HOLD
CLOSE_LONG
CLOSE_SHORT
```

### 7.3 Rule-Based Example Signals

#### Moving Average Crossover

```text
If EMA fast > EMA slow → BUY
If EMA fast < EMA slow → SELL
Otherwise → HOLD
```

#### RSI Mean Reversion

```text
If RSI < 30 → BUY
If RSI > 70 → SELL
Otherwise → HOLD
```

#### Breakout

```text
If close > rolling_high_20 → BUY
If close < rolling_low_20 → SELL
Otherwise → HOLD
```

### 7.4 Model-Based Signal

For model output probabilities:

```text
If buy_prob > buy_threshold and buy_prob > sell_prob → BUY
If sell_prob > sell_threshold and sell_prob > buy_prob → SELL
Otherwise → HOLD
```

Example:

```python
if buy_prob > min_buy_threshold and buy_prob > sell_prob:
    side = "BUY"
elif sell_prob > min_sell_threshold and sell_prob > buy_prob:
    side = "SELL"
else:
    side = "HOLD"
```

---

## 8. Signal Filtering

A raw signal must pass filters before becoming a trade decision.

### 8.1 Required Filters

```text
- confidence threshold
- spread filter
- risk/reward filter
- volatility filter
- session filter
- max position filter
- correlation filter
- daily risk budget filter
- kill switch filter
- regime blacklist filter
- news/event filter if enabled
```

### 8.2 Spread Filter

Reject trade if:

```text
current_spread > max_allowed_spread
```

Recommended dynamic version:

```text
current_spread > median_spread * spread_multiplier
```

Example:

```python
if current_spread > median_spread * 2.5:
    reject("spread_too_high")
```

### 8.3 Risk/Reward Filter

Reject trade if expected R:R is below minimum.

```text
reward / risk < MIN_RR
```

Default:

```python
MIN_RR = 1.5
```

### 8.4 Regime Filter

The system may reject trades during dangerous regimes.

Example:

```text
If regime == BLACK_SWAN → reject all new trades
If regime == HIGH_VOLATILITY → reduce size or require higher confidence
```

### 8.5 MTF Confirmation Filter

For trend-following signals:

```text
H4 trend must align with trade direction
M15 momentum must not strongly oppose trade direction
```

Example:

```text
BUY allowed only if:
- H4 EMA fast > H4 EMA slow
- H4 ADX above trend threshold
- M15 momentum not bearish
```

---

## 9. Trade Decision Specification

A trade decision is the result of passing a signal through filters and risk management.

### 9.1 Decision Types

```text
ENTER_LONG
ENTER_SHORT
EXIT_LONG
EXIT_SHORT
REJECT
HOLD
HALT
```

### 9.2 Decision Object

```json
{
  "timestamp": "2026-05-04T10:15:00",
  "symbol": "XAUUSDm",
  "decision": "ENTER_LONG",
  "side": "BUY",
  "entry_type": "MARKET",
  "entry_price_estimate": 2310.50,
  "stop_loss": 2304.00,
  "take_profit": 2323.50,
  "risk_pct": 0.25,
  "position_size": 0.03,
  "rr": 2.0,
  "status": "APPROVED",
  "reasons": [
    "buy_prob_above_threshold",
    "mtf_confirmed",
    "spread_ok",
    "rr_ok",
    "risk_budget_ok"
  ]
}
```

### 9.3 Rejected Decision Object

```json
{
  "timestamp": "2026-05-04T10:15:00",
  "symbol": "XAUUSDm",
  "decision": "REJECT",
  "side": "BUY",
  "status": "REJECTED",
  "reasons": [
    "spread_too_high",
    "rr_below_minimum"
  ]
}
```

Every raw signal must produce either an approved trade decision or a rejected decision log.

---

## 10. Risk Management Specification

Risk management is mandatory. No signal may bypass the risk layer.

### 10.1 Risk Constraints

The system must enforce:

```text
- maximum risk per trade
- maximum daily loss
- maximum weekly loss
- maximum open positions
- maximum symbol exposure
- maximum correlated exposure
- maximum lot size
- minimum lot size
- broker lot step
- stop loss required for every position
```

### 10.2 Recommended Risk Modes

| Mode | Risk Per Trade | Daily Loss Limit | Description |
|---|---:|---:|---|
| `research` | 0% | 0% | No execution |
| `paper` | 0% | 0% | Demo only |
| `micro_live` | 0.10–0.25% | 0.5–1.0% | First real-money testing |
| `conservative` | 0.25–0.50% | 1.0–1.5% | Stable live mode |
| `aggressive` | up to 1.0% | 2.0–3.0% | Only after proven edge |

### 10.3 Position Sizing

Base formula:

```text
risk_amount = account_equity * risk_per_trade
position_size = risk_amount / stop_distance_value
```

For CFD/FX, position sizing must account for:

```text
pip value
contract size
lot size
symbol currency
account currency
```

### 10.4 Fractional Kelly Rule

If Kelly sizing is used, it must be capped.

```text
final_risk = min(fractional_kelly_risk, fixed_risk_cap, volatility_target_risk)
```

Recommended:

```python
FRACTIONAL_KELLY = 0.25
MAX_RISK_PER_TRADE = 0.005
```

The system must never use uncapped full Kelly sizing in live mode.

### 10.5 Stop Loss Requirement

Every new position must have a stop loss.

If the broker accepts the order but SL is missing:

```text
1. attempt to set SL immediately
2. if SL update fails, close position or halt system
3. log emergency event
```

---

## 11. Trade Lifecycle Specification

The system must track trades as stateful objects.

### 11.1 Trade States

```text
SIGNAL_CREATED
SIGNAL_REJECTED
ORDER_CREATED
ORDER_SENT
ORDER_FILLED
ORDER_REJECTED
POSITION_OPEN
POSITION_PARTIALLY_CLOSED
POSITION_CLOSED_TP
POSITION_CLOSED_SL
POSITION_CLOSED_TIMEOUT
POSITION_CLOSED_SIGNAL
POSITION_CLOSED_MANUAL
ERROR
```

### 11.2 Entry Logic

A trade may be opened only if:

```text
- signal is approved
- risk checks pass
- no conflicting position exists
- execution mode allows orders
- market is open
- symbol is tradable
- spread is acceptable
```

### 11.3 Exit Logic

A trade may be closed by:

```text
- stop loss hit
- take profit hit
- time stop reached
- opposite signal
- risk engine forced exit
- kill switch
- manual close
- system error protection
```

### 11.4 Time Stop

The system should support a maximum holding period.

Example:

```python
TIME_STOP_BARS = 24
```

If a position remains open for longer than the configured bar limit, it should be closed or marked for closure.

---

## 12. Backtesting Specification

Backtesting must simulate the trade lifecycle, not just signal returns.

### 12.1 Required Behavior

The backtester must:

```text
- process candles in chronological order
- avoid lookahead bias
- generate signals using only available past/current data
- open positions based on approved decisions
- track open positions across multiple bars
- check TP/SL using high/low prices
- apply time stop
- apply transaction costs
- apply slippage
- update equity curve
- log every trade
```

### 12.2 No Lookahead Rule

Signals generated from candle `t` can only be executed at a valid future price, usually:

```text
next candle open
or simulated market price after signal time
```

Invalid:

```python
signal[t] uses close[t+1]
```

Valid:

```python
signal[t] uses data up to t
position_return[t+1] uses signal[t]
```

### 12.3 TP/SL Resolution

For long positions:

```text
If low <= stop_loss → SL hit
If high >= take_profit → TP hit
```

For short positions:

```text
If high >= stop_loss → SL hit
If low <= take_profit → TP hit
```

### 12.4 Ambiguous Same-Bar TP/SL

If both TP and SL are touched in the same candle, the backtester must use a deterministic policy.

Allowed policies:

```text
conservative: assume SL first
optimistic: assume TP first
intrabar: use lower timeframe data if available
randomized: probabilistic path simulation
```

Default should be:

```text
conservative
```

### 12.5 Transaction Costs

Backtest must include:

```text
spread
commission
slippage
swap/overnight cost if applicable
```

### 12.6 Slippage Model

Recommended scenarios:

| Scenario | Slippage Assumption |
|---|---|
| Base | 0.5 × spread |
| Bad | 1.0 × spread |
| Stress | 2.0 × spread |
| News | 3.0–5.0 × spread |

### 12.7 Backtest Outputs

Backtest must produce:

```text
trade log
equity curve
drawdown curve
monthly returns
symbol-level performance
strategy-level performance
cost analysis
rejected signal summary
```

---

## 13. Walk-Forward Testing Specification

Walk-forward testing is required before paper or live deployment.

### 13.1 Recommended Split

```text
Train: 12 months
Validation: 3 months
Test: 3 months
Step forward: 3 months
```

Example:

```text
Round 1:
Train: 2021-01 → 2021-12
Validation: 2022-01 → 2022-03
Test: 2022-04 → 2022-06

Round 2:
Train: 2021-04 → 2022-03
Validation: 2022-04 → 2022-06
Test: 2022-07 → 2022-09
```

### 13.2 Rules

```text
- Test set must not be used for parameter tuning
- Thresholds must be selected on train/validation only
- Final test results must be locked and reproducible
- Each round must log model version, config hash, and data range
```

---

## 14. Performance Metrics Specification

The system must not rely on win rate alone.

### 14.1 Required Metrics

```text
Total return
Annualized return if applicable
Win rate
Average win
Average loss
Profit factor
Expectancy
Sharpe ratio
Sortino ratio
Max drawdown
Calmar ratio
Average R multiple
Median R multiple
Longest losing streak
Number of trades
Exposure time
Average holding time
Cost as % of gross profit
Return by symbol
Return by regime
Return by session
```

### 14.2 Expectancy

```text
Expectancy = (Win Rate × Average Win) - (Loss Rate × Average Loss)
```

### 14.3 Profit Factor

```text
Profit Factor = Gross Profit / Gross Loss
```

### 14.4 Drawdown

```text
Drawdown = (Equity - Running Peak Equity) / Running Peak Equity
```

---

## 15. Robustness Testing Specification

Before paper or live deployment, the strategy must pass robustness checks.

### 15.1 Required Tests

```text
- parameter sensitivity test
- transaction cost stress test
- spread stress test
- slippage stress test
- Monte Carlo trade shuffle
- remove best N trades test
- double worst N losses test
- multi-symbol consistency test
- regime-based performance analysis
```

### 15.2 Parameter Sensitivity

The system should test whether performance survives nearby parameter values.

Example:

```text
confidence_threshold = 0.50, 0.55, 0.60, 0.65, 0.70
ATR_multiplier = 1.5, 2.0, 2.5, 3.0
TP_R = 1.5, 2.0, 2.5, 3.0
```

A production candidate should not depend on a single fragile parameter value.

### 15.3 Monte Carlo Trade Shuffle

The system must estimate drawdown risk by randomizing trade order.

Output:

```text
Median max drawdown
P95 max drawdown
P99 max drawdown
Probability of ruin
Worst simulated losing streak
```

---

## 16. Execution Specification

### 16.1 Order Types

The execution layer should support:

```text
market order
limit order
stop order
stop loss
take profit
position close
position modify
```

### 16.2 Order Request Object

```json
{
  "symbol": "XAUUSDm",
  "side": "BUY",
  "order_type": "MARKET",
  "volume": 0.03,
  "stop_loss": 2304.00,
  "take_profit": 2323.50,
  "magic": 7001,
  "comment": "ml_trade_v5"
}
```

### 16.3 Pre-Trade Execution Checks

Before sending an order:

```text
- MT5 connected
- account ID matches expected account
- symbol is visible and tradable
- market is open
- spread acceptable
- lot size within broker min/max/step
- SL/TP distance satisfies broker stop level
- margin is sufficient
- no risk limit breach
- position state reconciled
```

### 16.4 Post-Trade Checks

After sending an order:

```text
- verify order result
- verify actual fill price
- verify actual volume
- verify position exists if filled
- verify SL/TP attached
- log slippage
- update local state
- update risk budget
```

---

## 17. Live State Reconciliation

The system must not rely only on internal memory.

Every live loop should:

```text
1. fetch broker open positions
2. filter by known magic numbers
3. compare broker state with internal state
4. detect missing, duplicated, or mismatched positions
5. resolve mismatch or halt safely
```

### 17.1 Mismatch Examples

```text
Internal state says no position, broker has open position
Internal state says position open, broker has none
Position volume differs
Position SL/TP differs
Unknown position exists with system magic number
```

### 17.2 Required Behavior

If mismatch cannot be safely resolved:

```text
- halt new orders
- log critical event
- alert user
- require manual review
```

---

## 18. Kill Switch Specification

The system must include multiple kill switch triggers.

### 18.1 Required Triggers

```text
- daily loss limit breached
- weekly loss limit breached
- max drawdown breached
- consecutive loss limit breached
- data stale
- broker disconnected
- feature validation failed
- model/scaler mismatch
- position state mismatch
- spread extreme
- abnormal slippage
- unexpected exception in live loop
```

### 18.2 Kill Switch Behavior

Configurable behaviors:

```text
HALT_NEW_TRADES
CLOSE_ALL_SYSTEM_POSITIONS
REDUCE_POSITION_SIZE
MANUAL_REVIEW_REQUIRED
```

Default recommended behavior:

```text
HALT_NEW_TRADES
```

For critical safety failures:

```text
HALT_NEW_TRADES + MANUAL_REVIEW_REQUIRED
```

---

## 19. Logging Specification

Logging is mandatory for production-readiness.

### 19.1 Log Types

```text
system.log
signals.jsonl
decisions.jsonl
orders.jsonl
trades.jsonl
positions.jsonl
risk_events.jsonl
errors.jsonl
```

### 19.2 Decision Log Requirements

Every signal must create a decision log.

Required fields:

```text
timestamp
symbol
timeframe
raw_signal
final_decision
confidence
expected_return
spread
ATR
regime
risk_reward
position_size
risk_pct
filters_passed
filters_failed
reason_codes
model_version
config_hash
feature_schema_version
```

### 19.3 Trade Log Requirements

Every completed trade must include:

```text
trade_id
symbol
side
entry_time
entry_price
exit_time
exit_price
position_size
stop_loss
take_profit
exit_reason
gross_pnl
net_pnl
commission
spread_cost
slippage
R_multiple
holding_bars
model_version
config_hash
```

---

## 20. Storage Specification

For production-oriented use, the system should persist state.

Recommended local storage:

```text
SQLite
```

### 20.1 Required Tables

```text
signals
decisions
orders
positions
trades
risk_events
system_events
model_versions
config_versions
```

### 20.2 Reproducibility Metadata

Each backtest and live run should store:

```text
run_id
git_commit
config_hash
model_version
scaler_version
feature_schema_version
data_range
symbol_universe
execution_mode
start_time
end_time
```

---

## 21. Monitoring Specification

The dashboard or monitoring layer must answer:

```text
Is the system online?
Is MT5 connected?
Is market data fresh?
What positions are open?
How much risk is currently used?
What was the latest signal?
Why were recent signals rejected?
Is the kill switch active?
What model/config version is running?
```

### 21.1 Recommended Dashboard Panels

```text
System Health
Market Data Status
Open Positions
Risk Budget
Latest Signals
Rejected Signals
Model Version
Kill Switch Status
Daily Performance
```

---

## 22. Configuration Specification

All trading behavior must be configurable, not hardcoded.

### 22.1 Required Config Groups

```yaml
mode:
  name: conservative

symbols:
  enabled: [XAUUSDm, EURUSDm, USTECm]

risk:
  risk_per_trade: 0.0025
  daily_loss_limit: 0.01
  max_open_positions: 2
  max_correlation: 0.7
  max_lot: 0.10

signal:
  buy_threshold: 0.60
  sell_threshold: 0.60
  min_rr: 1.5

execution:
  order_type: market
  max_spread_multiplier: 2.5
  slippage_model: base

backtest:
  initial_equity: 10000
  commission_per_lot: 0
  same_bar_policy: conservative
```

### 22.2 Config Hash

Each run must compute a config hash and store it in logs.

---

## 23. Baseline Strategy Requirements

The platform must include simple baseline strategies for comparison.

Required baselines:

```text
buy and hold
random entry with same exit rules
moving average crossover
RSI mean reversion
ATR breakout
```

The main strategy must be compared against these baselines.

A model-based system is not considered validated unless it beats or improves upon relevant baselines after realistic costs.

---

## 24. Resume-Ready Validation Requirements

To be considered resume-ready, the project should include:

```text
- architecture diagram
- backtest report
- walk-forward report
- baseline comparison
- ablation study
- realistic transaction cost testing
- robustness testing
- paper/shadow trading logs
- risk management documentation
- deployment instructions
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
```

---

## 25. Production Candidate Checklist

A strategy/system version can be marked as production candidate only if:

```text
[ ] Data validation passes
[ ] Feature schema validation passes
[ ] Model/scaler hash validation passes
[ ] Backtest is reproducible
[ ] Walk-forward test completed
[ ] Out-of-sample result locked
[ ] Realistic costs included
[ ] Slippage stress test completed
[ ] Spread stress test completed
[ ] Monte Carlo robustness test completed
[ ] Baseline comparison completed
[ ] Ablation study completed
[ ] Risk limits configured
[ ] Kill switch tested
[ ] Shadow mode tested
[ ] Paper mode tested
[ ] MT5 state reconciliation tested
[ ] Decision logging enabled
[ ] Trade logging enabled
[ ] Dashboard/monitoring available
[ ] Emergency stop mechanism available
```

---

## 26. Recommended Development Priority

### Priority 1 — Correctness

```text
Data validation
Feature schema lock
Model/scaler hash check
No-lookahead backtest
Stateful TP/SL/timeout simulation
```

### Priority 2 — Risk Safety

```text
Fractional Kelly only
Risk caps
Daily loss limit
Max position limit
Correlation cap
Kill switch
```

### Priority 3 — Observability

```text
Decision logs
Rejected signal logs
Trade logs
Risk event logs
System health logs
```

### Priority 4 — Realism

```text
Spread model
Slippage model
Commission/swap
Session filters
News-time stress
```

### Priority 5 — Research Quality

```text
Walk-forward testing
Baseline comparison
Ablation study
Robustness testing
Paper trading comparison
```

---

## 27. Non-Goals

The Algo Trade core does not need to solve these directly:

```text
- predicting exact next candle OHLC
- guaranteeing profit
- fully autonomous online learning in live mode
- high-frequency trading latency optimization
- exchange co-location
- institutional order book execution
```

The immediate goal is a robust solo-developer quant trading platform, not a hedge fund execution stack.

---

## 28. Design Principle

The system should optimize for:

```text
Reliability over complexity
Reproducibility over beautiful backtests
Risk control over high win rate
Debuggability over magical AI behavior
Survivability over aggression
```

Final principle:

```text
Do not make the system smarter until it is harder for it to lie to you.
```
