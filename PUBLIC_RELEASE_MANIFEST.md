# Public Release Manifest: P2 Baseline through P5A.3

The sanitized development tree remains local; a separate reviewed release candidate
has one approved root commit staged privately on GitHub. The first hosted run failed
byte-sensitive fixture validation; P5A.3 records its narrowly scoped repair below.
No public publication or visibility change is authorized. This is an incomplete demo.
Only explicitly reviewed files were included; the original private tree was not
recursively copied or modified. Repository-relative paths are used throughout.

## Included file inventory

Reviewed public file count: **92**, including this manifest: 49 P2 files plus
9 P3A, 4 P3B.1, 7 P3B.2A, 5 P3B.3A, 8 P3B.3B, 4 P4A, 4 P4B, the P4C.2B LICENSE
and the P5A.3 exact-path .gitattributes file.
The local `.venv/`, generated package metadata/build output and all `data/` validation
material are excluded from this inventory and from any eventual public repository.
Source archives add only the three public build-generated metadata files documented
in the P4A report; no existing egg-info/environment directory is release input.
The wheel retains its 32 application modules plus five dist-info metadata files
and the approved MIT text at `dist-info/licenses/LICENSE`; it contains no demo assets.

The local audit/review documents `docs/LICENSE_PROVENANCE_AUDIT.md` (P4C.1) and
`docs/COMPLIANCE_REMEDIATION.md` (P4C.2A) are outside this 92-file release allowlist.
Retain them locally for review; including sanitized compliance documentation in a
future public repository needs an explicit inventory decision. No report, local
package metadata or wheel tree is automatically copied into public assets.

| File | Original category | Staging treatment |
|---|---|---|
| `.gitignore` | New privacy protection | Public exclusions plus P4A exact exception for the reviewed Windows dependency lock; privacy also enforced by allowlist |
| `.gitattributes` | New P5A.3 CI-integrity protection | Ten exact LF checkout rules for hash-bound synthetic inputs/manifest; no global normalization or evidence changes |
| `.github/workflows/offline-tests.yml` | New P4B prepared Windows CI | P4C.2A pins verified official v4.2.2/v5.4.0 commits; read token permission, hash-locked install and offline synthetic checks preserved; hosted run unverified |
| `.streamlit/config.toml` | New P3B.3B reviewed local configuration | Loopback/headless/manual settings; telemetry/file watching/static serving disabled; no secrets |
| `AGENTS.md` | New sanitized engineering instructions | Preserves safety conventions; records P3B.3B read-only local Dashboard authorization |
| `LICENSE` | New P4C.2B MIT license | Complete standard MIT text; Copyright (c) 2026 Zhenyu Wu; first-party material only |
| `MANIFEST.in` | New P4A explicit source-archive allowlist | Includes exactly the 92 reviewed release files through P5A.3; runtime/private/ignored data excluded independently of .gitignore |
| `PUBLIC_RELEASE_MANIFEST.md` | New release documentation | New exact inventory and validation record |
| `README.md` | New English public presentation | P4B Windows-first onboarding, capabilities/limits, architecture, privacy/human control and AI attribution; online/hosted checks unverified |
| `config/ashby_boards.example.yaml` | New empty registry example | No live board identities, ownership claims or timestamps |
| `config/greenhouse_boards.example.yaml` | New empty registry example | No live board identities, ownership claims or timestamps |
| `config/lever_sites.example.yaml` | New empty registry example | No live board identities, ownership claims or timestamps |
| `config/search_preferences.example.yaml` | Reviewed existing preferences example | Illustrative graduation/employer values; no active local settings copied |
| `pyproject.toml` | Reviewed packaging metadata | MIT license expression/exact LICENSE file added in P4C.2B; tested Streamlit pin, code-only wheel and safe CLI entry preserved |
| `requirements.txt` | Reviewed dependency declaration | Editable source-checkout install; removes duplicate broad Streamlit declaration and references Windows lock procedure |
| `requirements/windows-py312.lock` | New P4A tested dependency snapshot | 40 exact cached wheel versions/SHA-256 hashes for Windows AMD64 and CPython 3.12, including the build tool |
| `demo/fixtures/jobs.json` | New P3A authored synthetic fixture | Ten fictional positions and four fictional preparation records; reserved example.test URLs |
| `demo/fixtures/offline_cli_manifest.json` | New P3B.3A reviewed integrity metadata | Exactly nine fixed synthetic fixture/config paths and hashes; no private inputs or path discovery |
| `demo/fixtures/evidence/profile.md` | New P3A authored synthetic fixture | One fictional candidate, institution and education; no contact or real applicant data |
| `demo/fixtures/evidence/experience_bank.md` | New P3A authored synthetic fixture | Two toy projects; no real research results or physical deployment claims |
| `demo/fixtures/evidence/verification_report.md` | New P3A authored synthetic fixture | Evidence labels explicitly apply only within the fictional fixture |
| `demo/fixtures/evidence/ranking_features.json` | New P3A authored synthetic fixture | Existing version-1 evidence interface, five generic features, source hashes and anchors |
| `demo/fixtures/resume_review/general_resume.txt` | New P3B.2A authored synthetic fixture | General text resume with deliberately unsupported claims; no real applicant input |
| `demo/fixtures/resume_review/observations.md` | New P3B.2A authored synthetic fixture | Fictional reviewed canonical statements and experimental limitations; invented toy count is not a real result |
| `demo/fixtures/resume_review/claims.json` | New P3B.2A authored synthetic fixture | Six source-anchored claim records and five exact-text proposal rules; bound to existing candidate evidence hashes |
| `docs/DEMO_GUIDE.md` | New P3A English documentation | P3B.1 updates recovery safeguards and the current ranking/integration boundary |
| `docs/RANKING_GUIDE.md` | New P3B.1 English documentation | Generic evidence contract, scoring formulas, source citations, fictional scores and limitations |
| `docs/RESUME_REVIEW_GUIDE.md` | New P3B.2A English documentation | Explicit-input workflow, exact proposals, evidence states, limited DOCX support and deferred editing/approval |
| `docs/CLI_GUIDE.md` | New P3B.3A English documentation | Console/module commands, selection/refusal rules and outputs; P4A link supersedes the narrower historical installation check |
| `docs/DASHBOARD_DEMO_GUIDE.md` | New P3B.3B English documentation | Manual launch/shutdown, four pages and isolation; P4A clean-source install, exact Streamlit pin and Linux limits |
| `docs/CLEAN_INSTALL_VALIDATION.md` | New P4A English validation report | Clean source/sdist/wheel installation evidence, exact versions, offline procedure and platform limits |
| `docs/CI_GUIDE.md` | New P4B English documentation | Hosted CI preparation versus local verification, workflow boundaries and ignored screenshot candidates awaiting approval |
| `scripts/create_demo.py` | New P3A standalone entry point | Explicit offline initialization or --resume; no full CLI restoration |
| `scripts/run_dashboard.py` | New P3B.3B manual launcher | Public checkout/public .venv only; foreground local server; no startup or background integration |
| `scripts/verify_public_demo.py` | New P4B manual validation helper | Full tests/audit guard, temporary reviewed synthetic smoke, exact archive checks and native guarded loopback startup/shutdown; no new application behavior |
| `src/internship_agent/__init__.py` | Reviewed generic Python source | P3B.3A suppresses future runtime bytecode writes for the read-only staging demo; Python/version semantics unchanged |
| `src/internship_agent/__main__.py` | New P3B.3A entry point | Independently authored manual module entry to the five-command offline CLI |
| `src/internship_agent/application_report.py` | Reviewed generic Python source | Reviewed copy; source text unchanged |
| `src/internship_agent/applications.py` | Reviewed generic Python source | Reviewed copy; source text unchanged |
| `src/internship_agent/ashby.py` | Reviewed generic Python source | Reviewed copy; source text unchanged |
| `src/internship_agent/ashby_discovery.py` | Reviewed generic Python source | Reviewed copy; source text unchanged |
| `src/internship_agent/candidate_evidence.py` | Reviewed generic Python source | P3B.1 adds safe relative reference labels, limitation references, uniqueness checks and empty unknown claim sets; hashes/positive anchors retained |
| `src/internship_agent/cli.py` | New P3B.3A thin handlers | P3B.3B delegates input/ranking/resume calls to shared DemoServices; original commands/numerical results preserved |
| `src/internship_agent/company_discovery.py` | Reviewed generic Python source | Reviewed copy; source text unchanged |
| `src/internship_agent/config.py` | Reviewed generic Python source | Reviewed copy; source text unchanged |
| `src/internship_agent/database.py` | Reviewed generic Python source | Read-only integrity/layout/identity inspection APIs; schema and existing write behavior unchanged |
| `src/internship_agent/dashboard_app.py` | New P3B.3B thin presentation | Four local synthetic pages, filters/details/evidence; no database writes, editing, Apply or submission |
| `src/internship_agent/dashboard_services.py` | New P3B.3B snapshot adapter | Independently authored read-only validated snapshots and presentation filtering; no original private module copied |
| `src/internship_agent/dashboard_launch.py` | New P3B.3B runtime adapter | Explicit loopback-only manual launch, workspace config/no secrets, telemetry disabled and runtime audit guard |
| `src/internship_agent/demo.py` | New P3A initialization service | P3B.3A adds shared read-only complete-demo validation; initializer/recovery/no-overwrite logic retained |
| `src/internship_agent/demo_services.py` | New P3B.3B shared public services | Extracts existing CLI selection/allowlist safeguards and backend calls for both CLI and Dashboard |
| `src/internship_agent/deduplication.py` | Reviewed generic Python source | Reviewed copy; source text unchanged |
| `src/internship_agent/discovery.py` | Reviewed generic Python source | Reviewed copy; source text unchanged |
| `src/internship_agent/exports.py` | Reviewed generic Python source | Reviewed copy; source text unchanged |
| `src/internship_agent/greenhouse.py` | Reviewed generic Python source | Reviewed copy; source text unchanged |
| `src/internship_agent/lever.py` | Reviewed generic Python source | Reviewed copy; source text unchanged |
| `src/internship_agent/lever_discovery.py` | Reviewed generic Python source | Reviewed copy; source text unchanged |
| `src/internship_agent/models.py` | Reviewed generic Python source | Reviewed copy; source text unchanged |
| `src/internship_agent/public_http.py` | Reviewed generic Python source | Reviewed copy; source text unchanged |
| `src/internship_agent/ranking_job_evidence.py` | Reviewed generic Python source | Reviewed copy; source text unchanged |
| `src/internship_agent/ranking.py` | New P3B.1 generic engine | Independently authored pure ranking functions; no original personalized engine copied/imported |
| `src/internship_agent/ranking_locations.py` | Reviewed generic Python source | P3B.1 handles valid preference subsets conservatively; no location-based eligibility rejection |
| `src/internship_agent/registry_metadata.py` | Reviewed generic Python source | Reviewed copy; source text unchanged |
| `src/internship_agent/relevance.py` | Reviewed generic Python source | Reviewed copy; source text unchanged |
| `src/internship_agent/resume_review.py` | New P3B.2A generic backend | Read-only bounded TXT/conservative DOCX extraction, explicit evidence loading and pure proposals; no editing/approval/Apply |
| `src/internship_agent/unified_discovery.py` | Reviewed generic Python source | Reviewed copy; source text unchanged |
| `src/internship_agent/unified_report.py` | Reviewed generic Python source | Reviewed copy; source text unchanged |
| `tests/__init__.py` | Reviewed synthetic/offline tests | Reviewed copy; source text unchanged |
| `tests/fixtures/ashby_boards.yaml` | New synthetic-only test registry | Replaces original real registry fixture; no real source evidence |
| `tests/fixtures/greenhouse_boards.yaml` | New synthetic-only test registry | Replaces original real registry fixture; no real source evidence |
| `tests/fixtures/lever_sites.yaml` | New synthetic-only test registry | Replaces original real registry fixture; no real source evidence |
| `tests/fixtures/resume_paragraphs.xml` | New P3B.2A authored synthetic fixture | Minimal paragraph/run OOXML for in-memory extraction tests; no delivered or generated resume DOCX |
| `tests/test_applications.py` | Reviewed synthetic/offline tests | Public-only test sanitization; see detailed change list |
| `tests/test_ashby.py` | Reviewed synthetic/offline tests | Public-only test sanitization; see detailed change list |
| `tests/test_company_discovery.py` | Reviewed synthetic/offline tests | Public-only test sanitization; see detailed change list |
| `tests/test_config.py` | Reviewed synthetic/offline tests | Public-only test sanitization; see detailed change list |
| `tests/test_database.py` | Reviewed synthetic/offline tests | Reviewed copy; source text unchanged |
| `tests/test_deduplication.py` | Reviewed synthetic/offline tests | Reviewed copy; source text unchanged |
| `tests/test_demo.py` | New P3A synthetic/offline tests | 30 tests using temporary databases and authored public fixtures only |
| `tests/test_demo_safety.py` | New P3B.1 synthetic/offline tests | 9 adversarial demo-recovery tests; unrelated/extended databases remain unchanged |
| `tests/test_execution_state.py` | Reviewed synthetic/offline tests | Public-only test sanitization; see detailed change list |
| `tests/test_exports.py` | Reviewed synthetic/offline tests | Reviewed copy; source text unchanged |
| `tests/test_greenhouse.py` | Reviewed synthetic/offline tests | Public-only test sanitization; see detailed change list |
| `tests/test_generic_ranking.py` | New P3B.1 synthetic/offline tests | 41 independently authored ranking/evidence/privacy tests; no withheld tests copied |
| `tests/test_lever.py` | Reviewed synthetic/offline tests | Public-only test sanitization; see detailed change list |
| `tests/test_models.py` | Reviewed synthetic/offline tests | Reviewed copy; source text unchanged |
| `tests/test_public_cli.py` | New P3B.3A synthetic/offline tests | 38 argument/selection/listing/ranking/proposal/read-only/privacy/failure integrations; no withheld tests copied |
| `tests/test_public_dashboard.py` | New P3B.3B synthetic/offline tests | 33 service/AppTest/UI/runtime-boundary regressions; only temporary databases and authored fixtures |
| `tests/test_packaging.py` | New P4A standard-library regressions | Prior 7 checks plus P5A.3 exact LF rules and unchanged-fixture hashes; integrity assertions preserved |
| `tests/test_public_documentation.py` | New P4B documentation/CI checks | Five existing tests; pin assertion updated to verified official full commits; permissions, synthetic inputs and guard checks retained |
| `tests/test_resume_review.py` | New P3B.2A synthetic/offline tests | 47 source/extraction/proposal/structure/privacy regressions; no withheld tests copied |
| `tests/test_unified_discovery.py` | Reviewed synthetic/offline tests | Public-only test sanitization; see detailed change list |

## Strict exclusions

Entire original candidate/, resumes/, data/, reports/, logs/ and candidate/_sources/
contents are excluded. No candidate/profile.md, candidate/experience_bank.md,
candidate/verification_report.md, candidate/ranking_features.json, resume proposal
or approval state, personal evidence snapshot, application notes/receipts, real
SQLite database/backup/sidecar, resume document or screenshot is included.

Also excluded: .venv/, all Python caches, *.egg-info/, build outputs, local settings,
secrets/session files, .git/ and nested Git histories. Original README.md, AGENTS.md,
docs/ guides, audit reports and active config/*.yaml registries were not copied.
Only the reviewed preference example was used as a template; real preferences
and active ATS identities/provenance were excluded.

All original tests/fixtures files were individually inspected. The original
registry YAML fixtures referenced real company tokens and verification timestamps;
none were copied. New fictional test registries replace them. The entire
`tests/fixtures/greenhouse_original_regressions.json` fixture is excluded because
it contains full real third-party descriptions and identifying URLs.

## Original withheld source and interfaces

| File | Reason |
|---|---|
| Original personalized `src/internship_agent/ranking.py` | Still excluded and never accessed/copied in P3B.1; a new generic public module now occupies this path |
| `src/internship_agent/resume_check.py` | Personal research/repository/publication logic requires generalization |
| `src/internship_agent/ranking_report.py` | Dependent reporting/API integration remains withheld |
| Original personalized `src/internship_agent/cli.py` | Still excluded; P3B.3A independently authors a small synthetic-only public CLI at this path |
| Original `src/internship_agent/__main__.py` | Never copied; P3B.3A supplies a new safe module entry |
| Original personalized `src/internship_agent/dashboard_services.py` | Still excluded; P3B.3B independently authors a public read-only adapter at this path |
| Original personalized `src/internship_agent/dashboard_app.py` | Still excluded; P3B.3B independently authors the public synthetic presentation at this path |
| `Start Internship Agent.cmd` | Manual launcher reviewed; withheld because dashboard cannot run |
| `Start Internship Agent.ps1` | Manual loopback launcher reviewed; withheld because dashboard cannot run |

## Public-only changes (P2 baseline)

- All 23 included Python backend modules preserve their reviewed source text.
  No database schema, identity rule, application transition or backend logic changed.
  Files are stored as UTF-8 with LF newlines. Eight included source modules had
  only line-ending normalization: `src/internship_agent/models.py`, `src/internship_agent/database.py`, `src/internship_agent/applications.py`, `src/internship_agent/application_report.py`, `src/internship_agent/config.py`, `src/internship_agent/candidate_evidence.py`, `src/internship_agent/ranking_locations.py`, `src/internship_agent/ranking_job_evidence.py`.
- pyproject.toml removes the console script for the withheld CLI. Dependencies and
  Python version requirements remain unchanged; no package was installed.
- The preference example labels values as illustrative, changes the example
  graduation month and resets the employer-operations preference to a neutral value.
  Work authorization remains UNKNOWN; manual execution and human final action remain.
- Three config registry examples are empty. They assert no company ownership,
  live verification, token validity or audit timestamp.
- Three test-only registry fixtures use fictional company/token identities and
  clearly labeled artificial timestamps. Mock tests never contact their ATS URLs.
- Included tests point to the safe preference example, replace real company/token
  identifiers with matching fictional identities, and replace local audit-date
  literals with artificial fixture dates. A copied test method/class is removed
  only when blocked by an excluded dependency or the excluded third-party fixture.
  The exact omitted coverage is recorded below; no failed test is hidden as passing.
- AGENTS.md, .gitignore, minimal README.md and this manifest are newly written
  English staging documentation. The original guides remain untouched.

## Available offline test coverage (P2 baseline)

Original source inventory: **311 test methods**. Available staging inventory:
**207 test methods**. **104 original methods are withheld**, not passed or skipped.
No new demo data, candidate bundle or product feature was implemented.

| Runnable module | Tests |
|---|---:|
| `tests/test_applications.py` | 36 |
| `tests/test_ashby.py` | 6 |
| `tests/test_company_discovery.py` | 29 |
| `tests/test_config.py` | 15 |
| `tests/test_database.py` | 20 |
| `tests/test_deduplication.py` | 10 |
| `tests/test_execution_state.py` | 12 |
| `tests/test_exports.py` | 5 |
| `tests/test_greenhouse.py` | 17 |
| `tests/test_lever.py` | 7 |
| `tests/test_models.py` | 5 |
| `tests/test_unified_discovery.py` | 45 |

### Entire withheld test modules

| Module | Tests | Required follow-up |
|---|---:|---|
| `tests/test_cli.py` | 4 | CLI withheld; restore integration coverage after safe interfaces exist |
| `tests/test_ashby_audit_completion.py` | 17 | Contains source-derived third-party responsibilities; needs original synthetic replacement plus CLI restoration |
| `tests/test_ranking.py` | 20 | Depends on real candidate evidence and personalized project mapping; needs synthetic candidate and generic ranking engine |
| `tests/test_resume_check.py` | 7 | Contains personal identifiers and research scenarios; needs synthetic resume/repository evidence and generic review engine |
| `tests/test_resume_update.py` | 11 | Resume approval engine withheld; synthetic update cases must be revalidated once restored |
| `tests/test_dashboard.py` | 11 | Private candidate dependency plus withheld dashboard services; needs synthetic evidence |
| `tests/test_dashboard_polish.py` | 18 | Dashboard services withheld; safely runnable public UI needed before restoring coverage |

### Individually withheld integration/fixture cases

| Original module | Test | Reason |
|---|---|---|
| `tests/test_config.py` | `ConfigCliTests.test_valid_cli_invocation` | CLI depends on withheld personalized modules |
| `tests/test_config.py` | `ConfigCliTests.test_invalid_cli_invocation_returns_nonzero` | CLI depends on withheld personalized modules |
| `tests/test_execution_state.py` | `ExecutionCliTests.test_cli_run_start_status_interrupt_resume_and_complete` | CLI depends on withheld personalized modules |
| `tests/test_execution_state.py` | `ExecutionCliTests.test_cli_help_describes_execution_commands` | CLI depends on withheld personalized modules |
| `tests/test_greenhouse.py` | `DiscoveryPersistenceTests.test_reclassifies_the_eight_saved_greenhouse_positions_without_deleting_jobs` | Real third-party fixture needs synthetic replacement |
| `tests/test_unified_discovery.py` | `UnifiedTests.test_cli_help_documents_manual_selection_and_limits` | CLI depends on withheld personalized modules |
| `tests/test_unified_discovery.py` | `UnifiedTests.test_cli_dry_run_cannot_also_save` | CLI depends on withheld personalized modules |
| `tests/test_applications.py` | `TrackerCliTests.test_cli_preparation_and_history` | CLI depends on withheld personalized modules |
| `tests/test_applications.py` | `TrackerCliTests.test_cli_requires_confirmation_and_date` | CLI depends on withheld personalized modules |
| `tests/test_applications.py` | `TrackerCliTests.test_cli_submission_and_follow_up` | CLI depends on withheld personalized modules |
| `tests/test_applications.py` | `TrackerCliTests.test_cli_rejects_applied_via_generic_command_and_invalid_date` | CLI depends on withheld personalized modules |
| `tests/test_applications.py` | `TrackerCliTests.test_cli_listing_filters_and_show_are_read_only` | CLI depends on withheld personalized modules |
| `tests/test_applications.py` | `TrackerCliTests.test_cli_notes_deadline_and_report` | CLI depends on withheld personalized modules |
| `tests/test_applications.py` | `TrackerCliTests.test_cli_unknown_job_and_invalid_status_have_readable_errors` | CLI depends on withheld personalized modules |
| `tests/test_applications.py` | `TrackerCliTests.test_help_has_human_only_semantics_and_no_database_writes` | CLI depends on withheld personalized modules |
| `tests/test_applications.py` | `TrackerCliTests.test_all_tracker_commands_make_no_network_requests` | CLI depends on withheld personalized modules |

## Validation results (P2 baseline)

- **207 tests passed**, 0 failures, 0 errors, 0 skipped (Python 3.12.10).
  Only the 207 available staging tests were executed. The 104 withheld original
  cases were not executed and are not counted as passes.
- Tests used the existing local Python environment without installing dependencies.
  Package-origin checks verified all 20 loaded application modules came from
  this tree's src/. No editable-install fallback to private source was used.
- Runtime audit guards blocked network operations, private-project input reads
  and writes/mutations to either project tree. Observed attempts: **0 network,
  0 private input reads, 0 protected writes**. Tests used temporary databases.
  Staging hashes were identical before and after the test run.
- All four YAML templates passed parsing and the existing backend loaders. Each
  ATS template loaded zero entries. Weights total 100; execution is manual;
  scheduler and auto-start are false; work authorization is UNKNOWN;
  auto-submit is false and final submission requires human action.
- Recursive path/content screening found **0 unresolved findings**. No excluded
  directory, private document, database/backup, image, cache, environment, symlink
  or .git directory was included. The exact 49-file allowlist was verified.
- Content checks covered personal identifiers and contacts, absolute local paths,
  credential/token/key patterns, and identifying URLs/substantial contiguous text
  from the excluded real-job fixture. Five contact/URL-pattern occurrences were
  reviewed as synthetic example-domain or credential-rejection test inputs.
  No real credential or contact data was found. This local scan is not a formal
  license review, independent secret-scanner certification or clean-install test.
- SHA-256/size comparison of **all 10,724 original files**, including ignored
  candidate inputs, environment files and outer/nested Git metadata, found **0
  changed, 0 added and 0 removed**. Original job database and both original
  resume hashes are unchanged. No original candidate records were modified.
- No Git repository initialization, remote creation, GitHub action, upload,
  live discovery, application submission, scheduler or service execution occurred.


## Step P3A implementation and validation

P3A was explicitly authorized after the P2 handoff. Work used only this public
workspace, authored synthetic fixtures and an isolated public environment. No
original private source, test, environment, database or resume was read or copied.

- Added nine public files listed above; modified AGENTS.md, README.md,
  PUBLIC_RELEASE_MANIFEST.md and database.py. All original 207 public tests and
  existing test fixtures are unchanged. Dependency declarations, configuration,
  identity rules, application transitions and SQLite schema version 6 are unchanged.
- The fictional candidate has a computer science bachelor's education with
  expected graduation May 2028, five generic supported fixture features and two
  toy projects: grid navigation and shape classification. Source hashes and
  anchors validate through the existing evidence loader. No ranking, resume
  document or resume-update workflow is implemented. Logical `candidate/...`
  references from that interface are labels, not private input paths or verified
  applicant provenance; downstream integration remains deferred.
- Ten original fictional descriptions cover robotics, machine learning,
  simulation, vision, unknown requirements, a fictional sponsorship restriction,
  PhD-only eligibility, another internship term and less relevant examples. All
  URLs use example.test. The existing relevance backend produces four
  MAIN_SHORTLIST, three NEEDS_REVIEW and three EXCLUDED records; these are role
  classifications, not confirmed candidate eligibility. Work authorization
  remains UNKNOWN. Metadata explicitly says SYNTHETIC_FIXTURE_NOT_VERIFIED.
- Four fictional application records occupy NOT_STARTED, RESEARCHING, PREPARING
  and READY_TO_APPLY states. Notes/history are labeled synthetic. There is no
  APPLIED record, submission confirmation, receipt, real form preparation or
  deadline verification.
- The standalone command is `& .\.venv\Scripts\python.exe -B scripts/create_demo.py`.
  It creates `data/demo/demo.sqlite3` only after successful validation. Existing
  final databases/sidecars are refused without opening or overwriting them.
  Interrupted progress remains in `data/demo/demo.building.sqlite3`; explicit
  --resume validates ownership, fixture fingerprint and existing records before
  continuing. Edited records/notes/statuses and unrelated databases are refused.
  A stale lock requires human review. See docs/DEMO_GUIDE.md for disposal.
- Fixtures, IDs, classifications, notes and states are deterministic. SQLite
  audit timestamps record the actual run time; database bytes are not promised
  to match. No preferences contain run state. No separate demo schema was added.
- A new ignored `.venv/` uses Python 3.12.10 and PyYAML 6.0.3, installed from a
  locally cached wheel with --no-index and --no-deps. No package download or new
  dependency declaration occurred. PDF/UI dependencies were not needed or
  installed. This is P3A environment validation, not a clean full-package install.
- **237 tests passed: 207 preserved tests plus 30 new P3A tests; zero failures,
  errors or skips.** The 104 withheld original cases remain withheld and are not
  counted as passes or restored coverage. Tests cover fixture/evidence validity,
  model compatibility, integrity, deterministic logical data, overwrite refusal,
  publication races, interruption recovery, private/network input restrictions
  and unchanged application transition/confirmation safeguards.
- The actual initializer smoke run generated **10 synthetic jobs and 4
  preparation records**. Read-only validation reported integrity_check=ok,
  foreign_key_violations=0 and schema_version=6. A second invocation refused
  existing output. The database remains local and excluded by existing `data/`
  and `*.sqlite*` rules; `.venv/`, sidecars and locks are also ignored.
- Runtime guards constrained suite reads to public sources, the isolated/runtime
  dependencies and test temporary files; all suite database writes used temporary
  locations. Smoke-run writes were restricted to the designated synthetic output
  and its parent directory creation. The original private tree was not hashed
  again because accessing it is prohibited in P3A. No original private files were
  accessed or modified by this task; no fresh private-file comparison was performed.
- No live ATS boards, discovery, browser automation, application submission,
  scheduler, service, Dashboard, full CLI, ranking engine, resume updater, Git
  repository/remote, license, upload or publication was added or executed.
- The final guarded suite passed all **237 tests** with **0 network attempts,
  0 external/protected input-read attempts and 0 protected-write attempts**.
  Package-origin checks verified all 22 loaded application modules came from
  this public tree's src/. The successful guarded initializer smoke run also
  recorded zero blocked network, input-read or protected-write attempts.
- Public-file hash comparison against the initial 49-file staging baseline
  confirms nine additions, four intended modifications and no removals. All
  existing test files/fixtures, dependency declarations and configuration are
  unchanged. The 58-file reviewed inventory matches this manifest exactly.
  Public path/content screening found zero unresolved personal-absolute-path
  or credential-pattern findings; every new fixture carries the synthetic notice,
  has no applicant contact data and uses only reserved example.test URLs.
  This local check is not an independent secret-scanner or license certification.

## Step P3B.1 implementation and validation

P3A was reviewed and accepted before explicit authorization for P3B.1. This step
restores a generic ranking backend and fixes the requested public demo-recovery
safety issue; it does not restore the remaining application interfaces.

- Added four public files: ranking.py, test_generic_ranking.py,
  test_demo_safety.py and docs/RANKING_GUIDE.md. Modified candidate_evidence.py,
  database.py, demo.py, ranking_locations.py, AGENTS.md, README.md,
  docs/DEMO_GUIDE.md and this manifest. All previous test files and all P3A fixtures
  are unchanged. No original private source, evidence, environment or tests were
  read, imported or copied. No new dependency was installed or declared.
- The engine consumes explicit CandidateEvidence, JobRecord, validated
  configuration and optional JobMetadata/ApplicationRecord objects. It performs
  no file/database/network access or writes. Existing job evidence extraction,
  alternative-skill grouping, location assessment, relevance classification,
  application status validation and configuration weights are reused.
- The version-1 evidence schema remains source-hashed and source-anchored.
  Unique generic project IDs select no affinities. Empty skills/projects represent
  absent evidence and earn zero in those components. Positive claims still require
  supported feature mappings, verification anchors and matching source hashes.
  Safe relative source labels and retained limitation anchors make explanations
  traceable to the synthetic files; no raw candidate text or private notes appear.
- Current weights are unchanged: role alignment 30, skills 30, project relevance
  25, location 15. Required skill groups count 2, preferred/duty groups count 1;
  alternatives count once. Project credit uses the best single project's weighted
  coverage. Missing evidence receives zero without weight redistribution. Each
  component is rounded to two decimals and the score sums those contributions.
  Ordering is deterministic by displayed score and job identity, independently
  of eligibility, relevance classification or application status.
- Eligibility is assessed before scoring and remains separately annotated.
  Candidate degree, graduation and authorization facts are UNKNOWN in the feature
  schema; illustrative target settings are not applicant evidence. Explicit
  PhD-only/wrong-cohort cases can be POLICY_EXCLUDED under configured policies.
  This is a policy flag, not a confirmed applicant-ineligibility claim. Unknown
  sponsorship/ambiguous cohorts are never automatic rejection. No row is filtered
  from the ranking. Existing relevance labels and application statuses are retained
  separately; ranking never changes tracker state or records a submission.
- All ten fictional jobs were evaluated with the P3A candidate. Example scores:
  Robotics Software 91.00, Computer Vision 88.00, Simulation 75.00, Machine
  Learning 72.67, Fall Simulation 66.00, Robotics ML 63.50, Perception 55.00,
  PhD-only ML Research 36.00, Mechanical Engineering 12.00 and Marketing 6.00.
  Each includes calculations, job/config references, candidate anchors, limitations
  and input fingerprints. Scores are lexical heuristics over recognized features;
  sparse evidence is flagged. The Computer Vision result recognizes evaluation
  only and does not establish broad computer-vision expertise.
- Changing the reviewed synthetic mapping matters: removing PyTorch and its
  project mappings lowers the ML score from 72.67 to 54.33; removing only the
  classifier project lowers it to 64.33 with unchanged skills credit. Renaming
  projects provides no bonus. Simulation-only limitations withhold physical
  deployment/production credit and retain source references.
- Before code changes, synthetic temporary-database probes confirmed that an
  ordinary unrelated database was refused unchanged. A compatible run marker
  combined with an extra table/trigger was incorrectly accepted and the trigger
  changed an unrelated synthetic record. This public staging issue was fixed.
  Recovery now validates the exact fresh schema read-only and rejects extra
  identity aliases or discovery checkpoints before writable access. Run diagnostics,
  progress counters and completed payloads must also match initialization state.
  Added safety
  tests verify byte-for-byte preservation of extended, altered or unrelated
  databases and refusal of older schemas without migration/backup. All existing
  normal recovery, no-overwrite and manual-edit protections still pass.
- **287 tests passed: all previous 237 plus 41 generic-ranking tests and 9 demo
  recovery tests; zero failures, errors or skips.** The 104 original withheld
  cases remain withheld, not restored or counted as passes. Tests use only
  authored synthetic data, mocked services and temporary databases.
- The full suite ran in the existing ignored public `.venv/` with offline audit
  guards. Observed attempts: **0 network, 0 external/protected input reads and
  0 protected writes**. All 25 loaded application modules originated in public
  src/. Test database writes were confined to temporary locations. Ranking a
  generated temporary demo left database bytes, records and schema unchanged.
- No real database/resume or original private project was accessed or modified.
  No private-file hash comparison was attempted. No live boards, discovery,
  forms, submission, resume update, full CLI, Streamlit, launcher, scheduler,
  service, Git repository/remote, license, upload or publication was introduced.
- Final public inventory screening matched all 62 reviewed files to this manifest
  and found zero unresolved personal-absolute-path or credential-pattern findings.
  All P3A synthetic fixtures and all previous test files are hash-identical to
  their P3B.1 starting state. Four files were added, eight intentionally modified
  and none removed. The private tree was not inspected for comparison. These are
  local allowlist/content checks, not an independent scanner or license review.

## Step P3B.2A implementation and validation

P3B.1 was accepted before explicit authorization for the generic resume evidence
review/proposal step. All changes are confined to sanitized public staging. The
original personalized resume engine and private evidence remain excluded.

- Added seven reviewed public files: resume_review.py, test_resume_review.py,
  docs/RESUME_REVIEW_GUIDE.md, the three resume_review/ fixtures and
  tests/fixtures/resume_paragraphs.xml. Modified only AGENTS.md, README.md,
  docs/DEMO_GUIDE.md, docs/RANKING_GUIDE.md and this manifest. Existing backend,
  ranking, database/schema, P3A fixtures and all 287 prior test files are unchanged.
  No new dependency was declared or installed; the public isolated .venv is reused.
- Explicit loaders accept one resume and one reviewed candidate/evidence bundle.
  No defaults, document searches, private-profile imports or live services exist.
  The existing candidate evidence loader is reused unchanged. A generic version-1
  resume ledger binds source and mapping hashes, exact canonical claim text,
  unique claim/rule IDs, exact source anchors, evidence states and qualifiers.
  Supplemental review sources are explicitly supplied rather than discovered.
- Extraction retains exact TXT line content/offsets and supported DOCX paragraph
  text across runs, tabs and text breaks. UTF-8 and size limits apply; redirected
  inputs are refused. The conservative DOCX package/structure subset rejects
  tables, inherited styles, hidden text, revisions, fields, hyperlinks, drawings,
  headers/footers, comments, embeds and external relationships. Unsupported
  documents return limitations and no partial content or proposals. No source
  document is flattened, repaired, rendered, written or otherwise modified.
- The pure proposal engine maintains one general resume; it has no job input or
  job-specific variant generation. Each change carries a stable content/location
  ID, exact before/after strings, source references/hashes, evidence status,
  experimental qualifiers, limitations/uncertainties and a whole-proposal
  fingerprint. Canonical after text is verbatim source-anchored, not invented
  paraphrasing. Source/mapping modifications or missing/ambiguous evidence fail
  closed. IDs and fingerprints reproduce deterministically for identical inputs.
- Exact canonical content gets its CONFIRMED/PENDING/INFERRED/UNKNOWN review
  status. Mapped unsupported wording produces a human-review correction; unmapped
  wording remains UNKNOWN without an invented rewrite. CONFIRMED in synthetic
  fixtures means within fiction only. Hashes/anchors validate provenance, not
  independent truth. No automatic approvals, receipt/state persistence, Apply
  control or document editing/generation exists.
- The new resume fixture includes four deliberate unsupported statements plus
  already-supported fictional education and unknown professional experience.
  Review proposes four replacements and one supported skills addition. Examples:
  physical deployment becomes toy simulation with no physical deployment; a
  real-world-performance claim becomes a qualified synthetic validation split;
  an invented 80%-held-out/readiness claim becomes a fictional seen count of
  8/10 with no held-out or readiness conclusion; accepted publication becomes
  PENDING with no acceptance evidence. This toy observation was authored solely
  for tests, not copied/derived from any real research result. No dates, metrics,
  degrees, employment or publication acceptance were invented by the engine.
- **334 tests passed: all previous 287 plus 47 new P3B.2A tests; zero failures,
  errors or skips.** Coverage includes exact extraction, source anchors, stable
  IDs/fingerprints, unsupported/pending claims, missing/modified evidence,
  simulation/seen/held-out/measured qualifiers, read-only behavior, privacy
  isolation and unsupported document structures. The 104 original withheld
  cases remain excluded and are not counted as restored passes.
- The complete suite ran under offline audit guards in the existing public .venv.
  Observed attempts: **0 network, 0 external/protected input reads and 0 protected
  writes**. All 26 loaded application modules came from public src/. Test databases
  and mutation fixtures use temporary locations; no real/user database or resume
  is read. Source-resume and evidence byte comparisons are unchanged after review.
- P3A fixtures still validate with ten jobs/four preparation fixtures and the
  unchanged fixture fingerprint. All ten P3B.1 scores/order were rechecked unchanged:
  91.00, 88.00, 75.00, 72.67, 66.00, 63.50, 55.00, 36.00, 12.00 and 6.00.
  Existing tests generate valid temporary demo databases and preserve tracker
  protections. No existing generated demo/user database was needed for this step.
- No original private files, resumes, research records, metrics, source checkouts,
  environment or tests were accessed, imported, copied or modified. No private
  hash comparison was attempted. No live requests, discovery, application-record
  mutation, submission, scheduler, service, CLI, Dashboard, Windows launcher,
  resume Apply, Git repository/remote, license, upload or publication was introduced.
- Final inventory screening matched all 69 reviewed public files to this manifest
  and found zero unresolved personal-absolute-path or credential-pattern findings.
  Hash comparison against the 62-file starting inventory confirms seven additions,
  five documentation/instruction modifications and no removals. Every prior source
  module, test file, configuration/dependency declaration and P3A fixture is
  unchanged. New fixtures carry the synthetic notice and contain no contact data.
  This is local allowlist/content verification, not an independent secret scanner
  or license review. Source DOCX/resume outputs remain ignored and private.

## Step P3B.3A implementation and validation

P3B.2A was accepted before explicit P3B.3A authorization. This step connects the
public backends into a small end-to-end offline demonstration; the full original
personalized CLI and Dashboard remain excluded.

- Added five public files: cli.py, __main__.py, test_public_cli.py,
  docs/CLI_GUIDE.md and demo/fixtures/offline_cli_manifest.json. Modified only
  __init__.py, demo.py, pyproject.toml, AGENTS.md, README.md, the three backend
  guides and this manifest. Existing ranking, resume review, database/schema,
  application transition logic, synthetic candidate/job/resume fixtures and all
  prior test files are unchanged. No private source or tests were copied/imported.
- Five manual commands are available through `python -B -m internship_agent` and
  the verified `internship-agent` console entry: demo-status, demo-jobs,
  demo-applications, demo-rank and demo-resume-review. Thin handlers call current
  JobDatabase/demo validation, ranking/evidence and resume-review functions.
  Initializing/recovering remains exclusively in scripts/create_demo.py; the CLI
  never implicitly initializes, migrates, resumes or repairs missing input.
- Database commands require explicit --database selection of the established
  public data/demo/demo.sqlite3 path (or its exact absolute equivalent). Other
  filenames/locations, traversal, URIs, UNC/device paths and alternate streams
  are refused before opening. Sidecars, locks, partial outputs and redirected
  inputs are refused. No candidate/resume/evidence/registry path override exists.
- The new fixed-path allowlist hashes exactly nine reviewed public fixture/config
  files. Missing, corrupt, changed or unexpected inputs are refused without
  fallback. It is local review/integrity metadata, not ownership authentication
  or independent fact verification. All business validation uses public backends.
- Databases open read-only and must pass complete demo run/schema/integrity,
  identity, metadata, application history/state and payload verification before
  any records are displayed. Extra/unrelated or edited data is refused; application
  notes/receipts are omitted from listing/ranking output. Commands print terminal
  results only. No application records, status changes, reports, resumes,
  approvals, Apply state, database progress or output documents are written.
- Ranking retains the unchanged 30/30/25/15 weights and ten sorted scores:
  91.00, 88.00, 75.00, 72.67, 66.00, 63.50, 55.00, 36.00, 12.00 and 6.00.
  Output shows all components/calculations, source anchors, limitations/fingerprints
  and separate UNKNOWN/POLICY_EXCLUDED/relevance/application annotations. It
  labels heuristic scores and sparse evidence; it does not present probabilities.
- Resume review renders the same five exact proposals, change IDs, states,
  qualifiers, uncertainties and proposal fingerprint as P3B.2A:
  a3f9fc4ef400028115be11cc90d54412968efb775e827c80af23be93bf242c83.
  Pending publication remains PENDING; the original synthetic TXT resume is
  unchanged. Narrow DOCX support/unsupported structures are explained. Resume
  Apply, approvals, editing, DOCX/PDF generation are unavailable.
- The declared setuptools>=68 build requirement was satisfied from a cached
  setuptools 84.0.0 wheel without network access. The public isolated .venv then
  installed this checkout editable with --no-index --no-deps --no-build-isolation.
  Console commands were verified without a PYTHONPATH override and loaded public
  source. No dependency declarations were added/upgraded. PDF/UI packages remain
  unnecessary/uninstalled. Ignored environment/build metadata is not release
  material; clean full-package installation or standalone-wheel support is unverified.
- **372 tests passed: all previous 334 plus 38 new CLI integrations; zero failures,
  errors or skips.** Tests use temporary databases and synthetic fixtures only.
  Existing demo recovery/no-overwrite guards remain tested and authoritative.
  The 104 withheld original cases remain excluded and are not counted as restored
  passes. Help/arguments, selection, listing, explanations, unknown eligibility,
  proposal text, failures, privacy and read-only behavior are covered.
- The full suite ran under offline audit guards: **0 network, 0 external/protected
  input-read and 0 protected-write attempts**. All 27 loaded application modules
  came from public src/. A guarded installed-package smoke run of all five commands
  also recorded zero network/input/write attempts and confirmed every fixture and
  demo database hash unchanged, with no SQLite sidecars created. The explicitly
  selected synthetic database has 10 jobs/4 preparation records, integrity_check=ok,
  foreign_key_violations=0 and schema_version=6. Public package startup suppresses
  future runtime source-cache writes; -B/PYTHONDONTWRITEBYTECODE remain documented.
- No original private files, environment, real resume/research/database or actual
  application notes were accessed or modified. No private-file hash comparison
  was attempted. No live boards/ATS requests, browser automation, submission,
  scheduling/services, Streamlit, Windows launcher, full personalized CLI, resume
  Apply, Git repository/remote, license, upload or publishing occurred.
- Final reviewed inventory matches all 74 public files exactly. Local path/content
  screening found zero unresolved personal-absolute-path or credential findings;
  the nine-file offline allowlist matches every current source hash. Comparison
  against the 69-file starting inventory confirms five additions, nine intended
  modifications and no removals. All prior tests, existing demo/resume fixtures,
  database/application code and ranking/resume-review engines are unchanged.
  Runtime .venv/data output remains excluded. These are local allowlist/content
  checks, not an independent secret-scanner certification or license review.

## Step P3B.3B implementation and validation

P3B.3A was reviewed and accepted before explicit P3B.3B authorization. The public
offline Dashboard is independently authored and uses only sanitized public code
and synthetic data; original private Dashboard files were never accessed/copied.

- Added eight reviewed files: demo_services.py, dashboard_services.py,
  dashboard_app.py, dashboard_launch.py, scripts/run_dashboard.py,
  tests/test_public_dashboard.py, .streamlit/config.toml and
  docs/DASHBOARD_DEMO_GUIDE.md. Modified cli.py, AGENTS.md, README.md, the four
  existing guides and this manifest. Existing database/application/ranking/resume
  engines, initializer/recovery logic, all synthetic fixtures and all prior test
  files remain unchanged. No database/schema/identity/status rule changed.
- Streamlit is a thin presentation layer with Overview, Demo Jobs, Application
  Tracker and General Resume views. Native metrics/tables, search/filter/sort,
  full-title detail panels, component/evidence explanations, separate eligibility
  warnings, read-only history/validated synthetic notes, exact resume proposals
  and Advanced Details metadata are implemented. No raw JSON is shown in primary
  views. Counts/scores come from validated snapshots. Every page displays the exact
  synthetic notice; jobs are never represented as current open vacancies or linked
  to real employer application pages.
- DemoServices extracts the CLI's public fixed-path/allowlist boundary and existing
  ranking/resume backend calls. CLI commands and protections are preserved. Both
  clients reject redirected, modified, incomplete, arbitrary or incompatible
  inputs. The Dashboard explicitly configures data/demo/demo.sqlite3; no path
  browser, profile/registry fallback or uploader exists. SQLite opens read-only,
  complete demo identity/schema/payload validation precedes returning records,
  and connections close before rendering. Each user-triggered rerun revalidates
  inputs without persistent data caching or continuous polling.
- The tracker displays four synthetic preparation records and their existing
  history. There is no status-change/submission control, simulated successful
  submission or browser automation. General Resume reuses the unchanged review
  engine/five proposals, preserves exact before/after text, evidence states,
  limitations and uncertainties, and keeps Apply unavailable. No approval or
  DOCX/PDF editing/generation is implemented; narrow DOCX support is explained.
- All ten numerical ranking results/order and 30/30/25/15 weights remain unchanged:
  91.00, 88.00, 75.00, 72.67, 66.00, 63.50, 55.00, 36.00, 12.00 and 6.00.
  UNKNOWN remains review-needed, not automatic ineligibility; POLICY_EXCLUDED
  remains a separate configured policy. Sparse evidence and simulation/experimental
  qualifications remain visible. The resume proposal fingerprint remains
  a3f9fc4ef400028115be11cc90d54412968efb775e827c80af23be93bf242c83.
- The explicit foreground launch is `.venv/Scripts/python.exe -B
  scripts/run_dashboard.py --theme light` (or --theme dark). It checks the public
  .venv, anchors working paths to staging and binds only 127.0.0.1:8501. Telemetry,
  automatic browser startup, file watching, reload/static serving and detailed
  errors are disabled. Global/user Streamlit configuration/secrets and environment
  overrides are excluded; CORS/XSRF remain enabled. An ignored local runtime-temp
  directory is ensured at explicit launch. Runtime OS metadata is initialized
  locally before guarding. Streamlit 1.65's separate configuration-file polling
  hook is explicitly disabled despite its fileWatcherType override; a regression
  verifies no poll watcher is installed and incompatible bootstrap APIs fail closed.
  Runtime guards follow initialization,
  using a process-lifetime external-read/network/write/subprocess boundary.
  Browser transport is local loopback only. No startup integration, scheduler,
  daemon, background service or public deployment is installed.
- Streamlit 1.65.0 and dependencies were installed into the existing public .venv
  from cached local wheels with --no-index. The already-declared pypdf requirement
  was satisfied locally; pip check found no broken requirements. No dependency
  declarations or private environments were copied/changed. This is not a clean
  install claim. Windows/Python 3.12.10/Streamlit 1.65.0 are tested; Linux launch
  is documented but untested. Older allowed Streamlit versions, standalone package
  portability and the configuration adapter need further compatibility review.
- **405 tests passed: all previous 372 plus 33 Dashboard regressions; zero
  failures, errors or skips.** Service tests use temporary SQLite/fixtures and
  Streamlit AppTest renders without an HTTP server. Tests cover counts, unchanged
  scores/order, eligibility separation, filtering/history/proposals, exact output,
  read-only byte preservation, bad inputs, private/network isolation and absence
  of editing/submission/scheduling/public binding controls. The 104 original
  withheld cases remain excluded and are not counted as restored passes.
- The final full-suite guard recorded **0 external network, 0 protected/outside
  input-read and 0 protected-write attempts**. All 30 loaded application modules
  originated in public src/. On Windows, the guard permitted 58 standard-library
  event-loop socket-pair IPC operations only; no ATS/HTTP requests occurred in
  tests. Direct safety-rejection tests use simulated audit events, not real writes.
  Runtime local transport is expected. The final guarded native startup/shutdown
  smoke check reported zero external network/input/filesystem-write attempts.
- Actual local-browser visual inspection covered all four pages in light and
  dark themes, including job details/evidence and exact resume corrections. The
  inspected page assets were locally served; telemetry was disabled. Real
  synthetic-only JPEG captures are in ignored data/dashboard-validation/screenshots:
  overview, jobs, tracker and resume in both themes, plus resume-proposals-light
  and a contact sheet composed from the actual captures. No screenshots were
  fabricated or derived from private material. The browser's default narrow
  viewport was used; this is not exhaustive accessibility/breakpoint certification.
  The observed dark information-banner contrast was approximately 4.9:1.
- The existing synthetic demo has 10 jobs/4 preparation records, integrity_check=ok,
  foreign_key_violations=0 and schema_version=6. Rendering/widget tests preserve all
  temporary-database bytes, and actual local verification preserved the existing
  demo database and every source fixture byte-for-byte. Source resumes were not
  modified. Manual validation servers were stopped; no local server remains.
  The Codex Windows terminal did not forward Ctrl+C to its child during validation,
  so only the verified task-owned server was terminated, followed by a successful
  native startup/shutdown smoke check. See the guide's shutdown fallback.
- No original private source, candidate/profile/resume/research/database or actual
  application notes were accessed/copied/modified. No private hash comparison was
  attempted. No live ATS boards, external recruiting calls, form filling,
  application submission, resume Apply, Git repository/remote, uploads, publishing
  or license creation occurred. Generated screenshots/runtime output stay ignored.
- Final reviewed inventory matches all 82 public files. Local path/content screening
  found zero unresolved personal-absolute-path or credential-pattern findings and
  the original nine-file fixture allowlist remains hash-valid. Comparison against
  the 74-file starting inventory confirms eight additions, eight intended changes
  and no removals. All prior tests, synthetic fixtures and core database/demo/
  application/ranking/resume engines are unchanged. Ten actual screenshot/inspection
  artifacts are stored under ignored data/, outside the release inventory. No
  private-file comparison was attempted; these are local staging checks, not an
  independent secret-scanner or license certification.

## P4A: Clean installation and dependency reproducibility

- **PASS: Windows 11 build 10.0.26200, AMD64, CPython 3.12.10.** Disposable
  source copies contain only the explicit reviewed release inventory; no previous
  venv, generated database, caches, logs, screenshots, Git or private data was
  copied. Fresh environments install offline from 40 reviewed cached wheels,
  with package indexes disabled and no private environment reuse. The final
  Windows snapshot contains exact versions/SHA-256 hashes and setuptools 84.0.0;
  pip 25.0.1 comes from venv creation. Full dependency resolution and pip check
  pass. No `--no-deps` bypass, automatic upgrades or downloads occurred.
- Streamlit is constrained to **1.65.0**, the existing tested version, because
  launcher configuration handling is version-sensitive. PyYAML remains 6.0.3;
  the existing pypdf range is satisfied by 6.20.0. Exact transitive versions,
  commands, environment details and limitations are in
  [docs/CLEAN_INSTALL_VALIDATION.md](docs/CLEAN_INSTALL_VALIDATION.md).
- Packaging review found the original source archive omitted runtime/config/
  launcher/test fixtures. New MANIFEST.in excludes by default and includes all
  **86 exact reviewed files**. Source archives contain those files plus only
  PKG-INFO, setup.cfg and the generated SOURCES.txt. A new extracted-source venv
  installs all dependencies offline, imports its own src/, passes pip check,
  creates fresh demo data and completes the workflow. No PYTHONPATH is required.
  requirements.txt's `-e .` must be installed from the intended source root.
- Wheel installation is separately verified in a new venv outside source roots:
  code imports from site-packages, console help and pip check pass. It contains
  32 Python files and 5 dist-info files, with no fixtures/config/scripts. The
  wheel-only resume demo fails closed with exit 1 and no proposal output.
  **Standalone wheel demo is unsupported**; source checkout/extracted sdist is
  the supported demo. No runtime-asset relocation or portability feature was added.
- **409 tests passed: all 405 prior public tests plus 4 packaging regressions;
  zero failures, errors or skips.** The original 82-file source baseline also
  passed all 405 in a fresh environment. Final tests in the new extracted-source
  environment recorded **0 network, 0 outside input reads and 0 protected writes**.
  All 30 application modules came from its src/. Only 58 trusted Windows stdlib
  socket-pair IPC operations were permitted for AppTest. The 104 original withheld
  cases remain excluded, not counted as restored passes. Core modules, old tests,
  schema, synthetic fixtures, ranking formulas and resume logic are unchanged.
- Fresh demo initialization and all five read-only CLI commands pass; integrity
  is ok, foreign-key violations 0, schema 6, COMPLETED, 10 fictional jobs and
  4 preparation records. Scores remain 91.00, 88.00, 75.00, 72.67, 66.00, 63.50,
  55.00, 36.00, 12.00 and 6.00. Five exact resume proposals and both existing
  fixture/proposal fingerprints remain unchanged. A guarded CLI smoke check
  records zero network/external input/write attempts and preserves all fixture
  and database bytes. Reinitialization and --resume against completed output
  return 1 without changing it; unexpected-database regression tests pass.
- The unchanged safety launcher runs the real foreground dashboard from the
  extracted source and all four pages were inspected in the local browser. OS
  inspection confirms 127.0.0.1:8501 only; all 137 observed page assets are local.
  The Codex terminal did not deliver Ctrl+C to the child, and Stop-Process reported
  a host error. Native termination stopped only the verified task-owned server;
  its launcher exited and zero processes/listeners remained. Thus real-browser
  cleanup is verified, but graceful Ctrl+C delivery is not. A separate native
  startup/shutdown test using Streamlit's existing stop-immediately testing hook
  through the safety launcher returns 0 and records zero external network/input/
  write attempts. The forced-stop browser session has no final counter line.
- Source and wheel artifacts exclude invented ignored packaging canaries, secrets,
  candidate directories, environments, caches, Git, databases and runtime output.
  Final inspection checks exact names/content rather than trusting .gitignore.
  Generated environments, wheels, build artifacts and one actual synthetic-only
  validation screenshot stay under ignored data/clean-install-p4a/.
- **Linux UNVERIFIED/BLOCKED:** Ubuntu 24.04 WSL/Python 3.12.3 is available, but
  creating an independent clean venv fails because ensurepip is absent; cached
  compiled wheels target Windows. No Linux packages were installed, no tests/demo
  runs are claimed and no network download occurred. macOS and other Python
  versions remain untested. Source review does not establish platform compatibility.
- No original private workspace or applicant/resume/research/user-database input
  was accessed or modified. No live ATS, submission, editing/Apply, scheduler,
  background service, remote, GitHub repository, push, CI, license or publication
  was introduced. This is local reproducibility validation, not a dependency
  vulnerability, license/provenance or OS-wide security certification.

## P4B: Public documentation, onboarding and offline-test CI preparation

- Replaced the staging notice with a publication-quality English README describing
  the implemented synthetic demo, capabilities/limits, Windows requirements,
  source installation, initialization, CLI/dashboard use, tests, architecture,
  privacy/human approvals and AI-assisted development. No badge, public repository
  URL, automatic submission, unrestricted DOCX, Linux or standalone-wheel promise
  is advertised. ATS backend modules are clearly outside the public demo path.
- Offline local-wheel installation remains the verified P4A method. The README
  separately documents an ordinary PyPI install with the same hashed Windows
  snapshot and labels it unexecuted. Hosted setup/Action resolution, current index
  availability and a network clean install are unverified. Streamlit 1.65.0 and
  every dependency declaration/hash remain unchanged; no package was downloaded.
- Targeted corrections align all demo/ranking/resume/CLI/dashboard guides with
  current behavior and source installation. The P4A report remains historical
  evidence. README/CI-guide PowerShell examples and five workflow run blocks pass
  local syntax parsing; local Markdown file links pass offline existence checks.
  Final inspection resolves 50 local file links. Both documented ranking/resume
  Python examples and console help execute with synthetic inputs; read-only API
  example audit counters are all zero. Interactive Read-Host, py-launcher spelling,
  index installation and hosted steps are syntax/documentation only, not executed
  checks. Backend commands/entry points retain P4A and local-smoke evidence.
  The exact README no-index source-install command also passes as a reinstall in
  the clean P4A environment with dependencies already present; pip check and import
  paths pass. It is not counted as another fresh or package-index installation.
  External URLs, GitHub Markdown/Mermaid rendering and Action tags were not checked
  online; no remote-latest-version claim is made.
- Prepared `.github/workflows/offline-tests.yml`: one windows-2022/Python 3.12 job,
  exact checkout v4.2.2/setup-python v5.4.0 version tags, contents:read only,
  no persisted checkout credentials/secrets, hash-locked dependency installation,
  offline editable install, pip check and manual validation helper. No scheduled
  trigger, deployment, cache/artifact upload or publishing step exists. Version
  tags are not immutable commits; remote contents/provenance and hosted execution
  require later review. **Hosted CI has not run.** Windows Server 2022 and the
  Action-selected Python patch are prepared targets, not locally verified targets.
- `scripts/verify_public_demo.py` is a test coordinator, not an application feature.
  It runs pip check and all tests, allows only synthetic temporary writes, refuses
  external transport and existing data/demo input reads, initializes a new fixture
  copy, checks all five CLI handlers/help/selected ranking and read-only hashes,
  then builds/inspects exact-inventory source/wheel copies with invented ignored
  canaries. A separate worker uses the existing native shutdown test hook through
  the unchanged safety launcher. No Python/application logic in src/ was changed.
- **414 tests passed: all 409 existing public tests plus 5 documentation/CI checks;
  zero failures, errors or skips.** pip check, synthetic smoke, SQLite integrity/
  schema/counts, unchanged ranking/proposals, source/wheel boundaries and native
  guarded startup/shutdown pass locally in the P4A clean source environment.
  Test/application audit counters: **0 network, 0 external input, 0 protected writes**;
  58 trusted Windows stdlib socket-pair IPC events support AppTest. The 104 original
  private cases remain omitted and are not counted as restored passes. An initial
  coordinator discovery error was fixed by setting the unittest top-level root;
  existing tests/backend were neither skipped nor changed to bypass it.
- The reviewed inventory is **90 files**: four P4B additions (workflow, CI Guide,
  verifier and five-case test module). MANIFEST.in includes them explicitly.
  Temporary builds contain only these reviewed bytes plus three public generated
  sdist metadata files; the wheel contains the unchanged 32 modules and 5 dist-info
  files. Invented secrets/candidate/database/log canaries stay excluded. Existing
  backend/fixtures/launchers/configuration/dependency hashes are unchanged.
- Existing ignored screenshots are listed as candidates in docs/CI_GUIDE.md;
  none entered README/public assets or the source archive. Contact-sheet/proposal
  pixels and all eleven JPEG metadata records were reviewed locally; EXIF count is
  zero. The cropped proposal view omits the top synthetic banner and displays
  deliberately unsupported fictional claims, so any later publication needs
  explicit synthetic/evidence-review context. Human approval is still required.
- Windows 11/Python 3.12.10 remains the verified local target. Linux UNVERIFIED/
  BLOCKED and macOS/other-version limits remain unchanged. No original private
  project/candidate/resume/user database was read or modified. No live ATS,
  submission, Resume Apply, runtime integration, Git repository/remote, push,
  upload, license, provenance approval or public release occurred. Stop at P4B.

## P4C.2A: License provenance resolution and compliance preparation

- The selected preference is MIT; intended public attribution is **Copyright (c)
  2026 Zhenyu Wu**, expressly authorized by the user. This is not proof of first-
  party ownership. During P4C.2A, the authority question initially received
  “I need to review this first.” The subsequent completed human review is recorded
  below and supersedes that pending status. No LICENSE/NOTICE or source copyright
  headers were added. P4C.2B creation still requires explicit approval.
- Narrow, unauthenticated official HTTPS reads were authorized by the user. The
  research tool initially supplied no usable content and ordinary local requests
  were socket-blocked; approved requests then returned actual HTTP 200 license,
  notice, tag-ref and action.yml evidence. Version-specific source-license evidence
  for Streamlit 1.65.0, NumPy 2.5.4, Pillow 12.3.0, Arrow 25.0.1, setuptools 84.0.0,
  PyYAML 6.0.3 and pypdf 6.20.0 is recorded with response hashes in the local
  remediation report. Initial premature resolved-status claims were corrected;
  final findings rely on actual responses. No local project files, inventories,
  credentials, private paths, candidate or environment data were uploaded.
- The planned initial artifact is the GitHub source checkout, with dependencies
  independently installed. No mandatory new project NOTICE was identified for the
  observed source-only boundary, conditional on the human first-party review and
  no undisclosed copied third-party material. This is not legal or blanket binary-
  compatibility clearance. Native/vendor/font/frontend contents, cached-wheel
  authenticity and applicable notices need further review if ever redistributed.
- Official provider documentation and linked legal pages were read. Greenhouse
  GET authentication, Lever published-posting interfaces and Ashby board interfaces
  are documented; customer/content/IP terms do not establish unrestricted employer
  description republication or retention rights for future usage. Applicability
  remains context-dependent. No live recruiting API, posting endpoint, submission,
  authenticated account or provider asset was accessed/copied into the project.
- The two existing Action versions now use official tag-ref verified full commits:
  checkout v4.2.2 = 11bd71901bbe5b1630ceea73d27597364c9af683; setup-python v5.4.0 =
  42375524e23c412d93fb67b49958b491fce71c38. Readable version comments and existing
  permissions/triggers/commands are preserved. Only the existing test's expected
  pin assertion changes. Immutable identity is not a full bundled-code audit,
  latest-version or vulnerability-clearance claim. Hosted CI has not run.
- **414 tests passed; zero failures, errors or skips**, plus pip check, synthetic
  CLI/SQLite smoke, unchanged scores/proposals/read-only hashes, 90-file source/
  wheel packaging and native guarded startup/shutdown. Offline test audit counters
  are 0 network, 0 external input, 0 protected writes; 58 trusted stdlib socket-pair
  IPC operations support Windows AppTest. Authorized official evidence requests
  are separate from the offline test run. No dependencies were downloaded,
  installed or changed; no new application behavior or schema was introduced.
- The 90-file release/package allowlist is unchanged. Both long P4C reports are
  local review records excluded from the future source artifact pending an explicit
  inventory decision. Private/runtime materials, real job-description fixtures,
  dependency wheels, screenshots and Git history remain excluded. No original
  private workspace was accessed or modified. No Git/remote, upload, license,
  public asset, live feature or publication was created. Stop after P4C.2A.

## Human first-party licensing authority confirmation — 2026-10-11

The user completed the review and confirmed, to the best of their knowledge,
authority to license the included public source, tests, documentation and synthetic
fixtures under MIT. They reported no known employer/client/university/contributor
or other agreement preventing licensing, and no known unlicensed third-party
material in the reviewed release. Intended attribution remains
**Copyright (c) 2026 Zhenyu Wu**. The exact confirmation is preserved in the local
`docs/COMPLIANCE_REMEDIATION.md` review record.

This is human knowledge/authority confirmation, not independent ownership evidence,
exclusive rights or guaranteed copyrightability of AI-assisted output. The human
review gate is recorded complete. LICENSE creation remains expressly deferred
until separate Step P4C.2B implementation authorization. No LICENSE/NOTICE, Git,
remote, upload, publication, dependency, workflow or application change accompanies
this documentation-only update. The 90-file allowlist is unchanged; tests were
not rerun and the prior 414-test result remains historical.

## P4C.2B: MIT License implementation and release validation

- The user explicitly authorized LICENSE creation after completing the first-party
  authority review, to the best of their knowledge, for the personal project. They
  reported no known university/laboratory/employer/client/contributor or other
  restriction and no known unlicensed copied material. This is a human authority
  statement, not exclusive ownership or guaranteed copyrightability of AI output.
- Created root `LICENSE`: complete standard **MIT License** with exactly
  **Copyright (c) 2026 Zhenyu Wu**. No extra restrictions, source-file copyright
  headers or CLA were added. Standard terms were independently compared with a
  pre-existing local MIT license, ignoring only whitespace/line wrapping; the
  normalized terms SHA-256 is
  fe2a9817987f862eaced948f0468c7f51d2fedfc48c5c505b246a49a3870e9a5.
  Three targeted regressions verify full terms/notice, README/metadata agreement,
  explicit inclusion and internal-report exclusions.
- README links the first-party MIT grant and preserves the AI-assisted development
  attribution and functional limitations. Dependencies keep their own licenses;
  MIT supplies no rights in ATS services, employer descriptions, logos, trademarks
  or other external content. No mandatory project NOTICE was identified for this
  reviewed source-only release; no NOTICE or dependency license collection added.
- `pyproject.toml` declares `license = "MIT"` and `license-files = ["LICENSE"]`.
  The build floor is raised from setuptools>=68 to >=84, the already-tested
  installed/locked backend supporting this metadata, with no third-party upgrade or
  installation. Runtime dependency declarations and all 40 locked versions/hashes
  are unchanged. No contradictory legacy License field/classifier is introduced.
  Offline editable reinstall of the project in the public validation environment
  passes pip check and reports the same MIT license expression/file; this is not
  a fresh-install or hosted-CI claim.
- The exact release allowlist is **91 files**, the prior 90 plus LICENSE. The
  unchanged default-exclude policy and one new MANIFEST.in inclusion preserve
  runtime/private exclusions. Local P4C audit/remediation reports remain outside
  the release. Source builds contain those exact 91 bytes plus PKG-INFO, setup.cfg
  and generated SOURCES.txt. Wheel builds contain 32 unchanged source modules,
  five metadata files and one license file; they still cannot run the complete
  standalone demo. Both formats have License-Expression: MIT, License-File: LICENSE,
  no conflicting legacy license metadata, and byte-identical approved license text.
- **417 tests passed: all prior 414 plus 3 targeted license regressions; zero
  failures, errors or skips.** The public offline validation helper, pip check,
  synthetic CLI/SQLite initialization, no-overwrite/read-only hashes, unchanged
  scores/proposals, exact package inspection with ignored canaries and native
  guarded startup/shutdown passed in the existing clean P4A environment. Offline
  audit counters: 0 network, 0 external input, 0 protected writes; 58 trusted
  Windows stdlib socket-pair IPC events support AppTest. The 104 withheld cases
  remain excluded, not counted as restored. Hosted GitHub Actions have not run.
- All application modules, fixtures/candidate evidence, configuration, runtime
  dependencies/lock, real manual launchers, security protections and historical
  internal audits remain byte-identical to the starting public tree. Only license,
  metadata/inventory/documentation, packaging helper and targeted test changes
  were made. Privacy screening finds no unresolved private absolute paths or
  credential patterns. No original private workspace, real resume/user database,
  live ATS, network request, upload, Git/remote, screenshot asset, submission or
  publication was accessed/created. Stop after P4C.2B.

## P5A.3: First hosted CI failure and exact-path checkout repair

- The private root run on 94d6bcaf5395cc808d8d4b17c33f93238095dc84 completed
  dependency installation and pip check, then ran 417 tests with 4 failures and
  189 errors. Read-only inspection of run 38217268996 confirms the recurring
  candidate-source hash error; no job posting, private input or raw log is copied
  into release files. Repository visibility was independently verified PRIVATE.
- Committed evidence Markdown files are LF-only and match their approved hashes:
  profile.md has 15 LF/0 CRLF, experience_bank.md 15/0, verification_report.md 21/0.
  A real disposable core.autocrlf=true checkout produces respectively 15, 15 and 21
  CRLF sequences. Their SHA-256 values change, while replacing CRLF with LF returns
  exactly the committed bytes. The nine offline-manifest inputs all transform the
  same way. Both candidate-loader and offline fixture validation fail as designed.
  The full reproduction matches the hosted totals exactly: 417 tests, 4 failures,
  189 errors, all 189 with the candidate-source message.
- Prior local core.autocrlf=false preserved LF and therefore passed. Added only
  ten anchored `.gitattributes` text/eol=lf rules for the nine byte-hashed synthetic
  config/fixture files plus their offline manifest. There is no wildcard or global
  normalization. No source content, expected hash, ranking_features.json, claims
  ledger, loader or integrity check changes. Unprotected checkout files still
  convert to CRLF; fresh protected checkout files retain their original LF hashes.
- The release allowlist and MANIFEST.in now contain 92 files, adding only
  .gitattributes. One focused regression checks exact rule scope, LF bytes and
  unchanged expected hashes. README and CI Guide explain the failure and fix.
  Local diagnosis/test logs and reports remain ignored outside the tracked tree.
- The repaired Windows-style checkout passes **418 tests**, all 417 prior cases
  plus the new regression, zero failures/errors/skips. Synthetic CLI/SQLite smoke,
  unchanged ranking scores and resume proposal fingerprint, exact 92-file source/
  wheel packaging and MIT validation pass. Guards record 0 network, 0 outside input
  and 0 protected writes; 58 trusted stdlib socket-pair IPC events support AppTest.
  A passing hosted corrective run is not inferred from these local results.
- Only six reviewed paths change: .gitattributes, MANIFEST.in, this manifest,
  README.md, docs/CI_GUIDE.md and tests/test_packaging.py. The original root commit,
  all source logic/security, synthetic evidence, dependency hashes and LICENSE
  are preserved. One conditional corrective commit/private push is authorized
  only after the full validation and independent remote gates. No second attempt,
  public visibility, extra branch/tag/release, live ATS or submission is authorized.

## Current compatibility and release blockers

1. The public offline CLI and Streamlit Dashboard, generic ranking and read-only
   resume proposals are available. Full personalized/general-user interfaces,
   onboarding/application integration and approval-gated resume editing remain
   deferred. Keep Apply disabled until a separately authorized writer/approval
   workflow is implemented and verified.
2. There is no local preference file, live verified ATS registry, initialized user
   database, real candidate evidence mapping or resume. The synthetic evidence
   bundle and generated demo database are not user inputs. Empty
   registry templates cannot support live discovery without separate verification.
3. The fictional evidence bundle and P3B.2A synthetic resume-review fixtures are
   available. Approval-bound DOCX output, fresh-source/conflict validation,
   structure-aware editing and render/layout verification still need a later
   authorized step. Replacements for real-job regression cases and restored safe
   ranking-report/resume/UI integration coverage remain outstanding. None of the 104
   withheld tests was copied back. Synthetic ATS registries remain mock-test inputs.
4. English README onboarding, Dashboard/CLI/backend/CI guides, clean Windows
   installation instructions and offline initialization now exist. Broader real-user onboarding
   documentation remains deferred. Linux, macOS, other Python/Streamlit versions
   and a standalone-wheel demo are unverified or unsupported as documented.
   No cross-platform functionality change or general compatibility claim is made.
5. MIT is now applied to first-party reviewed material; attribution is Copyright (c) 2026
   Zhenyu Wu, expressly authorized for public attribution. Human first-party
   authority review is complete and attested to the best of the user's knowledge;
   independent or exclusive ownership is not asserted. P4C.2B explicitly authorizes
   the complete MIT LICENSE and approved notice, now applied. No separate NOTICE
   obligation was identified for the current source-only artifact; no NOTICE was
   added. Third-party licenses are preserved. Any newly discovered source-provenance
   exception must be reviewed; binary/vendor-component uncertainties are recorded
   in the local remediation report and must be resolved if those components are
   ever redistributed. The planned initial release distributes source only.
6. P4A completes clean Windows source/sdist installation and existing synthetic
   integration validation. Final staged publication review/approval remains
   outstanding. The exact local Windows snapshot is not a cross-platform lock,
   dependency vulnerability audit or redistribution approval. Any dependency
   change needs separate compatibility/provenance review.
   The first hosted dependency install completed but full CI failed checkout
   integrity. The corrective hosted result must be inspected separately. Package
   artifact authenticity and selected screenshot assets need further review.
   P4C.2A could not independently verify
   full supply-chain security. Official Action tag identities are verified and pinned;
   no passing hosted CI or vulnerability-clearance claim is inferred from local tests.

Stop after the single P5A.3 corrective attempt. No additional commits, pushes,
live features, public release or visibility change is authorized by this step.
