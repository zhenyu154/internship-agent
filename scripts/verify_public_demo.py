"""Manual CI checks for reviewed public files; no application features.

The coordinator spawns only this interpreter and pip/check workers. Application
checks run behind a process-lifetime audit boundary, in synthetic temporary trees.
The separate dashboard worker uses the unchanged safety launcher and Streamlit's
native stop-immediately test hook. No user database or document is selected.
"""

import contextlib
from email.parser import BytesParser
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import runpy
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import unquote, urlsplit
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SMOKE_FILES = (
    "config/search_preferences.example.yaml", "demo/fixtures/jobs.json",
    "demo/fixtures/offline_cli_manifest.json", "demo/fixtures/evidence/profile.md",
    "demo/fixtures/evidence/experience_bank.md", "demo/fixtures/evidence/verification_report.md",
    "demo/fixtures/evidence/ranking_features.json", "demo/fixtures/resume_review/general_resume.txt",
    "demo/fixtures/resume_review/observations.md", "demo/fixtures/resume_review/claims.json",
    "scripts/create_demo.py",
)


def reviewed_files():
    from internship_agent.demo_services import reject_links
    inventory_path = ROOT / "PUBLIC_RELEASE_MANIFEST.md"
    reject_links(inventory_path)
    inventory = inventory_path.read_text(encoding="utf-8")
    inventory = inventory.split("## Included file inventory", 1)[1].split("## Strict exclusions", 1)[0]
    labels = re.findall(r"^\| `([^`]+)` \|", inventory, re.M)
    for label in labels:
        path = ROOT / label
        if Path(label).is_absolute() or ".." in Path(label).parts or "*" in label:
            raise ValueError("Unsafe public inventory label")
        reject_links(path)
        if not path.resolve().is_relative_to(ROOT.resolve()) or not path.is_file():
            raise ValueError("Missing or redirected public inventory input")
    if not labels or len(labels) != len(set(labels)):
        raise ValueError("Invalid public inventory")
    return labels


def install_test_guard(work):
    runtime = Path(sys.base_prefix).resolve()
    counts = dict(network=0, external_input=0, protected_write=0, trusted_socketpair=0)

    def refuse(kind):
        counts[kind] += 1
        raise PermissionError("Public CI isolation refused " + kind)

    def check_path(raw, writing=False):
        if raw is None or isinstance(raw, int) or raw in {":memory:", os.devnull}:
            return
        raw = os.fsdecode(raw)
        if raw.startswith("file:"):
            raw = unquote(urlsplit(raw).path)
            if len(raw) > 2 and raw[0] == "/" and raw[2] == ":":
                raw = raw[1:]
        path = Path(raw).resolve()
        if writing and not path.is_relative_to(work):
            refuse("protected_write")
        if not (path.is_relative_to(ROOT) or path.is_relative_to(runtime)):
            refuse("external_input")
        if path.is_relative_to(ROOT / "data") and not path.is_relative_to(work):
            refuse("external_input")
        if path.is_relative_to(ROOT) and path.relative_to(ROOT).parts[:1] in [
                (name,) for name in ("candidate", "resumes", "reports", "logs", "private", "credentials", "secrets")]:
            refuse("external_input")

    def trusted_ipc():
        frame = sys._getframe(2)
        while frame:
            if (frame.f_code.co_name == "_fallback_socketpair"
                    and Path(frame.f_code.co_filename).resolve() == runtime / "Lib" / "socket.py"):
                return True
            frame = frame.f_back
        return False

    def audit(event, args):
        if event in {"socket.connect", "socket.connect_ex", "socket.bind", "socket.sendto"}:
            address = args[-1]
            if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"} and trusted_ipc():
                counts["trusted_socketpair"] += 1
            else:
                refuse("network")
        elif event in {"socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr", "subprocess.Popen", "os.system"}:
            refuse("network")
        elif event == "open":
            mode, flags = args[1] or "", args[2] or 0
            check_path(args[0], any(c in mode for c in "wax+") or bool(flags & (
                os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)))
        elif event == "sqlite3.connect":
            check_path(args[0])
        elif event in {"os.mkdir", "os.remove", "os.rmdir", "os.chmod", "os.utime"}:
            check_path(args[0], True)
        elif event in {"os.rename", "os.link", "os.symlink"}:
            check_path(args[0], True)
            check_path(args[1], True)
        elif event in {"os.listdir", "os.scandir"}:
            check_path(args[0])

    sys.addaudithook(audit)
    return counts


def smoke(work, labels):
    from internship_agent import cli, demo
    from internship_agent.demo_services import DemoServices
    root = work / "smoke"
    for label in SMOKE_FILES:
        if label not in labels:
            raise ValueError("Smoke input is not reviewed")
        destination = root / label
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / label, destination)
    overrides = dict(PUBLIC_ROOT=root, FIXTURE_DIRECTORY=root / "demo/fixtures",
                     PREFERENCES=root / "config/search_preferences.example.yaml",
                     OUTPUT_ROOT=root, OUTPUT_DIRECTORY=root / "data/demo")
    with patch.multiple(demo, **overrides), patch.object(cli, "PUBLIC_ROOT", root):
        with patch.object(sys, "argv", ["scripts/create_demo.py"]), contextlib.redirect_stdout(io.StringIO()):
            try:
                runpy.run_path(str(root / "scripts/create_demo.py"), run_name="__main__")
            except SystemExit as result:
                if result.code != 0:
                    raise RuntimeError("Fresh synthetic initializer failed")
        inputs = [root / label for label in SMOKE_FILES] + [root / "data/demo/demo.sqlite3"]
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
        commands = [["--help"], *[[command, "--database", "data/demo/demo.sqlite3"] for command in (
            "demo-status", "demo-jobs", "demo-applications", "demo-rank")],
            ["demo-rank", "--database", "data/demo/demo.sqlite3", "--job", "demo-002"],
            ["demo-resume-review"]]
        for command in commands:
            output, error = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
                code = cli.main(command)
            if code != 0 or demo.NOTICE not in output.getvalue():
                raise RuntimeError("Synthetic CLI smoke failed: " + command[0])
        services = DemoServices(root)
        with services.open_database("data/demo/demo.sqlite3") as (database, validation):
            scores = [item.technical_match_score for item in services.ranked_jobs(database)]
        _, proposal = services.resume_review()
        expected = dict(integrity_check="ok", foreign_key_violations=0, schema_version=6,
                        jobs=10, applications=4, run_status="COMPLETED")
        if any(validation[key] != value for key, value in expected.items()):
            raise RuntimeError("Fresh SQLite smoke mismatch")
        if scores != [91, 88, 75, 72.67, 66, 63.5, 55, 36, 12, 6] or len(proposal.changes) != 5:
            raise RuntimeError("Ranking/resume regression")
        for resume in (False, True):
            try:
                demo.create_demo(resume=resume)
            except (OSError, ValueError):
                pass
            else:
                raise RuntimeError("Existing output unexpectedly accepted")
        if any(hashlib.sha256(path.read_bytes()).hexdigest() != value for path, value in before.items()):
            raise RuntimeError("Read-only smoke modified its inputs")
    print("Synthetic smoke PASS: help, all five commands, selected ranking, SQLite schema/integrity, no-overwrite and unchanged input bytes.")


def packaging(work, labels):
    from setuptools import build_meta
    source, output = work / "source", work / "artifacts"
    output.mkdir()
    for label in labels:
        destination = source / label
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / label, destination)
    # Invented exclusion canaries only; never read a real secrets/private directory.
    for label in (".env", ".streamlit/secrets.toml", "candidate/synthetic.txt",
                  "data/synthetic.sqlite3", "logs/synthetic.log"):
        canary = source / label
        canary.parent.mkdir(parents=True, exist_ok=True)
        canary.write_text("SYNTHETIC PACKAGING EXCLUSION MARKER", encoding="utf-8")
    previous = Path.cwd()
    try:
        os.chdir(source)
        with contextlib.redirect_stdout(io.StringIO()):
            sdist = output / build_meta.build_sdist(str(output))
            wheel = output / build_meta.build_wheel(str(output))
    finally:
        os.chdir(previous)
    expected_license = (ROOT / "LICENSE").read_bytes()

    def validate_license_metadata(raw):
        metadata = BytesParser().parsebytes(raw)
        if metadata.get("License-Expression") != "MIT" or metadata.get_all("License-File") != ["LICENSE"]:
            raise RuntimeError("Built license metadata differs from the approved MIT declaration")
        if metadata.get("License") or any(value.startswith("License ::") for value in metadata.get_all("Classifier", [])):
            raise RuntimeError("Contradictory legacy license metadata")
    with tarfile.open(sdist) as archive:
        files = {member.name.split("/", 1)[1]: member for member in archive.getmembers() if member.isfile()}
        extra = {"PKG-INFO", "setup.cfg", "src/internship_agent_2027.egg-info/SOURCES.txt"}
        if set(files) != set(labels) | extra:
            raise RuntimeError("Source archive differs from reviewed inventory")
        for label in labels:
            if archive.extractfile(files[label]).read() != (ROOT / label).read_bytes():
                raise RuntimeError("Source archive content changed")
        validate_license_metadata(archive.extractfile(files["PKG-INFO"]).read())
        if archive.extractfile(files["LICENSE"]).read() != expected_license:
            raise RuntimeError("Source archive license changed")
    with zipfile.ZipFile(wheel) as archive:
        code = {label.removeprefix("src/") for label in labels if label.startswith("src/")}
        metadata = {"internship_agent_2027-0.1.0.dist-info/" + name for name in (
            "METADATA", "WHEEL", "entry_points.txt", "top_level.txt", "RECORD", "licenses/LICENSE")}
        if set(archive.namelist()) != code | metadata:
            raise RuntimeError("Wheel contains unexpected files")
        for label in code:
            if archive.read(label) != (ROOT / "src" / label).read_bytes():
                raise RuntimeError("Wheel content changed")
        validate_license_metadata(archive.read("internship_agent_2027-0.1.0.dist-info/METADATA"))
        if archive.read("internship_agent_2027-0.1.0.dist-info/licenses/LICENSE") != expected_license:
            raise RuntimeError("Wheel license changed")
    print(f"Packaging PASS: {len(labels)} reviewed source files plus three generated metadata files; MIT text/metadata in source and wheel; code-only wheel boundary preserved.")


def checks():
    from internship_agent.demo_services import reject_links
    platform.uname()  # Trusted local Windows metadata probe before isolation.
    os.chdir(ROOT)
    parent = ROOT / "data/ci-verification"
    reject_links(parent)
    parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="offline-", dir=parent)).resolve()
    tempfile.tempdir = str(work)
    counts = install_test_guard(work)
    labels = reviewed_files()
    result = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.discover(
        str(ROOT / "tests"), top_level_dir=str(ROOT)))
    if not result.wasSuccessful() or result.testsRun < 409 or result.skipped:
        return 1
    smoke(work, labels)
    packaging(work, labels)
    loaded = [Path(module.__file__).resolve() for name, module in sys.modules.items()
              if name.startswith("internship_agent") and getattr(module, "__file__", None)]
    if not all(path.is_relative_to(ROOT / "src") for path in loaded):
        raise RuntimeError("Application imports escaped the public source")
    # Only the newly-created, resolved verification subtree is removed.
    if work.parent != parent.resolve():
        raise RuntimeError("Unexpected verification cleanup target")
    shutil.rmtree(work)
    print("Offline audit counters:", json.dumps(counts, sort_keys=True))
    return int(any(counts[key] for key in ("network", "external_input", "protected_write")))


def dashboard():
    from internship_agent import dashboard_launch
    from streamlit.web import bootstrap
    original_run, original_guard = bootstrap.run, dashboard_launch.offline_audit_guard
    recorded = []

    def native_shutdown(*args, **kwargs):
        kwargs["stop_immediately_for_testing"] = True
        return original_run(*args, **kwargs)

    def record_guard(*args, **kwargs):
        guard, counts = original_guard(*args, **kwargs)
        recorded.append(counts)
        return guard, counts  # The original process-lifetime protections remain active.

    with patch.object(bootstrap, "run", native_shutdown), patch.object(dashboard_launch, "offline_audit_guard", record_guard):
        code = dashboard_launch.main(["--theme", "light"])
    return int(code != 0 or len(recorded) != 1 or any(recorded[0].values()))


def main():
    if sys.argv[1:] == ["--checks"]:
        return checks()
    if sys.argv[1:] == ["--dashboard"]:
        return dashboard()
    if sys.argv[1:]:
        raise ValueError("No public input/path overrides are accepted")
    if Path(sys.prefix).resolve() != (ROOT / ".venv").resolve():
        raise RuntimeError("Use this source checkout's .venv")
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError("This Windows CI procedure is prepared for Python 3.12")
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    commands = [
        [sys.executable, "-B", "-m", "pip", "--isolated", "--disable-pip-version-check", "check"],
        [sys.executable, "-B", str(Path(__file__).resolve()), "--checks"],
        [sys.executable, "-B", str(Path(__file__).resolve()), "--dashboard"],
    ]
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, env=environment, check=False)
        if result.returncode:
            return result.returncode
    print("Public offline verification PASS. Hosted CI and index installation remain unverified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
