"""Public packaging contract regressions prompted by clean-install omissions."""

from pathlib import Path
import hashlib
import re
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_complete_standard_mit_terms_and_exact_approved_notice(self):
        text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertEqual(text.splitlines()[:3], ["MIT License", "", "Copyright (c) 2026 Zhenyu Wu"])
        self.assertEqual(text.count("Copyright (c) 2026 Zhenyu Wu"), 1)
        terms = text[text.index("Permission is hereby granted, free of charge") :]
        # Standard terms independently compared with pre-existing local MIT text;
        # normalize line wrapping only, never words or license restrictions.
        digest = hashlib.sha256(" ".join(terms.split()).encode("utf-8")).hexdigest()
        self.assertEqual(digest, "fe2a9817987f862eaced948f0468c7f51d2fedfc48c5c505b246a49a3870e9a5")

    def test_license_metadata_and_readme_agree_without_relicensing_dependencies(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(project["project"]["license"], "MIT")
        self.assertEqual(project["project"]["license-files"], ["LICENSE"])
        self.assertEqual(project["build-system"]["requires"], ["setuptools>=84"])
        self.assertFalse(any(value.startswith("License ::") for value in project["project"].get("classifiers", [])))
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("[MIT License](LICENSE)", readme)
        self.assertIn("Third-party dependencies retain their", readme)
        self.assertIn("own licenses", readme)
        self.assertIn("OpenAI Codex", readme)
        self.assertIn("MIT does not grant rights", readme)

    def test_project_license_is_reviewed_and_internal_audits_stay_excluded(self):
        labels = [line.removeprefix("include ") for line in
                  (ROOT / "MANIFEST.in").read_text(encoding="utf-8").splitlines()
                  if line.startswith("include ")]
        self.assertIn("LICENSE", labels)
        self.assertNotIn("docs/LICENSE_PROVENANCE_AUDIT.md", labels)
        self.assertNotIn("docs/COMPLIANCE_REMEDIATION.md", labels)
        self.assertFalse((ROOT / "NOTICE").exists())

    def test_source_archive_allowlist_matches_reviewed_release_inventory(self):
        manifest = (ROOT / "PUBLIC_RELEASE_MANIFEST.md").read_text(encoding="utf-8")
        inventory = manifest.split("## Included file inventory", 1)[1].split("## Strict exclusions", 1)[0]
        reviewed = re.findall(r"^\| `([^`]+)` \|", inventory, re.M)
        directives = (ROOT / "MANIFEST.in").read_text(encoding="utf-8").splitlines()
        included = [line.removeprefix("include ") for line in directives if line.startswith("include ")]
        self.assertEqual(set(included), set(reviewed))
        self.assertEqual(len(included), len(set(included)))
        self.assertEqual(directives[0], "global-exclude *")
        for label in included:
            self.assertNotIn("*", label)
            self.assertNotIn("..", Path(label).parts)
            self.assertTrue((ROOT / label).is_file())

    def test_source_archive_contains_inputs_required_for_the_offline_workflow(self):
        labels = set(line.removeprefix("include ") for line in
                     (ROOT / "MANIFEST.in").read_text(encoding="utf-8").splitlines() if line.startswith("include "))
        required = {".streamlit/config.toml", "scripts/create_demo.py", "scripts/run_dashboard.py",
                    "config/search_preferences.example.yaml", "demo/fixtures/jobs.json",
                    "demo/fixtures/offline_cli_manifest.json", "tests/__init__.py",
                    "tests/fixtures/resume_paragraphs.xml", "demo/fixtures/evidence/ranking_features.json",
                    "demo/fixtures/resume_review/claims.json", "requirements/windows-py312.lock"}
        self.assertLessEqual(required, labels)

    def test_version_sensitive_streamlit_adapter_has_exact_supported_version(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        dependencies = project["project"]["dependencies"]
        self.assertIn("streamlit==1.65.0", dependencies)
        self.assertEqual(project["project"]["requires-python"], ">=3.12")
        self.assertEqual(project["project"]["scripts"]["internship-agent"], "internship_agent.cli:main")
        self.assertFalse(project["tool"]["setuptools"]["include-package-data"])
        self.assertNotIn("streamlit>=", (ROOT / "requirements.txt").read_text(encoding="utf-8"))

    def test_windows_lock_uses_exact_versions_and_reviewed_wheel_hashes(self):
        text = (ROOT / "requirements" / "windows-py312.lock").read_text(encoding="utf-8")
        entries = [line for line in text.splitlines() if line and not line.startswith("#")]
        self.assertTrue(entries)
        names = []
        for line in entries:
            self.assertRegex(line, r"^[A-Za-z0-9_.-]+==[A-Za-z0-9_.+]+ --hash=sha256:[a-f0-9]{64}$")
            names.append(line.split("==", 1)[0].lower().replace("_", "-"))
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(any(line.startswith("streamlit==1.65.0 ") for line in entries))
        self.assertTrue(any(line.startswith("setuptools==84.0.0 ") for line in entries))
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertGreater(ignore.index("!requirements/windows-py312.lock"), ignore.index("*.lock"))


if __name__ == "__main__":
    unittest.main()
