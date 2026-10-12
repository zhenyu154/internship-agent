"""Read-only Lever Postings API access and safe posting normalization."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
import socket
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from .config import ConfigurationError
from .registry_metadata import read_provenance, provenance_fields
from .greenhouse import GreenhouseDataError, GreenhouseError, _evidence, html_to_safe_text

LEVER_API_HOST = "api.lever.co"
LEVER_API_ROOT = f"https://{LEVER_API_HOST}/v0/postings"
UNKNOWN = "UNKNOWN"


class LeverError(GreenhouseError):
    """Base Lever error."""


class LeverDataError(LeverError):
    """Malformed Lever response data."""


class LeverHTTPError(LeverError):
    def __init__(self, status: int, url: str, message: str = "") -> None:
        detail = f": {message}" if message else ""
        super().__init__(f"Lever HTTP {status} for {url}{detail}")
        self.status = status
        self.url = url


@dataclass(frozen=True, slots=True)
class LeverSite:
    company_name: str
    site_token: str
    source_url: str
    verified_at: str
    active: bool
    ats_platform: str = ""
    official_careers_url: str = ""
    evidence_url: str = ""
    verification_status: str = ""


@dataclass(frozen=True, slots=True)
class LeverJob:
    company_name: str
    site_token: str
    posting_id: str
    title: str
    location: str
    country: str
    employment_type: str
    commitment: str
    team: str
    department: str
    description: str
    hosted_url: str
    apply_url: str
    work_authorization: str
    degree_requirements: str
    graduation_window: str
    internship_term: str
    verified_at: str
    relevance_category: str = UNKNOWN
    relevance_reason: str = UNKNOWN


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else UNKNOWN


def _identifier(value: Any) -> str:
    if isinstance(value, (int, str)) and str(value).strip():
        return str(value).strip()
    return UNKNOWN


def _timestamp(value: Any) -> str:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    return _text(value)


def _field(mapping: Any, key: str) -> str:
    return _text(mapping.get(key)) if isinstance(mapping, dict) else UNKNOWN


def _description(raw: dict[str, Any]) -> str:
    plain = raw.get("descriptionPlain")
    if isinstance(plain, str) and plain.strip():
        description = plain.strip()
    else:
        description = html_to_safe_text(raw.get("description"))
    lists = raw.get("lists")
    if isinstance(lists, list):
        extras = []
        for item in lists:
            if isinstance(item, dict):
                heading = _text(item.get("text"))
                content = html_to_safe_text(item.get("content"))
                if heading != UNKNOWN:
                    extras.append(heading)
                if content != UNKNOWN:
                    extras.append(content)
        if extras:
            description = "\n\n".join(part for part in [description, *extras] if part != UNKNOWN)
    additional = _text(raw.get("additionalPlain"))
    if additional == UNKNOWN:
        additional = html_to_safe_text(raw.get("additional"))
    if additional != UNKNOWN:
        description = "\n\n".join(part for part in (description, additional) if part != UNKNOWN)
    return description or UNKNOWN


def _locations(categories: Any) -> str:
    if not isinstance(categories, dict):
        return UNKNOWN
    values = []
    for key in ("location", "allLocations"):
        value = categories.get(key)
        if isinstance(value, list):
            values.extend(str(item) for item in value if item)
        elif isinstance(value, str) and value.strip():
            values.append(value.strip())
    return "; ".join(dict.fromkeys(values)) or UNKNOWN


def _term(text: str) -> str:
    years = set(re.findall(r"\b(?:Summer|Fall|Winter|Spring)\s+20\d{2}\b", text, re.I))
    summer_2027 = [value for value in years if value.casefold() == "summer 2027"]
    if summer_2027 and len(years) <= 1:
        return "Summer 2027"
    return UNKNOWN


def _validate_site(site: str) -> str:
    if not isinstance(site, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", site):
        raise ValueError(f"Invalid Lever site token: {site!r}")
    return site


def site_api_url(site: str, skip: int = 0, limit: int = 100) -> str:
    if type(skip) is not int or skip < 0 or type(limit) is not int or limit <= 0:
        raise ValueError("Lever pagination values are invalid")
    token = _validate_site(site)
    return f"{LEVER_API_ROOT}/{token}?{urlencode({'mode': 'json', 'skip': skip, 'limit': limit})}"


def load_lever_registry(path: str | Path) -> list[LeverSite]:
    try:
        import yaml
    except ModuleNotFoundError as error:
        raise ConfigurationError("PyYAML is required to load the Lever registry") from error
    source = Path(path)
    try:
        data = yaml.safe_load(source.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ConfigurationError(f"Lever registry not found: {source}") from error
    except yaml.YAMLError as error:
        raise ConfigurationError(f"Invalid Lever registry YAML: {error}") from error
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("sites"), list):
        raise ConfigurationError("Lever registry must contain version 1 and a sites list")
    sites = []
    seen = set()
    for index, raw in enumerate(data["sites"]):
        expected = {"company_name", "site_token", "source_url", "verified_at", "active"}
        if not isinstance(raw, dict):
            raise ConfigurationError(f"Lever registry site {index} must be a mapping")
        provenance = read_provenance(raw, expected)
        token = _validate_site(raw["site_token"])
        if token in seen:
            raise ConfigurationError(f"Duplicate Lever site token: {token}")
        seen.add(token)
        parsed = urlsplit(_text(raw["source_url"]))
        if parsed.scheme != "https" or parsed.hostname != "jobs.lever.co":
            raise ConfigurationError(f"Invalid Lever source URL for {token}")
        if not isinstance(raw["active"], bool):
            raise ConfigurationError(f"Lever active flag must be boolean for {token}")
        sites.append(LeverSite(_text(raw["company_name"]), token, _text(raw["source_url"]), _text(raw["verified_at"]), raw["active"], **provenance))
    return sites


def save_lever_registry(path: str | Path, sites: list[LeverSite]) -> None:
    import yaml
    payload = {"version": 1, "sites": [
        {"company_name": site.company_name, "site_token": site.site_token,
         "source_url": site.source_url, "verified_at": site.verified_at, "active": site.active, **provenance_fields(site)}
        for site in sites
    ]}
    Path(path).write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8", newline="\n")


class LeverClient:
    def __init__(self, timeout: float = 15.0, max_retries: int = 2, min_interval: float = 0.25,
                 page_limit: int = 100, opener: Callable[..., Any] | None = None,
                 sleeper: Callable[[float], None] | None = None) -> None:
        if timeout <= 0 or max_retries < 0 or min_interval < 0 or page_limit <= 0:
            raise ValueError("Invalid Lever client limits")
        self.timeout = timeout
        self.max_retries = max_retries
        self.min_interval = min_interval
        self.page_limit = page_limit
        self._opener = opener or urlopen
        self._sleeper = sleeper or time.sleep
        self._last_request = 0.0

    def _request_page(self, site: str, skip: int) -> list[dict[str, Any]]:
        url = site_api_url(site, skip, self.page_limit)
        request = Request(url, method="GET", headers={"Accept": "application/json", "User-Agent": "InternshipAgent/2027"})
        for attempt in range(self.max_retries + 1):
            delay = self.min_interval - (time.monotonic() - self._last_request)
            if delay > 0:
                self._sleeper(delay)
            self._last_request = time.monotonic()
            try:
                with self._opener(request, timeout=self.timeout) as response:
                    status = getattr(response, "status", None) or response.getcode()
                    body = response.read()
                if status != 200:
                    raise LeverHTTPError(status, url)
                data = json.loads(body.decode("utf-8"))
                if not isinstance(data, list):
                    raise LeverDataError(f"Lever response must be a JSON list: {url}")
                if any(not isinstance(item, dict) for item in data):
                    raise LeverDataError(f"Lever page contains malformed posting entries: {url}")
                return data
            except HTTPError as error:
                if error.code not in {429, 500, 502, 503, 504} or attempt >= self.max_retries:
                    raise LeverHTTPError(error.code, url, error.reason) from error
            except (TimeoutError, socket.timeout, URLError) as error:
                if attempt >= self.max_retries:
                    raise LeverError(f"Lever request timed out or failed: {url}") from error
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise LeverDataError(f"Malformed Lever JSON: {url}") from error
            if attempt < self.max_retries:
                self._sleeper(min(2.0, 0.5 * (2 ** attempt)))
        raise LeverError(f"Lever request failed: {url}")

    def iter_site_pages(self, site: str | LeverSite, start_skip: int = 0) -> Iterator[tuple[str, list[LeverJob]]]:
        site_token = site.site_token if isinstance(site, LeverSite) else site
        company_name = site.company_name if isinstance(site, LeverSite) else UNKNOWN
        if type(start_skip) is not int or start_skip < 0:
            raise ValueError("start_skip must be a non-negative integer")
        skip = start_skip
        seen_pages = set()
        verified_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        while True:
            raw_jobs = self._request_page(site_token, skip)
            signature = tuple(sorted(str(job.get("id", "")) for job in raw_jobs))
            if signature and signature in seen_pages:
                raise LeverDataError("Lever repeated a page; board retrieval is INCOMPLETE")
            seen_pages.add(signature)
            if len(seen_pages) > 200:
                raise LeverDataError("Lever page budget exceeded; board retrieval is INCOMPLETE")
            jobs = [self._parse_job(site_token, company_name, raw, verified_at) for raw in raw_jobs]
            yield f"{site_token}:{skip}", jobs
            if len(raw_jobs) < self.page_limit:
                break
            skip += self.page_limit

    def fetch_site(self, site: LeverSite) -> list[LeverJob]:
        jobs = []
        for _, page in self.iter_site_pages(site):
            jobs.extend(page)
        return jobs

    @staticmethod
    def _parse_job(site: str, company_name: str, raw: dict[str, Any], verified_at: str) -> LeverJob:
        categories = raw.get("categories") if isinstance(raw.get("categories"), dict) else {}
        description = _description(raw)
        evidence = f"{_text(raw.get('text'))}\n{description}"
        return LeverJob(
            company_name=_text(raw.get("company")) if isinstance(raw.get("company"), str) else company_name,
            site_token=site,
            posting_id=_identifier(raw.get("id")),
            title=_text(raw.get("text")),
            location=_locations(categories),
            country=_field(categories, "country"),
            employment_type=_field(categories, "commitment"),
            commitment=_field(categories, "commitment"),
            team=_field(categories, "team"),
            department=_field(categories, "department"),
            description=description,
            hosted_url=_text(raw.get("hostedUrl")),
            apply_url=_text(raw.get("applyUrl")),
            work_authorization=_evidence(evidence, (r"sponsor", r"work authorization", r"visa", r"employment eligibility", r"legally authorized")),
            degree_requirements=_evidence(evidence, (r"\bdegree\b", r"bachelor", r"master", r"ph\.d", r"doctoral", r"graduate")),
            graduation_window=_evidence(evidence, (r"graduat", r"class of", r"enroll")),
            internship_term=_term(evidence),
            verified_at=verified_at,
        )
