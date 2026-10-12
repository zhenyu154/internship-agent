"""Local application validation and read-only opportunity views; no network calls."""

from dataclasses import dataclass
from datetime import date
import re
from types import SimpleNamespace

from .models import ApplicationRecord, JobMetadata, JobRecord
from .relevance import EXCLUDED, MAIN_SHORTLIST, NEEDS_REVIEW, preview_priority

APPLICATION_STATUSES = (
    "NOT_STARTED", "RESEARCHING", "PREPARING", "READY_TO_APPLY", "APPLIED",
    "INTERVIEWING", "OFFER", "REJECTED", "WITHDRAWN", "CLOSED",
)
PRE_SUBMISSION = frozenset(APPLICATION_STATUSES[:4])
# Forward preparation steps may be skipped; returning to an earlier preparation
# step is explicit. Post-submission outcomes never erase the submitted date.
STATUS_TRANSITIONS = {
    **{status: PRE_SUBMISSION | {"WITHDRAWN", "CLOSED"} for status in PRE_SUBMISSION},
    "APPLIED": frozenset({"APPLIED", "INTERVIEWING", "REJECTED", "WITHDRAWN", "CLOSED"}),
    "INTERVIEWING": frozenset({"INTERVIEWING", "OFFER", "REJECTED", "WITHDRAWN", "CLOSED"}),
    "OFFER": frozenset({"OFFER", "WITHDRAWN", "CLOSED"}),
    **{status: frozenset({status}) for status in ("REJECTED", "WITHDRAWN", "CLOSED")},
}


class ApplicationStateError(ValueError):
    """Invalid manual application data or transition."""


def validate_status(status: str) -> str:
    if status not in APPLICATION_STATUSES:
        raise ApplicationStateError(f"Invalid application status: {status}")
    return status


def validate_date(value: str, name: str, *, submitted: bool = False) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ApplicationStateError(f"{name} must be YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ApplicationStateError(f"{name} is not a valid calendar date") from error
    if submitted and parsed > date.today():
        raise ApplicationStateError("submitted_at cannot be in the future")
    return value


def text(value: str, name: str, *, required: bool = False) -> str:
    if not isinstance(value, str) or (required and not value.strip()):
        raise ApplicationStateError(f"{name} must be {'a non-empty' if required else 'a'} string")
    return value.strip()


@dataclass(frozen=True)
class ApplicationOpportunity:
    record: JobRecord
    metadata: JobMetadata | None
    application: ApplicationRecord | None
    priority: tuple

    @property
    def status(self) -> str:
        return self.application.status if self.application else "NOT_STARTED"

    @property
    def classification(self) -> str:
        return self.metadata.relevance_category if self.metadata else "UNKNOWN"


def application_opportunities(database, *, status=None, high_priority=False,
                              include_excluded=False, preferences=None):
    """Untracked jobs are views, never implicit application inserts.

    Only confirmed relevant/review classifications enter the unstarted queue.
    Explicitly tracked jobs remain visible even after exclusion or feed removal.
    """
    if status is not None:
        validate_status(status)
    applications = {a.job_id: a for a in database.list_applications()}
    result = []
    for record in database.list_jobs():
        metadata = database.get_job_metadata(record.id)
        classification = metadata.relevance_category if metadata else "UNKNOWN"
        application = applications.get(record.id)
        if application is None and not include_excluded and classification not in (MAIN_SHORTLIST, NEEDS_REVIEW):
            continue
        job = record.job
        priority = preview_priority(SimpleNamespace(
            title=job.title, description=job.description, location=job.location,
            company_name=job.company, posting_id=job.source_job_id,
        ), preferences)
        entry = ApplicationOpportunity(record, metadata, application, priority)
        if status is not None and entry.status != status:
            continue
        if high_priority and priority[0] > 2:
            continue
        result.append(entry)
    return sorted(result, key=lambda entry: (*entry.priority, entry.record.id))
