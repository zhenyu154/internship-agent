"""Manual research evidence verification and append-only ATS registration.

The input JSON is a research handoff, not an authoritative registry. Only the
three existing ATS YAML files store registered boards. This workflow never opens
SQLite or collects jobs into it.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urljoin, urlsplit

import yaml

from .ashby import AshbyClient
from .config import ConfigurationError, _yaml_load
from .greenhouse import GreenhouseBoard, GreenhouseClient, GreenhouseError
from .lever import LeverClient, LeverSite
from .public_http import API_HOSTS, BOARD_HOSTS, PublicAccessError, PublicGetTransport, validate_https_url

SUPPORTED = "VERIFIED_SUPPORTED"
UNSUPPORTED = "VERIFIED_UNSUPPORTED"
REVIEW = "NEEDS_REVIEW"
INACTIVE = "INACTIVE"
REGISTRIES = {
    "Greenhouse": ("greenhouse_boards.yaml", "boards", "board_token"),
    "Lever": ("lever_sites.yaml", "sites", "site_token"),
    "Ashby": ("ashby_boards.yaml", "boards", "board_name"),
}


@dataclass(frozen=True)
class CompanyCandidate:
    company_name: str
    official_website: str
    official_careers_url: str
    evidence_url: str
    technical_focus: str
    region: str
    inclusion_reason: str
    board_url: str = ""
    aliases: tuple[str, ...] = ()
    china_operations_evidence: str = ""
    evidence_snapshot: str = ""


@dataclass(frozen=True)
class CompanyVerification:
    candidate: CompanyCandidate
    ats_platform: str
    token: str
    public_board_url: str
    verified_at: str
    status: str
    reason: str
    raw_postings: int = 0
    ownership_confirmed: bool = False
    careers_verified: bool = False


def normalize_name(value):
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def recognize_ats_url(url):
    p = urlsplit(url)
    validate_https_url(url, BOARD_HOSTS)
    parts = [part for part in p.path.split("/") if part]
    if not parts:
        raise PublicAccessError("ATS URL is missing a board/site token")
    if p.hostname in {"boards.greenhouse.io", "job-boards.greenhouse.io"}:
        platform = "Greenhouse"
        token = parse_qs(p.query).get("for", [""])[0] if parts[0] == "embed" else parts[0]
        host = "boards.greenhouse.io"
    elif p.hostname == "jobs.lever.co":
        platform, token, host = "Lever", parts[0], p.hostname
    else:
        platform, token, host = "Ashby", parts[0], p.hostname
    pattern = r"[A-Za-z0-9._-]+" if platform == "Ashby" else r"[A-Za-z0-9_-]+"
    if not re.fullmatch(pattern, token):
        raise PublicAccessError("Invalid or guessed ATS token")
    return platform, token, f"https://{host}/{token}"


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.urls = []
    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name in {"href", "src"} and value:
                self.urls.append(value)


def public_links(html, base_url):
    parser = _Links()
    parser.feed(html)
    # Some official pages embed a board URL in serialized page data. Inspect
    # strings as evidence only; do not run scripts or follow their instructions.
    decoded = unescape(html).replace("\\/", "/")
    strings = re.findall(r"https://(?:boards\.greenhouse\.io|job-boards\.greenhouse\.io|jobs\.lever\.co|jobs\.ashbyhq\.com)/[^\s\"'<>\\]+", decoded)
    return set(urljoin(base_url, url) for url in parser.urls + strings)


def identity_matches(candidate, html):
    text = normalize_name(unescape(re.sub(r"<[^>]+>", " ", html)))
    return any(len(normalize_name(name)) >= 3 and normalize_name(name) in text
               for name in (candidate.company_name, *candidate.aliases))


def load_candidates(path):
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list) or len(raw) > 30:
        raise ConfigurationError("Company research input must be a list of at most 30 candidates")
    result, seen = [], set()
    fields = set(CompanyCandidate.__dataclass_fields__)
    for item in raw:
        if not isinstance(item, dict) or set(item) - fields:
            raise ConfigurationError("Company research contains unknown fields")
        candidate = CompanyCandidate(**{**item, "aliases": tuple(item.get("aliases", ()))})
        if not candidate.company_name or normalize_name(candidate.company_name) in seen:
            raise ConfigurationError("Company names must be non-empty and unique")
        seen.add(normalize_name(candidate.company_name))
        result.append(candidate)
    return result


class CompanyVerifier:
    def __init__(self, candidates, transport=None):
        hosts = set(API_HOSTS | BOARD_HOSTS)
        for candidate in candidates:
            hosts.update(urlsplit(url).hostname for url in (
                candidate.official_website, candidate.official_careers_url, candidate.evidence_url
            ) if url)
        self.transport = transport or PublicGetTransport(hosts)
        self.greenhouse = GreenhouseClient(opener=self.transport, max_retries=1)
        self.lever = LeverClient(opener=self.transport, max_retries=1)
        self.ashby = AshbyClient(opener=self.transport, max_retries=1)
        self.cache = {}

    def verify_board(self, platform, token):
        key = platform, token
        if key not in self.cache:
            if platform == "Greenhouse":
                payload = self.greenhouse.fetch_board_payload(token)
                self.cache[key] = len(payload["jobs"])
            elif platform == "Lever":
                count = sum(len(jobs) for _, jobs in self.lever.iter_site_pages(token))
                self.cache[key] = count
            else:
                self.cache[key] = len(self.ashby.fetch_board(token))
        return self.cache[key]

    def verify(self, candidate):
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        platform, token, board_url = "UNKNOWN", "", ""
        careers_verified = False
        owned = False
        try:
            if not candidate.official_careers_url or not candidate.evidence_url:
                raise PublicAccessError("Missing official careers or evidence URL")
            official_host = urlsplit(candidate.official_website).hostname
            evidence_host = urlsplit(candidate.evidence_url).hostname
            # An ATS page alone is not proof of company ownership.
            if not official_host or official_host in API_HOSTS | BOARD_HOSTS:
                raise PublicAccessError("Official company website must be independently identified")
            if evidence_host != official_host and not (
                evidence_host and (evidence_host.endswith('.'+official_host) or official_host.endswith('.'+evidence_host))
            ):
                raise PublicAccessError("Ownership evidence must be on the official company domain")
            evidence = self.transport.page(candidate.evidence_url)
            # Browser-rendered snapshots are an explicit, reviewed research handoff.
            # Fetch/robots policy must still pass; snapshots never bypass a restriction.
            snapshot_links = set()
            if candidate.evidence_snapshot:
                path = Path(candidate.evidence_snapshot).resolve()
                if not path.is_relative_to(Path("reports").resolve()):
                    raise PublicAccessError("Research snapshots must reside under reports/")
                snapshot = json.loads(path.read_text(encoding="utf-8"))
                if snapshot.get("observed_url", "").rstrip("/") != candidate.evidence_url.rstrip("/"):
                    raise PublicAccessError("Rendered snapshot URL does not match official evidence")
                if snapshot.get("capture_method") != "Codex reviewed official careers DOM":
                    raise PublicAccessError("Rendered evidence needs an explicit research capture method")
                evidence += "\n" + snapshot.get("body_text", "")
                snapshot_links = set(snapshot.get("links", []))
            if not identity_matches(candidate, evidence):
                raise PublicAccessError("Official page does not confirm the company name or a documented alias")
            links = public_links(evidence, candidate.evidence_url) | snapshot_links
            if candidate.official_careers_url != candidate.evidence_url:
                if candidate.official_careers_url not in links:
                    raise PublicAccessError("Evidence does not link to the supplied official careers URL")
            careers_verified = True
            ats_links = []
            for link in sorted(links):
                if urlsplit(link).hostname in BOARD_HOSTS:
                    try:
                        ats_links.append(recognize_ats_url(link))
                    except PublicAccessError:
                        continue
            if candidate.board_url:
                requested = recognize_ats_url(candidate.board_url)
                if requested not in ats_links:
                    raise PublicAccessError("Board URL/token is not linked by official ownership evidence")
                platform, token, board_url = requested
            elif len(set(ats_links)) == 1:
                platform, token, board_url = ats_links[0]
            elif len(set(ats_links)) > 1:
                raise PublicAccessError("Multiple board mappings require explicit ownership review")
            else:
                workday = [url for url in links if (urlsplit(url).hostname or '').endswith('myworkdayjobs.com')]
                other = [url for url in links if (urlsplit(url).hostname or '').endswith(('jobs.feishu.cn', 'eightfold.ai'))]
                own_jobs = [url for url in links if urlsplit(url).hostname == urlsplit(candidate.official_careers_url).hostname and '/jobs/' in urlsplit(url).path]
                confirmed_custom = bool(workday or other or own_jobs or 'lifeattiktok.com' in candidate.official_careers_url)
                platform = "Workday" if workday else "Feishu / other ATS" if other else "Company-built careers frontend" if confirmed_custom else "UNKNOWN"
                status = UNSUPPORTED if confirmed_custom else REVIEW
                return CompanyVerification(candidate, platform, "", "", timestamp, status,
                                           "Official careers verified; no supported public board established; underlying provider may require review", careers_verified=True)
            owned = True
            count = self.verify_board(platform, token)
            return CompanyVerification(candidate, platform, token, board_url, timestamp, SUPPORTED,
                                       "Company-owned careers evidence links the board; public API schema validated",
                                       count, True, careers_verified)
        except HTTPError as error:
            status = INACTIVE if error.code in {404, 410} else REVIEW
            return CompanyVerification(candidate, platform, token, board_url, timestamp, status,
                                       f"Public verification HTTP {error.code}; no access restriction bypassed",
                                       ownership_confirmed=owned, careers_verified=careers_verified)
        except (PublicAccessError, GreenhouseError, URLError, OSError, ValueError) as error:
            status = INACTIVE if getattr(error, "status", None) in {404, 410} else REVIEW
            return CompanyVerification(candidate, platform, token, board_url, timestamp, status, str(error),
                                       ownership_confirmed=owned, careers_verified=careers_verified)


def register_companies(results, config_dir, *, save=False):
    """Preflight all ownership conflicts, then append to existing registries only."""
    config_dir = Path(config_dir)
    documents, originals, ownership, companies = {}, {}, {}, {}
    for platform, (filename, collection, token_field) in REGISTRIES.items():
        path = config_dir / filename
        originals[platform] = path.read_bytes()
        documents[platform] = _yaml_load(originals[platform].decode('utf-8'), path)
        rows = documents[platform][collection]
        for row in rows:
            key = platform, row[token_field].casefold()
            if key in ownership:
                raise ConfigurationError("Duplicate board identity in existing registry")
            ownership[key] = normalize_name(row['company_name'])
            companies[normalize_name(row['company_name'])] = key
    additions, duplicates = [], 0
    for result in results:
        if result.status != SUPPORTED:
            continue
        if not result.ownership_confirmed:
            raise ConfigurationError("An API response alone does not prove board ownership")
        key = result.ats_platform, result.token.casefold()
        names = {normalize_name(name) for name in (result.candidate.company_name, *result.candidate.aliases)}
        if key in ownership:
            if ownership[key] not in names:
                raise ConfigurationError(f"Conflicting board ownership: {key}")
            duplicates += 1
            continue
        if any(name in companies and companies[name] != key for name in names):
            raise ConfigurationError("Company alias maps to another registered board; manual review required")
        filename, collection, token_field = REGISTRIES[result.ats_platform]
        row = {
            'company_name': result.candidate.company_name, token_field: result.token,
            'source_url': result.public_board_url, 'verified_at': result.verified_at, 'active': True,
            'ats_platform': result.ats_platform,
            'official_careers_url': result.candidate.official_careers_url,
            'evidence_url': result.candidate.evidence_url, 'verification_status': SUPPORTED,
        }
        documents[result.ats_platform][collection].append(row)
        additions.append(row)
        ownership[key] = normalize_name(result.candidate.company_name)
        for name in names:
            companies[name] = key
    if save:
        # Never replace a file modified concurrently since preflight.
        for platform, original in originals.items():
            filename = REGISTRIES[platform][0]
            if (config_dir / filename).read_bytes() != original:
                raise ConfigurationError("Registry changed during verification; retry explicitly")
        for platform, document in documents.items():
            filename, collection, _ = REGISTRIES[platform]
            original_document = _yaml_load(originals[platform].decode('utf-8'), config_dir / filename)
            if document == original_document:
                continue
            staged = None
            try:
                with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',newline='\n',dir=config_dir,
                                                 prefix=f'.{filename}.',suffix='.tmp',delete=False) as stream:
                    staged = Path(stream.name)
                    yaml.safe_dump(document, stream, sort_keys=False, allow_unicode=True)
                os.replace(staged, config_dir / filename)
            finally:
                if staged is not None:
                    staged.unlink(missing_ok=True)
    return {'additions':additions, 'duplicates_skipped':duplicates, 'saved':save}


def write_research_report(path, results, registration):
    lines = ['# Company discovery Step 9A', '',
             'Manual public research handoff verified with official careers evidence and existing read-only ATS clients. No jobs were saved and SQLite was not opened by this workflow.', '',
             '| Company | Technical focus | Official website | Official careers | ATS / token | Public board URL | Ownership evidence | UTC verified | Status | Inclusion reason / unresolved issues |',
             '|---|---|---|---|---|---|---|---|---|---|']
    for r in results:
        c=r.candidate
        cells=[c.company_name,c.technical_focus,c.official_website,c.official_careers_url,
               f'{r.ats_platform} / {r.token or "N/A"}', r.public_board_url or "N/A", c.evidence_url,r.verified_at,r.status,
               f'{c.inclusion_reason}; {r.reason}' + (f'; China-operation evidence to review: {c.china_operations_evidence}' if c.china_operations_evidence else '')]
        lines.append('| '+' | '.join(str(x).replace('|','/').replace('\n',' ') for x in cells)+' |')
    lines += ['', f'Proposed additions: {len(registration["additions"])}; already registered: {registration["duplicates_skipped"]}.', '',
              'This input evidence file is not an authoritative registry. The three existing ATS registry files remain authoritative. API success alone never establishes company ownership.', '',
              'Live web research is not automatically resumable. Retain the reviewed candidate JSON and rerun verification manually. Verification responses are cached only during one command; registration is idempotent. Registry files are replaced atomically one at a time after conflict preflight; a filesystem failure between platforms can be safely retried.', '',
              'No inference is made about internships, visa sponsorship, work authorization, employee ethnicity, or candidate eligibility. Unsupported employers are retained above rather than discarded.']
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text('\n'.join(lines)+'\n',encoding='utf-8')
