from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from algo_trade.config import AppConfig
from algo_trade.decisions import DecisionEngine
from algo_trade.features import build_features, validate_feature_schema
from algo_trade.filters import SignalFilter
from algo_trade.reports import PerformanceReport, build_performance_report
from algo_trade.risk import RiskEngine
from algo_trade.storage import RunRecorder
from algo_trade.strategies import Strategy
from algo_trade.symbols import SymbolRegistry, SymbolSpec
from algo_trade.types import DecisionStatus, Position, RunMetadata, SignalSide, Trade, TradeState
from algo_trade.validation import validate_ohlcv


@dataclass(frozen=True)
class BacktestResult:
    run_id: str
    report: PerformanceReport
    trades: list[Trade]
    equity_curve: pd.Series
    run_dir: Path


class BacktestEngine:
    def __init__(self, config: AppConfig, registry: SymbolRegistry, strategy: Strategy):
        self.config = config
        self.registry = registry
        self.strategy = strategy

    def run(self, frame: pd.DataFrame, symbol_name: str) -> BacktestResult:
        quality = validate_ohlcv(frame)
        feature_frame = build_features(frame)
        validate_feature_schema(feature_frame)
        data = feature_frame.data
        symbol = self.registry.get(symbol_name)
        run_id = f"bt-{uuid.uuid4().hex[:12]}"
        run_dir = self.config.output_dir / run_id
        recorder = RunRecorder(run_id, run_dir)
        try:
            metadata = RunMetadata(
                run_id=run_id,
                config_hash=self.config.config_hash,
                data_range=(quality.start, quality.end),
                symbol_universe=[symbol_name],
                mode=self.config.mode,
            )
            recorder.record("system_events", "runs", metadata.to_record())
            recorder.record("system_events", "system_events", {"event": "data_quality", **quality.to_record()})
            recorder.record("system_events", "config_versions", {"config_hash": self.config.config_hash, "config": self.config.raw})

            risk = RiskEngine(self.config.raw["risk"], float(self.config.raw["backtest"]["initial_equity"]))
            filters = SignalFilter(self.config.raw["signal"], self.config.raw.get("filters", {}))
            decisions = DecisionEngine(filters, risk, self.config.raw["backtest"])
            return self._simulate(data, symbol, risk, decisions, recorder, run_id, run_dir)
        finally:
            recorder.close()

    def _simulate(
        self,
        data: pd.DataFrame,
        symbol: SymbolSpec,
        risk: RiskEngine,
        decisions: DecisionEngine,
        recorder: RunRecorder,
        run_id: str,
        run_dir: Path,
    ) -> BacktestResult:
        equity = float(self.config.raw["backtest"]["initial_equity"])
        equity_points: list[tuple[pd.Timestamp, float]] = []
        trades: list[Trade] = []
        rejected_reasons: list[str] = []
        position: Position | None = None

        for index in range(0, len(data) - 1):
            row = data.iloc[index]
            next_row = data.iloc[index + 1]
            timestamp = row["timestamp"]
            if position is not None:
                closed_trade = self._maybe_close(position, row, symbol, equity)
                if closed_trade is not None:
                    equity += closed_trade.net_pnl
                    trades.append(closed_trade)
                    recorder.record("trades", "trades", closed_trade.to_record(), closed_trade.exit_time.isoformat())
                    position = None

            signal = self.strategy.generate(row)
            recorder.record("signals", "signals", signal.to_record(), signal.timestamp.isoformat())
            if position is not None:
                equity_points.append((timestamp, equity))
                continue

            entry_price = float(next_row["open"])
            decision = decisions.decide(signal, symbol, equity, entry_price, 0)
            recorder.record("decisions", "decisions", decision.to_record(), decision.timestamp.isoformat())
            if decision.status == DecisionStatus.REJECTED:
                rejected_reasons.extend(decision.reasons)
            if decision.status == DecisionStatus.APPROVED and decision.stop_loss is not None and decision.take_profit is not None:
                position = Position(
                    trade_id=f"tr-{uuid.uuid4().hex[:12]}",
                    symbol=symbol.name,
                    side=decision.side,
                    entry_time=next_row["timestamp"].to_pydatetime(),
                    entry_price=entry_price,
                    volume=decision.position_size,
                    stop_loss=decision.stop_loss,
                    take_profit=decision.take_profit,
                    state=TradeState.POSITION_OPEN,
                )
                recorder.record(
                    "orders",
                    "orders",
                    {
                        "trade_id": position.trade_id,
                        "symbol": position.symbol,
                        "side": position.side.value,
                        "order_type": "SIMULATED_MARKET",
                        "entry_price": position.entry_price,
                        "stop_loss": position.stop_loss,
                        "take_profit": position.take_profit,
                    },
                    position.entry_time.isoformat(),
                )
            equity_points.append((timestamp, equity))

        if position is not None:
            final_row = data.iloc[-1]
            forced = self._close_position(position, final_row, float(final_row["close"]), TradeState.POSITION_CLOSED_TIMEOUT, symbol, equity)
            equity += forced.net_pnl
            trades.append(forced)
            recorder.record("trades", "trades", forced.to_record(), forced.exit_time.isoformat())
            equity_points.append((final_row["timestamp"], equity))

        equity_curve = pd.Series(
            [point[1] for point in equity_points],
            index=pd.to_datetime([point[0] for point in equity_points]),
            name="equity",
        )
        report = build_performance_report(trades, equity_curve, rejected_reasons, float(self.config.raw["backtest"]["initial_equity"]))
        recorder.record("system_events", "system_events", {"event": "performance_report", **report.to_record()})
        return BacktestResult(run_id=run_id, report=report, trades=trades, equity_curve=equity_curve, run_dir=run_dir)

    def _maybe_close(self, position: Position, row: pd.Series, symbol: SymbolSpec, equity: float) -> Trade | None:
        position.holding_bars += 1
        high = float(row["high"])
        low = float(row["low"])
        if position.side == SignalSide.BUY:
            stop_hit = low <= position.stop_loss
            tp_hit = high >= position.take_profit
            if stop_hit:
                return self._close_position(position, row, position.stop_loss, TradeState.POSITION_CLOSED_SL, symbol, equity)
            if tp_hit:
                return self._close_position(position, row, position.take_profit, TradeState.POSITION_CLOSED_TP, symbol, equity)
        else:
            stop_hit = high >= position.stop_loss
            tp_hit = low <= position.take_profit
            if stop_hit:
                return self._close_position(position, row, position.stop_loss, TradeState.POSITION_CLOSED_SL, symbol, equity)
            if tp_hit:
                return self._close_position(position, row, position.take_profit, TradeState.POSITION_CLOSED_TP, symbol, equity)
        if position.holding_bars >= int(self.config.raw["backtest"].get("time_stop_bars", 24)):
            return self._close_position(position, row, float(row["close"]), TradeState.POSITION_CLOSED_TIMEOUT, symbol, equity)
        return None

    def _close_position(
        self,
        position: Position,
        row: pd.Series,
        exit_price: float,
        exit_reason: TradeState,
        symbol: SymbolSpec,
        equity: float,
    ) -> Trade:
        direction = 1 if position.side == SignalSide.BUY else -1
        value_per_price_unit = (symbol.pip_value / symbol.pip_size) * position.volume
        gross_pnl = direction * (exit_price - position.entry_price) * value_per_price_unit
        spread_cost = float(row.get("spread", 0.0)) * symbol.pip_size * symbol.pip_value * position.volume * float(self.config.raw["backtest"].get("spread_cost_multiplier", 1.0))
        slippage = self._slippage(row, symbol, position.volume)
        commission = float(self.config.raw["backtest"].get("commission_per_lot", 0.0)) * position.volume
        net_pnl = gross_pnl - spread_cost - slippage - commission
        risk_amount = abs(position.entry_price - position.stop_loss) * value_per_price_unit
        r_multiple = net_pnl / risk_amount if risk_amount else 0.0
        return Trade(
            trade_id=position.trade_id,
            symbol=position.symbol,
            side=position.side,
            entry_time=position.entry_time,
            entry_price=position.entry_price,
            exit_time=row["timestamp"].to_pydatetime(),
            exit_price=exit_price,
            position_size=position.volume,
            stop_loss=position.stop_loss,
            take_profit=position.take_profit,
            exit_reason=exit_reason,
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            commission=commission,
            spread_cost=spread_cost,
            slippage=slippage,
            r_multiple=r_multiple,
            holding_bars=position.holding_bars,
            model_version="none",
            config_hash=self.config.config_hash,
        )

    def _slippage(self, row: pd.Series, symbol: SymbolSpec, volume: float) -> float:
        model = self.config.raw["backtest"].get("slippage_model", "base")
        multiplier = {"base": 0.5, "bad": 1.0, "stress": 2.0, "news": 3.0}.get(model, 0.5)
        return float(row.get("spread", 0.0)) * multiplier * symbol.pip_size * symbol.pip_value * volume
