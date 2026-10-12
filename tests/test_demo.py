"""Offline P3A tests using authored synthetic fixtures and temporary databases."""

from contextlib import closing, contextmanager, redirect_stderr, redirect_stdout
from dataclasses import asdict
from io import StringIO
import json
from pathlib import Path
import runpy
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from internship_agent import demo
from internship_agent.applications import ApplicationStateError, PRE_SUBMISSION
from internship_agent.candidate_evidence import load_candidate_evidence
from internship_agent.database import JobDatabase, SCHEMA_VERSION
from internship_agent.models import ApplicationRecord, Job, JobMetadata

PUBLIC_ROOT = demo.PUBLIC_ROOT


class DemoTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.directory = self.root / "data" / "demo"
        self.final = self.directory / "demo.sqlite3"
        self.pending = self.directory / "demo.building.sqlite3"
        self.output_patch = patch.multiple(demo, OUTPUT_ROOT=self.root, OUTPUT_DIRECTORY=self.directory)
        self.output_patch.start()
        self.addCleanup(self.output_patch.stop)

    @contextmanager
    def fixture_copy(self):
        fixtures = self.root / "demo" / "fixtures"
        shutil.copytree(demo.FIXTURE_DIRECTORY, fixtures)
        preferences = self.root / "config" / "search_preferences.example.yaml"
        preferences.parent.mkdir()
        shutil.copyfile(demo.PREFERENCES, preferences)
        with patch.multiple(demo, PUBLIC_ROOT=self.root, FIXTURE_DIRECTORY=fixtures, PREFERENCES=preferences):
            yield fixtures

    def interrupt_after_three(self):
        original = JobDatabase.save_job_metadata
        calls = 0

        def interrupt(database, metadata):
            nonlocal calls
            calls += 1
            if calls == 4:
                raise KeyboardInterrupt()
            return original(database, metadata)

        with patch.object(JobDatabase, "save_job_metadata", interrupt):
            with self.assertRaises(KeyboardInterrupt):
                demo.create_demo()

    def test_fixture_contains_ten_valid_jobs_and_four_preparation_records(self):
        entries, fingerprint = demo.load_demo_fixtures()
        self.assertEqual(len(entries), 10)
        self.assertEqual(sum(entry.application is not None for entry in entries), 4)
        self.assertEqual(len(fingerprint), 64)
        for entry in entries:
            self.assertIsInstance(entry.job, Job)
            self.assertTrue(entry.job.company.startswith("Fictional "))
            self.assertTrue(entry.job.description.startswith(demo.NOTICE))
            self.assertEqual(entry.job.url, f"https://example.test/internships/{entry.job.source_job_id}")
            self.assertEqual(entry.metadata["verified_at"], "SYNTHETIC_FIXTURE_NOT_VERIFIED")
            if entry.application:
                self.assertIn(entry.application["status"], PRE_SUBMISSION)
                self.assertTrue(entry.application["notes"].startswith(demo.NOTICE))

    def test_candidate_evidence_uses_existing_interface_and_preserves_limits(self):
        evidence = load_candidate_evidence(demo.FIXTURE_DIRECTORY / "evidence")
        self.assertEqual(evidence.supported, {"python", "numpy", "pytorch", "evaluation", "planning"})
        self.assertEqual([project["id"] for project in evidence.projects],
                         ["demo_grid_navigation", "demo_shape_classifier"])
        self.assertEqual(set(evidence.limitations), {"simulation_only", "generalization_unestablished"})
        profile = (demo.FIXTURE_DIRECTORY / "evidence" / "profile.md").read_text(encoding="utf-8")
        self.assertIn("Synthetic Candidate Demo-01", profile)
        self.assertIn("expected graduation May 2028", profile)
        self.assertIn("Candidate work authorization: UNKNOWN", profile)

    def test_all_evidence_artifacts_are_labeled_without_contact_or_resume_data(self):
        for path in (demo.FIXTURE_DIRECTORY / "evidence").iterdir():
            content = path.read_text(encoding="utf-8")
            self.assertIn(demo.NOTICE, content)
            self.assertNotIn("@", content)
            self.assertNotIn("https://", content)
            self.assertNotIn("C:\\Users\\", content)
        self.assertEqual({path.name for path in (demo.FIXTURE_DIRECTORY / "evidence").iterdir()},
                         {"profile.md", "experience_bank.md", "verification_report.md", "ranking_features.json"})

    def test_existing_relevance_backend_covers_unknown_restriction_and_exclusions(self):
        entries, _ = demo.load_demo_fixtures()
        categories = {entry.job.source_job_id: entry.metadata["relevance_category"] for entry in entries}
        self.assertEqual(categories["demo-001"], "MAIN_SHORTLIST")
        self.assertEqual(categories["demo-005"], "NEEDS_REVIEW")
        self.assertEqual(categories["demo-006"], "NEEDS_REVIEW")
        self.assertEqual(categories["demo-007"], "EXCLUDED")
        self.assertEqual(categories["demo-008"], "EXCLUDED")
        self.assertEqual(categories["demo-009"], "EXCLUDED")

    def test_unsafe_or_unexpected_fixture_fields_are_rejected_before_writes(self):
        with self.fixture_copy() as fixtures:
            path = fixtures / "jobs.json"
            original = path.read_text(encoding="utf-8")
            changes = [
                lambda row: row["job"].update(url="https://jobs.example.com/real-123"),
                lambda row: row["job"].update(source="greenhouse"),
                lambda row: row["job"].update(company="Actual Employer"),
                lambda row: row["job"].update(source_job_id="real-123"),
                lambda row: row["job"].update(applicant_email="fiction@example.test"),
                lambda row: row["application"].update(status="APPLIED"),
                lambda row: row["application"].update(notes="Unlabeled note"),
                lambda row: row["metadata"].update(work_authorization=123),
            ]
            for change in changes:
                with self.subTest(change=change):
                    raw = json.loads(original)
                    change(raw["jobs"][0])
                    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
                    with self.assertRaises((ValueError, TypeError)):
                        demo.create_demo()
                    self.assertFalse(self.directory.exists())

    def test_duplicate_identities_are_rejected(self):
        with self.fixture_copy() as fixtures:
            path = fixtures / "jobs.json"
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["jobs"][1] = raw["jobs"][0]
            path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                demo.create_demo()

    def test_missing_synthetic_notice_is_rejected(self):
        with self.fixture_copy() as fixtures:
            path = fixtures / "jobs.json"
            path.write_text(path.read_text(encoding="utf-8").replace(demo.NOTICE, "Unlabeled"), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "notice"):
                demo.create_demo()

    def test_changed_candidate_sources_fail_closed(self):
        with self.fixture_copy() as fixtures:
            path = fixtures / "evidence" / "profile.md"
            path.write_text(path.read_text(encoding="utf-8") + "\nChanged fictional education.\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "sources changed"):
                demo.create_demo()
            self.assertFalse(self.directory.exists())

    def test_generated_database_is_compatible_and_contains_no_submitted_state(self):
        result = demo.create_demo()
        self.assertEqual((result.path, result.jobs, result.applications), (self.final, 10, 4))
        self.assertFalse(self.pending.exists())
        self.assertFalse((self.directory / "demo.lock").exists())
        with JobDatabase(self.final, read_only=True) as database:
            self.assertEqual(database.count_jobs(), 10)
            for record in database.list_jobs():
                self.assertIsInstance(database.get_job_metadata(record.id), JobMetadata)
            for application in database.list_applications():
                self.assertIsInstance(application, ApplicationRecord)
                self.assertIn(application.status, PRE_SUBMISSION)
                self.assertIsNone(application.submitted_at)
                self.assertEqual(application.receipt_reference, "")
                self.assertNotIn("HUMAN_SUBMISSION_CONFIRMATION",
                                 {event.event for event in database.application_history(application.job_id)})
            run = database.get_run(demo.RUN_ID)
            self.assertEqual((run.status, run.work_item_total, run.work_item_completed), ("COMPLETED", 10, 10))

    def test_sqlite_integrity_foreign_keys_and_schema_are_valid(self):
        result = demo.create_demo()
        self.assertEqual(result.validation, {"integrity_check": "ok", "foreign_key_violations": 0,
                                             "schema_version": SCHEMA_VERSION})
        connection = sqlite3.connect(self.final)
        self.addCleanup(connection.close)
        self.assertEqual(connection.execute("PRAGMA integrity_check").fetchall(), [("ok",)])
        self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
        self.assertEqual(len(connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()), 8)

    def test_validation_detects_foreign_key_corruption_without_changing_records(self):
        demo.create_demo()
        with closing(sqlite3.connect(self.final)) as connection, connection:
            connection.execute("INSERT INTO job_identities VALUES ('invalid-fixture-identity', 999)")
        before = self.final.read_bytes()
        with JobDatabase(self.final, read_only=True) as database:
            with self.assertRaises(sqlite3.DatabaseError):
                database.validate_integrity()
        self.assertEqual(self.final.read_bytes(), before)

    def test_repeated_generation_has_identical_logical_data(self):
        def snapshot(path):
            with JobDatabase(path, read_only=True) as database:
                return (
                    [(record.id, asdict(record.job), asdict(database.get_job_metadata(record.id)))
                     for record in database.list_jobs()],
                    [(record.job_id, record.status, record.notes, record.submitted_at, record.receipt_reference)
                     for record in database.list_applications()],
                    [(event.job_id, event.previous_status, event.new_status, event.event, event.reason)
                     for record in database.list_applications() for event in database.application_history(record.job_id)],
                    database.get_run(demo.RUN_ID).config_fingerprint,
                )
        first = demo.create_demo()
        with patch.object(demo, "OUTPUT_DIRECTORY", self.root / "second-demo"):
            second = demo.create_demo()
        self.assertEqual(first.fixture_fingerprint, second.fixture_fingerprint)
        self.assertEqual(snapshot(first.path), snapshot(second.path))

    def test_existing_final_database_is_never_opened_or_overwritten(self):
        self.directory.mkdir(parents=True)
        self.final.write_bytes(b"Synthetic sentinel; not a user database")
        with patch("sqlite3.connect", side_effect=AssertionError("Existing database was opened")):
            with self.assertRaises(FileExistsError):
                demo.create_demo()
        self.assertEqual(self.final.read_bytes(), b"Synthetic sentinel; not a user database")
        self.assertFalse(self.pending.exists())

    def test_existing_final_sidecars_are_never_touched(self):
        self.directory.mkdir(parents=True)
        sidecar = Path(str(self.final) + "-wal")
        sidecar.write_bytes(b"Synthetic sidecar sentinel")
        with self.assertRaises(FileExistsError):
            demo.create_demo()
        self.assertEqual(sidecar.read_bytes(), b"Synthetic sidecar sentinel")
        self.assertFalse(self.pending.exists())

    def test_existing_partial_requires_explicit_recovery_without_opening_it(self):
        self.directory.mkdir(parents=True)
        self.pending.write_bytes(b"Synthetic partial sentinel")
        with patch("sqlite3.connect", side_effect=AssertionError("Partial database was opened")):
            with self.assertRaises(FileExistsError):
                demo.create_demo()
        self.assertEqual(self.pending.read_bytes(), b"Synthetic partial sentinel")

    def test_resume_requires_an_existing_partial(self):
        with self.assertRaisesRegex(FileExistsError, "No partial"):
            demo.create_demo(resume=True)
        self.assertFalse(self.directory.exists())

    def test_output_cannot_escape_the_public_workspace(self):
        with patch.object(demo, "OUTPUT_DIRECTORY", self.root.parent / "outside-demo"):
            with self.assertRaisesRegex(ValueError, "public workspace"):
                demo.create_demo()

    def test_redirected_paths_are_rejected_before_database_access(self):
        for method in ("is_symlink", "is_junction"):
            with self.subTest(method=method), patch.object(Path, method, return_value=True):
                with patch("sqlite3.connect", side_effect=AssertionError("Redirect was followed")):
                    with self.assertRaisesRegex(ValueError, "symlinks"):
                        demo.create_demo()

    def test_concurrent_or_stale_lock_is_preserved(self):
        self.directory.mkdir(parents=True)
        lock = self.directory / "demo.lock"
        lock.write_text(demo.NOTICE, encoding="utf-8")
        with self.assertRaises(FileExistsError):
            demo.create_demo()
        self.assertEqual(lock.read_text(encoding="utf-8"), demo.NOTICE)
        self.assertFalse(self.pending.exists())

    def test_interrupted_run_preserves_progress_and_recovers_without_duplicates(self):
        self.interrupt_after_three()
        self.assertFalse(self.final.exists())
        with JobDatabase(self.pending, read_only=True) as database:
            self.assertEqual(database.count_jobs(), 4)
            self.assertEqual(database.get_run(demo.RUN_ID).status, "INTERRUPTED")
            self.assertEqual(database.get_run(demo.RUN_ID).work_item_completed, 3)
            previous = database.list_jobs()
            history = database.application_history(1)
        demo.create_demo(resume=True)
        with JobDatabase(self.final, read_only=True) as database:
            self.assertEqual(database.list_jobs()[:4], previous)
            self.assertEqual(database.application_history(1), history)
            self.assertEqual(len(database.list_applications()), 4)
            self.assertEqual(sum(len(database.application_history(i)) for i in range(1, 5)), 7)
            self.assertEqual(database.validate_integrity()["integrity_check"], "ok")

    def test_unrelated_partial_database_is_rejected_without_mutation(self):
        with JobDatabase(self.pending):
            pass
        before = self.pending.read_bytes()
        with self.assertRaisesRegex(ValueError, "compatible synthetic"):
            demo.create_demo(resume=True)
        self.assertEqual(self.pending.read_bytes(), before)

    def test_changed_fixture_fingerprint_prevents_recovery(self):
        self.interrupt_after_three()
        before = self.pending.read_bytes()
        with self.fixture_copy() as fixtures:
            path = fixtures / "jobs.json"
            path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "compatible synthetic"):
                demo.create_demo(resume=True)
        self.assertEqual(self.pending.read_bytes(), before)

    def test_manual_application_notes_are_preserved_on_recovery_conflict(self):
        self.interrupt_after_three()
        with JobDatabase(self.pending) as database:
            database.add_application_note(1, demo.NOTICE + " Manually edited fictional note.")
        before = self.pending.read_bytes()
        with self.assertRaisesRegex(ValueError, "preserving"):
            demo.create_demo(resume=True)
        self.assertEqual(self.pending.read_bytes(), before)

    def test_completed_partial_can_be_published_after_a_publication_failure(self):
        with patch.object(demo.os, "link", side_effect=OSError("Synthetic publication failure")):
            with self.assertRaises(OSError):
                demo.create_demo()
        with JobDatabase(self.pending, read_only=True) as database:
            self.assertEqual(database.get_run(demo.RUN_ID).status, "COMPLETED")
        with patch.object(JobDatabase, "add_job", side_effect=AssertionError("Already completed job was rewritten")):
            result = demo.create_demo(resume=True)
        self.assertEqual(result.jobs, 10)

    def test_manual_status_reversal_on_an_unfinished_item_is_preserved(self):
        original = JobDatabase.save_item_progress

        def interrupt(database, run_id, item_key, state, error_details=""):
            if item_key == "demo-001" and state == "COMPLETED":
                raise KeyboardInterrupt()
            return original(database, run_id, item_key, state, error_details)

        with patch.object(JobDatabase, "save_item_progress", interrupt):
            with self.assertRaises(KeyboardInterrupt):
                demo.create_demo()
        with JobDatabase(self.pending) as database:
            database.set_application_status(1, "NOT_STARTED", reason=demo.NOTICE + " Manual status reversal.")
        before = self.pending.read_bytes()
        with self.assertRaisesRegex(ValueError, "history.*preserving"):
            demo.create_demo(resume=True)
        self.assertEqual(self.pending.read_bytes(), before)
        self.assertFalse(self.final.exists())

    def test_publication_race_preserves_a_newly_existing_final_file(self):
        def competing_file(source, destination):
            destination.write_bytes(b"Synthetic competing-file sentinel")
            raise FileExistsError("Synthetic publication race")
        with patch.object(demo.os, "link", side_effect=competing_file):
            with self.assertRaises(FileExistsError):
                demo.create_demo()
        self.assertEqual(self.final.read_bytes(), b"Synthetic competing-file sentinel")
        self.assertTrue(self.pending.exists())

    def test_existing_application_transition_and_confirmation_guards_remain_active(self):
        demo.create_demo()
        with JobDatabase(self.final) as database:
            before = database.get_application(1)
            history = database.application_history(1)
            for operation in (
                lambda: database.set_application_status(1, "APPLIED"),
                lambda: database.mark_application_submitted(1, "2000-01-01", confirmed_by_user=False),
                lambda: database.set_application_status(1, "OFFER"),
            ):
                with self.assertRaises(ApplicationStateError):
                    operation()
            self.assertEqual(database.get_application(1), before)
            self.assertEqual(database.application_history(1), history)

    def test_initializer_never_uses_submission_or_network_functions(self):
        with (patch.object(JobDatabase, "mark_application_submitted", side_effect=AssertionError("Submission called")),
              patch("socket.create_connection", side_effect=AssertionError("Network called")),
              patch("socket.getaddrinfo", side_effect=AssertionError("DNS called")),
              patch("urllib.request.urlopen", side_effect=AssertionError("HTTP called"))):
            self.assertEqual(demo.create_demo().jobs, 10)

    def test_no_private_inputs_or_real_job_description_fixtures_are_read(self):
        allowed_fixtures = {demo.PREFERENCES, demo.FIXTURE_DIRECTORY / "jobs.json",
                            *(demo.FIXTURE_DIRECTORY / "evidence" / name for name in
                              ("profile.md", "experience_bank.md", "verification_report.md", "ranking_features.json"))}
        original_bytes, original_text = Path.read_bytes, Path.read_text
        observed = set()

        def read_bytes(path):
            self.assertIn(path, allowed_fixtures)
            observed.add(path)
            return original_bytes(path)

        def read_text(path, *args, **kwargs):
            self.assertIn(path, allowed_fixtures)
            observed.add(path)
            return original_text(path, *args, **kwargs)

        with patch.object(Path, "read_bytes", read_bytes), patch.object(Path, "read_text", read_text):
            demo.create_demo()
        self.assertEqual(observed, allowed_fixtures)

    def test_standalone_entry_point_reports_counts_and_refuses_overwrite(self):
        namespace = runpy.run_path(str(PUBLIC_ROOT / "scripts" / "create_demo.py"))
        main = namespace["main"]
        with patch.dict(main.__globals__, PUBLIC_ROOT=self.root), patch("sys.argv", ["create_demo.py"]):
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(), 0)
            self.assertIn(demo.NOTICE, output.getvalue())
            self.assertIn("Synthetic jobs: 10; synthetic application records: 4", output.getvalue())
            self.assertIn("SQLite integrity: ok", output.getvalue())
            self.assertIn("data/demo/demo.sqlite3", output.getvalue())
            self.assertNotIn(str(self.root), output.getvalue())
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                self.assertEqual(main(), 1)


if __name__ == "__main__":
    unittest.main()
