"""SQLite persistence for jobs and manual, resumable execution state."""

from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import json
from types import TracebackType
from uuid import uuid4

from .applications import (
    APPLICATION_STATUSES, PRE_SUBMISSION, STATUS_TRANSITIONS, ApplicationStateError,
    text, validate_date, validate_status,
)
from .deduplication import job_identity_keys
from .models import (
    AddJobResult,
    ApplicationRecord,
    ApplicationStatusEvent,
    Job,
    JobMetadata,
    JobRecord,
    RunRecord,
    WorkItemRecord,
)

SCHEMA_VERSION = 6
RUN_STATUSES = frozenset({"RUNNING", "COMPLETED", "INTERRUPTED", "FAILED"})
WORK_ITEM_STATES = frozenset({"PENDING", "IN_PROGRESS", "COMPLETED", "FAILED"})

_RUN_TRANSITIONS = {
    "RUNNING": frozenset({"RUNNING", "COMPLETED", "INTERRUPTED", "FAILED"}),
    "COMPLETED": frozenset({"COMPLETED"}),
    "INTERRUPTED": frozenset({"INTERRUPTED", "RUNNING", "FAILED"}),
    "FAILED": frozenset({"FAILED"}),
}
_ITEM_TRANSITIONS = {
    "PENDING": frozenset({"PENDING", "IN_PROGRESS", "COMPLETED", "FAILED"}),
    "IN_PROGRESS": frozenset({"PENDING", "IN_PROGRESS", "COMPLETED", "FAILED"}),
    "COMPLETED": frozenset({"COMPLETED"}),
    "FAILED": frozenset({"PENDING", "IN_PROGRESS", "COMPLETED", "FAILED"}),
}

_JOB_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY,
        title TEXT NOT NULL CHECK (length(trim(title)) > 0),
        company TEXT NOT NULL CHECK (length(trim(company)) > 0),
        location TEXT NOT NULL DEFAULT '',
        url TEXT NOT NULL DEFAULT '',
        source TEXT NOT NULL DEFAULT '',
        source_job_id TEXT NOT NULL DEFAULT '',
        description TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
        CHECK (source_job_id = '' OR length(trim(source)) > 0)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS job_identities (
        identity_key TEXT PRIMARY KEY,
        job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS job_identities_job_id ON job_identities(job_id)",
)

_EXECUTION_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS execution_runs (
        run_id TEXT PRIMARY KEY,
        run_type TEXT NOT NULL CHECK (length(trim(run_type)) > 0),
        started_at TEXT NOT NULL,
        completed_at TEXT,
        status TEXT NOT NULL CHECK (status IN ('RUNNING', 'COMPLETED', 'INTERRUPTED', 'FAILED')),
        config_fingerprint TEXT NOT NULL CHECK (length(trim(config_fingerprint)) > 0),
        work_item_total INTEGER NOT NULL DEFAULT 0 CHECK (work_item_total >= 0),
        work_item_completed INTEGER NOT NULL DEFAULT 0 CHECK (work_item_completed >= 0),
        work_item_failed INTEGER NOT NULL DEFAULT 0 CHECK (work_item_failed >= 0),
        last_progress_at TEXT NOT NULL,
        error_summary TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS work_items (
        run_id TEXT NOT NULL REFERENCES execution_runs(run_id),
        item_key TEXT NOT NULL CHECK (length(trim(item_key)) > 0),
        state TEXT NOT NULL CHECK (state IN ('PENDING', 'IN_PROGRESS', 'COMPLETED', 'FAILED')),
        last_updated_at TEXT NOT NULL,
        error_details TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (run_id, item_key)
    )
    """,
    "CREATE INDEX IF NOT EXISTS work_items_run_state ON work_items(run_id, state)",
)

_METADATA_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS job_metadata (
        job_id INTEGER PRIMARY KEY REFERENCES jobs(id),
        source_url TEXT NOT NULL DEFAULT '',
        greenhouse_board_token TEXT NOT NULL DEFAULT '',
        published_at TEXT NOT NULL DEFAULT 'UNKNOWN',
        updated_at TEXT NOT NULL DEFAULT 'UNKNOWN',
        internship_term TEXT NOT NULL DEFAULT 'UNKNOWN',
        degree_requirements TEXT NOT NULL DEFAULT 'UNKNOWN',
        graduation_window TEXT NOT NULL DEFAULT 'UNKNOWN',
        work_authorization TEXT NOT NULL DEFAULT 'UNKNOWN',
        compensation TEXT NOT NULL DEFAULT 'UNKNOWN',
        relevance_category TEXT NOT NULL DEFAULT 'UNKNOWN',
        relevance_reason TEXT NOT NULL DEFAULT 'UNKNOWN',
        verified_at TEXT NOT NULL
    )
    """,
)


_CHECKPOINT_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS discovery_checkpoints (
        run_id TEXT NOT NULL,
        item_key TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        saved_at TEXT NOT NULL,
        PRIMARY KEY (run_id, item_key),
        FOREIGN KEY (run_id, item_key) REFERENCES work_items(run_id, item_key)
    )
    """,
)


_APPLICATION_STATUS_SQL = ", ".join(f"'{status}'" for status in APPLICATION_STATUSES)
_APPLICATION_SCHEMA = (
    f"""
    CREATE TABLE IF NOT EXISTS applications (
        job_id INTEGER PRIMARY KEY REFERENCES jobs(id),
        status TEXT NOT NULL CHECK (status IN ({_APPLICATION_STATUS_SQL})),
        status_updated_at TEXT NOT NULL,
        submitted_at TEXT,
        follow_up_at TEXT,
        deadline TEXT,
        deadline_evidence TEXT NOT NULL DEFAULT '',
        deadline_verified_at TEXT,
        notes TEXT NOT NULL DEFAULT '',
        receipt_reference TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        CHECK (status NOT IN ('APPLIED', 'INTERVIEWING', 'OFFER') OR submitted_at IS NOT NULL),
        CHECK ((deadline IS NULL AND deadline_evidence = '' AND deadline_verified_at IS NULL)
               OR (deadline IS NOT NULL AND length(trim(deadline_evidence)) > 0
                   AND deadline_verified_at IS NOT NULL))
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS application_status_history (
        id INTEGER PRIMARY KEY,
        job_id INTEGER NOT NULL REFERENCES applications(job_id),
        previous_status TEXT CHECK (previous_status IS NULL OR previous_status IN ({_APPLICATION_STATUS_SQL})),
        new_status TEXT NOT NULL CHECK (new_status IN ({_APPLICATION_STATUS_SQL})),
        occurred_at TEXT NOT NULL,
        event TEXT NOT NULL CHECK (event IN ('HUMAN_CREATE', 'HUMAN_STATUS_CHANGE',
                                            'HUMAN_SUBMISSION_CONFIRMATION', 'SYSTEM_EVENT')),
        reason TEXT NOT NULL DEFAULT '',
        CHECK (new_status != 'APPLIED' OR event = 'HUMAN_SUBMISSION_CONFIRMATION')
    )
    """,
    "CREATE INDEX IF NOT EXISTS application_history_job_id ON application_status_history(job_id, id)",
    """CREATE TRIGGER IF NOT EXISTS application_history_no_update
       BEFORE UPDATE ON application_status_history BEGIN
       SELECT RAISE(ABORT, 'Application status history is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS application_history_no_delete
       BEFORE DELETE ON application_status_history BEGIN
       SELECT RAISE(ABORT, 'Application status history is append-only'); END""",
)


class DeduplicationConflictError(ValueError):
    """A submitted job connects identities belonging to different saved jobs."""


class RunStateError(ValueError):
    """A run or work-item state transition is invalid."""


class RunNotFoundError(RunStateError):
    """The requested execution run does not exist."""


class DuplicateRunError(RunStateError):
    """The requested run ID already exists."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


class JobDatabase:
    def __init__(self, path: str | Path, *, read_only: bool = False) -> None:
        self.path = Path(path)
        if not read_only:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migration_backup_path: Path | None = None
        target = self.path.resolve().as_uri() + "?mode=ro" if read_only else self.path
        self._connection = sqlite3.connect(target, timeout=10, uri=read_only)
        self._connection.row_factory = sqlite3.Row
        try:
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute("PRAGMA busy_timeout = 10000")
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise ValueError(f"Unsupported database schema version: {version}")
            if read_only:
                self._connection.execute("PRAGMA query_only = ON")
                if version != SCHEMA_VERSION:
                    raise ValueError("Read-only access requires current schema; migrate explicitly with init first")
            elif version == 0:
                self._create_schema()
            elif version < SCHEMA_VERSION:
                self.migration_backup_path = self._backup_before_migration()
                if version == 1:
                    self._migrate_v1_to_v2()
                if version <= 2:
                    self._migrate_v2_to_v3()
                if version <= 3:
                    self._migrate_v3_to_v4()
                if version <= 4:
                    self._migrate_v4_to_v5()
                self._migrate_v5_to_v6()
        except Exception:
            self._connection.close()
            raise

    def _create_schema(self) -> None:
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            for statement in (*_JOB_SCHEMA, *_EXECUTION_SCHEMA, *_METADATA_SCHEMA, *_CHECKPOINT_SCHEMA, *_APPLICATION_SCHEMA):
                self._connection.execute(statement)
            self._connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _backup_before_migration(self) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = self.path.with_name(
            f"{self.path.name}.pre-v{SCHEMA_VERSION}-{timestamp}-{uuid4().hex[:8]}.bak"
        )
        backup_connection = sqlite3.connect(backup)
        try:
            self._connection.backup(backup_connection)
            if backup_connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise sqlite3.DatabaseError("Pre-migration backup failed integrity verification")
        finally:
            backup_connection.close()
        return backup

    def _migrate_v1_to_v2(self) -> None:
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            for statement in _EXECUTION_SCHEMA:
                self._connection.execute(statement)
            self._connection.execute("PRAGMA user_version = 2")

    def _migrate_v2_to_v3(self) -> None:
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            for statement in _METADATA_SCHEMA:
                self._connection.execute(statement)
            self._connection.execute("PRAGMA user_version = 3")

    def _migrate_v3_to_v4(self) -> None:
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            columns = {row[1] for row in self._connection.execute("PRAGMA table_info(job_metadata)")}
            if "compensation" not in columns:
                self._connection.execute("ALTER TABLE job_metadata ADD COLUMN compensation TEXT NOT NULL DEFAULT 'UNKNOWN'")
            self._connection.execute("PRAGMA user_version = 4")

    def _migrate_v4_to_v5(self) -> None:
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            for statement in _CHECKPOINT_SCHEMA:
                self._connection.execute(statement)
            self._connection.execute("PRAGMA user_version = 5")

    def _migrate_v5_to_v6(self) -> None:
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            for statement in _APPLICATION_SCHEMA:
                self._connection.execute(statement)
            self._connection.execute("PRAGMA user_version = 6")

    def __enter__(self) -> "JobDatabase":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._connection.close()

    def add_job(self, job: Job, *, source_identity_only: bool = False) -> AddJobResult:
        keys = job_identity_keys(job)
        if source_identity_only:
            if not job.source or not job.source_job_id:
                raise ValueError("source_identity_only requires a source and source_job_id")
            keys = (keys[0],)
        placeholders = ", ".join("?" for _ in keys)
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            matches = self._connection.execute(
                f"SELECT DISTINCT job_id FROM job_identities "
                f"WHERE identity_key IN ({placeholders})",
                keys,
            ).fetchall()
            if len(matches) > 1:
                ids = sorted(row["job_id"] for row in matches)
                raise DeduplicationConflictError(
                    f"Job identities refer to multiple existing jobs: {ids}"
                )
            created = not matches
            if matches:
                job_id = matches[0]["job_id"]
            else:
                cursor = self._connection.execute(
                    "INSERT INTO jobs "
                    "(title, company, location, url, source, source_job_id, description) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (job.title, job.company, job.location, job.url,
                     job.source, job.source_job_id, job.description),
                )
                job_id = cursor.lastrowid
            self._connection.executemany(
                "INSERT INTO job_identities (identity_key, job_id) VALUES (?, ?) "
                "ON CONFLICT(identity_key) DO NOTHING",
                ((key, job_id) for key in keys),
            )
            record = self.get_job(job_id)
            if record is None:
                raise RuntimeError("Stored job could not be read back")
        return AddJobResult(record=record, created=created)

    @staticmethod
    def _record(row: sqlite3.Row) -> JobRecord:
        return JobRecord(
            id=row["id"],
            job=Job(
                title=row["title"], company=row["company"],
                location=row["location"], url=row["url"],
                source=row["source"], source_job_id=row["source_job_id"],
                description=row["description"],
            ),
            created_at=row["created_at"],
        )

    @staticmethod
    def _run_record(row: sqlite3.Row) -> RunRecord:
        return RunRecord(
            run_id=row["run_id"], run_type=row["run_type"],
            started_at=row["started_at"], completed_at=row["completed_at"],
            status=row["status"], config_fingerprint=row["config_fingerprint"],
            work_item_total=row["work_item_total"],
            work_item_completed=row["work_item_completed"],
            work_item_failed=row["work_item_failed"],
            last_progress_at=row["last_progress_at"],
            error_summary=row["error_summary"],
        )

    @staticmethod
    def _item_record(row: sqlite3.Row) -> WorkItemRecord:
        return WorkItemRecord(
            run_id=row["run_id"], item_key=row["item_key"], state=row["state"],
            last_updated_at=row["last_updated_at"], error_details=row["error_details"],
        )

    def get_job(self, job_id: int) -> JobRecord | None:
        row = self._connection.execute(
            "SELECT * FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return self._record(row) if row is not None else None

    def list_jobs(self) -> list[JobRecord]:
        rows = self._connection.execute("SELECT * FROM jobs ORDER BY id").fetchall()
        return [self._record(row) for row in rows]

    def count_jobs(self) -> int:
        return self._connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]

    def validate_integrity(self) -> dict[str, str | int]:
        """Check the current schema and SQLite integrity without changing records."""
        integrity = [row[0] for row in self._connection.execute("PRAGMA integrity_check")]
        foreign_keys = self._connection.execute("PRAGMA foreign_key_check").fetchall()
        version = self._connection.execute("PRAGMA user_version").fetchone()[0]
        if integrity != ["ok"] or foreign_keys or version != SCHEMA_VERSION:
            raise sqlite3.DatabaseError("Database integrity, foreign keys or schema validation failed")
        return {"integrity_check": "ok", "foreign_key_violations": 0, "schema_version": version}

    def validate_schema_layout(self) -> None:
        """Require the exact fresh schema for ownership-sensitive demo recovery.

        Ordinary user databases may retain migration-specific SQL formatting;
        this stricter check is only used by the synthetic initializer.
        """
        query = "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name"
        reference = sqlite3.connect(":memory:")
        try:
            for statement in (*_JOB_SCHEMA, *_EXECUTION_SCHEMA, *_METADATA_SCHEMA,
                              *_CHECKPOINT_SCHEMA, *_APPLICATION_SCHEMA):
                reference.execute(statement)
            expected = reference.execute(query).fetchall()
        finally:
            reference.close()
        actual = [tuple(row) for row in self._connection.execute(query)]
        if actual != expected:
            raise sqlite3.DatabaseError("Unexpected schema objects; preserving the existing database")

    def list_job_identities(self) -> list[tuple[str, int]]:
        return [tuple(row) for row in self._connection.execute(
            "SELECT identity_key, job_id FROM job_identities ORDER BY identity_key"
        )]

    def get_job_metadata(self, job_id: int) -> JobMetadata | None:
        row = self._connection.execute(
            "SELECT * FROM job_metadata WHERE job_id = ?", (job_id,)
        ).fetchone()
        if row is None:
            return None
        return JobMetadata(
            job_id=row["job_id"],
            source_url=row["source_url"],
            greenhouse_board_token=row["greenhouse_board_token"],
            published_at=row["published_at"],
            updated_at=row["updated_at"],
            internship_term=row["internship_term"],
            degree_requirements=row["degree_requirements"],
            graduation_window=row["graduation_window"],
            work_authorization=row["work_authorization"],
            compensation=row["compensation"],
            relevance_category=row["relevance_category"],
            relevance_reason=row["relevance_reason"],
            verified_at=row["verified_at"],
        )

    def save_job_metadata(self, metadata: JobMetadata) -> JobMetadata:
        if not isinstance(metadata.job_id, int):
            raise ValueError("job_id must be an integer")
        verified_at = _required_text(metadata.verified_at, "verified_at")
        fields = (
            metadata.source_url, metadata.greenhouse_board_token,
            metadata.published_at, metadata.updated_at, metadata.internship_term,
            metadata.degree_requirements, metadata.graduation_window,
            metadata.work_authorization, metadata.compensation, metadata.relevance_category,
            metadata.relevance_reason, verified_at,
        )
        if any(not isinstance(value, str) for value in fields):
            raise ValueError("job metadata fields must be strings")
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            if self.get_job(metadata.job_id) is None:
                raise ValueError(f"Job not found: {metadata.job_id}")
            self._connection.execute(
                "INSERT INTO job_metadata (job_id, source_url, greenhouse_board_token, "
                "published_at, updated_at, internship_term, degree_requirements, "
                "graduation_window, work_authorization, compensation, relevance_category, "
                "relevance_reason, verified_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(job_id) DO UPDATE SET source_url = excluded.source_url, "
                "greenhouse_board_token = excluded.greenhouse_board_token, "
                "published_at = excluded.published_at, updated_at = excluded.updated_at, "
                "internship_term = excluded.internship_term, "
                "degree_requirements = excluded.degree_requirements, "
                "graduation_window = excluded.graduation_window, "
                "work_authorization = excluded.work_authorization, "
                "compensation = excluded.compensation, "
                "relevance_category = excluded.relevance_category, "
                "relevance_reason = excluded.relevance_reason, "
                "verified_at = excluded.verified_at",
                (metadata.job_id, *fields),
            )
        saved = self.get_job_metadata(metadata.job_id)
        if saved is None:
            raise RuntimeError("Stored job metadata could not be read back")
        return saved

    def start_run(
        self,
        run_type: str,
        config_fingerprint: str,
        item_keys: Iterable[str] = (),
        run_id: str | None = None,
    ) -> RunRecord:
        run_type = _required_text(run_type, "run_type")
        config_fingerprint = _required_text(config_fingerprint, "config_fingerprint")
        run_id = _required_text(run_id or uuid4().hex, "run_id")
        keys = [_required_text(key, "item_key") for key in item_keys]
        if len(keys) != len(set(keys)):
            raise ValueError("item_keys must not contain duplicates")
        now = _utc_now()
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.execute(
                    "INSERT INTO execution_runs "
                    "(run_id, run_type, started_at, status, config_fingerprint, last_progress_at) "
                    "VALUES (?, ?, ?, 'RUNNING', ?, ?)",
                    (run_id, run_type, now, config_fingerprint, now),
                )
            except sqlite3.IntegrityError as error:
                raise DuplicateRunError(f"Run ID already exists: {run_id}") from error
            self._connection.executemany(
                "INSERT INTO work_items (run_id, item_key, state, last_updated_at) "
                "VALUES (?, ?, 'PENDING', ?)",
                ((run_id, key, now) for key in keys),
            )
            self._refresh_run_counts(run_id, now)
            run = self.get_run(run_id)
            if run is None:
                raise RuntimeError("Started run could not be read back")
        return run

    def get_run(self, run_id: str) -> RunRecord | None:
        row = self._connection.execute(
            "SELECT * FROM execution_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        return self._run_record(row) if row is not None else None

    def list_runs(self, limit: int | None = None) -> list[RunRecord]:
        if limit is not None and (type(limit) is not int or limit <= 0):
            raise ValueError("limit must be a positive integer")
        query = "SELECT * FROM execution_runs ORDER BY started_at DESC"
        parameters: tuple[int, ...] = ()
        if limit is not None:
            query += " LIMIT ?"
            parameters = (limit,)
        rows = self._connection.execute(query, parameters).fetchall()
        return [self._run_record(row) for row in rows]

    def get_work_items(self, run_id: str) -> list[WorkItemRecord]:
        rows = self._connection.execute(
            "SELECT * FROM work_items WHERE run_id = ? ORDER BY item_key", (run_id,)
        ).fetchall()
        return [self._item_record(row) for row in rows]

    def ensure_work_item(self, run_id: str, item_key: str) -> WorkItemRecord:
        item_key = _required_text(item_key, "item_key")
        now = _utc_now()
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            run = self._require_run(run_id)
            if run["status"] != "RUNNING":
                raise RunStateError(f"Cannot add work item for run in state {run['status']}")
            self._connection.execute(
                "INSERT INTO work_items (run_id, item_key, state, last_updated_at) "
                "VALUES (?, ?, 'PENDING', ?) ON CONFLICT(run_id, item_key) DO NOTHING",
                (run_id, item_key, now),
            )
            self._refresh_run_counts(run_id, now)
            row = self._connection.execute(
                "SELECT * FROM work_items WHERE run_id = ? AND item_key = ?",
                (run_id, item_key),
            ).fetchone()
        return self._item_record(row)

    def inspect_run(self, run_id: str) -> tuple[RunRecord, list[WorkItemRecord]]:
        run = self.get_run(run_id)
        if run is None:
            raise RunNotFoundError(f"Run not found: {run_id}")
        return run, self.get_work_items(run_id)

    def _require_run(self, run_id: str) -> sqlite3.Row:
        row = self._connection.execute(
            "SELECT * FROM execution_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            raise RunNotFoundError(f"Run not found: {run_id}")
        return row

    def _refresh_run_counts(self, run_id: str, progress_at: str) -> None:
        counts = self._connection.execute(
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN state = 'COMPLETED' THEN 1 ELSE 0 END) AS completed, "
            "SUM(CASE WHEN state = 'FAILED' THEN 1 ELSE 0 END) AS failed "
            "FROM work_items WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        self._connection.execute(
            "UPDATE execution_runs SET work_item_total = ?, work_item_completed = ?, "
            "work_item_failed = ?, last_progress_at = ? WHERE run_id = ?",
            (counts["total"], counts["completed"] or 0, counts["failed"] or 0,
             progress_at, run_id),
        )

    def save_item_progress(
        self,
        run_id: str,
        item_key: str,
        state: str,
        error_details: str = "",
    ) -> WorkItemRecord:
        item_key = _required_text(item_key, "item_key")
        if state not in WORK_ITEM_STATES:
            raise RunStateError(f"Invalid work-item state: {state}")
        if not isinstance(error_details, str):
            raise ValueError("error_details must be a string")
        now = _utc_now()
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            run = self._require_run(run_id)
            if run["status"] != "RUNNING":
                raise RunStateError(
                    f"Cannot update work item for run {run_id} in state {run['status']}"
                )
            item = self._connection.execute(
                "SELECT * FROM work_items WHERE run_id = ? AND item_key = ?",
                (run_id, item_key),
            ).fetchone()
            if item is None:
                raise RunStateError(f"Work item not found: {run_id}/{item_key}")
            current = item["state"]
            if state not in _ITEM_TRANSITIONS[current]:
                raise RunStateError(f"Cannot transition work item {current} -> {state}")
            self._connection.execute(
                "UPDATE work_items SET state = ?, last_updated_at = ?, error_details = ? "
                "WHERE run_id = ? AND item_key = ?",
                (state, now, error_details.strip(), run_id, item_key),
            )
            self._refresh_run_counts(run_id, now)
            updated = self._connection.execute(
                "SELECT * FROM work_items WHERE run_id = ? AND item_key = ?",
                (run_id, item_key),
            ).fetchone()
        return self._item_record(updated)

    def complete_run(self, run_id: str) -> RunRecord:
        now = _utc_now()
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            run = self._require_run(run_id)
            if "COMPLETED" not in _RUN_TRANSITIONS[run["status"]]:
                raise RunStateError(f"Cannot complete run in state {run['status']}")
            incomplete = self._connection.execute(
                "SELECT COUNT(*) FROM work_items WHERE run_id = ? "
                "AND state IN ('PENDING', 'IN_PROGRESS')", (run_id,)
            ).fetchone()[0]
            if incomplete:
                raise RunStateError(f"Cannot complete run with {incomplete} incomplete work item(s)")
            self._connection.execute(
                "UPDATE execution_runs SET status = 'COMPLETED', completed_at = ?, "
                "error_summary = '' WHERE run_id = ?",
                (now, run_id),
            )
            self._refresh_run_counts(run_id, now)
            updated = self.get_run(run_id)
        return updated

    def interrupt_run(self, run_id: str, error_summary: str = "") -> RunRecord:
        if not isinstance(error_summary, str):
            raise ValueError("error_summary must be a string")
        now = _utc_now()
        reason = error_summary.strip() or "Run interrupted"
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            run = self._require_run(run_id)
            if "INTERRUPTED" not in _RUN_TRANSITIONS[run["status"]]:
                raise RunStateError(f"Cannot interrupt run in state {run['status']}")
            self._connection.execute(
                "UPDATE work_items SET state = 'PENDING', last_updated_at = ?, "
                "error_details = '' WHERE run_id = ? AND state = 'IN_PROGRESS'",
                (now, run_id),
            )
            self._connection.execute(
                "UPDATE execution_runs SET status = 'INTERRUPTED', completed_at = NULL, "
                "error_summary = ? WHERE run_id = ?",
                (reason, run_id),
            )
            self._refresh_run_counts(run_id, now)
            updated = self.get_run(run_id)
        return updated

    mark_run_interrupted = interrupt_run

    def resume_run(self, run_id: str) -> RunRecord:
        now = _utc_now()
        recovery_reason = "Recovered after previous process was not finalized"
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            run = self._require_run(run_id)
            if run["status"] not in {"RUNNING", "INTERRUPTED"}:
                raise RunStateError(f"Cannot resume run in state {run['status']}")
            if run["status"] == "RUNNING":
                self._connection.execute(
                    "UPDATE execution_runs SET status = 'INTERRUPTED', error_summary = ? "
                    "WHERE run_id = ?",
                    (recovery_reason, run_id),
                )
            self._connection.execute(
                "UPDATE work_items SET state = 'PENDING', last_updated_at = ?, "
                "error_details = '' WHERE run_id = ? AND state IN ('IN_PROGRESS', 'FAILED')",
                (now, run_id),
            )
            self._connection.execute(
                "UPDATE execution_runs SET status = 'RUNNING', completed_at = NULL, "
                "error_summary = '' WHERE run_id = ?",
                (run_id,),
            )
            self._refresh_run_counts(run_id, now)
            updated = self.get_run(run_id)
        return updated

    def record_failed_run(self, run_id: str, error_summary: str) -> RunRecord:
        error_summary = _required_text(error_summary, "error_summary")
        now = _utc_now()
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            run = self._require_run(run_id)
            if run["status"] not in {"RUNNING", "INTERRUPTED"}:
                raise RunStateError(f"Cannot fail run in state {run['status']}")
            self._connection.execute(
                "UPDATE work_items SET state = 'FAILED', last_updated_at = ?, "
                "error_details = ? WHERE run_id = ? AND state = 'IN_PROGRESS'",
                (now, error_summary, run_id),
            )
            self._connection.execute(
                "UPDATE execution_runs SET status = 'FAILED', completed_at = ?, "
                "error_summary = ? WHERE run_id = ?",
                (now, error_summary, run_id),
            )
            self._refresh_run_counts(run_id, now)
            updated = self.get_run(run_id)
        return updated

    fail_run = record_failed_run


    def save_discovery_checkpoint(self, run_id: str, item_key: str, payload: dict) -> None:
        """Commit a JSON snapshot and its completed work-item checkpoint atomically."""
        item_key = _required_text(item_key, "item_key")
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False)
        now = _utc_now()
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            run = self._require_run(run_id)
            if run["status"] != "RUNNING":
                raise RunStateError("Checkpoint writes require a RUNNING run")
            self._connection.execute(
                "INSERT INTO work_items (run_id,item_key,state,last_updated_at) VALUES (?,?,'PENDING',?) "
                "ON CONFLICT(run_id,item_key) DO NOTHING", (run_id,item_key,now),
            )
            self._connection.execute(
                "INSERT INTO discovery_checkpoints (run_id,item_key,payload_json,saved_at) VALUES (?,?,?,?) "
                "ON CONFLICT(run_id,item_key) DO UPDATE SET payload_json=excluded.payload_json,saved_at=excluded.saved_at",
                (run_id,item_key,encoded,now),
            )
            self._connection.execute(
                "UPDATE work_items SET state='COMPLETED',last_updated_at=?,error_details='' WHERE run_id=? AND item_key=?",
                (now,run_id,item_key),
            )
            self._refresh_run_counts(run_id,now)

    def load_discovery_checkpoints(self, run_id: str) -> dict[str, dict]:
        return {row["item_key"]:json.loads(row["payload_json"]) for row in self._connection.execute(
            "SELECT item_key,payload_json FROM discovery_checkpoints WHERE run_id=?", (run_id,)
        )}


    @staticmethod
    def _application_record(row: sqlite3.Row) -> ApplicationRecord:
        return ApplicationRecord(**dict(row))

    def get_application(self, job_id: int) -> ApplicationRecord | None:
        row = self._connection.execute(
            "SELECT * FROM applications WHERE job_id = ?", (job_id,)
        ).fetchone()
        return self._application_record(row) if row else None

    def list_applications(self, status: str | None = None) -> list[ApplicationRecord]:
        if status is not None:
            validate_status(status)
        rows = self._connection.execute(
            "SELECT * FROM applications " + ("WHERE status = ? " if status else "") + "ORDER BY job_id",
            (status,) if status else (),
        )
        return [self._application_record(row) for row in rows]

    def application_history(self, job_id: int) -> list[ApplicationStatusEvent]:
        self._require_application_job(job_id)
        return [ApplicationStatusEvent(**dict(row)) for row in self._connection.execute(
            "SELECT * FROM application_status_history WHERE job_id = ? ORDER BY id", (job_id,)
        )]

    def _require_application_job(self, job_id: int) -> None:
        if type(job_id) is not int or self.get_job(job_id) is None:
            raise ApplicationStateError(f"Job not found: {job_id}")

    def _append_application_event(self, job_id, previous, status, now, event, reason):
        self._connection.execute(
            "INSERT INTO application_status_history "
            "(job_id, previous_status, new_status, occurred_at, event, reason) VALUES (?, ?, ?, ?, ?, ?)",
            (job_id, previous, status, now, event, reason),
        )

    def _ensure_application(self, job_id: int, now: str) -> ApplicationRecord:
        # Called only from explicit manual write transactions. Discovery never calls it.
        self._require_application_job(job_id)
        existing = self.get_application(job_id)
        if existing is not None:
            return existing
        self._connection.execute(
            "INSERT INTO applications (job_id, status, status_updated_at, created_at, updated_at) "
            "VALUES (?, 'NOT_STARTED', ?, ?, ?)", (job_id, now, now, now),
        )
        self._append_application_event(job_id, None, "NOT_STARTED", now, "HUMAN_CREATE", "")
        return self.get_application(job_id)

    def create_application(self, job_id: int) -> ApplicationRecord:
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            record = self._ensure_application(job_id, _utc_now())
        return record

    def set_application_status(self, job_id: int, status: str, *, reason: str = "") -> ApplicationRecord:
        validate_status(status)
        reason = text(reason, "reason")
        if status == "APPLIED":
            raise ApplicationStateError("APPLIED requires mark-submitted with explicit user confirmation")
        now = _utc_now()
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            current = self._ensure_application(job_id, now)
            if status not in STATUS_TRANSITIONS[current.status]:
                raise ApplicationStateError(f"Invalid application transition: {current.status} -> {status}")
            if status != current.status:
                self._connection.execute(
                    "UPDATE applications SET status = ?, status_updated_at = ?, updated_at = ? WHERE job_id = ?",
                    (status, now, now, job_id),
                )
                self._append_application_event(job_id, current.status, status, now, "HUMAN_STATUS_CHANGE", reason)
            record = self.get_application(job_id)
        return record

    def mark_application_submitted(self, job_id: int, submitted_at: str, *,
                                   confirmed_by_user: bool = False, receipt_reference: str = "",
                                   reason: str = "") -> ApplicationRecord:
        """Record a user's assertion of successful submission; never submit or verify it externally."""
        if confirmed_by_user is not True:
            raise ApplicationStateError("Successful submission must be explicitly confirmed by the user")
        submitted_at = validate_date(submitted_at, "submitted_at", submitted=True)
        receipt_reference = text(receipt_reference, "receipt_reference")
        reason = text(reason, "reason")
        now = _utc_now()
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            current = self._ensure_application(job_id, now)
            if current.status == "APPLIED" and current.submitted_at == submitted_at and current.receipt_reference == receipt_reference:
                return current  # Idempotent confirmation; preserve the original event.
            if current.status not in PRE_SUBMISSION:
                raise ApplicationStateError(f"Cannot mark submitted from {current.status}; prior confirmation is preserved")
            self._connection.execute(
                "UPDATE applications SET status = 'APPLIED', submitted_at = ?, receipt_reference = ?, "
                "status_updated_at = ?, updated_at = ? WHERE job_id = ?",
                (submitted_at, receipt_reference, now, now, job_id),
            )
            self._append_application_event(job_id, current.status, "APPLIED", now,
                                           "HUMAN_SUBMISSION_CONFIRMATION", reason)
            record = self.get_application(job_id)
        return record

    def set_application_follow_up(self, job_id: int, follow_up_at: str | None) -> ApplicationRecord:
        if follow_up_at is not None:
            validate_date(follow_up_at, "follow_up_at")
        return self._update_application_details(job_id, {"follow_up_at": follow_up_at})

    def set_application_deadline(self, job_id: int, deadline: str, evidence: str, *,
                                 verified_by_user: bool = False) -> ApplicationRecord:
        if verified_by_user is not True:
            raise ApplicationStateError("Deadline requires explicit verification by the user")
        validate_date(deadline, "deadline")
        evidence = text(evidence, "deadline evidence", required=True)
        return self._update_application_details(job_id, {
            "deadline": deadline, "deadline_evidence": evidence, "deadline_verified_at": _utc_now(),
        })

    def clear_application_deadline(self, job_id: int) -> ApplicationRecord:
        return self._update_application_details(job_id, {
            "deadline": None, "deadline_evidence": "", "deadline_verified_at": None,
        })

    def add_application_note(self, job_id: int, note: str) -> ApplicationRecord:
        note = text(note, "note", required=True)
        now = _utc_now()
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            current = self._ensure_application(job_id, now)
            notes = current.notes + ("\n" if current.notes else "") + note
            self._connection.execute("UPDATE applications SET notes = ?, updated_at = ? WHERE job_id = ?",
                                     (notes, now, job_id))
            record = self.get_application(job_id)
        return record

    def _update_application_details(self, job_id: int, values: dict) -> ApplicationRecord:
        # Fixed internal field names; callers cannot inject arbitrary SQL/columns.
        allowed = {"follow_up_at", "deadline", "deadline_evidence", "deadline_verified_at"}
        if not values or not set(values) <= allowed:
            raise ApplicationStateError("Invalid application detail fields")
        now = _utc_now()
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            self._ensure_application(job_id, now)
            assignment = ", ".join(f"{field} = ?" for field in values)
            self._connection.execute(f"UPDATE applications SET {assignment}, updated_at = ? WHERE job_id = ?",
                                     (*values.values(), now, job_id))
            record = self.get_application(job_id)
        return record
