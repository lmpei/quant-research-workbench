from __future__ import annotations

from datetime import datetime, timedelta
import unittest

from app.datasets import validate_candles
from app.domain import Candle
from app.engine import run_backtest


def candle(ts: datetime, open_: float, high: float, low: float, close: float, volume: float = 10000) -> dict:
    return {
        "datetime": ts.isoformat(),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


class EngineTests(unittest.TestCase):
    def test_validate_daily_requires_adjustment(self) -> None:
        candles = [
            Candle(datetime=datetime(2025, 1, 2), open=10, high=11, low=9.8, close=10.5, volume=1000),
            Candle(datetime=datetime(2025, 1, 3), open=10.4, high=11.1, low=10.1, close=10.9, volume=1200),
        ]
        report = validate_candles(candles, "1d", None)
        self.assertEqual(report["status"], "invalid")
        self.assertTrue(any("adjustment" in message for message in report["errors"]))

    def test_grid_backtest_respects_lot_size(self) -> None:
        start = datetime(2025, 1, 2, 15, 0)
        dataset = {
            "dataset_id": "ds_test_grid",
            "dataset_hash": "hash_grid",
            "timeframe": "1d",
            "candles": [
                candle(start, 100, 101, 99.5, 100),
                candle(start + timedelta(days=1), 99, 99.3, 96.5, 97),
                candle(start + timedelta(days=2), 96.5, 101.5, 96, 101),
                candle(start + timedelta(days=3), 100.5, 102, 100, 101.2),
            ],
        }
        result = run_backtest(
            dataset,
            strategy_type="grid",
            backtest_config_payload={
                "initial_cash": 100000,
                "fee_rate": 0.0003,
                "slippage_rate": 0.0005,
                "lot_size": 100,
                "max_position_pct": 0.8,
                "risk_control_enabled": True,
            },
            strategy_params={
                "base_price": 100,
                "grid_step_pct": 0.01,
                "grid_levels": 4,
                "order_amount": 20000,
                "max_position_pct": 0.8,
                "take_profit_pct": 0.2,
                "stop_loss_pct": 0.2,
            },
        )
        self.assertGreaterEqual(len(result["trades"]), 1)
        self.assertTrue(all(trade["quantity"] % 100 == 0 for trade in result["trades"]))
        self.assertEqual(len(result["timeseries"]["benchmark_curve"]), 4)

    def test_partial_t0_rejects_daily_dataset(self) -> None:
        start = datetime(2025, 1, 2, 15, 0)
        dataset = {
            "dataset_id": "ds_test_t0_daily",
            "dataset_hash": "hash_t0_daily",
            "timeframe": "1d",
            "candles": [
                candle(start, 100, 101, 99.5, 100),
                candle(start + timedelta(days=1), 99.2, 100.1, 98.6, 99.6),
                candle(start + timedelta(days=2), 99.8, 101.2, 99.1, 100.7),
            ],
        }
        with self.assertRaises(ValueError):
            run_backtest(
                dataset,
                strategy_type="partial_t0",
                backtest_config_payload={
                    "initial_cash": 100000,
                    "fee_rate": 0.0003,
                    "slippage_rate": 0.0005,
                    "lot_size": 100,
                    "max_position_pct": 1.0,
                },
                strategy_params={
                    "base_position_pct": 0.7,
                    "active_position_pct": 0.3,
                    "buy_trigger_pct": 0.015,
                    "sell_trigger_pct": 0.015,
                    "mean_revert_target_pct": 0.008,
                    "stop_loss_pct": 0.02,
                    "reference_mode": "prev_close",
                },
            )

    def test_partial_t0_active_inventory_cannot_sell_same_day(self) -> None:
        start = datetime(2025, 1, 2, 9, 45)
        dataset = {
            "dataset_id": "ds_test_t0",
            "dataset_hash": "hash_t0",
            "timeframe": "15m",
            "candles": [
                candle(start, 100, 101, 99.5, 100),
                candle(start + timedelta(minutes=15), 99, 99.5, 96.5, 97),
                candle(start + timedelta(minutes=30), 96, 103, 95.8, 102),
                candle(start + timedelta(days=1), 101, 104, 100.5, 103),
                candle(start + timedelta(days=1, minutes=15), 103, 104.5, 102.6, 104),
            ],
        }
        result = run_backtest(
            dataset,
            strategy_type="partial_t0",
            backtest_config_payload={
                "initial_cash": 100000,
                "fee_rate": 0.0003,
                "slippage_rate": 0.0005,
                "lot_size": 100,
                "max_position_pct": 1.0,
            },
            strategy_params={
                "base_position_pct": 0.7,
                "active_position_pct": 0.3,
                "buy_trigger_pct": 0.015,
                "sell_trigger_pct": 0.015,
                "mean_revert_target_pct": 0.008,
                "stop_loss_pct": 0.02,
                "reference_mode": "prev_close",
            },
        )
        reasons = [trade["reason"] for trade in result["trades"]]
        self.assertIn("initial_base_position", reasons)
        self.assertIn("active_deviation_buy", reasons)
        self.assertTrue(
            any(reason in {"active_deviation_sell", "active_mean_revert_take_profit"} for reason in reasons)
        )
        buy_trade = next(trade for trade in result["trades"] if trade["reason"] == "active_deviation_buy")
        sell_trade = next(
            trade
            for trade in result["trades"]
            if trade["reason"] in {"active_deviation_sell", "active_mean_revert_take_profit"}
        )
        self.assertGreater(
            datetime.fromisoformat(sell_trade["datetime"]).date(),
            datetime.fromisoformat(buy_trade["datetime"]).date(),
        )
        self.assertGreater(sell_trade["tax"], 0)


if __name__ == "__main__":
    unittest.main()
