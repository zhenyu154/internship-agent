from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from internship_agent.database import (
    DeduplicationConflictError, JobDatabase, SCHEMA_VERSION,
)
from internship_agent.models import Job


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "nested" / "jobs.sqlite3"
        self.database = JobDatabase(self.path)
        self.addCleanup(self.database.close)
        self.job = Job(title="Software Intern", company="Example Company", location="Remote")

    def test_initializes_an_empty_database_and_schema_version(self):
        self.assertTrue(self.path.is_file())
        self.assertEqual(self.database.list_jobs(), [])
        self.assertEqual(self.database.count_jobs(), 0)
        connection = sqlite3.connect(self.path)
        try:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
            tables = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )}
        finally:
            connection.close()
        self.assertEqual(
            tables,
            {"jobs", "job_identities", "execution_runs", "work_items", "job_metadata", "discovery_checkpoints", "applications", "application_status_history"},
        )

    def test_add_get_and_reopen_preserve_all_fields(self):
        job = replace(
            self.job, url="https://example.test/jobs/42", source="manual",
            source_job_id="42", description="Python and SQLite",
        )
        result = self.database.add_job(job)
        self.assertTrue(result.created)
        self.assertEqual(result.record.job, job)
        self.assertEqual(self.database.get_job(result.record.id), result.record)
        self.assertEqual(datetime.fromisoformat(result.record.created_at).tzinfo, timezone.utc)
        self.assertIsNone(self.database.get_job(999))
        self.database.close()
        with JobDatabase(self.path) as reopened:
            self.assertEqual(reopened.list_jobs(), [result.record])
            duplicate = reopened.add_job(job)
            self.assertFalse(duplicate.created)
            self.assertEqual(duplicate.record, result.record)

    def test_fallback_deduplicates_case_whitespace_and_unicode(self):
        first = self.database.add_job(self.job)
        second = self.database.add_job(Job(
            title="  ＳＯＦＴＷＡＲＥ   INTERN ", company="example company",
            location=" REMOTE ", description="A different description", source="manual",
        ))
        self.assertFalse(second.created)
        self.assertEqual(second.record, first.record)
        self.assertEqual(self.database.count_jobs(), 1)

    def test_fallback_keeps_different_titles_companies_and_locations(self):
        self.database.add_job(self.job)
        for job in (
            replace(self.job, title="Research Intern"),
            replace(self.job, company="Another Company"),
            replace(self.job, location="Seattle"),
        ):
            with self.subTest(job=job):
                self.assertTrue(self.database.add_job(job).created)
        self.assertEqual(self.database.count_jobs(), 4)

    def test_source_id_deduplicates_without_overwriting_original(self):
        first = self.database.add_job(replace(self.job, source="Example Careers", source_job_id="42"))
        second = self.database.add_job(replace(
            self.job, title="Updated title", location="Seattle", source=" EXAMPLE   CAREERS ",
            source_job_id=" 42 ", description="Updated description",
        ))
        self.assertFalse(second.created)
        self.assertEqual(second.record, first.record)

    def test_distinct_source_ids_are_separate_postings(self):
        for job_id in ("42", "43"):
            self.assertTrue(self.database.add_job(
                replace(self.job, source="careers", source_job_id=job_id)
            ).created)
        self.assertEqual(self.database.count_jobs(), 2)

    def test_source_job_ids_are_case_sensitive(self):
        for job_id in ("ABC", "abc"):
            self.assertTrue(self.database.add_job(
                replace(self.job, source="careers", source_job_id=job_id)
            ).created)
        self.assertEqual(self.database.count_jobs(), 2)

    def test_source_ids_are_scoped_to_source(self):
        for source in ("company careers", "campus board"):
            self.assertTrue(self.database.add_job(
                replace(self.job, source=source, source_job_id="42")
            ).created)
        self.assertEqual(self.database.count_jobs(), 2)

    def test_url_deduplicates_tracking_variants(self):
        first = self.database.add_job(replace(
            self.job, url="https://careers.example/jobs/42?team=eng",
        ))
        duplicate = self.database.add_job(replace(
            self.job, title="Updated title",
            url="HTTPS://CAREERS.EXAMPLE:443/jobs/42?utm_campaign=fall&team=eng#apply",
        ))
        self.assertFalse(duplicate.created)
        self.assertEqual(duplicate.record, first.record)
        self.assertEqual(self.database.count_jobs(), 1)

    def test_distinct_url_job_parameters_do_not_merge(self):
        for job_id in ("42", "43"):
            self.assertTrue(self.database.add_job(replace(
                self.job, url=f"https://example.test/jobs?id={job_id}",
            )).created)
        self.assertEqual(self.database.count_jobs(), 2)

    def test_duplicate_attaches_new_source_identity(self):
        first = self.database.add_job(replace(self.job, url="https://example.test/jobs/42"))
        second = self.database.add_job(replace(
            self.job, url="https://example.test/jobs/42", source="careers", source_job_id="42",
        ))
        third = self.database.add_job(replace(self.job, source="careers", source_job_id="42"))
        self.assertFalse(second.created)
        self.assertFalse(third.created)
        self.assertEqual(third.record, first.record)
        self.assertEqual(self.database.count_jobs(), 1)

    def test_duplicate_attaches_new_url_identity(self):
        first = self.database.add_job(replace(self.job, source="careers", source_job_id="42"))
        second = self.database.add_job(replace(
            self.job, source="careers", source_job_id="42", url="https://example.test/jobs/42",
        ))
        third = self.database.add_job(replace(self.job, url="https://example.test/jobs/42"))
        self.assertFalse(second.created)
        self.assertFalse(third.created)
        self.assertEqual(third.record, first.record)

    def test_strong_and_fallback_records_do_not_automatically_merge(self):
        first = self.database.add_job(self.job)
        second = self.database.add_job(replace(self.job, source="careers", source_job_id="42"))
        self.assertTrue(first.created)
        self.assertTrue(second.created)
        self.assertNotEqual(first.record.id, second.record.id)

    def test_conflicting_identities_roll_back_and_allow_future_writes(self):
        first = self.database.add_job(replace(self.job, source="careers", source_job_id="42"))
        second = self.database.add_job(replace(self.job, url="https://example.test/jobs/43"))
        with self.assertRaises(DeduplicationConflictError):
            self.database.add_job(replace(
                self.job, source="careers", source_job_id="42", url="https://example.test/jobs/43",
            ))
        self.assertEqual(self.database.list_jobs(), [first.record, second.record])
        self.assertTrue(self.database.add_job(replace(self.job, company="Another Company")).created)

    def test_invalid_url_does_not_create_a_job(self):
        with self.assertRaises(ValueError):
            self.database.add_job(replace(self.job, url="/relative/jobs/42"))
        self.assertEqual(self.database.count_jobs(), 0)
        self.assertTrue(self.database.add_job(self.job).created)

    def test_sql_special_characters_are_stored_as_data(self):
        job = replace(self.job, title="Intern'); DROP TABLE jobs; --")
        self.assertEqual(self.database.add_job(job).record.job.title, job.title)
        self.assertEqual(self.database.count_jobs(), 1)

    def test_list_jobs_is_ordered_by_id(self):
        first = self.database.add_job(replace(self.job, title="Z Intern"))
        second = self.database.add_job(replace(self.job, title="A Intern"))
        self.assertEqual(self.database.list_jobs(), [first.record, second.record])

    def test_sqlite_enforces_unique_identities_and_foreign_keys(self):
        result = self.database.add_job(self.job)
        connection = sqlite3.connect(self.path)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            identity = connection.execute("SELECT identity_key FROM job_identities").fetchone()[0]
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO job_identities (identity_key, job_id) VALUES (?, ?)",
                    (identity, result.record.id),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO job_identities (identity_key, job_id) VALUES (?, ?)",
                    ("unmatched-identity", 999),
                )
        finally:
            connection.close()

    def test_unsupported_schema_version_is_rejected(self):
        other_path = self.path.parent / "future.sqlite3"
        connection = sqlite3.connect(other_path)
        try:
            connection.execute("PRAGMA user_version = 99")
            connection.commit()
        finally:
            connection.close()
        with self.assertRaisesRegex(ValueError, "Unsupported database schema version: 99"):
            JobDatabase(other_path)

    def test_concurrent_duplicate_submissions_create_one_job(self):
        barrier = threading.Barrier(4)

        def submit(_):
            with JobDatabase(self.path) as database:
                barrier.wait(timeout=10)
                return database.add_job(replace(
                    self.job, source="careers", source_job_id="42",
                ))

        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(submit, range(4)))
        self.assertEqual(sum(result.created for result in results), 1)
        self.assertEqual(len({result.record.id for result in results}), 1)
        self.assertEqual(self.database.count_jobs(), 1)

