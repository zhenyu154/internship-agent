# Offline synthetic demonstration

SYNTHETIC DEMONSTRATION DATA — NOT REAL JOB POSTINGS.

P3A supplies one fictional candidate, ten authored fictional internship positions,
and four fictional application preparation records. No real person, employer,
posting, contact, research result, resume or application receipt is included.
Every illustrative URL uses `example.test`; do not visit or submit to these URLs.

## Contents

- `demo/fixtures/evidence/`: fictional education (computer science bachelor's
  degree, expected May 2028), skills and two toy projects. The three Markdown
  sources and `ranking_features.json` satisfy the existing candidate evidence
  interface, including hashes, anchors and simulation/generalization limitations.
  CONFIRMED and SUPPORTED labels apply only within the fictional fixture.
- `demo/fixtures/jobs.json`: robotics, machine learning, simulation, computer
  vision, perception, mechanical engineering and marketing examples. Cases cover
  unknown requirements, a fictional sponsorship restriction, PhD-only eligibility
  and a different internship term. Descriptions are original synthetic text.
- Four application records: NOT_STARTED, RESEARCHING, PREPARING and READY_TO_APPLY.
  These are fictional tracking states. No forms are prepared or submitted; no
  APPLIED record, submission confirmation, deadline verification or receipt exists.

The existing relevance backend produces four MAIN_SHORTLIST, three NEEDS_REVIEW
and three EXCLUDED classifications. MAIN_SHORTLIST describes role/cohort/location
signals, not confirmed candidate eligibility. Candidate work authorization remains
UNKNOWN. The initializer does not calculate ranking scores; the CLI and dashboard
rank these records separately through the generic evidence engine. Metadata uses
`SYNTHETIC_FIXTURE_NOT_VERIFIED`; there is no real source or board verification.

## Generate the local demo

Use Python 3.12 and this source tree's `.venv`. Follow the current
[README installation steps](../README.md) or [P4A procedure](CLEAN_INSTALL_VALIDATION.md)
to install all declared dependencies. P4A verifies Windows source/extracted-sdist
installation using reviewed cached wheels. The original P3A initializer needed
only PyYAML; that narrower historical check does not describe today's complete
test/dashboard requirements. Wheels are not bundled with the source.

From the staging root in PowerShell, with the prepared `.venv`:

```powershell
& .\.venv\Scripts\python.exe -B scripts/create_demo.py
```

The script loads only fixed fixtures and the public preference example, then
uses the existing JobDatabase schema and application backend. There are no custom
output/input path arguments, live ATS calls, browser actions or background tasks.
Do not point this staging project at private files to satisfy dependencies.

Successful output reports:

```text
SYNTHETIC DEMONSTRATION DATA — NOT REAL JOB POSTINGS.
Created data/demo/demo.sqlite3
Synthetic jobs: 10; synthetic application records: 4
SQLite integrity: ok; foreign-key violations: 0; schema version: 6
Fixture fingerprint: <SHA-256 of the reviewed fixtures and preference example>
```

The final database is validated before publication. Data, IDs, classifications,
application states and the fixture fingerprint repeat deterministically. Backend
creation/progress/history timestamps record the actual local run time, so database
bytes and audit timestamps are not promised to match across runs.

## Existing output and interruptions

An existing `data/demo/demo.sqlite3` or its sidecars causes refusal without opening
or overwriting it. There is no force/reset option. A partial run stays in
`data/demo/demo.building.sqlite3`, with committed jobs and work-item progress in
SQLite. The final filename appears only after validation, through atomic
publication that fails if that filename already exists.

After a normal interrupted run, explicitly recover it with:

```powershell
& .\.venv\Scripts\python.exe -B scripts/create_demo.py --resume
```

Recovery requires the same fixture fingerprint and an owned synthetic run using
the current schema. P3B.1 strengthens recovery with exact fresh-schema checks and
rejection of extra identity aliases or discovery checkpoint payloads. Unrelated
tables/triggers and older schemas are refused before writable access. Edited
run diagnostics or incomplete completed-item payloads also cause refusal. Changed
job data, metadata or application notes/statuses cause
refusal; manual edits are preserved. A hard process termination may leave
`data/demo/demo.lock`. After confirming no initializer is running and reviewing
the disposable output, remove only that stale lock before recovery:

```powershell
Remove-Item -LiteralPath .\data\demo\demo.lock
```

If fixtures changed, recovery is refused. Review and explicitly dispose of the
old synthetic output, then generate a fresh demo. Never use recovery on a real
database. Generated databases, sidecars and locks are excluded by `.gitignore`.

## Verify and remove disposable output

Run all available offline tests with temporary databases:

```powershell
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
$env:PYTHONDONTWRITEBYTECODE = '1'
& .\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

To remove the generated demo after inspection, confirm no initializer is running
and that the resolved path is this workspace's `data/demo` directory. Check that
the directory and its contents are not symlinks/junctions and contain only
disposable synthetic output; then run:

```powershell
Resolve-Path -LiteralPath .\data\demo
Get-ChildItem -LiteralPath .\data\demo -Force
Remove-Item -LiteralPath .\data\demo -Recurse
```

Never remove a general `data` directory or another workspace. `.venv/` and its
offline wheel cache are also ignored and are not public release artifacts.

## Deferred work

P3B.3A supplies a [small read-only public CLI](CLI_GUIDE.md) for status, jobs,
preparation records, unchanged ranking and synthetic resume proposals. The CLI
requires explicit final-demo database selection and performs no initialization,
recovery or other writes. The initializer remains authoritative.

P3B.3B supplies a [local public offline dashboard](DASHBOARD_DEMO_GUIDE.md).
The original personalized Dashboard, resume updater and full private interfaces
remain excluded. P3B.1 supplies an independently
authored [generic ranking backend](RANKING_GUIDE.md). This demo is a backend
initialization procedure, not a complete public application. P3B.2A adds a separate
[synthetic text-resume review fixture and proposal backend](RESUME_REVIEW_GUIDE.md).
It does not generate/edit DOCX or implement resume Apply. CLI/dashboard display
ranking and resume proposals for this fictional bundle; broader real-user/report/
writer integration remains deferred. The
ranking guide uses explicit relative fixture source labels, while the evidence
loader retains legacy logical `candidate/...` labels by default. Neither
labeling scheme establishes real applicant provenance.

The [README](../README.md) supplies current onboarding and [CI Guide](CI_GUIDE.md)
describes prepared offline verification. Broader integration coverage, safe
replacements for withheld cases, dependency/provenance review, license selection
and publication approval remain separate steps. No live boards, discovery
requests, submissions, remote, upload or license are introduced.
