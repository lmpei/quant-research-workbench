from __future__ import annotations

from datetime import datetime, timedelta
import os
from unittest.mock import patch
import unittest

from app.engine import run_backtest
from app.reporting import build_chat_request, generate_report, llm_runtime_status, read_llm_settings


def candle(ts: datetime, open_: float, high: float, low: float, close: float, volume: float = 10000) -> dict:
    return {
        "datetime": ts.isoformat(),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def demo_backtest() -> tuple[dict, dict]:
    start = datetime(2025, 1, 2, 15, 0)
    dataset = {
        "dataset_id": "ds_report_demo",
        "dataset_hash": "hash_report_demo",
        "name": "BYD_Daily_Demo",
        "symbol": "002594.SZ",
        "timeframe": "1d",
        "candles": [
            candle(start, 100, 101, 99.5, 100),
            candle(start + timedelta(days=1), 99, 99.3, 96.5, 97),
            candle(start + timedelta(days=2), 96.5, 101.5, 96, 101),
            candle(start + timedelta(days=3), 100.5, 102, 100, 101.2),
        ],
    }
    backtest = run_backtest(
        dataset,
        strategy_type="grid",
        backtest_config_payload={
            "initial_cash": 100000,
            "fee_rate": 0.0003,
            "slippage_rate": 0.0005,
            "lot_size": 100,
            "max_position_pct": 0.8,
            "risk_control_enabled": True,
            "execution_mode": "signal_on_close_fill_next_open",
            "benchmark_mode": "buy_and_hold",
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
    return dataset, backtest


class ReportingTests(unittest.TestCase):
    def test_chat_settings_have_priority(self) -> None:
        with patch.dict(
            os.environ,
            {
                "CHAT_PROVIDER": "qwen",
                "CHAT_API_KEY": "chat-key",
                "CHAT_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "CHAT_MODEL": "qwen-plus",
                "OPENAI_API_KEY": "openai-key",
            },
            clear=True,
        ):
            settings = read_llm_settings()

        self.assertIsNotNone(settings)
        self.assertEqual(settings["provider"], "qwen")
        self.assertEqual(settings["api_key"], "chat-key")
        self.assertEqual(settings["model"], "qwen-plus")
        self.assertIn("dashscope.aliyuncs.com", settings["base_url"])

    def test_chat_request_uses_chat_completions_contract(self) -> None:
        request = build_chat_request(
            "请输出一段中文报告。",
            {
                "provider": "qwen",
                "api_key": "chat-key",
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "model": "qwen-plus",
            },
        )

        self.assertTrue(request.full_url.endswith("/chat/completions"))
        self.assertEqual(request.headers["Authorization"], "Bearer chat-key")
        self.assertEqual(request.get_method(), "POST")

    def test_generate_report_without_keys_uses_rule_based_markdown(self) -> None:
        dataset, backtest = demo_backtest()
        with patch.dict(os.environ, {}, clear=True):
            report = generate_report(dataset, backtest, None)

        self.assertEqual(report["title"], "网格策略分析报告")
        self.assertIn("## 策略表现总结", report["raw_markdown"])
        self.assertIn("## 参数优化建议", report["raw_markdown"])
        self.assertTrue(report["structured_recommendations"]["market_regime_label"])
        self.assertGreaterEqual(len(report["next_experiments"]), 1)

    def test_llm_runtime_status_without_keys_uses_template(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            runtime = llm_runtime_status()

        self.assertEqual(runtime["source"], "template")
        self.assertEqual(runtime["provider_label"], "规则模板")

    def test_llm_runtime_status_prefers_chat_provider(self) -> None:
        with patch.dict(
            os.environ,
            {
                "CHAT_PROVIDER": "qwen",
                "CHAT_API_KEY": "chat-key",
                "CHAT_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "CHAT_MODEL": "qwen-plus",
            },
            clear=True,
        ):
            runtime = llm_runtime_status()

        self.assertEqual(runtime["source"], "qwen")
        self.assertEqual(runtime["provider_label"], "Qwen")
        self.assertEqual(runtime["model"], "qwen-plus")


if __name__ == "__main__":
    unittest.main()
