# Public copy: synthetic identities and timestamps; no live source verification.
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest

from internship_agent.database import (
    DuplicateRunError,
    JobDatabase,
    RunStateError,
)
from internship_agent.models import Job


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_CONFIG = PROJECT_ROOT / "config" / "search_preferences.example.yaml"


class ExecutionStateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "state.sqlite3"
        self.database = JobDatabase(self.path)
        self.addCleanup(self.database.close)

    def start(self, *items, run_id=None):
        return self.database.start_run(
            "simulation", "sha256:test-config", items, run_id=run_id
        )

    def test_creating_run_persists_metadata_and_work_items(self):
        run = self.start("alpha", "beta")
        self.assertEqual(run.status, "RUNNING")
        self.assertEqual(run.run_type, "simulation")
        self.assertEqual(run.config_fingerprint, "sha256:test-config")
        self.assertEqual((run.work_item_total, run.work_item_completed, run.work_item_failed), (2, 0, 0))
        self.assertTrue(run.started_at.endswith("Z"))
        self.assertEqual([item.item_key for item in self.database.get_work_items(run.run_id)], ["alpha", "beta"])

    def test_completing_run_persists_across_restart(self):
        run = self.start("alpha", "beta")
        self.database.save_item_progress(run.run_id, "alpha", "COMPLETED")
        self.database.save_item_progress(run.run_id, "beta", "COMPLETED")
        completed = self.database.complete_run(run.run_id)
        self.assertEqual(completed.status, "COMPLETED")
        self.assertIsNotNone(completed.completed_at)
        self.database.close()
        with JobDatabase(self.path) as reopened:
            persisted, items = reopened.inspect_run(run.run_id)
            self.assertEqual(persisted.status, "COMPLETED")
            self.assertEqual([item.state for item in items], ["COMPLETED", "COMPLETED"])

    def test_interrupting_and_resuming_preserves_completed_items(self):
        run = self.start("completed", "in-progress", "pending")
        self.database.save_item_progress(run.run_id, "completed", "COMPLETED")
        self.database.save_item_progress(run.run_id, "in-progress", "IN_PROGRESS")
        interrupted = self.database.interrupt_run(run.run_id, "user paused the run")
        self.assertEqual(interrupted.status, "INTERRUPTED")
        items = {item.item_key: item for item in self.database.get_work_items(run.run_id)}
        self.assertEqual(items["completed"].state, "COMPLETED")
        self.assertEqual(items["in-progress"].state, "PENDING")
        resumed = self.database.resume_run(run.run_id)
        self.assertEqual(resumed.status, "RUNNING")
        self.assertEqual(resumed.work_item_completed, 1)
        self.assertEqual({item.item_key for item in self.database.get_work_items(run.run_id)
                          if item.state == "PENDING"}, {"in-progress", "pending"})

    def test_running_run_is_recovered_after_simulated_process_crash(self):
        run = self.start("alpha", "beta")
        self.database.save_item_progress(run.run_id, "alpha", "COMPLETED")
        self.database.save_item_progress(run.run_id, "beta", "IN_PROGRESS")
        self.database.close()
        with JobDatabase(self.path) as restarted:
            before = restarted.get_run(run.run_id)
            self.assertEqual(before.status, "RUNNING")
            resumed = restarted.resume_run(run.run_id)
            self.assertEqual(resumed.status, "RUNNING")
            items = {item.item_key: item for item in restarted.get_work_items(run.run_id)}
            self.assertEqual(items["alpha"].state, "COMPLETED")
            self.assertEqual(items["beta"].state, "PENDING")

    def test_failed_items_are_retryable_without_repeating_completed_items(self):
        run = self.start("done", "retry")
        self.database.save_item_progress(run.run_id, "done", "COMPLETED")
        self.database.save_item_progress(run.run_id, "retry", "FAILED", "temporary error")
        self.assertEqual(self.database.get_run(run.run_id).work_item_failed, 1)
        self.database.resume_run(run.run_id)
        items = {item.item_key: item for item in self.database.get_work_items(run.run_id)}
        self.assertEqual(items["done"].state, "COMPLETED")
        self.assertEqual(items["retry"].state, "PENDING")
        self.database.save_item_progress(run.run_id, "retry", "COMPLETED")
        self.assertEqual(self.database.complete_run(run.run_id).status, "COMPLETED")

    def test_duplicate_run_identity_is_rejected(self):
        self.start("alpha", run_id="fixed-run")
        with self.assertRaises(DuplicateRunError):
            self.start("beta", run_id="fixed-run")

    def test_invalid_run_and_item_transitions_are_rejected(self):
        run = self.start("alpha")
        with self.assertRaisesRegex(RunStateError, "incomplete"):
            self.database.complete_run(run.run_id)
        self.database.save_item_progress(run.run_id, "alpha", "COMPLETED")
        with self.assertRaisesRegex(RunStateError, "Cannot transition"):
            self.database.save_item_progress(run.run_id, "alpha", "PENDING")
        self.database.complete_run(run.run_id)
        with self.assertRaisesRegex(RunStateError, "COMPLETED"):
            self.database.interrupt_run(run.run_id)
        with self.assertRaisesRegex(RunStateError, "COMPLETED"):
            self.database.resume_run(run.run_id)

    def test_failed_run_is_terminal_and_records_error(self):
        run = self.start("alpha")
        self.database.save_item_progress(run.run_id, "alpha", "IN_PROGRESS")
        failed = self.database.record_failed_run(run.run_id, "simulated fatal error")
        self.assertEqual(failed.status, "FAILED")
        self.assertEqual(failed.error_summary, "simulated fatal error")
        item = self.database.get_work_items(run.run_id)[0]
        self.assertEqual(item.state, "FAILED")
        with self.assertRaises(RunStateError):
            self.database.resume_run(run.run_id)

    def test_existing_jobs_are_unchanged_by_run_state_operations(self):
        job = self.database.add_job(Job(title="Research Intern", company="Example"))
        run = self.start("alpha")
        self.database.save_item_progress(run.run_id, "alpha", "COMPLETED")
        self.database.complete_run(run.run_id)
        self.assertEqual(self.database.count_jobs(), 1)
        self.assertEqual(self.database.get_job(job.record.id), job.record)

    def test_v1_database_is_migrated_with_a_backup_and_jobs_preserved(self):
        path = Path(self.temporary.name) / "legacy.sqlite3"
        connection = sqlite3.connect(path)
        try:
            connection.executescript("""
                CREATE TABLE jobs (
                    id INTEGER PRIMARY KEY,
                    title TEXT NOT NULL,
                    company TEXT NOT NULL,
                    location TEXT NOT NULL DEFAULT '',
                    url TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT '',
                    source_job_id TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT '2026-01-01T00:00:00.000Z'
                );
                CREATE TABLE job_identities (
                    identity_key TEXT PRIMARY KEY,
                    job_id INTEGER NOT NULL REFERENCES jobs(id)
                );
            """)
            connection.execute(
                "INSERT INTO jobs (title, company) VALUES ('Legacy Intern', 'Example')"
            )
            connection.execute("PRAGMA user_version = 1")
            connection.commit()
        finally:
            connection.close()
        with JobDatabase(path) as migrated:
            self.assertTrue(migrated.migration_backup_path.is_file())
            self.assertEqual(migrated.get_job(1).job.title, "Legacy Intern")
            self.assertEqual(migrated.get_run("missing"), None)
            self.assertEqual(migrated.start_run("migration-check", "fingerprint").status, "RUNNING")
        check = sqlite3.connect(path)
        try:
            self.assertEqual(check.execute("PRAGMA user_version").fetchone()[0], 6)
        finally:
            check.close()

    def test_concurrent_unique_runs_are_safe(self):
        barrier = threading.Barrier(4)

        def create(index):
            with JobDatabase(self.path) as database:
                barrier.wait(timeout=10)
                return database.start_run("parallel", "fingerprint", run_id=f"run-{index}")

        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(create, range(4)))
        self.assertEqual({result.run_id for result in results}, {f"run-{i}" for i in range(4)})
        with JobDatabase(self.path) as reopened:
            self.assertEqual(len(reopened.list_runs()), 4)

    def test_concurrent_duplicate_run_ids_leave_one_record(self):
        barrier = threading.Barrier(4)

        def create(_):
            try:
                with JobDatabase(self.path) as database:
                    barrier.wait(timeout=10)
                    return database.start_run("parallel", "fingerprint", run_id="same-run")
            except DuplicateRunError:
                return None

        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(create, range(4)))
        self.assertEqual(sum(result is not None for result in results), 1)
        with JobDatabase(self.path) as reopened:
            self.assertEqual(len(reopened.list_runs()), 1)



