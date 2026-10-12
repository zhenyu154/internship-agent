"""Explainable Greenhouse relevance filtering and saved-job reclassification."""

from dataclasses import dataclass, replace
import re
from typing import Any

from .greenhouse import GreenhouseJob, UNKNOWN

MAIN_SHORTLIST = "MAIN_SHORTLIST"
NEEDS_REVIEW = "NEEDS_REVIEW"
EXCLUDED = "EXCLUDED"


@dataclass(frozen=True, slots=True)
class RelevanceResult:
    category: str
    reason: str


_TITLE_ROLE_TERMS = (
    "machine learning", "ml engineer", "robot", "robotics", "software engineer",
    "software developer", "autonomy", "simulation", "computer vision",
    "multimodal", "research engineer", "ai engineer", "data scientist",
    "perception", "embedded software", "research intern",
)
_TECHNICAL_DUTY_TERMS = (
    "machine learning", "deep learning", "model", "algorithm", "computer vision",
    "perception", "autonomy", "simulation", "sensor fusion", "state estimation",
    "robot operating system", "software framework", "data pipeline", "python",
    "pytorch", "tensorflow", "c++", "java", "code", "coding", "develop",
    "implement", "train", "inference", "neural", "robotics software",
)
_HARD_BUSINESS_TITLE_TERMS = (
    "manufacturing", "supply chain", "operations", "strategy", "procurement",
    "inventory", "finance", "marketing", "sales", "human resources", "mba",
)
_HARD_BUSINESS_DUTY_TERMS = (
    "procurement", "inventory management", "supply chain", "workstream",
    "weekly readout", "senior leadership", "manufacturing during vehicle builds",
    "facility footprint", "finance", "issue tracking", "production floor",
)
_PRODUCT_BUSINESS_DUTY_TERMS = (
    "product roadmap", "product strategy", "customer research", "user research",
    "market research", "go-to-market", "stakeholder", "requirements gathering",
    "prioritize features", "product requirements", "business case",
    "product problem", "recommendation to leadership", "requirements engineers",
    "commercial teams", "what we build next",
)
_HARDWARE_TITLE_TERMS = ("electrical engineering", "mechanical engineering", "hardware", "embedded", "firmware")
_INTERNSHIP_TERMS = ("intern", "internship", "co-op", "coop")
_PHD_ONLY_PATTERNS = (
    r"\bph\.?d\.?\s+(?:only|required|candidate|required candidates)",
    r"\bph\.?d\.?\s+degree",
    r"\bph\.?d\.?\s+internship",
    r"doctoral degree\s+(?:only|required)",
    r"\(\s*ph\.?d\.?\s*\)",
)
_LOCATION_TERMS = {
    "California": ("california", "ca", "san francisco", "los angeles", "san diego", "palo alto"),
    "Washington": ("washington", "wa", "seattle", "bellevue"),
    "New York": ("new york", "ny", "new york city"),
    "Other US": ("united states", "usa", "remote", "hybrid"),
}


def _matches(text: str, terms: tuple[str, ...]) -> list[str]:
    return [
        term for term in terms
        if re.search(rf"(?<![a-z]){re.escape(term)}(?![a-z])", text)
    ]


def _location_preference(location: str, preference_order: list[str]) -> str:
    lowered = location.casefold()
    for preference in preference_order:
        if any(term in lowered for term in _LOCATION_TERMS.get(preference, ())):
            return preference
    return UNKNOWN



def _role_context_text(description: str) -> str:
    """Prefer role sections over generic company introductions."""
    headings = re.search(
        r"(?im)^\s*(?:about the role[^\n]*|what you['’]ll do|your role:|"
        r"responsibilities:?|what you['’]ll work on:)\s*$",
        description,
    )
    return description[headings.end():] if headings else description


def _hands_on_product_engineering(text: str) -> bool:
    return bool(re.search(
        r"\b(?:build|develop|implement|train|fine[- ]tune|design)\w*\b"
        r"[^.\n]{0,100}\b(?:ml models?|machine learning models?|"
        r"neural networks?|manipulation algorithms?|robot control software|"
        r"inference pipelines?|simulation environments?)\b",
        text, re.I,
    ))



def source_internship_terms(title: str, description: str) -> set[str]:
    """Read seasonal cohort evidence; graduation dates are not internship dates."""
    pattern = r"\b(?:Summer|Fall|Winter|Spring)\s+20\d{2}\b"
    terms = {term.title() for term in re.findall(pattern, title, re.I)}
    # Titles can separate season and year with a program/start-month label.
    for season, year in re.findall(r"\b(Summer|Fall|Winter|Spring)\b[^.\n]{0,50}?\b(20\d{2})\b", title, re.I):
        terms.add(f"{season.title()} {year}")
    for line in re.split(r"\n+|(?<=[.!?])\s+", description):
        contextual = re.search(r"intern|cohort|program|session|program dates", line, re.I)
        labeled = re.search(r"^\s*(?:[-*]\s*)?(?:Summer|Fall|Winter|Spring)\s+20\d{2}\s*:", line, re.I)
        if (contextual or labeled) and not re.search(r"graduat", line, re.I):
            terms.update(term.title() for term in re.findall(pattern, line, re.I))
    return terms


def explicit_phd_only(title: str, description: str) -> bool:
    alternatives = r"bachelor|master|\bBS\b|\bMS\b|\bBSc\b|\bMSc\b"
    for line in [title, *description.splitlines()]:
        if re.search(alternatives, line, re.I) or re.search(r"preferred|nice to have", line, re.I):
            continue
        if any(re.search(pattern, line, re.I) for pattern in _PHD_ONLY_PATTERNS):
            return True
        if re.search(r"(?:pursuing|enrolled|currently|must)[^.\n]*\bph\.?d", line, re.I):
            return True
    return False


def classify_greenhouse_job(job: GreenhouseJob, preferences: dict[str, Any]) -> RelevanceResult:
    title_text = job.title.casefold()
    full_text = f"{job.title}\n{job.description}".casefold()
    title_role_hits = _matches(title_text, _TITLE_ROLE_TERMS)
    technical_hits = _matches(full_text, _TECHNICAL_DUTY_TERMS)
    business_title_hits = _matches(title_text, _HARD_BUSINESS_TITLE_TERMS)
    business_duty_hits = _matches(full_text, _HARD_BUSINESS_DUTY_TERMS)
    role_context = _role_context_text(job.description).casefold()
    product_duty_hits = _matches(role_context, _PRODUCT_BUSINESS_DUTY_TERMS)
    internship_hits = _matches(title_text, _INTERNSHIP_TERMS)
    location = _location_preference(job.location, preferences["locations"]["preference_order"])
    phd_only = explicit_phd_only(job.title, job.description)

    if phd_only and preferences["eligibility"]["phd_only"] == "EXCLUDE":
        return RelevanceResult(EXCLUDED, "Explicit PhD-only language was found")
    if not internship_hits:
        return RelevanceResult(EXCLUDED, "Job title has no internship, intern, co-op, or coop signal")
    terms = source_internship_terms(job.title, job.description)
    if terms and "Summer 2027" not in terms and preferences["eligibility"]["explicitly_wrong_internship_term"] == "EXCLUDE":
        return RelevanceResult(EXCLUDED, "Source explicitly describes another internship cohort: " + ", ".join(sorted(terms)))
    if business_title_hits and not title_role_hits:
        return RelevanceResult(
            EXCLUDED,
            f"Title is a business/operations function ({', '.join(business_title_hits)}); "
            "technical keywords occur in organizational context rather than the target role",
        )
    if business_duty_hits and not title_role_hits:
        return RelevanceResult(
            EXCLUDED,
            f"Responsibilities are business/operations focused ({', '.join(business_duty_hits[:3])})",
        )
    if (
        _matches(title_text, ("product",)) and not title_role_hits
        and product_duty_hits and not _hands_on_product_engineering(role_context)
    ):
        return RelevanceResult(
            EXCLUDED,
            "Product/business responsibilities were found without a hands-on technical role function",
        )

    if _matches(title_text, ("product design", "ux design", "user experience")) and _matches(
        role_context, ("interaction design", "portfolio", "user research", "test with real users", "visual design")
    ) and not _hands_on_product_engineering(role_context):
        return RelevanceResult(EXCLUDED, "Product/UX design responsibilities and portfolio requirements; not ML/robotics engineering")
    if _matches(title_text, ("it engineer", "it support")) and not _hands_on_product_engineering(role_context):
        return RelevanceResult(NEEDS_REVIEW, "IT engineering role with generic software duties; specific ML/robotics responsibility requires review")

    hardware_title_hits = _matches(title_text, _HARDWARE_TITLE_TERMS)
    if hardware_title_hits and not title_role_hits:
        return RelevanceResult(
            NEEDS_REVIEW,
            f"Hardware-focused title ({', '.join(hardware_title_hits)}); review against robotics software/ML experience",
        )
    if not title_role_hits and not technical_hits:
        return RelevanceResult(EXCLUDED, "No target technical role or concrete technical duties were found")

    reasons = []
    if title_role_hits:
        reasons.append(f"technical role function: {', '.join(title_role_hits[:4])}")
    else:
        reasons.append(f"technical duties: {', '.join(technical_hits[:4])}")
    if job.internship_term == "Summer 2027" or "summer 2027" in full_text:
        reasons.append("Summer 2027 signal confirmed")
    else:
        reasons.append("internship term is UNKNOWN and needs review")
    if location != UNKNOWN:
        reasons.append(f"location fits configured group: {location}")
    else:
        reasons.append("location is UNKNOWN or outside configured preference labels")
    if job.degree_requirements == UNKNOWN:
        reasons.append("degree requirements are UNKNOWN")
    if job.work_authorization == UNKNOWN:
        reasons.append("work authorization is UNKNOWN")
    elif "does not support" in job.work_authorization.casefold() or "not eligible" in job.work_authorization.casefold():
        return RelevanceResult(NEEDS_REVIEW, "; ".join(reasons + ["source contains a work-authorization restriction requiring candidate review"]))

    if job.internship_term == "Summer 2027" and location != UNKNOWN:
        return RelevanceResult(MAIN_SHORTLIST, "; ".join(reasons))
    return RelevanceResult(NEEDS_REVIEW, "; ".join(reasons))


def preview_priority(job: Any, preferences: dict[str, Any] | None = None) -> tuple:
    """Technical fit first; eligibility category is deliberately not a sort key."""
    title = job.title.casefold()
    duties = _role_context_text(job.description).casefold()
    direct = (
        "robot learning", "learned manipulation", "manipulation policies",
        "embodied ai", "physical ai", "robotics ml", "robotics machine learning", "manipulation",
    )
    related = (
        "world model", "world modeling", "world models", "autonomy", "simulation",
        "sim to real", "perception", "state estimation", "slam", "applied ml",
        "machine learning", "computer vision", "neural rendering", "metric prototyping",
    )
    hardware = ("hardware", "electrical engineering", "sensor systems", "mechanical engineer", "mechanical engineering")
    infrastructure = ("infrastructure", "ml inference", "fleet platform")
    software = ("software", "platform", "evaluation", "validation", "safety")
    if _matches(title, hardware) and not _matches(title, ("software", "machine learning", "ml engineer")):
        tier = 4
    elif _matches(title, direct):
        tier = 1
    elif _matches(title, infrastructure):
        tier = 3
    elif _matches(title, ("machine learning", "ml engineer", "research")) and _matches(duties, direct):
        tier = 1
    elif _matches(title, related):
        tier = 2
    elif _matches(title, software):
        tier = 3
    elif _matches(duties, direct):
        tier = 1
    elif _matches(duties, related):
        tier = 2
    else:
        tier = 3
    # Respect configured location priorities within a technical-fit tier.
    order = (preferences or {}).get("locations", {}).get(
        "preference_order", ["California", "Washington", "New York", "Other US"]
    )
    location_group = _location_preference(job.location, order)
    location_index = order.index(location_group) if location_group in order else len(order)
    return tier, location_index, job.company_name.casefold(), title, getattr(job, "posting_id", "")


def reclassify_saved_greenhouse_jobs(database: Any, preferences: dict[str, Any]) -> dict[str, int]:
    """Reclassify stored Greenhouse metadata without deleting or replacing jobs."""

    counts = {MAIN_SHORTLIST: 0, NEEDS_REVIEW: 0, EXCLUDED: 0}
    for record in database.list_jobs():
        metadata = database.get_job_metadata(record.id)
        if metadata is None or not metadata.greenhouse_board_token:
            continue
        result = classify_greenhouse_job(GreenhouseJob(
            company_name=record.job.company,
            board_token=metadata.greenhouse_board_token,
            source_job_id=record.job.source_job_id.split(":", 1)[-1],
            title=record.job.title,
            location=record.job.location or UNKNOWN,
            application_url=record.job.url or UNKNOWN,
            description=record.job.description or UNKNOWN,
            published_at=metadata.published_at,
            updated_at=metadata.updated_at,
            internship_term=metadata.internship_term,
            degree_requirements=metadata.degree_requirements,
            graduation_window=metadata.graduation_window,
            work_authorization=metadata.work_authorization,
            source_url=metadata.source_url,
            verified_at=metadata.verified_at,
        ), preferences)
        database.save_job_metadata(replace(
            metadata,
            relevance_category=result.category,
            relevance_reason=result.reason,
        ))
        counts[result.category] += 1
    return counts
