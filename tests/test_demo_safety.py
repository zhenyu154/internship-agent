"""Synthetic adversarial recovery cases; no user or private databases."""

from contextlib import closing
from dataclasses import replace
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from internship_agent import demo
from internship_agent.database import JobDatabase


class DemoRecoverySafetyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.output = self.root / "data" / "demo"
        self.pending = self.output / "demo.building.sqlite3"
        self.entries, self.fingerprint = demo.load_demo_fixtures()
        self.patch = patch.multiple(demo, OUTPUT_ROOT=self.root, OUTPUT_DIRECTORY=self.output)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def seed_run(self):
        with JobDatabase(self.pending) as database:
            database.start_run(demo.RUN_TYPE, self.fingerprint,
                               [entry.job.source_job_id for entry in self.entries], demo.RUN_ID)

    def assert_refused_unchanged(self):
        before = self.pending.read_bytes()
        with self.assertRaises((ValueError, sqlite3.DatabaseError)):
            demo.create_demo(resume=True)
        self.assertEqual(self.pending.read_bytes(), before)
        self.assertFalse((self.output / "demo.sqlite3").exists())
        self.assertFalse((self.output / "demo.lock").exists())

    def test_extended_schema_and_trigger_cannot_modify_unrelated_records(self):
        self.seed_run()
        with closing(sqlite3.connect(self.pending)) as connection, connection:
            connection.execute("CREATE TABLE unrelated_records (value TEXT)")
            connection.execute("INSERT INTO unrelated_records VALUES ('Synthetic unrelated sentinel')")
            connection.execute("CREATE TRIGGER unrelated_trigger AFTER INSERT ON jobs BEGIN "
                               "UPDATE unrelated_records SET value=value || '.'; END")
        self.assert_refused_unchanged()
        with closing(sqlite3.connect(self.pending)) as connection:
            self.assertEqual(connection.execute("SELECT value FROM unrelated_records").fetchone()[0],
                             "Synthetic unrelated sentinel")

    def test_extra_table_without_a_trigger_is_refused(self):
        self.seed_run()
        with closing(sqlite3.connect(self.pending)) as connection:
            connection.execute("CREATE TABLE unrelated_records (value TEXT)")
        self.assert_refused_unchanged()

    def test_altered_append_only_constraints_are_refused(self):
        self.seed_run()
        with closing(sqlite3.connect(self.pending)) as connection:
            connection.execute("DROP TRIGGER application_history_no_update")
        self.assert_refused_unchanged()

    def test_extra_identity_alias_is_refused(self):
        self.seed_run()
        with JobDatabase(self.pending) as database:
            database.add_job(self.entries[0].job)
            database.add_job(replace(self.entries[0].job, url="https://example.test/unrelated-alias"))
        self.assert_refused_unchanged()

    def test_unrelated_discovery_payload_is_refused(self):
        self.seed_run()
        with JobDatabase(self.pending) as database:
            database.save_discovery_checkpoint(demo.RUN_ID, self.entries[0].job.source_job_id,
                                              {"notice": demo.NOTICE, "unrelated": "Synthetic sentinel"})
        self.assert_refused_unchanged()

    def test_arbitrary_older_database_is_not_migrated_or_backed_up(self):
        self.seed_run()
        with closing(sqlite3.connect(self.pending)) as connection:
            connection.execute("PRAGMA user_version = 5")
        self.assert_refused_unchanged()
        self.assertEqual(list(self.output.glob("*.bak")), [])

    def test_unrelated_run_diagnostics_are_preserved(self):
        self.seed_run()
        with closing(sqlite3.connect(self.pending)) as connection, connection:
            connection.execute("UPDATE execution_runs SET error_summary='Synthetic unrelated diagnostics'")
        self.assert_refused_unchanged()

    def test_unrelated_work_item_errors_are_preserved(self):
        self.seed_run()
        with JobDatabase(self.pending) as database:
            database.save_item_progress(demo.RUN_ID, self.entries[0].job.source_job_id,
                                        "IN_PROGRESS", "Synthetic unrelated work-item diagnostic")
        self.assert_refused_unchanged()

    def test_completed_items_cannot_hide_missing_payloads(self):
        self.seed_run()
        with JobDatabase(self.pending) as database:
            database.save_item_progress(demo.RUN_ID, self.entries[0].job.source_job_id, "COMPLETED")
        self.assert_refused_unchanged()


if __name__ == "__main__":
    unittest.main()
