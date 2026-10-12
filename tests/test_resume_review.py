"""Synthetic offline general-resume review; no private documents or edits."""

from contextlib import contextmanager
from dataclasses import asdict, replace
import hashlib
from io import BytesIO
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

from internship_agent import demo
from internship_agent.candidate_evidence import SOURCE_FILES
from internship_agent.resume_review import (
    MAX_BYTES, ContentAssessment, ResumeEvidence, extract_resume, load_resume,
    load_resume_evidence, render_proposal, review_resume,
)

ROOT = demo.PUBLIC_ROOT
BASE = ROOT / "demo" / "fixtures" / "resume_review"
CANDIDATE = demo.FIXTURE_DIRECTORY / "evidence"
RESUME = BASE / "general_resume.txt"
XML_FIXTURE = ROOT / "tests" / "fixtures" / "resume_paragraphs.xml"
TYPES = b'''<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'''
RELS = b'''<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'''


def package(xml, extra=None, relationships=RELS, types=TYPES):
    """In-memory authored OOXML fixture only; no output-document generation API."""
    stream = BytesIO()
    with ZipFile(stream, "w", compression=ZIP_DEFLATED) as archive:
        for name, value in {"[Content_Types].xml": types, "_rels/.rels": relationships,
                            "word/document.xml": xml, **(extra or {})}.items():
            archive.writestr(name, value)
    return stream.getvalue()


class ResumeReviewTests(unittest.TestCase):
    def setUp(self):
        self.evidence = self.load_evidence()
        self.document = load_resume(RESUME, source_label="demo/fixtures/resume_review/general_resume.txt")
        self.proposal = review_resume(self.document, self.evidence)

    def load_evidence(self, candidate=CANDIDATE, base=BASE):
        return load_resume_evidence(candidate_directory=candidate, claims_path=base / "claims.json",
            sources={"observations.md": base / "observations.md"},
            candidate_reference_prefix="demo/fixtures/evidence",
            source_reference_prefix="demo/fixtures/resume_review")

    @contextmanager
    def copied_bundle(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            candidate, base = root / "candidate_evidence", root / "review"
            shutil.copytree(CANDIDATE, candidate)
            shutil.copytree(BASE, base)
            yield candidate, base

    def changed_claim(self, identifier):
        return next(change for change in self.proposal.changes if change.claim_id == identifier)

    def alter_mapping(self, path, change):
        raw = json.loads(path.read_text(encoding="utf-8"))
        change(raw)
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    def test_utf8_txt_preserves_exact_whitespace_unicode_and_offsets(self):
        text = "  Synthetic — exact\ttext  \r\nSecond line\n\nLast line"
        document = extract_resume(text.encode(), format="txt", source_label="synthetic/resume.txt")
        self.assertEqual([block.text for block in document.blocks],
                         ["  Synthetic — exact\ttext  ", "Second line", "", "Last line"])
        self.assertEqual([text[block.start:block.end] for block in document.blocks],
                         [block.text for block in document.blocks])
        self.assertEqual(document.source_sha256, hashlib.sha256(text.encode()).hexdigest())

    def test_resume_before_texts_are_exact_source_blocks(self):
        existing = {block.block_id: block.text for block in self.document.blocks}
        for change in self.proposal.changes:
            if change.action == "REPLACE":
                self.assertEqual(change.before, existing[change.block_id])
            else:
                self.assertEqual(change.before, "")

    def test_supported_resume_content_is_identified_with_sources(self):
        education = next(item for item in self.proposal.assessments if item.claim_id == "education")
        self.assertIsInstance(education, ContentAssessment)
        self.assertEqual(education.evidence_status, "CONFIRMED")
        self.assertTrue(education.anchors)
        self.assertFalse(any(change.claim_id == "education" for change in self.proposal.changes))

    def test_each_after_text_is_verbatim_anchored_and_source_lines_resolve(self):
        for change in self.proposal.changes:
            self.assertIn(change.after, {anchor.quote for anchor in change.anchors})
            for anchor in change.anchors:
                file, number = anchor.reference.rsplit(":", 1)
                path = ROOT / file
                text = path.read_text(encoding="utf-8")
                self.assertIn(anchor.quote, text)
                self.assertEqual(text[:text.index(anchor.quote)].count("\n") + 1, int(number))
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), anchor.source_sha256)

    def test_stable_ids_and_fingerprints_on_identical_reviews(self):
        again = review_resume(self.document, self.evidence)
        self.assertEqual(self.proposal, again)
        self.assertEqual(len(self.proposal.proposal_fingerprint), 64)
        self.assertEqual(len({change.change_id for change in self.proposal.changes}), len(self.proposal.changes))

    def test_copying_explicit_inputs_does_not_put_absolute_paths_into_proposals(self):
        with self.copied_bundle() as (candidate, base):
            evidence = self.load_evidence(candidate, base)
            document = load_resume(base / "general_resume.txt", source_label=self.document.source_label)
            proposal = review_resume(document, evidence)
        self.assertEqual(proposal, self.proposal)
        self.assertNotIn(str(BASE), render_proposal(proposal))

    def test_resume_changes_change_the_proposal_fingerprint(self):
        raw = RESUME.read_bytes() + b"\nSynthetic extra unmapped line.\n"
        changed = review_resume(extract_resume(raw, format="txt", source_label=self.document.source_label), self.evidence)
        self.assertNotEqual(changed.proposal_fingerprint, self.proposal.proposal_fingerprint)

    def test_evidence_status_changes_change_fingerprint_without_promoting_claim(self):
        claims = tuple(replace(claim, status="INFERRED") if claim.claim_id == "skills" else claim
                       for claim in self.evidence.claims)
        changed = review_resume(self.document, replace(self.evidence, claims=claims))
        self.assertNotEqual(changed.proposal_fingerprint, self.proposal.proposal_fingerprint)
        skill = next(change for change in changed.changes if change.claim_id == "skills")
        self.assertEqual(skill.evidence_status, "INFERRED")
        self.assertTrue(any("not promote" in item for item in skill.uncertainties))

    def test_unrelated_resume_changes_do_not_rename_existing_changes(self):
        raw = RESUME.read_bytes().replace(b"Professional experience: unknown synthetic entry requiring review.",
                                         b"Professional experience: another unmapped synthetic entry.")
        document = extract_resume(raw, format="txt", source_label=self.document.source_label)
        changed = review_resume(document, self.evidence)
        self.assertEqual([item.change_id for item in changed.changes],
                         [item.change_id for item in self.proposal.changes])

    def test_pending_publication_stays_pending_and_no_acceptance_is_invented(self):
        change = self.changed_claim("publication_pending")
        self.assertEqual(change.evidence_status, "PENDING")
        self.assertEqual(change.before_status, "UNSUPPORTED")
        self.assertEqual(change.after, "Publication status: pending; no acceptance evidence exists.")
        self.assertEqual(dict(change.qualifiers)["publication"], "pending")
        self.assertTrue(change.limitations and change.uncertainties)

    def test_unmapped_professional_experience_remains_unknown_with_no_invented_replacement(self):
        assessment = next(item for item in self.proposal.assessments if item.before.startswith("Professional experience:"))
        self.assertEqual(assessment.evidence_status, "UNKNOWN")
        self.assertIsNone(assessment.claim_id)
        self.assertFalse(any(change.before.startswith("Professional experience:") for change in self.proposal.changes))

    def test_no_degree_dates_or_metrics_are_invented(self):
        source_text = (BASE / "observations.md").read_text(encoding="utf-8")
        self.assertTrue(all(change.after in source_text for change in self.proposal.changes))
        self.assertFalse(any(change.claim_id == "education" for change in self.proposal.changes))
        self.assertFalse(any("80%" in change.after for change in self.proposal.changes))

    def test_simulation_qualification_is_preserved(self):
        change = self.changed_claim("grid_simulation")
        self.assertIn("toy simulation; no physical robot deployment", change.after)
        self.assertEqual(dict(change.qualifiers)["deployment"], "simulation")
        self.assertTrue(any("Simulation" in item for item in change.limitations))

    def test_seen_measurement_does_not_become_held_out_or_inferred_readiness(self):
        change = self.changed_claim("toy_seen_measurement")
        self.assertIn("8 of 10 correct labels on seen synthetic examples", change.after)
        self.assertIn("no held-out measurement or production readiness", change.after)
        self.assertEqual(dict(change.qualifiers)["evaluation"], "seen")
        self.assertEqual(dict(change.qualifiers)["result"], "measured")

    def test_validation_split_is_not_promoted_to_real_world_performance(self):
        change = self.changed_claim("classifier_validation")
        self.assertIn("separate synthetic validation split", change.after)
        self.assertIn("real-world generalization is unestablished", change.after)
        self.assertEqual(dict(change.qualifiers)["result"], "unknown")

    def test_modified_candidate_source_evidence_fails_closed(self):
        with self.copied_bundle() as (candidate, base):
            path = candidate / "profile.md"
            path.write_text(path.read_text(encoding="utf-8") + "\nChanged synthetic degree.\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "sources changed"):
                self.load_evidence(candidate, base)

    def test_missing_candidate_source_evidence_fails_closed(self):
        with self.copied_bundle() as (candidate, base):
            (candidate / "verification_report.md").unlink()
            with self.assertRaises(FileNotFoundError):
                self.load_evidence(candidate, base)

    def test_modified_candidate_mapping_requires_resume_ledger_review(self):
        with self.copied_bundle() as (candidate, base):
            path = candidate / "ranking_features.json"
            path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Candidate evidence changed"):
                self.load_evidence(candidate, base)

    def test_modified_supplemental_evidence_requires_review(self):
        with self.copied_bundle() as (candidate, base):
            path = base / "observations.md"
            path.write_text(path.read_text(encoding="utf-8") + "\nChanged synthetic observation.\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "sources changed"):
                self.load_evidence(candidate, base)

    def test_missing_supplemental_source_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "sources changed or are missing"):
            load_resume_evidence(candidate_directory=CANDIDATE, claims_path=BASE / "claims.json", sources={},
                candidate_reference_prefix="demo/fixtures/evidence", source_reference_prefix="demo/fixtures/resume_review")

    def test_missing_or_modified_anchor_fails_closed(self):
        with self.copied_bundle() as (candidate, base):
            path = base / "claims.json"
            self.alter_mapping(path, lambda raw: raw["claims"][0]["evidence"][0].update(quote="Invented unanchored acceptance."))
            with self.assertRaisesRegex(ValueError, "anchor is missing"):
                self.load_evidence(candidate, base)

    def test_new_canonical_wording_cannot_bypass_exact_source_anchor(self):
        with self.copied_bundle() as (candidate, base):
            path = base / "claims.json"
            self.alter_mapping(path, lambda raw: raw["claims"][0].update(text="Fictional PhD awarded in an invented year."))
            with self.assertRaisesRegex(ValueError, "equal an exact"):
                self.load_evidence(candidate, base)

    def test_physical_qualifier_cannot_override_simulation_only_sources(self):
        with self.copied_bundle() as (candidate, base):
            path = base / "claims.json"
            self.alter_mapping(path, lambda raw: raw["claims"][1]["qualifiers"].update(deployment="physical"))
            with self.assertRaisesRegex(ValueError, "simulation-only"):
                self.load_evidence(candidate, base)

    def test_unexpected_contract_fields_are_rejected(self):
        with self.copied_bundle() as (candidate, base):
            path = base / "claims.json"
            self.alter_mapping(path, lambda raw: raw.update(auto_approve=True))
            with self.assertRaisesRegex(ValueError, "contract"):
                self.load_evidence(candidate, base)

    def test_unreviewed_status_is_rejected(self):
        with self.copied_bundle() as (candidate, base):
            path = base / "claims.json"
            self.alter_mapping(path, lambda raw: raw["claims"][0].update(status="APPROVED"))
            with self.assertRaisesRegex(ValueError, "evidence status"):
                self.load_evidence(candidate, base)

    def test_conflicting_before_rules_are_rejected(self):
        with self.copied_bundle() as (candidate, base):
            path = base / "claims.json"
            def conflict(raw):
                raw["rules"].append({**raw["rules"][0], "id": "conflicting_rule"})
            self.alter_mapping(path, conflict)
            with self.assertRaisesRegex(ValueError, "Conflicting exact before"):
                self.load_evidence(candidate, base)

    def test_already_supported_content_does_not_get_reproposed(self):
        raw = RESUME.read_text(encoding="utf-8")
        for change in self.proposal.changes:
            if change.action == "REPLACE": raw = raw.replace(change.before, change.after)
            else: raw += change.after + "\n"
        document = extract_resume(raw.encode(), format="txt", source_label=self.document.source_label)
        again = review_resume(document, self.evidence)
        self.assertEqual(again.changes, ())
        self.assertTrue(any(item.evidence_status == "PENDING" for item in again.assessments))

    def test_duplicate_exact_text_gets_distinct_location_ids(self):
        before = self.changed_claim("grid_simulation").before
        raw = (before + "\n" + before + "\n").encode()
        proposal = review_resume(extract_resume(raw, format="txt", source_label="synthetic/repeated.txt"), self.evidence)
        replacements = [change for change in proposal.changes if change.action == "REPLACE"]
        self.assertEqual(len(replacements), 2)
        self.assertNotEqual(replacements[0].change_id, replacements[1].change_id)

    def test_exact_matching_does_not_silently_normalize_resume_content(self):
        raw = RESUME.read_bytes().replace(b"Demo Grid Navigation deployed", b" Demo Grid Navigation deployed")
        proposal = review_resume(extract_resume(raw, format="txt", source_label=self.document.source_label), self.evidence)
        self.assertFalse(any(change.claim_id == "grid_simulation" for change in proposal.changes))
        self.assertTrue(any(item.before.startswith(" Demo Grid") and item.evidence_status == "UNKNOWN"
                            for item in proposal.assessments))

    def test_pure_review_has_no_file_network_database_or_application_access(self):
        with (patch("builtins.open", side_effect=AssertionError("File access")),
              patch.object(Path, "open", side_effect=AssertionError("Path access")),
              patch("sqlite3.connect", side_effect=AssertionError("Database access")),
              patch("socket.create_connection", side_effect=AssertionError("Network access")),
              patch("socket.getaddrinfo", side_effect=AssertionError("DNS access")),
              patch("urllib.request.urlopen", side_effect=AssertionError("HTTP access"))):
            self.assertEqual(review_resume(self.document, self.evidence), self.proposal)
            self.assertIn("Before (exact)", render_proposal(self.proposal))

    def test_loading_and_reviewing_leave_all_source_bytes_unchanged(self):
        paths = [RESUME, BASE / "claims.json", BASE / "observations.md",
                 *(CANDIDATE / name for name in (*SOURCE_FILES, "ranking_features.json"))]
        before = {path: path.read_bytes() for path in paths}
        self.load_evidence()
        load_resume(RESUME, source_label=self.document.source_label)
        review_resume(self.document, self.evidence)
        render_proposal(self.proposal)
        self.assertEqual(before, {path: path.read_bytes() for path in paths})

    def test_explicit_loading_reads_only_named_synthetic_inputs(self):
        allowed = {RESUME, BASE / "claims.json", BASE / "observations.md",
                   *(CANDIDATE / name for name in (*SOURCE_FILES, "ranking_features.json"))}
        original = Path.open
        observed = set()
        def guarded(path, mode="r", *args, **kwargs):
            self.assertIn(path, allowed)
            self.assertNotIn(mode, {"w", "wb", "a", "ab", "r+", "rb+"})
            observed.add(path)
            return original(path, mode, *args, **kwargs)
        with patch.object(Path, "open", guarded):
            self.load_evidence()
            load_resume(RESUME, source_label=self.document.source_label)
        self.assertEqual(observed, allowed)

    def test_inputs_are_required_no_default_document_search(self):
        with self.assertRaises(TypeError): load_resume()
        with self.assertRaises(TypeError): load_resume_evidence()
        with self.assertRaises(ValueError): review_resume(None, self.evidence)

    def test_unsafe_source_labels_are_refused_before_io(self):
        with patch.object(Path, "open", side_effect=AssertionError("Unexpected input read")):
            for label in ("../private", "/absolute", "folder\\file", "folder/../file"):
                with self.subTest(label=label), self.assertRaises(ValueError):
                    load_resume("unread.txt", source_label=label)

    def test_redirected_explicit_inputs_are_refused(self):
        for method in ("is_symlink", "is_junction"):
            with patch.object(Path, method, return_value=True), self.assertRaisesRegex(ValueError, "symlinks"):
                load_resume(RESUME, source_label=self.document.source_label)

    def test_human_readable_output_contains_exact_changes_statuses_and_sources(self):
        text = render_proposal(self.proposal)
        for change in self.proposal.changes:
            self.assertIn(change.change_id, text)
            self.assertIn(json.dumps(change.before, ensure_ascii=False), text)
            self.assertIn(json.dumps(change.after, ensure_ascii=False), text)
            self.assertIn(change.evidence_status, text)
            self.assertIn(change.anchors[0].reference, text)
        self.assertIn(self.proposal.proposal_fingerprint, text)
        self.assertNotIn("approved", text.lower())

    def test_experimental_ledger_is_explicitly_synthetic_without_contacts(self):
        for path in BASE.iterdir():
            text = path.read_text(encoding="utf-8")
            self.assertIn(demo.NOTICE, text)
            self.assertNotIn("@", text)
            self.assertNotIn("C:\\Users\\", text)

    def test_supported_docx_extracts_exact_run_text_tabs_and_breaks(self):
        document = extract_resume(package(XML_FIXTURE.read_bytes()), format="docx", source_label="synthetic/resume.docx")
        self.assertTrue(document.supported)
        self.assertEqual([block.text for block in document.blocks],
                         [demo.NOTICE, "  Exact synthetic\ttext\nwith trailing spaces  "])
        self.assertEqual(document.blocks[1].reference, "synthetic/resume.docx:paragraph:2")
        self.assertTrue(any("layout" in limitation for limitation in document.limitations))

    def test_docx_review_keeps_exact_paragraph_target(self):
        before = self.changed_claim("grid_simulation").before
        xml = XML_FIXTURE.read_text(encoding="utf-8").replace("  Exact ", before).replace("synthetic", "").replace(
            "<w:tab/><w:t>text</w:t><w:br/><w:t xml:space=\"preserve\">with trailing spaces  </w:t>", "")
        document = extract_resume(package(xml.encode()), format="docx", source_label="synthetic/review.docx")
        proposal = review_resume(document, self.evidence)
        self.assertTrue(document.supported)
        replacement = next(change for change in proposal.changes if change.claim_id == "grid_simulation")
        self.assertEqual(replacement.before, before)
        self.assertEqual(replacement.block_id, "paragraph-2")

    def test_unsupported_docx_structures_never_return_partial_text_or_changes(self):
        original = XML_FIXTURE.read_text(encoding="utf-8")
        nodes = [
            '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Synthetic table</w:t></w:r></w:p></w:tc></w:tr></w:tbl>',
            '<w:p><w:hyperlink><w:r><w:t>Synthetic link</w:t></w:r></w:hyperlink></w:p>',
            '<w:p><w:ins><w:r><w:t>Synthetic revision</w:t></w:r></w:ins></w:p>',
            '<w:p><w:r><w:rPr><w:vanish/></w:rPr><w:t>Synthetic hidden text</w:t></w:r></w:p>',
            '<w:p><w:r><w:drawing/></w:r></w:p>',
            '<w:sdt><w:sdtContent><w:p/></w:sdtContent></w:sdt>',
            '<w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r></w:p>',
            '<w:p><w:pPr><w:pStyle w:val="HiddenStyle"/></w:pPr><w:r><w:t>Synthetic inherited style</w:t></w:r></w:p>',
            '<w:p><w:pPr><w:numPr/></w:pPr></w:p>',
            '<w:p><w:r><w:br w:type="page"/></w:r></w:p>',
        ]
        for node in nodes:
            with self.subTest(node=node):
                xml = original.replace("<w:sectPr>", node + "<w:sectPr>")
                document = extract_resume(package(xml.encode()), format="docx", source_label="synthetic/unsupported.docx")
                self.assertFalse(document.supported)
                self.assertEqual(document.blocks, ())
                self.assertEqual(review_resume(document, self.evidence).changes, ())

    def test_docx_other_stories_embeds_and_metadata_are_reported_as_unsupported(self):
        for part in ("word/header1.xml", "word/footer1.xml", "word/comments.xml", "word/footnotes.xml",
                     "word/styles.xml", "word/embeddings/object.bin", "docProps/core.xml"):
            with self.subTest(part=part):
                document = extract_resume(package(XML_FIXTURE.read_bytes(), {part: b"Synthetic unsupported fixture"}),
                                          format="docx", source_label="synthetic/other-stories.docx")
                self.assertFalse(document.supported)
                self.assertEqual(document.blocks, ())

    def test_external_docx_relationships_are_never_followed(self):
        relationships = RELS.replace(b'Target="word/document.xml"', b'Target="https://example.test/private" TargetMode="External"')
        with patch("urllib.request.urlopen", side_effect=AssertionError("External request")):
            document = extract_resume(package(XML_FIXTURE.read_bytes(), relationships=relationships),
                                      format="docx", source_label="synthetic/external.docx")
        self.assertFalse(document.supported)
        self.assertEqual(document.blocks, ())

    def test_docx_dtd_and_entities_are_rejected(self):
        xml = XML_FIXTURE.read_bytes().replace(b'?>', b'?><!DOCTYPE document [<!ENTITY secret "Synthetic entity">]>', 1)
        document = extract_resume(package(xml), format="docx", source_label="synthetic/entity.docx")
        self.assertFalse(document.supported)

    def test_malformed_document_or_wrong_formats_are_not_guessed(self):
        for raw, format in ((b"not a zip", "docx"), (b"Synthetic PDF", "pdf"), (b"\xff\xfe", "txt"),
                            (b"\x00Synthetic", "txt"), (b"\xef\xbb\xbfSynthetic", "txt")):
            with self.subTest(format=format, raw=raw):
                document = extract_resume(raw, format=format, source_label="synthetic/unknown.txt")
                self.assertFalse(document.supported)
                self.assertEqual(review_resume(document, self.evidence).changes, ())

    def test_bounded_input_sizes_prevent_unbounded_extraction(self):
        with self.assertRaisesRegex(ValueError, "bounded bytes"):
            extract_resume(b"x" * (MAX_BYTES + 1), format="txt", source_label="synthetic/oversized.txt")
        compressed = package(XML_FIXTURE.read_bytes(), {"word/oversized.xml": b"x" * (MAX_BYTES + 1)})
        document = extract_resume(compressed, format="docx", source_label="synthetic/oversized.docx")
        self.assertFalse(document.supported)

    def test_fabricated_unanchored_evidence_snapshots_are_rejected(self):
        claims = (replace(self.evidence.claims[0], anchors=()),)
        with self.assertRaisesRegex(ValueError, "verbatim anchors"):
            review_resume(self.document, replace(self.evidence, claims=claims))

    def test_proposals_contain_no_approval_or_apply_state(self):
        serialized = asdict(self.proposal)
        self.assertNotIn("approved", serialized)
        self.assertNotIn("apply", serialized)
        self.assertNotIn("submitted", serialized)
        self.assertNotIn("job_id", json.dumps(serialized))


if __name__ == "__main__":
    unittest.main()
