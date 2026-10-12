"""Readable prioritized unified discovery reports with explicit coverage gaps."""

from dataclasses import asdict
import json
from pathlib import Path

from .relevance import MAIN_SHORTLIST, NEEDS_REVIEW, preview_priority


def cell(value):
    return str(value).replace('|','/').replace('\n',' ').replace('<','&lt;').replace('>','&gt;')


def write_unified_report(result,path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    completed=sum(c.status=='COMPLETED' for c in result.coverage)
    incomplete=len(result.coverage)-completed
    counts=result.counts
    lines=['# Unified internship discovery', '',
        f'UTC run timestamp: {result.timestamp}; mode: {result.mode}; execution run: {result.run_id or "NONE (preview only)"}.', '',
        f'Coverage: {len(result.coverage)} boards attempted, {completed} completed, {incomplete} INCOMPLETE. '
        f'Raw postings: {sum(c.raw_jobs for c in result.coverage)}; eligible: {len(result.eligible)}; '
        f'EXCLUDED: {counts.get("EXCLUDED",0)}; MAIN_SHORTLIST: {counts.get("MAIN_SHORTLIST",0)}; '
        f'NEEDS_REVIEW: {counts.get("NEEDS_REVIEW",0)}.', '',
        f'Confirmed Summer 2027 evidence among eligible findings: {sum(j.internship_term=="Summer 2027" for j in result.eligible)}. '
        f'New rows saved: {result.newly_saved}; existing identities skipped: {result.existing_skipped}.', '',
        f'Preview limit: {result.display_limit}; configured/explicit candidate cap: {result.candidate_cap}. '
        + ('--save-all explicitly saves all eligible findings independently of both preview order and candidate cap.' if result.save_all else 'Default save selects only the prioritized preview; all sources are still scanned.'), '',
        'No current student, work authorization, sponsorship, CPT/OPT, physical-robot experience, or availability claim is invented. '
        'Technical priority is separate from eligibility category. A high-value NEEDS_REVIEW role can lead the preview.', '',
        '## Source coverage', '',
        '| Company | Platform / board | Retrieval | Raw postings | Pages retained | Pages fetched this command | Eligible | Excluded | Last successful verification UTC | Errors |',
        '|---|---|---|---:|---:|---:|---:|---:|---|---|']
    for c in result.coverage:
        values=[c.company,f'{c.source}:{c.board}',c.status,c.raw_jobs,c.pages,c.pages_fetched_this_command,c.eligible,c.excluded,c.last_verified_at,c.error or 'None']
        lines.append('| '+' | '.join(cell(v) for v in values)+' |')
    lines += ['', '## Prioritized review queue', '',
        f'Displaying {len(result.preview)} real eligible positions out of {len(result.eligible)} found. '
        'Order: direct robot learning/manipulation, related ML/world models/autonomy/simulation, robotics software/infrastructure, hardware review; location/name/identity break ties.', '',
        '| # | Company / role | Location | Source | Technical tier | Classification and relevance | Internship term / evidence | Degree / graduation evidence | Work authorization | Official job URL | Application URL (human action only) | Verified UTC |',
        '|---:|---|---|---|---:|---|---|---|---|---|---|---|']
    for index,j in enumerate(result.preview,1):
        values=[index,f'{j.company_name}: {j.title}',j.location,j.source,preview_priority(j)[0],
                f'{j.relevance_category}: {j.relevance_reason}', f'{j.internship_term}: {j.internship_term_evidence}',
                f'Degree: {j.degree_requirements}; Graduation: {j.graduation_window}',j.work_authorization,
                f'[{j.source_key}]({j.job_url})' if j.job_url!='UNKNOWN' else 'UNKNOWN',
                f'[Application]({j.application_url})' if j.application_url!='UNKNOWN' else 'UNKNOWN',j.verified_at]
        lines.append('| '+' | '.join(cell(v) for v in values)+' |')
    subsets=[('Direct robot learning / manipulation',[j for j in result.preview if preview_priority(j)[0]==1]),
             ('Confirmed Summer 2027',[j for j in result.preview if j.internship_term=='Summer 2027']),
             ('High-value NEEDS_REVIEW',[j for j in result.preview if j.relevance_category==NEEDS_REVIEW and preview_priority(j)[0]<=2]),
             ('Other software / ML engineering',[j for j in result.preview if preview_priority(j)[0]==3])]
    for title,jobs in subsets:
        lines+=['',f'## {title}','']
        lines.extend([f'- {j.company_name} / {j.title}: [{j.source_key}]({j.job_url}) ({j.relevance_category})' for j in jobs]
                     or ['No positions in the displayed preview; no openings invented.'])
    lines+=['','## Eligibility questions for human review','',
        '- Verify candidate work authorization and any explicit visa/sponsorship restriction; missing source evidence is UNKNOWN, not rejection.',
        '- Verify Summer 2027 cohort availability. An internship or 2027 title alone does not establish Summer 2027.',
        '- Verify required versus preferred degrees, graduation window, return-to-school requirements, and location/relocation.',
        '- Review specialized hardware/physical deployment/formal-verification requirements against verified experience.', '',
        '## Incomplete retrieval / recovery','']
    lines.extend([f'- {c.source}:{c.board}: INCOMPLETE; {cell(c.error)}. Completed page snapshots remain retained; retry explicitly.' for c in result.coverage if c.status!='COMPLETED']
                 or ['All selected boards reached their complete-list/terminal-page condition.'])
    lines+=['','## Suspected cross-platform duplicates','']
    lines.extend([f'- {p["company"]} / {p["title"]}: {", ".join(p["identities"])}; {p["reason"]}. Human review; kept separate.' for p in result.suspected_duplicates]
                 or ['None detected with credible matching URL or identical substantial description evidence. No uncertain records merged.'])
    lines+=['','## Data and execution boundary','',
        'Existing historical job fields and strong identities remain unchanged. Source metadata may be reverified during explicit saves. '
        'A complete page checkpoint means its JSON snapshot is durable in the canonical SQLite database; it does not by itself mean that every job is saved. '
        'Default preview opens no database and creates no execution records. There is no scheduler, daemon, account access, application endpoint request, or submission.', '',
        'Published/updated timestamps remain separate; neither is asserted to be the original creation date unless the source establishes that meaning. '
        'Full normalized source findings and accounting accompany this report in the adjacent JSON file.']
    path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    path.with_suffix('.json').write_text(json.dumps(asdict(result),ensure_ascii=False,indent=2),encoding='utf-8')
    return path
