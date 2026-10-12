"""Generic reviewed feature/project mappings anchored to explicit local sources."""

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re

SOURCE_FILES = ("profile.md", "experience_bank.md", "verification_report.md")


@dataclass(frozen=True)
class CandidateEvidence:
    supported: frozenset[str]
    projects: tuple[dict, ...]
    references: dict[str, tuple[str, ...]]
    limitations: tuple[str, ...]
    fingerprints: dict[str, str]
    mapping_fingerprint: str
    limitation_references: dict[str, tuple[str, ...]] = field(default_factory=dict)


def load_candidate_evidence(directory="candidate", mapping_path=None, *, reference_prefix="candidate"):
    """Fail closed when reviewed evidence or source versions no longer match.

    This verifies anchors and provenance, not the truth of arbitrary new claims.
    Adding features requires reviewing the mapping against all three sources.
    Reports use references/feature labels, never raw candidate document text.
    """
    if (not isinstance(reference_prefix, str)
            or not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", reference_prefix)
            or any(part in {".", ".."} for part in reference_prefix.split("/"))):
        raise ValueError("Candidate reference prefix must be a safe repository-relative label")
    directory = Path(directory)
    path = Path(mapping_path) if mapping_path else directory / "ranking_features.json"
    raw = path.read_bytes()
    mapping = json.loads(raw.decode("utf-8"))
    if (not isinstance(mapping, dict) or type(mapping.get("version")) is not int
            or mapping.get("version") != 1 or mapping.get("review_basis") != "local_source_review"):
        raise ValueError("Candidate mapping requires version 1 and documented local_source_review")
    documents = {name: (directory / name).read_bytes() for name in SOURCE_FILES}
    fingerprints = {name: hashlib.sha256(value).hexdigest() for name, value in documents.items()}
    if mapping.get("source_sha256") != fingerprints:
        raise ValueError("Candidate sources changed; review and update ranking_features.json before scoring")
    texts = {name: raw.decode("utf-8") for name, raw in documents.items()}
    if any(not isinstance(mapping.get(name, []), list) for name in ("features", "projects", "limitations")):
        raise ValueError("Candidate features, projects and limitations must be lists")

    def references(entries):
        if not isinstance(entries, list) or not entries:
            raise ValueError("Each supported feature/project needs source anchors")
        result = []
        for entry in entries:
            name, quote = entry.get("file"), entry.get("quote")
            if name not in texts or not isinstance(quote, str) or len(quote) < 8 or quote not in texts[name]:
                raise ValueError("Candidate mapping contains missing/invalid source anchors")
            line = texts[name][:texts[name].index(quote)].count("\n") + 1
            result.append(f"{reference_prefix}/{name}:{line}")
        return tuple(result)

    supported, refs = set(), {}
    for feature in mapping.get("features", []):
        key = feature.get("id")
        if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", key) or key in refs:
            raise ValueError("Candidate feature IDs must be unique safe identifiers")
        if feature.get("status") != "SUPPORTED":
            raise ValueError("Only SUPPORTED features may appear in the scoring mapping")
        anchors = feature.get("evidence", [])
        if not any(a.get("file") == "verification_report.md" for a in anchors):
            raise ValueError("Supported features must reference the verification report")
        refs[key] = references(anchors)
        supported.add(key)
    projects, project_ids = [], set()
    for project in mapping.get("projects", []):
        if (not re.fullmatch(r"[a-z][a-z0-9_]*", project.get("id", ""))
                or project["id"] in project_ids):
            raise ValueError("Invalid candidate project ID")
        project_ids.add(project["id"])
        if (not isinstance(project.get("features"), list) or not project["features"]
                or any(not isinstance(key, str) for key in project["features"])
                or len(project["features"]) != len(set(project["features"]))):
            raise ValueError("Project features must be a non-empty unique list")
        if not set(project.get("features", [])) <= supported:
            raise ValueError("Project mapping contains an unverified feature")
        projects.append({"id": project["id"], "features": tuple(project["features"]),
                         "references": references(project.get("evidence"))})
    limitations, limitation_refs = [], {}
    for limitation in mapping.get("limitations", []):
        anchors = references(limitation.get("evidence"))
        if limitation.get("id") not in ("simulation_only", "generalization_unestablished", "publication_pending"):
            raise ValueError("Unsupported candidate limitation label")
        if limitation["id"] in limitation_refs:
            raise ValueError("Duplicate candidate limitation label")
        limitation_refs[limitation["id"]] = anchors
        limitations.append(limitation["id"])
    # Empty collections assert no skills/projects and earn no evidence-based
    # credit. Every positive claim still requires the same hashes and anchors.
    return CandidateEvidence(frozenset(supported), tuple(projects), refs, tuple(limitations),
                             fingerprints, hashlib.sha256(raw).hexdigest(), limitation_refs)
