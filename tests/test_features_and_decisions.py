import unittest

import pandas as pd

from algo_trade.decisions import DecisionEngine
from algo_trade.features import FeatureFrame, FEATURE_SCHEMA, build_features, validate_feature_schema
from algo_trade.filters import SignalFilter
from algo_trade.risk import RiskEngine
from algo_trade.symbols import SymbolSpec
from algo_trade.types import DecisionStatus, Signal, SignalSide


def symbol() -> SymbolSpec:
    return SymbolSpec(
        name="XAUUSDm",
        asset_class="metal",
        magic=7001,
        pip_size=0.01,
        pip_value=1.0,
        contract_size=100,
        min_lot=0.01,
        max_lot=1.0,
        lot_step=0.01,
        average_spread=18,
        trading_session="24x5",
    )


class FeatureAndDecisionTest(unittest.TestCase):
    def test_feature_schema_lock_rejects_wrong_order(self):
        data = pd.DataFrame({"a": [1.0], "b": [2.0]})
        feature_frame = FeatureFrame(data=data, feature_schema_version="x", schema=["b", "a"])
        with self.assertRaisesRegex(ValueError, "Feature schema mismatch"):
            validate_feature_schema(feature_frame, expected_schema=["a", "b"])

    def test_feature_pipeline_has_finite_rows(self):
        frame = pd.read_csv("data/sample_XAUUSDm_M15.csv")
        frame["timestamp"] = pd.to_datetime(frame["timestamp"])
        feature_frame = build_features(frame)
        self.assertEqual(feature_frame.schema, FEATURE_SCHEMA)
        validate_feature_schema(feature_frame)

    def test_approved_signal_requires_risk_layer(self):
        signal = Signal(
            timestamp=pd.Timestamp("2026-01-01").to_pydatetime(),
            symbol="XAUUSDm",
            side=SignalSide.BUY,
            confidence=0.8,
            expected_return=0.01,
            source="test",
            timeframe="M15",
            metadata={"atr": 1.0, "spread": 18},
        )
        decision = DecisionEngine(
            SignalFilter({"buy_threshold": 0.6, "sell_threshold": 0.6, "min_rr": 1.5}, {"max_spread_multiplier": 2.5}),
            RiskEngine({"risk_per_trade": 0.0025, "daily_loss_limit": 0.01, "max_drawdown": 0.5, "max_open_positions": 2, "max_lot": 0.10}, 10000),
            {"time_stop_bars": 24},
        ).decide(signal, symbol(), equity=10000, entry_price=100.0, open_positions=0)
        self.assertEqual(decision.status, DecisionStatus.APPROVED)
        self.assertIn("stop_loss_required", decision.reasons)
        self.assertGreater(decision.position_size, 0)

    def test_rejects_spread_and_low_rr(self):
        signal = Signal(
            timestamp=pd.Timestamp("2026-01-01").to_pydatetime(),
            symbol="XAUUSDm",
            side=SignalSide.BUY,
            confidence=0.8,
            expected_return=0.01,
            source="test",
            timeframe="M15",
            metadata={"atr": 1.0, "spread": 1000},
        )
        decision = DecisionEngine(
            SignalFilter({"buy_threshold": 0.6, "sell_threshold": 0.6, "min_rr": 3.0}, {"max_spread_multiplier": 2.5}),
            RiskEngine({"risk_per_trade": 0.0025, "daily_loss_limit": 0.01, "max_drawdown": 0.5, "max_open_positions": 2, "max_lot": 0.10}, 10000),
            {},
        ).decide(signal, symbol(), equity=10000, entry_price=100.0, open_positions=0)
        self.assertEqual(decision.status, DecisionStatus.REJECTED)
        self.assertIn("spread_too_high", decision.reasons)


if __name__ == "__main__":
    unittest.main()
