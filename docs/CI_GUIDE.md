# Offline-test CI preparation (P4B)

The workflow at [`.github/workflows/offline-tests.yml`](../.github/workflows/offline-tests.yml)
is staged in a private repository. The first hosted run failed: 417 tests completed
with 4 failures and 189 errors, dominated by candidate-source integrity checks.
P5A.3 reproduced Windows LF-to-CRLF checkout conversion and adds only exact-path
[.gitattributes](../.gitattributes) rules for the ten reviewed inputs/manifest.
No passing hosted result is claimed until the corrective run is inspected. There
is no deployment, public repository, release or artifact upload.

## Workflow design and network boundary

One `windows-2022` job selects Python 3.12, creates `.venv`, installs the hash-locked
Windows dependencies, installs the source package and checks dependencies. It then
runs the complete public validation helper. `contents: read` is the only declared
GitHub token permission; checkout credentials are not persisted. There are no
repository secrets, scheduled triggers, privileged pull-request triggers, cache
or artifact uploads, deploy steps or external ATS calls.

P4B used version tags. P4C.2A verified the official GitHub tag-ref JSON and
commit-pinned action.yml files over HTTPS, then retained the versions while pinning:

- `actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683` (v4.2.2)
- `actions/setup-python@42375524e23c412d93fb67b49958b491fce71c38` (v5.4.0)

Readable comments remain. The first sandbox requests were blocked, but the approved
narrow read-only verification returned HTTP 200 and supplied both exact identities.
This resolves tag mutability, not a full bundled-code/security audit or a latest-
version claim. Hosted execution remains unverified. Evidence and remaining limits
are in the local COMPLIANCE_REMEDIATION.md report, excluded from release pending review.

Future hosted checkout/Action setup and dependency installation require network
access. The dependency step explicitly contacts PyPI with `--require-hashes` and
`--only-binary=:all:` using `requirements/windows-py312.lock`; the subsequent
editable source install has `--no-index` and resolves the installed dependencies.
This is separate from application verification: synthetic data/tests never call
ATS or other external services. Package-index availability of every locked wheel,
Windows Server 2022 behavior and the setup Action's selected Python patch version
are **not independently verified**. P4A's actual baseline remains Windows 11,
Python 3.12.10 and local cached wheels. Do not interpret YAML preparation as a
passed internet-based clean installation.

## Local validation helper

[`scripts/verify_public_demo.py`](../scripts/verify_public_demo.py) is a manual test
coordinator, not a runtime integration. Run it from the installed source checkout
using that checkout's `.venv`:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
& .\.venv\Scripts\python.exe -B scripts/verify_public_demo.py
if ($LASTEXITCODE -ne 0) { throw 'Offline public verification failed.' }
```

The coordinator calls only its current interpreter/pip and two validation workers:

1. `pip check` confirms installed requirements without an index.
2. The guarded worker runs the entire `unittest` suite, with no skipped cases.
   Its process-lifetime audit boundary rejects external sockets/DNS/subprocesses,
   unexpected reads and writes outside its newly-created synthetic temporary tree.
   Only trusted Windows standard-library socket-pair IPC is permitted for AppTest.
3. It copies eleven individually reviewed synthetic/runtime files to a temporary
   root and invokes the existing initializer there. Source/backend imports remain
   in the reviewed checkout; there is no recursive source or private-file copy.
4. Help, all five CLI commands and selected-job ranking run through the same public
   handlers. It checks SQLite schema/integrity/counts, unchanged scores/proposals,
   no-overwrite/resume refusals and read-only input hashes. It never opens the
   checkout's existing `data/demo` database.
5. A disposable exact-inventory source copy is built with the installed setuptools
   backend. Source/wheel contents are checked against reviewed filenames and bytes.
   Invented ignored `.env`, secrets, candidate, database and log canaries must stay
   excluded. The complete source archive contains reviewed files plus only three
   generated metadata files; the wheel retains its code-only boundary.
6. A separate worker starts and immediately stops native Streamlit through the
   unchanged safe launcher using its existing testing hook. Original loopback,
   configuration and audit protections remain active; zero blocked attempts are
   required. This is startup/shutdown verification, not a real browser walkthrough.
   The full suite covers all four pages through Streamlit AppTest; actual browser
   inspection and Ctrl+C delivery limitations are documented in P4A.

The temporary tree is created under ignored `data/ci-verification/` and only that
verified task-owned subtree is removed. Package inputs come from the release
inventory, not a general file glob or `.gitignore` alone. No artifact leaves the
runner. Audit checks are Python-level scoped validation, not an OS-wide sandbox.

## Verification record

P4A passed 409 public tests in a clean extracted-source environment. P4B's final
local CI-equivalent run passed **414 tests: all 409 prior tests plus 5 documentation/
CI regressions**, zero failures/errors/skips. pip check, fresh synthetic CLI smoke,
90-file source/wheel inspection and native guarded startup/shutdown passed.
Audit counters were **0 network, 0 external input, 0 protected writes**; 58 trusted
Windows standard-library socket-pair operations supported AppTest. All loaded
application modules came from the clean copy's src/. The first coordinator attempt
failed test discovery because its scripts entry point omitted the tests package;
explicit top-level discovery fixed it without changing existing tests/backend.
README/CI PowerShell examples and all five workflow run blocks parse locally.
Local Markdown file links resolve; external links and GitHub rendering were not
checked online. Further results are recorded in
[PUBLIC_RELEASE_MANIFEST.md](../PUBLIC_RELEASE_MANIFEST.md).
Final link inspection resolved **50 local Markdown file links**. Both Python
examples in the ranking and resume-review guides executed using their explicit
synthetic fixtures; their read-only audit counters were all zero. Console help
was also executed. The `py -3.12` convenience spelling, interactive Read-Host path
prompt, package-index commands and hosted Action steps were not independently
executed; PowerShell syntax parsing is not execution evidence.
The exact README source-install command (`--no-index --no-build-isolation -r
requirements.txt`) was also executed from the clean source root with its locked
dependencies already present. Editable installation, pip check and the import-path
check passed; this is a source reinstall, not another fresh or online installation.
The prior 104 private tests remain withheld. Hosted triggers, Actions downloads,
package-index installation and GitHub-specific YAML execution had not run at P4B.
The first private hosted run subsequently installed dependencies and passed pip
check, then failed 417 tests with 4 failures/189 errors. P5A.3 reproduces that exact
result in a real core.autocrlf=true checkout. All nine hash-listed inputs converted
from LF to CRLF; the three candidate Markdown sources failed source_sha256 first,
and initialization-dependent tests failed before reaching their intended checks.

The correction adds ten exact `text eol=lf` path rules: nine byte-reviewed fixture/
config inputs plus the offline hash manifest. There is no blanket normalization,
fingerprint regeneration or loader change. Local core.autocrlf=false had preserved
the original LF bytes, explaining the earlier passing local suite. Fresh Windows-
style checkout reproduction passes 418 tests (all prior 417 plus one regression),
zero failures/errors/skips. Synthetic smoke, hashes, rankings/proposals, packaging
and MIT checks pass with zero audit violations; other files remain CRLF in that
checkout. Git may reuse existing stat-clean files, so diagnosis rematerialized only
the ten protected paths in a disposable checkout. No actual evidence file was
rewritten. Hosted success still requires inspection of the new corrective run;
local results do not prove GitHub is fixed.

## Screenshots requiring separate approval

The following existing captures are candidates only. They remain ignored and
outside the release inventory; no public image assets or README screenshots were
added. Relative paths are from the source root.

| Candidate | Use | Review considerations |
|---|---|---|
| `data/dashboard-validation/screenshots/overview-light.jpg` | Main workflow overview | Synthetic notice/counts; narrow original viewport |
| `data/dashboard-validation/screenshots/jobs-light.jpg` | Ranking and separate eligibility | Fictional job and score details; verify evidence text remains legible |
| `data/dashboard-validation/screenshots/tracker-light.jpg` | Preparation history | Invented notes/history only; inspect timestamps before publishing |
| `data/dashboard-validation/screenshots/resume-proposals-light.jpg` | Exact proposal and limitations | Top synthetic banner is out of frame and intentionally unsupported resume claims are visible; needs explicit synthetic-review caption/context |
| `data/dashboard-validation/screenshots/contact-sheet.jpg` | Compare eight light/dark page captures | Composed from actual screenshots; small text unsuitable as the main README image |
| `data/clean-install-p4a/dashboard-resume-clean.jpg` | Clean-source review evidence | Synthetic TXT and read-only notice; narrow cropped viewport |

Corresponding `*-dark.jpg` and `resume-light.jpg` originals also exist. Check each
selected image's pixels/metadata, source authenticity and wording immediately
before approving it. A synthetic fixture can contain intentionally unsupported
claims for review; do not crop away the evidence-review context or imply real
results. Copy only specifically approved images into a separately reviewed asset
allowlist. Do not publish an ignored runtime directory wholesale.
P4B inspected the contact sheet and the proposal capture, and checked metadata on
all eleven existing JPEGs: no EXIF fields were present, only ordinary JFIF fields.
The page captures are 589 x 859 pixels; the contact sheet is 720 x 2040. This is a
local review, not blanket approval or a guarantee for future images.

## Remaining boundaries

Windows/Python 3.12 source workflow is supported as documented. Linux remains
UNVERIFIED because the available Ubuntu lacked ensurepip and matching cached
compiled wheels. macOS/other versions are untested. The standalone wheel does not
contain the complete demo. Current onboarding is in the [README](../README.md),
and exact clean-install evidence is in [the P4A report](CLEAN_INSTALL_VALIDATION.md).

Publication still requires license/notice/provenance approval, safe broader
integration coverage and final human review. Screenshots need separate approval.
No live discovery, submission, Resume Apply, runtime feature, Git repository,
remote, upload or license was introduced. Stop after P4B.

P4C.2B subsequently applies the complete first-party MIT [LICENSE](../LICENSE),
with Copyright (c) 2026 Zhenyu Wu. Dependencies retain their own terms; no dependency
wheels/assets or internal compliance reports are added to release artifacts. The
inventory is now 91 files. The packaging helper checks License-Expression: MIT,
License-File: LICENSE and identical license bytes in sdist and wheel. The wheel
still excludes demo inputs and contains code plus metadata/license only. Modern
license metadata uses the already-tested setuptools 84 backend; the build floor
is now >=84 while the exact Windows lock remains unchanged at 84.0.0. Final P4C.2B
test results and remaining publication gates are recorded in the release manifest.
