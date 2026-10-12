"""Safe, strict loading and validation for local search preferences."""

from collections.abc import Mapping, Sequence
from pathlib import Path
import re
from typing import Any


class ConfigurationError(ValueError):
    """Raised when search preferences are missing, unsafe, or malformed."""


_TOP_LEVEL = {
    "version", "target", "locations", "roles", "employers", "eligibility",
    "ranking", "discovery", "execution", "applications",
}
_TARGET = {"internship_term", "expected_graduation", "degree", "country"}
_LOCATIONS = {"preference_order", "include_remote", "include_hybrid", "relocation_willingness"}
_ROLES = {"primary", "secondary", "match_job_description_content", "allow_related_job_titles"}
_EMPLOYERS = {
    "company_sizes", "prioritize_documented_china_based_operations",
    "infer_sponsorship_from_company_background", "infer_employee_ethnicity",
}
_ELIGIBILITY = {
    "phd_only", "explicitly_ineligible_degree", "explicitly_incompatible_graduation",
    "explicitly_wrong_internship_term", "unspecified_degree_requirements",
    "unspecified_graduation_window", "unspecified_work_authorization",
    "explicit_no_sponsorship", "candidate_work_authorization",
}
_RANKING = {"weights", "check_eligibility_before_scoring", "require_explanation", "treat_scores_as_heuristics"}
_WEIGHTS = {"role_alignment", "technical_skills_match", "research_project_relevance", "location_preference"}
_DISCOVERY = {
    "max_candidates_per_run", "prefer_official_career_pages", "source_categories",
    "allow_aggregators_for_discovery", "verify_with_official_source", "deduplicate",
    "preserve_existing_records",
}
_EXECUTION = {
    "mode", "trigger", "scheduler_enabled", "auto_start", "persist_progress",
    "incremental_discovery", "resume_incomplete_runs", "reverify_existing_jobs_after_days",
    "save_verified_results_incrementally",
}
_APPLICATIONS = {"auto_submit", "human_review_required", "human_performs_final_submission"}

_DECISION_STATES = {"EXCLUDE", "INCLUDE", "NEEDS_REVIEW"}
_RELOCATION_STATES = {"UNKNOWN", "WILLING", "UNWILLING", "NEEDS_REVIEW"}
_COMPANY_SIZES = {"Large", "Mid-size", "Startup"}
_SOURCE_CATEGORIES = {"Company career websites", "Greenhouse", "Lever", "Ashby"}
_LOCATION_NAMES = {"California", "Washington", "New York", "Other US"}


def _yaml_load(text: str, source: Path) -> Any:
    try:
        import yaml
    except ModuleNotFoundError as error:
        raise ConfigurationError(
            "PyYAML is required to load configuration; install project dependencies first"
        ) from error

    class StrictSafeLoader(yaml.SafeLoader):
        pass

    def construct_mapping(loader: Any, node: Any, deep: bool = False) -> dict[str, Any]:
        mapping: dict[str, Any] = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise ConfigurationError(
                    f"Configuration mapping keys must be strings in {source} "
                    f"near line {key_node.start_mark.line + 1}"
                )
            if key in mapping:
                raise ConfigurationError(
                    f"Duplicate configuration key {key!r} in {source} "
                    f"near line {key_node.start_mark.line + 1}"
                )
            mapping[key] = loader.construct_object(value_node, deep=deep)
        return mapping

    StrictSafeLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_mapping
    )
    try:
        return yaml.load(text, Loader=StrictSafeLoader)
    except ConfigurationError:
        raise
    except yaml.YAMLError as error:
        raise ConfigurationError(f"Invalid YAML in {source}: {error}") from error


def _mapping(value: Any, name: str, allowed: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigurationError(f"{name} must be a YAML mapping")
    keys = set(value)
    unknown = sorted(keys - allowed)
    if unknown:
        raise ConfigurationError(f"Unknown configuration field(s) at {name}: {', '.join(unknown)}")
    missing = sorted(allowed - keys)
    if missing:
        raise ConfigurationError(f"Missing required configuration field(s) at {name}: {', '.join(missing)}")
    return value


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{name} must be a non-empty string")
    return value


def _boolean(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise ConfigurationError(f"{name} must be a boolean")
    return value


def _integer(value: Any, name: str, *, positive: bool = False) -> int:
    if type(value) is not int or (positive and value <= 0) or (not positive and value < 0):
        condition = "a positive integer" if positive else "a non-negative integer"
        raise ConfigurationError(f"{name} must be {condition}")
    return value


def _string_list(value: Any, name: str, allowed: set[str] | None = None) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        raise ConfigurationError(f"{name} must be a non-empty list of strings")
    result = []
    for index, item in enumerate(value):
        item_name = f"{name}[{index}]"
        item = _string(item, item_name)
        if allowed is not None and item not in allowed:
            raise ConfigurationError(f"{item_name} has unsupported value {item!r}")
        result.append(item)
    if len(result) != len(set(result)):
        raise ConfigurationError(f"{name} must not contain duplicate values")
    return result


def _decision(value: Any, name: str) -> str:
    value = _string(value, name)
    if value not in _DECISION_STATES:
        raise ConfigurationError(f"{name} must be one of {sorted(_DECISION_STATES)}")
    return value


def _validate(config: Any) -> dict[str, Any]:
    root = _mapping(config, "root", _TOP_LEVEL)
    if root["version"] != 1 or type(root["version"]) is not int:
        raise ConfigurationError("version must be the integer 1")

    target = _mapping(root["target"], "target", _TARGET)
    if target["internship_term"] != "Summer 2027":
        raise ConfigurationError("target.internship_term must be 'Summer 2027'")
    if not re.fullmatch(r"\d{4}-\d{2}", _string(target["expected_graduation"], "target.expected_graduation")):
        raise ConfigurationError("target.expected_graduation must use YYYY-MM format")
    if target["degree"] != "Master's":
        raise ConfigurationError("target.degree must be \"Master's\"")
    if target["country"] != "United States":
        raise ConfigurationError("target.country must be 'United States'")

    locations = _mapping(root["locations"], "locations", _LOCATIONS)
    _string_list(locations["preference_order"], "locations.preference_order", _LOCATION_NAMES)
    _boolean(locations["include_remote"], "locations.include_remote")
    _boolean(locations["include_hybrid"], "locations.include_hybrid")
    relocation = _string(locations["relocation_willingness"], "locations.relocation_willingness")
    if relocation not in _RELOCATION_STATES:
        raise ConfigurationError(f"locations.relocation_willingness has unsupported value {relocation!r}")

    roles = _mapping(root["roles"], "roles", _ROLES)
    _string_list(roles["primary"], "roles.primary")
    _string_list(roles["secondary"], "roles.secondary")
    _boolean(roles["match_job_description_content"], "roles.match_job_description_content")
    _boolean(roles["allow_related_job_titles"], "roles.allow_related_job_titles")

    employers = _mapping(root["employers"], "employers", _EMPLOYERS)
    _string_list(employers["company_sizes"], "employers.company_sizes", _COMPANY_SIZES)
    for field in _EMPLOYERS - {"company_sizes"}:
        _boolean(employers[field], f"employers.{field}")

    eligibility = _mapping(root["eligibility"], "eligibility", _ELIGIBILITY)
    for field in _ELIGIBILITY - {"candidate_work_authorization"}:
        _decision(eligibility[field], f"eligibility.{field}")
    if eligibility["explicit_no_sponsorship"] != "NEEDS_REVIEW":
        raise ConfigurationError("eligibility.explicit_no_sponsorship must remain NEEDS_REVIEW")
    if eligibility["unspecified_work_authorization"] != "NEEDS_REVIEW":
        raise ConfigurationError("eligibility.unspecified_work_authorization must remain NEEDS_REVIEW")
    if eligibility["candidate_work_authorization"] != "UNKNOWN":
        raise ConfigurationError("eligibility.candidate_work_authorization must remain UNKNOWN")

    ranking = _mapping(root["ranking"], "ranking", _RANKING)
    weights = _mapping(ranking["weights"], "ranking.weights", _WEIGHTS)
    for field in _WEIGHTS:
        _integer(weights[field], f"ranking.weights.{field}")
    if sum(weights.values()) != 100:
        raise ConfigurationError("ranking.weights must sum to exactly 100")
    for field in _RANKING - {"weights"}:
        _boolean(ranking[field], f"ranking.{field}")

    discovery = _mapping(root["discovery"], "discovery", _DISCOVERY)
    _integer(discovery["max_candidates_per_run"], "discovery.max_candidates_per_run", positive=True)
    _string_list(discovery["source_categories"], "discovery.source_categories", _SOURCE_CATEGORIES)
    for field in _DISCOVERY - {"max_candidates_per_run", "source_categories"}:
        _boolean(discovery[field], f"discovery.{field}")

    execution = _mapping(root["execution"], "execution", _EXECUTION)
    if execution["mode"] != "manual":
        raise ConfigurationError("execution.mode must be 'manual'")
    if execution["trigger"] != "explicit_user_request":
        raise ConfigurationError("execution.trigger must be 'explicit_user_request'")
    for field in _EXECUTION - {"mode", "trigger", "reverify_existing_jobs_after_days"}:
        _boolean(execution[field], f"execution.{field}")
    _integer(execution["reverify_existing_jobs_after_days"], "execution.reverify_existing_jobs_after_days", positive=True)
    if execution["scheduler_enabled"] or execution["auto_start"]:
        raise ConfigurationError("execution.scheduler_enabled and execution.auto_start must both be false")

    applications = _mapping(root["applications"], "applications", _APPLICATIONS)
    if applications["auto_submit"]:
        raise ConfigurationError("applications.auto_submit must be false")
    if not applications["human_review_required"] or not applications["human_performs_final_submission"]:
        raise ConfigurationError("applications.human_review_required and applications.human_performs_final_submission must both be true")
    for field in _APPLICATIONS:
        _boolean(applications[field], f"applications.{field}")

    return dict(root)


def load_config(path: str | Path) -> dict[str, Any]:
    """Load and strictly validate a local YAML configuration file."""

    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise ConfigurationError(f"Configuration file not found: {source}") from error
    except OSError as error:
        raise ConfigurationError(f"Could not read configuration file {source}: {error}") from error
    return _validate(_yaml_load(text, source))


def validate_config(data: Any) -> dict[str, Any]:
    """Validate an already-loaded preferences mapping without reading files."""
    return _validate(data)
