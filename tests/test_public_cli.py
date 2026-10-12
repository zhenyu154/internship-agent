"""Authored offline CLI integrations: synthetic fixtures and temporary SQLite."""

from contextlib import closing, redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import runpy
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from internship_agent import cli, demo
from internship_agent.database import JobDatabase
from internship_agent.resume_review import load_resume, load_resume_evidence, render_proposal, review_resume

PUBLIC_ROOT = demo.PUBLIC_ROOT


class PublicCLITests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.fixtures = self.root / "demo" / "fixtures"
        shutil.copytree(PUBLIC_ROOT / "demo" / "fixtures", self.fixtures)
        config = self.root / "config" / "search_preferences.example.yaml"
        config.parent.mkdir()
        shutil.copyfile(PUBLIC_ROOT / "config" / "search_preferences.example.yaml", config)
        self.patch = patch.multiple(demo, PUBLIC_ROOT=self.root, FIXTURE_DIRECTORY=self.fixtures,
            PREFERENCES=config, OUTPUT_ROOT=self.root, OUTPUT_DIRECTORY=self.root / "data" / "demo")
        self.patch.start()
        self.addCleanup(self.patch.stop)
        root_patch = patch.object(cli, "PUBLIC_ROOT", self.root)
        root_patch.start()
        self.addCleanup(root_patch.stop)
        self.result = demo.create_demo()
        self.database = self.result.path

    def command(self, *arguments):
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(list(arguments))
        return code, out.getvalue(), err.getvalue()

    def db_command(self, name, *arguments):
        return self.command(name, "--database", cli.DATABASE_LABEL, *arguments)

    def snapshot(self):
        return {path.relative_to(self.root).as_posix(): path.read_bytes()
                for path in self.root.rglob("*") if path.is_file()}

    def test_root_help_has_exactly_the_five_offline_commands(self):
        code, out, err = self.command("--help")
        self.assertEqual((code, err), (0, ""))
        for name in ("demo-status", "demo-jobs", "demo-applications", "demo-rank", "demo-resume-review"):
            self.assertIn(name, out)
        self.assertIn(demo.NOTICE, out)
        self.assertIn("Resume Apply is unavailable", out)

    def test_command_help_never_loads_fixtures_or_opens_sqlite(self):
        with (patch.object(cli, "_fixtures", side_effect=AssertionError("Fixture access")),
              patch("sqlite3.connect", side_effect=AssertionError("Database access"))):
            for name in ("demo-status", "demo-jobs", "demo-applications", "demo-rank", "demo-resume-review"):
                with self.subTest(name=name):
                    self.assertEqual(self.command(name, "--help")[0], 0)

    def test_no_command_missing_arguments_and_unknown_options_exit_two(self):
        for arguments in ((), ("missing-command",), ("demo-status",),
                          ("demo-rank", "--database"), ("demo-jobs", "--database", cli.DATABASE_LABEL, "--save"),
                          ("demo-resume-review", "--resume", "private-sentinel.txt"),
                          ("demo-status", "--dat", cli.DATABASE_LABEL)):
            with self.subTest(arguments=arguments):
                code, out, err = self.command(*arguments)
                self.assertEqual((code, out), (2, ""))
                self.assertIn("Invalid command or arguments", err)
                self.assertNotIn("private-sentinel", err)

    def test_unsafe_database_selections_fail_before_sqlite_access(self):
        values = ("../private.sqlite3", "data/demo/../demo/demo.sqlite3", "data/jobs.sqlite3",
                  "file:data/demo/demo.sqlite3?mode=rw", "https://example.test/demo.sqlite3",
                  "//example.test/share/demo.sqlite3", "data/demo/demo.sqlite3:stream",
                  str(self.root / "unrelated.sqlite3"), "data/demo/demo.building.sqlite3")
        with patch("sqlite3.connect", side_effect=AssertionError("Unsafe database opened")):
            for value in values:
                with self.subTest(value=value):
                    code, out, err = self.command("demo-status", "--database", value)
                    self.assertEqual((code, out), (1, ""))
                    self.assertIn("established public demo", err)

    def test_relative_backslash_and_exact_absolute_database_are_accepted(self):
        for value in (cli.DATABASE_LABEL, cli.DATABASE_LABEL.replace("/", "\\"), str(self.database)):
            with self.subTest(value=value):
                self.assertEqual(self.command("demo-status", "--database", value)[0], 0)

    def test_selected_demo_path_is_staging_relative_not_current_directory(self):
        with patch("pathlib.Path.cwd", side_effect=AssertionError("Unexpected current-directory lookup")):
            code, out, err = self.db_command("demo-status")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("Selected database: data/demo/demo.sqlite3", out)

    def test_demo_status_reports_counts_run_integrity_and_fingerprint(self):
        code, out, err = self.db_command("demo-status")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("Demo run: COMPLETED", out)
        self.assertIn("Synthetic jobs: 10; preparation records: 4", out)
        self.assertIn("SQLite integrity: ok; foreign-key violations: 0; schema version: 6", out)
        self.assertIn(self.result.fixture_fingerprint, out)

    def test_jobs_list_all_ten_synthetic_postings_with_classifications(self):
        code, out, err = self.db_command("demo-jobs")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("Synthetic jobs: 10", out)
        self.assertEqual(sum(line.startswith("demo-") for line in out.splitlines()), 10)
        for entry in demo.load_demo_fixtures()[0]:
            self.assertIn(entry.job.source_job_id, out)
            self.assertIn(entry.job.url, out)
            self.assertIn(entry.job.company, out)
        self.assertIn("relevance: EXCLUDED", out)

    def test_application_list_has_only_four_preparation_records_without_notes(self):
        code, out, err = self.db_command("demo-applications")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("Synthetic preparation records: 4", out)
        self.assertEqual(sum(line.startswith("demo-") for line in out.splitlines()), 4)
        for status in ("NOT_STARTED", "RESEARCHING", "PREPARING", "READY_TO_APPLY"):
            self.assertIn(status, out)
        self.assertIn("Notes and receipts are omitted", out)
        self.assertNotIn("Illustrative research note", out)
        self.assertNotIn("APPLIED", out)

    def test_rank_preserves_all_ten_scores_and_deterministic_order(self):
        code, out, err = self.db_command("demo-rank")
        self.assertEqual((code, err), (0, ""))
        rows = [line for line in out.splitlines() if line.startswith("demo-")]
        self.assertEqual([line.split(" | ")[0] for line in rows],
                         ["demo-001", "demo-004", "demo-003", "demo-002", "demo-008", "demo-006",
                          "demo-005", "demo-007", "demo-010", "demo-009"])
        self.assertEqual([line.rsplit("score: ", 1)[1] for line in rows],
                         ["91.00/100", "88.00/100", "75.00/100", "72.67/100", "66.00/100",
                          "63.50/100", "55.00/100", "36.00/100", "12.00/100", "6.00/100"])

    def test_rank_one_job_displays_existing_components_and_evidence(self):
        code, out, err = self.db_command("demo-rank", "--job", "demo-002")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("score: 72.67/100", out)
        for component in ("Role alignment: 24.00/30", "Technical skills: 20.00/30",
                          "Project relevance: 16.67/25", "Location preference: 12.00/15"):
            self.assertIn(component, out)
        self.assertIn("demo_shape_classifier", out)
        self.assertIn("demo/fixtures/evidence/verification_report.md:", out)
        self.assertIn("job:2:description:duties:", out)
        self.assertIn("config:ranking:weights:", out)
        self.assertIn("[CONFIRMED]", out)
        self.assertIn("[INFERRED]", out)
        self.assertEqual(sum(line.startswith("demo-") for line in out.splitlines()), 1)

    def test_rank_unknown_policy_excluded_and_sparse_limitations_are_separate(self):
        out = self.db_command("demo-rank")[1]
        self.assertIn("Eligibility: UNKNOWN", out)
        self.assertIn("Eligibility: POLICY_EXCLUDED", out)
        self.assertIn("UNKNOWN requires review and is not automatic ineligibility", out)
        self.assertIn("Sparse job evidence", out)
        self.assertIn("not admission probabilities", out)
        self.assertIn("application: PREPARING", out)
        self.assertNotIn("Illustrative preparation note", out)

    def test_missing_job_returns_nonzero_without_partial_rank_output(self):
        code, out, err = self.db_command("demo-rank", "--job", "unlisted-synthetic-id")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("fictional job was not found", err)

    def test_cli_checks_demo_weights_without_changing_backend_calculations(self):
        from internship_agent.config import load_config
        preferences = load_config(demo.PREFERENCES)
        preferences["ranking"]["weights"].update(role_alignment=40, technical_skills_match=20)
        with patch("internship_agent.config.load_config", return_value=preferences):
            code, out, err = self.db_command("demo-rank")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("reviewed 30/30/25/15 weights", err)

    def test_resume_review_uses_backend_output_and_identical_proposal(self):
        base = self.fixtures / "resume_review"
        evidence = load_resume_evidence(candidate_directory=self.fixtures / "evidence", claims_path=base / "claims.json",
            sources={"observations.md": base / "observations.md"}, candidate_reference_prefix="demo/fixtures/evidence",
            source_reference_prefix="demo/fixtures/resume_review")
        proposal = review_resume(load_resume(base / "general_resume.txt",
                                source_label="demo/fixtures/resume_review/general_resume.txt"), evidence)
        code, out, err = self.command("demo-resume-review")
        self.assertEqual((code, err), (0, ""))
        self.assertIn(render_proposal(proposal), out)
        self.assertIn("a3f9fc4ef400028115be11cc90d54412968efb775e827c80af23be93bf242c83", out)
        for change in proposal.changes:
            self.assertIn(change.change_id, out)
            self.assertIn(json.dumps(change.before, ensure_ascii=False), out)
            self.assertIn(json.dumps(change.after, ensure_ascii=False), out)
        self.assertIn("Evidence status: PENDING", out)
        self.assertIn("uncertainties", out)

    def test_resume_review_reports_narrow_docx_support_and_apply_unavailable(self):
        out = self.command("demo-resume-review")[1]
        self.assertIn("DOCX review supports a narrow paragraph/run subset only", out)
        self.assertIn("no partial flattening", out)
        self.assertIn("Resume Apply is unavailable", out)
        self.assertIn("Human review is required", out)

    def test_resume_review_never_needs_a_database(self):
        self.database.unlink()
        with patch("sqlite3.connect", side_effect=AssertionError("Resume command opened SQLite")):
            self.assertEqual(self.command("demo-resume-review")[0], 0)
        self.assertFalse(self.database.exists())

    def test_read_only_operations_leave_the_whole_demo_tree_unchanged(self):
        before = self.snapshot()
        for name in ("demo-status", "demo-jobs", "demo-applications", "demo-rank"):
            self.assertEqual(self.db_command(name)[0], 0)
        self.assertEqual(self.command("demo-resume-review")[0], 0)
        self.assertEqual(self.snapshot(), before)

    def test_database_is_always_opened_read_only(self):
        original = JobDatabase.__init__
        def guarded(database, path, *, read_only=False):
            self.assertTrue(read_only)
            self.assertEqual(Path(path), self.database)
            return original(database, path, read_only=read_only)
        with patch.object(JobDatabase, "__init__", guarded):
            for name in ("demo-status", "demo-jobs", "demo-applications", "demo-rank"):
                self.assertEqual(self.db_command(name)[0], 0)

    def test_no_application_writes_submission_or_resume_generation(self):
        with (patch.object(JobDatabase, "create_application", side_effect=AssertionError("Application creation")),
              patch.object(JobDatabase, "set_application_status", side_effect=AssertionError("Status mutation")),
              patch.object(JobDatabase, "mark_application_submitted", side_effect=AssertionError("Submission")),
              patch.object(demo, "create_demo", side_effect=AssertionError("Implicit initialization"))):
            for name in ("demo-status", "demo-jobs", "demo-applications", "demo-rank"):
                self.assertEqual(self.db_command(name)[0], 0)
            self.assertEqual(self.command("demo-resume-review")[0], 0)
        self.assertEqual(list(self.root.rglob("*.docx")), [])
        self.assertEqual(list(self.root.rglob("*.pdf")), [])

    def test_offline_cli_never_accesses_dns_http_or_sockets(self):
        with (patch("socket.create_connection", side_effect=AssertionError("Network")),
              patch("socket.getaddrinfo", side_effect=AssertionError("DNS")),
              patch("urllib.request.urlopen", side_effect=AssertionError("HTTP"))):
            for name in ("demo-status", "demo-jobs", "demo-applications", "demo-rank"):
                self.assertEqual(self.db_command(name)[0], 0)
            self.assertEqual(self.command("demo-resume-review")[0], 0)

    def test_file_reads_are_only_fixed_allowlisted_public_inputs(self):
        allowed = {self.root / label for label in (*cli.FIXTURE_LABELS, cli.MANIFEST_LABEL)}
        original = Path.open
        observed = set()
        def guarded(path, *args, **kwargs):
            self.assertIn(path, allowed)
            observed.add(path)
            mode = args[0] if args else kwargs.get("mode", "r")
            self.assertIn(mode, ("r", "rb"))
            return original(path, *args, **kwargs)
        with patch.object(Path, "open", guarded):
            self.assertEqual(self.db_command("demo-rank")[0], 0)
            self.assertEqual(self.command("demo-resume-review")[0], 0)
        self.assertEqual(observed, allowed)

    def test_missing_database_refuses_without_creating_it(self):
        self.database.unlink()
        before = self.snapshot()
        code, out, err = self.db_command("demo-status")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("Create it explicitly", err)
        self.assertEqual(self.snapshot(), before)

    def test_corrupt_database_returns_nonzero_and_preserves_bytes(self):
        self.database.write_bytes(b"Synthetic corrupt SQLite sentinel")
        before = self.database.read_bytes()
        code, out, err = self.db_command("demo-jobs")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("corrupt or incompatible", err)
        self.assertEqual(self.database.read_bytes(), before)

    def test_unrelated_database_is_refused_with_no_record_leak(self):
        self.database.unlink()
        with JobDatabase(self.database) as database:
            pass
        before = self.database.read_bytes()
        code, out, err = self.db_command("demo-applications")
        self.assertEqual((code, out), (1, ""))
        self.assertEqual(self.database.read_bytes(), before)
        self.assertIn("corrupt or incompatible", err)

    def test_extra_schema_cannot_execute_unrelated_triggers_or_leak_records(self):
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("CREATE TABLE unrelated (value TEXT)")
            connection.execute("INSERT INTO unrelated VALUES ('Synthetic private-record sentinel')")
        before = self.database.read_bytes()
        code, out, err = self.db_command("demo-status")
        self.assertEqual((code, out), (1, ""))
        self.assertNotIn("private-record sentinel", err)
        self.assertEqual(self.database.read_bytes(), before)

    def test_changed_application_notes_are_preserved_without_display(self):
        with JobDatabase(self.database) as database:
            database.add_application_note(1, "Synthetic private-note sentinel")
        before = self.database.read_bytes()
        code, out, err = self.db_command("demo-applications")
        self.assertEqual((code, out), (1, ""))
        self.assertNotIn("private-note sentinel", err)
        self.assertEqual(self.database.read_bytes(), before)

    def test_older_database_is_not_migrated_or_backed_up(self):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("PRAGMA user_version = 5")
        before = self.database.read_bytes()
        self.assertEqual(self.db_command("demo-status")[0], 1)
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(list(self.database.parent.glob("*.bak")), [])

    def test_sidecars_or_initialization_markers_refuse_before_database_access(self):
        for name in ("demo.sqlite3-wal", "demo.sqlite3-shm", "demo.sqlite3-journal", "demo.lock", "demo.building.sqlite3"):
            marker = self.database.parent / name
            marker.write_text("Synthetic marker sentinel", encoding="utf-8")
            try:
                with patch("sqlite3.connect", side_effect=AssertionError("SQLite opened while active")):
                    self.assertEqual(self.db_command("demo-status")[0], 1)
                self.assertEqual(marker.read_text(encoding="utf-8"), "Synthetic marker sentinel")
            finally:
                marker.unlink()

    def test_redirected_inputs_are_refused_before_reads(self):
        for method in ("is_symlink", "is_junction"):
            with patch.object(Path, method, return_value=True), patch("sqlite3.connect", side_effect=AssertionError("Redirect opened")):
                self.assertEqual(self.db_command("demo-status")[0], 1)
                self.assertEqual(self.command("demo-resume-review")[0], 1)

    def test_missing_fixtures_do_not_fall_back_to_personal_inputs(self):
        (self.fixtures / "evidence" / "profile.md").unlink()
        code, out, err = self.db_command("demo-rank")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("Required public demo input is missing", err)

    def test_changed_resume_fixture_is_not_displayed(self):
        path = self.fixtures / "resume_review" / "general_resume.txt"
        path.write_text("Synthetic unexpected-resume sentinel", encoding="utf-8")
        code, out, err = self.command("demo-resume-review")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("fixture changed", err)
        self.assertNotIn("unexpected-resume sentinel", err)

    def test_changed_configuration_does_not_modify_scores_or_get_used(self):
        path = self.root / "config" / "search_preferences.example.yaml"
        path.write_text(path.read_text(encoding="utf-8").replace("role_alignment: 30", "role_alignment: 40"), encoding="utf-8")
        code, out, err = self.db_command("demo-rank")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("fixture changed", err)

    def test_missing_corrupt_or_unsafe_allowlist_is_refused(self):
        path = self.root / cli.MANIFEST_LABEL
        original = path.read_bytes()
        for content in (b"not-json", b"{}", original.replace(b'demo/fixtures/jobs.json', b'../unrelated-input.json')):
            path.write_bytes(content)
            with self.subTest(content=content[:20]):
                code, out, err = self.command("demo-resume-review")
                self.assertEqual((code, out), (1, ""))
                self.assertTrue(err)
        path.unlink()
        self.assertEqual(self.command("demo-resume-review")[0], 1)

    def test_error_diagnostics_do_not_expose_exception_paths_or_secrets(self):
        with patch.object(cli, "_fixtures", side_effect=OSError("Synthetic credential/path sentinel")):
            code, out, err = self.command("demo-resume-review")
        self.assertEqual((code, out), (1, ""))
        self.assertNotIn("credential/path sentinel", err)
        self.assertNotIn(str(self.root), err)

    def test_resume_missing_database_selection_options_and_apply_are_rejected(self):
        for arguments in (("demo-resume-review", "--database", cli.DATABASE_LABEL),
                          ("demo-resume-review", "--apply"), ("demo-resume-review", "--approve"),
                          ("submit",), ("discover",), ("dashboard",), ("init",)):
            with self.subTest(arguments=arguments):
                self.assertEqual(self.command(*arguments)[0], 2)

    def test_module_entry_point_uses_the_public_handlers(self):
        out, err = StringIO(), StringIO()
        with patch("sys.argv", ["internship_agent", "demo-status", "--database", cli.DATABASE_LABEL]), redirect_stdout(out), redirect_stderr(err):
            with self.assertRaises(SystemExit) as result:
                runpy.run_module("internship_agent", run_name="__main__")
        self.assertEqual(result.exception.code, 0)
        self.assertIn("Synthetic jobs: 10; preparation records: 4", out.getvalue())
        self.assertEqual(err.getvalue(), "")

    def test_initializer_no_overwrite_protection_remains_authoritative(self):
        before = self.snapshot()
        with self.assertRaises(FileExistsError):
            demo.create_demo()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.db_command("demo-status")[0], 0)


if __name__ == "__main__":
    unittest.main()
