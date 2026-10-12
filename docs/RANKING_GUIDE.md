# Generic evidence-based ranking (P3B.1)

Examples use SYNTHETIC DEMONSTRATION DATA — NOT REAL JOB POSTINGS.

`internship_agent.ranking` is independently authored public code. It does not
import or copy the withheld personalized engine. `rank_job` and `rank_jobs`
consume explicit JobRecord, CandidateEvidence and validated preferences objects.
Optional JobMetadata and ApplicationRecord objects supply context. The engine
does not load files, open databases, save scores, prepare forms or make requests.
Database access remains in JobDatabase; callers may explicitly supply its records.

## Candidate evidence contract

The existing version-1 mapping remains the evidence format:

- `review_basis: local_source_review` and SHA-256 values for `profile.md`,
  `experience_bank.md` and `verification_report.md`.
- `features`: unique generic IDs in the public `ranking_job_evidence.SKILLS`
  vocabulary, status SUPPORTED and exact source anchors. Each positive skill
  claim must reference the verification report. No free-text candidate guessing.
- `projects`: unique generic IDs, non-empty unique supported feature lists and
  source anchors. IDs identify evidence; they never select an affinity or bonus.
- `limitations`: supported limitation labels and source anchors. Simulation-only
  evidence cannot earn physical deployment or production-experience credit.

The loader verifies source hashes and anchor presence, not the truth of claims.
For these fixtures, CONFIRMED/SUPPORTED means within authored fiction only.
Empty feature/project lists are valid unknown evidence and earn zero credit in
their components. Positive claims retain the same evidence requirements.
Unknown feature IDs are rejected by this ranker rather than silently interpreted.

Pass `reference_prefix="demo/fixtures/evidence"` when loading the P3A bundle.
The prefix is a safe relative source label; outputs cite actual fixture lines
without exposing document text or personal absolute paths. The loader retains
the legacy logical `candidate/` prefix by default, but the engine never invokes
that default or reads an implicit candidate directory.

## Score and explanation

Weights come exclusively from validated configuration. The current example uses
30 role alignment + 30 technical skills + 25 project relevance + 15 location,
totaling 100. Each component earns weight × fraction, rounded to two decimals;
the displayed score is the sum of those component points. Missing components
retain their configured weight and earn zero, without redistributing points.

- Role alignment: normalize configured/title words, including ML expansion and
  removal of common internship/engineering/cohort words. A complete primary
  title match earns fraction 1; a complete secondary match earns 0.8. When related
  titles are allowed, partial matches earn half that fraction × token coverage.
  Enabled role/duty-section matches use the same half-credit rule. Company
  background text does not establish a technical role or candidate skill.
- Skills: reuse `extract_job_evidence` and `skill_groups`. Required groups count
  2, preferred/duty groups count 1; an alternative language/framework/simulator
  group counts once. Coverage counts groups with an anchored supported feature.
  Repeated keywords do not multiply credit. Degree-only text adds no skill credit.
- Projects: apply the same weighted group coverage to each project's supported
  features, then use the best single project. Multiple projects do not accumulate
  bonuses; changing the feature mappings can change scores. Project-ID ties use
  lexical order for a stable explanation, with no effect on the numeric score.
- Location: reuse `assess_location`, including remote/country ambiguity flags
  and configured preference order. A known US location outside a valid preference
  subset earns zero; it does not imply applicant ineligibility.

This technical match score includes the configured role/location preference
components. It is a lexical heuristic over recognized features, not a probability
of success or coverage of every qualification. Sparse evidence is flagged. The
fixed vocabulary and complex/negated language still require human source review.
No company-background, project-name, eligibility or application-state bonus exists.

Each result contains component fractions, points, calculations, matched/missing
skill alternatives, candidate source-line citations, logical job-field/parsed-
section citations, configuration references and fingerprints of the candidate
snapshot, preferences and job input. Candidate anchors/configuration are CONFIRMED
within their supplied snapshots; lexical job matches are INFERRED. Application
notes, receipts and raw candidate document contents never enter the output.

## Eligibility, relevance and application state

Eligibility is assessed before the independent technical score. Candidate degree,
graduation and work authorization remain UNKNOWN in the feature-only schema;
illustrative target preferences do not establish those applicant facts.

Explicit PhD-only or another single internship cohort can produce POLICY_EXCLUDED
under the corresponding configured policy. This describes a selection policy,
not confirmed applicant ineligibility. Ambiguous cohorts and unknown sponsorship
remain UNKNOWN and require human review. No result is automatically removed.

Stored relevance classifications remain separate; without a usable stored
classification the existing relevance backend supplies one. Application status
is an annotation only. Untracked jobs display NOT_STARTED as a read-only view;
no application record is created. Ordering uses descending displayed score, then
normalized company/title/location/source/ID/URL and database ID; eligibility,
relevance and application status are not ordering keys.

## Offline example using only P3A fixtures

Use the installed source `.venv` from the [README](../README.md), and run the following
Python code locally. It needs no generated or user database and does not restore
the full CLI. This example intentionally supplies no application records.

```python
from internship_agent.candidate_evidence import load_candidate_evidence
from internship_agent.config import load_config
from internship_agent.demo import FIXTURE_DIRECTORY, PREFERENCES, load_demo_fixtures
from internship_agent.models import JobMetadata, JobRecord
from internship_agent.ranking import rank_jobs

candidate = load_candidate_evidence(
    FIXTURE_DIRECTORY / "evidence", reference_prefix="demo/fixtures/evidence"
)
entries, _ = load_demo_fixtures()
jobs = [JobRecord(i, entry.job, "SYNTHETIC_FIXTURE")
        for i, entry in enumerate(entries, 1)]
metadata = {job.id: JobMetadata(job.id, **entry.metadata)
            for job, entry in zip(jobs, entries)}
results = rank_jobs(jobs, candidate, load_config(PREFERENCES), metadata=metadata)
for result in results:
    print(result.job_id, result.technical_match_score, result.eligibility.status)
```

| Fictional job ID | Short role | Score | Eligibility annotation |
|---|---|---:|---|
| demo-001 | Robotics Software | 91.00 | UNKNOWN |
| demo-004 | Computer Vision | 88.00 | UNKNOWN |
| demo-003 | Simulation | 75.00 | UNKNOWN |
| demo-002 | Machine Learning | 72.67 | UNKNOWN |
| demo-008 | Fall Simulation | 66.00 | POLICY_EXCLUDED |
| demo-006 | Robotics Machine Learning | 63.50 | UNKNOWN |
| demo-005 | Perception | 55.00 | UNKNOWN |
| demo-007 | PhD-only ML Research | 36.00 | POLICY_EXCLUDED |
| demo-010 | Mechanical Engineering | 12.00 | UNKNOWN |
| demo-009 | Marketing | 6.00 | UNKNOWN |

For demo-001, contributions are 30 role + 30 skills + 25 project + 6 location.
Python/evaluation job evidence traces to the duties section; candidate credit
traces to the experience/verification source lines and Demo Grid Navigation's
feature mapping. No physical robotics experience is inferred.

For demo-002, contributions are 24 + 20 + 16.67 + 12. PyTorch and evaluation
match; recognized model-training evidence is absent from the candidate mapping.
Removing PyTorch from a reviewed synthetic mapping and its project features
reduces this score to 54.33. Removing only Demo Shape Classifier reduces it to
64.33 while skills credit stays unchanged. Editing source documents requires
reviewing anchors and updating hashes before the loader accepts the mapping.

Computer Vision's high score covers only its one recognized evaluation group;
the result explicitly warns about sparse evidence. It does not assert broad
computer-vision expertise. Mechanical/marketing scores come only from location
preferences, with zero skills/project credit.

## Recovery safety and deferred functionality

P3B.3A integrates these unchanged results into the [small offline CLI](CLI_GUIDE.md).
Its demo-rank command accepts only the explicitly selected validated synthetic
database, renders these component/evidence objects and performs no writes.
P3B.3B's [offline dashboard](DASHBOARD_DEMO_GUIDE.md) renders the same unchanged
rankings and evidence through shared read-only synthetic services.

P3B.1 found and fixed a P3A recovery gap: compatible run markers alone did not
exclude unrelated tables/triggers. Recovery now checks the exact fresh public
schema read-only, rejects extra job identity aliases/checkpoint payloads and
preserves unrelated or edited data. Older schemas are refused without migration
or backup. Edited run diagnostics and incomplete completed-item payloads also
cause refusal before writable access. Nine synthetic regressions cover these
cases; normal P3A recovery and
no-overwrite protections remain tested. This is a compatibility/content check,
not cryptographic ownership authentication or a general user-database repair tool.

The generic ranking backend is available. P3B.2A adds a separate
[read-only resume review/proposal backend](RESUME_REVIEW_GUIDE.md). Broader ranking
report integration, resume editing/updating and personalized interfaces remain deferred.
The separate public offline Dashboard is now available in P3B.3B.
Original withheld personalized modules and tests were not accessed or copied.
No live discovery, forms, submission, scheduler, service, remote, license or
publication was added. Current Windows onboarding and verified offline source
installation are in the [README](../README.md) and [P4A report](CLEAN_INSTALL_VALIDATION.md).
Safe broader integrations, regression coverage, provenance/license review,
unverified platforms and publication approval remain release blockers.
