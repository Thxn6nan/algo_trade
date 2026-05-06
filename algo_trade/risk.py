from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from algo_trade.symbols import SymbolSpec
from algo_trade.types import RiskSnapshot


@dataclass(frozen=True)
class PositionSizeResult:
    lots: float
    risk_amount: float
    risk_pct: float
    reason: str


class RiskEngine:
    def __init__(self, config: dict, initial_equity: float):
        self.config = config
        self.initial_equity = initial_equity
        self.peak_equity = initial_equity
        self.loss_period_date: date | None = None
        self.day_start_equity = initial_equity
        self.kill_switch_active = False
        self.kill_switch_reason: str | None = None

    def snapshot(self, equity: float, open_risk: float = 0.0, timestamp: datetime | None = None) -> RiskSnapshot:
        if timestamp is not None:
            current_date = timestamp.date()
            if self.loss_period_date is None:
                self.loss_period_date = current_date
            elif current_date != self.loss_period_date:
                self.loss_period_date = current_date
                self.day_start_equity = equity
                if self.kill_switch_reason == "daily_loss_limit_breached":
                    self.kill_switch_active = False
                    self.kill_switch_reason = None

        self.peak_equity = max(self.peak_equity, equity)
        drawdown = 0.0 if self.peak_equity == 0 else (self.peak_equity - equity) / self.peak_equity
        if drawdown >= float(self.config.get("max_drawdown", 1.0)):
            self.kill_switch_active = True
            self.kill_switch_reason = "max_drawdown_breached"

        loss_anchor = self.day_start_equity if timestamp is not None else self.initial_equity
        daily_loss = max(0.0, loss_anchor - equity)
        daily_loss_base = loss_anchor if loss_anchor > 0 else self.initial_equity
        if (
            self.kill_switch_reason != "max_drawdown_breached"
            and daily_loss / daily_loss_base >= float(self.config.get("daily_loss_limit", 1.0))
        ):
            self.kill_switch_active = True
            self.kill_switch_reason = "daily_loss_limit_breached"
        return RiskSnapshot(
            equity=equity,
            open_risk=open_risk,
            daily_loss=daily_loss,
            weekly_loss=daily_loss,
            drawdown=drawdown,
            kill_switch_active=self.kill_switch_active,
            kill_switch_reason=self.kill_switch_reason,
        )

    def size_position(
        self,
        equity: float,
        symbol: SymbolSpec,
        entry_price: float,
        stop_loss: float,
    ) -> PositionSizeResult:
        stop_distance = abs(entry_price - stop_loss)
        if stop_distance <= 0:
            return PositionSizeResult(0.0, 0.0, 0.0, "invalid_stop_distance")
        risk_pct = float(self.config["risk_per_trade"])
        risk_amount = equity * risk_pct
        value_per_price_unit_per_lot = symbol.tick_value / symbol.tick_size
        raw_lots = risk_amount / (stop_distance * value_per_price_unit_per_lot)
        lots = symbol.round_lot(raw_lots, max_lot_override=float(self.config.get("max_lot", symbol.max_lot)))
        if lots <= 0:
            return PositionSizeResult(0.0, risk_amount, risk_pct, "lot_size_zero")
        return PositionSizeResult(lots, risk_amount, risk_pct, "risk_sized")
