from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from algo_trade.config import AppConfig
from algo_trade.decisions import DecisionEngine
from algo_trade.env import load_dotenv
from algo_trade.execution import MT5ExecutionAdapter
from algo_trade.features import build_features, validate_feature_schema
from algo_trade.filters import SignalFilter
from algo_trade.risk import RiskEngine
from algo_trade.storage import RunRecorder
from algo_trade.strategies import Strategy
from algo_trade.symbols import SymbolRegistry
from algo_trade.types import DecisionStatus, OrderRequest, RunMetadata, SignalSide
from algo_trade.validation import validate_ohlcv


class RealMarketGateway(Protocol):
    def latest_bars(self, symbol: str, timeframe: str, count: int = 250, include_current: bool = False): ...
    def current_price(self, symbol: str, side: SignalSide) -> float: ...
    def account_equity(self) -> float: ...
    def open_positions_count(self, symbol: str) -> int: ...
    def is_market_open(self, symbol: str, max_tick_age_seconds: int = 1800) -> bool: ...
    def shutdown(self) -> None: ...


@dataclass(frozen=True)
class RealtimeRunResult:
    run_id: str
    mode: str
    decision_status: str
    order_action: str
    run_dir: str


class RealtimeRunner:
    def __init__(self, config: AppConfig, registry: SymbolRegistry, strategy: Strategy, gateway: RealMarketGateway):
        self.config = config
        self.registry = registry
        self.strategy = strategy
        self.gateway = gateway

    def run_once(self, symbol_name: str, timeframe: str) -> RealtimeRunResult:
        mode = self.config.mode
        if mode not in {"paper", "micro_live", "live"}:
            raise ValueError(f"RealtimeRunner only supports paper/micro_live/live, got {mode!r}")
        if mode in {"micro_live", "live"}:
            self._validate_live_guards()

        symbol = self.registry.get(symbol_name)
        run_id = f"{mode}-{uuid.uuid4().hex[:12]}"
        run_dir = self.config.output_dir / run_id
        recorder = RunRecorder(run_id, run_dir, mode=mode, config_hash=self.config.config_hash)
        order_action = "none"
        decision_status = "UNKNOWN"
        try:
            open_positions = self.gateway.open_positions_count(symbol_name)
            reconciliation = self._reconcile_startup(symbol_name, open_positions)
            recorder.record("reconciliation", "reconciliation_events", reconciliation)
            if reconciliation["status"] != "passed":
                return RealtimeRunResult(run_id, mode, "HALTED", "reconciliation_halt", str(run_dir))

            if not self.gateway.is_market_open(
                symbol_name,
                int(self.config.raw.get("real_data", {}).get("max_tick_age_seconds", 1800)),
            ):
                recorder.record(
                    "risk_events",
                    "risk_events",
                    {"event": "market_closed_or_stale", "symbol": symbol_name, "severity": "CRITICAL"},
                )
                return RealtimeRunResult(run_id, mode, "HALTED", "market_closed_or_stale", str(run_dir))

            bars_count = int(self.config.raw.get("real_data", {}).get("bars", 250))
            frame = self.gateway.latest_bars(symbol_name, timeframe, count=bars_count, include_current=False)
            quality = validate_ohlcv(
                frame,
                missing_threshold=int(self.config.raw.get("real_data", {}).get("missing_bars_allowed", 0)),
                allow_session_gaps=bool(self.config.raw.get("real_data", {}).get("allow_session_gaps", True)),
                max_session_gap_minutes=int(self.config.raw.get("real_data", {}).get("max_session_gap_minutes", 180)),
                source=str(self.config.raw.get("real_data", {}).get("source", "mt5")),
                timestamp_semantics=str(self.config.raw.get("data", {}).get("timestamp_semantics", "candle_open_time")),
            )
            feature_frame = build_features(frame)
            validate_feature_schema(feature_frame)
            data = feature_frame.data
            data["feature_schema_version"] = feature_frame.feature_schema_version
            row = data.iloc[-1]
            signal = self.strategy.generate(row)
            entry_price = self.gateway.current_price(symbol_name, signal.side) if signal.side != SignalSide.HOLD else float(row["close"])
            equity = self._equity()

            metadata = RunMetadata(
                run_id=run_id,
                config_hash=self.config.config_hash,
                data_range=(quality.start, quality.end),
                symbol_universe=[symbol_name],
                mode=mode,
            )
            recorder.record("system_events", "runs", metadata.to_record())
            recorder.record("system_events", "system_events", {"event": "data_quality", **quality.to_record()})
            recorder.record("system_events", "config_versions", {"config_hash": self.config.config_hash, "config": self.config.raw})
            recorder.record("signals", "signals", signal.to_record(), signal.timestamp.isoformat())

            risk = RiskEngine(self.config.raw["risk"], equity)
            filters = SignalFilter(self.config.raw["signal"], self.config.raw.get("filters", {}))
            decisions = DecisionEngine(filters, risk, self.config.raw.get("backtest", {}))
            decision = decisions.decide(signal, symbol, equity, entry_price, open_positions)
            decision_status = decision.status.value
            recorder.record("decisions", "decisions", decision.to_record(), decision.timestamp.isoformat())

            if decision.status != DecisionStatus.APPROVED:
                order_action = "not_approved"
            elif mode == "paper":
                order_action = "paper_recorded"
                recorder.record("orders", "orders", self._paper_order_record(decision, symbol.magic, run_id), decision.timestamp.isoformat())
            else:
                execution = MT5ExecutionAdapter(gateway=self.gateway, send_orders=True)
                response = execution.submit_order(self._order_request(decision, symbol.magic, run_id, "live"))
                order_action = "live_sent"
                recorder.record("orders", "orders", {"mode": "live", "response": response}, decision.timestamp.isoformat())

            recorder.record("system_events", "system_events", {"event": "realtime_run_complete", "mode": mode, "order_action": order_action})
            return RealtimeRunResult(run_id, mode, decision_status, order_action, str(run_dir))
        finally:
            recorder.close()
            self.gateway.shutdown()

    def _equity(self) -> float:
        if self.config.mode == "paper":
            return float(self.config.raw.get("execution", {}).get("paper_equity", self.config.raw["backtest"]["initial_equity"]))
        return self.gateway.account_equity()

    def _validate_live_guards(self) -> None:
        load_dotenv(self.config.raw.get("execution", {}).get("env_path", ".env"))
        execution = self.config.raw.get("execution", {})
        account = self.config.raw.get("account", {})
        risk = self.config.raw.get("risk", {})
        if execution.get("live_enabled") is not True:
            raise RuntimeError("live mode requires execution.live_enabled=true")
        if execution.get("confirm_live") != "I_UNDERSTAND_LIVE_TRADING_RISK":
            raise RuntimeError("live mode requires execution.confirm_live=I_UNDERSTAND_LIVE_TRADING_RISK")
        if os.getenv("SYSTEM_MODE", "").lower() not in {"micro_live", "live"}:
            raise RuntimeError("live-capable mode requires SYSTEM_MODE=micro_live or SYSTEM_MODE=live in .env")
        expected_account_id = account.get("expected_account_id")
        if expected_account_id is not None and str(expected_account_id) != _env_first("ACCOUNT_ID", "MT5_LOGIN"):
            raise RuntimeError("live mode account ID does not match account.expected_account_id")
        expected_server = account.get("expected_server")
        if expected_server is not None and str(expected_server) != _env_first("SERVER_NAME", "MT5_SERVER"):
            raise RuntimeError("live mode server does not match account.expected_server")
        if str(risk.get("profile", "")).lower() in {"research", "paper"}:
            raise RuntimeError("live mode requires a non-research risk profile")
        emergency_stop_file = risk.get("emergency_stop_file")
        if emergency_stop_file and Path(emergency_stop_file).exists():
            raise RuntimeError("live mode blocked by emergency stop file")

    def _reconcile_startup(self, symbol_name: str, open_positions: int) -> dict[str, object]:
        max_allowed = int(self.config.raw.get("risk", {}).get("max_open_positions", 1))
        if self.config.mode in {"micro_live", "live"} and open_positions and not self.config.raw.get("execution", {}).get("allow_existing_positions", False):
            return {
                "event": "startup_reconciliation",
                "symbol": symbol_name,
                "broker_open_positions": open_positions,
                "local_open_positions": 0,
                "status": "blocked",
                "severity": "CRITICAL",
                "reason": "broker_positions_require_manual_review",
            }
        return {
            "event": "startup_reconciliation",
            "symbol": symbol_name,
            "broker_open_positions": open_positions,
            "local_open_positions": 0,
            "status": "passed" if open_positions <= max_allowed else "blocked",
            "severity": "INFO" if open_positions <= max_allowed else "CRITICAL",
        }

    def _paper_order_record(self, decision, magic: int, run_id: str) -> dict[str, object]:
        order = self._order_request(decision, magic, run_id, "paper")
        return {
            "mode": "paper",
            "status": "PAPER_ACCEPTED",
            "symbol": order.symbol,
            "side": order.side.value,
            "order_type": order.order_type,
            "volume": order.volume,
            "stop_loss": order.stop_loss,
            "take_profit": order.take_profit,
            "magic": order.magic,
            "comment": order.comment,
        }

    def _order_request(self, decision, magic: int, run_id: str, mode: str) -> OrderRequest:
        if decision.stop_loss is None or decision.take_profit is None:
            raise RuntimeError("Approved realtime decisions must include stop_loss and take_profit")
        return OrderRequest(
            symbol=decision.symbol,
            side=decision.side,
            order_type=decision.entry_type or "MARKET",
            volume=decision.position_size,
            stop_loss=decision.stop_loss,
            take_profit=decision.take_profit,
            magic=magic,
            comment=f"algo_trade:{mode}:{run_id}",
        )


def _env_first(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None
