"""Manual Ashby discovery using shared relevance and SQLite persistence."""

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
from pathlib import Path

from .ashby import AshbyBoard, AshbyClient, AshbyError, AshbyJob, load_ashby_registry, save_ashby_registry
from .config import load_config
from .database import JobDatabase
from .greenhouse import GreenhouseJob, UNKNOWN
from .models import Job, JobMetadata
from .relevance import EXCLUDED, classify_greenhouse_job, preview_priority


@dataclass(frozen=True, slots=True)
class AshbyDiscoveryResult:
    run_id: str | None
    boards_verified: int
    jobs_retrieved: int
    internship_candidates: int
    summer_2027_count: int
    main_shortlist: int
    needs_review: int
    excluded: int
    jobs_saved: int
    errors: tuple[str, ...]
    jobs: tuple[AshbyJob, ...]
    duplicates_skipped: int = 0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _classify(job: AshbyJob, preferences: dict) -> AshbyJob:
    shared = GreenhouseJob(
        company_name=job.company_name,
        board_token=job.board_name,
        source_job_id=job.posting_id,
        title=job.title,
        location=job.location,
        application_url=job.apply_url,
        description=job.description,
        published_at=job.published_at,
        updated_at=UNKNOWN,
        internship_term=job.internship_term,
        degree_requirements=job.degree_requirements,
        graduation_window=job.graduation_window,
        work_authorization=job.work_authorization,
        source_url=job.job_url,
        verified_at=job.verified_at,
    )
    result = classify_greenhouse_job(shared, preferences)
    return replace(job, relevance_category=result.category, relevance_reason=result.reason)


def _store(database: JobDatabase, job: AshbyJob) -> bool:
    if job.posting_id == "UNKNOWN":
        return False
    stored = database.add_job(Job(
        title=job.title,
        company=job.company_name if job.company_name != "UNKNOWN" else job.board_name,
        location=job.location if job.location != "UNKNOWN" else "",
        url=job.apply_url if job.apply_url != "UNKNOWN" else job.job_url,
        source="ashby",
        source_job_id=f"{job.board_name}:{job.posting_id}",
        description=job.description if job.description != "UNKNOWN" else "",
    ))
    database.save_job_metadata(JobMetadata(
        job_id=stored.record.id,
        source_url=job.job_url,
        greenhouse_board_token="",
        published_at=job.published_at,
        updated_at="UNKNOWN",
        internship_term=job.internship_term,
        degree_requirements=job.degree_requirements,
        graduation_window=job.graduation_window,
        work_authorization=job.work_authorization,
        compensation=job.compensation,
        relevance_category=job.relevance_category,
        relevance_reason=job.relevance_reason,
        verified_at=job.verified_at,
    ))
    return stored.created


class AshbyDiscovery:
    def __init__(self, client: AshbyClient | None = None) -> None:
        self.client = client or AshbyClient()

    def discover(self, config_path: str | Path, registry_path: str | Path, *, database: JobDatabase | None = None,
                 limit: int = 10, save: bool = False, resume_run_id: str | None = None,
                 save_registry: bool = False, save_all: bool = False) -> AshbyDiscoveryResult:
        if type(limit) is not int or limit <= 0:
            raise ValueError("limit must be a positive integer")
        config_path = Path(config_path)
        registry_path = Path(registry_path)
        preferences = load_config(config_path)
        boards = load_ashby_registry(registry_path)
        active = [board for board in boards if board.active]
        if save and database is None:
            raise ValueError("database is required when save=True")
        if save_all and not save:
            raise ValueError("save_all requires save=True")
        if resume_run_id and not save:
            raise ValueError("resume_run_id requires save=True")

        run_id = None
        completed = set()
        if save:
            if resume_run_id:
                database.resume_run(resume_run_id)
                run_id = resume_run_id
            else:
                run_id = database.start_run("ashby_discovery", _fingerprint(config_path), []).run_id
            completed = {item.item_key for item in database.get_work_items(run_id) if item.state == "COMPLETED"}

        retrieved = candidates = summer = main = review = excluded = saved = 0
        eligible = []
        processed_boards = []
        duplicates = 0
        errors = []
        verified = []
        for board in active:
            try:
                if board.board_name in completed:
                    verified.append(board)
                    continue
                if save and run_id:
                    database.ensure_work_item(run_id, board.board_name)
                    database.save_item_progress(run_id, board.board_name, "IN_PROGRESS")
                raw_jobs = [
                    job if job.company_name != UNKNOWN else replace(job, company_name=board.company_name)
                    for job in self.client.fetch_board(board.board_name)
                ]
                retrieved += len(raw_jobs)
                board_verified = _now()
                verified.append(replace(board, verified_at=board_verified, active=True))
                for raw in raw_jobs:
                    if raw.is_listed is False:
                        excluded += 1
                        continue
                    classified = _classify(raw, preferences)
                    if raw.employment_type.casefold() in {"intern", "internship", "co-op", "coop"} or "intern" in raw.title.casefold():
                        candidates += 1
                    if classified.internship_term == "Summer 2027":
                        summer += 1
                    if classified.relevance_category == "MAIN_SHORTLIST":
                        main += 1
                    elif classified.relevance_category == "NEEDS_REVIEW":
                        review += 1
                    else:
                        excluded += 1
                    if classified.relevance_category != EXCLUDED:
                        eligible.append(classified)
                        if save and save_all:
                            if _store(database, classified):
                                saved += 1
                            else:
                                duplicates += 1
                processed_boards.append(board.board_name)
                if save and save_all:
                    # A checkpoint is complete only after its jobs are durable.
                    database.save_item_progress(run_id, board.board_name, "COMPLETED")
            except (AshbyError, ValueError) as error:
                errors.append(f"{board.board_name}: {error}")
                verified.append(replace(board, verified_at=_now(), active=False))
                if save and run_id:
                    database.ensure_work_item(run_id, board.board_name)
                    database.save_item_progress(run_id, board.board_name, "FAILED", str(error))
        ordered = sorted(eligible, key=lambda job: preview_priority(job, preferences))
        relevant = ordered[:limit]
        if save and not save_all:
            for candidate in relevant:
                if _store(database, candidate):
                    saved += 1
                else:
                    duplicates += 1
            for board_name in processed_boards:
                database.save_item_progress(run_id, board_name, "COMPLETED")
        if save and run_id:
            if errors:
                database.interrupt_run(run_id, "; ".join(errors))
            else:
                database.complete_run(run_id)
            if save_registry:
                by_name = {board.board_name: board for board in verified}
                save_ashby_registry(registry_path, [by_name.get(board.board_name, board) for board in boards])
        return AshbyDiscoveryResult(run_id, len(verified), retrieved, candidates, summer, main, review, excluded, saved, tuple(errors), tuple(relevant), duplicates)
