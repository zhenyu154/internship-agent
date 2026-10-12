"""Validated job inputs and immutable persistence results."""

from dataclasses import dataclass, fields


@dataclass(frozen=True, slots=True)
class Job:
    title: str
    company: str
    location: str = ""
    url: str = ""
    source: str = ""
    source_job_id: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if not isinstance(value, str):
                raise ValueError(f"{field.name} must be a string")
            object.__setattr__(self, field.name, value.strip())
        for name in ("title", "company"):
            if not getattr(self, name):
                raise ValueError(f"{name} must not be empty")
        if self.source_job_id and not self.source:
            raise ValueError("source is required when source_job_id is provided")


@dataclass(frozen=True, slots=True)
class JobRecord:
    id: int
    job: Job
    created_at: str


@dataclass(frozen=True, slots=True)
class AddJobResult:
    record: JobRecord
    created: bool


@dataclass(frozen=True, slots=True)
class RunRecord:
    run_id: str
    run_type: str
    started_at: str
    completed_at: str | None
    status: str
    config_fingerprint: str
    work_item_total: int
    work_item_completed: int
    work_item_failed: int
    last_progress_at: str
    error_summary: str


@dataclass(frozen=True, slots=True)
class WorkItemRecord:
    run_id: str
    item_key: str
    state: str
    last_updated_at: str
    error_details: str


@dataclass(frozen=True, slots=True)
class JobMetadata:
    job_id: int
    source_url: str = ""
    greenhouse_board_token: str = ""
    published_at: str = "UNKNOWN"
    updated_at: str = "UNKNOWN"
    internship_term: str = "UNKNOWN"
    degree_requirements: str = "UNKNOWN"
    graduation_window: str = "UNKNOWN"
    work_authorization: str = "UNKNOWN"
    compensation: str = "UNKNOWN"
    relevance_category: str = "UNKNOWN"
    relevance_reason: str = "UNKNOWN"
    verified_at: str = ""


@dataclass(frozen=True, slots=True)
class ApplicationRecord:
    job_id: int
    status: str
    status_updated_at: str
    submitted_at: str | None
    follow_up_at: str | None
    deadline: str | None
    deadline_evidence: str
    deadline_verified_at: str | None
    notes: str
    receipt_reference: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class ApplicationStatusEvent:
    id: int
    job_id: int
    previous_status: str | None
    new_status: str
    occurred_at: str
    event: str
    reason: str
