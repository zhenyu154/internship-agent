"""Manual cross-platform discovery with SQLite page snapshots and one classifier."""

from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import hashlib
import html
import ipaddress
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from .ashby import AshbyBoard, AshbyClient, load_ashby_registry
from .config import ConfigurationError, load_config
from .database import JobDatabase, RunStateError
from .deduplication import canonicalize_url, normalize_text
from .greenhouse import GreenhouseBoard, GreenhouseClient, GreenhouseError, GreenhouseJob, _evidence, load_board_registry
from .lever import LeverClient, LeverSite, load_lever_registry
from .models import Job, JobMetadata
from .public_http import API_HOSTS, PublicGetTransport
from .relevance import EXCLUDED, MAIN_SHORTLIST, NEEDS_REVIEW, classify_greenhouse_job, preview_priority, source_internship_terms

UNKNOWN = "UNKNOWN"
REGISTRY_SPECS = {
    "greenhouse": ("greenhouse_boards.yaml", load_board_registry, "board_token", GreenhouseBoard),
    "lever": ("lever_sites.yaml", load_lever_registry, "site_token", LeverSite),
    "ashby": ("ashby_boards.yaml", load_ashby_registry, "board_name", AshbyBoard),
}


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class DiscoveredJob:
    source: str
    board: str
    posting_id: str
    company_name: str
    title: str
    location: str
    job_url: str
    application_url: str
    description: str
    published_at: str = UNKNOWN
    updated_at: str = UNKNOWN
    internship_term: str = UNKNOWN
    internship_term_evidence: str = UNKNOWN
    degree_requirements: str = UNKNOWN
    graduation_window: str = UNKNOWN
    work_authorization: str = UNKNOWN
    compensation: str = UNKNOWN
    team: str = UNKNOWN
    department: str = UNKNOWN
    employment_type: str = UNKNOWN
    is_listed: bool | None = None
    verified_at: str = UNKNOWN
    relevance_category: str = UNKNOWN
    relevance_reason: str = UNKNOWN

    @property
    def source_key(self):
        return f"{self.source}:{self.board}:{self.posting_id}"


@dataclass
class BoardCoverage:
    source: str
    board: str
    company: str
    status: str = "INCOMPLETE"
    raw_jobs: int = 0
    pages: int = 0
    pages_fetched_this_command: int = 0
    eligible: int = 0
    excluded: int = 0
    last_verified_at: str = UNKNOWN
    error: str = ""


@dataclass
class UnifiedResult:
    timestamp: str
    run_id: str | None
    coverage: list[BoardCoverage]
    all_jobs: list[DiscoveredJob]
    preview: list[DiscoveredJob]
    suspected_duplicates: list[dict]
    newly_saved: int
    existing_skipped: int
    candidate_cap: int
    display_limit: int
    save_all: bool
    mode: str
    http_requests: list[dict]

    @property
    def eligible(self):
        return [j for j in self.all_jobs if j.relevance_category != EXCLUDED]

    @property
    def counts(self):
        return dict(Counter(j.relevance_category for j in self.all_jobs))


def _official_url(value):
    if not isinstance(value, str) or value == UNKNOWN or not value:
        return UNKNOWN
    p = urlsplit(value)
    if p.scheme != "https" or not p.hostname or p.username is not None or p.password is not None:
        raise ValueError("Posting URL must be public HTTPS without credentials")
    if p.hostname in {"localhost"} or p.hostname.endswith((".local", ".localhost", ".internal")):
        raise ValueError("Local posting URLs are forbidden")
    try:
        address = ipaddress.ip_address(p.hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("Private posting URLs are forbidden")
    return canonicalize_url(value)


def normalize_posting(source, record, raw, preferences):
    board = getattr(record, REGISTRY_SPECS[source][2])
    description = html.unescape(raw.description or UNKNOWN)
    description = re.sub(r"\[data:image/[^\]]+\]", "", description).strip() or UNKNOWN
    posting_id = str(getattr(raw, "source_job_id", getattr(raw, "posting_id", UNKNOWN)))
    job_url = getattr(raw, "hosted_url", getattr(raw, "job_url", getattr(raw, "application_url", UNKNOWN)))
    apply_url = getattr(raw, "apply_url", getattr(raw, "application_url", UNKNOWN))
    job_url, apply_url = _official_url(job_url), _official_url(apply_url)
    if posting_id in {"", UNKNOWN} or raw.title in {"", UNKNOWN} or (job_url == UNKNOWN and apply_url == UNKNOWN):
        raise ValueError("Posting lacks a stable ID, title, or official URL")
    evidence = f"{raw.title}\n{description}"
    degree = _evidence(evidence, (r"\bdegree\b", r"bachelor", r"master", r"\b(?:BS|MS|BSc|MSc)\b", r"ph\.?d", r"doctoral"))
    graduation = _evidence(description, (r"graduat", r"class of", r"enroll"))
    work = _evidence(description, (r"\bsponsorship\b", r"work authorization", r"visa", r"legally authorized", r"authorization to work", r"citizenship", r"permanent resident", r"export control", r"security clearance"))
    terms = source_internship_terms(raw.title, description)
    term = "Summer 2027" if "Summer 2027" in terms else UNKNOWN
    job = DiscoveredJob(
        source=source, board=board, posting_id=posting_id, company_name=record.company_name,
        title=raw.title, location=raw.location or UNKNOWN, job_url=job_url,
        application_url=apply_url, description=description,
        published_at=getattr(raw, "published_at", UNKNOWN), updated_at=getattr(raw, "updated_at", UNKNOWN),
        internship_term=term, internship_term_evidence=_evidence(evidence,(r"summer",r"cohort",r"internship dates",r"2027")),
        degree_requirements=degree, graduation_window=graduation, work_authorization=work,
        compensation=getattr(raw,"compensation",UNKNOWN), team=getattr(raw,"team",UNKNOWN),
        department=getattr(raw,"department",UNKNOWN), employment_type=getattr(raw,"employment_type",UNKNOWN),
        is_listed=getattr(raw,"is_listed",None), verified_at=raw.verified_at,
    )
    shared = GreenhouseJob(
        job.company_name, job.board, job.posting_id, job.title, job.location, job.application_url,
        job.description, job.published_at, job.updated_at, job.internship_term,
        job.degree_requirements, job.graduation_window, job.work_authorization,
        job.job_url, job.verified_at,
    )
    decision = classify_greenhouse_job(shared,preferences)
    if source == "ashby" and job.is_listed is False:
        return replace(job,relevance_category=EXCLUDED,relevance_reason="Ashby isListed=false; public listing not verified")
    if source == "ashby" and job.is_listed is None and decision.category != EXCLUDED:
        return replace(job,relevance_category=NEEDS_REVIEW,relevance_reason=decision.reason+"; Ashby listing status UNKNOWN")
    return replace(job,relevance_category=decision.category,relevance_reason=decision.reason)


def suspected_cross_platform_duplicates(jobs):
    groups = defaultdict(list)
    for job in jobs:
        groups[normalize_text(job.company_name)].append(job)
    pairs = {}
    for company_jobs in groups.values():
        for index, a in enumerate(company_jobs):
            for b in company_jobs[index+1:]:
                if a.source == b.source:
                    continue
                aurls={_official_url(url) for url in (a.job_url,a.application_url) if url != UNKNOWN}
                burls={_official_url(url) for url in (b.job_url,b.application_url) if url != UNKNOWN}
                same_text = (normalize_text(a.title)==normalize_text(b.title)
                             and normalize_text(a.location)==normalize_text(b.location)
                             and len(a.description)>=100
                             and normalize_text(a.description)==normalize_text(b.description))
                if (aurls & burls) or same_text:
                    key=tuple(sorted((a.source_key,b.source_key)))
                    pairs[key]={"identities":list(key),"company":a.company_name,"title":a.title,
                                "reason":"Same official URL" if aurls & burls else "Identical title/location and substantial description",
                                "action":"Human review required; records remain separate"}
    return list(pairs.values())


@contextmanager
def exclusive_run_lock(database_path):
    """OS lock exists only while a save command is alive; no worker or scheduler."""
    path=Path(database_path)
    path.parent.mkdir(parents=True,exist_ok=True)
    stream=path.with_name(path.name+'.unified.lock').open('a+b')
    try:
        stream.seek(0,2)
        if stream.tell()==0:
            stream.write(b'0');stream.flush()
        stream.seek(0)
        try:
            import os
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as error:
            raise RunStateError("Another unified save is active; resume/start only after it exits") from error
        try:
            yield
        finally:
            stream.seek(0)
            if os.name=='nt':
                msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:
                fcntl.flock(stream.fileno(),fcntl.LOCK_UN)
    finally:
        stream.close()


class UnifiedDiscovery:
    def __init__(self,clients=None,transport=None):
        self.transport = transport or PublicGetTransport(API_HOSTS,max_requests=300,interval=0.35)
        self.clients = clients or {
            "greenhouse":GreenhouseClient(opener=self.transport,max_retries=2),
            "lever":LeverClient(opener=self.transport,max_retries=2),
            "ashby":AshbyClient(opener=self.transport,max_retries=2),
        }

    @staticmethod
    def _plans(config_dir,sources,boards):
        all_plans=[]
        for source,(filename,loader,token_field,_) in REGISTRY_SPECS.items():
            if sources and source not in sources:
                continue
            for record in loader(Path(config_dir)/filename):
                key=f"{source}:{getattr(record,token_field)}"
                valid_time=False
                try:
                    valid_time=datetime.fromisoformat(record.verified_at.replace('Z','+00:00')).tzinfo is not None
                except ValueError:
                    pass
                verified=getattr(record,'verification_status','') in {'','VERIFIED_SUPPORTED'} and valid_time
                if record.active and verified and (not boards or key in boards):
                    all_plans.append({'source':source,'board_key':key,'record':asdict(record)})
        if boards and set(boards)-{plan['board_key'] for plan in all_plans}:
            raise ConfigurationError("Selected board is absent, inactive, or unverified")
        if not all_plans:
            raise ConfigurationError("No active verified boards selected")
        return all_plans

    def run(self,config_path='config/search_preferences.yaml',config_dir='config',*,database_path='data/jobs.sqlite3',
            limit=20,save=False,save_all=False,sources=None,boards=None,max_candidates=None,resume=None):
        preferences=load_config(config_path)
        cap=preferences['discovery']['max_candidates_per_run'] if max_candidates is None else max_candidates
        if type(cap) is not int or cap<=0 or type(limit) is not int or limit<=0:
            raise ConfigurationError("Preview limit and candidate cap must be positive integers")
        if limit>cap:
            raise ConfigurationError("--limit exceeds max_candidates_per_run; use an explicit --max-candidates override")
        if (save_all or resume) and not save:
            raise ConfigurationError("--save-all and --resume require explicit --save")
        plans=self._plans(config_dir,sources,boards)
        settings={'plans':plans,'limit':limit,'cap':cap,'save_all':save_all}
        fingerprint=hashlib.sha256(Path(config_path).read_bytes()).hexdigest()
        if not save:
            return self._execute(plans,preferences,settings,None,None,{})
        with exclusive_run_lock(database_path):
            with JobDatabase(database_path) as database:
                if resume:
                    run=database.get_run(resume)
                    if run is None or run.run_type!='unified_discovery' or run.config_fingerprint!=fingerprint:
                        raise RunStateError("Resume ID/type/configuration fingerprint does not match this unified run")
                    snapshots=database.load_discovery_checkpoints(resume)
                    if snapshots.get('__manifest__')!=settings:
                        raise RunStateError("Resume board selection or save/preview policy changed; start a new explicit run")
                    database.resume_run(resume)
                    run_id=resume
                else:
                    run_id=database.start_run('unified_discovery',fingerprint,[plan['board_key'] for plan in plans]).run_id
                    database.save_discovery_checkpoint(run_id,'__manifest__',settings)
                    snapshots=database.load_discovery_checkpoints(run_id)
                try:
                    return self._execute(plans,preferences,settings,database,run_id,snapshots)
                except BaseException as error:
                    # Hard process termination leaves RUNNING; explicit resume is protected by the OS lock.
                    try:database.interrupt_run(run_id,str(error) or 'User interrupted command')
                    except Exception:pass
                    raise

    def _execute(self,plans,preferences,settings,database,run_id,snapshots):
        timestamp=utc_now()
        coverage=[]
        all_jobs={}
        for plan in plans:
            source=plan['source'];board_key=plan['board_key']
            record=REGISTRY_SPECS[source][3](**plan['record'])
            board=board_key.split(':',1)[1]
            state=BoardCoverage(source,board,record.company_name)
            coverage.append(state)
            offset=0;terminal=False;seen_ids=set();page_number=0
            if database:
                item=next(i for i in database.get_work_items(run_id) if i.item_key==board_key)
                if item.state!='COMPLETED':database.save_item_progress(run_id,board_key,'IN_PROGRESS')
            def accept(snapshot):
                nonlocal page_number
                state.raw_jobs+=snapshot['raw_count'];state.pages+=1;page_number+=1
                state.last_verified_at=snapshot['verified_at']
                for data in snapshot['jobs']:
                    job=DiscoveredJob(**data)
                    seen_ids.add(job.posting_id)
                    all_jobs[job.source_key]=job
            while True:
                page_key=f'page:{board_key}:{offset}'
                if page_key not in snapshots:break
                snapshot=snapshots[page_key];accept(snapshot)
                terminal=snapshot['terminal']
                if terminal:break
                offset+=self.clients[source].page_limit
            try:
                if not terminal:
                    if source=='lever':
                        pages=self.clients[source].iter_site_pages(record,start_skip=offset)
                    else:
                        raw=self.clients[source].fetch_jobs(record) if source=='greenhouse' else self.clients[source].fetch_board(board)
                        pages=iter([(str(offset),raw)])
                    for key,raw_page in pages:
                        if source=='lever':offset=int(key.rsplit(':',1)[1])
                        page_key=f'page:{board_key}:{offset}'
                        # Validate before checkpointing; malformed records are never called a complete scan.
                        normalized=[normalize_posting(source,record,raw,preferences) for raw in raw_page]
                        ids={j.posting_id for j in normalized}
                        if normalized and ids & seen_ids:
                            raise ValueError('Repeated/overlapping Lever page; retrieval INCOMPLETE')
                        terminal=source!='lever' or len(raw_page)<self.clients[source].page_limit
                        snapshot={'raw_count':len(raw_page),'terminal':terminal,
                                  'verified_at':max((j.verified_at for j in normalized),default=utc_now()),
                                  'jobs':[asdict(j) for j in normalized]}
                        if database:database.save_discovery_checkpoint(run_id,page_key,snapshot)
                        snapshots[page_key]=snapshot
                        state.pages_fetched_this_command+=1;accept(snapshot)
                    if not terminal:
                        raise ValueError('Adapter stopped before a terminal page; retrieval INCOMPLETE')
                state.status='COMPLETED'
                if database:
                    database.save_item_progress(run_id,board_key,'COMPLETED')
            except (GreenhouseError,ValueError,OSError) as error:
                state.status='INCOMPLETE';state.error=str(error)
                if database:database.save_item_progress(run_id,board_key,'FAILED',state.error)
            board_jobs=[j for j in all_jobs.values() if j.source==source and j.board==board]
            state.eligible=sum(j.relevance_category!=EXCLUDED for j in board_jobs)
            state.excluded=sum(j.relevance_category==EXCLUDED for j in board_jobs)
        jobs=list(all_jobs.values())
        eligible=sorted([j for j in jobs if j.relevance_category!=EXCLUDED],key=lambda j:preview_priority(j,preferences))
        preview=eligible[:settings['limit']]
        selected=eligible if settings['save_all'] else preview
        historical=[]
        if database:
            for record in database.list_jobs():
                if record.job.source not in REGISTRY_SPECS or ':' not in record.job.source_job_id:continue
                meta=database.get_job_metadata(record.id)
                historical.append(DiscoveredJob(record.job.source,*record.job.source_job_id.split(':',1),
                    record.job.company,record.job.title,record.job.location,
                    meta.source_url if meta else record.job.url,record.job.url,record.job.description))
        suspects=suspected_cross_platform_duplicates(list({j.source_key:j for j in historical+jobs}.values()))
        newly_saved=existing=0
        if database:
            for job in selected:
                checkpoint=f'saved:{job.source_key}'
                if checkpoint in snapshots:
                    newly_saved+=int(snapshots[checkpoint]['created']);existing+=int(not snapshots[checkpoint]['created'])
                    continue
                result=database.add_job(Job(
                    title=job.title,company=job.company_name,location='' if job.location==UNKNOWN else job.location,
                    url=job.application_url if job.application_url!=UNKNOWN else job.job_url,
                    source=job.source,source_job_id=f'{job.board}:{job.posting_id}',description=job.description,
                ),source_identity_only=True)
                database.save_job_metadata(JobMetadata(
                    job_id=result.record.id,source_url=job.job_url,greenhouse_board_token=job.board if job.source=='greenhouse' else '',
                    published_at=job.published_at,updated_at=job.updated_at,internship_term=job.internship_term,
                    degree_requirements=job.degree_requirements,graduation_window=job.graduation_window,
                    work_authorization=job.work_authorization,compensation=job.compensation,
                    relevance_category=job.relevance_category,relevance_reason=job.relevance_reason,verified_at=job.verified_at,
                ))
                database.save_discovery_checkpoint(run_id,checkpoint,{'created':result.created,'job_id':result.record.id})
                newly_saved+=int(result.created);existing+=int(not result.created)
            if any(c.status!='COMPLETED' for c in coverage):database.interrupt_run(run_id,'Incomplete boards; explicitly resume to retry')
            else:database.complete_run(run_id)
        return UnifiedResult(timestamp,run_id,coverage,jobs,preview,suspects,newly_saved,existing,
                             settings['cap'],settings['limit'],settings['save_all'],'save' if database else 'dry-run',self.transport.requests)
