from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Callable

from .domain import new_id
from .storage import create_job, get_job, update_job


class JobManager:
    def __init__(self) -> None:
        self.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="qrw-job")

    def submit(self, job_type: str, request_payload: dict, handler: Callable[[], dict]) -> dict:
        job_id = new_id("job")
        create_job(job_id, job_type, request_payload)

        def runner() -> None:
            update_job(job_id, status="running", started_at=datetime.utcnow().isoformat())
            try:
                result_ref = handler()
                update_job(
                    job_id,
                    status="completed",
                    result_ref=result_ref,
                    finished_at=datetime.utcnow().isoformat(),
                )
            except Exception as exc:  # pragma: no cover - background errors are surfaced through job polling.
                update_job(
                    job_id,
                    status="failed",
                    error_text=str(exc),
                    finished_at=datetime.utcnow().isoformat(),
                )

        self.executor.submit(runner)
        return get_job(job_id)

