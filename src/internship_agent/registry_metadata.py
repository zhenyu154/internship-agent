"""Backward-compatible provenance fields for the three existing ATS registries."""

from .config import ConfigurationError

OPTIONAL_FIELDS = frozenset({"ats_platform", "official_careers_url", "evidence_url", "verification_status"})


def read_provenance(raw, required):
    if not required.issubset(raw) or set(raw) - required - OPTIONAL_FIELDS:
        raise ConfigurationError("Registry entry has missing or unknown fields")
    result = {key: raw[key] for key in OPTIONAL_FIELDS if key in raw}
    if any(not isinstance(value, str) or not value for value in result.values()):
        raise ConfigurationError("Registry provenance fields must be non-empty strings")
    if result.get("verification_status", "VERIFIED_SUPPORTED") != "VERIFIED_SUPPORTED":
        raise ConfigurationError("Registered provenance must be VERIFIED_SUPPORTED")
    return result


def provenance_fields(record):
    return {key: getattr(record, key) for key in sorted(OPTIONAL_FIELDS) if getattr(record, key, "")}
