# Public copy: synthetic identities and timestamps; no live source verification.
import json
from pathlib import Path
import tempfile
import unittest

from internship_agent.database import JobDatabase
from internship_agent.lever import (
    LeverClient,
    LeverDataError,
    LeverError,
    LeverHTTPError,
    LeverJob,
    LeverSite,
    load_lever_registry,
    site_api_url,
)
from internship_agent.lever_discovery import LeverDiscovery
from internship_agent.relevance import EXCLUDED, MAIN_SHORTLIST, NEEDS_REVIEW


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG = PROJECT_ROOT / "config" / "search_preferences.example.yaml"
REGISTRY = PROJECT_ROOT / "tests" / "fixtures" / "lever_sites.yaml"


class Response:
    def __init__(self, data, status=200):
        self.data = json.dumps(data).encode()
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


def posting(posting_id, title, description, **extra):
    value = {
        "id": posting_id, "text": title,
        "hostedUrl": f"https://jobs.lever.co/example-lever-alpha/{posting_id}",
        "applyUrl": f"https://jobs.lever.co/example-lever-alpha/{posting_id}/apply",
        "categories": {"location": "San Francisco, CA", "team": "Engineering", "department": "Engineering", "commitment": "Internship"},
        "descriptionPlain": description,
    }
    value.update(extra)
    return value


class LeverClientTests(unittest.TestCase):
    def test_registry_and_url(self):
        sites = load_lever_registry(REGISTRY)
        self.assertEqual([site.site_token for site in sites], ["example-lever-alpha", "example-lever-beta", "example-lever-gamma"])
        self.assertIn("skip=0", site_api_url("example-lever-alpha"))
        self.assertIn("limit=100", site_api_url("example-lever-alpha"))

    def test_successful_pagination_and_field_parsing(self):
        opener = Opener([
            Response([posting("1", "Simulation, Sim to Real Intern", "Summer 2027 simulation and robotics." )]),
            Response([]),
        ])
        jobs = list(LeverClient(page_limit=1, min_interval=0, sleeper=lambda _: None, opener=opener).iter_site_pages("example-lever-alpha"))
        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0][1][0].posting_id, "1")
        self.assertEqual(jobs[0][1][0].hosted_url, "https://jobs.lever.co/example-lever-alpha/1")
        self.assertEqual(len(opener.requests), 2)
        self.assertEqual(opener.requests[0].method, "GET")

    def test_missing_fields_and_malformed_json(self):
        opener = Opener([Response([{"id": "x", "text": "Intern"}]), Response([])])
        jobs = list(LeverClient(min_interval=0, sleeper=lambda _: None, opener=opener).iter_site_pages("example-lever-alpha"))[0][1]
        self.assertEqual(jobs[0].location, "UNKNOWN")
        self.assertEqual(jobs[0].apply_url, "UNKNOWN")
        class BadResponse(Response):
            def read(self): return b"{bad"
        with self.assertRaises(LeverDataError):
            list(LeverClient(min_interval=0, sleeper=lambda _: None, opener=Opener([BadResponse([])])).iter_site_pages("example-lever-alpha"))

    def test_http_error_is_reported(self):
        from urllib.error import HTTPError
        error = HTTPError(site_api_url("example-lever-alpha"), 404, "not found", {}, None)
        with self.assertRaises(LeverHTTPError):
            list(LeverClient(min_interval=0, sleeper=lambda _: None, opener=Opener([error])).iter_site_pages("example-lever-alpha"))


class LeverDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.db_path = Path(self.tmp.name) / "jobs.sqlite3"

    def make_job(self, title, description, term="UNKNOWN"):
        return LeverJob(
            company_name="Example Lever Alpha", site_token="example-lever-alpha", posting_id=title,
            title=title, location="San Francisco, CA", country="United States",
            employment_type="Internship", commitment="Internship", team="Engineering",
            department="Engineering", description=description,
            hosted_url=f"https://jobs.lever.co/example-lever-alpha/{title}",
            apply_url=f"https://jobs.lever.co/example-lever-alpha/{title}/apply",
            work_authorization="UNKNOWN", degree_requirements="UNKNOWN",
            graduation_window="UNKNOWN", internship_term=term,
            verified_at="2025-01-10T00:00:00Z",
        )

    def test_dry_run_isolated_and_classification_reuses_shared_logic(self):
        jobs = [self.make_job("Simulation Engineer Intern", "Summer 2027 simulation and robot learning internship.", "Summer 2027")]
        class FakeClient:
            def iter_site_pages(self, site):
                yield f"{site}:0", jobs
        result = LeverDiscovery(FakeClient()).discover(CONFIG, REGISTRY, limit=10, save=False)
        self.assertEqual(result.jobs_saved, 0)
        self.assertFalse(self.db_path.exists())
        self.assertEqual(result.jobs[0].relevance_category, MAIN_SHORTLIST)

    def test_save_repeat_and_greenhouse_preservation(self):
        jobs = [self.make_job("Simulation Engineer Intern", "Summer 2027 simulation and robot learning internship.", "Summer 2027")]
        class FakeClient:
            def iter_site_pages(self, site):
                yield f"{site}:0", jobs
        with JobDatabase(self.db_path) as db:
            existing = db.add_job(__import__('internship_agent.models', fromlist=['Job']).Job(title="Greenhouse Job", company="Example Greenhouse Alpha", source="greenhouse", source_job_id="example-gh-alpha:1"))
            first = LeverDiscovery(FakeClient()).discover(CONFIG, REGISTRY, database=db, save=True, limit=10)
            second = LeverDiscovery(FakeClient()).discover(CONFIG, REGISTRY, database=db, save=True, limit=10)
            self.assertEqual(first.jobs_saved, 3)
            self.assertEqual(second.jobs_saved, 3)
            self.assertEqual(db.count_jobs(), 2)
            self.assertEqual(db.get_job(existing.record.id).job.title, "Greenhouse Job")

    def test_shared_relevance_handles_senior_and_business_roles(self):
        jobs = [
            self.make_job("Senior Robotics Engineer", "Full-time senior robotics role."),
            self.make_job("Operations Intern", "Summer 2027 procurement and supply chain operations internship.", "Summer 2027"),
        ]
        class FakeClient:
            def iter_site_pages(self, site):
                yield f"{site}:0", jobs
        result = LeverDiscovery(FakeClient()).discover(CONFIG, REGISTRY, save=False, limit=10)
        self.assertEqual(result.jobs, ())

