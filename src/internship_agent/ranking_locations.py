"""Conservative location evidence for ranking; no assumption about remote state eligibility."""

from dataclasses import dataclass
import re

STATES = dict(pair.split(":") for pair in (
    "AL:Alabama|AK:Alaska|AZ:Arizona|AR:Arkansas|CA:California|CO:Colorado|CT:Connecticut|"
    "DE:Delaware|FL:Florida|GA:Georgia|HI:Hawaii|ID:Idaho|IL:Illinois|IN:Indiana|IA:Iowa|"
    "KS:Kansas|KY:Kentucky|LA:Louisiana|ME:Maine|MD:Maryland|MA:Massachusetts|MI:Michigan|"
    "MN:Minnesota|MS:Mississippi|MO:Missouri|MT:Montana|NE:Nebraska|NV:Nevada|NH:New Hampshire|"
    "NJ:New Jersey|NM:New Mexico|NY:New York|NC:North Carolina|ND:North Dakota|OH:Ohio|"
    "OK:Oklahoma|OR:Oregon|PA:Pennsylvania|RI:Rhode Island|SC:South Carolina|SD:South Dakota|"
    "TN:Tennessee|TX:Texas|UT:Utah|VT:Vermont|VA:Virginia|WA:Washington|WV:West Virginia|"
    "WI:Wisconsin|WY:Wyoming"
).split("|"))
CITIES = {"san francisco": "California", "sunnyvale": "California", "san diego": "California",
          "los angeles": "California", "palo alto": "California", "redwood city": "California",
          "seattle": "Washington", "bellevue": "Washington", "new york city": "New York",
          "nyc": "New York", "houston": "Other US", "boston": "Other US", "austin": "Other US",
          "dallas": "Other US", "pensacola": "Other US"}
FOREIGN = r"\b(?:canada|canadian|toronto|vancouver|montreal|united kingdom|uk|london|germany|berlin|france|paris|singapore|china|beijing|shanghai|india|bengaluru|australia|sydney|japan|tokyo|mexico)\b"


@dataclass(frozen=True)
class LocationEvidence:
    group: str
    fraction: float
    evidence: str
    flags: tuple[str, ...]


def assess_location(location, preferences):
    order = preferences["locations"]["preference_order"]
    groups, flags, foreign = set(), [], False
    for part in re.split(r";|\||\s+or\s+|\s*/\s*", location):
        part = part.strip()
        if not part:
            continue
        if re.search(FOREIGN, part, re.I):
            foreign = True
            # A country marked foreign must not be interpreted as California from CA.
            if not re.search(r"\b(?:United States|USA|US)\b", part, re.I):
                continue
        is_remote = bool(re.search(r"\bremote\b", part, re.I))
        is_hybrid = bool(re.search(r"\bhybrid\b", part, re.I))
        if is_remote:
            flags.append("Remote state eligibility/restrictions need verification; remote does not imply all US states")
            if not preferences["locations"]["include_remote"]:
                continue
        if is_hybrid and not preferences["locations"]["include_hybrid"]:
            continue
        if re.search(r"Washington,?\s*(?:D\.?C\.?|District of Columbia)|\bDC\b", part, re.I):
            groups.add("Other US")
            continue
        state_hits = []
        for code, name in STATES.items():
            if re.search(rf"\b{re.escape(name)}\b", part, re.I) or re.search(rf"(?:,\s*|^){code}(?:\b|$)", part):
                if name == "Washington" and part.casefold() == "washington":
                    flags.append("Washington alone is ambiguous between state and DC")
                    continue
                state_hits.append(name)
        for state in state_hits:
            groups.add(state if state in ("California", "Washington", "New York") else "Other US")
        if not state_hits:
            for city, group in CITIES.items():
                if re.search(rf"\b{re.escape(city)}\b", part, re.I):
                    groups.add(group)
        if re.search(r"\b(?:United States|USA|US|U\.S\.)\b", part, re.I):
            groups.add("Other US")
        if is_remote and not state_hits:
            # US-only remote has geographic evidence for Other US, never CA/WA/NY.
            if not re.search(r"\b(?:United States|USA|US|U\.S\.)\b", part, re.I) and not groups:
                flags.append("Remote country/location is UNKNOWN")
    if groups:
        preferred = groups & set(order)
        if not preferred:
            return LocationEvidence("OUTSIDE_PREFERENCES", 0.0,
                f"Stored US location is outside configured preference groups: {location}",
                tuple(dict.fromkeys([*flags, "US location is outside configured preference groups"])))
        group = min(preferred, key=order.index)
        fraction = (1.0, .8, .6, .4)[order.index(group)]
        return LocationEvidence(group, fraction, f"Stored location identifies {group}: {location}", tuple(dict.fromkeys(flags)))
    group = "NON_US" if foreign else "UNKNOWN"
    flags.append("Only a non-US location is confirmed" if foreign else "US location evidence is missing/ambiguous")
    return LocationEvidence(group, 0.0, f"Location is {group}; no verified US option", tuple(dict.fromkeys(flags)))
