import csv
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from internship_agent.database import JobDatabase
from internship_agent.exports import CSV_FIELDS, export_jobs
from internship_agent.models import Job


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.database = JobDatabase(self.root / "jobs.sqlite3")
        self.addCleanup(self.database.close)
        self.output = self.root / "reports" / "jobs.csv"

    def test_empty_export_still_writes_a_header(self):
        self.assertEqual(export_jobs(self.database, self.output), 0)
        with self.output.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.reader(stream))
        self.assertEqual(rows, [list(CSV_FIELDS)])

    def test_unicode_quotes_commas_and_newlines_round_trip(self):
        job = Job(
            title='Research Intern, "2027"', company="Example Café",
            location="Montréal", description="First line\nSecond, quoted \"line\"",
        )
        record = self.database.add_job(job).record
        self.assertEqual(export_jobs(self.database, self.output), 1)
        with self.output.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], str(record.id))
        self.assertEqual(rows[0]["title"], job.title)
        self.assertEqual(rows[0]["company"], job.company)
        self.assertEqual(rows[0]["description"], job.description)
        self.assertEqual(rows[0]["created_at"], record.created_at)

    def test_export_replaces_previous_snapshot_in_id_order(self):
        first = self.database.add_job(Job(title="Z Intern", company="Example"))
        export_jobs(self.database, self.output)
        second = self.database.add_job(Job(title="A Intern", company="Example"))
        self.assertEqual(export_jobs(self.database, self.output), 2)
        with self.output.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual([row["id"] for row in rows], [str(first.record.id), str(second.record.id)])
        self.assertEqual(self.database.count_jobs(), 2)

    def test_export_cannot_overwrite_the_database(self):
        self.database.add_job(Job(title="Intern", company="Example"))
        with self.assertRaisesRegex(ValueError, "must not overwrite"):
            export_jobs(self.database, self.database.path)
        self.assertEqual(self.database.count_jobs(), 1)

    def test_failed_export_preserves_previous_snapshot_and_cleans_temporary_file(self):
        export_jobs(self.database, self.output)
        previous = self.output.read_bytes()
        self.database.add_job(Job(title="Intern", company="Example"))
        with patch("internship_agent.exports.os.replace", side_effect=OSError("simulated failure")):
            with self.assertRaisesRegex(OSError, "simulated failure"):
                export_jobs(self.database, self.output)
        self.assertEqual(self.output.read_bytes(), previous)
        self.assertEqual(list(self.output.parent.iterdir()), [self.output])
