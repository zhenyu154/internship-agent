# Public copy: synthetic identities and timestamps; no live source verification.
import json
from pathlib import Path
import tempfile
import unittest

from internship_agent.ashby import AshbyClient, AshbyDataError, AshbyError, load_ashby_registry
from internship_agent.ashby_discovery import AshbyDiscovery
from internship_agent.database import JobDatabase
from internship_agent.relevance import EXCLUDED, MAIN_SHORTLIST, NEEDS_REVIEW

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "search_preferences.example.yaml"
REGISTRY = ROOT / "tests" / "fixtures" / "ashby_boards.yaml"


class Response:
    def __init__(self, payload, status=200):
        self.data = json.dumps(payload).encode()
        self.status = status
    def __enter__(self): return self
    def __exit__(self, *args): return None
    def read(self): return self.data
    def getcode(self): return self.status


class Opener:
    def __init__(self, responses): self.responses = list(responses); self.requests = []
    def __call__(self, request, timeout):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception): raise response
        return response


def job(title, description, **extra):
    value = {
        "id": title,
        "companyName": "Example Ashby Alpha",
        "title": title,
        "department": "Engineering",
        "team": "Robotics",
        "location": "Palo Alto, CA",
        "secondaryLocations": ["Remote, US"],
        "workplaceType": "Hybrid",
        "employmentType": "FullTime",
        "descriptionPlain": description,
        "jobUrl": f"https://jobs.ashbyhq.com/example-ashby-alpha/{title.replace(' ', '-')}",
        "applyUrl": f"https://jobs.ashbyhq.com/example-ashby-alpha/{title.replace(' ', '-')}",
        "publishedAt": "2025-01-01T00:00:00Z",
        "compensation": {"min": 40, "max": 60, "currency": "USD"},
        "isListed": True,
    }
    value.update(extra)
    return value


class AshbyClientTests(unittest.TestCase):
    def test_registry_and_successful_parse(self):
        boards = load_ashby_registry(REGISTRY)
        self.assertEqual([board.board_name for board in boards], ["example-ashby-alpha", "example-ashby-beta", "example-ashby-gamma"])
        opener = Opener([Response({"jobs": [job("Machine Learning Intern", "Summer 2027 machine learning internship.")]})])
        jobs = AshbyClient(min_interval=0, sleeper=lambda _: None, opener=opener).fetch_board("example-ashby-alpha")
        self.assertEqual(jobs[0].work_mode, "Hybrid")
        self.assertEqual(jobs[0].secondary_locations, "Remote, US")
        self.assertIn("USD", jobs[0].compensation)
        self.assertEqual(opener.requests[0].method, "GET")
        self.assertIn("includeCompensation=true", opener.requests[0].full_url)

    def test_malformed_json_and_missing_optional_fields(self):
        class Bad(Response):
            def read(self): return b"{bad"
        with self.assertRaises(AshbyDataError):
            AshbyClient(min_interval=0, sleeper=lambda _: None, opener=Opener([Bad({})])).fetch_board("example-ashby-alpha")
        opener = Opener([Response({"jobs": [{"id": "1", "title": "Intern"}]})])
        parsed = AshbyClient(min_interval=0, sleeper=lambda _: None, opener=opener).fetch_board("example-ashby-alpha")[0]
        self.assertEqual(parsed.description, "UNKNOWN")
        self.assertEqual(parsed.compensation, "UNKNOWN")
        self.assertIsNone(parsed.is_listed)

    def test_unlisted_and_http_errors(self):
        opener = Opener([Response({"jobs": [job("Hidden", "Summer 2027 ML", isListed=False)]})])
        parsed = AshbyClient(min_interval=0, sleeper=lambda _: None, opener=opener).fetch_board("example-ashby-alpha")[0]
        self.assertFalse(parsed.is_listed)
        from urllib.error import HTTPError
        error = HTTPError("https://api.ashbyhq.com/x", 404, "not found", {}, None)
        with self.assertRaises(AshbyError):
            AshbyClient(min_interval=0, sleeper=lambda _: None, opener=Opener([error])).fetch_board("example-ashby-alpha")


class AshbyDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.db_path = Path(self.tmp.name) / "jobs.sqlite3"

    def make_job(self, title, description, employment="FullTime"):
        from internship_agent.ashby import AshbyJob
        return AshbyJob("Example Ashby Alpha", "example-ashby-alpha", title, title, "Engineering", "Robotics", "Palo Alto, CA", "UNKNOWN", "Hybrid", employment, description, f"https://jobs.ashbyhq.com/example-ashby-alpha/{title}", f"https://jobs.ashbyhq.com/example-ashby-alpha/{title}", "2025-01-01T00:00:00Z", "UNKNOWN", "Summer 2027" if "Summer 2027" in description else "UNKNOWN", "UNKNOWN", "UNKNOWN", "UNKNOWN", True, "2025-01-10T00:00:00Z")

    def fake_client(self):
        jobs = [
            self.make_job("2027 Internship Behavior ML Engineer, Learned Manipulation Policies", "Summer 2027 internship building learned manipulation policies."),
            self.make_job("Product Intern", "Summer 2027 product and business operations internship."),
            self.make_job("Machine Learning Intern", "Machine learning internship.", employment="FullTime"),
        ]
        class Client:
            def fetch_board(self, board): return jobs
        return Client()

    def test_dry_run_and_shared_classification(self):
        result = AshbyDiscovery(self.fake_client()).discover(CONFIG, REGISTRY, save=False, limit=10)
        self.assertFalse(self.db_path.exists())
        self.assertGreaterEqual(result.main_shortlist, 1)
        self.assertGreaterEqual(result.excluded, 1)

    def test_save_repeat_and_existing_jobs_preserved(self):
        with JobDatabase(self.db_path) as db:
            from internship_agent.models import Job
            existing = db.add_job(Job(title="Existing Greenhouse", company="Example Greenhouse Alpha", source="greenhouse", source_job_id="example-gh-alpha:1"))
            first = AshbyDiscovery(self.fake_client()).discover(CONFIG, REGISTRY, database=db, save=True, limit=10)
            second = AshbyDiscovery(self.fake_client()).discover(CONFIG, REGISTRY, database=db, save=True, limit=10)
            self.assertEqual(first.jobs_saved, 2)
            self.assertEqual(second.jobs_saved, 0)
            self.assertEqual(db.get_job(existing.record.id).job.title, "Existing Greenhouse")
            self.assertEqual(len(db.list_jobs()), 3)

    def test_save_all_persists_candidates_beyond_preview_limit(self):
        with JobDatabase(self.db_path) as db:
            first = AshbyDiscovery(self.fake_client()).discover(
                CONFIG, REGISTRY, database=db, save=True, limit=1, save_all=True
            )
            self.assertEqual(first.jobs_saved, 2)
            self.assertEqual(len(first.jobs), 1)
            self.assertEqual(len(db.list_jobs()), 2)

