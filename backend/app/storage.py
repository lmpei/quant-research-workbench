from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import json
import sqlite3
from pathlib import Path
from typing import Any

from .datasets import build_demo_dataset, build_intraday_demo_dataset
from .domain import DatasetRecord, serialize


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "workbench.db"


def json_dumps(payload: Any) -> str:
    return json.dumps(serialize(payload), ensure_ascii=False)


@contextmanager
def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


def init_db() -> None:
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS datasets (
                dataset_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                source_type TEXT NOT NULL,
                rows_count INTEGER NOT NULL,
                start_at TEXT NOT NULL,
                end_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                market TEXT NOT NULL,
                timezone TEXT NOT NULL,
                session TEXT NOT NULL,
                adjustment TEXT,
                dataset_hash TEXT NOT NULL,
                validation_status TEXT NOT NULL,
                validation_report_json TEXT NOT NULL,
                candles_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS backtests (
                backtest_id TEXT PRIMARY KEY,
                dataset_id TEXT NOT NULL,
                dataset_hash TEXT NOT NULL,
                strategy_type TEXT NOT NULL,
                strategy_version TEXT NOT NULL,
                engine_version TEXT NOT NULL,
                created_at TEXT NOT NULL,
                config_json TEXT NOT NULL,
                params_json TEXT NOT NULL,
                result_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS experiments (
                experiment_id TEXT PRIMARY KEY,
                dataset_id TEXT NOT NULL,
                dataset_hash TEXT NOT NULL,
                strategy_type TEXT NOT NULL,
                ranking_metric TEXT NOT NULL,
                ranking_formula TEXT NOT NULL,
                total_runs INTEGER NOT NULL,
                engine_version TEXT NOT NULL,
                strategy_version TEXT NOT NULL,
                created_at TEXT NOT NULL,
                backtest_config_json TEXT NOT NULL,
                base_strategy_params_json TEXT NOT NULL DEFAULT '{}',
                param_grid_json TEXT NOT NULL,
                runs_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS reports (
                report_id TEXT PRIMARY KEY,
                backtest_id TEXT,
                experiment_id TEXT,
                report_type TEXT NOT NULL,
                title TEXT NOT NULL,
                sections_json TEXT NOT NULL,
                raw_markdown TEXT NOT NULL,
                structured_recommendations_json TEXT NOT NULL,
                next_experiments_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                job_type TEXT NOT NULL,
                status TEXT NOT NULL,
                request_json TEXT NOT NULL,
                result_ref_json TEXT,
                error_text TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT
            );
            """
        )
        try:
            connection.execute("ALTER TABLE experiments ADD COLUMN base_strategy_params_json TEXT NOT NULL DEFAULT '{}'")
        except sqlite3.OperationalError:
            pass
        connection.commit()


def ensure_demo_dataset() -> None:
    if not get_dataset("ds_demo_byd_1d"):
        dataset, candles = build_demo_dataset()
        save_dataset(dataset, candles)
    if not get_dataset("ds_demo_byd_15m"):
        dataset, candles = build_intraday_demo_dataset()
        save_dataset(dataset, candles)


def save_dataset(record: DatasetRecord, candles: list[dict] | list[Any]) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO datasets (
                dataset_id, name, symbol, timeframe, source_type, rows_count, start_at, end_at, created_at,
                market, timezone, session, adjustment, dataset_hash, validation_status, validation_report_json,
                candles_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.dataset_id,
                record.name,
                record.symbol,
                record.timeframe,
                record.source_type,
                record.rows,
                record.start_at.isoformat(),
                record.end_at.isoformat(),
                record.created_at.isoformat(),
                record.market,
                record.timezone,
                record.session,
                record.adjustment,
                record.dataset_hash,
                record.validation_status,
                json_dumps(record.validation_report),
                json_dumps(candles),
            ),
        )
        connection.commit()


def list_datasets() -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT dataset_id, name, symbol, timeframe, source_type, rows_count, start_at, end_at,
                   market, timezone, session, adjustment, dataset_hash, validation_status, validation_report_json, created_at
            FROM datasets
            ORDER BY created_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_dataset(dataset_id: str) -> dict | None:
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM datasets WHERE dataset_id = ?", (dataset_id,)).fetchone()
    return dict(row) if row else None


def save_backtest(backtest: dict) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO backtests (
                backtest_id, dataset_id, dataset_hash, strategy_type, strategy_version, engine_version,
                created_at, config_json, params_json, result_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                backtest["backtest_id"],
                backtest["dataset_id"],
                backtest["dataset_hash"],
                backtest["strategy_type"],
                backtest["strategy_version"],
                backtest["engine_version"],
                backtest["created_at"],
                json.dumps(backtest["backtest_config"]),
                json.dumps(backtest["strategy_params"]),
                json.dumps(backtest),
            ),
        )
        connection.commit()


def get_backtest(backtest_id: str) -> dict | None:
    with get_connection() as connection:
        row = connection.execute("SELECT result_json FROM backtests WHERE backtest_id = ?", (backtest_id,)).fetchone()
    return json.loads(row["result_json"]) if row else None


def save_experiment(experiment: dict) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO experiments (
                experiment_id, dataset_id, dataset_hash, strategy_type, ranking_metric, ranking_formula,
                total_runs, engine_version, strategy_version, created_at, backtest_config_json,
                base_strategy_params_json, param_grid_json, runs_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                experiment["experiment_id"],
                experiment["dataset_id"],
                experiment["dataset_hash"],
                experiment["strategy_type"],
                experiment["ranking_metric"],
                experiment["ranking_formula"],
                experiment["total_runs"],
                experiment["engine_version"],
                experiment["strategy_version"],
                experiment["created_at"],
                json.dumps(experiment["backtest_config"]),
                json.dumps(experiment["base_strategy_params"]),
                json.dumps(experiment["param_grid"]),
                json.dumps(experiment["runs"]),
            ),
        )
        connection.commit()


def list_experiments() -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT experiment_id, dataset_id, dataset_hash, strategy_type, ranking_metric, ranking_formula,
                   total_runs, engine_version, strategy_version, created_at, backtest_config_json,
                   base_strategy_params_json, param_grid_json, runs_json
            FROM experiments
            ORDER BY created_at DESC
            """
        ).fetchall()
    experiments = []
    for row in rows:
        payload = dict(row)
        payload["backtest_config"] = json.loads(payload.pop("backtest_config_json"))
        payload["base_strategy_params"] = json.loads(payload.pop("base_strategy_params_json"))
        payload["param_grid"] = json.loads(payload.pop("param_grid_json"))
        payload["runs"] = json.loads(payload.pop("runs_json"))
        experiments.append(payload)
    return experiments


def get_experiment(experiment_id: str) -> dict | None:
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM experiments WHERE experiment_id = ?", (experiment_id,)).fetchone()
    if not row:
        return None
    payload = dict(row)
    payload["backtest_config"] = json.loads(payload.pop("backtest_config_json"))
    payload["base_strategy_params"] = json.loads(payload.pop("base_strategy_params_json"))
    payload["param_grid"] = json.loads(payload.pop("param_grid_json"))
    payload["runs"] = json.loads(payload.pop("runs_json"))
    return payload


def save_report(report: dict) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO reports (
                report_id, backtest_id, experiment_id, report_type, title, sections_json, raw_markdown,
                structured_recommendations_json, next_experiments_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report["report_id"],
                report.get("backtest_id"),
                report.get("experiment_id"),
                report["report_type"],
                report["title"],
                json.dumps(report["sections"], ensure_ascii=False),
                report["raw_markdown"],
                json.dumps(report["structured_recommendations"], ensure_ascii=False),
                json.dumps(report["next_experiments"], ensure_ascii=False),
                report["created_at"],
            ),
        )
        connection.commit()


def get_report(report_id: str) -> dict | None:
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM reports WHERE report_id = ?", (report_id,)).fetchone()
    if not row:
        return None
    payload = dict(row)
    payload["sections"] = json.loads(payload.pop("sections_json"))
    payload["structured_recommendations"] = json.loads(payload.pop("structured_recommendations_json"))
    payload["next_experiments"] = json.loads(payload.pop("next_experiments_json"))
    return payload


def normalize_job_row(row: sqlite3.Row | dict) -> dict:
    payload = dict(row)
    payload["request"] = json.loads(payload.pop("request_json"))
    payload["result_ref"] = json.loads(payload["result_ref_json"]) if payload["result_ref_json"] else None
    payload.pop("result_ref_json")
    return payload


def create_job(job_id: str, job_type: str, request_payload: dict) -> dict:
    now = datetime.utcnow().isoformat()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO jobs (job_id, job_type, status, request_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (job_id, job_type, "queued", json.dumps(request_payload), now),
        )
        connection.commit()
    return get_job(job_id)


def update_job(
    job_id: str,
    *,
    status: str,
    result_ref: dict | None = None,
    error_text: str | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE jobs
            SET status = ?, result_ref_json = COALESCE(?, result_ref_json), error_text = COALESCE(?, error_text),
                started_at = COALESCE(?, started_at), finished_at = COALESCE(?, finished_at)
            WHERE job_id = ?
            """,
            (
                status,
                json.dumps(result_ref) if result_ref else None,
                error_text,
                started_at,
                finished_at,
                job_id,
            ),
        )
        connection.commit()


def get_job(job_id: str) -> dict | None:
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
    if not row:
        return None
    return normalize_job_row(row)


def list_recent_jobs(limit: int = 10) -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM jobs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [normalize_job_row(row) for row in rows]
