from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


SUPPORTED_MODES = {"research", "backtest", "walk_forward", "shadow", "paper", "micro_live", "live"}
LIVE_CAPABLE_MODES = {"micro_live", "live"}
RULE_BASED_STRATEGIES = {
    "buy_and_hold",
    "no_trade",
    "random_entry",
    "ma_crossover",
    "rsi_mean_reversion",
    "atr_breakout",
    "session_breakout",
    "london_ny_volatility_breakout",
    "pullback_trend_continuation",
    "range_mean_reversion",
}


@dataclass(frozen=True)
class AppConfig:
    raw: dict[str, Any]
    path: Path
    config_hash: str

    @property
    def mode(self) -> str:
        return self.raw["mode"]["name"]

    @property
    def enabled_symbols(self) -> list[str]:
        return list(self.raw["symbols"]["enabled"])

    @property
    def output_dir(self) -> Path:
        return Path(self.raw.get("paths", {}).get("output_dir", "runs"))

    @property
    def data_dir(self) -> Path:
        return Path(self.raw.get("paths", {}).get("data_dir", "data"))


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    validate_config(raw)
    return AppConfig(raw=raw, path=config_path, config_hash=hash_config(raw))


def with_mode(config: AppConfig, mode: str) -> AppConfig:
    raw = deepcopy(config.raw)
    raw.setdefault("mode", {})["name"] = mode
    validate_config(raw)
    return AppConfig(raw=raw, path=config.path, config_hash=hash_config(raw))


def validate_config(raw: dict[str, Any]) -> None:
    required_groups = ["mode", "account", "symbols", "data", "risk", "signal", "backtest", "shadow", "execution", "real_data"]
    missing = [group for group in required_groups if group not in raw]
    if missing:
        raise ValueError(f"Missing config groups: {missing}")

    mode = raw["mode"].get("name")
    if mode not in SUPPORTED_MODES:
        raise ValueError(f"Unsupported mode {mode!r}")

    if raw["shadow"].get("send_orders") is not False:
        raise ValueError("shadow.send_orders must be false")

    execution = raw["execution"]
    if mode == "paper" and execution.get("send_orders") is not False:
        raise ValueError("paper mode requires execution.send_orders=false")
    if mode in LIVE_CAPABLE_MODES and execution.get("send_orders") is not True:
        raise ValueError("live-capable mode requires execution.send_orders=true")

    enabled = raw["symbols"].get("enabled") or []
    registry = raw["symbols"].get("registry") or {}
    unknown = [symbol for symbol in enabled if symbol not in registry]
    if unknown:
        raise ValueError(f"Enabled symbols missing from registry: {unknown}")

    risk = raw["risk"]
    for key in ["risk_per_trade", "daily_loss_limit", "max_open_positions", "max_lot"]:
        if key not in risk:
            raise ValueError(f"Missing risk.{key}")
    if not 0 <= float(risk["risk_per_trade"]) <= 0.01:
        raise ValueError("risk.risk_per_trade must be between 0 and 1%")
    if mode in LIVE_CAPABLE_MODES:
        if float(risk["risk_per_trade"]) > 0.0025:
            raise ValueError("live-capable modes require risk.risk_per_trade <= 0.25%")
        if float(risk["daily_loss_limit"]) > 0.01:
            raise ValueError("live-capable modes require risk.daily_loss_limit <= 1%")
        account = raw["account"]
        if not account.get("expected_account_id") or not account.get("expected_server"):
            raise ValueError("live-capable modes require account.expected_account_id and account.expected_server")

    if raw["backtest"].get("execute_signal_at") != "next_open":
        raise ValueError("Only next_open execution is supported to prevent lookahead")
    if raw["backtest"].get("same_bar_policy") != "conservative":
        raise ValueError("Only conservative same-bar policy is supported initially")

    strategy = raw["signal"].get("strategy", "atr_breakout")
    rule_based_only = bool(raw.get("strategy_library", {}).get("rule_based_only", True))
    if rule_based_only and strategy not in RULE_BASED_STRATEGIES:
        raise ValueError(f"Strategy {strategy!r} is not allowed when strategy_library.rule_based_only=true; model_probability is disabled")


def hash_config(raw: dict[str, Any]) -> str:
    encoded = json.dumps(raw, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]
