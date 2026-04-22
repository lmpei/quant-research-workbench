from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timedelta
from typing import Any
import uuid


ENGINE_VERSION = "v1.0.0"
DEFAULT_EXECUTION_MODE = "signal_on_close_fill_next_open"
DEFAULT_BENCHMARK_MODE = "buy_and_hold"
CN_A_SHARE = "CN_A_SHARE"
CN_A_SHARE_TIMEZONE = "Asia/Shanghai"
CN_A_SHARE_SESSION = "09:30-11:30,13:00-15:00"
SELL_STAMP_DUTY_RATE = 0.001
REQUIRED_COLUMNS = ("datetime", "open", "high", "low", "close", "volume")
SUPPORTED_TIMEFRAMES = {
    "1d": timedelta(days=1),
    "15m": timedelta(minutes=15),
    "1m": timedelta(minutes=1),
}
STRATEGY_TIMEFRAME_MATRIX = {
    "grid": {"1d", "15m", "1m"},
    "partial_t0": {"15m", "1m"},
}


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def serialize(value: Any) -> Any:
    if is_dataclass(value):
        return {key: serialize(item) for key, item in asdict(value).items()}
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: serialize(item) for key, item in value.items()}
    return value


@dataclass(slots=True)
class Candle:
    datetime: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def trade_date(self) -> str:
        return self.datetime.date().isoformat()


@dataclass(slots=True)
class DatasetRecord:
    dataset_id: str
    name: str
    symbol: str
    timeframe: str
    source_type: str
    rows: int
    start_at: datetime
    end_at: datetime
    created_at: datetime
    market: str = CN_A_SHARE
    timezone: str = CN_A_SHARE_TIMEZONE
    session: str = CN_A_SHARE_SESSION
    adjustment: str | None = None
    dataset_hash: str = ""
    validation_status: str = "valid"
    validation_report: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BacktestConfig:
    initial_cash: float
    fee_rate: float
    slippage_rate: float
    lot_size: int
    max_position_pct: float
    risk_control_enabled: bool = False
    allow_empty_position: bool = True
    execution_mode: str = DEFAULT_EXECUTION_MODE
    benchmark_mode: str = DEFAULT_BENCHMARK_MODE


@dataclass(slots=True)
class TradeRecord:
    trade_id: str
    backtest_id: str
    datetime: datetime
    side: str
    price: float
    quantity: int
    amount: float
    fee: float
    slippage_cost: float
    tax: float
    cash_after: float
    position_after: int
    nav_after: float
    reason: str


@dataclass(slots=True)
class RoundTrip:
    entry_datetime: datetime
    exit_datetime: datetime
    quantity: int
    entry_price: float
    exit_price: float
    pnl: float
    return_pct: float
    holding_days: int


@dataclass(slots=True)
class EquityPoint:
    datetime: datetime
    nav: float
    cash: float
    position_value: float
    position_pct: float
    drawdown: float
    benchmark_nav: float | None = None


@dataclass(slots=True)
class BacktestSummary:
    backtest_id: str
    dataset_id: str
    strategy_type: str
    total_return: float
    annualized_return: float | None
    max_drawdown: float
    win_rate: float
    profit_loss_ratio: float
    trade_count: int
    fees_paid: float
    final_nav: float
    benchmark_return: float | None
    excess_return: float | None
    exposure_ratio: float
    turnover_ratio: float
    cost_ratio: float
    round_trip_win_rate: float
    created_at: datetime


@dataclass(slots=True)
class BacktestResult:
    backtest_id: str
    dataset_id: str
    dataset_hash: str
    strategy_type: str
    strategy_version: str
    engine_version: str
    backtest_config: dict[str, Any]
    strategy_params: dict[str, Any]
    summary: BacktestSummary
    equity_points: list[EquityPoint]
    benchmark_curve: list[dict[str, Any]]
    trades: list[TradeRecord]
    round_trips: list[RoundTrip]
    cost_breakdown: dict[str, float]
    execution_mode: str
    benchmark_mode: str
    created_at: datetime


@dataclass(slots=True)
class ExperimentRun:
    run_id: str
    params: dict[str, Any]
    summary: dict[str, Any]


@dataclass(slots=True)
class ExperimentRecord:
    experiment_id: str
    dataset_id: str
    dataset_hash: str
    strategy_type: str
    ranking_metric: str
    ranking_formula: str
    total_runs: int
    created_at: datetime
    engine_version: str
    strategy_version: str
    backtest_config: dict[str, Any]
    base_strategy_params: dict[str, Any]
    param_grid: dict[str, list[Any]]
    runs: list[ExperimentRun]


@dataclass(slots=True)
class AIReportRecord:
    report_id: str
    backtest_id: str | None
    experiment_id: str | None
    report_type: str
    title: str
    sections: list[dict[str, str]]
    raw_markdown: str
    structured_recommendations: dict[str, Any]
    next_experiments: list[dict[str, Any]]
    created_at: datetime
