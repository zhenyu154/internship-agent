"""Manual Greenhouse discovery orchestration with optional SQLite persistence."""

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Any

from .config import load_config
from .database import JobDatabase
from .greenhouse import (
    GreenhouseBoard,
    GreenhouseClient,
    GreenhouseError,
    GreenhouseJob,
    load_board_registry,
    save_board_registry,
)
from .models import Job, JobMetadata
from .relevance import EXCLUDED, classify_greenhouse_job


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _config_fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    run_id: str | None
    boards_verified: int
    jobs_retrieved: int
    jobs_relevant: int
    jobs_saved: int
    errors: tuple[str, ...]
    jobs: tuple[GreenhouseJob, ...]


class GreenhouseDiscovery:
    def __init__(self, client: GreenhouseClient | None = None) -> None:
        self.client = client or GreenhouseClient()

    @staticmethod
    def _store_job(database: JobDatabase, job: GreenhouseJob) -> bool:
        if job.source_job_id == "UNKNOWN":
            return False
        stored = database.add_job(Job(
            title=job.title,
            company=job.company_name,
            location=job.location if job.location != "UNKNOWN" else "",
            url=job.application_url if job.application_url != "UNKNOWN" else "",
            source="greenhouse",
            source_job_id=f"{job.board_token}:{job.source_job_id}",
            description=job.description if job.description != "UNKNOWN" else "",
        ))
        database.save_job_metadata(JobMetadata(
            job_id=stored.record.id,
            source_url=job.source_url,
            greenhouse_board_token=job.board_token,
            published_at=job.published_at,
            updated_at=job.updated_at,
            internship_term=job.internship_term,
            degree_requirements=job.degree_requirements,
            graduation_window=job.graduation_window,
            work_authorization=job.work_authorization,
            relevance_category=job.relevance_category,
            relevance_reason=job.relevance_reason,
            verified_at=job.verified_at,
        ))
        return True

    def discover(
        self,
        config_path: str | Path,
        registry_path: str | Path,
        *,
        database: JobDatabase | None = None,
        limit: int = 10,
        save: bool = False,
        resume_run_id: str | None = None,
        save_registry: bool = False,
    ) -> DiscoveryResult:
        if type(limit) is not int or limit <= 0:
            raise ValueError("limit must be a positive integer")
        config_path = Path(config_path)
        registry_path = Path(registry_path)
        preferences = load_config(config_path)
        boards = load_board_registry(registry_path)
        active_boards = [board for board in boards if board.active]
        if not active_boards:
            raise ValueError("Greenhouse registry has no active boards")
        if save and database is None:
            raise ValueError("database is required when save=True")
        if resume_run_id and not save:
            raise ValueError("resume_run_id requires save=True")

        run_id: str | None = None
        completed_tokens: set[str] = set()
        if save:
            if resume_run_id:
                database.resume_run(resume_run_id)
                run_id = resume_run_id
            else:
                run = database.start_run(
                    "greenhouse_discovery",
                    _config_fingerprint(config_path),
                    [board.board_token for board in active_boards],
                )
                run_id = run.run_id
            completed_tokens = {
                item.item_key for item in database.get_work_items(run_id)
                if item.state == "COMPLETED"
            }

        retrieved = 0
        relevant: list[GreenhouseJob] = []
        saved = 0
        errors: list[str] = []
        verified_boards: list[GreenhouseBoard] = []
        for board in active_boards:
            if board.board_token in completed_tokens:
                verified_boards.append(board)
                continue
            verified_at = _now()
            try:
                jobs = self.client.fetch_jobs(board)
                retrieved += len(jobs)
                verified_boards.append(replace(board, verified_at=verified_at, active=True))
                for job in jobs:
                    classification = classify_greenhouse_job(job, preferences)
                    enriched = replace(
                        job,
                        relevance_category=classification.category,
                        relevance_reason=classification.reason,
                    )
                    if classification.category != EXCLUDED and len(relevant) < limit:
                        relevant.append(enriched)
                        if save and database is not None and self._store_job(database, enriched):
                            saved += 1
                if save and run_id:
                    database.save_item_progress(run_id, board.board_token, "COMPLETED")
            except (GreenhouseError, ValueError) as error:
                message = f"{board.board_token}: {error}"
                errors.append(message)
                verified_boards.append(replace(board, verified_at=verified_at, active=False))
                if save and run_id:
                    database.save_item_progress(run_id, board.board_token, "FAILED", str(error))

        relevant = relevant[:limit]
        if save and run_id:
            if errors:
                database.interrupt_run(run_id, "; ".join(errors))
            else:
                database.complete_run(run_id)
            if save_registry:
                by_token = {board.board_token: board for board in verified_boards}
                save_board_registry(registry_path, [by_token.get(board.board_token, board) for board in boards])

        return DiscoveryResult(
            run_id=run_id,
            boards_verified=len(verified_boards),
            jobs_retrieved=retrieved,
            jobs_relevant=len(relevant),
            jobs_saved=saved,
            errors=tuple(errors),
            jobs=tuple(relevant),
        )
