"""Read-only general-resume extraction and anchored, exact-text proposals.

Explicit files only. No edits, approvals, application state or job inputs.
"""

from dataclasses import asdict, dataclass
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from .candidate_evidence import CandidateEvidence, SOURCE_FILES, load_candidate_evidence

ENGINE_VERSION = "resume-review-v1"
MAX_BYTES = 4 * 1024 * 1024
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
OFFICE_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
STATUSES = {"CONFIRMED", "PENDING", "INFERRED", "UNKNOWN"}
QUALIFIERS = {
    "deployment": {"simulation", "physical", "not_applicable", "unknown"},
    "evaluation": {"seen", "held_out", "both", "not_applicable", "unknown"},
    "result": {"measured", "inferred", "not_applicable", "unknown"},
    "publication": {"accepted", "pending", "not_applicable", "unknown"},
}


@dataclass(frozen=True)
class ResumeBlock:
    block_id: str
    text: str
    reference: str
    start: int | None = None
    end: int | None = None


@dataclass(frozen=True)
class ResumeDocument:
    source_label: str
    source_sha256: str
    format: str
    supported: bool
    blocks: tuple[ResumeBlock, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class SourceAnchor:
    reference: str
    quote: str
    source_sha256: str


@dataclass(frozen=True)
class ResumeClaim:
    claim_id: str
    text: str
    status: str
    anchors: tuple[SourceAnchor, ...]
    limitations: tuple[str, ...]
    qualifiers: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ProposalRule:
    rule_id: str
    before: str
    claim_id: str


@dataclass(frozen=True)
class ResumeEvidence:
    claims: tuple[ResumeClaim, ...]
    rules: tuple[ProposalRule, ...]
    candidate_fingerprint: str
    source_fingerprints: tuple[tuple[str, str], ...]
    mapping_sha256: str
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class ContentAssessment:
    block_id: str
    before: str
    evidence_status: str
    claim_id: str | None
    anchors: tuple[SourceAnchor, ...]
    uncertainties: tuple[str, ...]


@dataclass(frozen=True)
class ProposedChange:
    change_id: str
    action: str
    block_id: str
    resume_reference: str
    rule_id: str
    claim_id: str
    before: str
    after: str
    before_status: str
    evidence_status: str
    anchors: tuple[SourceAnchor, ...]
    qualifiers: tuple[tuple[str, str], ...]
    limitations: tuple[str, ...]
    uncertainties: tuple[str, ...]


@dataclass(frozen=True)
class ResumeProposal:
    engine_version: str
    resume_sha256: str
    evidence_fingerprint: str
    proposal_fingerprint: str
    supported_document: bool
    changes: tuple[ProposedChange, ...]
    assessments: tuple[ContentAssessment, ...]
    limitations: tuple[str, ...]


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _fingerprint(value) -> str:
    return _hash(json.dumps(value, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":")).encode("utf-8"))


def _label(value: str) -> str:
    if (not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", value)
            or any(part in {".", ".."} for part in value.split("/"))):
        raise ValueError("Source label must be explicitly supplied and repository-relative")
    return value


def _read(path) -> bytes:
    path = Path(path)
    if any(component.is_symlink() or component.is_junction() for component in (path, *path.parents)):
        raise ValueError("Explicit inputs cannot traverse symlinks or junctions")
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Input exceeds the bounded review size")
    return raw


def _xml(raw):
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("DTD/entity content is unsupported")
    # OOXML inputs are intentionally limited to UTF-8 here.
    return ET.fromstring(raw.decode("utf-8"))


def _unsupported(label, raw, format, reason):
    return ResumeDocument(label, _hash(raw), format, False, (), (reason,))


def _docx(raw, label):
    try:
        with ZipFile(BytesIO(raw)) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            required = {"[Content_Types].xml", "_rels/.rels", "word/document.xml"}
            if (len(names) != len(set(names)) or set(names) != required
                    or sum(info.file_size for info in infos) > MAX_BYTES
                    or any(info.flag_bits & 1 for info in infos)):
                return _unsupported(label, raw, "docx", "DOCX package parts, encryption or size are unsupported; no content flattened.")
            types = _xml(archive.read("[Content_Types].xml"))
            relationships = _xml(archive.read("_rels/.rels"))
            root = _xml(archive.read("word/document.xml"))
            if types.tag != f"{{{CT}}}Types" or relationships.tag != f"{{{REL}}}Relationships":
                raise ValueError("Unsupported package metadata")
            for node in types:
                allowed = (node.tag == f"{{{CT}}}Default" and node.get("Extension") == "rels"
                           and node.get("ContentType") == "application/vnd.openxmlformats-package.relationships+xml")
                allowed |= (node.tag == f"{{{CT}}}Default" and node.get("Extension") == "xml"
                            and node.get("ContentType") == "application/xml")
                allowed |= (node.tag == f"{{{CT}}}Override" and node.get("PartName") == "/word/document.xml"
                            and node.get("ContentType") == "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml")
                if not allowed:
                    raise ValueError("Unsupported content type")
            if (len(relationships) != 1 or relationships[0].tag != f"{{{REL}}}Relationship"
                    or relationships[0].get("Target") != "word/document.xml"
                    or relationships[0].get("Type") != OFFICE_REL
                    or relationships[0].get("TargetMode") is not None):
                raise ValueError("Unsupported or external relationship")
            # Strict paragraph/run subset. Tables, fields, hyperlinks, revisions,
            # hidden text, inherited styles, drawings and other stories fail closed.
            children = {
                "document": {"body"}, "body": {"p", "sectPr"}, "p": {"r", "pPr"},
                "r": {"rPr", "t", "tab", "br", "cr"},
                "pPr": {"spacing", "jc", "ind", "keepNext", "keepLines"},
                "rPr": {"b", "i", "u", "sz", "szCs", "rFonts", "color"},
                "sectPr": {"pgSz", "pgMar"},
            }
            if root.tag != f"{{{W}}}document" or len(root) != 1:
                raise ValueError("Unsupported main document")
            for node in root.iter():
                if not node.tag.startswith(f"{{{W}}}"):
                    raise ValueError("Unsupported namespace")
                local = node.tag[len(W) + 2:]
                if local not in children and local not in {"t", "tab", "br", "cr", "spacing", "jc", "ind", "keepNext", "keepLines", "b", "i", "u", "sz", "szCs", "rFonts", "color", "pgSz", "pgMar"}:
                    raise ValueError("Unsupported DOCX structure")
                if any(child.tag not in {f"{{{W}}}{name}" for name in children.get(local, ())} for child in node):
                    raise ValueError("Unsupported nested DOCX structure")
                if (node.text and node.text.strip() and local != "t") or (node.tail and node.tail.strip()):
                    raise ValueError("Unmapped XML text")
                if local == "br" and node.get(f"{{{W}}}type", "textWrapping") != "textWrapping":
                    raise ValueError("Page/column breaks are unsupported")
                if local == "rFonts" and any("Theme" in key for key in node.attrib):
                    raise ValueError("Inherited font settings are unsupported")
            blocks = []
            body = root[0]
            for index, paragraph in enumerate(body.findall(f"{{{W}}}p"), 1):
                parts = []
                for run in paragraph.findall(f"{{{W}}}r"):
                    for node in run:
                        if node.tag == f"{{{W}}}t": parts.append(node.text or "")
                        elif node.tag == f"{{{W}}}tab": parts.append("\t")
                        elif node.tag in {f"{{{W}}}br", f"{{{W}}}cr"}: parts.append("\n")
                blocks.append(ResumeBlock(f"paragraph-{index}", "".join(parts), f"{label}:paragraph:{index}"))
            return ResumeDocument(label, _hash(raw), "docx", True, tuple(blocks),
                ("Extraction covers only the supported paragraph/run subset; layout/page appearance is not validated.",))
    except (BadZipFile, ET.ParseError, UnicodeError, ValueError, KeyError, RuntimeError):
        return _unsupported(label, raw, "docx", "Unsupported or malformed DOCX structure; no partial extraction or edits.")


def extract_resume(raw: bytes, *, format: str, source_label: str) -> ResumeDocument:
    """Exact text from explicit bytes; unsupported structures return no blocks."""
    label = _label(source_label)
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        raise ValueError("Resume must be explicitly supplied as bounded bytes")
    if format == "docx":
        return _docx(raw, label)
    if format != "txt":
        return _unsupported(label, raw, format, "Only UTF-8 TXT and a conservative DOCX subset are supported.")
    try:
        text = raw.decode("utf-8")
    except UnicodeError:
        return _unsupported(label, raw, "txt", "Resume text must be UTF-8; no encoding guessing.")
    if "\x00" in text or text.startswith("\ufeff"):
        return _unsupported(label, raw, "txt", "NUL or BOM text is unsupported; exact source is preserved.")
    offset, blocks = 0, []
    for index, line in enumerate(text.splitlines(keepends=True), 1):
        # Preserve Unicode, indentation, tabs and trailing spaces. Newline bytes
        # are captured by offsets/hash, not silently folded into paragraph text.
        content = line[:-2] if line.endswith("\r\n") else line[:-1] if line.endswith(("\n", "\r")) else line
        blocks.append(ResumeBlock(f"line-{index}", content, f"{label}:line:{index}", offset, offset + len(content)))
        offset += len(line)
    return ResumeDocument(label, _hash(raw), "txt", True, tuple(blocks), ())


def load_resume(path, *, source_label: str) -> ResumeDocument:
    """No default path, directory search, edits or format guessing."""
    _label(source_label)
    path = Path(path)
    return extract_resume(_read(path), format=path.suffix.lower().removeprefix("."), source_label=source_label)


def load_resume_evidence(*, candidate_directory, claims_path, sources: dict[str, Path],
                         candidate_reference_prefix: str, source_reference_prefix: str) -> ResumeEvidence:
    """Load an explicit reviewed claim ledger bound to existing candidate sources.

    sources maps safe file labels to explicitly supplied supplemental review files.
    Claim text must be verbatim in a source anchor, preventing generated metrics,
    degree/date/publication promotions. Semantic truth remains human-reviewed.
    """
    _label(candidate_reference_prefix)
    _label(source_reference_prefix)
    for name in sources:
        if (not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]+\.md", name)
                or name in SOURCE_FILES):
            raise ValueError("Supplemental source labels must be safe Markdown filenames")
    directory = Path(candidate_directory)
    for name in (*SOURCE_FILES, "ranking_features.json"):
        _read(directory / name)  # Bounded, no redirected inputs before existing loader.
    candidate = load_candidate_evidence(directory, reference_prefix=candidate_reference_prefix)
    if not isinstance(candidate, CandidateEvidence):
        raise ValueError("Reviewed candidate evidence is required")
    raw = _read(claims_path)
    mapping = json.loads(raw.decode("utf-8"))
    header = {"version", "notice", "candidate_mapping_sha256", "candidate_source_sha256", "source_sha256", "claims", "rules", "limitations"}
    if (not isinstance(mapping, dict) or set(mapping) != header or type(mapping["version"]) is not int
            or mapping["version"] != 1 or not isinstance(mapping["notice"], str)):
        raise ValueError("Unsupported reviewed resume evidence contract")
    if (mapping["candidate_mapping_sha256"] != candidate.mapping_fingerprint
            or mapping["candidate_source_sha256"] != candidate.fingerprints):
        raise ValueError("Candidate evidence changed; review the claim ledger before proposals")
    texts = {name: _read(path) for name, path in sources.items()}
    fingerprints = {name: _hash(content) for name, content in texts.items()}
    if mapping["source_sha256"] != fingerprints:
        raise ValueError("Resume evidence sources changed or are missing; review required")
    texts = {name: raw.decode("utf-8") for name, raw in texts.items()}
    if any(not isinstance(mapping[field], list) for field in ("claims", "rules", "limitations")):
        raise ValueError("Resume claims, rules and limitations must be lists")

    def strings(values):
        if not isinstance(values, list) or any(not isinstance(value, str) or not value for value in values):
            raise ValueError("Limitations must be explicit non-empty strings")
        return tuple(values)

    claims, identifiers = [], set()
    for claim in mapping["claims"]:
        if (not isinstance(claim, dict) or set(claim) != {"id", "text", "status", "evidence", "limitations", "qualifiers"}
                or not isinstance(claim.get("id"), str) or not re.fullmatch(r"[a-z][a-z0-9_]*", claim["id"])
                or claim["id"] in identifiers or not isinstance(claim["status"], str)
                or claim["status"] not in STATUSES or not isinstance(claim["text"], str) or not claim["text"]):
            raise ValueError("Claims require unique generic IDs, exact text and evidence status")
        identifiers.add(claim["id"])
        qualifiers = claim["qualifiers"]
        if (not isinstance(qualifiers, dict) or set(qualifiers) != set(QUALIFIERS)
                or any(not isinstance(value, str) or value not in QUALIFIERS[key] for key, value in qualifiers.items())):
            raise ValueError("Experimental qualifiers must be explicit reviewed enum values")
        if "simulation_only" in candidate.limitations and qualifiers["deployment"] == "physical":
            raise ValueError("Physical deployment contradicts reviewed simulation-only evidence")
        anchors = []
        if not isinstance(claim["evidence"], list) or not claim["evidence"]:
            raise ValueError("Every claim needs exact source anchors, including pending claims")
        for anchor in claim["evidence"]:
            if not isinstance(anchor, dict) or set(anchor) != {"file", "quote"}:
                raise ValueError("Invalid resume source anchor")
            name, quote = anchor["file"], anchor["quote"]
            if (name not in texts or not isinstance(quote, str) or len(quote) < 8
                    or quote not in texts[name] or texts[name].count(quote) != 1):
                raise ValueError("Resume source anchor is missing, modified or ambiguous")
            line = texts[name][:texts[name].index(quote)].count("\n") + 1
            anchors.append(SourceAnchor(f"{source_reference_prefix}/{name}:{line}", quote, fingerprints[name]))
        if not any(anchor.quote == claim["text"] for anchor in anchors):
            raise ValueError("Canonical claim text must equal an exact reviewed source anchor")
        claims.append(ResumeClaim(claim["id"], claim["text"], claim["status"], tuple(anchors),
                                  strings(claim["limitations"]), tuple(sorted(qualifiers.items()))))
    if len({claim.text for claim in claims}) != len(claims):
        raise ValueError("Canonical claim texts must be unique")
    rules, rule_ids, before_texts = [], set(), set()
    for rule in mapping["rules"]:
        if (not isinstance(rule, dict) or set(rule) != {"id", "before", "claim_id"}
                or not isinstance(rule.get("id"), str) or not re.fullmatch(r"[a-z][a-z0-9_]*", rule["id"])
                or not isinstance(rule["claim_id"], str)
                or rule["id"] in rule_ids or rule["claim_id"] not in identifiers
                or not isinstance(rule["before"], str)):
            raise ValueError("Invalid exact-text proposal rule")
        if rule["before"] and rule["before"] in before_texts:
            raise ValueError("Conflicting exact before text")
        rule_ids.add(rule["id"])
        before_texts.add(rule["before"])
        rules.append(ProposalRule(rule["id"], rule["before"], rule["claim_id"]))
    limitation_labels = tuple(f"Candidate limitation: {value}" for value in candidate.limitations)
    limitation_labels += tuple("Candidate limitation anchor: " + reference
                              for references in candidate.limitation_references.values() for reference in references)
    return ResumeEvidence(tuple(sorted(claims, key=lambda claim: claim.claim_id)),
        tuple(sorted(rules, key=lambda rule: rule.rule_id)), candidate.mapping_fingerprint,
        tuple(sorted((*candidate.fingerprints.items(), *fingerprints.items()))), _hash(raw),
        (*strings(mapping["limitations"]), *limitation_labels))


def review_resume(document: ResumeDocument, evidence: ResumeEvidence) -> ResumeProposal:
    """Pure review of explicit snapshots. Every change remains a human proposal."""
    if not isinstance(document, ResumeDocument) or not isinstance(evidence, ResumeEvidence):
        raise ValueError("Explicit ResumeDocument and reviewed ResumeEvidence are required")
    if (not re.fullmatch(r"[a-f0-9]{64}", document.source_sha256)
            or not re.fullmatch(r"[a-f0-9]{64}", evidence.candidate_fingerprint)
            or not re.fullmatch(r"[a-f0-9]{64}", evidence.mapping_sha256)):
        raise ValueError("Explicit source/evidence fingerprints are required")
    _label(document.source_label)
    for claim in evidence.claims:
        if (claim.status not in STATUSES or not claim.anchors
                or not any(anchor.quote == claim.text for anchor in claim.anchors)):
            raise ValueError("Positive and pending claims need reviewed verbatim anchors")
    if (len({claim.claim_id for claim in evidence.claims}) != len(evidence.claims)
            or len({block.block_id for block in document.blocks}) != len(document.blocks)):
        raise ValueError("Claim and document block identities must be unique")
    evidence_fingerprint = _fingerprint(asdict(evidence))
    claims = {claim.claim_id: claim for claim in evidence.claims}
    canonical = {claim.text: claim for claim in evidence.claims}
    rules = {rule.before: rule for rule in evidence.rules if rule.before}
    changes, assessments = [], []
    limitations = (*document.limitations, *evidence.limitations,
                    "Read-only proposals for one general resume; no approval, writing or job-specific variants.",
                    "Exact mapped content only; unmatched text is UNKNOWN, not a confirmed false claim.",
                    "Source anchors verify provenance, not independent truth; all supplied claims require human review.")

    def change(rule, block, action):
        claim = claims[rule.claim_id]
        uncertainty = ("Human review is required; the source resume is unchanged.",)
        if claim.status != "CONFIRMED":
            uncertainty += (f"Claim remains {claim.status}; this proposal does not promote it to a verified fact.",)
        identity = _fingerprint({"engine": ENGINE_VERSION, "rule": rule.rule_id, "claim": claim.claim_id,
                                 "block": block.block_id, "before": block.text, "after": claim.text})
        return ProposedChange("change-" + identity, action, block.block_id, block.reference,
            rule.rule_id, claim.claim_id, block.text, claim.text,
            "UNKNOWN" if action == "ADD" else "UNSUPPORTED", claim.status, claim.anchors,
            claim.qualifiers, (*claim.limitations, *evidence.limitations), uncertainty)

    if document.supported:
        for block in document.blocks:
            claim = canonical.get(block.text)
            rule = rules.get(block.text)
            if claim:
                assessments.append(ContentAssessment(block.block_id, block.text, claim.status, claim.claim_id,
                                                       claim.anchors, claim.limitations))
            elif rule:
                claim = claims[rule.claim_id]
                assessments.append(ContentAssessment(block.block_id, block.text, "UNSUPPORTED", claim.claim_id,
                    claim.anchors, ("Exact statement is not supported by this reviewed canonical claim; inspect proposed wording.",)))
                changes.append(change(rule, block, "REPLACE"))
            elif block.text:
                assessments.append(ContentAssessment(block.block_id, block.text, "UNKNOWN", None, (),
                    ("No reviewed exact-text claim/rule covers this block; no rewrite invented.",)))
        existing = {block.text for block in document.blocks}
        proposed = {item.after for item in changes}
        for rule in evidence.rules:
            if not rule.before and claims[rule.claim_id].text not in existing | proposed:
                block = ResumeBlock("append", "", f"{document.source_label}:append")
                changes.append(change(rule, block, "ADD"))
                proposed.add(claims[rule.claim_id].text)
    payload = {"engine": ENGINE_VERSION, "resume": asdict(document), "evidence": evidence_fingerprint,
               "changes": [asdict(item) for item in changes], "assessments": [asdict(item) for item in assessments],
               "limitations": limitations}
    return ResumeProposal(ENGINE_VERSION, document.source_sha256, evidence_fingerprint, _fingerprint(payload),
                          document.supported, tuple(changes), tuple(assessments), tuple(limitations))


def render_proposal(proposal: ResumeProposal) -> str:
    """Return private review text only; callers choose whether/where to save it."""
    lines = ["General resume evidence review — proposed changes only",
             f"Proposal fingerprint: {proposal.proposal_fingerprint}",
             f"Supported document: {proposal.supported_document}; proposed changes: {len(proposal.changes)}"]
    for item in proposal.changes:
        lines.extend(("", f"{item.change_id} | {item.action} | {item.resume_reference}",
            f"Evidence status: {item.evidence_status}; prior text: {item.before_status}",
            "Before (exact): " + json.dumps(item.before, ensure_ascii=False),
            "After (exact): " + json.dumps(item.after, ensure_ascii=False),
            "Sources: " + "; ".join(anchor.reference for anchor in item.anchors),
            "Qualifiers: " + "; ".join(f"{key}={value}" for key, value in item.qualifiers),
            "Limitations/uncertainties: " + "; ".join((*item.limitations, *item.uncertainties))))
    lines.extend(("", "Unmapped/unsupported content assessments:"))
    for assessment in proposal.assessments:
        if assessment.evidence_status in {"UNKNOWN", "UNSUPPORTED"}:
            lines.append(f"{assessment.block_id}: {assessment.evidence_status} — " + "; ".join(assessment.uncertainties))
    lines.extend(("", "Review limitations:", *proposal.limitations))
    return "\n".join(lines) + "\n"
