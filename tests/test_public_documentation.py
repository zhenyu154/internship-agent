"""Offline documentation/link and CI-boundary regressions; no URL requests."""

import importlib.util
import os
from pathlib import Path
import re
import unittest
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[1]


def helper():
    spec = importlib.util.spec_from_file_location("public_ci_helper", ROOT / "scripts/verify_public_demo.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PublicDocumentationTests(unittest.TestCase):
    def test_local_markdown_links_resolve_without_network_access(self):
        files = [ROOT / "README.md", ROOT / "PUBLIC_RELEASE_MANIFEST.md", *sorted((ROOT / "docs").glob("*.md"))]
        for source in files:
            # Ignore code-fence examples when checking actual Markdown links.
            text = re.sub(r"```.*?```", "", source.read_text(encoding="utf-8"), flags=re.S)
            for label in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
                parsed = urlsplit(label.strip("<>"))
                if parsed.scheme or parsed.netloc or not parsed.path:
                    continue
                target = (source.parent / unquote(parsed.path)).resolve()
                with self.subTest(file=source.relative_to(ROOT), link=label):
                    self.assertTrue(target.is_relative_to(ROOT))
                    self.assertTrue(target.is_file())

    def test_workflow_has_restricted_permissions_and_separate_network_install(self):
        raw = (ROOT / ".github/workflows/offline-tests.yml").read_text(encoding="utf-8")
        workflow = yaml.load(raw, Loader=yaml.BaseLoader)
        self.assertEqual(set(workflow["on"]), {"push", "pull_request", "workflow_dispatch"})
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        self.assertEqual(set(workflow["jobs"]), {"offline-demo"})
        job = workflow["jobs"]["offline-demo"]
        self.assertEqual(job["runs-on"], "windows-2022")
        self.assertNotIn("permissions", job)
        actions = [step for step in job["steps"] if "uses" in step]
        self.assertEqual([step["uses"] for step in actions], [
            "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683",
            "actions/setup-python@42375524e23c412d93fb67b49958b491fce71c38",
        ])
        self.assertEqual(actions[0]["with"]["persist-credentials"], "false")
        self.assertEqual(actions[1]["with"]["python-version"], "3.12")
        self.assertNotRegex(raw, r"(?i)secrets\.|upload-artifact|deploy|pull_request_target|schedule:")
        commands = [step["run"] for step in job["steps"] if "run" in step]
        index_steps = [command for command in commands if "--index-url" in command]
        self.assertEqual(len(index_steps), 1)
        self.assertIn("--require-hashes", index_steps[0])
        self.assertIn("requirements/windows-py312.lock", index_steps[0])
        self.assertTrue(any("pip" in command and " check" in command for command in commands))
        self.assertTrue(any("--no-index --no-build-isolation -r requirements.txt" in command for command in commands))
        self.assertTrue(any("scripts/verify_public_demo.py" in command for command in commands))
        self.assertTrue(all("$LASTEXITCODE" in command for command in commands))

    def test_smoke_inputs_are_individually_reviewed_synthetic_files(self):
        module = helper()
        self.assertLessEqual(set(module.SMOKE_FILES), set(module.reviewed_files()))
        self.assertEqual(len(module.SMOKE_FILES), len(set(module.SMOKE_FILES)))
        self.assertFalse(any(label.startswith(("candidate/", "resumes/", "data/", "logs/", "reports/")) for label in module.SMOKE_FILES))
        for label in module.SMOKE_FILES:
            self.assertTrue((ROOT / label).is_file())
        # A redirected inventory must be refused before its contents are read.
        with patch.object(Path, "is_symlink", return_value=True):
            with self.assertRaises(ValueError):
                module.reviewed_files()

    def test_verification_guard_rejects_network_private_reads_and_protected_writes(self):
        module = helper()
        work = ROOT / "data/ci-verification/synthetic-guard-test"
        with patch.object(module.sys, "addaudithook") as register:
            counts = module.install_test_guard(work)
        guard = register.call_args.args[0]
        events = [
            ("socket.connect", (None, ("203.0.113.1", 443))),
            ("socket.connect", (None, ("127.0.0.1", 8501))),
            ("socket.getaddrinfo", ("example.test", 443)),
            ("subprocess.Popen", ("synthetic",)),
            ("open", (str(ROOT / "candidate/synthetic.txt"), "r", 0)),
            ("open", (str(ROOT / "data/demo/demo.sqlite3"), "r", 0)),
            ("open", (str(ROOT / "README.md"), "w", os.O_WRONLY)),
        ]
        for event, args in events:
            with self.subTest(event=event), self.assertRaises(PermissionError):
                guard(event, args)
        self.assertEqual(counts["network"], 4)
        self.assertEqual(counts["external_input"], 2)
        self.assertEqual(counts["protected_write"], 1)

    def test_verification_guard_allows_only_disposable_synthetic_writes(self):
        module = helper()
        work = ROOT / "data/ci-verification/synthetic-guard-test"
        with patch.object(module.sys, "addaudithook") as register:
            counts = module.install_test_guard(work)
        guard = register.call_args.args[0]
        guard("open", (str(work / "synthetic.sqlite3"), "w", os.O_WRONLY))
        guard("sqlite3.connect", (str(work / "synthetic.sqlite3"),))
        guard("open", (str(ROOT / "demo/fixtures/jobs.json"), "r", 0))
        self.assertTrue(all(value == 0 for value in counts.values()))


if __name__ == "__main__":
    unittest.main()
