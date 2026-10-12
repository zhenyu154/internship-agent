"""Small offline synthetic CLI; no discovery, submission or resume Apply.

Independently authored public handlers; original personalized CLI is excluded.
"""

import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import sys

from . import demo

PUBLIC_ROOT = demo.PUBLIC_ROOT
from .demo_services import (
    DATABASE_LABEL, MANIFEST_LABEL, FIXTURE_LABELS, DOCX_LIMIT,
    DemoInputError, DemoServices, bounded_bytes, reject_links,
)

DemoCLIError = DemoInputError


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "Invalid command or arguments. Use --help for the offline demo commands.\n")


def _parser():
    parser = _Parser(prog="internship-agent", description=demo.NOTICE + " Read-only offline demo.",
                     epilog="Create/recover only with scripts/create_demo.py. Resume Apply is unavailable.",
                     allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)
    for name, help in (
        ("demo-status", "Validate the explicitly selected demo and show its summary."),
        ("demo-jobs", "List only validated synthetic job records."),
        ("demo-applications", "List synthetic preparation records; no notes/receipts."),
        ("demo-rank", "Show unchanged heuristic scores, evidence and separate eligibility."),
    ):
        command = commands.add_parser(name, help=help, description=help, allow_abbrev=False)
        command.add_argument("--database", required=True, metavar="DEMO_PATH",
            help=f"Explicit selection of {DATABASE_LABEL}; other paths are refused.")
        if name == "demo-rank":
            command.add_argument("--job", metavar="DEMO_ID", help="Explain one fictional posting, e.g. demo-002.")
    commands.add_parser("demo-resume-review", help="Display exact synthetic proposals; no approval/Apply.",
                       description=DOCX_LIMIT, allow_abbrev=False)
    return parser


def _reject_links(path):
    return reject_links(path)


def _public_file(label):
    return DemoServices(PUBLIC_ROOT).public_file(label)


def _bounded_bytes(path):
    return bounded_bytes(path)


def _fixtures():
    return DemoServices(PUBLIC_ROOT).validate_fixtures()


def _database_path(value):
    return DemoServices(PUBLIC_ROOT).database_path(value)


@contextmanager
def _database(value):
    from .database import JobDatabase
    path = _database_path(value)
    _fixtures()
    with JobDatabase(path, read_only=True) as database:
        validation = demo.validate_completed_demo(database)
        yield database, validation


def _quoted(value):
    return json.dumps(value, ensure_ascii=False)


def _status(database, validation):
    return (f"Selected database: {DATABASE_LABEL}\n"
            f"Demo run: {validation['run_status']}\n"
            f"Synthetic jobs: {validation['jobs']}; preparation records: {validation['applications']}\n"
            f"SQLite integrity: {validation['integrity_check']}; foreign-key violations: "
            f"{validation['foreign_key_violations']}; schema version: {validation['schema_version']}\n"
            f"Fixture fingerprint: {validation['fixture_fingerprint']}\n")


def _jobs(database):
    rows = database.list_jobs()
    lines = [f"Synthetic jobs: {len(rows)}"]
    for record in rows:
        job = record.job
        metadata = database.get_job_metadata(record.id)
        lines.append(f"{job.source_job_id} | {_quoted(job.title)} | {_quoted(job.company)} | "
                     f"{_quoted(job.location)} | relevance: {metadata.relevance_category} | {job.url}")
    return "\n".join(lines) + "\n"


def _applications(database):
    rows = database.list_applications()
    lines = [f"Synthetic preparation records: {len(rows)}", "Notes and receipts are omitted."]
    for application in rows:
        job = database.get_job(application.job_id).job
        lines.append(f"{job.source_job_id} | {_quoted(job.title)} | {application.status}")
    return "\n".join(lines) + "\n"


def _ranking(database, selected):
    records = database.list_jobs()
    by_id = {record.id: record for record in records}
    if selected is not None and selected not in {record.job.source_job_id for record in records}:
        raise DemoCLIError("Requested fictional job was not found; use demo-jobs to inspect IDs.")
    results = DemoServices(PUBLIC_ROOT).ranked_jobs(database)
    lines = ["Heuristic job match scores; not admission probabilities.",
             "Weights: role 30; technical skills 30; project relevance 25; location 15.",
             "UNKNOWN requires review and is not automatic ineligibility."]
    labels = {"role_alignment": "Role alignment", "technical_skills_match": "Technical skills",
              "research_project_relevance": "Project relevance", "location_preference": "Location preference"}
    for result in results:
        job = by_id[result.job_id].job
        if selected is not None and job.source_job_id != selected:
            continue
        lines.extend(("", f"{job.source_job_id} | {_quoted(job.title)} | score: {result.technical_match_score:.2f}/100",
            f"Eligibility: {result.eligibility.status} | relevance: {result.relevance_category} | "
            f"application: {result.application_status}"))
        for component in result.components:
            lines.append(f"{labels[component.name]}: {component.points:.2f}/{component.weight} — {component.calculation}")
            if component.project_id:
                lines.append(f"Project evidence: {component.project_id}")
            lines.append("Sources: " + "; ".join(f"{ref.reference} [{ref.state}]" for ref in component.evidence))
        for match in result.skill_matches:
            lines.append(f"{match.importance} skill group: {' or '.join(match.alternatives)}; "
                         f"supported: {', '.join(match.matched) or 'UNKNOWN / no supported match'}")
        lines.extend("Eligibility review: " + check for check in result.eligibility.checks)
        lines.extend("Eligibility source: " + ref.reference + f" [{ref.state}]" for ref in result.eligibility.evidence)
        lines.extend("Limitation: " + warning for warning in result.warnings)
        lines.extend("Limitation source: " + ref.reference for ref in result.limitation_evidence)
        lines.extend((f"Candidate fingerprint: {result.candidate_fingerprint}",
                      f"Configuration fingerprint: {result.configuration_fingerprint}",
                      f"Job fingerprint: {result.job_fingerprint}"))
    return "\n".join(lines) + "\n"


def _resume():
    from .resume_review import render_proposal
    _fixtures()
    document, proposal = DemoServices(PUBLIC_ROOT).resume_review()
    return render_proposal(proposal) + "\n" + DOCX_LIMIT + "\nResume Apply is unavailable.\n"


def main(argv=None) -> int:
    parser = _parser()
    try:
        arguments = parser.parse_args(argv)
    except SystemExit as result:
        return result.code
    try:
        if arguments.command == "demo-resume-review":
            output = _resume()
        else:
            with _database(arguments.database) as (database, validation):
                if arguments.command == "demo-status": output = _status(database, validation)
                elif arguments.command == "demo-jobs": output = _jobs(database)
                elif arguments.command == "demo-applications": output = _applications(database)
                else: output = _ranking(database, arguments.job)
        print(demo.NOTICE)
        print(output, end="")
        return 0
    except DemoCLIError as error:
        print(str(error), file=sys.stderr)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, sqlite3.Error):
        # Fixed diagnostics prevent arbitrary corrupt record/exception text from
        # leaking private inputs, paths, notes or credentials to the terminal.
        print("Demo input is corrupt or incompatible. Review docs/CLI_GUIDE.md; no changes were made.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
