import tempfile
import unittest
from pathlib import Path

import pandas as pd

from algo_trade.backtest import BacktestEngine
from algo_trade.config import load_config
from algo_trade.execution import MT5ExecutionAdapter
from algo_trade.strategies import Strategy
from algo_trade.symbols import SymbolRegistry
from algo_trade.types import Signal, SignalSide, TradeState


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


if __name__ == "__main__":
    unittest.main()
