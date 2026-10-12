"""Read-only Ashby public job-board API access and safe normalization."""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
import socket
import time
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from urllib.request import Request, urlopen

from .config import ConfigurationError
from .registry_metadata import read_provenance, provenance_fields
from .greenhouse import GreenhouseDataError, GreenhouseError, _evidence, html_to_safe_text

ASHBY_API_HOST = "api.ashbyhq.com"
ASHBY_API_ROOT = f"https://{ASHBY_API_HOST}/posting-api/job-board"
UNKNOWN = "UNKNOWN"


class AshbyError(GreenhouseError):
    pass


class AshbyHTTPError(AshbyError):
    def __init__(self, status: int, url: str, message: str = "") -> None:
        super().__init__(f"Ashby HTTP {status} for {url}: {message}".rstrip(": "))
        self.status = status
        self.url = url


class AshbyDataError(AshbyError):
    pass


@dataclass(frozen=True, slots=True)
class AshbyBoard:
    company_name: str
    board_name: str
    source_url: str
    verified_at: str
    active: bool
    ats_platform: str = ""
    official_careers_url: str = ""
    evidence_url: str = ""
    verification_status: str = ""


@dataclass(frozen=True, slots=True)
class AshbyJob:
    company_name: str
    board_name: str
    posting_id: str
    title: str
    department: str
    team: str
    location: str
    secondary_locations: str
    work_mode: str
    employment_type: str
    description: str
    job_url: str
    apply_url: str
    published_at: str
    compensation: str
    internship_term: str
    degree_requirements: str
    graduation_window: str
    work_authorization: str
    is_listed: bool | None
    verified_at: str
    relevance_category: str = UNKNOWN
    relevance_reason: str = UNKNOWN


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else UNKNOWN


def _identifier(value: Any) -> str:
    return str(value).strip() if isinstance(value, (str, int)) and str(value).strip() else UNKNOWN


def _timestamp(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return UNKNOWN


def _canonical_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return UNKNOWN
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
             if not k.casefold().startswith("utm_") and k.casefold() not in {"gh_src", "source"}]
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), ""))


def _list_text(value: Any) -> str:
    if isinstance(value, list):
        return "; ".join(_text(item) for item in value if _text(item) != UNKNOWN) or UNKNOWN
    return _text(value)


def _compensation(value: Any) -> str:
    if value in (None, "", {}):
        return UNKNOWN
    if isinstance(value, str):
        return value.strip() or UNKNOWN
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return UNKNOWN


def load_ashby_registry(path: str | Path) -> list[AshbyBoard]:
    try:
        import yaml
    except ModuleNotFoundError as error:
        raise ConfigurationError("PyYAML is required to load the Ashby registry") from error
    source = Path(path)
    try:
        data = yaml.safe_load(source.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ConfigurationError(f"Ashby registry not found: {source}") from error
    except yaml.YAMLError as error:
        raise ConfigurationError(f"Invalid Ashby registry YAML: {error}") from error
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("boards"), list):
        raise ConfigurationError("Ashby registry must contain version 1 and a boards list")
    boards = []
    seen = set()
    for index, raw in enumerate(data["boards"]):
        expected = {"company_name", "board_name", "source_url", "verified_at", "active"}
        if not isinstance(raw, dict):
            raise ConfigurationError(f"Ashby board {index} must be a mapping")
        provenance = read_provenance(raw, expected)
        name = _text(raw["board_name"])
        if name == UNKNOWN or not re.fullmatch(r"[A-Za-z0-9._-]+", name):
            raise ConfigurationError(f"Invalid Ashby board name: {name!r}")
        if name in seen:
            raise ConfigurationError(f"Duplicate Ashby board name: {name}")
        seen.add(name)
        parsed = urlsplit(_text(raw["source_url"]))
        if parsed.scheme != "https" or parsed.hostname != "jobs.ashbyhq.com":
            raise ConfigurationError(f"Invalid Ashby source URL for {name}")
        if not isinstance(raw["active"], bool):
            raise ConfigurationError(f"Ashby active flag must be boolean for {name}")
        boards.append(AshbyBoard(_text(raw["company_name"]), name, _text(raw["source_url"]), _text(raw["verified_at"]), raw["active"], **provenance))
    return boards


def save_ashby_registry(path: str | Path, boards: list[AshbyBoard]) -> None:
    import yaml
    payload = {"version": 1, "boards": [
        {"company_name": board.company_name, "board_name": board.board_name,
         "source_url": board.source_url, "verified_at": board.verified_at, "active": board.active, **provenance_fields(board)}
        for board in boards
    ]}
    Path(path).write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8", newline="\n")


class AshbyClient:
    def __init__(self, timeout: float = 15.0, max_retries: int = 2,
                 min_interval: float = 0.25, opener: Callable[..., Any] | None = None,
                 sleeper: Callable[[float], None] | None = None) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self.min_interval = min_interval
        self._opener = opener or urlopen
        self._sleeper = sleeper or time.sleep
        self._last_request = 0.0

    def fetch_board(self, board_name: str) -> list[AshbyJob]:
        if not isinstance(board_name, str) or not re.fullmatch(r"[A-Za-z0-9._-]+", board_name):
            raise ValueError(f"Invalid Ashby board name: {board_name!r}")
        url = f"{ASHBY_API_ROOT}/{board_name}?includeCompensation=true"
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
                    raise AshbyHTTPError(status, url)
                data = json.loads(body.decode("utf-8"))
                if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
                    raise AshbyDataError(f"Ashby response missing jobs list: {url}")
                if any(not isinstance(job,dict) for job in data["jobs"]):
                    raise AshbyDataError(f"Ashby list contains malformed postings: {url}")
                verified_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
                return [self._parse_job(board_name, raw, verified_at) for raw in data["jobs"] if isinstance(raw, dict)]
            except HTTPError as error:
                if error.code not in {429, 500, 502, 503, 504} or attempt >= self.max_retries:
                    raise AshbyHTTPError(error.code, url, error.reason) from error
            except (TimeoutError, socket.timeout, URLError) as error:
                if attempt >= self.max_retries:
                    raise AshbyError(f"Ashby request failed or timed out: {url}") from error
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise AshbyDataError(f"Malformed Ashby JSON: {url}") from error
            if attempt < self.max_retries:
                self._sleeper(min(2.0, 0.5 * (2 ** attempt)))
        raise AshbyError(f"Ashby request failed: {url}")

    @staticmethod
    def _parse_job(board_name: str, raw: dict[str, Any], verified_at: str) -> AshbyJob:
        description = _text(raw.get("descriptionPlain"))
        if description == UNKNOWN:
            description = html_to_safe_text(raw.get("descriptionHtml"))
        location = _text(raw.get("location"))
        secondary = _list_text(raw.get("secondaryLocations") or raw.get("additionalLocations"))
        text = f"{_text(raw.get('title'))}\n{description}"
        return AshbyJob(
            company_name=_text(raw.get("companyName")),
            board_name=board_name,
            posting_id=_identifier(raw.get("id") or raw.get("jobId")),
            title=_text(raw.get("title")),
            department=_text(raw.get("department")),
            team=_text(raw.get("team")),
            location=location,
            secondary_locations=secondary,
            work_mode=_text(raw.get("workplaceType") or raw.get("workplace")),
            employment_type=_text(raw.get("employmentType")),
            description=description,
            job_url=_canonical_url(_text(raw.get("jobUrl") or raw.get("jobURL"))),
            apply_url=_canonical_url(_text(raw.get("applyUrl") or raw.get("applyURL"))),
            published_at=_timestamp(raw.get("publishedAt")),
            compensation=_compensation(raw.get("compensation")),
            internship_term="Summer 2027" if re.search(r"\bSummer\s+2027\b", text, re.I) else UNKNOWN,
            degree_requirements=_evidence(text, (r"\bdegree\b", r"bachelor", r"master", r"ph\.d", r"doctoral", r"graduate")),
            graduation_window=_evidence(text, (r"graduat", r"class of", r"enroll")),
            work_authorization=_evidence(text, (r"sponsor", r"work authorization", r"visa", r"employment eligibility", r"legally authorized")),
            is_listed=raw.get("isListed") if isinstance(raw.get("isListed"), bool) else None,
            verified_at=verified_at,
        )
