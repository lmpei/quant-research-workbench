from __future__ import annotations

from datetime import datetime
import json
import os
from typing import Any
from urllib import error, request

from .domain import AIReportRecord, new_id, serialize


STRATEGY_LABELS = {
    "grid": "网格策略",
    "partial_t0": "部分仓位做T",
}

MARKET_REGIME_LABELS = {
    "range_bound": "震荡行情",
    "trend_up": "上行趋势",
    "trend_down": "下行趋势",
    "high_volatility": "高波动行情",
    "mixed": "混合行情",
}

RISK_LEVEL_LABELS = {
    "high": "高",
    "medium": "中",
    "low": "低",
}

ACTION_LABELS = {
    "increase": "提高",
    "decrease": "降低",
    "inspect": "参考",
}

PARAM_LABELS = {
    "base_price": "基准价",
    "grid_step_pct": "网格间距",
    "grid_levels": "网格层数",
    "order_amount": "单格金额",
    "max_position_pct": "最大仓位",
    "take_profit_pct": "止盈阈值",
    "stop_loss_pct": "止损阈值",
    "base_position_pct": "底仓比例",
    "active_position_pct": "机动仓比例",
    "buy_trigger_pct": "买入阈值",
    "sell_trigger_pct": "卖出阈值",
    "mean_revert_target_pct": "回归止盈",
    "reference_mode": "参考基线",
}

REFERENCE_MODE_LABELS = {
    "prev_close": "昨收",
    "moving_average": "均线",
    "intraday_vwap": "日内均价",
}

DEFAULT_DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"


def env_value(name: str) -> str | None:
    value = os.getenv(name)
    if not value:
        return None
    value = value.strip()
    return value or None


def strategy_label(strategy_type: str) -> str:
    return STRATEGY_LABELS.get(strategy_type, strategy_type)


def market_regime_label(value: str) -> str:
    return MARKET_REGIME_LABELS.get(value, value)


def risk_level_label(value: str) -> str:
    return RISK_LEVEL_LABELS.get(value, value)


def action_label(value: str) -> str:
    return ACTION_LABELS.get(value, value)


def param_label(key: str) -> str:
    return PARAM_LABELS.get(key, key)


def format_param_value(key: str, value: Any) -> str:
    if isinstance(value, list):
        return " / ".join(format_param_value(key, item) for item in value)
    if isinstance(value, float):
        if key.endswith("_pct") or key.endswith("_rate"):
            return f"{value:.2%}"
        return f"{value:.4f}".rstrip("0").rstrip(".")
    if isinstance(value, int):
        return str(value)
    if key == "reference_mode":
        return REFERENCE_MODE_LABELS.get(value, value)
    return str(value)


def format_param_snapshot(params: dict[str, Any]) -> str:
    return "；".join(f"{param_label(key)}：{format_param_value(key, value)}" for key, value in params.items())


def read_llm_settings() -> dict[str, str] | None:
    chat_api_key = env_value("CHAT_API_KEY")
    if chat_api_key:
        return {
            "provider": env_value("CHAT_PROVIDER") or "qwen",
            "api_key": chat_api_key,
            "base_url": (env_value("CHAT_BASE_URL") or DEFAULT_DASHSCOPE_BASE_URL).rstrip("/"),
            "model": env_value("CHAT_MODEL") or "qwen-plus",
        }
    openai_api_key = env_value("OPENAI_API_KEY")
    if openai_api_key:
        return {
            "provider": "openai",
            "api_key": openai_api_key,
            "base_url": (env_value("OPENAI_BASE_URL") or DEFAULT_OPENAI_BASE_URL).rstrip("/"),
            "model": env_value("OPENAI_MODEL") or "gpt-4.1-mini",
        }
    return None


def provider_label(settings: dict[str, str]) -> str:
    provider = settings.get("provider", "").lower()
    if provider == "qwen":
        return "Qwen"
    if provider == "openai":
        return "OpenAI"
    return settings.get("provider", "模型服务")


def infer_market_regime(backtest: dict[str, Any]) -> str:
    summary = backtest["summary"]
    benchmark_return = summary.get("benchmark_return") or 0
    max_drawdown = summary.get("max_drawdown") or 0
    turnover_ratio = summary.get("turnover_ratio") or 0
    if abs(benchmark_return) < 0.05 and turnover_ratio > 1.0:
        return "range_bound"
    if benchmark_return > 0.08 and max_drawdown < 0.12:
        return "trend_up"
    if benchmark_return < -0.08:
        return "trend_down"
    if max_drawdown > 0.18:
        return "high_volatility"
    return "mixed"


def build_risk_flags(backtest: dict[str, Any]) -> list[dict[str, str]]:
    summary = backtest["summary"]
    flags = []
    if summary["max_drawdown"] > 0.12:
        flags.append(
            {
                "level": "high",
                "level_label": risk_level_label("high"),
                "message": "最大回撤超过 12%，策略在样本期内的抗波动能力偏弱。",
            }
        )
    if summary["cost_ratio"] > 0.02:
        flags.append(
            {
                "level": "medium",
                "level_label": risk_level_label("medium"),
                "message": "交易成本占比偏高，频繁成交正在侵蚀策略边际收益。",
            }
        )
    if summary["turnover_ratio"] > 4:
        flags.append(
            {
                "level": "medium",
                "level_label": risk_level_label("medium"),
                "message": "换手率显著偏高，结果对成交语义和滑点假设较敏感。",
            }
        )
    if summary["win_rate"] < 0.45:
        flags.append(
            {
                "level": "medium",
                "level_label": risk_level_label("medium"),
                "message": "闭合交易对胜率低于 45%，收益可能依赖少量大额盈利交易。",
            }
        )
    if not flags:
        flags.append(
            {
                "level": "low",
                "level_label": risk_level_label("low"),
                "message": "主要风险指标未触发默认阈值，但结论仍只代表历史样本表现。",
            }
        )
    return flags


def build_param_changes(strategy_type: str, backtest: dict[str, Any], experiment: dict[str, Any] | None) -> list[dict[str, Any]]:
    summary = backtest["summary"]
    changes: list[dict[str, Any]] = []
    if strategy_type == "grid":
        if summary["cost_ratio"] > 0.02:
            changes.append(
                {
                    "parameter": "grid_step_pct",
                    "parameter_label": param_label("grid_step_pct"),
                    "action": "increase",
                    "action_label": action_label("increase"),
                    "reason": "适度放宽网格间距，减少无效高频成交带来的手续费拖累。",
                }
            )
        if summary["max_drawdown"] > 0.12:
            changes.append(
                {
                    "parameter": "max_position_pct",
                    "parameter_label": param_label("max_position_pct"),
                    "action": "decrease",
                    "action_label": action_label("decrease"),
                    "reason": "降低库存上限，有助于控制单边下跌行情中的回撤。",
                }
            )
        if summary["trade_count"] < 6:
            changes.append(
                {
                    "parameter": "grid_levels",
                    "parameter_label": param_label("grid_levels"),
                    "action": "increase",
                    "action_label": action_label("increase"),
                    "reason": "当前成交密度偏低，可适度增加层数提升震荡区间捕捉能力。",
                }
            )
    else:
        if summary["win_rate"] < 0.5:
            changes.append(
                {
                    "parameter": "buy_trigger_pct",
                    "parameter_label": param_label("buy_trigger_pct"),
                    "action": "increase",
                    "action_label": action_label("increase"),
                    "reason": "等待更深的回撤再加机动仓，有助于提高主动腿的入场质量。",
                }
            )
        if summary["cost_ratio"] > 0.015:
            changes.append(
                {
                    "parameter": "mean_revert_target_pct",
                    "parameter_label": param_label("mean_revert_target_pct"),
                    "action": "increase",
                    "action_label": action_label("increase"),
                    "reason": "适度提高回归止盈阈值，更容易覆盖 A 股双边成本。",
                }
            )
        if summary["max_drawdown"] > 0.1:
            changes.append(
                {
                    "parameter": "active_position_pct",
                    "parameter_label": param_label("active_position_pct"),
                    "action": "decrease",
                    "action_label": action_label("decrease"),
                    "reason": "减少机动仓比例，降低主动加仓对整体回撤的放大作用。",
                }
            )
    if experiment and experiment.get("runs"):
        best = experiment["runs"][0]
        changes.append(
            {
                "parameter": "best_run_reference",
                "parameter_label": "最佳组合参考",
                "action": "inspect",
                "action_label": action_label("inspect"),
                "reason": "可先将最新实验中的最佳组合回填为下一轮研究基线。",
                "value": best["params"],
            }
        )
    return changes


def build_recommended_sweeps(strategy_type: str, backtest: dict[str, Any], experiment: dict[str, Any] | None) -> list[dict[str, Any]]:
    params = backtest["strategy_params"]
    if strategy_type == "grid":
        step = float(params.get("grid_step_pct", 0.02))
        levels = int(params.get("grid_levels", 6))
        order_amount = float(params.get("order_amount", 5000))
        return [
            {
                "name": "grid_spacing_probe",
                "title": "网格间距探索",
                "parameters": {"grid_step_pct": [round(step * 0.8, 4), step, round(step * 1.2, 4)]},
                "reason": "验证更宽或更窄的网格间距，哪个更能在成本后保留收益。",
            },
            {
                "name": "inventory_probe",
                "title": "库存深度探索",
                "parameters": {
                    "grid_levels": [max(2, levels - 2), levels, levels + 2],
                    "order_amount": [max(1000, order_amount * 0.8), order_amount, order_amount * 1.2],
                },
                "reason": "比较库存深度与单格金额对换手率、回撤和净收益的影响。",
            },
        ]
    buy_trigger = float(params.get("buy_trigger_pct", 0.015))
    mean_revert_target = float(params.get("mean_revert_target_pct", 0.008))
    return [
        {
            "name": "entry_threshold_probe",
            "title": "入场阈值探索",
            "parameters": {"buy_trigger_pct": [round(buy_trigger * 0.8, 4), buy_trigger, round(buy_trigger * 1.2, 4)]},
            "reason": "比较更浅与更深的机动仓加仓阈值对胜率和成交频率的影响。",
        },
        {
            "name": "exit_probe",
            "title": "止盈阈值探索",
            "parameters": {
                "mean_revert_target_pct": [round(mean_revert_target * 0.8, 4), mean_revert_target, round(mean_revert_target * 1.25, 4)]
            },
            "reason": "平衡持有时长与交易成本，寻找更合理的回归止盈区间。",
        },
    ]


def build_rule_based_sections(
    dataset: dict[str, Any],
    backtest: dict[str, Any],
    experiment: dict[str, Any] | None,
) -> tuple[list[dict[str, str]], dict[str, Any], list[dict[str, Any]]]:
    summary = backtest["summary"]
    regime = infer_market_regime(backtest)
    risk_flags = build_risk_flags(backtest)
    param_changes = build_param_changes(backtest["strategy_type"], backtest, experiment)
    sweeps = build_recommended_sweeps(backtest["strategy_type"], backtest, experiment)
    best_run = experiment["runs"][0] if experiment and experiment.get("runs") else None
    worst_run = experiment["runs"][-1] if experiment and experiment.get("runs") else None
    strategy_name = strategy_label(backtest["strategy_type"])
    regime_name = market_regime_label(regime)
    sections = [
        {
            "title": "策略表现总结",
            "content": (
                f"{dataset['symbol']} 在样本区间内采用{strategy_name}后，总收益为 {summary['total_return']:.2%}，"
                f"最大回撤为 {summary['max_drawdown']:.2%}，闭合交易对胜率为 {summary['win_rate']:.2%}，"
                f"相对买入持有的超额收益为 {(summary.get('excess_return') or 0):.2%}。"
            ),
        },
        {
            "title": "风险与失效场景分析",
            "content": (
                f"当前样本更接近“{regime_name}”。成本占初始资金 {summary['cost_ratio']:.2%}，"
                f"换手率为 {summary['turnover_ratio']:.2f}。主要风险包括："
                f"{'；'.join(flag['message'] for flag in risk_flags)}"
            ),
        },
        {
            "title": "参数优化建议",
            "content": (
                "建议优先调整："
                + (
                    "；".join(
                        f"{item['parameter_label']}建议{item['action_label']}，原因是{item['reason']}"
                        for item in param_changes[:3]
                    )
                    if param_changes
                    else "当前参数可先作为下一轮实验基线。"
                )
            ),
        },
        {
            "title": "下一轮实验建议",
            "content": (
                f"建议直接执行 {len(sweeps)} 组结构化实验。"
                + (
                    f" 当前最佳组合为 {format_param_snapshot(best_run['params'])}；"
                    f"表现最弱的组合为 {format_param_snapshot(worst_run['params'])}。"
                    if best_run and worst_run
                    else ""
                )
            ),
        },
    ]
    structured = {
        "market_regime": regime,
        "market_regime_label": regime_name,
        "risk_flags": risk_flags,
        "recommended_param_changes": param_changes,
        "recommended_sweeps": sweeps,
    }
    return sections, structured, sweeps


def prompt_for_llm(dataset: dict[str, Any], backtest: dict[str, Any], experiment: dict[str, Any] | None) -> str:
    summary = backtest["summary"]
    payload = {
        "标的": dataset["symbol"],
        "数据集": dataset["name"],
        "周期": dataset["timeframe"],
        "策略": strategy_label(backtest["strategy_type"]),
        "参数": backtest["strategy_params"],
        "关键指标": summary,
        "最佳参数组合": experiment["runs"][0]["params"] if experiment and experiment.get("runs") else None,
        "最弱参数组合": experiment["runs"][-1]["params"] if experiment and experiment.get("runs") else None,
    }
    return (
        "你是一名克制、专业的量化研究助手。请基于给定的结构化回测数据，"
        "用中文 Markdown 输出恰好四个二级标题："
        "“策略表现总结”“风险与失效场景分析”“参数优化建议”“下一轮实验建议”。"
        "要求："
        "1. 必须引用输入中的具体指标；"
        "2. 不夸大收益，不输出任何实盘建议；"
        "3. 明确指出更适合震荡、趋势还是混合行情；"
        "4. 语言简洁，适合研究复盘。"
        f"输入数据：{json.dumps(payload, ensure_ascii=False)}"
    )


def build_chat_request(prompt: str, settings: dict[str, str]) -> request.Request:
    body = {
        "model": settings["model"],
        "messages": [
            {
                "role": "system",
                "content": "你是量化研究报告助手，只输出中文 Markdown，不要额外解释。",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "temperature": 0.35,
    }
    return request.Request(
        f"{settings['base_url']}/chat/completions",
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings['api_key']}",
        },
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
    )


def summarize_http_body(raw_body: str) -> str:
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        return raw_body.strip()[:200]
    if isinstance(payload, dict):
        for key in ("message", "detail", "error", "msg"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:200]
            if isinstance(value, dict) and isinstance(value.get("message"), str):
                return value["message"].strip()[:200]
    return raw_body.strip()[:200]


def compatible_chat_completions(prompt: str, settings: dict[str, str]) -> str:
    req = build_chat_request(prompt, settings)
    provider_name = provider_label(settings)
    try:
        with request.urlopen(req, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        detail = summarize_http_body(body)
        if exc.code in {401, 403}:
            raise RuntimeError(f"{provider_name} 鉴权失败，请检查 API Key 是否正确可用。") from exc
        if exc.code == 404:
            raise RuntimeError(
                f"{provider_name} 接口地址不可用，请确认基础地址为兼容模式地址，并使用 /chat/completions。"
            ) from exc
        raise RuntimeError(f"{provider_name} 调用失败（HTTP {exc.code}）：{detail or '上游返回异常。'}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"无法连接 {provider_name} 模型服务，请检查基础地址或当前网络环境。") from exc
    except TimeoutError as exc:
        raise RuntimeError(f"{provider_name} 模型服务响应超时，请稍后重试。") from exc
    except Exception as exc:
        raise RuntimeError(f"{provider_name} 模型服务调用失败：{str(exc)}") from exc

    choices = payload.get("choices", [])
    if not choices:
        raise RuntimeError(f"{provider_name} 返回结果为空，未生成报告内容。")
    message = choices[0].get("message", {})
    content = message.get("content")
    if isinstance(content, list):
        parts = [item.get("text", "") for item in content if isinstance(item, dict)]
        content = "".join(parts).strip()
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError(f"{provider_name} 返回内容格式异常，未提取到报告文本。")
    return content.strip()


def sections_to_markdown(sections: list[dict[str, str]]) -> str:
    lines = []
    for section in sections:
        lines.append(f"## {section['title']}")
        lines.append(section["content"])
        lines.append("")
    return "\n".join(lines).strip()


def generate_report(
    dataset: dict[str, Any],
    backtest: dict[str, Any],
    experiment: dict[str, Any] | None = None,
    report_type: str = "strategy_analysis",
) -> dict[str, Any]:
    sections, structured, next_experiments = build_rule_based_sections(dataset, backtest, experiment)
    settings = read_llm_settings()
    if settings:
        markdown = compatible_chat_completions(prompt_for_llm(dataset, backtest, experiment), settings)
    else:
        markdown = sections_to_markdown(sections)
    report = AIReportRecord(
        report_id=new_id("rp"),
        backtest_id=backtest.get("backtest_id"),
        experiment_id=experiment.get("experiment_id") if experiment else None,
        report_type=report_type,
        title=f"{strategy_label(backtest['strategy_type'])}分析报告",
        sections=sections,
        raw_markdown=markdown,
        structured_recommendations=structured,
        next_experiments=next_experiments,
        created_at=datetime.utcnow(),
    )
    return serialize(report)
