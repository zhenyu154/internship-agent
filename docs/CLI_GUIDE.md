# Safe public offline CLI (P3B.3A)

SYNTHETIC DEMONSTRATION DATA — NOT REAL JOB POSTINGS.

This small, independently authored CLI connects the public demo database, ranking
backend and read-only resume proposals. It is an end-to-end offline demonstration
inside this staging checkout. The full personalized CLI/Dashboard, Windows
launchers, resume Apply, discovery and submission remain excluded. P3B.3B now
provides a separately authored public read-only Dashboard.

## Environment and entry points

For current installation, follow [P4A clean-install validation](CLEAN_INSTALL_VALIDATION.md).
It installs all declared dependencies into a fresh public `.venv` with full offline
dependency resolution and `pip check`; no `--no-deps` shortcut or PYTHONPATH is needed.
The source root must be the working directory when installing `requirements.txt`.
The code-only wheel does not supply the fixed demo assets.

The following records the narrower historical P3B.3A environment check.
It used Python 3.12+ and the existing isolated public `.venv`. PyYAML 6.0.3 is sufficient
for these offline operations. The declared PDF/UI packages are not imported or
installed for the demo. Dependencies were not added or upgraded in project metadata.

P3B.3A installed the declared setuptools build requirement from a locally cached
wheel, then verified the editable package/console entry point with offline flags:

```powershell
& .\.venv\Scripts\python.exe -B -m pip --isolated --disable-pip-version-check install --no-index --no-deps --no-build-isolation --no-cache-dir -e .
```

This requires the build tooling already available locally. It creates ignored
environment/package metadata only; do not fetch packages without authorization.
It is a verified staging editable install, not clean full-package installation
or a standalone wheel/portability claim. The fixture paths are anchored to this
checkout, rather than another project or the current directory.

The verified console entry point is:

```powershell
& .\.venv\Scripts\internship-agent.exe --help
```

Without installing the console entry point, use the package module from staging:

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
$env:PYTHONDONTWRITEBYTECODE = '1'
& .\.venv\Scripts\python.exe -B -m internship_agent --help
```

The module and console script call the same public handlers. `--help` and each
command's `--help` need no database or fixture loading. Use UTF-8 terminal/output
settings when needed to display the synthetic notice and Unicode exact strings.

## End-to-end manual demonstration

From the staging root, create a fresh demo using the existing initializer only:

```powershell
& .\.venv\Scripts\python.exe -B scripts/create_demo.py
```

If the demo already exists, this command refuses overwrite and preserves it.
Review the [demo guide](DEMO_GUIDE.md) for explicit interrupted-run recovery or
disposal. The CLI neither creates nor resumes a database.

Inspect the explicitly selected final demo database:

```powershell
& .\.venv\Scripts\internship-agent.exe demo-status --database data/demo/demo.sqlite3
& .\.venv\Scripts\internship-agent.exe demo-jobs --database data/demo/demo.sqlite3
& .\.venv\Scripts\internship-agent.exe demo-applications --database data/demo/demo.sqlite3
& .\.venv\Scripts\internship-agent.exe demo-rank --database data/demo/demo.sqlite3
& .\.venv\Scripts\internship-agent.exe demo-rank --database data/demo/demo.sqlite3 --job demo-002
& .\.venv\Scripts\internship-agent.exe demo-resume-review
```

Replace `internship-agent.exe` with `python.exe -B -m internship_agent` for the
module entry point. All commands print to the terminal; none saves a report.

| Command | Verified synthetic result |
|---|---|
| `demo-status` | COMPLETED; 10 jobs; 4 preparation records; integrity ok; zero foreign-key violations; schema 6 |
| `demo-jobs` | All 10 fictional postings, IDs, reserved example.test URLs and existing relevance classifications |
| `demo-applications` | Only 4 tracked preparation records; NOT_STARTED, RESEARCHING, PREPARING and READY_TO_APPLY; notes/receipts omitted |
| `demo-rank` | All 10 unchanged scores with component calculations, anchors, limitations and separate eligibility/application annotations |
| `demo-rank --job demo-002` | 72.67/100; components 24.00 + 20.00 + 16.67 + 12.00; eligibility UNKNOWN |
| `demo-resume-review` | Same five proposals, stable change IDs and proposal fingerprint; exact before/after text; pending publication stays PENDING |

Status includes the unchanged demo fixture fingerprint. Ranking uses the existing
30/30/25/15 weights and the current ranking formulas, not a second implementation.
Scores are heuristics, not admission probabilities. UNKNOWN needs review and is
not automatic ineligibility. POLICY_EXCLUDED cases remain displayed separately.
Sparse evidence and simulation/generalization limits remain visible.

The unchanged sorted scores are 91.00, 88.00, 75.00, 72.67, 66.00, 63.50, 55.00,
36.00, 12.00 and 6.00. The source/candidate/configuration references and fingerprints
come directly from the ranking results. No ranking output is saved in SQLite.

Resume output is the existing backend rendering, with exact JSON-escaped strings,
source anchors, evidence states, experimental qualifiers and uncertainties. The
synthetic proposal fingerprint remains
`a3f9fc4ef400028115be11cc90d54412968efb775e827c80af23be93bf242c83`.
It proposes four corrections and one skills addition without changing the source
resume. Resume Apply is unavailable. The command uses the synthetic TXT fixture;
DOCX extraction supports only the conservative paragraph/run package subset in
the [resume-review guide](RESUME_REVIEW_GUIDE.md). Tables, styles, tracked changes,
fields, images, hidden text and other unsupported parts cannot be flattened or
silently modified. No DOCX editing, approval or PDF generation is implemented.

## Isolation and failures

Database commands require `--database`. Only `data/demo/demo.sqlite3` in this
public workspace is selectable; its exact absolute equivalent and Windows path
separators are accepted. Other filenames/locations, traversal, URIs, UNC/device
paths and alternate streams are refused before opening a database. No candidate,
resume, research, registry or report path override is offered.

The fixed public `demo/fixtures/offline_cli_manifest.json` lists exactly nine
reviewed fixture/configuration files and hashes. Missing/changed files or an
unexpected allowlist cause refusal. Updating synthetic fixtures/configuration
requires a separate reviewed allowlist update; the CLI never rewrites it. This
is local integrity/review metadata, not authentication or independent truth.

SQLite is opened with read-only access, without schema migration. Before any
records are displayed, the shared demo backend validates the complete run,
current exact schema, integrity, identities, job/metadata payloads, application
states/notes/history, progress and fixture fingerprint. An arbitrary or edited
database is refused; its records are not printed. Active sidecars, locks and
partial output cause refusal before opening SQLite. Stop all writers and review
disposable output first; this is a manual single-process demo, not a concurrency
or live-update interface. Symlinks/junctions are refused for all demo inputs.

Exit codes: 0 for success/help, 2 for invalid arguments, 1 for missing/corrupt/
incompatible inputs. Failures print fixed diagnostics without arbitrary exception
text, absolute paths, notes or credentials. No partial result is printed. A missing
database is not initialized; no private files are searched as a fallback.

Filesystem writes are confined to explicitly requested initialization and the
documented local environment installation. Read-only commands do not write
databases, applications, resumes, reports or progress state. Use `-B` or
PYTHONDONTWRITEBYTECODE to suppress Python's normal bytecode cache writes; public
package startup also disables future bytecode writes. Existing `.gitignore` rules
exclude .venv, data, SQLite/sidecars, locks, egg-info/build output and real documents.

## Testing and deferred work

P3B.3B adds a [local read-only dashboard](DASHBOARD_DEMO_GUIDE.md). CLI and UI
now share `DemoServices` for the same fixed input/allowlist, ranking and resume
backend calls. Existing commands, scores and proposals are unchanged.

```powershell
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
$env:PYTHONDONTWRITEBYTECODE = '1'
& .\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

Only synthetic fixtures, mocked services and temporary databases are used by
tests. This step does not add live boards, APIs, browser automation, submissions,
scheduling, background services, Git remotes, a license or publication. P3B.3B's
thin read-only Dashboard has synthetic integration coverage and loopback-only
manual operation; broader user integrations remain deferred. Resume Apply must remain
disabled until an approved writer workflow exists. The [README](../README.md) supplies onboarding;
provenance/license review and publication approval remain release blockers.
P4A verifies clean Windows source installation; other platform/demo distribution
limits are recorded in its report. The P3B.3A implementation scope remains unchanged.
