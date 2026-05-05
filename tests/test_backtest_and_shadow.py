import tempfile
import unittest
from pathlib import Path

import pandas as pd

from algo_trade.backtest import BacktestEngine
from algo_trade.config import load_config, validate_config, with_mode
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
    def __init__(self):
        self.orders: list[OrderRequest] = []
        self.shutdown_called = False

    def latest_bars(self, symbol: str, timeframe: str, count: int = 250, include_current: bool = False) -> pd.DataFrame:
        return load_sample().tail(count).reset_index(drop=True)

    def current_price(self, symbol: str, side: SignalSide) -> float:
        return 100.0

    def account_equity(self) -> float:
        return 10000.0

    def open_positions_count(self, symbol: str) -> int:
        return 0

    def is_market_open(self, symbol: str, max_tick_age_seconds: int = 1800) -> bool:
        return True

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
            config.raw["backtest"]["time_stop_bars"] = 3
            registry = SymbolRegistry.from_config(config.raw["symbols"])
            result = BacktestEngine(config, registry, AlwaysBuyStrategy()).run(load_sample(), "XAUUSDm")
            self.assertTrue((Path(result.run_dir) / "signals.jsonl").exists())
            self.assertTrue((Path(result.run_dir) / "decisions.jsonl").exists())
            self.assertTrue((Path(result.run_dir) / "trades.jsonl").exists())
            self.assertTrue((Path(result.run_dir) / "state.sqlite").exists())
            self.assertGreaterEqual(result.report.number_of_trades, 1)

    def test_same_bar_policy_is_conservative_sl_first(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = load_config("config/default.yaml")
            config.raw["paths"]["output_dir"] = temp_dir
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

    def test_live_mode_requires_send_orders_config_guard(self):
        raw = load_config("config/default.yaml").raw
        raw["mode"]["name"] = "live"
        with self.assertRaisesRegex(ValueError, "execution.send_orders=true"):
            validate_config(raw)


if __name__ == "__main__":
    unittest.main()
