"""Offline service/UI regressions; authored fixtures and temporary databases only."""

from contextlib import closing
from dataclasses import replace
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from internship_agent import demo
from internship_agent.dashboard_launch import SAFE_OPTIONS, configure_streamlit, disable_config_polling, offline_audit_guard
from internship_agent.dashboard_services import filter_jobs, job_rows, load_snapshot
from internship_agent.demo_services import DATABASE_LABEL, DemoServices
from internship_agent.database import JobDatabase

PUBLIC_ROOT = demo.PUBLIC_ROOT
APP = PUBLIC_ROOT / "src" / "internship_agent" / "dashboard_app.py"


class DashboardTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        fixtures = self.root / "demo" / "fixtures"
        shutil.copytree(PUBLIC_ROOT / "demo" / "fixtures", fixtures)
        config = self.root / "config" / "search_preferences.example.yaml"
        config.parent.mkdir()
        shutil.copyfile(PUBLIC_ROOT / "config" / "search_preferences.example.yaml", config)
        self.patch = patch.multiple(demo, PUBLIC_ROOT=self.root, FIXTURE_DIRECTORY=fixtures,
            PREFERENCES=config, OUTPUT_ROOT=self.root, OUTPUT_DIRECTORY=self.root / "data" / "demo")
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.result = demo.create_demo()
        self.path = self.result.path

    def snapshot(self):
        return load_snapshot(database_label=DATABASE_LABEL, public_root=self.root)

    def file_state(self):
        return {path.relative_to(self.root).as_posix(): path.read_bytes()
                for path in self.root.rglob("*") if path.is_file()}

    def app(self):
        # Native Streamlit AppTest executes the presentation without a server.
        configure_streamlit(public_root=PUBLIC_ROOT)
        from streamlit.testing.v1 import AppTest
        return AppTest.from_file(str(APP), default_timeout=20).run()

    def test_snapshot_contains_validated_ten_jobs_and_four_records(self):
        snapshot = self.snapshot()
        self.assertEqual((len(snapshot.jobs), len(snapshot.applications)), (10, 4))
        self.assertEqual(snapshot.validation["integrity_check"], "ok")
        self.assertEqual(snapshot.validation["foreign_key_violations"], 0)
        self.assertEqual(snapshot.validation["schema_version"], 6)
        self.assertEqual(snapshot.validation["fixture_fingerprint"], self.result.fixture_fingerprint)

    def test_all_scores_and_backend_sort_order_are_unchanged(self):
        snapshot = self.snapshot()
        self.assertEqual([result.technical_match_score for result in snapshot.rankings],
                         [91, 88, 75, 72.67, 66, 63.5, 55, 36, 12, 6])
        self.assertEqual([row["ID"] for row in job_rows(snapshot)],
                         ["demo-001", "demo-004", "demo-003", "demo-002", "demo-008", "demo-006",
                          "demo-005", "demo-007", "demo-010", "demo-009"])

    def test_eligibility_and_preparation_status_are_separate_from_scores(self):
        rows = job_rows(self.snapshot())
        self.assertEqual(next(row for row in rows if row["ID"] == "demo-008")["Eligibility"], "POLICY_EXCLUDED")
        self.assertEqual(next(row for row in rows if row["ID"] == "demo-006")["Eligibility"], "UNKNOWN")
        self.assertEqual(next(row for row in rows if row["ID"] == "demo-002")["Preparation"], "PREPARING")
        self.assertTrue(all(row["Job Match Score"] > 0 for row in rows))

    def test_ui_filters_never_change_records_or_scores(self):
        rows = job_rows(self.snapshot())
        original = [dict(row) for row in rows]
        filtered = filter_jobs(rows, search="simulation", relevance=("EXCLUDED",), eligibility=("POLICY_EXCLUDED",))
        self.assertEqual([row["ID"] for row in filtered], ["demo-008"])
        self.assertEqual(rows, original)

    def test_ui_sort_options_do_not_recalculate_match_scores(self):
        rows = job_rows(self.snapshot())
        for sort in ("Company: A to Z", "Position: A to Z", "Score: low to high", "Score: high to low"):
            with self.subTest(sort=sort):
                ordered = filter_jobs(rows, sort=sort)
                self.assertEqual({row["ID"]: row["Job Match Score"] for row in ordered},
                                 {row["ID"]: row["Job Match Score"] for row in rows})
        self.assertEqual(filter_jobs(rows, sort="Score: low to high")[0]["Job Match Score"], 6)
        with self.assertRaises(ValueError): filter_jobs(rows, sort="Unknown presentation sort")

    def test_application_associations_and_history_are_preserved(self):
        snapshot = self.snapshot()
        self.assertEqual({record.status for record in snapshot.applications},
                         {"NOT_STARTED", "RESEARCHING", "PREPARING", "READY_TO_APPLY"})
        self.assertEqual(sum(len(events) for events in snapshot.history.values()), 7)
        self.assertTrue(all(record.submitted_at is None for record in snapshot.applications))
        self.assertTrue(all(event.new_status != "APPLIED" for events in snapshot.history.values() for event in events))

    def test_resume_snapshot_has_the_unchanged_five_exact_proposals(self):
        snapshot = self.snapshot()
        self.assertEqual(len(snapshot.proposal.changes), 5)
        self.assertEqual(snapshot.proposal.proposal_fingerprint,
                         "a3f9fc4ef400028115be11cc90d54412968efb775e827c80af23be93bf242c83")
        pending = next(change for change in snapshot.proposal.changes if change.claim_id == "publication_pending")
        self.assertEqual(pending.evidence_status, "PENDING")
        self.assertIn("pending; no acceptance evidence", pending.after)

    def test_loading_snapshots_never_modifies_any_demo_file(self):
        before = self.file_state()
        self.snapshot()
        self.snapshot()
        self.assertEqual(self.file_state(), before)

    def test_database_connections_are_read_only(self):
        original = JobDatabase.__init__
        def guarded(database, path, *, read_only=False):
            self.assertTrue(read_only)
            return original(database, path, read_only=read_only)
        with patch.object(JobDatabase, "__init__", guarded): self.snapshot()

    def test_snapshot_has_no_submission_resume_edit_or_initialization_calls(self):
        with (patch.object(JobDatabase, "create_application", side_effect=AssertionError("Application creation")),
              patch.object(JobDatabase, "set_application_status", side_effect=AssertionError("Status write")),
              patch.object(JobDatabase, "mark_application_submitted", side_effect=AssertionError("Submission")),
              patch.object(demo, "create_demo", side_effect=AssertionError("Silent init"))):
            self.snapshot()
        self.assertEqual(list(self.root.rglob("*.docx")), [])
        self.assertEqual(list(self.root.rglob("*.pdf")), [])

    def test_offline_services_have_no_socket_dns_or_http_requests(self):
        with (patch("socket.create_connection", side_effect=AssertionError("Socket")),
              patch("socket.getaddrinfo", side_effect=AssertionError("DNS")),
              patch("urllib.request.urlopen", side_effect=AssertionError("HTTP"))):
            self.snapshot()

    def test_unsafe_database_selection_is_rejected_before_access(self):
        with patch("sqlite3.connect", side_effect=AssertionError("Unsafe database read")):
            with self.assertRaises(ValueError):
                load_snapshot(database_label="../unrelated.sqlite3", public_root=self.root)

    def test_missing_database_never_gets_initialized(self):
        self.path.unlink()
        with self.assertRaises(ValueError): self.snapshot()
        self.assertFalse(self.path.exists())

    def test_corrupt_database_is_preserved_without_a_partial_snapshot(self):
        self.path.write_bytes(b"Synthetic corrupt database sentinel")
        before = self.path.read_bytes()
        with self.assertRaises(sqlite3.DatabaseError): self.snapshot()
        self.assertEqual(self.path.read_bytes(), before)

    def test_unexpected_database_is_rejected_with_byte_preservation(self):
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("CREATE TABLE unrelated_records (value TEXT)")
        before = self.path.read_bytes()
        with self.assertRaises(sqlite3.DatabaseError): self.snapshot()
        self.assertEqual(self.path.read_bytes(), before)

    def test_modified_notes_are_refused_and_never_displayed(self):
        with JobDatabase(self.path) as database:
            database.add_application_note(1, "Synthetic unrelated private-note sentinel")
        before = self.path.read_bytes()
        with self.assertRaises(ValueError): self.snapshot()
        self.assertEqual(self.path.read_bytes(), before)

    def test_missing_fixture_never_uses_other_evidence(self):
        (self.root / "demo" / "fixtures" / "evidence" / "profile.md").unlink()
        with self.assertRaises(ValueError): self.snapshot()

    def test_only_allowlisted_named_input_files_are_read(self):
        from internship_agent.demo_services import FIXTURE_LABELS, MANIFEST_LABEL
        allowed = {self.root / label for label in (*FIXTURE_LABELS, MANIFEST_LABEL)}
        original = Path.open
        def guarded(path, *args, **kwargs):
            self.assertIn(path, allowed)
            return original(path, *args, **kwargs)
        with patch.object(Path, "open", guarded): self.snapshot()

    def test_every_page_has_the_visible_synthetic_banner(self):
        app = self.app()
        for name in ("Overview", "Demo Jobs", "Application Tracker", "General Resume"):
            app.sidebar.radio[0].set_value(name).run()
            self.assertEqual(len(app.exception), 0)
            self.assertTrue(any(item.value == demo.NOTICE for item in app.info))

    def test_overview_metrics_come_from_validated_snapshot(self):
        app = self.app()
        values = {metric.label: metric.value for metric in app.metric}
        self.assertEqual(values["Fictional opportunities"], "10")
        self.assertEqual(values["Preparation records"], "4")
        self.assertEqual(values["Proposed resume changes"], "5")
        self.assertEqual(values["Database integrity"], "OK")

    def test_jobs_table_has_scores_eligibility_search_sort_and_full_details(self):
        app = self.app()
        app.sidebar.radio[0].set_value("Demo Jobs").run()
        table = app.dataframe[0].value
        self.assertEqual(len(table), 10)
        self.assertIn("Eligibility", table.columns)
        self.assertIn("Job Match Score", table.columns)
        app.selectbox(key="selected_job").set_value("demo-002").run()
        self.assertTrue(any(item.value == "Machine Learning Intern — Summer 2027" for item in app.subheader))
        self.assertTrue(any("UNKNOWN" in item.value for item in app.warning))
        self.assertEqual([metric.value for metric in app.metric], ["24.00 / 30", "20.00 / 30", "16.67 / 25", "12.00 / 15"])
        app.text_input(key="job_search").set_value("Perception").run()
        self.assertEqual(len(app.dataframe[0].value), 1)

    def test_jobs_policy_exclusion_and_sparse_warnings_are_displayed(self):
        app = self.app()
        app.sidebar.radio[0].set_value("Demo Jobs").run()
        app.selectbox(key="selected_job").set_value("demo-007").run()
        self.assertTrue(any("POLICY_EXCLUDED" in item.value for item in app.warning))
        self.assertTrue(any("Sparse job evidence" in item.value for item in app.warning))

    def test_tracker_page_displays_existing_history_with_no_write_controls(self):
        app = self.app()
        app.sidebar.radio[0].set_value("Application Tracker").run()
        self.assertEqual(len(app.dataframe[0].value), 4)
        self.assertEqual(len(app.dataframe[1].value), 2)
        self.assertEqual(len(app.button), 0)
        self.assertTrue(any("No application has been submitted" in item.value for item in app.info))

    def test_resume_page_displays_exact_proposals_and_advanced_fingerprint(self):
        snapshot = self.snapshot()
        app = self.app()
        app.sidebar.radio[0].set_value("General Resume").run()
        strings = [code.value for code in app.code]
        for change in snapshot.proposal.changes:
            self.assertIn(change.after, strings)
            if change.before: self.assertIn(change.before, strings)
        self.assertTrue(any(snapshot.proposal.proposal_fingerprint in item.value for item in app.text))
        self.assertTrue(any("Apply is unavailable" in item.value for item in app.info))
        self.assertEqual(len(app.button), 0)

    def test_page_rendering_and_widget_changes_are_read_only(self):
        before = self.file_state()
        app = self.app()
        for page in ("Demo Jobs", "Application Tracker", "General Resume", "Overview"):
            app.sidebar.radio[0].set_value(page).run()
            self.assertEqual(len(app.exception), 0)
        self.assertEqual(self.file_state(), before)

    def test_missing_database_ui_has_manual_initialization_instructions(self):
        self.path.unlink()
        app = self.app()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(app.error)
        self.assertTrue(any("scripts/create_demo.py" in code.value for code in app.code))
        self.assertFalse(self.path.exists())

    def test_corrupt_database_ui_exposes_no_record_or_exception_text(self):
        self.path.write_bytes(b"Synthetic private-record sentinel")
        app = self.app()
        self.assertTrue(app.error)
        self.assertNotIn("private-record sentinel", " ".join(item.value for item in app.error))
        self.assertEqual(len(app.metric), 0)

    def test_launch_configuration_is_loopback_manual_and_without_telemetry(self):
        config = tomllib.loads((PUBLIC_ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
        self.assertEqual(config["server"]["address"], "127.0.0.1")
        self.assertFalse(config["browser"]["gatherUsageStats"])
        self.assertEqual(config["server"]["fileWatcherType"], "none")
        self.assertFalse(config["server"]["runOnSave"])
        self.assertTrue(config["server"]["headless"])
        self.assertEqual(SAFE_OPTIONS["secrets.files"], [])

    def test_streamlit_configuration_uses_only_workspace_file_and_no_secrets(self):
        configure_streamlit(public_root=PUBLIC_ROOT, theme="dark")
        from streamlit import config
        self.assertEqual(config.get_config_files("config.toml"), [str(PUBLIC_ROOT / ".streamlit" / "config.toml")])
        self.assertEqual(config.get_config_files("secrets.toml"), [])
        self.assertEqual(config.get_option("server.address"), "127.0.0.1")
        self.assertEqual(config.get_option("theme.base"), "dark")
        with self.assertRaises(ValueError): configure_streamlit(public_root=PUBLIC_ROOT, theme="https://example.test/theme")

    def test_separate_streamlit_config_polling_hook_is_disabled(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        watcher = Mock(side_effect=AssertionError("Configuration polling started"))
        bootstrap = SimpleNamespace(_install_config_watchers=watcher)
        disable_config_polling(bootstrap)
        bootstrap._install_config_watchers({})
        watcher.assert_not_called()
        with self.assertRaises(RuntimeError): disable_config_polling(SimpleNamespace())

    def test_launch_guard_refuses_public_binding_and_external_network(self):
        guard, attempts = offline_audit_guard(self.root, sys.base_prefix)
        for event, args in (("socket.bind", (None, ("0.0.0.0", 8501))),
                            ("socket.connect", (None, ("203.0.113.1", 443))),
                            ("socket.getaddrinfo", ("jobs.example.test", 443)),
                            ("subprocess.Popen", ("synthetic-process",))):
            with self.subTest(event=event), self.assertRaises(PermissionError): guard(event, args)
        self.assertEqual(attempts["external_network"], 4)
        guard("socket.bind", (None, ("127.0.0.1", 8501)))
        guard("socket.connect", (None, ("127.0.0.1", 8501)))

    def test_launch_guard_refuses_private_reads_and_persistent_writes(self):
        guard, attempts = offline_audit_guard(self.root, sys.base_prefix)
        with self.assertRaises(PermissionError): guard("open", (str(self.root / "private" / "synthetic.txt"), "r", 0))
        with self.assertRaises(PermissionError): guard("open", (str(self.path), "w", 0))
        with self.assertRaises(PermissionError): guard("sqlite3.connect", (str(self.path),))
        self.assertEqual(attempts["external_input"], 1)
        self.assertEqual(attempts["filesystem_write"], 2)

    def test_no_dashboard_control_submits_approves_edits_or_schedules(self):
        app = self.app()
        for page in ("Overview", "Demo Jobs", "Application Tracker", "General Resume"):
            app.sidebar.radio[0].set_value(page).run()
            self.assertEqual(len(app.button), 0)
            self.assertEqual(len(app.file_uploader), 0)
            self.assertTrue(all(frame.proto.editing_mode == 0 for frame in app.dataframe))


if __name__ == "__main__":
    unittest.main()
