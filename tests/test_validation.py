import unittest

import pandas as pd

from algo_trade.validation import validate_ohlcv


def valid_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ["2026-01-01T00:00:00", "XAUUSDm", "M15", 100, 101, 99, 100.5, 1000, 18],
            ["2026-01-01T00:15:00", "XAUUSDm", "M15", 100.5, 101.5, 100, 101, 1000, 18],
            ["2026-01-01T00:30:00", "XAUUSDm", "M15", 101, 102, 100.5, 101.5, 1000, 18],
        ],
        columns=["timestamp", "symbol", "timeframe", "open", "high", "low", "close", "volume", "spread"],
    ).assign(timestamp=lambda frame: pd.to_datetime(frame["timestamp"]))


class DataValidationTest(unittest.TestCase):
    def test_valid_data_returns_quality_report(self):
        report = validate_ohlcv(valid_frame(), source="unit_test")
        self.assertEqual(report.duplicate_timestamps, 0)
        self.assertEqual(report.invalid_candles, 0)
        self.assertEqual(report.nan_count, 0)
        self.assertEqual(report.infinite_count, 0)
        self.assertEqual(report.source, "unit_test")
        self.assertEqual(report.validation_status, "passed")

    def test_missing_columns_fail(self):
        frame = valid_frame().drop(columns=["spread"])
        with self.assertRaisesRegex(ValueError, "Missing OHLCV columns"):
            validate_ohlcv(frame)

    def test_invalid_ohlc_fails(self):
        frame = valid_frame()
        frame.loc[0, "high"] = 98
        with self.assertRaisesRegex(ValueError, "Invalid candles"):
            validate_ohlcv(frame)

    def test_duplicate_timestamp_fails(self):
        frame = valid_frame()
        frame.loc[1, "timestamp"] = frame.loc[0, "timestamp"]
        with self.assertRaisesRegex(ValueError, "Duplicate timestamps"):
            validate_ohlcv(frame)

    def test_same_timestamp_across_symbols_is_allowed(self):
        frame = valid_frame()
        other = valid_frame()
        other["symbol"] = "EURUSDm"
        combined = pd.concat([frame, other], ignore_index=True)
        report = validate_ohlcv(combined)
        self.assertEqual(report.duplicate_timestamps, 0)
        self.assertEqual(report.symbol, "XAUUSDm,EURUSDm")

    def test_unsorted_timestamp_fails(self):
        frame = valid_frame().iloc[[1, 0, 2]].reset_index(drop=True)
        with self.assertRaisesRegex(ValueError, "sorted ascending"):
            validate_ohlcv(frame)

    def test_negative_spread_fails(self):
        frame = valid_frame()
        frame.loc[0, "spread"] = -1
        with self.assertRaisesRegex(ValueError, "Invalid candles"):
            validate_ohlcv(frame)

    def test_infinite_numeric_value_fails(self):
        frame = valid_frame()
        frame.loc[0, "close"] = float("inf")
        with self.assertRaisesRegex(ValueError, "infinite values"):
            validate_ohlcv(frame)

    def test_market_session_gap_can_be_allowed(self):
        frame = pd.DataFrame(
            [
                ["2026-01-02T23:45:00", "XAUUSDm", "M15", 100, 101, 99, 100.5, 1000, 18],
                ["2026-01-05T00:00:00", "XAUUSDm", "M15", 100.5, 101.5, 100, 101, 1000, 18],
                ["2026-01-05T00:15:00", "XAUUSDm", "M15", 101, 102, 100.5, 101.5, 1000, 18],
            ],
            columns=["timestamp", "symbol", "timeframe", "open", "high", "low", "close", "volume", "spread"],
        ).assign(timestamp=lambda data: pd.to_datetime(data["timestamp"]))

        with self.assertRaisesRegex(ValueError, "Missing bars"):
            validate_ohlcv(frame)

        report = validate_ohlcv(frame, allow_session_gaps=True)
        self.assertEqual(report.missing_bars, 0)

    def test_intraday_maintenance_gap_can_be_allowed(self):
        frame = pd.DataFrame(
            [
                ["2026-01-05T20:45:00", "XAUUSDm", "M15", 100, 101, 99, 100.5, 1000, 18],
                ["2026-01-05T22:00:00", "XAUUSDm", "M15", 100.5, 101.5, 100, 101, 1000, 18],
                ["2026-01-05T22:15:00", "XAUUSDm", "M15", 101, 102, 100.5, 101.5, 1000, 18],
            ],
            columns=["timestamp", "symbol", "timeframe", "open", "high", "low", "close", "volume", "spread"],
        ).assign(timestamp=lambda data: pd.to_datetime(data["timestamp"]))

        with self.assertRaisesRegex(ValueError, "Missing bars"):
            validate_ohlcv(frame)

        report = validate_ohlcv(frame, allow_session_gaps=True, max_session_gap_minutes=120)
        self.assertEqual(report.missing_bars, 0)


if __name__ == "__main__":
    unittest.main()
