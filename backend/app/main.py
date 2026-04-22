from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .datasets import parse_csv_upload
from .domain import CN_A_SHARE, DEFAULT_EXECUTION_MODE, SELL_STAMP_DUTY_RATE
from .engine import run_backtest, run_parameter_sweep
from .jobs import JobManager
from .reporting import generate_report, llm_runtime_status
from .storage import (
    ensure_demo_dataset,
    get_backtest,
    get_dataset,
    get_experiment,
    get_job,
    get_report,
    init_db,
    list_datasets,
    list_experiments,
    list_recent_jobs,
    save_backtest,
    save_dataset,
    save_experiment,
    save_report,
)


app = FastAPI(title="Quant Research Workbench API", version="1.0.0")
job_manager = JobManager()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    ensure_demo_dataset()


def parse_dataset_payload(record: dict[str, Any], *, include_candles: bool = False) -> dict[str, Any]:
    payload = {
        "dataset_id": record["dataset_id"],
        "name": record["name"],
        "symbol": record["symbol"],
        "timeframe": record["timeframe"],
        "source_type": record["source_type"],
        "rows": record.get("rows_count", record.get("rows")),
        "start_at": record["start_at"],
        "end_at": record["end_at"],
        "created_at": record["created_at"],
        "market": record["market"],
        "timezone": record["timezone"],
        "session": record["session"],
        "adjustment": record["adjustment"],
        "dataset_hash": record["dataset_hash"],
        "validation_status": record["validation_status"],
    }
    validation_report = record.get("validation_report")
    if validation_report is None and record.get("validation_report_json"):
        validation_report = json.loads(record["validation_report_json"])
    payload["validation_report"] = validation_report
    candles = []
    if record.get("candles_json"):
        candles = json.loads(record["candles_json"])
        payload["preview"] = candles[:12]
    if include_candles:
        payload["candles"] = candles
    return payload


def summarize_job(job: dict[str, Any] | None) -> dict[str, Any] | None:
    if not job:
        return None
    return {
        "job_id": job["job_id"],
        "job_type": job["job_type"],
        "status": job["status"],
        "error_text": job.get("error_text"),
        "created_at": job.get("created_at"),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "result_ref": job.get("result_ref"),
    }


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def root() -> dict[str, str]:
    return {
        "message": "AI 单票策略研究工作台 API 已启动。",
        "health": "/api/health",
        "system_status": "/api/system/status",
        "docs": "/docs",
    }


@app.get("/api/system/status")
def system_status() -> dict[str, Any]:
    datasets_payload = [parse_dataset_payload(item, include_candles=False) for item in list_datasets()]
    jobs = list_recent_jobs(limit=12)
    recent_job = jobs[0] if jobs else None
    last_failed_job = next((job for job in jobs if job["status"] == "failed"), None)
    return {
        "status": "ok",
        "product_name": "AI 单票策略研究工作台",
        "market": CN_A_SHARE,
        "execution_mode": DEFAULT_EXECUTION_MODE,
        "rules": {
            "lot_size": 100,
            "sell_stamp_duty_rate": SELL_STAMP_DUTY_RATE,
            "t_plus_one": True,
            "fee_included": True,
            "slippage_included": True,
        },
        "llm": llm_runtime_status(),
        "datasets_total": len(datasets_payload),
        "demo_datasets": [
            {
                "dataset_id": item["dataset_id"],
                "name": item["name"],
                "symbol": item["symbol"],
                "timeframe": item["timeframe"],
            }
            for item in datasets_payload
            if item["source_type"] == "demo"
        ],
        "recent_job": summarize_job(recent_job),
        "last_failed_job": summarize_job(last_failed_job),
    }


@app.get("/api/datasets")
def datasets() -> list[dict[str, Any]]:
    return [parse_dataset_payload(item, include_candles=False) for item in list_datasets()]


@app.get("/api/datasets/{dataset_id}")
def dataset_detail(dataset_id: str) -> dict[str, Any]:
    dataset = get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="未找到数据集。")
    return parse_dataset_payload(dataset, include_candles=True)


@app.post("/api/datasets/upload")
async def upload_dataset(
    name: str = Form(...),
    symbol: str = Form(...),
    timeframe: str = Form(...),
    adjustment: str | None = Form(None),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    try:
        record, candles = parse_csv_upload(
            content=await file.read(),
            name=name,
            symbol=symbol,
            timeframe=timeframe,
            adjustment=adjustment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    save_dataset(record, candles)
    stored = get_dataset(record.dataset_id)
    return parse_dataset_payload(stored, include_candles=True)


@app.post("/api/backtests/run")
def run_single_backtest(payload: dict[str, Any]) -> dict[str, Any]:
    dataset = get_dataset(payload["dataset_id"])
    if not dataset:
        raise HTTPException(status_code=404, detail="未找到数据集。")
    try:
        result = run_backtest(
            parse_dataset_payload(dataset, include_candles=True),
            strategy_type=payload["strategy_type"],
            backtest_config_payload=payload.get("backtest_config", {}),
            strategy_params=payload.get("strategy_params", {}),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    save_backtest(result)
    return result


@app.get("/api/backtests/{backtest_id}")
def backtest_detail(backtest_id: str) -> dict[str, Any]:
    result = get_backtest(backtest_id)
    if not result:
        raise HTTPException(status_code=404, detail="未找到回测结果。")
    return result


@app.post("/api/backtests/sweep")
def create_sweep(payload: dict[str, Any]) -> dict[str, Any]:
    dataset = get_dataset(payload["dataset_id"])
    if not dataset:
        raise HTTPException(status_code=404, detail="未找到数据集。")
    dataset_payload = parse_dataset_payload(dataset, include_candles=True)

    def worker() -> dict[str, str]:
        experiment = run_parameter_sweep(
            dataset_payload,
            strategy_type=payload["strategy_type"],
            backtest_config_payload=payload.get("backtest_config", {}),
            base_strategy_params=payload.get("base_strategy_params", {}),
            param_grid=payload.get("param_grid", {}),
            ranking_metric=payload.get("ranking_metric", "risk_adjusted_return"),
        )
        save_experiment(experiment)
        return {"kind": "experiment", "experiment_id": experiment["experiment_id"]}

    return job_manager.submit("sweep", payload, worker)


@app.get("/api/experiments")
def experiments() -> list[dict[str, Any]]:
    items = list_experiments()
    response = []
    for item in items:
        top_run = item["runs"][0] if item["runs"] else None
        response.append(
            {
                "experiment_id": item["experiment_id"],
                "dataset_id": item["dataset_id"],
                "dataset_hash": item["dataset_hash"],
                "strategy_type": item["strategy_type"],
                "ranking_metric": item["ranking_metric"],
                "ranking_formula": item["ranking_formula"],
                "total_runs": item["total_runs"],
                "engine_version": item["engine_version"],
                "strategy_version": item["strategy_version"],
                "created_at": item["created_at"],
                "top_run": top_run,
            }
        )
    return response


@app.get("/api/experiments/{experiment_id}")
def experiment_detail(experiment_id: str) -> dict[str, Any]:
    experiment = get_experiment(experiment_id)
    if not experiment:
        raise HTTPException(status_code=404, detail="未找到实验记录。")
    return experiment


@app.post("/api/reports/generate")
def create_report(payload: dict[str, Any]) -> dict[str, Any]:
    dataset = get_dataset(payload["dataset_id"])
    backtest = get_backtest(payload["backtest_id"])
    experiment = get_experiment(payload["experiment_id"]) if payload.get("experiment_id") else None
    if not dataset:
        raise HTTPException(status_code=404, detail="未找到数据集。")
    if not backtest:
        raise HTTPException(status_code=404, detail="未找到回测结果。")

    def worker() -> dict[str, str]:
        report = generate_report(
            parse_dataset_payload(dataset, include_candles=True),
            backtest,
            experiment,
            report_type=payload.get("report_type", "strategy_analysis"),
        )
        save_report(report)
        return {"kind": "report", "report_id": report["report_id"]}

    return job_manager.submit("report", payload, worker)


@app.get("/api/reports/{report_id}")
def report_detail(report_id: str) -> dict[str, Any]:
    report = get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="未找到分析报告。")
    return report


@app.get("/api/jobs/{job_id}")
def job_detail(job_id: str) -> dict[str, Any]:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="未找到任务记录。")
    return job
