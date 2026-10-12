"""Manual Lever discovery using the shared relevance and persistence layers."""

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
import hashlib
from typing import Any

from .config import load_config
from .database import JobDatabase
from .greenhouse import GreenhouseJob
from .lever import LeverClient, LeverError, LeverJob, LeverSite, load_lever_registry, save_lever_registry
from .models import Job, JobMetadata
from .relevance import EXCLUDED, classify_greenhouse_job


@dataclass(frozen=True, slots=True)
class LeverDiscoveryResult:
    run_id: str | None
    sites_verified: int
    jobs_retrieved: int
    jobs_relevant: int
    jobs_saved: int
    errors: tuple[str, ...]
    jobs: tuple[LeverJob, ...]


def _fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _as_greenhouse_job(job: LeverJob) -> GreenhouseJob:
    return GreenhouseJob(
        company_name=job.company_name,
        board_token=job.site_token,
        source_job_id=job.posting_id,
        title=job.title,
        location=job.location,
        application_url=job.apply_url,
        description=job.description,
        published_at="UNKNOWN",
        updated_at="UNKNOWN",
        internship_term=job.internship_term,
        degree_requirements=job.degree_requirements,
        graduation_window=job.graduation_window,
        work_authorization=job.work_authorization,
        source_url=job.hosted_url,
        verified_at=job.verified_at,
    )


def _store_job(database: JobDatabase, job: LeverJob) -> bool:
    if job.posting_id == "UNKNOWN":
        return False
    stored = database.add_job(Job(
        title=job.title,
        company=job.company_name,
        location=job.location if job.location != "UNKNOWN" else "",
        url=job.apply_url if job.apply_url != "UNKNOWN" else "",
        source="lever",
        source_job_id=f"{job.site_token}:{job.posting_id}",
        description=job.description if job.description != "UNKNOWN" else "",
    ))
    database.save_job_metadata(JobMetadata(
        job_id=stored.record.id,
        source_url=job.hosted_url,
        greenhouse_board_token="",
        published_at="UNKNOWN",
        updated_at="UNKNOWN",
        internship_term=job.internship_term,
        degree_requirements=job.degree_requirements,
        graduation_window=job.graduation_window,
        work_authorization=job.work_authorization,
        relevance_category=job.relevance_category,
        relevance_reason=job.relevance_reason,
        verified_at=job.verified_at,
    ))
    return True


class LeverDiscovery:
    def __init__(self, client: LeverClient | None = None) -> None:
        self.client = client or LeverClient()

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
    ) -> LeverDiscoveryResult:
        if type(limit) is not int or limit <= 0:
            raise ValueError("limit must be a positive integer")
        config_path = Path(config_path)
        registry_path = Path(registry_path)
        preferences = load_config(config_path)
        sites = load_lever_registry(registry_path)
        active = [site for site in sites if site.active]
        if not active:
            raise ValueError("Lever registry has no active sites")
        if save and database is None:
            raise ValueError("database is required when save=True")
        if resume_run_id and not save:
            raise ValueError("resume_run_id requires save=True")

        run_id = None
        completed_items: set[str] = set()
        if save:
            if resume_run_id:
                database.resume_run(resume_run_id)
                run_id = resume_run_id
            else:
                run_id = database.start_run("lever_discovery", _fingerprint(config_path), []).run_id
            completed_items = {
                item.item_key for item in database.get_work_items(run_id)
                if item.state == "COMPLETED"
            }

        retrieved = 0
        relevant: list[LeverJob] = []
        saved = 0
        errors: list[str] = []
        verified_sites: list[LeverSite] = []
        for site in active:
            site_ok = True
            verified_at = _now()
            try:
                for page_key, page in self.client.iter_site_pages(site):
                    if save and run_id:
                        database.ensure_work_item(run_id, page_key)
                    if page_key in completed_items:
                        continue
                    retrieved += len(page)
                    for raw_job in page:
                        classification = classify_greenhouse_job(_as_greenhouse_job(raw_job), preferences)
                        job = replace(raw_job, relevance_category=classification.category, relevance_reason=classification.reason)
                        if classification.category != EXCLUDED and len(relevant) < limit:
                            relevant.append(job)
                            if save and database is not None and _store_job(database, job):
                                saved += 1
                    if save and run_id:
                        database.save_item_progress(run_id, page_key, "COMPLETED")
                verified_sites.append(replace(site, active=True, verified_at=verified_at))
            except (LeverError, ValueError) as error:
                site_ok = False
                message = f"{site.site_token}: {error}"
                errors.append(message)
                verified_sites.append(replace(site, active=False, verified_at=verified_at))
                if save and run_id:
                    errors_item = f"{site.site_token}:0"
                    database.ensure_work_item(run_id, errors_item)
                    database.save_item_progress(run_id, errors_item, "FAILED", str(error))
            if not site_ok:
                continue

        if save and run_id:
            if errors:
                database.interrupt_run(run_id, "; ".join(errors))
            else:
                database.complete_run(run_id)
            if save_registry:
                verified = {site.site_token: site for site in verified_sites}
                save_lever_registry(registry_path, [verified.get(site.site_token, site) for site in sites])
        return LeverDiscoveryResult(
            run_id=run_id,
            sites_verified=len(verified_sites),
            jobs_retrieved=retrieved,
            jobs_relevant=len(relevant),
            jobs_saved=saved,
            errors=tuple(errors),
            jobs=tuple(relevant),
        )
