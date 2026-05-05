from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class SignalSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    CLOSE_LONG = "CLOSE_LONG"
    CLOSE_SHORT = "CLOSE_SHORT"


class DecisionType(StrEnum):
    ENTER_LONG = "ENTER_LONG"
    ENTER_SHORT = "ENTER_SHORT"
    EXIT_LONG = "EXIT_LONG"
    EXIT_SHORT = "EXIT_SHORT"
    REJECT = "REJECT"
    HOLD = "HOLD"
    HALT = "HALT"


class DecisionStatus(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    HELD = "HELD"
    HALTED = "HALTED"


class TradeState(StrEnum):
    SIGNAL_CREATED = "SIGNAL_CREATED"
    SIGNAL_REJECTED = "SIGNAL_REJECTED"
    ORDER_CREATED = "ORDER_CREATED"
    ORDER_SENT = "ORDER_SENT"
    ORDER_FILLED = "ORDER_FILLED"
    ORDER_REJECTED = "ORDER_REJECTED"
    POSITION_OPEN = "POSITION_OPEN"
    POSITION_PARTIALLY_CLOSED = "POSITION_PARTIALLY_CLOSED"
    POSITION_CLOSED_TP = "POSITION_CLOSED_TP"
    POSITION_CLOSED_SL = "POSITION_CLOSED_SL"
    POSITION_CLOSED_TIMEOUT = "POSITION_CLOSED_TIMEOUT"
    POSITION_CLOSED_SIGNAL = "POSITION_CLOSED_SIGNAL"
    POSITION_CLOSED_MANUAL = "POSITION_CLOSED_MANUAL"
    ERROR = "ERROR"


@dataclass(frozen=True)
class MarketBar:
    timestamp: datetime
    symbol: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    spread: float = 0.0


@dataclass(frozen=True)
class FeatureFrame:
    data: Any
    feature_schema_version: str
    schema: list[str]


@dataclass(frozen=True)
class Signal:
    timestamp: datetime
    symbol: str
    side: SignalSide
    confidence: float
    expected_return: float
    source: str
    timeframe: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        record = asdict(self)
        record["timestamp"] = self.timestamp.isoformat()
        record["side"] = self.side.value
        return record


@dataclass(frozen=True)
class TradeDecision:
    timestamp: datetime
    symbol: str
    decision: DecisionType
    side: SignalSide
    entry_type: str | None
    entry_price_estimate: float | None
    stop_loss: float | None
    take_profit: float | None
    risk_pct: float
    position_size: float
    rr: float
    status: DecisionStatus
    reasons: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        record = asdict(self)
        record["timestamp"] = self.timestamp.isoformat()
        record["decision"] = self.decision.value
        record["side"] = self.side.value
        record["status"] = self.status.value
        return record


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    side: SignalSide
    order_type: str
    volume: float
    stop_loss: float
    take_profit: float
    magic: int
    comment: str


@dataclass
class Position:
    trade_id: str
    symbol: str
    side: SignalSide
    entry_time: datetime
    entry_price: float
    volume: float
    stop_loss: float
    take_profit: float
    state: TradeState = TradeState.POSITION_OPEN
    holding_bars: int = 0


@dataclass(frozen=True)
class Trade:
    trade_id: str
    symbol: str
    side: SignalSide
    entry_time: datetime
    entry_price: float
    exit_time: datetime
    exit_price: float
    position_size: float
    stop_loss: float
    take_profit: float
    exit_reason: TradeState
    gross_pnl: float
    net_pnl: float
    commission: float
    spread_cost: float
    slippage: float
    r_multiple: float
    holding_bars: int
    model_version: str
    config_hash: str

    def to_record(self) -> dict[str, Any]:
        record = asdict(self)
        record["side"] = self.side.value
        record["entry_time"] = self.entry_time.isoformat()
        record["exit_time"] = self.exit_time.isoformat()
        record["exit_reason"] = self.exit_reason.value
        return record


@dataclass(frozen=True)
class RiskSnapshot:
    equity: float
    open_risk: float
    daily_loss: float
    weekly_loss: float
    drawdown: float
    kill_switch_active: bool
    kill_switch_reason: str | None = None


@dataclass(frozen=True)
class RunMetadata:
    run_id: str
    config_hash: str
    data_range: tuple[str, str] | None
    symbol_universe: list[str]
    mode: str
    model_version: str = "none"
    git_commit: str | None = None

    def to_record(self) -> dict[str, Any]:
        return asdict(self)
