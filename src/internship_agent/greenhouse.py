"""Read-only Greenhouse Job Board API access and safe job parsing."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import socket
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from .config import ConfigurationError
from .registry_metadata import read_provenance, provenance_fields

GREENHOUSE_API_HOST = "boards-api.greenhouse.io"
GREENHOUSE_API_ROOT = f"https://{GREENHOUSE_API_HOST}/v1/boards"
UNKNOWN = "UNKNOWN"


class GreenhouseError(RuntimeError):
    """Base error for read-only Greenhouse access and parsing."""


class GreenhouseHTTPError(GreenhouseError):
    """The official API returned an unsuccessful HTTP response."""

    def __init__(self, status: int, url: str, message: str = "") -> None:
        detail = f": {message}" if message else ""
        super().__init__(f"Greenhouse HTTP {status} for {url}{detail}")
        self.status = status
        self.url = url


class GreenhouseDataError(GreenhouseError):
    """The API response was malformed or missing required collection data."""


@dataclass(frozen=True, slots=True)
class GreenhouseBoard:
    company_name: str
    board_token: str
    source_url: str
    verified_at: str
    active: bool
    ats_platform: str = ""
    official_careers_url: str = ""
    evidence_url: str = ""
    verification_status: str = ""


@dataclass(frozen=True, slots=True)
class GreenhouseJob:
    company_name: str
    board_token: str
    source_job_id: str
    title: str
    location: str
    application_url: str
    description: str
    published_at: str
    updated_at: str
    internship_term: str
    degree_requirements: str
    graduation_window: str
    work_authorization: str
    source_url: str
    verified_at: str
    relevance_category: str = UNKNOWN
    relevance_reason: str = UNKNOWN


class _SafeHTMLText(HTMLParser):
    _SKIPPED = {"script", "style", "noscript", "template"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        if tag in self._SKIPPED:
            self._skip_depth += 1
        elif self._skip_depth == 0 and tag in {"br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag in self._SKIPPED and self._skip_depth:
            self._skip_depth -= 1
        elif self._skip_depth == 0 and tag in {"p", "div", "li", "tr", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self.parts.append(data)


def html_to_safe_text(value: Any) -> str:
    if not isinstance(value, str):
        return UNKNOWN
    parser = _SafeHTMLText()
    try:
        parser.feed(value)
        parser.close()
    except Exception as error:
        raise GreenhouseDataError(f"Could not decode job description HTML: {error}") from error
    text = re.sub(r"[ \t\r\f\v]+", " ", "".join(parser.parts))
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n[ ]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() or UNKNOWN


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else UNKNOWN


def _identifier(value: Any) -> str:
    if isinstance(value, (int, str)) and str(value).strip():
        return str(value).strip()
    return UNKNOWN


def _location(value: Any) -> str:
    if isinstance(value, dict):
        return _text(value.get("name"))
    return _text(value)


def _evidence(text: str, patterns: Iterable[str]) -> str:
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
    selected = [sentence.strip() for sentence in sentences if any(re.search(pattern, sentence, re.I) for pattern in patterns)]
    return " ".join(selected[:3]) or UNKNOWN


def _internship_term(text: str) -> str:
    match = re.search(r"\bSummer\s+2027\b", text, re.I)
    return "Summer 2027" if match else UNKNOWN


def _validate_board_token(board_token: str) -> str:
    board_token = _text(board_token)
    if board_token == UNKNOWN or not re.fullmatch(r"[A-Za-z0-9_-]+", board_token):
        raise ValueError(f"Invalid Greenhouse board token: {board_token!r}")
    return board_token


def board_api_url(board_token: str) -> str:
    token = _validate_board_token(board_token)
    return f"{GREENHOUSE_API_ROOT}/{quote(token, safe='')}/jobs?content=true"


def load_board_registry(path: str | Path) -> list[GreenhouseBoard]:
    try:
        import yaml
    except ModuleNotFoundError as error:
        raise ConfigurationError("PyYAML is required to load the Greenhouse registry") from error
    source = Path(path)
    try:
        data = yaml.safe_load(source.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ConfigurationError(f"Greenhouse registry not found: {source}") from error
    except yaml.YAMLError as error:
        raise ConfigurationError(f"Invalid Greenhouse registry YAML: {error}") from error
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("boards"), list):
        raise ConfigurationError("Greenhouse registry must contain version 1 and a boards list")
    boards: list[GreenhouseBoard] = []
    seen: set[str] = set()
    for index, raw in enumerate(data["boards"]):
        if not isinstance(raw, dict):
            raise ConfigurationError(f"Greenhouse registry board {index} must be a mapping")
        expected = {"company_name", "board_token", "source_url", "verified_at", "active"}
        provenance = read_provenance(raw, expected)
        token = _validate_board_token(raw["board_token"])
        if token in seen:
            raise ConfigurationError(f"Duplicate Greenhouse board token: {token}")
        seen.add(token)
        source_url = _text(raw["source_url"])
        parsed = urlsplit(source_url)
        if parsed.scheme != "https" or parsed.hostname not in {"boards.greenhouse.io", "job-boards.greenhouse.io"}:
            raise ConfigurationError(f"Invalid Greenhouse source URL for {token}")
        if not isinstance(raw["active"], bool):
            raise ConfigurationError(f"Greenhouse active flag must be boolean for {token}")
        boards.append(GreenhouseBoard(
            company_name=_text(raw["company_name"]), board_token=token,
            source_url=source_url, verified_at=_text(raw["verified_at"]),
            active=raw["active"], **provenance,
        ))
    return boards


def save_board_registry(path: str | Path, boards: Iterable[GreenhouseBoard]) -> None:
    try:
        import yaml
    except ModuleNotFoundError as error:
        raise ConfigurationError("PyYAML is required to save the Greenhouse registry") from error
    payload = {
        "version": 1,
        "boards": [
            {
                "company_name": board.company_name,
                "board_token": board.board_token,
                "source_url": board.source_url,
                "verified_at": board.verified_at,
                "active": board.active,
                **provenance_fields(board),
            }
            for board in boards
        ],
    }
    Path(path).write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8", newline="\n")


class GreenhouseClient:
    """Bounded, read-only client for the public Greenhouse Job Board API."""

    def __init__(
        self,
        timeout: float = 15.0,
        max_retries: int = 2,
        min_interval: float = 0.25,
        opener: Callable[..., Any] | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        if timeout <= 0 or max_retries < 0 or min_interval < 0:
            raise ValueError("Invalid Greenhouse client limits")
        self.timeout = timeout
        self.max_retries = max_retries
        self.min_interval = min_interval
        self._opener = opener or urlopen
        self._sleeper = sleeper or time.sleep
        self._last_request = 0.0

    def _wait_for_rate_limit(self) -> None:
        delay = self.min_interval - (time.monotonic() - self._last_request)
        if delay > 0:
            self._sleeper(delay)
        self._last_request = time.monotonic()

    @staticmethod
    def _assert_official_url(url: str) -> None:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname != GREENHOUSE_API_HOST:
            raise ValueError("Greenhouse requests must use the official HTTPS API host")

    def fetch_board_payload(self, board_token: str) -> dict[str, Any]:
        url = board_api_url(board_token)
        self._assert_official_url(url)
        request = Request(
            url,
            method="GET",
            headers={"Accept": "application/json", "User-Agent": "InternshipAgent/2027"},
        )
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            if attempt:
                self._sleeper(min(2.0, 0.5 * (2 ** (attempt - 1))))
            self._wait_for_rate_limit()
            try:
                with self._opener(request, timeout=self.timeout) as response:
                    status = getattr(response, "status", None)
                    if status is None:
                        status = response.getcode()
                    body = response.read()
                if status != 200:
                    raise GreenhouseHTTPError(status, url)
                try:
                    data = json.loads(body.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise GreenhouseDataError(f"Malformed JSON from {url}") from error
                if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
                    raise GreenhouseDataError(f"Greenhouse response missing jobs list: {url}")
                if any(not isinstance(job, dict) for job in data["jobs"]):
                    raise GreenhouseDataError(f"Greenhouse list contains malformed postings: {url}")
                return data
            except HTTPError as error:
                if error.code not in {429, 500, 502, 503, 504} or attempt >= self.max_retries:
                    raise GreenhouseHTTPError(error.code, url, error.reason) from error
                last_error = error
            except (TimeoutError, socket.timeout, URLError) as error:
                if isinstance(error, URLError) and not isinstance(error.reason, (TimeoutError, socket.timeout)):
                    if "timed out" not in str(error.reason).casefold():
                        raise GreenhouseError(f"Greenhouse request failed for {url}: {error}") from error
                if attempt >= self.max_retries:
                    raise GreenhouseError(f"Greenhouse request timed out for {url}") from error
                last_error = error
            except GreenhouseHTTPError as error:
                if error.status not in {429, 500, 502, 503, 504} or attempt >= self.max_retries:
                    raise
                last_error = error
        raise GreenhouseError(f"Greenhouse request failed after retries: {last_error}")

    def fetch_jobs(self, board: GreenhouseBoard) -> list[GreenhouseJob]:
        payload = self.fetch_board_payload(board.board_token)
        verified_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        source_url = board_api_url(board.board_token)
        jobs: list[GreenhouseJob] = []
        for raw in payload["jobs"]:
            if not isinstance(raw, dict):
                continue
            description = html_to_safe_text(raw.get("content"))
            evidence_text = f"{_text(raw.get('title'))}\n{description}"
            jobs.append(GreenhouseJob(
                company_name=_text((raw.get("company") or {}).get("name")) if isinstance(raw.get("company"), dict) else board.company_name,
                board_token=board.board_token,
                source_job_id=_identifier(raw.get("id")),
                title=_text(raw.get("title")),
                location=_location(raw.get("location")),
                application_url=_text(raw.get("absolute_url")),
                description=description,
                published_at=_text(raw.get("created_at")),
                updated_at=_text(raw.get("updated_at")),
                internship_term=_internship_term(evidence_text),
                degree_requirements=_evidence(evidence_text, (r"\bdegree\b", r"bachelor", r"master", r"ph\.d", r"doctoral", r"graduate")),
                graduation_window=_evidence(evidence_text, (r"graduat", r"class of", r"enroll")),
                work_authorization=_evidence(evidence_text, (r"sponsor", r"work authorization", r"visa", r"employment eligibility", r"legally authorized")),
                source_url=source_url,
                verified_at=verified_at,
            ))
        return jobs
