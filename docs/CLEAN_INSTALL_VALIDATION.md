# Clean installation and reproducibility (P4A)

SYNTHETIC DEMONSTRATION DATA — NOT REAL JOB POSTINGS.

This report records local clean-source installation checks. It distinguishes a
source-checkout demo from an installed code-only wheel. No private environment,
source tree, candidate, resume, database, secrets or Git metadata is copied.

Validation date: **2026-10-11**. **PASS for the Windows source-checkout and extracted
source-distribution workflows.** Wheel installation succeeds, but its standalone
demo is unsupported. Linux remains **UNVERIFIED**, with a blocked clean-environment
attempt; macOS and other Python versions were not tested.

## Tested environment and requirements

| Item | Verified value |
|---|---|
| Operating system | Windows 11, build 10.0.26200, AMD64 |
| Python | CPython 3.12.10 |
| New-venv pip | 25.0.1 |
| Build backend | setuptools 84.0.0, `setuptools.build_meta` |
| Local project | internship-agent-2027 0.1.0 |
| Declared Python requirement | `>=3.12`; only 3.12.10 completes this validation |
| Declared application dependencies | `PyYAML==6.0.3`, `pypdf>=5,<7`, `streamlit==1.65.0` |
| Declared build requirement | `setuptools>=68`; the tested snapshot uses 84.0.0 |

The launcher modifies a version-sensitive Streamlit configuration/poll-watcher
API. The earlier `streamlit>=1.40,<2` range included untested versions. P4A pins
`1.65.0`, the previously tested cached version, without upgrading dependencies or
weakening the launcher. pypdf remains declared even though the synthetic TXT demo
does not need PDF extraction. No dependency was removed to bypass installation.

The exact 40-package Windows snapshot is in
[`requirements/windows-py312.lock`](../requirements/windows-py312.lock), including
one SHA-256 per reviewed local wheel. These are locally tested versions, not a
latest-version, vulnerability, provenance or license certification. The lock is
for **Windows AMD64 / CPython 3.12** and is explicitly excepted from `.gitignore`'s
general runtime `*.lock` exclusion. Wheels and virtual environments are not
included in release artifacts.

| Dependency | Tested version |
|---|---|
| altair | 6.3.0 |
| anyio | 4.15.1 |
| attrs | 26.1.0 |
| certifi | 2026.7.22 |
| charset-normalizer | 3.5.2 |
| click | 8.5.0 |
| h11 | 0.16.0 |
| httptools | 0.9.0 |
| idna | 3.20 |
| itsdangerous | 2.2.0 |
| Jinja2 | 3.1.6 |
| jsonschema | 4.26.0 |
| jsonschema-specifications | 2025.9.1 |
| MarkupSafe | 3.0.4 |
| narwhals | 2.27.1 |
| numpy | 2.5.4 |
| packaging | 26.3 |
| pandas | 3.0.6 |
| pillow | 12.3.0 |
| protobuf | 7.36.2 |
| pyarrow | 25.0.1 |
| pydeck | 0.9.3 |
| pypdf | 6.20.0 |
| python-dateutil | 2.9.0.post0 |
| python-multipart | 0.0.32 |
| PyYAML | 6.0.3 |
| referencing | 0.37.0 |
| requests | 2.34.2 |
| rpds-py | 2026.9.1 |
| setuptools | 84.0.0 |
| six | 1.17.0 |
| starlette | 1.7.0 |
| streamlit | 1.65.0 |
| toml | 0.10.2 |
| typing_extensions | 4.16.0 |
| tzdata | 2026.5 |
| urllib3 | 2.8.0 |
| uvicorn | 0.54.0 |
| watchdog | 6.0.0 |
| websockets | 17.2 |

## Exact offline source installation

Start with a source tree containing only the reviewed manifest files, or extract
the inspected source archive. Do not copy an existing `.venv`, database, logs,
screenshots, caches, Git metadata, credentials or any other workspace's files.
Have a separately reviewed local wheel directory containing the locked artifacts;
P4A used local pip-cache wheel bytes and verified their hashes. No package index,
download or private environment was used. Without those wheels the procedure is
blocked: ask for authorization before fetching packages.

Run **from the new source root** in PowerShell. Supply the actual Python 3.12 and
local wheel paths in the first two variables. The venv must not already exist.

```powershell
$p4aPython = '<Python-3.12-executable>'
$p4aWheels = '<reviewed-local-wheel-directory>'
$env:PYTHONDONTWRITEBYTECODE = '1'
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
if (Test-Path -LiteralPath .venv) { throw 'Use a fresh source test directory.' }
& $p4aPython -B -m venv .venv
& .\.venv\Scripts\python.exe -B -m pip --isolated --disable-pip-version-check install --no-index --no-cache-dir --only-binary=:all: --require-hashes --find-links $p4aWheels -r requirements/windows-py312.lock
& .\.venv\Scripts\python.exe -B -m pip --isolated --disable-pip-version-check install --no-index --no-cache-dir --no-build-isolation --find-links $p4aWheels -r requirements.txt
& .\.venv\Scripts\python.exe -B -m pip --isolated --disable-pip-version-check check
& .\.venv\Scripts\python.exe -B -c "import internship_agent; print(internship_agent.__file__)"
& .\.venv\Scripts\internship-agent.exe --help
```

Check each command's exit code before continuing. The lock installs the tested
build tool and all transitive dependencies. The editable project install performs
full dependency resolution, with indexes disabled and build isolation disabled
because the reviewed backend is already installed. **No `--no-deps` shortcut is
used.** `requirements.txt` contains `-e .`: pip resolves it against the current
working directory, not the directory containing that requirements file. Passing
an absolute requirements-file path from a different checkout can install that
other checkout; avoid this and verify the import path above. Installation does
not require PYTHONPATH or an existing database.

Validation used separate new venvs for the original 82-file source baseline,
the revised 86-file source copy, the extracted source archive and the wheel-only
test. Everything is under ignored `data/clean-install-p4a/`. The original public
development venv was not copied or used for clean tests. The baseline install
already passed all 405 prior tests; final validation runs all 409 below.

## Initialize and verify the offline workflow

From the clean source root and its new `.venv`:

```powershell
& .\.venv\Scripts\python.exe -B scripts/create_demo.py
& .\.venv\Scripts\internship-agent.exe demo-status --database data/demo/demo.sqlite3
& .\.venv\Scripts\internship-agent.exe demo-jobs --database data/demo/demo.sqlite3
& .\.venv\Scripts\internship-agent.exe demo-applications --database data/demo/demo.sqlite3
& .\.venv\Scripts\internship-agent.exe demo-rank --database data/demo/demo.sqlite3
& .\.venv\Scripts\internship-agent.exe demo-rank --database data/demo/demo.sqlite3 --job demo-002
& .\.venv\Scripts\internship-agent.exe demo-resume-review
```

The installed `python.exe -B -m internship_agent` entry is also verified with
PYTHONPATH absent. Help and all five commands return 0. The initializer creates
new synthetic output, not a copy of a previous demo or user database.

| Check | Result |
|---|---|
| SQLite | integrity_check `ok`, zero foreign-key violations, schema 6 |
| Demo state | COMPLETED, 10 fictional jobs, 4 preparation records |
| Sorted ranking scores | 91.00, 88.00, 75.00, 72.67, 66.00, 63.50, 55.00, 36.00, 12.00, 6.00 |
| Selected demo-002 | 72.67, separate UNKNOWN eligibility |
| Resume review | 5 exact evidence-anchored proposals; source unchanged; Apply unavailable |
| Repeat initializer | exit 1; existing output preserved |
| `--resume` against completed output | exit 1; existing output preserved |
| Read-only smoke verification | database and all fixture bytes unchanged |

The fixture fingerprint remains
`cdb28079be0c14f07f5d4209eaf0d91be019834c2bf0683b803282d4330f0980`;
the proposal fingerprint remains
`a3f9fc4ef400028115be11cc90d54412968efb775e827c80af23be93bf242c83`.
The existing adversarial recovery tests also pass for unrelated/extended SQLite
files and modified demo state. No initializer/backend behavior change was needed.

## Dashboard and shutdown

Launch manually from the clean source root:

```powershell
& .\.venv\Scripts\python.exe -B scripts/run_dashboard.py --theme light
```

Open `http://127.0.0.1:8501` in a local browser. The real foreground server from
the extracted source archive rendered **Overview, Demo Jobs, Application Tracker
and General Resume** successfully. Counts, 91-point selected job, separate UNKNOWN
eligibility, existing preparation history and exact simulation-qualified resume
correction were inspected. All pages displayed the synthetic notice. A local
asset inventory observed 137 assets, all at `http://127.0.0.1:8501`; telemetry is
disabled. The process-lifetime launcher guard remained enabled. No unrestricted
`streamlit run` invocation was used. OS socket inspection confirmed the only
server listener was **127.0.0.1:8501**.

Stop with Ctrl+C in the launch terminal and confirm the listener closes. Closing
the browser does not stop the server. In this Codex Windows terminal, Ctrl+C was
not forwarded to the Python child; PowerShell's Stop-Process also reported a host
error. The native termination tool stopped only the server whose clean-venv
launcher path and parent-child identity had been verified. Its venv launcher then
exited, and OS checks confirmed zero validation processes/listeners. This browser
session therefore verifies operation and cleanup, **not successful Ctrl+C delivery**.

A separate smoke check used Streamlit's existing
`stop_immediately_for_testing=True` hook through the unchanged safety launcher.
Native startup and shutdown returned 0 and printed zero external-network,
external-input and filesystem-write attempts. This is a clean framework
startup/shutdown check, not a substitute for the real four-page browser check.
The real browser server was forcibly stopped, so its final counter line was not
available. No product shutdown mechanism or scheduler was added. No server remains.
An actual synthetic-only browser capture is ignored at
`data/clean-install-p4a/dashboard-resume-clean.jpg`.

## Packaging findings and fixes

The original clean editable install worked, but its source archive omitted
runtime fixtures, configuration, launch scripts and test fixtures. P4A adds
`MANIFEST.in` with a default exclusion and **86 exact reviewed filenames**, no
recursive include. Tests verify the inventory matches PUBLIC_RELEASE_MANIFEST.md.
The archive now contains those 86 files plus only three build-generated metadata
files: `PKG-INFO`, `setup.cfg` and
`src/internship_agent_2027.egg-info/SOURCES.txt`. These contain public metadata;
an existing environment or egg-info directory is not copied as release input.

Builds were made locally with the installed setuptools backend:

```powershell
# Use an already-created ignored artifact directory.
& .\.venv\Scripts\python.exe -B -c "from setuptools import build_meta; print(build_meta.build_sdist('dist')); print(build_meta.build_wheel('dist'))"
```

Archive names and contents were inspected before extraction. A brand-new venv in
the extracted sdist installed all locked dependencies and the project offline,
passed `pip check`, imported the extracted `src/`, initialized new demo output and
passed the complete offline workflow. Documentation was finalized afterward;
final archives were rebuilt and compared with the reviewed/tested source files.

The wheel deliberately contains **32 Python files and 5 dist-info files**, with
`include-package-data=false`; no demo assets, source launchers or local settings.
Its metadata and console entry are valid. A separate fresh wheel-only environment
installed all dependencies and the wheel offline, passed `pip check`, imported
from its own site-packages and displayed CLI help from outside a source tree.
`demo-resume-review` returned 1 with a fixed missing-input diagnostic and no
proposal output. **Standalone wheel demo: unsupported**, not a passed end-to-end
install. The supported demo distribution is source checkout/extracted sdist.
Relocating runtime assets or designing general package resources is deferred.

Synthetic ignored canaries for `.env`, local Streamlit secrets, candidate data,
database and logs were placed in the disposable source for a build. Archive
inspection found none of them, nor any venv, Git metadata, cache, database, private
resume or runtime output. Canaries were invented packaging markers, not real
secrets or candidate files; they were removed after checking. `.gitignore` alone
was not used as the package privacy boundary.

## Tests and privacy validation

From the clean source root:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
& .\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
& .\.venv\Scripts\python.exe -B -m pip --isolated --disable-pip-version-check check
```

**409 tests passed: all 405 prior public tests plus 4 packaging regressions;
zero failures, errors or skips.** The final complete run used the new extracted
source environment with an additional process-wide audit guard. It allowed reads
only inside that clean source/runtime and writes only in its isolated test temp
directory. All 30 loaded application modules originated in its `src/`, not the
development checkout. Counters: **0 network, 0 outside input reads, 0 protected
writes**. Windows AppTest needed 58 trusted standard-library `_fallback_socketpair`
IPC operations; the guard allowed only that internal path and blocked other sockets.
Expected simulated guard-rejection diagnostics are not real protected writes.
`pip check` passed in all four Windows install environments.

The four new regressions cover archive allowlist equality, necessary runtime
assets, the exact tested Streamlit/entry-point boundary, and hashed dependency
pins including the `.gitignore` lock exception. The original 104 withheld private
cases remain omitted and are not counted as restored passes.

A separately guarded clean CLI/read-only workflow recorded zero network,
external-input or write attempts and preserved database/fixture hashes. The
dashboard launcher blocks external transport, unexpected inputs and persistent
writes; observed browser assets were local. No private project, candidate,
resume, research or user database was accessed. No real ATS request, application
submission, resume edit/Apply, schedule, remote, CI, license or publication was
introduced. These are scoped local validation results, not an OS-wide security
certification or a scan of the private project.

## Platform limits and troubleshooting

Windows is **verified** as above. A local Ubuntu 24.04 WSL environment genuinely
exists, with CPython 3.12.3. Independent creation of a new Linux `.venv` inside
the disposable public validation tree failed because `ensurepip` is missing;
the distribution needs its Python venv support. No system package was installed.
The available compiled wheels also have Windows tags, not Linux-compatible tags.
No Linux dependency install, tests or demo run is claimed. Linux remains
**UNVERIFIED/BLOCKED pending a separately authorized local venv toolchain and
matching Linux wheels**. Nothing was downloaded. macOS and Python 3.13+ are untested.

Source review found Path-based runtime paths, an exact source-local `.venv`
check and Python 3.12's junction detection. Generic discovery locking already
branches between Windows msvcrt and Unix fcntl; live discovery was not executed.
The dashboard's missing-demo hint and primary documentation show a Windows Python
path. These observations do not establish Linux compatibility, and no portability
feature was added.

- **Missing/mismatched wheel or hash:** stop; use reviewed matching artifacts.
  Do not remove hash checking, loosen dependencies or download without permission.
- **Wrong import source:** run the editable install from the intended source root
  and recheck `internship_agent.__file__` and `sys.prefix`.
- **Wheel-only missing inputs:** use the reviewed source tree; never redirect to
  another workspace's candidate/resume/database.
- **Existing or unexpected database:** preserve it; follow DEMO_GUIDE.md. The
  initializer and read-only interfaces must refuse it rather than overwrite it.
- **Version-sensitive launcher error:** use the pinned Streamlit version; review
  the adapter before changing the pin, never bypass its guards.
- **Port busy or Ctrl+C ineffective:** verify ownership and stop only your demo
  process. Do not change binding or terminate unrelated Python processes.
- **Unicode terminal output:** use UTF-8 terminal/output settings; source evidence
  and exact proposal strings remain UTF-8.

Remaining release blockers are license/notice/provenance approval, broader
onboarding/documentation and safe integration coverage, unverified platforms,
any future standalone-wheel demo support, and final publication review. Resume
editing requires a separately approved evidence/conflict/approval workflow and
DOCX structure/render validation. Apply stays unavailable. Stop after P4A.
