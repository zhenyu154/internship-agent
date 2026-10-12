# Public offline Streamlit dashboard (P3B.3B)

SYNTHETIC DEMONSTRATION DATA — NOT REAL JOB POSTINGS.

The four-page dashboard demonstrates the existing public backends with one
fictional candidate, ten fictional jobs, four preparation records and five resume
proposals. It is local, manual and read-only. It is not a live recruiting service,
real applicant profile or application-submission tool.

## Prerequisites and installation

Use Python 3.12+ and this source checkout's isolated `.venv`. Follow the
[P4A clean-install procedure](CLEAN_INSTALL_VALIDATION.md), using reviewed local
wheels and the hashed Windows dependency snapshot. Windows 11, Python 3.12.10 and
Streamlit 1.65.0 pass fresh source and extracted-source-archive validation;
`pip check` reports no broken requirements. The code-only wheel does not contain
the demo fixtures, launcher or configuration and cannot run this complete workflow.

P4A pins Streamlit to `1.65.0` because the configuration adapter uses version-sensitive
APIs; the previous broad range was not a verified compatibility promise. Older or
newer versions need separate review/testing. The wheel cache is ignored environment
material, not bundled release data. Do not use the private project or download
missing packages without authorization.

Initialize explicitly if the synthetic database does not already exist:

```powershell
& .\.venv\Scripts\python.exe -B scripts/create_demo.py
```

Existing output is refused. Recovery and disposal remain governed by the
[demo guide](DEMO_GUIDE.md); the dashboard never initializes, repairs or overwrites
a database. The configured input is exactly `data/demo/demo.sqlite3` in this
workspace. Other paths and arbitrary/user databases are not accepted.

## Manual launch and shutdown

From the staging root in PowerShell:

```powershell
& .\.venv\Scripts\python.exe -B scripts/run_dashboard.py --theme light
```

For the dark theme, first stop the light server, then launch:

```powershell
& .\.venv\Scripts\python.exe -B scripts/run_dashboard.py --theme dark
```

Open `http://127.0.0.1:8501` in a local browser. The script runs in the foreground,
binds only to `127.0.0.1`, and does not start a browser automatically. There is no
startup integration, public deployment, scheduler, daemon or background service.
Keep the terminal open while using the demo. **Stop with Ctrl+C in that terminal**;
wait for shutdown before relaunching. Closing the browser tab does not stop the
server. If a terminal host does not forward Ctrl+C, terminate only the verified
task-owned Python process running `scripts/run_dashboard.py`; never stop unrelated
Python sessions. Validation in the Codex Windows terminal needed this fallback.

Use this launcher, not an unrestricted `streamlit run` invocation. It constrains
configuration to the reviewed workspace file, ignores global/user secrets, removes
Streamlit environment overrides in its own process, disables telemetry, file
watching, static serving, auto-reload and detailed error exposure, and retains
CORS/XSRF protections. No address, external configuration or job-input override
is offered. Streamlit 1.65's separate config-file poll watcher is explicitly
suppressed by the reviewed bootstrap adapter; restart manually for configuration
changes. No ongoing configuration polling is installed. The launcher checks
the public `.venv`, sets the public
working directory, and ensures an ignored `.venv/dashboard-tmp` directory during
explicit startup. Runtime metadata is initialized locally; its process-lifetime
guard rejects external sockets, unexpected reads, subprocesses and persistent
filesystem writes after initialization. Local browser/WebSocket traffic is allowed.

The configuration adapter is verified against Streamlit 1.65.0 and must be reviewed
when changing library versions. The source dashboard module alone does not install
the launch guard; bypassing the launcher is outside the supported workflow.

Untested Linux manual equivalent, from the staging root:

```sh
.venv/bin/python -B scripts/run_dashboard.py --theme light
```

Stop with Ctrl+C. This command is documented, **not claimed tested**. P4A found
Ubuntu 24.04/Python 3.12.3, but clean environment creation was blocked by missing
`ensurepip`; the local compiled wheels target Windows. Linux remains UNVERIFIED.
No Windows `.cmd`/`.ps1` launcher or broader portability feature was added.

## Four-page walkthrough

Every page carries the exact synthetic-data banner. Use the sidebar's
**Explore the demo** navigation; on narrow windows, expand the sidebar with the
top-left arrow. Native tables support search, column sorting and horizontal scroll.
Full selected-job titles remain available in the detail panel.

1. **Overview:** validated job/preparation counts, database integrity and resume
   proposal count. A concise capability table distinguishes implemented local
   functionality from planned document output and broader integrations. Advanced
   Details contains the fixed input path, schema and fixture fingerprint.
2. **Demo Jobs:** all fictional opportunities with unchanged Job Match Scores,
   separate eligibility, relevance and preparation annotations. Search/filter/sort
   affects presentation only. Select a posting for its full title, component
   scores, job/candidate/configuration evidence, sparse-evidence warnings,
   limitations and advanced fingerprints. Illustrative example.test addresses are
   displayed as text, not links to employer application pages. UNKNOWN requires
   review; POLICY_EXCLUDED is a configured policy, not confirmed applicant
   ineligibility. Scores are heuristics, not admission probabilities.
3. **Application Tracker:** four existing fictional preparation records, their
   job associations and append-only history. Synthetic notes may be expanded only
   after full demo validation. Audit timestamps are under Advanced Details.
   There is no submission/status-change control or simulated successful application.
4. **General Resume:** current synthetic TXT fixture, evidence statuses and five
   exact before/after proposals. IDs, source anchors, qualifiers, limitations and
   uncertainties remain visible; the proposal fingerprint is under Advanced
   Details. CONFIRMED applies only within authored fiction; publication stays
   PENDING. Resume Apply is unavailable. DOCX parsing retains its narrow conservative
   subset; unsupported structures cannot be silently flattened or edited.

Counts and scores are derived from validated snapshots, not hardcoded UI metrics.
The existing ranking weights stay 30/30/25/15, with scores/order unchanged. Resume
proposals use the unchanged review engine and fingerprint. No raw JSON is displayed
in primary views and no resume/application write API is called.

## Read-only boundary and troubleshooting

CLI and dashboard share `DemoServices`: fixed path selection, the existing nine-
file hash allowlist, redirected-path refusal, read-only SQLite access and complete
demo validation. Only after schema/run/identity/payload verification are records
returned to the UI. Arbitrary, edited, old-schema, corrupt or incomplete databases
are refused without migration. The connection is closed before rendering. Every
user-triggered rerun loads/revalidates current inputs; no persistent data cache or
continuous polling is added. Session widget state is presentation only.

- **Missing demo:** use the explicit initializer above. No private path fallback.
- **Changed or corrupt input:** inspect the public fixture allowlist and disposable
  output. Do not weaken validation or copy private files to make a page load.
- **Busy/partial database:** stop writers and follow explicit recovery instructions.
  Sidecars, locks and partial output are refused, not silently removed.
- **Port unavailable:** stop the previous verified demo process or review which
  process owns the loopback port. The launcher does not kill another process or
  widen binding automatically.
- **Missing Streamlit:** install reviewed local packages into the public `.venv`;
  ask before any download. Do not launch with a private environment.
- **Theme/layout:** light and dark were visually inspected in the in-app browser's
  default narrow viewport. Native responsive layout stacks metrics/columns and
  tables scroll horizontally. This is not an exhaustive accessibility, browser or
  responsive-breakpoint certification.

Errors are fixed, human-readable messages rather than arbitrary exception or
record text. Framework local diagnostic output may appear in the launch terminal;
keep runtime output private. Generated data, runtime caches and validation
screenshots stay under ignored directories and are not public release artifacts.

## Verification and screenshot evidence

The complete unittest suite uses mocked services, temporary databases and authored
synthetic fixtures. Streamlit AppTest renders the pages without an HTTP server.
On Windows, its event loop uses standard-library loopback socket-pair IPC; guarded
tests permit only that internal channel and continue to reject external traffic.
No ATS/HTTP request is required for tests. Runtime OS version metadata uses a local
standard-library probe before launch guards are registered; it accesses no private
project data.

```powershell
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
$env:PYTHONDONTWRITEBYTECODE = '1'
& .\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

Real screenshots were captured locally with synthetic data only, in
`data/dashboard-validation/screenshots/`: overview-light/dark.jpg, jobs-light/dark.jpg,
tracker-light/dark.jpg, resume-light/dark.jpg and resume-proposals-light.jpg.
`contact-sheet.jpg` combines the eight page captures for inspection; it contains
scaled actual screenshots, not invented UI.
They are excluded from the reviewed release inventory. No fabricated screenshots
or private applicant material was used. The visible page assets inspected were
served locally; telemetry is disabled. Local browser transport is expected and
does not make this a live discovery system.

## Remaining release work

Approval-bound DOCX editing, immutable originals, fresh evidence/conflict checks,
render/layout verification and any resume Apply integration require a later
authorized step. Real applicant onboarding, general-user workflows, safe broader
integration coverage, broader real-applicant onboarding, compatibility beyond the
tested Windows source workflow, code/dependency provenance, license selection and
final publication approval remain outstanding. P4A verifies clean installation and
pins the tested Streamlit version without changing dashboard behavior. No Git
repository/remote, upload, public hosting or license was created. P4B's
[README](../README.md) documents supported onboarding; the [CI Guide](CI_GUIDE.md)
distinguishes local verification from unexecuted hosted CI.
