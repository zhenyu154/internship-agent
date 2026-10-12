"""Non-sensitive local tracker snapshots. Private application text stays in SQLite."""

from collections import Counter
from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile

from .applications import APPLICATION_STATUSES, application_opportunities
from .relevance import EXCLUDED, NEEDS_REVIEW
from .unified_report import cell


def write_application_report(database, path=None, *, preferences=None, today=None):
    now = datetime.now(timezone.utc)
    today = today or now.date()
    path = Path(path or f"reports/application_tracker_{now.strftime('%Y%m%dT%H%M%S%fZ')}.md")
    if path.resolve() == database.path.resolve() or path.suffix.casefold() != ".md":
        raise ValueError("Application report must be a Markdown file separate from SQLite")
    entries = application_opportunities(database, preferences=preferences)
    tracked = database.list_applications()
    counts = Counter(a.status for a in tracked)
    untracked = sum(e.application is None for e in entries)
    lines = ["# Application tracker", "", f"Snapshot UTC: {now.isoformat(timespec='seconds')}", "",
             f"Historical jobs: {database.count_jobs()}; explicitly tracked applications: {len(tracked)}; "
             f"untracked relevant/review opportunities: {untracked}.", "",
             "Untracked opportunities display NOT_STARTED without creating application records. "
             "Technical priority is separate from eligibility and application state. "
             "Missing source evidence remains UNKNOWN. Stored postings may be stale; no live verification was performed.", "",
             "Technical tiers reuse discovery rules: 1 = direct robot learning/manipulation/embodied AI; "
             "2 = related ML/world models/autonomy/simulation/perception; 3 = software/infrastructure; "
             "4 = hardware requiring review. These tiers do not confirm eligibility.", "",
             "## Persisted application status breakdown", "", "| Status | Records |", "|---|---:|"]
    lines += [f"| {status} | {counts[status]} |" for status in APPLICATION_STATUSES]

    def section(title, subset):
        lines.extend(["", f"## {title}", ""])
        if not subset:
            lines.append("None recorded in this snapshot.")
            return
        lines.extend(["| Job ID | Company / role | Technical tier | Application status | Source classification | Submitted date | Verified deadline | Follow-up date | Term evidence | Degree / graduation evidence | Work authorization evidence |",
                      "|---:|---|---:|---|---|---|---|---|---|---|---|"])
        for e in subset:
            a, m, j = e.application, e.metadata, e.record.job
            values = [e.record.id, f"{j.company}: {j.title}", e.priority[0], e.status, e.classification,
                      a.submitted_at if a and a.submitted_at else "UNKNOWN",
                      a.deadline if a and a.deadline_verified_at else "UNKNOWN",
                      a.follow_up_at if a and a.follow_up_at else "NOT SET",
                      m.internship_term if m else "UNKNOWN",
                      f"{m.degree_requirements} / {m.graduation_window}" if m else "UNKNOWN",
                      m.work_authorization if m else "UNKNOWN"]
            lines.append("| " + " | ".join(cell(value) for value in values) + " |")

    section("Not-started high-priority opportunities",
            [e for e in entries if e.status == "NOT_STARTED" and e.priority[0] <= 2 and e.classification != EXCLUDED])
    section("Research and preparation",
            [e for e in entries if e.status in ("RESEARCHING", "PREPARING", "READY_TO_APPLY")])
    section("Submitted applications and subsequent outcomes",
            [e for e in entries if e.application and e.application.submitted_at])
    active = [e for e in entries if e.status not in ("REJECTED", "WITHDRAWN", "CLOSED")]
    deadlines = [e for e in active if e.application and e.application.deadline_verified_at
                 and e.application.deadline >= today.isoformat()]
    section("Upcoming verified deadlines", sorted(deadlines, key=lambda e: (e.application.deadline, e.priority)))
    followups = [e for e in active if e.application and e.application.follow_up_at]
    section("Explicit follow-up actions", sorted(followups, key=lambda e: (e.application.follow_up_at, e.priority)))
    reviews = [e for e in entries if e.classification in (NEEDS_REVIEW, "UNKNOWN") or e.metadata is None
               or any(getattr(e.metadata, field) == "UNKNOWN" for field in
                      ("internship_term", "degree_requirements", "graduation_window", "work_authorization"))]
    section("Positions requiring eligibility review", reviews)
    lines += ["", "Deadline dates are entered only after an explicit user verification assertion; supporting evidence "
              "is retained privately in SQLite and can be inspected with application show. Follow-up dates "
              "are user-entered plans, with no reminders or employer contact. No deadlines or submissions are inferred.", "",
              "This shareable report omits user notes, receipt references, change reasons, deadline evidence text, "
              "and candidate contact information. Submission confirmation records the user's assertion; "
              "the software neither proves nor performs submission."]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write("\n".join(lines) + "\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return path
