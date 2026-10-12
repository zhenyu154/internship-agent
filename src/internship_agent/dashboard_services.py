"""Independently authored read-only synthetic dashboard snapshots and UI filters."""

from dataclasses import dataclass
from pathlib import Path

from . import demo
from .demo_services import DATABASE_LABEL, DemoServices
from .models import ApplicationRecord, ApplicationStatusEvent, JobMetadata, JobRecord
from .ranking import RankingResult
from .resume_review import ResumeDocument, ResumeProposal


@dataclass(frozen=True)
class DashboardSnapshot:
    validation: dict[str, str | int]
    jobs: tuple[JobRecord, ...]
    metadata: dict[int, JobMetadata]
    rankings: tuple[RankingResult, ...]
    applications: tuple[ApplicationRecord, ...]
    history: dict[int, tuple[ApplicationStatusEvent, ...]]
    resume: ResumeDocument
    proposal: ResumeProposal


def load_snapshot(*, database_label: str, public_root: Path) -> DashboardSnapshot:
    services = DemoServices(public_root)
    with services.open_database(database_label) as (database, validation):
        jobs = tuple(database.list_jobs())
        metadata = {record.id: database.get_job_metadata(record.id) for record in jobs}
        rankings = services.ranked_jobs(database)
        applications = tuple(database.list_applications())
        history = {record.job_id: tuple(database.application_history(record.job_id)) for record in applications}
    resume, proposal = services.resume_review()
    return DashboardSnapshot(validation, jobs, metadata, rankings, applications, history, resume, proposal)


def job_rows(snapshot):
    by_id = {record.id: record for record in snapshot.jobs}
    return [{"ID": by_id[result.job_id].job.source_job_id,
             "Position": by_id[result.job_id].job.title, "Company": by_id[result.job_id].job.company,
             "Location": by_id[result.job_id].job.location, "Job Match Score": result.technical_match_score,
             "Eligibility": result.eligibility.status, "Relevance": result.relevance_category,
             "Preparation": result.application_status}
            for result in snapshot.rankings]


def filter_jobs(rows, *, search="", relevance=(), eligibility=(), sort="Score: high to low"):
    term = search.strip().casefold()
    result = [row for row in rows if (not term or any(term in str(row[field]).casefold()
              for field in ("ID", "Position", "Company", "Location")))
              and (not relevance or row["Relevance"] in relevance)
              and (not eligibility or row["Eligibility"] in eligibility)]
    if sort == "Company: A to Z": result.sort(key=lambda row: (row["Company"].casefold(), row["Position"].casefold(), row["ID"]))
    elif sort == "Position: A to Z": result.sort(key=lambda row: (row["Position"].casefold(), row["Company"].casefold(), row["ID"]))
    elif sort == "Score: low to high": result.sort(key=lambda row: (row["Job Match Score"], row["ID"]))
    elif sort != "Score: high to low": raise ValueError("Unsupported presentation sort")
    # Default retains the backend's deterministic score/identity ordering.
    return result
