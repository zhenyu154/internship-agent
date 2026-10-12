"""Public Streamlit presentation only; validated synthetic snapshots are read-only."""

import sqlite3
import streamlit as st

from internship_agent import demo
from internship_agent.dashboard_services import filter_jobs, job_rows, load_snapshot
from internship_agent.demo_services import DATABASE_LABEL, DOCX_LIMIT, DemoInputError

PAGES = ("Overview", "Demo Jobs", "Application Tracker", "General Resume")
COMPONENT_LABELS = {"role_alignment": "Role alignment", "technical_skills_match": "Technical skills",
                    "research_project_relevance": "Project relevance", "location_preference": "Location preference"}


def _advanced(validation):
    with st.expander("Advanced Details"):
        st.caption("The application reads only the configured synthetic database and reviewed fixture allowlist.")
        st.text("Configured database: " + DATABASE_LABEL)
        st.text("Schema version: " + str(validation["schema_version"]))
        st.text("Fixture fingerprint: " + str(validation["fixture_fingerprint"]))


def overview(snapshot):
    st.title("A transparent internship workflow")
    st.write("Explore job matching, preparation tracking and evidence-based resume review in one local demonstration.")
    columns = st.columns(4)
    columns[0].metric("Fictional opportunities", len(snapshot.jobs))
    columns[1].metric("Preparation records", len(snapshot.applications))
    columns[2].metric("Database integrity", str(snapshot.validation["integrity_check"]).upper())
    columns[3].metric("Proposed resume changes", len(snapshot.proposal.changes))
    st.success("Demo run completed • SQLite validated • Read-only presentation")
    left, right = st.columns([1.2, 1])
    with left, st.container(border=True):
        st.subheader("Explore the demonstration")
        st.markdown("**Demo Jobs** — compare explainable match scores and eligibility annotations.")
        st.markdown("**Application Tracker** — inspect fictional preparation history.")
        st.markdown("**General Resume** — review exact, source-anchored suggestions for one resume.")
        st.caption("Navigate using the sidebar. All examples are authored fiction; none represents an open vacancy or real applicant.")
    with right, st.container(border=True):
        st.subheader("Human decisions stay human")
        st.write("UNKNOWN means evidence needs review. A match score never confirms eligibility or predicts admission.")
        st.write("There is no application submission, resume editing, approval, automatic discovery or scheduling in this demonstration.")
    st.subheader("Implemented and planned capabilities")
    st.dataframe([
        {"Capability": "Synthetic storage and interruption-safe initialization", "Availability": "Implemented locally"},
        {"Capability": "Evidence-based ranking and separate eligibility", "Availability": "Implemented, read-only"},
        {"Capability": "Preparation records and append-only history", "Availability": "Implemented, read-only demo"},
        {"Capability": "One general resume: review and proposals", "Availability": "Implemented, review only"},
        {"Capability": "Approval-gated document output", "Availability": "Planned; Apply unavailable"},
        {"Capability": "Real applicant onboarding and broader integrations", "Availability": "Deferred; requires separate review"},
    ], hide_index=True, width="stretch")
    st.caption("Foreign-key violations: " + str(snapshot.validation["foreign_key_violations"]) + ". No live sources are contacted.")
    _advanced(snapshot.validation)


def jobs(snapshot):
    st.title("Fictional opportunities, explained")
    st.caption("Scores are technical and preference heuristics. Eligibility and preparation status remain separate.")
    rows = job_rows(snapshot)
    search = st.text_input("Search positions, companies or locations", placeholder="Try simulation, vision or Seattle", key="job_search")
    filters = st.columns([1.2, 1.2, 1])
    relevance = filters[0].multiselect("Relevance", sorted({row["Relevance"] for row in rows}), key="relevance_filter")
    eligibility = filters[1].multiselect("Eligibility", sorted({row["Eligibility"] for row in rows}), key="eligibility_filter")
    sort = filters[2].selectbox("Sort", ["Score: high to low", "Score: low to high", "Company: A to Z", "Position: A to Z"], key="job_sort")
    shown = filter_jobs(rows, search=search, relevance=relevance, eligibility=eligibility, sort=sort)
    st.caption(f"Showing {len(shown)} of {len(rows)} fictional opportunities. Select a posting below to inspect its evidence.")
    if not shown:
        st.info("No synthetic examples match these filters. Clear a filter or change the search.")
        return
    st.dataframe(shown, hide_index=True, width="stretch", height=390,
        column_order=["Position", "Company", "Job Match Score", "Eligibility", "Relevance", "Location", "Preparation", "ID"],
        column_config={"Position": st.column_config.TextColumn(width="large"),
                       "Job Match Score": st.column_config.NumberColumn(format="%.2f", help="Heuristic on a 0–100 scale; not a probability."),
                       "Eligibility": st.column_config.TextColumn(width="medium", help="UNKNOWN requires review; POLICY_EXCLUDED is a configured selection policy.")})
    selected = st.selectbox("Inspect a fictional posting", [row["ID"] for row in shown],
        format_func=lambda identifier: next(row["Position"] + " · " + row["Company"] for row in rows if row["ID"] == identifier), key="selected_job")
    record = next(record for record in snapshot.jobs if record.job.source_job_id == selected)
    result = next(result for result in snapshot.rankings if result.job_id == record.id)
    with st.container(border=True):
        st.subheader(record.job.title)
        st.write(record.job.company + " · " + record.job.location)
        if result.eligibility.status == "UNKNOWN":
            st.warning("Eligibility: UNKNOWN — human review is required. Unknown sponsorship is not automatic ineligibility.")
        else:
            st.warning("Eligibility: POLICY_EXCLUDED — a configured cohort or degree policy applies. This is separate from the match score.")
        st.caption(f"Relevance: {result.relevance_category} · Preparation: {result.application_status}")
        columns = st.columns(4)
        for column, component in zip(columns, result.components):
            column.metric(COMPONENT_LABELS[component.name], f"{component.points:.2f} / {component.weight}")
        st.write(f"**Job Match Score: {result.technical_match_score:.2f} / 100**")
        st.caption("Illustrative address only; this is not an employer application link.")
        st.code(record.job.url, language=None)
        with st.expander("Fictional job description"):
            st.text(record.job.description)
        for warning in result.warnings:
            if "Sparse" in warning: st.warning(warning)
        with st.expander("Evidence and score explanations", expanded=True):
            for component in result.components:
                st.markdown("**" + COMPONENT_LABELS[component.name] + "**")
                st.caption(component.calculation)
                if component.project_id: st.caption("Mapped project: " + component.project_id)
                st.dataframe([{"Source": reference.reference, "Evidence state": reference.state}
                              for reference in component.evidence], hide_index=True, width="stretch")
            st.dataframe([{"Importance": match.importance, "Skill alternatives": " or ".join(match.alternatives),
                           "Supported candidate evidence": ", ".join(match.matched) or "No supported match"}
                          for match in result.skill_matches], hide_index=True, width="stretch")
            st.markdown("**Eligibility review**")
            for check in result.eligibility.checks: st.write("• " + check)
            st.markdown("**Limitations and uncertainties**")
            for warning in result.warnings: st.write("• " + warning)
        with st.expander("Advanced Details"):
            st.text("Candidate fingerprint: " + result.candidate_fingerprint)
            st.text("Configuration fingerprint: " + result.configuration_fingerprint)
            st.text("Job fingerprint: " + result.job_fingerprint)
            for reference in result.limitation_evidence: st.caption(reference.reference)


def applications(snapshot):
    st.title("Preparation, with a clear history")
    st.write("Inspect the four types of preparation state through fictional examples. This page is read-only.")
    st.info("No application has been submitted. There is no submission, status-change or browser-automation control.")
    by_id = {record.id: record.job for record in snapshot.jobs}
    st.metric("Synthetic preparation records", len(snapshot.applications))
    st.dataframe([{"Position": by_id[record.job_id].title, "Company": by_id[record.job_id].company,
                   "Preparation status": record.status, "Job ID": by_id[record.job_id].source_job_id}
                  for record in snapshot.applications], hide_index=True, width="stretch")
    selected = st.selectbox("Inspect preparation history", [record.job_id for record in snapshot.applications],
                            format_func=lambda identifier: by_id[identifier].title, key="selected_application")
    application = next(record for record in snapshot.applications if record.job_id == selected)
    st.subheader(by_id[selected].title)
    st.caption("Current synthetic preparation state: " + application.status)
    st.dataframe([{"Previous state": event.previous_status or "—", "New state": event.new_status,
                   "Event": event.event.replace("_", " ").title(), "Reason": event.reason or "Initial synthetic record"}
                  for event in snapshot.history[selected]], hide_index=True, width="stretch")
    with st.expander("Synthetic preparation notes"):
        st.text(application.notes)
    with st.expander("Advanced Details"):
        st.caption("These are locally generated fixture audit timestamps, not real applicant history.")
        st.text("Created: " + application.created_at)
        for event in snapshot.history[selected]: st.text(f"{event.new_status}: {event.occurred_at}")


def resume(snapshot):
    st.title("One general resume, grounded in evidence")
    st.write("Review supported statements and exact proposed changes without creating a job-specific resume variant.")
    st.info("Resume Apply is unavailable. These are proposed changes only; the source resume stays unchanged.")
    columns = st.columns(3)
    columns[0].metric("Proposed changes", len(snapshot.proposal.changes))
    columns[1].metric("Supported statements", sum(item.evidence_status == "CONFIRMED" for item in snapshot.proposal.assessments))
    columns[2].metric("Pending claim proposals", sum(item.evidence_status == "PENDING" for item in snapshot.proposal.changes))
    with st.expander("Current synthetic general resume", expanded=True):
        st.code("\n".join(block.text for block in snapshot.resume.blocks), language=None, wrap_lines=True)
    st.subheader("Evidence review and proposed changes")
    st.caption("CONFIRMED means within the authored fictional evidence only. Unmapped statements stay UNKNOWN.")
    for index, change in enumerate(snapshot.proposal.changes, 1):
        title = f"{index}. {'Addition' if change.action == 'ADD' else 'Correction'} · {change.evidence_status} · {change.claim_id.replace('_', ' ').title()}"
        with st.expander(title, expanded=index == 1):
            if change.evidence_status == "PENDING": st.warning("Pending stays pending. No publication acceptance is verified.")
            before, after = st.columns(2)
            before.markdown("**Before — exact text**")
            before.code(change.before if change.before else "[No existing text; proposed addition]", language=None, wrap_lines=True)
            after.markdown("**After — exact proposed text**")
            after.code(change.after, language=None, wrap_lines=True)
            st.caption("Stable change ID: " + change.change_id)
            for anchor in change.anchors: st.caption("Source: " + anchor.reference)
            st.caption("Experimental qualifiers: " + "; ".join(f"{key}: {value}" for key, value in change.qualifiers))
            for text in (*change.limitations, *change.uncertainties): st.write("• " + text)
    with st.expander("Evidence statuses and unmapped content"):
        st.dataframe([{"Resume block": item.block_id, "Evidence status": item.evidence_status,
                       "Reviewed claim": item.claim_id or "No mapped claim"} for item in snapshot.proposal.assessments],
                     hide_index=True, width="stretch")
    st.caption(DOCX_LIMIT)
    with st.expander("Advanced Details"):
        st.text("Proposal fingerprint: " + snapshot.proposal.proposal_fingerprint)
        st.text("Resume fingerprint: " + snapshot.proposal.resume_sha256)
        for limitation in snapshot.proposal.limitations: st.write("• " + limitation)


def main():
    st.set_page_config(page_title="Internship Agent 2027 · Offline Demo", page_icon="IA", layout="wide",
                       menu_items={"Get Help": None, "Report a bug": None, "About": None})
    st.sidebar.title("Internship Agent 2027")
    st.sidebar.caption("Public offline demonstration")
    page = st.sidebar.radio("Explore the demo", PAGES, key="page")
    st.sidebar.caption("Read-only · Synthetic data · Local execution")
    st.sidebar.code(DATABASE_LABEL, language=None)
    st.info(demo.NOTICE)
    try:
        snapshot = load_snapshot(database_label=DATABASE_LABEL, public_root=demo.PUBLIC_ROOT)
    except (DemoInputError, OSError, ValueError, TypeError, KeyError, AttributeError, sqlite3.Error):
        st.error("The synthetic demo cannot be loaded safely. Its inputs may be missing, modified, busy or incompatible. No data was changed.")
        st.write("Create a new demo explicitly from the public staging root, or review existing disposable output using the Demo Guide.")
        st.code(".venv/Scripts/python.exe -B scripts/create_demo.py", language=None)
        st.caption("Initialization and recovery remain manual; this page never initializes, overwrites or repairs a database.")
        return
    {"Overview": overview, "Demo Jobs": jobs, "Application Tracker": applications, "General Resume": resume}[page](snapshot)


if __name__ == "__main__":
    main()
