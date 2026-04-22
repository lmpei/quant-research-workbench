from __future__ import annotations

from collections import Counter
from datetime import datetime, time, timedelta
from hashlib import sha256
import csv
import io
import math
import random

from .domain import (
    Candle,
    DatasetRecord,
    REQUIRED_COLUMNS,
    SUPPORTED_TIMEFRAMES,
    CN_A_SHARE,
    CN_A_SHARE_SESSION,
    CN_A_SHARE_TIMEZONE,
    new_id,
)


def parse_datetime(value: str) -> datetime:
    value = value.strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d",
    ):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(f"Unsupported datetime format: {value}")


def normalized_dataset_hash(
    symbol: str,
    timeframe: str,
    adjustment: str | None,
    candles: list[Candle],
) -> str:
    digest = sha256()
    digest.update(symbol.encode("utf-8"))
    digest.update(timeframe.encode("utf-8"))
    digest.update((adjustment or "none").encode("utf-8"))
    for candle in candles:
        digest.update(
            (
                f"{candle.datetime.isoformat()}|{candle.open:.4f}|{candle.high:.4f}|"
                f"{candle.low:.4f}|{candle.close:.4f}|{candle.volume:.4f}"
            ).encode("utf-8")
        )
    return digest.hexdigest()


def infer_expected_delta(datetimes: list[datetime], timeframe: str) -> timedelta | None:
    if timeframe in SUPPORTED_TIMEFRAMES:
        return SUPPORTED_TIMEFRAMES[timeframe]
    if len(datetimes) < 2:
        return None
    diffs = [datetimes[idx + 1] - datetimes[idx] for idx in range(len(datetimes) - 1)]
    if not diffs:
        return None
    return Counter(diffs).most_common(1)[0][0]


def validate_candles(candles: list[Candle], timeframe: str, adjustment: str | None) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    datetimes = [item.datetime for item in candles]
    duplicates = 0
    if not candles:
        errors.append("CSV contains no rows.")
    if timeframe == "1d" and not adjustment:
        errors.append("Daily datasets must declare an adjustment mode.")
    if datetimes != sorted(datetimes):
        errors.append("Timestamps must be strictly ascending.")
    duplicates = len(datetimes) - len(set(datetimes))
    if duplicates:
        errors.append(f"Duplicate timestamps detected: {duplicates}.")
    abnormal_rows = 0
    for candle in candles:
        if min(candle.open, candle.high, candle.low, candle.close) <= 0:
            abnormal_rows += 1
        if candle.high < max(candle.open, candle.close) or candle.low > min(candle.open, candle.close):
            abnormal_rows += 1
        if candle.volume < 0:
            abnormal_rows += 1
    if abnormal_rows:
        errors.append(f"Found {abnormal_rows} rows with invalid OHLCV relationships.")
    expected_delta = infer_expected_delta(datetimes, timeframe)
    gap_samples: list[str] = []
    gap_count = 0
    if expected_delta and len(datetimes) > 1:
        for previous, current in zip(datetimes, datetimes[1:]):
            delta = current - previous
            if timeframe == "1d":
                if delta.days > 4:
                    gap_count += 1
                    gap_samples.append(f"{previous.date()} -> {current.date()} ({delta.days}d)")
            elif previous.date() != current.date():
                continue
            elif previous.time() <= time(11, 30) and current.time() >= time(13, 0) and delta <= timedelta(hours=2):
                continue
            elif delta > expected_delta * 1.5:
                gap_count += 1
                gap_samples.append(f"{previous.isoformat()} -> {current.isoformat()}")
    if gap_count:
        warnings.append(f"Detected {gap_count} potential missing-bar gaps.")
    status = "valid" if not errors else "invalid"
    return {
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "duplicates": duplicates,
        "potential_missing_gaps": gap_count,
        "gap_samples": gap_samples[:5],
        "expected_interval": str(expected_delta) if expected_delta else None,
        "row_count": len(candles),
    }


def parse_csv_upload(
    *,
    content: bytes,
    name: str,
    symbol: str,
    timeframe: str,
    adjustment: str | None,
) -> tuple[DatasetRecord, list[Candle]]:
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in (reader.fieldnames or [])]
    if missing_columns:
        raise ValueError(f"Missing required columns: {', '.join(missing_columns)}")
    candles: list[Candle] = []
    for row in reader:
        candles.append(
            Candle(
                datetime=parse_datetime(row["datetime"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            )
        )
    validation_report = validate_candles(candles, timeframe, adjustment)
    if validation_report["status"] != "valid":
        raise ValueError("; ".join(validation_report["errors"]))
    created_at = datetime.utcnow()
    record = DatasetRecord(
        dataset_id=new_id("ds"),
        name=name,
        symbol=symbol,
        timeframe=timeframe,
        source_type="csv",
        rows=len(candles),
        start_at=candles[0].datetime,
        end_at=candles[-1].datetime,
        created_at=created_at,
        market=CN_A_SHARE,
        timezone=CN_A_SHARE_TIMEZONE,
        session=CN_A_SHARE_SESSION,
        adjustment=adjustment,
        dataset_hash=normalized_dataset_hash(symbol, timeframe, adjustment, candles),
        validation_status=validation_report["status"],
        validation_report=validation_report,
    )
    return record, candles


def generate_demo_candles() -> list[Candle]:
    rng = random.Random(7)
    candles: list[Candle] = []
    current = datetime(2025, 1, 2, 15, 0, 0)
    price = 212.0
    business_days = 90
    while len(candles) < business_days:
        if current.weekday() >= 5:
            current += timedelta(days=1)
            continue
        cycle = math.sin(len(candles) / 5.0) * 3.8
        drift = 0.22 if len(candles) < 25 else (-0.11 if len(candles) > 58 else 0.06)
        open_price = max(120.0, price + drift + rng.uniform(-1.2, 1.1))
        close_price = max(120.0, open_price + cycle * 0.18 + rng.uniform(-2.0, 2.4))
        high_price = max(open_price, close_price) + rng.uniform(0.5, 2.8)
        low_price = min(open_price, close_price) - rng.uniform(0.4, 2.2)
        volume = 900000 + rng.randint(0, 700000)
        candles.append(
            Candle(
                datetime=current,
                open=round(open_price, 2),
                high=round(high_price, 2),
                low=round(low_price, 2),
                close=round(close_price, 2),
                volume=volume,
            )
        )
        price = close_price
        current += timedelta(days=1)
    return candles


def build_demo_dataset() -> tuple[DatasetRecord, list[Candle]]:
    candles = generate_demo_candles()
    validation_report = validate_candles(candles, "1d", "forward_adjusted")
    created_at = datetime.utcnow()
    dataset = DatasetRecord(
        dataset_id="ds_demo_byd_1d",
        name="BYD_Daily_Demo",
        symbol="002594.SZ",
        timeframe="1d",
        source_type="demo",
        rows=len(candles),
        start_at=candles[0].datetime,
        end_at=candles[-1].datetime,
        created_at=created_at,
        market=CN_A_SHARE,
        timezone=CN_A_SHARE_TIMEZONE,
        session=CN_A_SHARE_SESSION,
        adjustment="forward_adjusted",
        dataset_hash=normalized_dataset_hash("002594.SZ", "1d", "forward_adjusted", candles),
        validation_status=validation_report["status"],
        validation_report=validation_report,
    )
    return dataset, candles


def generate_intraday_demo_candles() -> list[Candle]:
    rng = random.Random(19)
    session_times = [
        (9, 45),
        (10, 0),
        (10, 15),
        (10, 30),
        (10, 45),
        (11, 0),
        (11, 15),
        (11, 30),
        (13, 15),
        (13, 30),
        (13, 45),
        (14, 0),
        (14, 15),
        (14, 30),
        (14, 45),
        (15, 0),
    ]
    current_date = datetime(2025, 3, 3)
    price = 224.0
    candles: list[Candle] = []
    while len(candles) < 128:
        if current_date.weekday() >= 5:
            current_date += timedelta(days=1)
            continue
        day_bias = math.sin(len(candles) / 9.0) * 1.8 + rng.uniform(-0.9, 0.9)
        for hour, minute in session_times:
            timestamp = datetime(current_date.year, current_date.month, current_date.day, hour, minute)
            intraday_wave = math.sin((hour * 60 + minute) / 22.0) * 0.9
            open_price = max(150.0, price + rng.uniform(-0.8, 0.8))
            close_price = max(150.0, open_price + intraday_wave + day_bias * 0.15 + rng.uniform(-1.0, 1.0))
            high_price = max(open_price, close_price) + rng.uniform(0.1, 0.8)
            low_price = min(open_price, close_price) - rng.uniform(0.1, 0.9)
            volume = 45000 + rng.randint(0, 35000)
            candles.append(
                Candle(
                    datetime=timestamp,
                    open=round(open_price, 2),
                    high=round(high_price, 2),
                    low=round(low_price, 2),
                    close=round(close_price, 2),
                    volume=volume,
                )
            )
            price = close_price
        current_date += timedelta(days=1)
    return candles


def build_intraday_demo_dataset() -> tuple[DatasetRecord, list[Candle]]:
    candles = generate_intraday_demo_candles()
    validation_report = validate_candles(candles, "15m", "forward_adjusted")
    created_at = datetime.utcnow()
    dataset = DatasetRecord(
        dataset_id="ds_demo_byd_15m",
        name="BYD_15m_Demo",
        symbol="002594.SZ",
        timeframe="15m",
        source_type="demo",
        rows=len(candles),
        start_at=candles[0].datetime,
        end_at=candles[-1].datetime,
        created_at=created_at,
        market=CN_A_SHARE,
        timezone=CN_A_SHARE_TIMEZONE,
        session=CN_A_SHARE_SESSION,
        adjustment="forward_adjusted",
        dataset_hash=normalized_dataset_hash("002594.SZ", "15m", "forward_adjusted", candles),
        validation_status=validation_report["status"],
        validation_report=validation_report,
    )
    return dataset, candles
