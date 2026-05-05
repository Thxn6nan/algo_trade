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
        report = validate_ohlcv(valid_frame())
        self.assertEqual(report.duplicate_timestamps, 0)
        self.assertEqual(report.invalid_candles, 0)

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

    def test_unsorted_timestamp_fails(self):
        frame = valid_frame().iloc[[1, 0, 2]].reset_index(drop=True)
        with self.assertRaisesRegex(ValueError, "sorted ascending"):
            validate_ohlcv(frame)

    def test_negative_spread_fails(self):
        frame = valid_frame()
        frame.loc[0, "spread"] = -1
        with self.assertRaisesRegex(ValueError, "Invalid candles"):
            validate_ohlcv(frame)


if __name__ == "__main__":
    unittest.main()
