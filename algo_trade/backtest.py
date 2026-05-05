from __future__ import annotations

import uuid
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pandas as pd

from algo_trade.audit import SymbolAuditReport, build_symbol_audit
from algo_trade.config import AppConfig
from algo_trade.decisions import DecisionEngine
from algo_trade.features import build_features, validate_feature_schema
from algo_trade.filters import SignalFilter
from algo_trade.reports import PerformanceReport, build_performance_report
from algo_trade.risk import RiskEngine
from algo_trade.storage import RunRecorder
from algo_trade.strategies import Strategy
from algo_trade.symbols import SymbolRegistry, SymbolSpec
from algo_trade.types import DecisionStatus, DecisionType, Position, RunMetadata, Signal, SignalSide, Trade, TradeDecision, TradeState
from algo_trade.validation import validate_ohlcv
from algo_trade.viability import StrategyViabilityReport, build_strategy_viability


@dataclass(frozen=True)
class BacktestResult:
    run_id: str
    report: PerformanceReport
    trades: list[Trade]
    equity_curve: pd.Series
    run_dir: Path
    data_quality: object | None = None
    symbol_audit: SymbolAuditReport | None = None
    strategy_viability: StrategyViabilityReport | None = None


class BacktestEngine:
    def __init__(
        self,
        config: AppConfig,
        registry: SymbolRegistry,
        strategy: Strategy,
        record_events: bool = True,
        progress_callback: Callable[[dict[str, object]], None] | None = None,
        progress_step_percent: int = 5,
        progress_label: str | None = None,
    ):
        self.config = config
        self.registry = registry
        self.strategy = strategy
        self.record_events = record_events
        self.progress_callback = progress_callback
        self.progress_step_percent = max(1, min(int(progress_step_percent), 100))
        self.progress_label = progress_label or f"backtest {strategy.name}"

    def run(self, frame: pd.DataFrame, symbol_name: str) -> BacktestResult:
        self._enforce_data_evidence(frame, symbol_name)
        data_config = self.config.raw.get("data", {})
        missing_bar_policy = str(data_config.get("missing_bar_policy", "fail"))
        missing_threshold = int(
            data_config.get(
                "missing_bars_allowed",
                len(frame) * float(data_config.get("max_missing_bar_ratio", 0.0)),
            )
        )
        if missing_bar_policy == "warn":
            missing_threshold = len(frame)
        quality = validate_ohlcv(
            frame,
            missing_threshold=missing_threshold,
            allow_session_gaps=bool(data_config.get("allow_session_gaps", False)),
            max_session_gap_minutes=int(data_config.get("max_session_gap_minutes", 180)),
            source=str(self.config.raw.get("data", {}).get("source", "csv")),
            source_path=str(frame.attrs.get("source_path")) if frame.attrs.get("source_path") else None,
            timestamp_semantics=str(self.config.raw.get("data", {}).get("timestamp_semantics", "candle_open_time")),
        )
        feature_frame = build_features(frame)
        validate_feature_schema(feature_frame)
        data = feature_frame.data
        data["feature_schema_version"] = feature_frame.feature_schema_version
        symbol = self.registry.get(symbol_name)
        run_id = f"bt-{uuid.uuid4().hex[:12]}"
        run_dir = self.config.output_dir / run_id
        symbol_audit = build_symbol_audit(
            frame,
            symbol,
            timestamp_semantics=str(self.config.raw.get("data", {}).get("timestamp_semantics", "candle_open_time")),
            broker_metadata=frame.attrs.get("broker_metadata"),
            max_spread_median_to_config_ratio=float(
                self.config.raw.get("symbol_audit", {}).get("max_spread_median_to_config_ratio", 3.0)
            ),
            require_broker_metadata=bool(self.config.raw.get("symbol_audit", {}).get("require_broker_metadata", True)),
        )
        self._persist_broker_metadata_snapshot(frame, run_dir)
        recorder = (
            RunRecorder(run_id, run_dir, mode=self.config.mode, config_hash=self.config.config_hash)
            if self.record_events
            else NullRecorder()
        )
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
            recorder.record("system_events", "system_events", {"event": "symbol_audit", **symbol_audit.to_record()})
            if frame.attrs.get("broker_metadata"):
                recorder.record(
                    "system_events",
                    "system_events",
                    {"event": "broker_symbol_metadata", **frame.attrs["broker_metadata"]},
                )
            recorder.record("system_events", "config_versions", {"config_hash": self.config.config_hash, "config": self.config.raw})
            recorder.record("system_events", "symbol_registry_snapshots", {"symbols": self.config.raw["symbols"]})

            risk = RiskEngine(self.config.raw["risk"], float(self.config.raw["backtest"]["initial_equity"]))
            filters = SignalFilter(
                self.config.raw["signal"],
                self.config.raw.get("filters", {}),
                self.config.raw.get("session_filters", {}),
                self.config.raw.get("regime_filters", {}),
            )
            decisions = DecisionEngine(filters, risk, self.config.raw["backtest"])
            return self._simulate(data, symbol, risk, decisions, recorder, run_id, run_dir, quality, symbol_audit)
        finally:
            recorder.close()

    def _enforce_data_evidence(self, frame: pd.DataFrame, symbol_name: str) -> None:
        data_config = self.config.raw.get("data", {})
        min_bars = int(data_config.get("min_bars", 0))
        if len(frame) < min_bars:
            raise ValueError(
                f"Backtest evidence rejected for {symbol_name}: {len(frame)} bars found, "
                f"minimum required is {min_bars}. Use real broker data or enable MT5 backfill."
            )
        if bool(data_config.get("require_real_data", True)) and bool(frame.attrs.get("is_sample_data", False)):
            raise ValueError("Backtest evidence rejected: sample fixture data is not allowed when data.require_real_data=true")

    def _simulate(
        self,
        data: pd.DataFrame,
        symbol: SymbolSpec,
        risk: RiskEngine,
        decisions: DecisionEngine,
        recorder: RunRecorder,
        run_id: str,
        run_dir: Path,
        quality: object,
        symbol_audit: SymbolAuditReport,
    ) -> BacktestResult:
        equity = float(self.config.raw["backtest"]["initial_equity"])
        equity_points: list[tuple[pd.Timestamp, float]] = []
        trades: list[Trade] = []
        rejected_reasons: list[str] = []
        signals_for_viability: list[Signal] = []
        decisions_for_viability: list[TradeDecision] = []
        position: Position | None = None
        total_iterations = max(len(data) - 1, 1)
        next_progress_threshold = self.progress_step_percent

        self._emit_progress(0, 0, total_iterations)

        def report_progress(current: int) -> None:
            nonlocal next_progress_threshold
            percent = int((current / total_iterations) * 100)
            while next_progress_threshold < 100 and percent >= next_progress_threshold:
                self._emit_progress(next_progress_threshold, current, total_iterations)
                next_progress_threshold += self.progress_step_percent
            if current >= total_iterations:
                self._emit_progress(100, total_iterations, total_iterations)

        for index in range(0, len(data) - 1):
            try:
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
                signals_for_viability.append(signal)
                recorder.record("signals", "signals", signal.to_record(), signal.timestamp.isoformat())
                if position is not None:
                    decision = self._blocked_by_position_decision(signal, position)
                    decisions_for_viability.append(decision)
                    recorder.record("decisions", "decisions", decision.to_record(), decision.timestamp.isoformat())
                    rejected_reasons.extend(decision.reasons)
                    equity_points.append((timestamp, equity))
                    continue

                entry_price = float(next_row["open"])
                decision = decisions.decide(signal, symbol, equity, entry_price, 0)
                decisions_for_viability.append(decision)
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
                        metadata=signal.metadata.copy(),
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
                    recorder.record(
                        "fills",
                        "fills",
                        {
                            "trade_id": position.trade_id,
                            "symbol": position.symbol,
                            "side": position.side.value,
                            "fill_price": position.entry_price,
                            "volume": position.volume,
                            "state": TradeState.ORDER_FILLED.value,
                        },
                        position.entry_time.isoformat(),
                    )
                    recorder.record(
                        "positions",
                        "positions",
                        {
                            "trade_id": position.trade_id,
                            "symbol": position.symbol,
                            "side": position.side.value,
                            "entry_price": position.entry_price,
                            "volume": position.volume,
                            "stop_loss": position.stop_loss,
                            "take_profit": position.take_profit,
                            "state": position.state.value,
                        },
                        position.entry_time.isoformat(),
                    )
                equity_points.append((timestamp, equity))
            finally:
                report_progress(index + 1)

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
        viability = build_strategy_viability(signals_for_viability, decisions_for_viability, self.config.raw.get("strategy_viability", {}))
        recorder.record("system_events", "system_events", {"event": "performance_report", **report.to_record()})
        recorder.record("system_events", "system_events", {"event": "strategy_viability", **viability.to_record()})
        return BacktestResult(
            run_id=run_id,
            report=report,
            trades=trades,
            equity_curve=equity_curve,
            run_dir=run_dir,
            data_quality=quality,
            symbol_audit=symbol_audit,
            strategy_viability=viability,
        )

    def _emit_progress(self, percent: int, current: int, total: int) -> None:
        if self.progress_callback is None:
            return
        self.progress_callback(
            {
                "label": self.progress_label,
                "strategy": self.strategy.name,
                "percent": int(percent),
                "current": int(current),
                "total": int(total),
            }
        )

    def _persist_broker_metadata_snapshot(self, frame: pd.DataFrame, run_dir: Path) -> None:
        if not self.record_events:
            return
        metadata = frame.attrs.get("broker_metadata")
        error = frame.attrs.get("broker_metadata_error")
        if not metadata and not error:
            return
        run_dir.mkdir(parents=True, exist_ok=True)
        if metadata:
            (run_dir / "broker_symbol_metadata.json").write_text(
                json.dumps(metadata, indent=2, sort_keys=True, default=str),
                encoding="utf-8",
            )
        if error:
            (run_dir / "broker_symbol_metadata_error.json").write_text(
                json.dumps({"error": str(error)}, indent=2, sort_keys=True),
                encoding="utf-8",
            )

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

    def _blocked_by_position_decision(self, signal: Signal, position: Position) -> TradeDecision:
        return TradeDecision(
            timestamp=signal.timestamp,
            symbol=signal.symbol,
            decision=DecisionType.REJECT,
            side=signal.side,
            entry_type=None,
            entry_price_estimate=None,
            stop_loss=None,
            take_profit=None,
            risk_pct=0.0,
            position_size=0.0,
            rr=0.0,
            status=DecisionStatus.REJECTED,
            reasons=["position_already_open"],
            signal_id=signal.signal_id,
            metadata={
                "source": signal.source,
                "confidence": signal.confidence,
                "expected_return": signal.expected_return,
                "open_trade_id": position.trade_id,
                **signal.metadata,
            },
        )

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
            strategy_version=getattr(self.strategy, "version", "unknown"),
            entry_session=position.metadata.get("session_label"),
            entry_trend_regime=position.metadata.get("trend_regime"),
            entry_range_regime=position.metadata.get("range_regime"),
            entry_spread_percentile_session=position.metadata.get("spread_percentile_session"),
        )

    def _slippage(self, row: pd.Series, symbol: SymbolSpec, volume: float) -> float:
        model = self.config.raw["backtest"].get("slippage_model", "base")
        multiplier = {"base": 0.5, "bad": 1.0, "stress": 2.0, "news": 3.0}.get(model, 0.5)
        return float(row.get("spread", 0.0)) * multiplier * symbol.pip_size * symbol.pip_value * volume


class NullRecorder:
    def record(self, stream: str, table: str, payload: dict, timestamp: str | None = None) -> None:
        return None

    def close(self) -> None:
        return None
