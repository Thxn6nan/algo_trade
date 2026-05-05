import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import pandas as pd

from algo_trade.audit import build_symbol_audit
from algo_trade.backtest import BacktestResult
from algo_trade.config import load_config, validate_config
from algo_trade.edge import _assess
from algo_trade.edge_report import write_edge_report
from algo_trade.features import FEATURE_SCHEMA, build_features, validate_feature_schema
from algo_trade.filters import SignalFilter
from algo_trade.reports import build_performance_report
from algo_trade.robustness import run_parameter_sweeps, run_robustness_suite
from algo_trade.strategies import get_strategy
from algo_trade.symbols import SymbolRegistry, SymbolSpec
from algo_trade.types import DecisionStatus, Signal, SignalSide, Trade, TradeState
from algo_trade.viability import build_strategy_viability
from algo_trade.walk_forward import build_walk_forward_splits


def symbol() -> SymbolSpec:
    return SymbolSpec(
        name="XAUUSDm",
        asset_class="metal",
        magic=7001,
        pip_size=0.01,
        pip_value=1.0,
        tick_size=0.01,
        tick_value=1.0,
        contract_size=100,
        min_lot=0.01,
        max_lot=1.0,
        lot_step=0.01,
        average_spread=18,
        trading_session="24x5",
        max_spread_points=280,
    )


def market_frame(periods: int = 40) -> pd.DataFrame:
    timestamps = pd.date_range("2026-01-05 00:00:00", periods=periods, freq="15min")
    closes = [100 + index * 0.2 for index in range(periods)]
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "symbol": ["XAUUSDm"] * periods,
            "timeframe": ["M15"] * periods,
            "open": closes,
            "high": [value + 0.5 for value in closes],
            "low": [value - 0.5 for value in closes],
            "close": [value + 0.1 for value in closes],
            "volume": [1000] * periods,
            "spread": [160, 160, 160, 280] * (periods // 4) + [160] * (periods % 4),
        }
    )
    frame.attrs["source_path"] = "data/XAUUSDm_M15.csv"
    frame.attrs["is_sample_data"] = False
    return frame


def closed_trade(r_multiple: float, net_pnl: float, session: str = "London") -> Trade:
    return Trade(
        trade_id=f"tr-{r_multiple}",
        symbol="XAUUSDm",
        side=SignalSide.BUY,
        entry_time=pd.Timestamp("2026-01-05 09:00").to_pydatetime(),
        entry_price=100.0,
        exit_time=pd.Timestamp("2026-01-05 10:00").to_pydatetime(),
        exit_price=101.0,
        position_size=0.01,
        stop_loss=99.0,
        take_profit=102.0,
        exit_reason=TradeState.POSITION_CLOSED_TP,
        gross_pnl=net_pnl,
        net_pnl=net_pnl,
        commission=0.0,
        spread_cost=0.0,
        slippage=0.0,
        r_multiple=r_multiple,
        holding_bars=4,
        model_version="none",
        config_hash="cfg",
        entry_session=session,
        entry_trend_regime="trend_up",
        entry_range_regime="expanding",
    )


class RealEdgeRoadmapTest(unittest.TestCase):
    def test_symbol_audit_flags_spread_config_mismatch_without_blocking_backtest(self):
        audit = build_symbol_audit(
            market_frame(),
            symbol(),
            timestamp_semantics="candle_open_time",
            broker_metadata=None,
        )

        self.assertEqual(audit.source_path, "data/XAUUSDm_M15.csv")
        self.assertEqual(audit.spread_percentiles["p50"], 160.0)
        self.assertEqual(audit.spread_by_session["rollover"]["p50"], 160.0)
        self.assertFalse(audit.broker_metadata_confirmed)
        self.assertIn("broker_metadata_unconfirmed", audit.promotion_blockers)
        self.assertIn("spread_config_mismatch", audit.promotion_blockers)

    def test_symbol_audit_requires_matching_broker_metadata_before_confirming(self):
        matching_metadata = {
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

        metadata_symbol = replace(symbol(), average_spread=160, tick_size=0.01, tick_value=1.0)

        confirmed = build_symbol_audit(
            market_frame(),
            metadata_symbol,
            timestamp_semantics="candle_open_time",
            broker_metadata=matching_metadata,
        )
        mismatched = build_symbol_audit(
            market_frame(),
            metadata_symbol,
            timestamp_semantics="candle_open_time",
            broker_metadata={**matching_metadata, "trade_tick_value": 10.0},
        )

        self.assertTrue(confirmed.broker_metadata_confirmed)
        self.assertNotIn("broker_metadata_unconfirmed", confirmed.promotion_blockers)
        self.assertFalse(mismatched.broker_metadata_confirmed)
        self.assertIn("broker_metadata_mismatch", mismatched.promotion_blockers)

    def test_strategy_viability_classifies_high_rejection_rate_as_invalid_configuration(self):
        signals = [
            Signal(
                timestamp=pd.Timestamp("2026-01-05").to_pydatetime(),
                symbol="XAUUSDm",
                side=SignalSide.BUY,
                confidence=0.7,
                expected_return=0.01,
                source="test",
                timeframe="M15",
            )
            for _ in range(100)
        ]
        decisions = [{"status": DecisionStatus.REJECTED.value, "side": SignalSide.BUY.value, "reasons": ["spread_too_high"]} for _ in range(98)]
        decisions.extend(
            [{"status": DecisionStatus.APPROVED.value, "side": SignalSide.BUY.value, "reasons": ["risk_sized"]} for _ in range(2)]
        )

        viability = build_strategy_viability(
            signals,
            decisions,
            {"min_raw_signals": 100, "min_approved_trades": 30, "max_rejection_rate": 0.95, "require_both_sides": False},
        )

        self.assertFalse(viability.passed)
        self.assertEqual(viability.raw_signals, 100)
        self.assertEqual(viability.approved_trades, 2)
        self.assertAlmostEqual(viability.rejection_rate, 0.98)
        self.assertEqual(viability.failure_class, "invalid_configuration")
        self.assertIn("rejection_rate_too_high", viability.reasons)

    def test_feature_schema_v2_contains_session_regime_and_spread_percentile_features(self):
        feature_frame = build_features(market_frame(240))
        validate_feature_schema(feature_frame)

        for column in [
            "session_label",
            "hour_of_day",
            "day_of_week",
            "atr_percentile",
            "realized_volatility_percentile",
            "trend_regime",
            "range_regime",
            "is_rollover",
            "spread_percentile_session",
        ]:
            self.assertIn(column, FEATURE_SCHEMA)
            self.assertIn(column, feature_frame.data.columns)
        self.assertEqual(feature_frame.feature_schema_version, "technical_v2")

    def test_filters_can_reject_rollover_and_high_session_spread_percentile(self):
        signal = Signal(
            timestamp=pd.Timestamp("2026-01-05").to_pydatetime(),
            symbol="XAUUSDm",
            side=SignalSide.BUY,
            confidence=0.8,
            expected_return=0.01,
            source="test",
            timeframe="M15",
            metadata={
                "atr": 1.0,
                "spread": 280,
                "session_label": "rollover",
                "spread_percentile_session": 0.99,
                "trend_regime": "trend_up",
                "range_regime": "expanding",
            },
        )

        result = SignalFilter(
            {"buy_threshold": 0.6, "sell_threshold": 0.6, "min_rr": 1.5},
            {"max_spread_multiplier": 5.0, "max_spread_percentile": 0.95},
            {"allowed_sessions": ["London", "NewYork"], "exclude_rollover": True},
            {"allowed_trend_regimes": ["trend_up", "trend_down"]},
        ).evaluate(signal, symbol(), rr=2.0)

        self.assertFalse(result.passed)
        self.assertIn("session_not_allowed", result.failed_reasons)
        self.assertIn("spread_percentile_too_high", result.failed_reasons)

    def test_rule_based_strategy_library_contains_new_candidates_and_disables_model_probability_by_default(self):
        row = build_features(market_frame(80)).data.iloc[-1].copy()
        row["session_label"] = "London"
        row["atr_percentile"] = 0.8
        row["realized_volatility_percentile"] = 0.8
        row["range_regime"] = "compressed"
        row["close"] = row["rolling_high"] + 1.0

        self.assertEqual(get_strategy("session_breakout").generate(row).source, "session_breakout")
        self.assertEqual(get_strategy("london_ny_volatility_breakout").generate(row).source, "london_ny_volatility_breakout")
        self.assertEqual(get_strategy("pullback_trend_continuation").name, "pullback_trend_continuation")
        self.assertEqual(get_strategy("range_mean_reversion").name, "range_mean_reversion")

        raw = load_config("config/default.yaml").raw
        raw["signal"]["strategy"] = "model_probability"
        with self.assertRaisesRegex(ValueError, "model_probability"):
            validate_config(raw)

    def test_random_baselines_are_active_enough_to_pass_default_confidence_filters(self):
        row = build_features(market_frame(80)).data.iloc[-1].copy()
        row["session_label"] = "London"

        random_strategy = get_strategy("random_entry")
        random_signals = [random_strategy.generate(row) for _ in range(12)]
        active_random = [signal for signal in random_signals if signal.side != SignalSide.HOLD]
        self.assertTrue(active_random)
        self.assertTrue(all(signal.confidence >= 0.60 for signal in active_random))
        self.assertNotEqual(get_strategy("frequency_matched_random").generate(row).side, SignalSide.HOLD)
        self.assertNotEqual(get_strategy("session_matched_random").generate(row).side, SignalSide.HOLD)
        self.assertNotEqual(get_strategy("direction_matched_random").generate(row).side, SignalSide.HOLD)

    def test_research_dev_walk_forward_split_blocks_promotion_pass(self):
        class ResearchDevWalkForward:
            rounds = [{"round": 1}]
            aggregate = {"positive_rounds": 1, "promotion_eligible": False}

            def to_record(self) -> dict[str, object]:
                return {"rounds": self.rounds, "aggregate": self.aggregate}

        config = load_config("config/default.yaml")
        config.raw["data"].update({"require_real_data": False, "min_bars": 1})
        config.raw["edge"].update(
            {
                "min_bars": 1,
                "min_trades": 1,
                "require_real_data": False,
                "require_beats_baselines": False,
                "require_stress_expectancy_positive": False,
                "require_walk_forward_positive": True,
                "require_robustness_positive": False,
            }
        )
        report = build_performance_report(
            [closed_trade(1.0, 100)],
            pd.Series([10000, 10100], index=pd.date_range("2026-01-01", periods=2, freq="D")),
            [],
            10000,
        )
        result = BacktestResult("bt-test", report, [closed_trade(1.0, 100)], pd.Series(dtype=float), Path("."))

        evidence = _assess(config, market_frame(), result, {}, {}, ResearchDevWalkForward(), None)

        self.assertEqual(evidence.verdict, "FAIL")
        self.assertIn("walk_forward_promotion_eligible", evidence.reasons)

    def test_walk_forward_splits_use_locked_test_windows(self):
        frame = pd.DataFrame({"timestamp": pd.date_range("2024-01-01", "2026-01-01", freq="D")})
        splits = build_walk_forward_splits(frame, train_months=12, validation_months=3, test_months=3, step_months=3)

        self.assertGreaterEqual(len(splits), 2)
        first = splits[0]
        self.assertEqual(first.train_start.date().isoformat(), "2024-01-01")
        self.assertEqual(first.validation_start.date().isoformat(), "2025-01-01")
        self.assertEqual(first.test_start.date().isoformat(), "2025-04-01")
        self.assertTrue(first.locked_test)

    def test_robustness_suite_reports_trade_dependency_without_requiring_backtest(self):
        summary = run_robustness_suite(
            trades=[closed_trade(2.0, 200), closed_trade(-1.0, -100), closed_trade(0.5, 50)],
            config={"remove_best_n": [1], "double_worst_n": [1], "monte_carlo_iterations": 25, "random_seed": 7},
        )

        self.assertIn("remove_best_1", summary.trade_dependency)
        self.assertIn("double_worst_1", summary.trade_dependency)
        self.assertEqual(summary.monte_carlo["iterations"], 25)

    def test_parameter_sweeps_are_rerun_based(self):
        config = load_config("config/default.yaml")
        config.raw["data"].update({"require_real_data": False, "min_bars": 1})
        config.raw["robustness"]["parameter_sweeps"] = {
            "signal.min_rr": [1.4, 1.6],
            "backtest.time_stop_bars": [12],
        }
        registry = SymbolRegistry.from_config(config.raw["symbols"])
        frame = market_frame(120)

        sweeps = run_parameter_sweeps(config, registry, frame, "XAUUSDm", get_strategy("pullback_trend_continuation"))

        self.assertIn("signal.min_rr=1.4", sweeps)
        self.assertIn("backtest.time_stop_bars=12", sweeps)
        self.assertIn("expectancy", sweeps["signal.min_rr=1.4"])

    def test_edge_report_writes_machine_and_human_readable_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report = build_performance_report(
                [closed_trade(1.0, 100), closed_trade(-0.5, -50)],
                pd.Series([10000, 10100, 10050], index=pd.date_range("2026-01-01", periods=3, freq="D")),
                ["spread_too_high"],
                10000,
            )
            payload = write_edge_report(
                Path(temp_dir),
                {
                    "run_id": "bt-test",
                    "data_quality": {"rows": 40, "missing_bars": 0},
                    "symbol_audit": {"promotion_blockers": []},
                    "strategy_viability": {"passed": True},
                    "edge_evidence": {"verdict": "FAIL", "failure_class": "no_edge"},
                    "baseline_comparison": {},
                    "performance": report.to_record(),
                    "trades": [closed_trade(1.0, 100).to_record()],
                    "walk_forward_summary": {},
                    "robustness_summary": {},
                    "promotion_gate": {"gate": "research_candidate", "passed": False},
                },
            )

            json_path = Path(temp_dir) / "edge_report.json"
            markdown_path = Path(temp_dir) / "edge_report.md"
            self.assertTrue(json_path.exists())
            self.assertTrue(markdown_path.exists())
            self.assertEqual(json.loads(json_path.read_text(encoding="utf-8"))["run_id"], "bt-test")
            self.assertIn("## Edge Verdict", markdown_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["session_regime_breakdown"]["by_session"]["London"]["trades"], 1)


if __name__ == "__main__":
    unittest.main()
