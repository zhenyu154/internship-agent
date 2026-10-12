"""Shared public synthetic input boundary for the CLI and local dashboard.

Read-only backend calls, fixed allowlisted inputs and no private-file fallback.
"""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re

from . import demo
from .database import JobDatabase

DATABASE_LABEL = "data/demo/demo.sqlite3"
MANIFEST_LABEL = "demo/fixtures/offline_cli_manifest.json"
FIXTURE_LABELS = (
    "config/search_preferences.example.yaml", "demo/fixtures/jobs.json",
    "demo/fixtures/evidence/profile.md", "demo/fixtures/evidence/experience_bank.md",
    "demo/fixtures/evidence/verification_report.md", "demo/fixtures/evidence/ranking_features.json",
    "demo/fixtures/resume_review/general_resume.txt", "demo/fixtures/resume_review/observations.md",
    "demo/fixtures/resume_review/claims.json",
)
DOCX_LIMIT = ("DOCX review supports a narrow paragraph/run subset only. Tables, inherited styles, fields, "
              "revisions, hidden text, drawings, headers/footers, comments, embeds and external relationships "
              "are unsupported; no partial flattening. This demonstration uses the synthetic TXT fixture.")


class DemoInputError(ValueError):
    """Fixed diagnostics containing no arbitrary input paths or record text."""


def reject_links(path):
    for component in (path, *path.parents):
        if component.is_symlink() or component.is_junction():
            raise DemoInputError("Redirected demo inputs are refused.")


def bounded_bytes(path):
    with path.open("rb") as stream:
        raw = stream.read(4 * 1024 * 1024 + 1)
    if len(raw) > 4 * 1024 * 1024:
        raise DemoInputError("Public demo input exceeds the bounded size.")
    return raw


class DemoServices:
    def __init__(self, public_root):
        self.root = Path(public_root)

    def public_file(self, label):
        if label not in (*FIXTURE_LABELS, MANIFEST_LABEL):
            raise DemoInputError("Only fixed reviewed public demo input labels are accepted.")
        path = self.root / label
        reject_links(path)
        if not path.is_file():
            raise DemoInputError("Required public demo input is missing. Review docs/CLI_GUIDE.md.")
        if not path.resolve().is_relative_to(self.root.resolve()):
            raise DemoInputError("Demo input escaped the public staging workspace.")
        return path

    def validate_fixtures(self):
        manifest = json.loads(bounded_bytes(self.public_file(MANIFEST_LABEL)).decode("utf-8"))
        if (not isinstance(manifest, dict) or set(manifest) != {"version", "notice", "files"}
                or type(manifest["version"]) is not int or manifest["version"] != 1
                or manifest["notice"] != demo.NOTICE or not isinstance(manifest["files"], dict)
                or set(manifest["files"]) != set(FIXTURE_LABELS)):
            raise DemoInputError("Unexpected offline fixture allowlist; reviewed synthetic inputs are required.")
        for label in FIXTURE_LABELS:
            raw = bounded_bytes(self.public_file(label))
            expected = manifest["files"][label]
            if (not isinstance(expected, str) or not re.fullmatch(r"[a-f0-9]{64}", expected)
                    or hashlib.sha256(raw).hexdigest() != expected):
                raise DemoInputError("Public demo fixture changed; review its allowlist before demonstration.")

    def database_path(self, value):
        if not isinstance(value, str):
            raise DemoInputError("Select only the established public demo database.")
        value = value.replace("\\", "/")
        if (any(part in {".", ".."} for part in value.split("/"))
                or value.startswith("//") or value.startswith("file:") or "\x00" in value):
            raise DemoInputError("Select only the established public demo database.")
        path, expected = Path(value), self.root / DATABASE_LABEL
        if path.is_absolute():
            if os.path.normcase(str(path)) != os.path.normcase(str(expected)):
                raise DemoInputError("Select only the established public demo database.")
        elif value != DATABASE_LABEL:
            raise DemoInputError("Select only the established public demo database.")
        reject_links(expected)
        for suffix in ("-wal", "-shm", "-journal"):
            if os.path.lexists(str(expected) + suffix):
                raise DemoInputError("Database sidecars are present; stop active writers and review disposable demo output.")
        for label in ("data/demo/demo.lock", "data/demo/demo.building.sqlite3"):
            if os.path.lexists(self.root / label):
                raise DemoInputError("Demo initialization/recovery is unfinished; use the existing initializer explicitly.")
        if not expected.is_file():
            raise DemoInputError("Demo database is missing. Create it explicitly with scripts/create_demo.py.")
        return expected

    @contextmanager
    def open_database(self, value):
        path = self.database_path(value)
        self.validate_fixtures()
        with JobDatabase(path, read_only=True) as database:
            validation = demo.validate_completed_demo(database)
            yield database, validation

    def ranked_jobs(self, database):
        from .candidate_evidence import load_candidate_evidence
        from .config import load_config
        from .ranking import rank_jobs
        records = database.list_jobs()
        candidate = load_candidate_evidence(self.public_file("demo/fixtures/evidence/ranking_features.json").parent,
                                           reference_prefix="demo/fixtures/evidence")
        preferences = load_config(self.public_file("config/search_preferences.example.yaml"))
        if preferences["ranking"]["weights"] != {
                "role_alignment": 30, "technical_skills_match": 30,
                "research_project_relevance": 25, "location_preference": 15}:
            raise DemoInputError("Offline demonstration requires the reviewed 30/30/25/15 weights.")
        return rank_jobs(records, candidate, preferences,
            metadata={record.id: database.get_job_metadata(record.id) for record in records},
            applications={record.job_id: record for record in database.list_applications()})

    def resume_review(self):
        from .resume_review import load_resume, load_resume_evidence, review_resume
        self.validate_fixtures()
        label = "demo/fixtures/resume_review/general_resume.txt"
        evidence = load_resume_evidence(
            candidate_directory=self.public_file("demo/fixtures/evidence/ranking_features.json").parent,
            claims_path=self.public_file("demo/fixtures/resume_review/claims.json"),
            sources={"observations.md": self.public_file("demo/fixtures/resume_review/observations.md")},
            candidate_reference_prefix="demo/fixtures/evidence", source_reference_prefix="demo/fixtures/resume_review")
        document = load_resume(self.public_file(label), source_label=label)
        proposal = review_resume(document, evidence)
        if not proposal.supported_document:
            raise DemoInputError("Synthetic resume input is unsupported; no partial review or changes performed.")
        return document, proposal
