import unittest

from internship_agent.models import Job


class JobTests(unittest.TestCase):
    def test_required_fields_are_trimmed(self):
        job = Job(title="  Research Intern  ", company="  Example Lab  ")
        self.assertEqual((job.title, job.company), ("Research Intern", "Example Lab"))
        self.assertEqual(job.location, "")

    def test_blank_required_fields_are_rejected(self):
        for field in ("title", "company"):
            with self.subTest(field=field):
                values = {"title": "Intern", "company": "Example", field: " \t\n"}
                with self.assertRaisesRegex(ValueError, field):
                    Job(**values)

    def test_non_string_fields_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "location"):
            Job(title="Intern", company="Example", location=None)

    def test_source_job_id_requires_source(self):
        with self.assertRaisesRegex(ValueError, "source is required"):
            Job(title="Intern", company="Example", source_job_id="123")

    def test_description_preserves_internal_newlines(self):
        job = Job(title="Intern", company="Example", description="  First\nSecond  ")
        self.assertEqual(job.description, "First\nSecond")
