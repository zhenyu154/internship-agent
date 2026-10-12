"""Generic, deterministic ranking of explicitly supplied evidence and job records.

No file loading, database writes, network access or candidate/project affinity
tables. Scores are lexical heuristics, separate from eligibility and application
state. Source anchors confirm provenance within the supplied snapshot, not truth.
"""

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from fractions import Fraction
import hashlib
import json
import re
from types import SimpleNamespace

from .applications import validate_status
from .candidate_evidence import CandidateEvidence, SOURCE_FILES
from .config import validate_config
from .models import ApplicationRecord, JobMetadata, JobRecord
from .ranking_job_evidence import SKILLS, extract_job_evidence, skill_groups
from .ranking_locations import assess_location
from .relevance import (
    EXCLUDED, MAIN_SHORTLIST, NEEDS_REVIEW, classify_greenhouse_job,
    explicit_phd_only, source_internship_terms,
)

COMPONENTS = ("role_alignment", "technical_skills_match", "research_project_relevance", "location_preference")


@dataclass(frozen=True)
class EvidenceReference:
    source: str
    reference: str
    state: str


@dataclass(frozen=True)
class SkillMatch:
    importance: str
    alternatives: tuple[str, ...]
    matched: tuple[str, ...]
    evidence: tuple[EvidenceReference, ...]


@dataclass(frozen=True)
class ScoreComponent:
    name: str
    weight: int
    fraction: float
    points: float
    calculation: str
    evidence: tuple[EvidenceReference, ...]
    project_id: str | None = None


@dataclass(frozen=True)
class EligibilityAssessment:
    status: str
    checks: tuple[str, ...]
    evidence: tuple[EvidenceReference, ...]


@dataclass(frozen=True)
class RankingResult:
    job_id: int
    technical_match_score: float
    components: tuple[ScoreComponent, ...]
    skill_matches: tuple[SkillMatch, ...]
    eligibility: EligibilityAssessment
    relevance_category: str
    application_status: str
    limitations: tuple[str, ...]
    limitation_evidence: tuple[EvidenceReference, ...]
    warnings: tuple[str, ...]
    candidate_fingerprint: str
    configuration_fingerprint: str
    job_fingerprint: str


def _fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


def _candidate_snapshot(candidate: CandidateEvidence) -> CandidateEvidence:
    if not isinstance(candidate, CandidateEvidence):
        raise ValueError("Explicit reviewed CandidateEvidence is required")
    candidate = CandidateEvidence(
        frozenset(candidate.supported), tuple(dict(project) for project in candidate.projects),
        {key: tuple(refs) for key, refs in candidate.references.items()}, tuple(candidate.limitations),
        dict(candidate.fingerprints), candidate.mapping_fingerprint,
        {key: tuple(refs) for key, refs in candidate.limitation_references.items()},
    )
    if (set(candidate.fingerprints) != set(SOURCE_FILES)
            or any(not re.fullmatch(r"[a-fA-F0-9]{64}", value) for value in
                   (*candidate.fingerprints.values(), candidate.mapping_fingerprint))):
        raise ValueError("Reviewed candidate source and mapping fingerprints are required")
    if not candidate.supported <= SKILLS.keys():
        raise ValueError("Candidate features must use the public ranking feature vocabulary")

    def validate_references(refs):
        if not refs or any(not isinstance(ref, str) or not re.fullmatch(
                r"(?:[A-Za-z0-9_.-]+/)+(?:profile\.md|experience_bank\.md|verification_report\.md):[1-9][0-9]*",
                ref) or any(part in {".", ".."} for part in ref.split("/")[:-1]) for ref in refs):
            raise ValueError("Source references must be anchored, repository-relative labels")

    for feature in candidate.supported:
        refs = candidate.references.get(feature, ())
        validate_references(refs)
        if not any("/verification_report.md:" in ref for ref in refs):
            raise ValueError("Supported candidate skills require verification-report anchors")
    project_ids = set()
    for project in candidate.projects:
        identifier = project.get("id", "")
        features = project.get("features", ())
        if (not isinstance(identifier, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", identifier)
                or identifier in project_ids or not isinstance(features, (tuple, list))
                or not features or len(set(features)) != len(features)
                or not set(features) <= candidate.supported):
            raise ValueError("Projects need unique generic IDs and supported feature mappings")
        project_ids.add(identifier)
        validate_references(project.get("references", ()))
        project["features"] = tuple(features)
        project["references"] = tuple(project["references"])
    for limitation in candidate.limitations:
        if limitation not in {"simulation_only", "generalization_unestablished", "publication_pending"}:
            raise ValueError("Unsupported candidate limitation")
        validate_references(candidate.limitation_references.get(limitation, ()))
    return candidate


def _candidate_fingerprint(candidate):
    return _fingerprint({
        "supported": sorted(candidate.supported),
        "projects": sorted(candidate.projects, key=lambda project: project["id"]),
        "references": {key: candidate.references[key] for key in sorted(candidate.supported)},
        "limitations": sorted(candidate.limitations), "limitation_references": candidate.limitation_references,
        "source_fingerprints": candidate.fingerprints, "mapping_fingerprint": candidate.mapping_fingerprint,
    })


def _candidate_refs(refs):
    return tuple(EvidenceReference("candidate", reference, "CONFIRMED") for reference in refs)


def _job_ref(record, field):
    return EvidenceReference("job", f"job:{record.id}:{field}", "INFERRED")


def _unique_refs(refs):
    return tuple(dict.fromkeys(refs))


def _tokens(text):
    text = re.sub(r"\bml\b", "machine learning", text.casefold())
    return frozenset(re.findall(r"[a-z]+", text)) - {
        "intern", "internship", "engineer", "engineering", "developer", "co", "op",
        "summer", "fall", "spring", "winter",
    }


def _role_alignment(record, evidence, preferences):
    candidates = [(Fraction(0), ())]
    sources = [(_tokens(record.job.title), _job_ref(record, "title"), True)]
    if preferences["roles"]["match_job_description_content"] and evidence.features:
        for section in ("duties", "role"):
            sources.extend((_tokens(line), _job_ref(record, f"description:{section}:{index}"), False)
                           for index, line in enumerate(getattr(evidence, section), 1))
    for family, maximum in (("primary", Fraction(1)), ("secondary", Fraction(4, 5))):
        for index, role in enumerate(preferences["roles"][family]):
            target = _tokens(role)
            if not target:
                continue
            for tokens, source, title in sources:
                coverage = Fraction(len(target & tokens), len(target))
                if coverage == 1 and title:
                    fraction = maximum
                elif title and not preferences["roles"]["allow_related_job_titles"]:
                    continue
                else:
                    fraction = maximum * coverage / 2
                if fraction:
                    candidates.append((fraction, (source, EvidenceReference(
                        "configuration", f"config:roles:{family}:{index}", "CONFIRMED"))))
    # Stable source selection for ties; there are no project-identity affinities.
    return sorted(candidates, key=lambda item: (-item[0], tuple(ref.reference for ref in item[1])))[0]


def _eligibility(record, metadata, preferences):
    # Assess before computing the independent score; never assert applicant facts
    # from illustrative target preferences or use policy/status as scoring input.
    checks = ["Candidate degree/graduation are UNKNOWN in the feature evidence schema.",
              "Candidate work authorization is UNKNOWN; sponsorship needs human review."]
    refs = [EvidenceReference("configuration", "config:eligibility:candidate_work_authorization", "UNKNOWN")]
    excluded = False
    terms = source_internship_terms(record.job.title, record.job.description)
    target = preferences["target"]["internship_term"]
    if len(terms) == 1 and target not in terms:
        checks.append("Stored posting explicitly names another internship cohort.")
        refs.append(_job_ref(record, "title+description:internship_term"))
        refs.extend((EvidenceReference("configuration", "config:target:internship_term", "CONFIRMED"),
                     EvidenceReference("configuration", "config:eligibility:explicitly_wrong_internship_term", "CONFIRMED")))
        excluded = preferences["eligibility"]["explicitly_wrong_internship_term"] == "EXCLUDE"
    elif terms == {target}:
        checks.append("Stored posting names the configured cohort; actual eligibility remains UNKNOWN.")
        refs.append(_job_ref(record, "title+description:internship_term"))
        refs.append(EvidenceReference("configuration", "config:target:internship_term", "CONFIRMED"))
    else:
        checks.append("Internship cohort is UNKNOWN or ambiguous; human review required.")
    if explicit_phd_only(record.job.title, record.job.description):
        checks.append("Stored posting has PhD-only language; applying the configured PhD-only policy.")
        refs.append(_job_ref(record, "title+description:phd_only"))
        refs.append(EvidenceReference("configuration", "config:eligibility:phd_only", "CONFIRMED"))
        excluded |= preferences["eligibility"]["phd_only"] == "EXCLUDE"
    if metadata is None or metadata.work_authorization == "UNKNOWN":
        checks.append("Posting work authorization is UNKNOWN; this is not an automatic rejection.")
    else:
        checks.append("Stored authorization text requires review; it does not confirm applicant eligibility.")
        refs.append(_job_ref(record, "metadata:work_authorization"))
    return EligibilityAssessment("POLICY_EXCLUDED" if excluded else "UNKNOWN", tuple(checks), tuple(refs))


def _rank(record, candidate, preferences, metadata, application):
    if not isinstance(record, JobRecord) or type(record.id) is not int or record.id <= 0:
        raise ValueError("Ranking requires a persisted JobRecord with a positive ID")
    if metadata is not None and metadata.job_id != record.id:
        raise ValueError("Job metadata identity does not match the ranked job")
    if application is not None:
        if application.job_id != record.id:
            raise ValueError("Application identity does not match the ranked job")
        validate_status(application.status)
    eligibility = _eligibility(record, metadata, preferences)
    job_evidence = extract_job_evidence(record.job.description)
    groups = skill_groups(job_evidence)
    supported = candidate.supported
    if "simulation_only" in candidate.limitations:
        supported = supported - {"real_robot", "production"}
    matches, denominator, numerator = [], 0, 0
    for importance, alternatives, line in groups:
        section = {"REQUIRED": "required", "PREFERRED": "preferred", "DUTY": "duties"}[importance]
        index = getattr(job_evidence, section).index(line) + 1
        matched = tuple(sorted(set(alternatives) & supported))
        refs = [_job_ref(record, f"description:{section}:{index}")]
        refs.extend(reference for key in matched for reference in _candidate_refs(candidate.references[key]))
        matches.append(SkillMatch(importance, alternatives, matched, _unique_refs(refs)))
        weight = 2 if importance == "REQUIRED" else 1
        denominator += weight
        numerator += weight if matched else 0
    skill_fraction = Fraction(numerator, denominator) if denominator else Fraction(0)
    project_candidates = []
    for project in candidate.projects:
        features = set(project["features"]) & supported
        covered = sum((2 if match.importance == "REQUIRED" else 1)
                      for match in matches if features & set(match.alternatives))
        fraction = Fraction(covered, denominator) if denominator else Fraction(0)
        project_candidates.append((fraction, project))
    project_candidates.sort(key=lambda item: (-item[0], item[1]["id"]))
    project_fraction, project = project_candidates[0] if project_candidates else (Fraction(0), None)
    role_fraction, role_refs = _role_alignment(record, job_evidence, preferences)
    location = assess_location(record.job.location, preferences)
    project_refs = ()
    if project is not None and project_fraction:
        project_features = set(project["features"]) & supported
        project_refs = _unique_refs((*_candidate_refs(project["references"]),
            *(ref for match in matches if project_features & set(match.alternatives) for ref in match.evidence)))
    fractions = (role_fraction, skill_fraction, project_fraction, Fraction(str(location.fraction)))
    references = (role_refs, _unique_refs(ref for match in matches for ref in match.evidence),
                  project_refs, (_job_ref(record, "location"), EvidenceReference(
                      "configuration", "config:locations:preference_order", "CONFIRMED")))
    components = []
    for name, fraction, refs in zip(COMPONENTS, fractions, references):
        weight = preferences["ranking"]["weights"][name]
        components.append(ScoreComponent(name, weight, float(fraction), round(float(weight * fraction), 2),
            f"{weight} × {fraction} (coverage of recognized evidence only)",
            _unique_refs((*refs, EvidenceReference("configuration", f"config:ranking:weights:{name}", "CONFIRMED"))),
            project["id"] if name == "research_project_relevance" and project is not None and fraction else None))
    warnings = ["Lexical heuristic: recognized skill coverage is not coverage of every qualification.",
                "Source anchors confirm provenance in the supplied snapshot, not independently verified facts."]
    warnings.extend(location.flags)
    if len(groups) < 2:
        warnings.append("Sparse job evidence: fewer than two recognized technical skill groups.")
    if not candidate.supported:
        warnings.append("Candidate skill evidence is missing; skills credit is zero.")
    if not candidate.projects:
        warnings.append("Candidate project evidence is missing; project credit is zero.")
    for limitation in sorted(candidate.limitations):
        warnings.append(f"Candidate limitation retained: {limitation}.")
    if metadata is not None and metadata.relevance_category in {MAIN_SHORTLIST, NEEDS_REVIEW, EXCLUDED}:
        category = metadata.relevance_category
    else:
        fields = {name: getattr(metadata, name, "UNKNOWN") for name in
                  ("internship_term", "degree_requirements", "graduation_window", "work_authorization")}
        category = classify_greenhouse_job(SimpleNamespace(**asdict(record.job), **fields), preferences).category
    return RankingResult(record.id, round(sum(component.points for component in components), 2), tuple(components),
        tuple(matches), eligibility, category, application.status if application else "NOT_STARTED",
        tuple(sorted(candidate.limitations)),
        _unique_refs(ref for limitation in sorted(candidate.limitations)
                     for ref in _candidate_refs(candidate.limitation_references[limitation])),
        tuple(warnings), _candidate_fingerprint(candidate),
        _fingerprint(preferences), _fingerprint(asdict(record.job)))


def rank_job(record: JobRecord, candidate: CandidateEvidence, preferences: dict, *,
             metadata: JobMetadata | None = None, application: ApplicationRecord | None = None) -> RankingResult:
    """Rank one record; callers explicitly load reviewed public evidence first."""
    preferences = validate_config(json.loads(json.dumps(preferences)))
    return _rank(record, _candidate_snapshot(candidate), preferences, metadata, application)


def rank_jobs(records: Iterable[JobRecord], candidate: CandidateEvidence, preferences: dict, *,
              metadata: Mapping[int, JobMetadata] | None = None,
              applications: Mapping[int, ApplicationRecord] | None = None) -> tuple[RankingResult, ...]:
    """Sort by score, then normalized job identity; never by eligibility/status."""
    preferences = validate_config(json.loads(json.dumps(preferences)))
    candidate = _candidate_snapshot(candidate)
    records = tuple(records)
    if len({record.id for record in records}) != len(records):
        raise ValueError("Ranked records must have unique job IDs")
    metadata, applications = metadata or {}, applications or {}
    rows = [(record, _rank(record, candidate, preferences, metadata.get(record.id), applications.get(record.id)))
            for record in records]
    rows.sort(key=lambda item: (-item[1].technical_match_score,
              *(getattr(item[0].job, field).casefold() for field in
                ("company", "title", "location", "source", "source_job_id", "url")), item[0].id))
    return tuple(result for _, result in rows)
