"""SYNTHETIC DEMONSTRATION DATA — NOT REAL JOB POSTINGS.

Manual offline initialization; fixed public fixture and output paths only.
"""

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

from .applications import PRE_SUBMISSION, text, validate_status
from .candidate_evidence import SOURCE_FILES, load_candidate_evidence
from .config import load_config
from .database import JobDatabase
from .deduplication import job_identity_keys
from .models import Job, JobMetadata
from .relevance import classify_greenhouse_job

NOTICE = "SYNTHETIC DEMONSTRATION DATA — NOT REAL JOB POSTINGS."
PUBLIC_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIRECTORY = PUBLIC_ROOT / "demo" / "fixtures"
OUTPUT_DIRECTORY = PUBLIC_ROOT / "data" / "demo"
OUTPUT_ROOT = PUBLIC_ROOT
PREFERENCES = PUBLIC_ROOT / "config" / "search_preferences.example.yaml"
RUN_ID = "synthetic-demo-v1"
RUN_TYPE = "SYNTHETIC_DEMO"
INTERRUPTION_NOTICE = NOTICE + " Initialization interrupted; explicit recovery required."


@dataclass(frozen=True)
class DemoEntry:
    job: Job
    metadata: dict[str, str]
    application: dict[str, str] | None


@dataclass(frozen=True)
class DemoResult:
    path: Path
    jobs: int
    applications: int
    validation: dict[str, str | int]
    fixture_fingerprint: str


def _reject_links(path: Path) -> None:
    for component in (path, *path.parents):
        if component.is_symlink() or component.is_junction():
            raise ValueError("Demo paths must not contain symlinks or directory junctions")


def load_demo_fixtures() -> tuple[tuple[DemoEntry, ...], str]:
    """Validate only the fixed public fixtures before any database creation."""
    files = [FIXTURE_DIRECTORY / "jobs.json", PREFERENCES,
             *(FIXTURE_DIRECTORY / "evidence" / name for name in (*SOURCE_FILES, "ranking_features.json"))]
    for path in files:
        _reject_links(path)
        if not path.resolve().is_relative_to(PUBLIC_ROOT.resolve()):
            raise ValueError("Demo fixture path must remain in the public workspace")
    contents = [path.read_bytes() for path in files]
    for content in (contents[0], *contents[2:]):
        if NOTICE not in content.decode("utf-8"):
            raise ValueError("Every demo fixture must include the synthetic notice")
    load_candidate_evidence(FIXTURE_DIRECTORY / "evidence")
    preferences = load_config(PREFERENCES)
    raw = json.loads(contents[0].decode("utf-8"))
    if set(raw) != {"version", "notice", "jobs"} or raw["version"] != 1 or raw["notice"] != NOTICE:
        raise ValueError("Invalid synthetic job fixture header")
    if not isinstance(raw["jobs"], list) or not 8 <= len(raw["jobs"]) <= 12:
        raise ValueError("Demo requires 8–12 fictional jobs")
    entries, identities = [], set()
    for entry in raw["jobs"]:
        if set(entry) != {"job", "metadata", "application"}:
            raise ValueError("Unexpected demo job fields")
        job = Job(**entry["job"])
        # Fixed reserved URLs and fictional identities are not live ATS records.
        expected_url = f"https://example.test/internships/{job.source_job_id}"
        if (job.source != "synthetic_demo" or not job.source_job_id.startswith("demo-")
                or job.url != expected_url or not job.company.startswith("Fictional ")
                or not job.description.startswith(NOTICE)):
            raise ValueError("Demo jobs must have fictional identities, reserved URLs and notices")
        keys = set(job_identity_keys(job))
        if keys & identities:
            raise ValueError("Duplicate demo job identity")
        identities.update(keys)
        fields = entry["metadata"]
        if set(fields) != {"internship_term", "degree_requirements", "graduation_window", "work_authorization"}:
            raise ValueError("Unexpected demo metadata fields")
        if any(not isinstance(value, str) or not value.strip() for value in fields.values()):
            raise ValueError("Demo metadata must contain non-empty strings")
        classification = classify_greenhouse_job(SimpleNamespace(**asdict(job), **fields), preferences)
        metadata = {**fields, "source_url": job.url,
                    "relevance_category": classification.category,
                    "relevance_reason": NOTICE + " " + classification.reason,
                    "verified_at": "SYNTHETIC_FIXTURE_NOT_VERIFIED"}
        application = entry["application"]
        if application is not None:
            if set(application) != {"status", "notes"}:
                raise ValueError("Unexpected demo application fields")
            if validate_status(application["status"]) not in PRE_SUBMISSION:
                raise ValueError("Demo application records must remain in preparation states")
            if not text(application["notes"], "demo notes", required=True).startswith(NOTICE):
                raise ValueError("Demo notes must include the synthetic notice")
        entries.append(DemoEntry(job, metadata, application))
    fingerprint = hashlib.sha256()
    for path, content in zip(files, contents):
        fingerprint.update(path.relative_to(PUBLIC_ROOT).as_posix().encode("utf-8") + b"\0")
        fingerprint.update(content + b"\0")
    return tuple(entries), fingerprint.hexdigest()


def _check_progress(database: JobDatabase, entries: tuple[DemoEntry, ...], fingerprint: str) -> None:
    """Fail closed on unrelated databases, changed fixtures or edited records."""
    database.validate_schema_layout()
    database.validate_integrity()
    runs = database.list_runs()
    if (len(runs) != 1 or runs[0].run_id != RUN_ID or runs[0].run_type != RUN_TYPE
            or runs[0].config_fingerprint != fingerprint
            or runs[0].status not in {"RUNNING", "INTERRUPTED", "COMPLETED"}):
        raise ValueError("Partial database is not a compatible synthetic demo run")
    expected = {entry.job.source_job_id: entry for entry in entries}
    items = database.get_work_items(RUN_ID)
    if {item.item_key for item in items} != set(expected):
        raise ValueError("Partial demo work items do not match the fixtures")
    completed = {item.item_key for item in items if item.state == "COMPLETED"}
    run = runs[0]
    expected_error = INTERRUPTION_NOTICE if run.status == "INTERRUPTED" else ""
    if (run.error_summary != expected_error
            or any(item.state not in {"PENDING", "IN_PROGRESS", "COMPLETED"} or item.error_details for item in items)
            or (run.work_item_total, run.work_item_completed, run.work_item_failed) != (len(items), len(completed), 0)
            or (run.status == "COMPLETED" and len(completed) != len(expected))):
        raise ValueError("Unexpected run progress or diagnostics; preserving the existing database")
    records = database.list_jobs()
    identities = {(key, record.id) for record in records for key in job_identity_keys(record.job)}
    if set(database.list_job_identities()) != identities:
        raise ValueError("Unexpected job identity aliases; preserving the existing database")
    if database.load_discovery_checkpoints(RUN_ID):
        raise ValueError("Unexpected discovery checkpoint data; preserving the existing database")
    if not completed <= {record.job.source_job_id for record in records}:
        raise ValueError("Completed demo item has no job record; preserving the existing database")
    for record in records:
        entry = expected.get(record.job.source_job_id)
        if entry is None or entry.job != record.job:
            raise ValueError("Existing job differs from its synthetic fixture; preserving it")
        metadata = database.get_job_metadata(record.id)
        if metadata is not None and metadata != JobMetadata(record.id, **entry.metadata):
            raise ValueError("Existing metadata differs from its synthetic fixture; preserving it")
        application = database.get_application(record.id)
        if record.job.source_job_id in completed:
            if (metadata != JobMetadata(record.id, **entry.metadata)
                    or (entry.application is not None and (application is None
                        or application.status != entry.application["status"]
                        or application.notes != entry.application["notes"]))):
                raise ValueError("Completed demo payload is incomplete; preserving the existing database")
        if application is not None:
            wanted = entry.application
            if (wanted is None or application.status not in {"NOT_STARTED", wanted["status"]}
                    or application.notes not in {"", wanted["notes"]}
                    or any((application.submitted_at, application.receipt_reference,
                            application.follow_up_at, application.deadline))):
                raise ValueError("Existing application differs from its synthetic fixture; preserving it")
            history = database.application_history(record.id)
            expected_statuses = ["NOT_STARTED"]
            if wanted["status"] != "NOT_STARTED":
                expected_statuses.append(wanted["status"])
            if ([event.new_status for event in history] != expected_statuses[:len(history)]
                    or not 1 <= len(history) <= len(expected_statuses)
                    or history[-1].new_status != application.status
                    or history[0].previous_status is not None
                    or history[0].event != "HUMAN_CREATE" or history[0].reason != ""
                    or (len(history) == 2 and (history[1].previous_status != "NOT_STARTED"
                        or history[1].event != "HUMAN_STATUS_CHANGE" or history[1].reason != NOTICE))):
                raise ValueError("Existing application history differs from initialization; preserving it")


def validate_completed_demo(database: JobDatabase) -> dict[str, str | int]:
    """Read-only complete-demo verification shared by public inspection clients.

    The caller explicitly selects and opens a read-only database. No creation,
    recovery, migration or selection/fallback behavior occurs in this function.
    """
    entries, fingerprint = load_demo_fixtures()
    _check_progress(database, entries, fingerprint)
    run = database.get_run(RUN_ID)
    if (run.status != "COMPLETED" or database.count_jobs() != len(entries)
            or len(database.list_applications()) != sum(entry.application is not None for entry in entries)):
        raise ValueError("Read-only inspection requires a complete synthetic demo")
    return {**database.validate_integrity(), "jobs": len(entries),
            "applications": sum(entry.application is not None for entry in entries),
            "run_status": run.status, "fixture_fingerprint": fingerprint}


def create_demo(*, resume: bool = False) -> DemoResult:
    """Create or explicitly recover one owned demo; never open an existing final DB."""
    entries, fingerprint = load_demo_fixtures()
    directory = OUTPUT_DIRECTORY
    if not directory.absolute().is_relative_to(OUTPUT_ROOT.absolute()):
        raise ValueError("Demo output must remain in the public workspace")
    _reject_links(directory)
    final = directory / "demo.sqlite3"
    pending = directory / "demo.building.sqlite3"
    lock = directory / "demo.lock"
    for path in (final, pending, lock, *(Path(str(database) + suffix)
                                       for database in (final, pending)
                                       for suffix in ("-wal", "-shm", "-journal"))):
        _reject_links(path)
    if any(os.path.lexists(str(final) + suffix) for suffix in ("", "-wal", "-shm", "-journal")):
        raise FileExistsError("Demo output already exists; no overwrite is permitted")
    pending_exists = os.path.lexists(pending)
    if pending_exists != resume:
        raise FileExistsError("Partial demo exists; use --resume explicitly" if pending_exists
                              else "No partial demo exists to resume")
    if not resume and any(os.path.lexists(str(pending) + suffix) for suffix in ("-wal", "-shm", "-journal")):
        raise FileExistsError("Partial database sidecars exist; review disposable output first")
    directory.mkdir(parents=True, exist_ok=True)
    # Exclusive lock serializes explicit runs, including recovery. A hard crash
    # leaves this lock for human review; never silently steal another run's lock.
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(NOTICE + "\n")
        if resume:
            with JobDatabase(pending, read_only=True) as database:
                _check_progress(database, entries, fingerprint)
        else:
            descriptor = os.open(pending, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
        with JobDatabase(pending) as database:
            if not resume:
                database.start_run(RUN_TYPE, fingerprint,
                                   (entry.job.source_job_id for entry in entries), RUN_ID)
            else:
                run = database.get_run(RUN_ID)
                if run.status != "COMPLETED":
                    database.resume_run(RUN_ID)
            try:
                run = database.get_run(RUN_ID)
                if run.status != "COMPLETED":
                    completed = {item.item_key for item in database.get_work_items(RUN_ID)
                                 if item.state == "COMPLETED"}
                    for entry in entries:
                        key = entry.job.source_job_id
                        if key in completed:
                            continue
                        database.save_item_progress(RUN_ID, key, "IN_PROGRESS")
                        record = database.add_job(entry.job).record
                        database.save_job_metadata(JobMetadata(record.id, **entry.metadata))
                        if entry.application:
                            application = database.create_application(record.id)
                            if application.status == "NOT_STARTED":
                                database.set_application_status(record.id, entry.application["status"], reason=NOTICE)
                            if not database.get_application(record.id).notes:
                                database.add_application_note(record.id, entry.application["notes"])
                        database.save_item_progress(RUN_ID, key, "COMPLETED")
                    database.complete_run(RUN_ID)
                _check_progress(database, entries, fingerprint)
                if database.count_jobs() != len(entries):
                    raise ValueError("Demo job count does not match the fixtures")
                applications = database.list_applications()
                if len(applications) != sum(entry.application is not None for entry in entries):
                    raise ValueError("Demo application count does not match the fixtures")
                for record, entry in zip(database.list_jobs(), entries):
                    if database.get_job_metadata(record.id) != JobMetadata(record.id, **entry.metadata):
                        raise ValueError("Demo metadata is incomplete")
                    if entry.application:
                        application = database.get_application(record.id)
                        if (application.status != entry.application["status"]
                                or application.notes != entry.application["notes"]):
                            raise ValueError("Demo application is incomplete")
                validation = database.validate_integrity()
            except BaseException:
                if database.get_run(RUN_ID).status == "RUNNING":
                    database.interrupt_run(RUN_ID, INTERRUPTION_NOTICE)
                raise
        # Atomic no-clobber publication. Another file appearing at the final path
        # causes failure; os.replace() would violate the no-overwrite guarantee.
        os.link(pending, final)
        pending.unlink()
        return DemoResult(final, len(entries), len(applications), validation, fingerprint)
    finally:
        lock.unlink()
