from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import itertools
import math
import statistics
from typing import Any

from .domain import (
    BacktestConfig,
    BacktestResult,
    BacktestSummary,
    Candle,
    EquityPoint,
    ExperimentRecord,
    ExperimentRun,
    RoundTrip,
    TradeRecord,
    SELL_STAMP_DUTY_RATE,
    STRATEGY_TIMEFRAME_MATRIX,
    ENGINE_VERSION,
    new_id,
    serialize,
)


GRID_STRATEGY_VERSION = "grid_v1"
PARTIAL_T0_STRATEGY_VERSION = "partial_t0_v1"
DEFAULT_RANKING_FORMULA = "score = total_return*50 + win_rate*20 - max_drawdown*20 - turnover_ratio*10"


class SimulationState:
    def __init__(self, backtest_id: str, config: BacktestConfig) -> None:
        self.backtest_id = backtest_id
        self.config = config
        self.cash = config.initial_cash
        self.shares = 0
        self.available_shares = 0
        self.locked_by_trade_date: dict[str, int] = {}
        self.current_trade_date: str | None = None
        self.trades: list[TradeRecord] = []
        self.equity_points: list[EquityPoint] = []
        self.total_fees = 0.0
        self.total_taxes = 0.0
        self.total_slippage_cost = 0.0
        self.total_trade_amount = 0.0
        self.halt_reason: str | None = None

    def release_shares(self, trade_date: str) -> None:
        if self.current_trade_date == trade_date:
            return
        releasable_dates = [day for day in self.locked_by_trade_date if day < trade_date]
        for day in releasable_dates:
            self.available_shares += self.locked_by_trade_date.pop(day)
        self.current_trade_date = trade_date


def normalize_shares(target_shares: float, lot_size: int) -> int:
    if lot_size <= 0:
        raise ValueError("lot_size must be positive")
    return max(0, int(target_shares // lot_size) * lot_size)


def load_candles(dataset_payload: dict[str, Any]) -> list[Candle]:
    candles = []
    for row in dataset_payload["candles"]:
        candles.append(
            Candle(
                datetime=datetime.fromisoformat(row["datetime"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            )
        )
    return candles


def ensure_strategy_supported(strategy_type: str, timeframe: str) -> None:
    supported = STRATEGY_TIMEFRAME_MATRIX.get(strategy_type)
    if not supported:
        raise ValueError(f"Unknown strategy type: {strategy_type}")
    if timeframe not in supported:
        raise ValueError(
            f"Strategy '{strategy_type}' does not support timeframe '{timeframe}'. "
            f"Supported: {', '.join(sorted(supported))}"
        )


def build_backtest_config(payload: dict[str, Any]) -> BacktestConfig:
    return BacktestConfig(
        initial_cash=float(payload.get("initial_cash", 100000)),
        fee_rate=float(payload.get("fee_rate", 0.0003)),
        slippage_rate=float(payload.get("slippage_rate", 0.0005)),
        lot_size=int(payload.get("lot_size", 100)),
        max_position_pct=float(payload.get("max_position_pct", 1.0)),
        risk_control_enabled=bool(payload.get("risk_control_enabled", False)),
        allow_empty_position=bool(payload.get("allow_empty_position", True)),
        execution_mode=payload.get("execution_mode", "signal_on_close_fill_next_open"),
        benchmark_mode=payload.get("benchmark_mode", "buy_and_hold"),
    )


def benchmark_curve(candles: list[Candle], config: BacktestConfig) -> tuple[list[dict[str, Any]], float]:
    if not candles:
        return [], 0.0
    entry_price = candles[0].open * (1 + config.slippage_rate)
    shares = normalize_shares(config.initial_cash / entry_price, config.lot_size)
    if shares <= 0:
        curve = [{"datetime": candle.datetime.isoformat(), "value": config.initial_cash} for candle in candles]
        return curve, 0.0
    amount = shares * entry_price
    fee = amount * config.fee_rate
    cash_left = config.initial_cash - amount - fee
    curve = []
    for candle in candles:
        curve.append(
            {
                "datetime": candle.datetime.isoformat(),
                "value": round(cash_left + shares * candle.close, 4),
            }
        )
    benchmark_return = curve[-1]["value"] / config.initial_cash - 1
    return curve, benchmark_return


def execute_order(
    state: SimulationState,
    *,
    candle: Candle,
    side: str,
    quantity: int,
    reason: str,
    available_immediately: bool = False,
) -> TradeRecord | None:
    if quantity <= 0:
        return None
    if side == "buy":
        execution_price = candle.open * (1 + state.config.slippage_rate)
        quantity = normalize_shares(quantity, state.config.lot_size)
        if quantity <= 0:
            return None
        total_amount = execution_price * quantity
        fee = total_amount * state.config.fee_rate
        max_affordable = normalize_shares(state.cash / (execution_price * (1 + state.config.fee_rate)), state.config.lot_size)
        quantity = min(quantity, max_affordable)
        if quantity <= 0:
            return None
        total_amount = execution_price * quantity
        fee = total_amount * state.config.fee_rate
        state.cash -= total_amount + fee
        state.shares += quantity
        if available_immediately:
            state.available_shares += quantity
        else:
            state.locked_by_trade_date[candle.trade_date] = state.locked_by_trade_date.get(candle.trade_date, 0) + quantity
        tax = 0.0
        slippage_cost = (execution_price - candle.open) * quantity
    else:
        execution_price = candle.open * (1 - state.config.slippage_rate)
        quantity = min(quantity, state.available_shares)
        quantity = normalize_shares(quantity, state.config.lot_size)
        if quantity <= 0:
            return None
        total_amount = execution_price * quantity
        fee = total_amount * state.config.fee_rate
        tax = total_amount * SELL_STAMP_DUTY_RATE
        state.cash += total_amount - fee - tax
        state.shares -= quantity
        state.available_shares -= quantity
        slippage_cost = (candle.open - execution_price) * quantity
    state.total_fees += fee
    state.total_taxes += tax
    state.total_slippage_cost += slippage_cost
    state.total_trade_amount += total_amount
    nav_after = state.cash + state.shares * candle.open
    trade = TradeRecord(
        trade_id=new_id("trd"),
        backtest_id=state.backtest_id,
        datetime=candle.datetime,
        side=side,
        price=round(execution_price, 4),
        quantity=quantity,
        amount=round(total_amount, 4),
        fee=round(fee, 4),
        slippage_cost=round(slippage_cost, 4),
        tax=round(tax, 4),
        cash_after=round(state.cash, 4),
        position_after=state.shares,
        nav_after=round(nav_after, 4),
        reason=reason,
    )
    state.trades.append(trade)
    return trade


def build_round_trips(trades: list[TradeRecord]) -> list[RoundTrip]:
    open_lots: list[dict[str, Any]] = []
    round_trips: list[RoundTrip] = []
    for trade in trades:
        if trade.side == "buy":
            open_lots.append(
                {
                    "datetime": trade.datetime,
                    "quantity": trade.quantity,
                    "price": trade.price,
                    "fee_per_share": (trade.fee + trade.tax) / trade.quantity if trade.quantity else 0,
                }
            )
            continue
        remaining = trade.quantity
        sell_fee_per_share = (trade.fee + trade.tax) / trade.quantity if trade.quantity else 0
        while remaining > 0 and open_lots:
            lot = open_lots[0]
            matched = min(remaining, lot["quantity"])
            entry_cost = matched * (lot["price"] + lot["fee_per_share"])
            exit_value = matched * (trade.price - sell_fee_per_share)
            pnl = exit_value - entry_cost
            round_trips.append(
                RoundTrip(
                    entry_datetime=lot["datetime"],
                    exit_datetime=trade.datetime,
                    quantity=matched,
                    entry_price=lot["price"],
                    exit_price=trade.price,
                    pnl=round(pnl, 4),
                    return_pct=round(pnl / entry_cost, 6) if entry_cost else 0.0,
                    holding_days=max(0, (trade.datetime.date() - lot["datetime"].date()).days),
                )
            )
            lot["quantity"] -= matched
            remaining -= matched
            if lot["quantity"] == 0:
                open_lots.pop(0)
    return round_trips


def calculate_profit_loss_ratio(round_trips: list[RoundTrip]) -> float:
    gains = [item.pnl for item in round_trips if item.pnl > 0]
    losses = [abs(item.pnl) for item in round_trips if item.pnl < 0]
    if not gains:
        return 0.0
    if not losses:
        return float(len(gains))
    return round(sum(gains) / len(gains) / (sum(losses) / len(losses)), 4)


def add_equity_point(state: SimulationState, candle: Candle) -> None:
    nav = state.cash + state.shares * candle.close
    position_value = state.shares * candle.close
    position_pct = position_value / nav if nav > 0 else 0.0
    state.equity_points.append(
        EquityPoint(
            datetime=candle.datetime,
            nav=round(nav, 4),
            cash=round(state.cash, 4),
            position_value=round(position_value, 4),
            position_pct=round(position_pct, 6),
            drawdown=0.0,
        )
    )


def finalize_equity_points(points: list[EquityPoint], benchmark: list[dict[str, Any]]) -> float:
    peak = 0.0
    max_drawdown = 0.0
    benchmark_lookup = {item["datetime"]: item["value"] for item in benchmark}
    for point in points:
        peak = max(peak, point.nav)
        point.drawdown = round((peak - point.nav) / peak, 6) if peak else 0.0
        point.benchmark_nav = benchmark_lookup.get(point.datetime.isoformat())
        max_drawdown = max(max_drawdown, point.drawdown)
    return max_drawdown


def grid_signal(
    *,
    candle: Candle,
    next_candle: Candle | None,
    state: SimulationState,
    config: BacktestConfig,
    params: dict[str, Any],
    strategy_state: dict[str, Any],
) -> dict[str, Any] | None:
    if not next_candle:
        return None
    nav = state.cash + state.shares * candle.close
    if state.halt_reason:
        if state.available_shares > 0:
            return {"side": "sell", "quantity": state.available_shares, "reason": state.halt_reason}
        return None
    take_profit_pct = float(params.get("take_profit_pct", 0) or 0)
    stop_loss_pct = float(params.get("stop_loss_pct", 0) or 0)
    if config.risk_control_enabled:
        if take_profit_pct and nav >= config.initial_cash * (1 + take_profit_pct):
            state.halt_reason = "risk_take_profit"
            if state.available_shares > 0:
                return {"side": "sell", "quantity": state.available_shares, "reason": state.halt_reason}
        if stop_loss_pct and nav <= config.initial_cash * (1 - stop_loss_pct):
            state.halt_reason = "risk_stop_loss"
            if state.available_shares > 0:
                return {"side": "sell", "quantity": state.available_shares, "reason": state.halt_reason}
    base_price = float(params.get("base_price") or candle.close)
    grid_step_pct = float(params.get("grid_step_pct", 0.02))
    grid_levels = int(params.get("grid_levels", 6))
    order_amount = float(params.get("order_amount", 5000))
    max_position_pct = float(params.get("max_position_pct", config.max_position_pct))
    step_abs = base_price * grid_step_pct
    if step_abs <= 0:
        return None
    current_bucket = max(-grid_levels, min(grid_levels, math.floor((candle.close - base_price) / step_abs)))
    cursor = strategy_state.setdefault("cursor", current_bucket)
    position_pct = (state.shares * candle.close) / nav if nav > 0 else 0.0
    order_quantity = normalize_shares(order_amount / next_candle.open, config.lot_size)
    if order_quantity <= 0:
        return None
    if current_bucket < cursor and position_pct < max_position_pct:
        strategy_state["cursor"] = cursor - 1
        return {
            "side": "buy",
            "quantity": order_quantity,
            "reason": f"grid_buy_level_{abs(strategy_state['cursor'])}",
        }
    if current_bucket > cursor and state.available_shares > 0:
        strategy_state["cursor"] = cursor + 1
        return {
            "side": "sell",
            "quantity": min(order_quantity, state.available_shares),
            "reason": f"grid_sell_level_{strategy_state['cursor']}",
        }
    return None


def reference_price(
    candles: list[Candle],
    index: int,
    params: dict[str, Any],
    strategy_state: dict[str, Any],
) -> float:
    mode = params.get("reference_mode", "prev_close")
    if mode == "moving_average":
        window = candles[max(0, index - 4) : index + 1]
        return sum(item.close for item in window) / len(window)
    if mode == "intraday_vwap":
        trade_date = candles[index].trade_date
        numerator = 0.0
        denominator = 0.0
        for item in reversed(candles[: index + 1]):
            if item.trade_date != trade_date:
                break
            numerator += item.close * max(item.volume, 1)
            denominator += max(item.volume, 1)
        return numerator / denominator if denominator else candles[index].close
    if index == 0:
        return candles[index].close
    return candles[index - 1].close


def total_active_shares(strategy_state: dict[str, Any]) -> int:
    return sum(lot["quantity"] for lot in strategy_state.get("active_lots", []))


def active_average_entry(strategy_state: dict[str, Any]) -> float:
    lots = strategy_state.get("active_lots", [])
    shares = total_active_shares(strategy_state)
    if not lots or shares <= 0:
        return 0.0
    notional = sum(lot["quantity"] * lot["price"] for lot in lots)
    return notional / shares


def reduce_active_lots(strategy_state: dict[str, Any], quantity: int) -> None:
    remaining = quantity
    active_lots = strategy_state.get("active_lots", [])
    while remaining > 0 and active_lots:
        lot = active_lots[0]
        matched = min(remaining, lot["quantity"])
        lot["quantity"] -= matched
        remaining -= matched
        if lot["quantity"] == 0:
            active_lots.pop(0)


def partial_t0_signal(
    *,
    candles: list[Candle],
    index: int,
    state: SimulationState,
    config: BacktestConfig,
    params: dict[str, Any],
    strategy_state: dict[str, Any],
) -> dict[str, Any] | None:
    next_candle = candles[index + 1] if index + 1 < len(candles) else None
    if not next_candle:
        return None
    reference = reference_price(candles, index, params, strategy_state)
    close_price = candles[index].close
    buy_trigger_pct = abs(float(params.get("buy_trigger_pct", 0.015)))
    sell_trigger_pct = abs(float(params.get("sell_trigger_pct", 0.015)))
    mean_revert_target_pct = abs(float(params.get("mean_revert_target_pct", 0.008)))
    stop_loss_pct = abs(float(params.get("stop_loss_pct", 0.02)))
    base_shares = strategy_state["base_shares"]
    active_cap_shares = strategy_state["active_cap_shares"]
    active_shares = total_active_shares(strategy_state)
    available_active_shares = max(0, state.available_shares - base_shares)
    chunk_quantity = strategy_state["chunk_shares"]
    avg_entry = active_average_entry(strategy_state)
    if active_shares > 0 and available_active_shares > 0:
        if avg_entry and close_price >= avg_entry * (1 + mean_revert_target_pct):
            return {
                "side": "sell",
                "quantity": min(active_shares, available_active_shares),
                "reason": "active_mean_revert_take_profit",
            }
        if avg_entry and close_price <= avg_entry * (1 - stop_loss_pct):
            return {
                "side": "sell",
                "quantity": min(active_shares, available_active_shares),
                "reason": "active_stop_loss",
            }
        if close_price >= reference * (1 + sell_trigger_pct):
            return {
                "side": "sell",
                "quantity": min(chunk_quantity, available_active_shares),
                "reason": "active_deviation_sell",
            }
    if close_price <= reference * (1 - buy_trigger_pct) and active_shares < active_cap_shares:
        remaining_capacity = active_cap_shares - active_shares
        return {
            "side": "buy",
            "quantity": min(chunk_quantity, remaining_capacity),
            "reason": "active_deviation_buy",
        }
    return None


def create_initial_base_position(
    state: SimulationState,
    *,
    first_candle: Candle,
    params: dict[str, Any],
) -> dict[str, Any]:
    base_position_pct = float(params.get("base_position_pct", 0.7))
    active_position_pct = float(params.get("active_position_pct", 0.3))
    base_quantity = normalize_shares(
        state.config.initial_cash * base_position_pct / first_candle.open,
        state.config.lot_size,
    )
    trade = execute_order(
        state,
        candle=first_candle,
        side="buy",
        quantity=base_quantity,
        reason="initial_base_position",
        available_immediately=True,
    )
    active_cap_shares = normalize_shares(
        state.config.initial_cash * active_position_pct / first_candle.open,
        state.config.lot_size,
    )
    chunk_shares = max(state.config.lot_size, normalize_shares(active_cap_shares / 3, state.config.lot_size))
    return {
        "base_shares": trade.quantity if trade else 0,
        "active_cap_shares": active_cap_shares,
        "chunk_shares": chunk_shares,
        "active_lots": [],
    }


def score_summary(summary: dict[str, Any]) -> float:
    return round(
        summary["total_return"] * 50
        + summary["win_rate"] * 20
        - summary["max_drawdown"] * 20
        - summary["turnover_ratio"] * 10,
        6,
    )


def run_backtest(
    dataset_payload: dict[str, Any],
    *,
    strategy_type: str,
    backtest_config_payload: dict[str, Any],
    strategy_params: dict[str, Any],
    backtest_id: str | None = None,
) -> dict[str, Any]:
    ensure_strategy_supported(strategy_type, dataset_payload["timeframe"])
    candles = load_candles(dataset_payload)
    if len(candles) < 2:
        raise ValueError("At least two candles are required for backtesting.")
    config = build_backtest_config(backtest_config_payload)
    backtest_id = backtest_id or new_id("bt")
    state = SimulationState(backtest_id, config)
    strategy_state: dict[str, Any] = {}
    if strategy_type == "partial_t0":
        strategy_state.update(create_initial_base_position(state, first_candle=candles[0], params=strategy_params))
    pending_order: dict[str, Any] | None = None
    for index, candle in enumerate(candles):
        state.release_shares(candle.trade_date)
        if pending_order and pending_order["fill_index"] == index:
            executed = execute_order(
                state,
                candle=candle,
                side=pending_order["side"],
                quantity=pending_order["quantity"],
                reason=pending_order["reason"],
            )
            if executed and strategy_type == "partial_t0":
                if executed.side == "buy" and executed.reason != "initial_base_position":
                    strategy_state["active_lots"].append({"quantity": executed.quantity, "price": executed.price})
                if executed.side == "sell":
                    reduce_active_lots(strategy_state, executed.quantity)
            pending_order = None
        add_equity_point(state, candle)
        if index == len(candles) - 1:
            break
        if strategy_type == "grid":
            signal = grid_signal(
                candle=candle,
                next_candle=candles[index + 1],
                state=state,
                config=config,
                params=strategy_params,
                strategy_state=strategy_state,
            )
        else:
            signal = partial_t0_signal(
                candles=candles,
                index=index,
                state=state,
                config=config,
                params=strategy_params,
                strategy_state=strategy_state,
            )
        if signal:
            pending_order = {**signal, "fill_index": index + 1}
    benchmark, benchmark_return = benchmark_curve(candles, config)
    max_drawdown = finalize_equity_points(state.equity_points, benchmark)
    round_trips = build_round_trips(state.trades)
    wins = [trip for trip in round_trips if trip.pnl > 0]
    summary = BacktestSummary(
        backtest_id=backtest_id,
        dataset_id=dataset_payload["dataset_id"],
        strategy_type=strategy_type,
        total_return=round(state.equity_points[-1].nav / config.initial_cash - 1, 6),
        annualized_return=annualized_return(candles, state.equity_points[-1].nav / config.initial_cash - 1),
        max_drawdown=round(max_drawdown, 6),
        win_rate=round(len(wins) / len(round_trips), 6) if round_trips else 0.0,
        profit_loss_ratio=calculate_profit_loss_ratio(round_trips),
        trade_count=len(state.trades),
        fees_paid=round(state.total_fees + state.total_taxes, 4),
        final_nav=round(state.equity_points[-1].nav, 4),
        benchmark_return=round(benchmark_return, 6) if benchmark else None,
        excess_return=round((state.equity_points[-1].nav / config.initial_cash - 1) - benchmark_return, 6) if benchmark else None,
        exposure_ratio=round(
            sum(point.position_pct for point in state.equity_points) / len(state.equity_points),
            6,
        ),
        turnover_ratio=round(state.total_trade_amount / config.initial_cash, 6),
        cost_ratio=round((state.total_fees + state.total_taxes + state.total_slippage_cost) / config.initial_cash, 6),
        round_trip_win_rate=round(len(wins) / len(round_trips), 6) if round_trips else 0.0,
        created_at=datetime.utcnow(),
    )
    result = BacktestResult(
        backtest_id=backtest_id,
        dataset_id=dataset_payload["dataset_id"],
        dataset_hash=dataset_payload["dataset_hash"],
        strategy_type=strategy_type,
        strategy_version=GRID_STRATEGY_VERSION if strategy_type == "grid" else PARTIAL_T0_STRATEGY_VERSION,
        engine_version=ENGINE_VERSION,
        backtest_config=serialize(config),
        strategy_params=strategy_params,
        summary=summary,
        equity_points=state.equity_points,
        benchmark_curve=benchmark,
        trades=state.trades,
        round_trips=round_trips,
        cost_breakdown={
            "commission": round(state.total_fees, 4),
            "stamp_duty": round(state.total_taxes, 4),
            "slippage": round(state.total_slippage_cost, 4),
            "total_cost": round(state.total_fees + state.total_taxes + state.total_slippage_cost, 4),
        },
        execution_mode=config.execution_mode,
        benchmark_mode=config.benchmark_mode,
        created_at=datetime.utcnow(),
    )
    payload = serialize(result)
    payload["timeseries"] = {
        "equity_curve": [
            {"datetime": point.datetime.isoformat(), "value": point.nav}
            for point in state.equity_points
        ],
        "position_curve": [
            {"datetime": point.datetime.isoformat(), "position_pct": point.position_pct}
            for point in state.equity_points
        ],
        "drawdown_curve": [
            {"datetime": point.datetime.isoformat(), "drawdown": point.drawdown}
            for point in state.equity_points
        ],
        "benchmark_curve": benchmark,
    }
    return payload


def annualized_return(candles: list[Candle], total_return: float) -> float | None:
    if len(candles) < 2:
        return None
    days = max(1, (candles[-1].datetime.date() - candles[0].datetime.date()).days)
    years = days / 365
    if years <= 0:
        return None
    return round((1 + total_return) ** (1 / years) - 1, 6)


def cartesian_param_grid(param_grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
    keys = list(param_grid)
    values = [param_grid[key] for key in keys]
    combinations = []
    for combo in itertools.product(*values):
        combinations.append({key: combo[idx] for idx, key in enumerate(keys)})
    return combinations


def run_parameter_sweep(
    dataset_payload: dict[str, Any],
    *,
    strategy_type: str,
    backtest_config_payload: dict[str, Any],
    base_strategy_params: dict[str, Any],
    param_grid: dict[str, list[Any]],
    ranking_metric: str = "risk_adjusted_return",
) -> dict[str, Any]:
    combinations = cartesian_param_grid(param_grid)
    runs: list[ExperimentRun] = []
    for params in combinations:
        merged_params = {**base_strategy_params, **params}
        result = run_backtest(
            dataset_payload,
            strategy_type=strategy_type,
            backtest_config_payload=backtest_config_payload,
            strategy_params=merged_params,
            backtest_id=new_id("bt"),
        )
        summary = result["summary"]
        summary["score"] = score_summary(summary)
        runs.append(
            ExperimentRun(
                run_id=new_id("run"),
                params=merged_params,
                summary=summary,
            )
        )
    runs.sort(key=lambda item: item.summary.get("score", 0), reverse=True)
    experiment = ExperimentRecord(
        experiment_id=new_id("exp"),
        dataset_id=dataset_payload["dataset_id"],
        dataset_hash=dataset_payload["dataset_hash"],
        strategy_type=strategy_type,
        ranking_metric=ranking_metric,
        ranking_formula=DEFAULT_RANKING_FORMULA,
        total_runs=len(runs),
        created_at=datetime.utcnow(),
        engine_version=ENGINE_VERSION,
        strategy_version=GRID_STRATEGY_VERSION if strategy_type == "grid" else PARTIAL_T0_STRATEGY_VERSION,
        backtest_config=backtest_config_payload,
        base_strategy_params=base_strategy_params,
        param_grid=param_grid,
        runs=runs,
    )
    return serialize(experiment)
