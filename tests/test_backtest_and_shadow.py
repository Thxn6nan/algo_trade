import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from algo_trade.backtest import BacktestEngine
from algo_trade.config import load_config, validate_config, with_mode
from algo_trade.data import HistoricalDataProvider, load_backtest_data
from algo_trade.edge import build_edge_evidence
from algo_trade.execution import MT5ExecutionAdapter
from algo_trade.realtime import RealtimeRunner
from algo_trade.strategies import Strategy
from algo_trade.symbols import SymbolRegistry
from algo_trade.types import OrderRequest, Signal, SignalSide, TradeState


class AlwaysBuyStrategy(Strategy):
    name = "always_buy"

    def generate(self, row: pd.Series) -> Signal:
        return Signal(
            timestamp=row["timestamp"].to_pydatetime(),
            symbol=row["symbol"],
            side=SignalSide.BUY,
            confidence=1.0,
            expected_return=0.01,
            source=self.name,
            timeframe=row["timeframe"],
            metadata={"atr": 1.0, "spread": 18},
        )


class FakeGateway:
    def __init__(self, open_positions: int = 0, market_open: bool = True):
        self.orders: list[OrderRequest] = []
        self.shutdown_called = False
        self.open_positions = open_positions
        self.market_open = market_open

    def latest_bars(self, symbol: str, timeframe: str, count: int = 250, include_current: bool = False) -> pd.DataFrame:
        return load_sample().tail(count).reset_index(drop=True)

    def symbol_metadata(self, symbol: str) -> dict[str, object]:
        return {
            "symbol": symbol,
            "point": 0.01,
            "digits": 2,
            "spread": 160,
            "tick_size": 0.01,
            "tick_value": 1.0,
            "contract_size": 100,
            "trade_tick_size": 0.01,
            "trade_tick_value": 1.0,
            "volume_min": 0.01,
            "volume_max": 1.0,
            "volume_step": 0.01,
        }

    def current_price(self, symbol: str, side: SignalSide) -> float:
        return 100.0

    def account_equity(self) -> float:
        return 10000.0

    def open_positions_count(self, symbol: str) -> int:
        return self.open_positions

    def is_market_open(self, symbol: str, max_tick_age_seconds: int = 1800) -> bool:
        return self.market_open

    def submit_order(self, order: OrderRequest) -> dict[str, object]:
        self.orders.append(order)
        return {"retcode": 10009, "order": 123}

    def shutdown(self) -> None:
        self.shutdown_called = True


def load_sample() -> pd.DataFrame:
    frame = pd.read_csv("data/sample_XAUUSDm_M15.csv")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    return frame


class BacktestAndShadowTest(unittest.TestCase):
    def test_backtest_generates_logs_and_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = load_config("config/default.yaml")
            config.raw["paths"]["output_dir"] = temp_dir
            config.raw["data"].update({"allow_sample_data": True, "require_real_data": False, "min_bars": 1})
            config.raw["backtest"]["time_stop_bars"] = 3
            registry = SymbolRegistry.from_config(config.raw["symbols"])
            result = BacktestEngine(config, registry, AlwaysBuyStrategy()).run(load_sample(), "XAUUSDm")
            self.assertTrue((Path(result.run_dir) / "signals.jsonl").exists())
            self.assertTrue((Path(result.run_dir) / "decisions.jsonl").exists())
            self.assertTrue((Path(result.run_dir) / "fills.jsonl").exists())
            self.assertTrue((Path(result.run_dir) / "positions.jsonl").exists())
            self.assertTrue((Path(result.run_dir) / "trades.jsonl").exists())
            self.assertTrue((Path(result.run_dir) / "state.sqlite").exists())
            self.assertGreaterEqual(result.report.number_of_trades, 1)
            signals = (Path(result.run_dir) / "signals.jsonl").read_text(encoding="utf-8").splitlines()
            decisions = (Path(result.run_dir) / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(signals), len(decisions))
            decision_record = json.loads(decisions[0])
            for key in ["run_id", "mode", "config_hash", "schema_version", "event_type", "severity", "decision_id", "signal_id"]:
                self.assertIn(key, decision_record)
            connection = sqlite3.connect(Path(result.run_dir) / "state.sqlite")
            try:
                tables = {
                    row[0]
                    for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
                }
            finally:
                connection.close()
            self.assertTrue({"fills", "reconciliation_events", "model_versions", "symbol_registry_snapshots"}.issubset(tables))

    def test_edge_evidence_fails_when_trade_count_is_not_enough(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = load_config("config/default.yaml")
            config.raw["paths"]["output_dir"] = temp_dir
            config.raw["data"].update({"allow_sample_data": True, "require_real_data": False, "min_bars": 1})
            config.raw["edge"].update(
                {
                    "min_bars": 1,
                    "min_trades": 999,
                    "require_real_data": False,
                    "require_beats_baselines": False,
                    "require_stress_expectancy_positive": False,
                    "baselines": [],
                    "stress_slippage_models": [],
                }
            )
            registry = SymbolRegistry.from_config(config.raw["symbols"])
            frame = load_sample()
            result = BacktestEngine(config, registry, AlwaysBuyStrategy()).run(frame, "XAUUSDm")
            evidence = build_edge_evidence(config, registry, frame, "XAUUSDm", AlwaysBuyStrategy(), result)
            self.assertEqual(evidence.verdict, "FAIL")
            self.assertIn("minimum_trades", evidence.reasons)
            self.assertTrue((Path(result.run_dir) / "edge_evidence.jsonl").exists())

    def test_same_bar_policy_is_conservative_sl_first(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = load_config("config/default.yaml")
            config.raw["paths"]["output_dir"] = temp_dir
            config.raw["data"].update({"allow_sample_data": True, "require_real_data": False, "min_bars": 1})
            registry = SymbolRegistry.from_config(config.raw["symbols"])
            frame = load_sample()
            frame.loc[2, "high"] = 103.0
            frame.loc[2, "low"] = 97.0
            result = BacktestEngine(config, registry, AlwaysBuyStrategy()).run(frame, "XAUUSDm")
            self.assertTrue(result.trades)
            self.assertEqual(result.trades[0].exit_reason, TradeState.POSITION_CLOSED_SL)

    def test_shadow_execution_adapter_cannot_submit_orders(self):
        adapter = MT5ExecutionAdapter(send_orders=False)
        with self.assertRaisesRegex(RuntimeError, "Order submission disabled"):
            adapter.submit_order(None)  # type: ignore[arg-type]

    def test_execution_adapter_sends_through_gateway_when_enabled(self):
        gateway = FakeGateway()
        adapter = MT5ExecutionAdapter(gateway=gateway, send_orders=True)
        response = adapter.submit_order(
            OrderRequest(
                symbol="XAUUSDm",
                side=SignalSide.BUY,
                order_type="MARKET",
                volume=0.01,
                stop_loss=99.0,
                take_profit=102.0,
                magic=7001,
                comment="test",
            )
        )
        self.assertEqual(response["retcode"], 10009)
        self.assertEqual(len(gateway.orders), 1)

    def test_sample_data_must_be_explicit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            shutil.copy("data/sample_XAUUSDm_M15.csv", Path(temp_dir) / "sample_XAUUSDm_M15.csv")
            provider = HistoricalDataProvider(temp_dir)
            with self.assertRaisesRegex(FileNotFoundError, "sample fixture exists"):
                provider.load("XAUUSDm", "M15")
            frame = provider.load("XAUUSDm", "M15", allow_sample_data=True)
            self.assertTrue(frame.attrs["is_sample_data"])

    def test_missing_data_backfills_from_gateway(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = load_config("config/default.yaml")
            config.raw["paths"]["data_dir"] = temp_dir
            config.raw["data"].update(
                {
                    "allow_sample_data": False,
                    "require_real_data": True,
                    "auto_fetch_latest": True,
                    "min_bars": 10,
                    "backfill_bars": 10,
                }
            )
            gateway = FakeGateway()
            frame = load_backtest_data(config, "XAUUSDm", "M15", gateway=gateway)
            self.assertEqual(len(frame), 10)
            self.assertFalse(frame.attrs["is_sample_data"])
            self.assertTrue((Path(temp_dir) / "XAUUSDm_M15.csv").exists())
            self.assertTrue(gateway.shutdown_called)

    def test_backtest_data_attaches_broker_symbol_metadata_from_gateway(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            shutil.copy("data/sample_XAUUSDm_M15.csv", Path(temp_dir) / "XAUUSDm_M15.csv")
            config = load_config("config/default.yaml")
            config.raw["paths"]["data_dir"] = temp_dir
            config.raw["data"].update(
                {
                    "allow_sample_data": False,
                    "require_real_data": True,
                    "auto_fetch_latest": False,
                    "min_bars": 10,
                }
            )
            frame = load_backtest_data(config, "XAUUSDm", "M15", gateway=FakeGateway())

            self.assertEqual(frame.attrs["broker_metadata"]["trade_tick_value"], 1.0)

    def test_backtest_persists_broker_symbol_metadata_snapshot(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = load_config("config/default.yaml")
            config.raw["paths"]["output_dir"] = temp_dir
            config.raw["data"].update({"allow_sample_data": True, "require_real_data": False, "min_bars": 1})
            registry = SymbolRegistry.from_config(config.raw["symbols"])
            frame = load_sample()
            frame.attrs["broker_metadata"] = FakeGateway().symbol_metadata("XAUUSDm")

            result = BacktestEngine(config, registry, AlwaysBuyStrategy()).run(frame, "XAUUSDm")

            snapshot_path = Path(result.run_dir) / "broker_symbol_metadata.json"
            self.assertTrue(snapshot_path.exists())
            self.assertTrue(result.symbol_audit.broker_metadata_confirmed)
            self.assertEqual(json.loads(snapshot_path.read_text(encoding="utf-8"))["symbol"], "XAUUSDm")

    def test_paper_mode_records_real_data_decision_without_sending_order(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = with_mode(load_config("config/default.yaml"), "paper")
            config.raw["paths"]["output_dir"] = temp_dir
            registry = SymbolRegistry.from_config(config.raw["symbols"])
            gateway = FakeGateway()
            result = RealtimeRunner(config, registry, AlwaysBuyStrategy(), gateway).run_once("XAUUSDm", "M15")
            self.assertEqual(result.mode, "paper")
            self.assertEqual(result.order_action, "paper_recorded")
            self.assertEqual(len(gateway.orders), 0)
            self.assertTrue(gateway.shutdown_called)
            self.assertTrue((Path(result.run_dir) / "orders.jsonl").exists())
            self.assertTrue((Path(result.run_dir) / "reconciliation.jsonl").exists())

    def test_live_mode_requires_send_orders_config_guard(self):
        raw = load_config("config/default.yaml").raw
        raw["mode"]["name"] = "live"
        with self.assertRaisesRegex(ValueError, "execution.send_orders=true"):
            validate_config(raw)

    def test_live_mode_rejects_account_mismatch_before_gateway_work(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "SYSTEM_MODE=live\nACCOUNT_ID=111\nACCOUNT_PASSWORD=x\nSERVER_NAME=Demo\n",
                encoding="utf-8",
            )
            config = load_config("config/default.yaml")
            config.raw["mode"]["name"] = "live"
            config.raw["paths"]["output_dir"] = temp_dir
            config.raw["execution"].update(
                {
                    "env_path": str(env_path),
                    "send_orders": True,
                    "live_enabled": True,
                    "confirm_live": "I_UNDERSTAND_LIVE_TRADING_RISK",
                }
            )
            config.raw["account"]["expected_account_id"] = 222
            config.raw["account"]["expected_server"] = "Demo"
            registry = SymbolRegistry.from_config(config.raw["symbols"])
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(RuntimeError, "account ID does not match"):
                    RealtimeRunner(config, registry, AlwaysBuyStrategy(), FakeGateway()).run_once("XAUUSDm", "M15")

    def test_live_mode_halts_when_broker_positions_need_reconciliation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "SYSTEM_MODE=live\nACCOUNT_ID=111\nACCOUNT_PASSWORD=x\nSERVER_NAME=Demo\n",
                encoding="utf-8",
            )
            config = load_config("config/default.yaml")
            config.raw["mode"]["name"] = "live"
            config.raw["paths"]["output_dir"] = temp_dir
            config.raw["execution"].update(
                {
                    "env_path": str(env_path),
                    "send_orders": True,
                    "live_enabled": True,
                    "confirm_live": "I_UNDERSTAND_LIVE_TRADING_RISK",
                    "allow_existing_positions": False,
                }
            )
            config.raw["account"]["expected_account_id"] = 111
            config.raw["account"]["expected_server"] = "Demo"
            registry = SymbolRegistry.from_config(config.raw["symbols"])
            with patch.dict(os.environ, {}, clear=True):
                result = RealtimeRunner(config, registry, AlwaysBuyStrategy(), FakeGateway(open_positions=1)).run_once("XAUUSDm", "M15")
            self.assertEqual(result.decision_status, "HALTED")
            self.assertEqual(result.order_action, "reconciliation_halt")
            reconciliation = Path(result.run_dir) / "reconciliation.jsonl"
            self.assertTrue(reconciliation.exists())
            self.assertIn("broker_positions_require_manual_review", reconciliation.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
