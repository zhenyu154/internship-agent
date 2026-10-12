import unittest

from internship_agent.deduplication import (
    canonicalize_url, job_identity_keys, normalize_text,
)
from internship_agent.models import Job


class IdentityTests(unittest.TestCase):
    def test_text_normalization_handles_unicode_case_and_whitespace(self):
        self.assertEqual(normalize_text("  ＳＯＦＴＷＡＲＥ\tIntern  "), "software intern")

    def test_url_normalization_removes_tracking_and_fragment(self):
        self.assertEqual(
            canonicalize_url(
                " HTTPS://Careers.Example:443/jobs/42?b=2&utm_source=x&a=1&FBCLID=y#details "
            ),
            "https://careers.example/jobs/42?a=1&b=2",
        )

    def test_empty_url_path_matches_root(self):
        self.assertEqual(canonicalize_url("http://EXAMPLE.test:80"), "http://example.test/")

    def test_meaningful_query_values_remain_distinct(self):
        first = canonicalize_url("https://example.test/jobs?id=1")
        second = canonicalize_url("https://example.test/jobs?id=2")
        self.assertNotEqual(first, second)

    def test_repeated_query_value_order_is_preserved(self):
        first = canonicalize_url("https://example.test/jobs?tag=a&tag=b")
        second = canonicalize_url("https://example.test/jobs?tag=b&tag=a")
        self.assertNotEqual(first, second)

    def test_scheme_path_case_and_trailing_slash_remain_distinct(self):
        original = canonicalize_url("https://example.test/Jobs")
        for value in (
            "http://example.test/Jobs", "https://example.test/jobs",
            "https://example.test/Jobs/",
        ):
            with self.subTest(value=value):
                self.assertNotEqual(original, canonicalize_url(value))

    def test_non_default_port_and_ipv6_are_preserved(self):
        self.assertEqual(
            canonicalize_url("https://[::1]:8443/jobs"), "https://[::1]:8443/jobs",
        )

    def test_invalid_urls_are_rejected(self):
        for value in (
            "/jobs/1", "file:///jobs/1", "https:///jobs/1",
            "https://user:secret@example.test/jobs", "https://example.test:bad/jobs",
            "https://bad host.test/jobs",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    canonicalize_url(value)

    def test_strong_identities_do_not_include_a_fallback(self):
        keys = job_identity_keys(Job(
            title="Intern", company="Example", source="Careers", source_job_id="42",
            url="https://example.test/jobs/42",
        ))
        self.assertEqual(len(keys), 2)
        self.assertTrue(keys[0].startswith("source:"))
        self.assertTrue(keys[1].startswith("url:"))

    def test_delimiter_characters_do_not_cause_identity_collisions(self):
        first = Job(title="A|B", company="C", location="D")
        second = Job(title="A", company="B|C", location="D")
        self.assertNotEqual(job_identity_keys(first), job_identity_keys(second))
