# Public copy: synthetic identities and timestamps; no live source verification.
"""Offline application tracking, migration, CLI and shareable-report regressions."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, redirect_stdout, redirect_stderr
from datetime import date, datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from internship_agent.applications import ApplicationStateError, application_opportunities, validate_date
from internship_agent.application_report import write_application_report
from internship_agent.database import JobDatabase, SCHEMA_VERSION
from internship_agent.models import Job, JobMetadata
from tests.test_unified_discovery import FakeGreenhouse, FakeLever, FakeAshby, raw, CONFIG
from internship_agent.unified_discovery import UnifiedDiscovery
import yaml


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "jobs.sqlite3"
        self.db = JobDatabase(self.path)
        self.addCleanup(self.db.close)
        self.job = self.db.add_job(Job("Robot Learning Intern", "Example Robotics", "San Francisco, CA",
                                      source="manual", source_job_id="example-1",
                                      description="Train manipulation policies for robots.")).record
        self.id = self.job.id
        self.db.save_job_metadata(JobMetadata(self.id, relevance_category="NEEDS_REVIEW", verified_at="2025-01-10T00:00:00Z"))
        self.submitted = "2026-01-01"

    def submit(self, **kwargs):
        return self.db.mark_application_submitted(self.id, self.submitted, confirmed_by_user=True, **kwargs)

    def test_create_read_and_repeat_create_are_idempotent(self):
        a = self.db.create_application(self.id)
        self.assertEqual(a.status, "NOT_STARTED")
        self.assertEqual(self.db.get_application(self.id), a)
        self.assertEqual(self.db.create_application(self.id), a)
        self.assertEqual(len(self.db.application_history(self.id)), 1)
        self.assertIsNone(a.submitted_at)
        self.assertIsNone(a.deadline)
        self.assertIsNone(a.follow_up_at)
        self.assertEqual(datetime.fromisoformat(a.created_at).tzinfo, timezone.utc)

    def test_preparation_transitions_and_history(self):
        for status in ("RESEARCHING", "PREPARING", "READY_TO_APPLY", "PREPARING"):
            self.db.set_application_status(self.id, status, reason="Manual preparation")
        events = self.db.application_history(self.id)
        self.assertEqual([e.new_status for e in events], ["NOT_STARTED", "RESEARCHING", "PREPARING", "READY_TO_APPLY", "PREPARING"])
        self.assertEqual(events[-1].previous_status, "READY_TO_APPLY")
        self.assertEqual(events[-1].event, "HUMAN_STATUS_CHANGE")
        self.assertEqual(events[-1].reason, "Manual preparation")

    def test_invalid_status_leaves_no_application(self):
        for status in ("MADE_UP", "applied", "", None):
            with self.subTest(status=status), self.assertRaises(ApplicationStateError):
                self.db.set_application_status(self.id, status)
        self.assertIsNone(self.db.get_application(self.id))

    def test_unknown_jobs_rejected(self):
        for operation in (lambda: self.db.create_application(999),
                          lambda: self.db.set_application_status(999, "PREPARING"),
                          lambda: self.db.mark_application_submitted(999, self.submitted, confirmed_by_user=True),
                          lambda: self.db.add_application_note(999, "Private note"),
                          lambda: self.db.set_application_follow_up(999, "2027-01-01"),
                          lambda: self.db.application_history(999)):
            with self.assertRaisesRegex(ApplicationStateError, "Job not found"):
                operation()
        self.assertEqual(self.db.list_applications(), [])

    def test_generic_applied_update_rejected(self):
        with self.assertRaisesRegex(ApplicationStateError, "confirmation"):
            self.db.set_application_status(self.id, "APPLIED")
        self.assertIsNone(self.db.get_application(self.id))

    def test_submission_requires_literal_human_confirmation(self):
        for confirmation in (False, None, 1, "yes"):
            with self.subTest(confirmation=confirmation), self.assertRaises(ApplicationStateError):
                self.db.mark_application_submitted(self.id, self.submitted, confirmed_by_user=confirmation)
        self.assertIsNone(self.db.get_application(self.id))

    def test_confirmed_submission_retains_event_date_and_receipt(self):
        self.db.set_application_status(self.id, "READY_TO_APPLY")
        a = self.submit(receipt_reference="local/receipt.txt", reason="User confirms receipt")
        self.assertEqual((a.status, a.submitted_at, a.receipt_reference), ("APPLIED", self.submitted, "local/receipt.txt"))
        event = self.db.application_history(self.id)[-1]
        self.assertEqual((event.previous_status, event.new_status, event.event),
                         ("READY_TO_APPLY", "APPLIED", "HUMAN_SUBMISSION_CONFIRMATION"))

    def test_repeated_confirmation_does_not_overwrite_event(self):
        original = self.submit(receipt_reference="receipt-1", reason="First confirmation")
        history = self.db.application_history(self.id)
        self.assertEqual(self.submit(receipt_reference="receipt-1"), original)
        self.assertEqual(self.db.application_history(self.id), history)
        with self.assertRaises(ApplicationStateError):
            self.submit(receipt_reference="different receipt")
        self.assertEqual(self.db.get_application(self.id), original)

    def test_submission_dates_validated_without_invention(self):
        for value in ("2026-02-30", "2026-1-1", "20260101", "", None,
                      (date.today() + timedelta(days=1)).isoformat()):
            with self.subTest(value=value), self.assertRaises(ApplicationStateError):
                self.db.mark_application_submitted(self.id, value, confirmed_by_user=True)
        self.assertIsNone(self.db.get_application(self.id))

    def test_outcome_transitions_preserve_submission(self):
        self.submit(receipt_reference="receipt-1")
        for status in ("INTERVIEWING", "OFFER", "CLOSED"):
            a = self.db.set_application_status(self.id, status)
            self.assertEqual(a.submitted_at, self.submitted)
            self.assertEqual(a.receipt_reference, "receipt-1")
        with self.assertRaises(ApplicationStateError):
            self.db.set_application_status(self.id, "PREPARING")

    def test_interview_without_submission_rejected_and_rolled_back(self):
        with self.assertRaises(ApplicationStateError):
            self.db.set_application_status(self.id, "INTERVIEWING")
        self.assertIsNone(self.db.get_application(self.id))
        self.assertEqual(self.db.application_history(self.id), [])

    def test_terminal_status_cannot_be_silently_reopened(self):
        self.db.set_application_status(self.id, "CLOSED")
        with self.assertRaises(ApplicationStateError):
            self.db.set_application_status(self.id, "RESEARCHING")
        with self.assertRaises(ApplicationStateError):
            self.submit()

    def test_same_status_is_a_noop(self):
        a = self.db.set_application_status(self.id, "PREPARING")
        history = self.db.application_history(self.id)
        self.assertEqual(self.db.set_application_status(self.id, "PREPARING"), a)
        self.assertEqual(self.db.application_history(self.id), history)

    def test_verified_deadline_and_evidence_persist_and_can_be_cleared(self):
        a = self.db.set_application_deadline(self.id, "2027-02-01", "Official posting inspected by user", verified_by_user=True)
        self.assertEqual(a.deadline, "2027-02-01")
        self.assertEqual(a.deadline_evidence, "Official posting inspected by user")
        self.assertIsNotNone(a.deadline_verified_at)
        a = self.db.clear_application_deadline(self.id)
        self.assertIsNone(a.deadline)
        self.assertEqual(a.deadline_evidence, "")
        self.assertIsNone(a.deadline_verified_at)

    def test_deadline_requires_date_evidence_and_verification(self):
        for deadline, evidence, verified in (("2027-02-30", "Official", True), ("2027-02-01", "", True),
                                             ("2027-02-01", "Official", False)):
            with self.subTest(deadline=deadline, evidence=evidence), self.assertRaises(ApplicationStateError):
                self.db.set_application_deadline(self.id, deadline, evidence, verified_by_user=verified)
        self.assertIsNone(self.db.get_application(self.id))

    def test_follow_up_is_explicit_and_clearable(self):
        self.assertEqual(self.db.set_application_follow_up(self.id, "2027-01-15").follow_up_at, "2027-01-15")
        self.assertIsNone(self.db.set_application_follow_up(self.id, None).follow_up_at)
        with self.assertRaises(ApplicationStateError):
            self.db.set_application_follow_up(self.id, "2027-02-30")

    def test_notes_append_without_changing_status_timestamp(self):
        a = self.db.set_application_status(self.id, "PREPARING")
        self.db.add_application_note(self.id, "First private note")
        b = self.db.add_application_note(self.id, "Second private note")
        self.assertEqual(b.notes, "First private note\nSecond private note")
        self.assertEqual(b.status_updated_at, a.status_updated_at)
        self.assertEqual(len(self.db.application_history(self.id)), 2)

    def test_persistence_after_reopening(self):
        self.submit(receipt_reference="local-receipt")
        self.db.add_application_note(self.id, "Remember this note")
        self.db.set_application_follow_up(self.id, "2027-01-15")
        self.db.set_application_deadline(self.id, "2027-01-10", "Verified source", verified_by_user=True)
        expected, history = self.db.get_application(self.id), self.db.application_history(self.id)
        with JobDatabase(self.path) as reopened:
            self.assertEqual(reopened.get_application(self.id), expected)
            self.assertEqual(reopened.application_history(self.id), history)

    def test_jobs_identities_metadata_and_runs_unchanged_by_tracker(self):
        run = self.db.start_run("simulation", "config", ["item"])
        with closing(sqlite3.connect(self.path)) as conn:
            before = {table: conn.execute(f"SELECT * FROM {table}").fetchall()
                      for table in ("jobs", "job_identities", "job_metadata", "execution_runs", "work_items")}
        self.submit()
        self.db.add_application_note(self.id, "Note")
        self.db.set_application_follow_up(self.id, "2027-01-15")
        with closing(sqlite3.connect(self.path)) as conn:
            after = {table: conn.execute(f"SELECT * FROM {table}").fetchall() for table in before}
        self.assertEqual(after, before)
        self.assertEqual(self.db.get_run(run.run_id), run)

    def test_transaction_rolls_back_status_and_history_on_event_failure(self):
        original = self.db.set_application_status(self.id, "PREPARING")
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute("CREATE TRIGGER simulate_failure BEFORE INSERT ON application_status_history "
                         "WHEN NEW.new_status = 'APPLIED' BEGIN SELECT RAISE(ABORT, 'simulated failure'); END")
        before = self.db.application_history(self.id)
        with self.assertRaises(sqlite3.IntegrityError):
            self.submit()
        self.assertEqual(self.db.get_application(self.id), original)
        self.assertEqual(self.db.application_history(self.id), before)

    def test_history_is_append_only(self):
        self.submit()
        for sql in ("DELETE FROM application_status_history", "UPDATE application_status_history SET reason='altered'"):
            with closing(sqlite3.connect(self.path)) as conn, self.assertRaises(sqlite3.IntegrityError):
                conn.execute(sql)
        self.assertEqual(len(self.db.application_history(self.id)), 2)

    def test_sql_constraints_reject_invalid_status_and_missing_submission(self):
        self.db.create_application(self.id)
        for sql in ("UPDATE applications SET status='INVALID'", "UPDATE applications SET status='APPLIED'"):
            with closing(sqlite3.connect(self.path)) as conn, self.assertRaises(sqlite3.IntegrityError):
                conn.execute(sql)

    def test_concurrent_notes_do_not_lose_updates(self):
        self.db.create_application(self.id)
        def write(note):
            with JobDatabase(self.path) as other:
                other.add_application_note(self.id, note)
        with ThreadPoolExecutor(max_workers=2) as workers:
            list(workers.map(write, ("Alpha", "Beta")))
        self.assertEqual(set(self.db.get_application(self.id).notes.splitlines()), {"Alpha", "Beta"})

    def test_concurrent_conflicting_submissions_preserve_first_confirmation(self):
        self.db.create_application(self.id)
        def submit(receipt):
            with JobDatabase(self.path) as other:
                try:
                    other.mark_application_submitted(self.id, self.submitted, confirmed_by_user=True, receipt_reference=receipt)
                    return True
                except ApplicationStateError:
                    return False
        with ThreadPoolExecutor(max_workers=2) as workers:
            outcomes = list(workers.map(submit, ("Alpha", "Beta")))
        self.assertEqual(sorted(outcomes), [False, True])
        self.assertEqual(len(self.db.application_history(self.id)), 2)

    def test_unknown_work_authorization_stays_in_high_priority_queue(self):
        entries = application_opportunities(self.db, high_priority=True)
        self.assertEqual([e.record.id for e in entries], [self.id])
        self.assertEqual(entries[0].metadata.work_authorization, "UNKNOWN")
        self.db.set_application_status(self.id, "PREPARING")
        self.assertEqual(application_opportunities(self.db, status="PREPARING")[0].classification, "NEEDS_REVIEW")

    def test_excluded_and_unclassified_jobs_are_not_automatically_queued(self):
        excluded = self.db.add_job(Job("Business Intern", "Example Business")).record
        self.db.save_job_metadata(JobMetadata(excluded.id, relevance_category="EXCLUDED", verified_at="2025-01-10T00:00:00Z"))
        unknown = self.db.add_job(Job("Unknown Intern", "Example Unknown")).record
        self.assertEqual([e.record.id for e in application_opportunities(self.db)], [self.id])
        self.assertEqual(len(application_opportunities(self.db, include_excluded=True)), 3)
        self.assertEqual(self.db.list_applications(), [])
        # Deliberate user tracking remains visible even after source exclusion.
        self.db.create_application(excluded.id)
        self.assertIn(excluded.id, [e.record.id for e in application_opportunities(self.db)])
        self.assertIsNone(self.db.get_application(unknown.id))

    def test_queue_uses_existing_technical_priority(self):
        hardware = self.db.add_job(Job("Electrical Engineering Intern", "Example Hardware", "San Francisco, CA")).record
        self.db.save_job_metadata(JobMetadata(hardware.id, relevance_category="MAIN_SHORTLIST", verified_at="2025-01-10T00:00:00Z"))
        entries = application_opportunities(self.db)
        self.assertEqual([e.record.id for e in entries], [self.id, hardware.id])
        self.assertEqual([e.record.id for e in application_opportunities(self.db, high_priority=True)], [self.id])

    def test_report_reads_without_creating_applications_or_deadlines(self):
        path = write_application_report(self.db, self.root / "tracker.md")
        report = path.read_text(encoding="utf-8")
        self.assertIn("explicitly tracked applications: 0", report)
        self.assertIn("untracked relevant/review opportunities: 1", report)
        self.assertIn("UNKNOWN", report)
        self.assertEqual(self.db.list_applications(), [])

    def test_report_omits_all_private_application_text(self):
        self.submit(receipt_reference="PRIVATE_RECEIPT", reason="PRIVATE_REASON")
        self.db.add_application_note(self.id, "PRIVATE_NOTE private.contact@example.test")
        self.db.set_application_deadline(self.id, "2027-01-10", "PRIVATE_DEADLINE_EVIDENCE", verified_by_user=True)
        report = write_application_report(self.db, self.root / "tracker.md", today=date(2026, 10, 10)).read_text()
        for secret in ("PRIVATE_RECEIPT", "PRIVATE_REASON", "PRIVATE_NOTE", "private.contact@example.test", "PRIVATE_DEADLINE_EVIDENCE"):
            self.assertNotIn(secret, report)
        self.assertIn("APPLIED", report)
        self.assertIn(self.submitted, report)
        self.assertIn("2027-01-10", report)

    def test_report_includes_preparation_review_and_follow_up(self):
        self.db.set_application_status(self.id, "PREPARING")
        self.db.set_application_follow_up(self.id, "2027-01-15")
        report = write_application_report(self.db, self.root / "tracker.md").read_text()
        self.assertIn("| PREPARING | 1 |", report)
        self.assertIn("2027-01-15", report)
        self.assertIn("NEEDS_REVIEW", report)

    def test_report_refuses_to_overwrite_database(self):
        with self.assertRaises(ValueError):
            write_application_report(self.db, self.path)
        self.assertEqual(self.db.count_jobs(), 1)

    def test_migration_from_v5_preserves_all_existing_tables_and_backup(self):
        run = self.db.start_run("simulation", "config", ["item"])
        self.db.save_discovery_checkpoint(run.run_id, "item", {"jobs": []})
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute("DROP TABLE application_status_history")
            conn.execute("DROP TABLE applications")
            conn.execute("PRAGMA user_version = 5")
            tables = ("jobs", "job_identities", "job_metadata", "execution_runs", "work_items", "discovery_checkpoints")
            before = {table: conn.execute(f"SELECT * FROM {table}").fetchall() for table in tables}
        with JobDatabase(self.path) as migrated:
            self.assertEqual(migrated.list_applications(), [])
            backup = migrated.migration_backup_path
            self.assertIsNotNone(backup)
        with closing(sqlite3.connect(self.path)) as conn:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
            self.assertEqual({t: conn.execute(f"SELECT * FROM {t}").fetchall() for t in tables}, before)
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        with closing(sqlite3.connect(backup)) as conn:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 5)
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual({t: conn.execute(f"SELECT * FROM {t}").fetchall() for t in tables}, before)

    def test_failed_migration_rolls_back_and_preserves_v5_backup(self):
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute("DROP TABLE application_status_history")
            conn.execute("DROP TABLE applications")
            conn.execute("PRAGMA user_version = 5")
        with patch("internship_agent.database._APPLICATION_SCHEMA", ("CREATE TABLE partial (id INTEGER)", "INVALID SQL")):
            with self.assertRaises(sqlite3.OperationalError):
                JobDatabase(self.path)
        with closing(sqlite3.connect(self.path)) as conn:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 5)
            self.assertIsNone(conn.execute("SELECT name FROM sqlite_master WHERE name='partial'").fetchone())
        self.assertEqual(self.db.get_job(self.id), self.job)
        self.assertTrue(list(self.root.glob("*.pre-v6-*.bak")))




class ApplicationDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "jobs.sqlite3"
        self.config_dir = self.root / "config"
        self.config_dir.mkdir()
        for filename, key, token_field, token, host in (
            ("greenhouse_boards.yaml", "boards", "board_token", "example-g", "boards.greenhouse.io"),
            ("lever_sites.yaml", "sites", "site_token", "example-l", "jobs.lever.co"),
            ("ashby_boards.yaml", "boards", "board_name", "example-a", "jobs.ashbyhq.com"),
        ):
            payload = {"version": 1, key: [{"company_name": f"Example {token}", token_field: token,
                       "source_url": f"https://{host}/{token}", "active": True, "verified_at": "2025-01-10T00:00:00Z"}]}
            (self.config_dir / filename).write_text(yaml.safe_dump(payload))
        self.clients = {"greenhouse": FakeGreenhouse(), "lever": FakeLever(), "ashby": FakeAshby()}

    def discover(self):
        return UnifiedDiscovery(clients=self.clients).run(CONFIG, self.config_dir, database_path=self.path,
                                                       limit=1, save=True, save_all=True)

    def prepare_tracking(self):
        self.discover()
        with JobDatabase(self.path) as db:
            job = db.list_jobs()[0]
            db.mark_application_submitted(job.id, "2026-01-01", confirmed_by_user=True, receipt_reference="PRIVATE_RECEIPT", reason="User assertion")
            db.add_application_note(job.id, "Private note")
            db.set_application_follow_up(job.id, "2027-01-15")
            db.set_application_deadline(job.id, "2027-01-10", "Private source evidence", verified_by_user=True)
            return job, db.get_application(job.id), db.application_history(job.id)

    def test_repeated_duplicate_discovery_preserves_all_manual_data(self):
        job, application, history = self.prepare_tracking()
        result = self.discover()
        self.assertEqual((result.newly_saved, result.existing_skipped), (0, 3))
        with JobDatabase(self.path) as db:
            self.assertEqual(db.get_job(job.id), job)
            self.assertEqual(db.get_application(job.id), application)
            self.assertEqual(db.application_history(job.id), history)
            self.assertEqual(db.count_jobs(), 3)

    def test_disappeared_or_excluded_posting_retains_application(self):
        job, application, history = self.prepare_tracking()
        self.clients["greenhouse"].jobs = []
        self.clients["lever"].pages = [[]]
        self.clients["ashby"].jobs = []
        self.discover()
        with JobDatabase(self.path) as db:
            self.assertEqual(db.count_jobs(), 3)
            self.assertEqual(db.get_job(job.id), job)
            self.assertEqual(db.get_application(job.id), application)
            self.assertEqual(db.application_history(job.id), history)
            self.assertIn(job.id, [e.record.id for e in application_opportunities(db)])

    def test_discovery_never_creates_or_marks_applications(self):
        self.discover()
        with JobDatabase(self.path) as db:
            self.assertEqual(db.list_applications(), [])
            for job in db.list_jobs():
                self.assertEqual(db.application_history(job.id), [])
