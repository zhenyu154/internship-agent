"""Deterministic identities for conservative duplicate detection."""

import hashlib
import json
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import Job

_TRACKING_PARAMETERS = frozenset({"gclid", "fbclid", "msclkid"})


def normalize_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def canonicalize_url(value: str) -> str:
    parts = urlsplit(value.strip())
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise ValueError("url must be an absolute HTTP or HTTPS URL")
    if parts.username is not None or parts.password is not None:
        raise ValueError("url must not include credentials")
    scheme = parts.scheme.lower()
    host = parts.hostname.lower()
    if any(character.isspace() for character in host):
        raise ValueError("url hostname must not contain whitespace")
    if ":" in host:
        host = f"[{host}]"
    port = parts.port
    if port is not None and (scheme, port) not in {("http", 80), ("https", 443)}:
        host = f"{host}:{port}"
    parameters = [
        (name, content)
        for name, content in parse_qsl(parts.query, keep_blank_values=True)
        if not name.casefold().startswith("utm_")
        and name.casefold() not in _TRACKING_PARAMETERS
    ]
    # Stable sorting by key preserves the order of values for repeated keys.
    parameters.sort(key=lambda pair: pair[0])
    return urlunsplit((scheme, host, parts.path or "/", urlencode(parameters), ""))


def _identity(kind: str, values: list[str]) -> str:
    payload = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
    return f"{kind}:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def job_identity_keys(job: Job) -> tuple[str, ...]:
    keys = []
    if job.source_job_id:
        keys.append(_identity("source", [normalize_text(job.source), job.source_job_id]))
    if job.url:
        keys.append(_identity("url", [canonicalize_url(job.url)]))
    if not keys:
        keys.append(_identity("fallback", [
            normalize_text(job.title),
            normalize_text(job.company),
            normalize_text(job.location),
        ]))
    return tuple(keys)
