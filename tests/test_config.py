# Public copy: synthetic identities and timestamps; no live source verification.
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from internship_agent.config import ConfigurationError, load_config


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_CONFIG = PROJECT_ROOT / "config" / "search_preferences.example.yaml"


class ConfigLoaderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.valid_text = EXAMPLE_CONFIG.read_text(encoding="utf-8")

    def write_config(self, text=None):
        path = self.root / "search_preferences.yaml"
        path.write_text(self.valid_text if text is None else text, encoding="utf-8")
        return path

    def test_valid_configuration_loads_without_modifying_source(self):
        path = self.write_config()
        before = path.read_bytes()
        config = load_config(path)
        self.assertEqual(config["version"], 1)
        self.assertEqual(config["execution"]["mode"], "manual")
        self.assertEqual(sum(config["ranking"]["weights"].values()), 100)
        self.assertEqual(path.read_bytes(), before)

    def test_missing_configuration_file(self):
        with self.assertRaisesRegex(ConfigurationError, "not found"):
            load_config(self.root / "missing.yaml")

    def test_invalid_yaml_syntax(self):
        with self.assertRaisesRegex(ConfigurationError, "Invalid YAML"):
            load_config(self.write_config("version: [\n"))

    def test_duplicate_yaml_keys_are_rejected(self):
        with self.assertRaisesRegex(ConfigurationError, "Duplicate configuration key"):
            load_config(self.write_config("version: 1\nversion: 1\n"))

    def test_missing_required_fields_are_rejected(self):
        with self.assertRaisesRegex(ConfigurationError, "Missing required"):
            load_config(self.write_config("version: 1\n"))

    def test_incorrect_data_types_are_rejected(self):
        text = self.valid_text.replace("version: 1", 'version: "1"', 1)
        with self.assertRaisesRegex(ConfigurationError, "version must be"):
            load_config(self.write_config(text))

    def test_unknown_configuration_fields_are_rejected(self):
        text = self.valid_text + "\nunexpected_field: true\n"
        with self.assertRaisesRegex(ConfigurationError, "Unknown configuration field"):
            load_config(self.write_config(text))

    def test_unknown_nested_fields_are_rejected(self):
        text = self.valid_text.replace(
            'mode: "manual"', 'mode: "manual"\n  unexpected: false', 1
        )
        with self.assertRaisesRegex(ConfigurationError, "Unknown configuration field"):
            load_config(self.write_config(text))

    def test_ranking_weights_must_sum_to_100(self):
        text = self.valid_text.replace("location_preference: 15", "location_preference: 14", 1)
        with self.assertRaisesRegex(ConfigurationError, "sum to exactly 100"):
            load_config(self.write_config(text))

    def test_ranking_weights_must_be_non_negative_integers(self):
        text = self.valid_text.replace("role_alignment: 30", "role_alignment: -1", 1)
        with self.assertRaisesRegex(ConfigurationError, "non-negative integer"):
            load_config(self.write_config(text))

    def test_scheduled_tasks_must_be_disabled(self):
        text = self.valid_text.replace("scheduler_enabled: false", "scheduler_enabled: true", 1)
        with self.assertRaisesRegex(ConfigurationError, "scheduler_enabled"):
            load_config(self.write_config(text))

    def test_auto_submit_must_be_disabled(self):
        text = self.valid_text.replace("auto_submit: false", "auto_submit: true", 1)
        with self.assertRaisesRegex(ConfigurationError, "auto_submit"):
            load_config(self.write_config(text))

    def test_human_approval_must_be_enabled(self):
        text = self.valid_text.replace("human_review_required: true", "human_review_required: false", 1)
        with self.assertRaisesRegex(ConfigurationError, "human_review_required"):
            load_config(self.write_config(text))

    def test_discovery_limits_must_be_positive(self):
        text = self.valid_text.replace("max_candidates_per_run: 40", "max_candidates_per_run: 0", 1)
        with self.assertRaisesRegex(ConfigurationError, "max_candidates_per_run"):
            load_config(self.write_config(text))
        text = self.valid_text.replace("reverify_existing_jobs_after_days: 7", "reverify_existing_jobs_after_days: -1", 1)
        with self.assertRaisesRegex(ConfigurationError, "reverify_existing_jobs_after_days"):
            load_config(self.write_config(text))

    def test_safety_enums_and_unknown_work_authorization_are_enforced(self):
        text = self.valid_text.replace('mode: "manual"', 'mode: "automatic"', 1)
        with self.assertRaisesRegex(ConfigurationError, "execution.mode"):
            load_config(self.write_config(text))
        text = self.valid_text.replace(
            'candidate_work_authorization: "UNKNOWN"',
            'candidate_work_authorization: "AUTHORIZED"',
            1,
        )
        with self.assertRaisesRegex(ConfigurationError, "candidate_work_authorization"):
            load_config(self.write_config(text))
        text = self.valid_text.replace(
            'explicit_no_sponsorship: "NEEDS_REVIEW"',
            'explicit_no_sponsorship: "EXCLUDE"',
            1,
        )
        with self.assertRaisesRegex(ConfigurationError, "explicit_no_sponsorship"):
            load_config(self.write_config(text))



