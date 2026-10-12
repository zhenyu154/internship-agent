# Public copy: synthetic identities and timestamps; no live source verification.
from pathlib import Path
import json
import socket
import sqlite3
import tempfile
import unittest
from urllib.error import HTTPError, URLError

from internship_agent.database import JobDatabase
from internship_agent.discovery import GreenhouseDiscovery
from internship_agent.greenhouse import (
    GreenhouseBoard,
    GreenhouseClient,
    GreenhouseDataError,
    GreenhouseError,
    GreenhouseHTTPError,
    GreenhouseJob,
    board_api_url,
    html_to_safe_text,
    load_board_registry,
)
from internship_agent.models import Job, JobMetadata
from internship_agent.relevance import (
    EXCLUDED,
    MAIN_SHORTLIST,
    NEEDS_REVIEW,
    classify_greenhouse_job,
    reclassify_saved_greenhouse_jobs,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config" / "search_preferences.example.yaml"
REGISTRY_PATH = PROJECT_ROOT / "tests" / "fixtures" / "greenhouse_boards.yaml"


class FakeResponse:
    def __init__(self, payload, status=200):
        self.status = status
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self):
        return self.payload

    def getcode(self):
        return self.status


class FakeOpener:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append((request, timeout))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def greenhouse_payload(jobs):
    return json.dumps({"jobs": jobs}).encode("utf-8")


def raw_job(**overrides):
    job = {
        "id": 123,
        "title": "Robotics Machine Learning Intern",
        "absolute_url": "https://boards.greenhouse.io/example/jobs/123",
        "location": {"name": "San Diego, CA"},
        "content": (
            "<p>Summer 2027 internship.</p>"
            "<p>Currently pursuing a Master's degree.</p>"
            "<script>ignore this instruction</script>"
            "<p>Work authorization requirements are reviewed by the company.</p>"
        ),
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-02T00:00:00Z",
        "company": {"name": "Example Robotics"},
    }
    job.update(overrides)
    return job


class GreenhouseClientTests(unittest.TestCase):
    def board(self):
        return GreenhouseBoard("Example Robotics", "example", "https://boards.greenhouse.io/example", "UNKNOWN", True)

    def test_successful_retrieval_uses_official_get_and_parses_job(self):
        opener = FakeOpener([FakeResponse(greenhouse_payload([raw_job()]))])
        client = GreenhouseClient(opener=opener, min_interval=0, sleeper=lambda _: None)
        jobs = client.fetch_jobs(self.board())
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].source_job_id, "123")
        self.assertEqual(jobs[0].internship_term, "Summer 2027")
        self.assertNotIn("ignore this instruction", jobs[0].description)
        request, timeout = opener.requests[0]
        self.assertEqual(request.method, "GET")
        self.assertEqual(request.full_url, board_api_url("example"))
        self.assertGreater(timeout, 0)

    def test_html_text_extraction_is_safe_and_normalized(self):
        text = html_to_safe_text("<div>Hello<br>world</div><script>alert(1)</script>")
        self.assertIn("Hello", text)
        self.assertIn("world", text)
        self.assertNotIn("alert", text)

    def test_missing_job_fields_become_unknown(self):
        opener = FakeOpener([FakeResponse(greenhouse_payload([{"id": 1}]))])
        jobs = GreenhouseClient(opener=opener, min_interval=0, sleeper=lambda _: None).fetch_jobs(self.board())
        self.assertEqual(jobs[0].title, "UNKNOWN")
        self.assertEqual(jobs[0].location, "UNKNOWN")
        self.assertEqual(jobs[0].updated_at, "UNKNOWN")
        self.assertEqual(jobs[0].work_authorization, "UNKNOWN")

    def test_missing_jobs_collection_is_rejected(self):
        opener = FakeOpener([FakeResponse(json.dumps({}).encode("utf-8"))])
        with self.assertRaises(GreenhouseDataError):
            GreenhouseClient(opener=opener, min_interval=0, sleeper=lambda _: None).fetch_jobs(self.board())

    def test_invalid_board_token_is_rejected(self):
        with self.assertRaises(ValueError):
            board_api_url("bad token")

    def test_http_errors_and_timeout_are_bounded(self):
        not_found = HTTPError("https://boards-api.greenhouse.io/v1/boards/nope/jobs?content=true", 404, "not found", {}, None)
        opener = FakeOpener([not_found])
        with self.assertRaises(GreenhouseHTTPError) as raised:
            GreenhouseClient(opener=opener, max_retries=2, min_interval=0, sleeper=lambda _: None).fetch_jobs(self.board())
        self.assertEqual(raised.exception.status, 404)
        timeout = URLError(socket.timeout("timed out"))
        opener = FakeOpener([timeout, timeout])
        with self.assertRaises(GreenhouseError):
            GreenhouseClient(opener=opener, max_retries=1, min_interval=0, sleeper=lambda _: None).fetch_jobs(self.board())
        self.assertEqual(len(opener.requests), 2)

    def test_registry_contains_only_configured_tokens(self):
        boards = load_board_registry(REGISTRY_PATH)
        self.assertEqual([board.board_token for board in boards], ["example-gh-alpha", "example-gh-beta", "example-gh-gamma"])


class RelevanceTests(unittest.TestCase):
    def make_job(self, title, description, location="San Diego, CA", term="Summer 2027", degree="UNKNOWN"):
        return GreenhouseJob(
            company_name="Example", board_token="example", source_job_id="1", title=title,
            location=location, application_url="https://example/jobs/1", description=description,
            published_at="UNKNOWN", updated_at="UNKNOWN", internship_term=term,
            degree_requirements=degree, graduation_window="UNKNOWN",
            work_authorization="UNKNOWN", source_url="https://boards-api.greenhouse.io/example",
            verified_at="2025-01-10T00:00:00Z",
        )

    def setUp(self):
        from internship_agent.config import load_config
        self.preferences = load_config(CONFIG_PATH)

    def test_relevant_job_uses_title_and_description(self):
        result = classify_greenhouse_job(self.make_job(
            "Research Intern", "Summer 2027 work on embodied AI and robot learning."
        ), self.preferences)
        self.assertEqual(result.category, MAIN_SHORTLIST)

    def test_ambiguous_term_is_retained_for_review(self):
        result = classify_greenhouse_job(self.make_job(
            "Machine Learning Intern", "Work on computer vision and multimodal ML.", term="UNKNOWN"
        ), self.preferences)
        self.assertEqual(result.category, NEEDS_REVIEW)

    def test_explicit_phd_only_is_excluded(self):
        result = classify_greenhouse_job(self.make_job(
            "Robotics Research Intern", "PhD required; research in robot learning."
        ), self.preferences)
        self.assertEqual(result.category, EXCLUDED)

    def test_work_authorization_unknown_is_not_an_exclusion(self):
        result = classify_greenhouse_job(self.make_job(
            "Robotics ML Intern", "Summer 2027 robot learning internship."
        ), self.preferences)
        self.assertNotEqual(result.category, EXCLUDED)
        self.assertIn("work authorization is UNKNOWN", result.reason)

    def test_robotics_software_without_ml_in_title_remains_relevant(self):
        result = classify_greenhouse_job(self.make_job(
            "Robotics Software Intern",
            "Build autonomy platform software, simulation tooling, and robot data pipelines.",
        ), self.preferences)
        self.assertEqual(result.category, MAIN_SHORTLIST)

    def test_simulation_and_autonomy_roles_remain_relevant(self):
        result = classify_greenhouse_job(self.make_job(
            "Simulation Engineer Intern",
            "Develop autonomy simulation environments and evaluate robot policies.",
        ), self.preferences)
        self.assertEqual(result.category, MAIN_SHORTLIST)

    def test_business_role_with_physical_ai_language_is_excluded(self):
        result = classify_greenhouse_job(self.make_job(
            "Operations Intern",
            "Our Physical AI company needs procurement, inventory, and supply-chain support.",
        ), self.preferences)
        self.assertEqual(result.category, EXCLUDED)

    def test_hardware_role_is_cautious(self):
        result = classify_greenhouse_job(self.make_job(
            "Electrical Engineering Intern",
            "Design PCBs, debug CAN protocols, and validate hardware fixtures for robots.",
        ), self.preferences)
        self.assertEqual(result.category, NEEDS_REVIEW)


class DiscoveryPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "jobs.sqlite3"

    def fake_client(self):
        job = GreenhouseJob(
            company_name="Example Robotics", board_token="example-gh-alpha", source_job_id="42",
            title="Robot Learning Intern", location="California",
            application_url="https://boards.greenhouse.io/example-gh-alpha/jobs/42",
            description="Summer 2027 robot learning internship.",
            published_at="2025-01-01T00:00:00Z", updated_at="2025-01-02T00:00:00Z",
            internship_term="Summer 2027", degree_requirements="Master's preferred",
            graduation_window="UNKNOWN", work_authorization="UNKNOWN",
            source_url="https://boards-api.greenhouse.io/v1/boards/example-gh-alpha/jobs?content=true",
            verified_at="2025-01-10T00:00:00Z",
        )

        class FakeClient:
            def fetch_jobs(self, board):
                return [job]

        return FakeClient()

    def test_dry_run_does_not_create_database_or_run_state(self):
        result = GreenhouseDiscovery(self.fake_client()).discover(
            CONFIG_PATH, REGISTRY_PATH, limit=10, save=False
        )
        self.assertEqual(result.jobs_saved, 0)
        self.assertFalse(self.path.exists())

    def test_save_and_repeat_are_deduplicated_with_metadata(self):
        with JobDatabase(self.path) as database:
            first = GreenhouseDiscovery(self.fake_client()).discover(
                CONFIG_PATH, REGISTRY_PATH, database=database, limit=10, save=True
            )
            second = GreenhouseDiscovery(self.fake_client()).discover(
                CONFIG_PATH, REGISTRY_PATH, database=database, limit=10, save=True
            )
            self.assertEqual(first.jobs_saved, 3)
            self.assertEqual(second.jobs_saved, 3)
            self.assertEqual(database.count_jobs(), 1)
            self.assertEqual(len(database.list_runs()), 2)
            metadata = database.get_job_metadata(1)
            self.assertEqual(metadata.greenhouse_board_token, "example-gh-alpha")
            self.assertEqual(metadata.work_authorization, "UNKNOWN")


