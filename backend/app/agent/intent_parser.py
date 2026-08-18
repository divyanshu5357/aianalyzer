import re
from typing import Any


METRIC_ALIASES = {
    "admission": [
        "admission",
        "admissions",
        "admitted",
        "enrolled",
        "enrollment",
    ],
    "leads": [
        "lead",
        "leads",
        "enquiry",
        "enquiries",
        "inquiry",
        "inquiries",
    ],
    "cucet": [
        "cucet",
        "cucet registration",
        "cucet registrations",
        "entrance test",
    ],
    "lead_cucet_rate": [
        "lead to cucet",
        "lead cucet rate",
        "lead-cucet",
        "lead conversion to cucet",
    ],
    "lead_admission_rate": [
        "lead to admission",
        "lead admission rate",
        "lead-admission",
        "lead conversion to admission",
        "admission rate",
        "conversion rate",
        "admission-rate",
        "conversion-rate",
    ],
    "cucet_admission_rate": [
        "cucet to admission",
        "cucet admission rate",
        "cucet-admission",
        "cucet conversion to admission",
    ],
}


DIMENSION_ALIASES = {
    "owner": [
        "owner",
        "owners",
        "who",
        "counselor",
        "counselors",
        "counsellor",
        "counsellors",
        "person",
    ],

    "program_name": [
        "program",
        "programs",
        "course",
        "courses",
    ],
    "campus_name": [
        "campus",
        "campuses",
    ],
    "state": [
        "state",
        "states",
    ],
    "cluster": [
        "cluster",
        "clusters",
    ],
    "lead_type": [
        "lead type",
        "lead types",
    ],
    "source": [
        "source",
        "sources",
    ],
    "main_source": [
        "main source",
        "source cluster",
    ],
}


FUNNEL_PATTERNS = [
    "funnel",
    "admission funnel",
    "admissions funnel",
    "lead funnel",
    "conversion funnel",
    "leads cucet admission",
    "leads to cucet to admission",
    "lead to cucet to admission",
]


COMPARISON_TRIGGERS = [
    r"\b(?:compare|comparison of)\s+(.*?)\s+(?:and|vs|versus|with|against)\s+(.*)",
    r"\b(.*?)\s+(?:vs|versus|compared to|compared with|against)\s+(.*)",
]

NOISE_WORDS = [
    "show", "compare", "comparison of", "as a bar chart", "as a pie chart", "as a line chart",
    "bar chart", "pie chart", "line chart", "chart", "graph", "table", "leads", "lead",
    "admissions", "admission", "cucet", "in 2026", "for 2026", "2026", "please", "me"
]


def normalize_text(text: str) -> str:
    """Normalize user question."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s%-]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def detect_response_format(question: str) -> tuple[str, str | None]:
    """
    Detect response_type ('text', 'table', 'chart') and chart_type ('bar', 'pie', 'line', None).
    """
    normalized = normalize_text(question)

    if (
        "bar chart" in normalized
        or "bar graph" in normalized
        or "bar plot" in normalized
        or "as a bar" in normalized
    ):
        return "chart", "bar"

    if (
        "pie chart" in normalized
        or "pie graph" in normalized
        or "pie plot" in normalized
        or "as a pie" in normalized
    ):
        return "chart", "pie"

    if (
        "line chart" in normalized
        or "line graph" in normalized
        or "trend chart" in normalized
        or "as a line" in normalized
    ):
        return "chart", "line"

    if (
        "chart" in normalized
        or "graph" in normalized
        or "plot" in normalized
        or "visualize" in normalized
    ):
        return "chart", "bar"

    if (
        "table" in normalized
        or "tabular" in normalized
        or "grid" in normalized
        or "by " in normalized
        or " vs " in normalized
        or " versus " in normalized
        or "compare" in normalized
        or "breakdown" in normalized
        or "list " in normalized
        or "top " in normalized
        or "dropped" in normalized
        or "decreased" in normalized
        or "increased" in normalized
        or "improved" in normalized
        or "decline" in normalized
        or "which course" in normalized
        or "which program" in normalized
        or "which counsellor" in normalized
        or "which counselor" in normalized
        or "which campus" in normalized
        or "which state" in normalized
        or "which source" in normalized
    ):
        return "table", None

    return "text", None


def _is_yoy_term(term: str) -> bool:
    t = term.lower().strip()
    if re.match(r"^2\d{3}$", t):
        return True
    yoy_indicators = ["last year", "previous year", "this year", "last cycle", "previous cycle", "py", "cy"]
    if any(ind in t for ind in yoy_indicators):
        return True
    return False


def extract_comparison(question: str) -> dict[str, Any] | None:
    """Extract generic comparison candidates from user question."""
    normalized = normalize_text(question)
    is_comp = any(kw in normalized for kw in ["vs", "versus", "compare", "compared", "against", "side by side", "difference between"])
    if not is_comp:
        return None

    left_raw, right_raw = None, None
    
    # 1. difference between A and B / compare A and B / compare A with/to B
    p1 = re.search(r"\b(?:difference between|compare|comparison of)\s+(.*?)\s+(?:and|with|to)\s+(.*)", normalized)
    if p1:
        left_raw, right_raw = p1.group(1), p1.group(2)
    else:
        # 2. how do A and B compare / put A and B side by side
        p2 = re.search(r"\b(?:how do|how does|put)\s+(.*?)\s+and\s+(.*?)\s+(?:compare|side by side)\b", normalized)
        if p2:
            left_raw, right_raw = p2.group(1), p2.group(2)
        else:
            # 3. A vs B / A versus B / A compared with B / A compared to B
            p3 = re.search(r"\b(.*?)\s+(?:vs|versus|compared with|compared to|against)\s+(.*)", normalized)
            if p3:
                left_raw, right_raw = p3.group(1), p3.group(2)

    if not left_raw or not right_raw:
        return None

    def _clean_phrase(phrase: str) -> str:
        p = phrase
        p = re.sub(r"^\s*between\s+", "", p, flags=re.IGNORECASE)
        for kw in NOISE_WORDS:
            p = re.sub(rf"\b{re.escape(kw)}\b", "", p, flags=re.IGNORECASE)
        p = re.sub(r"[^\w\s\.-]", "", p)
        return p.strip()

    left = _clean_phrase(left_raw)
    right = _clean_phrase(right_raw)

    if not left or not right:
        return None
        
    # If either is a YoY term, this is a YoY comparison, not an entity comparison!
    if _is_yoy_term(left) or _is_yoy_term(right):
        return None

    return {
        "is_comparison": True,
        "requested_values": [left.title(), right.title()],
        "raw_values": [left, right],
    }


def detect_metric(question: str) -> str | None:
    normalized = normalize_text(question)
    candidates = []

    for metric, aliases in METRIC_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                candidates.append((len(alias), metric))

    if not candidates:
        return None

    candidates.sort(reverse=True)
    return candidates[0][1]


def detect_funnel(question: str) -> bool:
    normalized = normalize_text(question)
    for pattern in FUNNEL_PATTERNS:
        if pattern in normalized:
            return True
    return False


def detect_funnel_by_stages(question: str) -> bool:
    normalized = normalize_text(question)
    stages = ["lead", "leads", "cucet", "admission", "admissions"]
    matched = sum(
        1 for stage in stages if re.search(rf"\b{re.escape(stage)}\b", normalized)
    )
    return matched >= 3


def detect_year(question: str) -> str | None:
    match = re.search(r"\b(20\d{2})\b", question)
    if match:
        return match.group(1)
    return None


def detect_time_context(question: str) -> str | None:
    normalized = normalize_text(question)
    explicit_year = detect_year(question)
    if explicit_year:
        return explicit_year

    for pattern in ["this year", "current year", "this cycle", "current cycle", "cy"]:
        if pattern in normalized:
            return "current_year"

    for pattern in ["last year", "previous year", "previous cycle", "py"]:
        if pattern in normalized:
            return "previous_year"

    return None


def detect_dimensions(question: str) -> list[str]:
    normalized = normalize_text(question)
    dimensions = []

    for dimension, aliases in DIMENSION_ALIASES.items():
        for alias in aliases:
            if re.search(r"\b" + re.escape(alias) + r"\b", normalized):
                dimensions.append(dimension)
                break

    return dimensions



def detect_source_intent(question: str) -> bool:
    normalized = normalize_text(question)
    patterns = [
        "source performance",
        "source analysis",
        "source performed",
        "sources performed",
        "best source",
        "worst source",
        "bad source",
        "poor conversion",
        "high leads",
        "low conversion",
        "most leads",
        "source gave",
        "source generated",
        "source conversion",
        "no admissions",
        "zero admissions",
        "leads but no",
        "leads but zero",
    ]
    return any(pattern in normalized for pattern in patterns)


def detect_source_detail(question: str) -> tuple[str | None, str | None]:
    normalized = normalize_text(question)
    known_sources = {
        "Digital": ["facebook", "google"],
        "Organic": ["website"],
        "Offline": ["education fair"],
    }

    for main_source, sources in known_sources.items():
        for source in sources:
            if source in normalized:
                return main_source, source.title()

    return None, None


def detect_anaphora_references(question: str) -> dict[str, Any]:
    q_norm = question.lower().strip()
    pronouns = ["they", "them", "their", "it", "this", "that", "those", "these", "same", "previous result", "last result", "which one", "the top 3", "top 3", "top three"]
    ambiguous_reference_phrases = [
        "what improved", "best one", "they perform", "how did they", "show me the best"
    ]
    has_pronoun = any(re.search(r"\b" + re.escape(p) + r"\b", q_norm) for p in pronouns) or \
                  "which one" in q_norm or "show top 3" in q_norm or "show top 5" in q_norm or "show the top 3" in q_norm or \
                  any(phrase in q_norm for phrase in ambiguous_reference_phrases) or \
                  bool(re.search(r"\b(one|they|them|it)\b", q_norm))

    selectors = {
        "first": ["first one", "the first one", "1st one"],
        "second": ["second one", "the second one", "2nd one"],
        "top_one": ["top one", "the top one", "which one"],
        "worst_one": ["worst one", "the worst one", "bottom one", "the bottom one"],
        "top_3": ["the top 3", "the top three", "show top 3", "show the top 3"],
    }
    matched_selector = None
    for s_key, s_aliases in selectors.items():
        if any(alias in q_norm for alias in s_aliases):
            matched_selector = s_key
            break

    has_explicit_dim = any(w in q_norm for w in ["course", "courses", "program", "programs", "counsellor", "counselors", "counsellors", "source", "sources", "state", "campus", "campuses"])
    is_standalone_yoy = has_explicit_dim and any(w in q_norm for w in ["dropped", "decreased", "increased", "decline", "improved", "drops", "increases", "decreases"]) and not ("compare them" in q_norm or "why" in q_norm or "reason" in q_norm)

    causal = any(kw in q_norm for kw in ["reason", "reasons", "why", "success", "cause", "caused", "drove", "driver", "drivers", "contribution", "contribute", "contributing", "additional"])
    is_chart = any(kw in q_norm for kw in ["bar chart", "pie chart", "line chart", "as a bar", "as a pie", "show as a pie", "show as a bar"])
    is_yoy = any(kw in q_norm for kw in ["compare with last year", "compared with last year", "compare them with last year", "compare it with last year", "compare to last year", "compare it to last year", "compared to last year"]) or \
             (("last year" in q_norm or "previous year" in q_norm) and ("compare" in q_norm or "compared" in q_norm))
    is_same = "same" in q_norm
    comp_check = extract_comparison(question)
    is_format_change = (is_chart or "show as table" in q_norm or "as table" in q_norm) and not has_explicit_dim and not comp_check

    is_reference = False
    if not is_standalone_yoy:
        is_reference = (has_pronoun and not has_explicit_dim) or (matched_selector is not None and not is_standalone_yoy) or is_same or causal or "only direct and indirect" in q_norm or "compare them" in q_norm or is_format_change

    return {
        "is_reference": is_reference,
        "has_pronoun": has_pronoun,
        "selector": matched_selector,
        "is_causal": causal,
        "is_chart": is_chart,
        "is_yoy": is_yoy,
        "is_same": is_same,
    }


def extract_heuristics_filters(question: str) -> dict[str, str]:
    q_lower = question.lower()
    filters = {}
    
    # If the question contains ranking, comparison, or YoY keywords, skip heuristic filter extraction
    skip_keywords = [
        "most", "highest", "lowest", "top", "vs", "versus", "compare", "compared",
        "improved", "dropped", "decreased", "increased", "decline", "declined",
        "improving", "dropping", "worst", "best", "who ", "which ", "why", "difference",
        "side by side", "between"
    ]
    if any(kw in q_lower for kw in skip_keywords):
        quotes = re.findall(r'["\'](.*?)["\']', question)
        if quotes:
            filters["unknown_dim"] = quotes[0]
        return filters

    # 1. Look for quoted strings
    quotes = re.findall(r'["\'](.*?)["\']', question)
    if quotes:
        # Keep quotes as potential filter values
        filters["unknown_dim"] = quotes[0]

    # 2. Heuristics for dimension keyword follow-ups
    for keyword, dim in [
        ("program", "program_name"),
        ("course", "program_name"),
        ("campus", "campus_name"),
        ("state", "state"),
        ("owner", "owner"),
        ("counselor", "owner"),
        ("counsellor", "owner"),
        ("source", "source"),
    ]:
        idx = q_lower.find(keyword)
        if idx != -1:
            # Extract substring after keyword
            sub = question[idx + len(keyword):].strip()
            # Clean leading noise
            sub = re.sub(r"^(name|of|for|is|to|:|'|\")\s*", "", sub, flags=re.IGNORECASE).strip()
            if sub:
                # Remove common trailing chart/format noise
                for noise in ["as a", "in 2026", "in 2025", "for 2026", "for 2025", "as a bar", "as a pie", "bar chart", "pie chart"]:
                    noise_idx = sub.lower().find(noise)
                    if noise_idx != -1:
                        sub = sub[:noise_idx].strip()
                sub = sub.rstrip("?:.!'\"").strip()
                if sub and len(sub) > 1:
                    filters[dim] = sub
                    
    # 3. Fallback for "for <value>" or "in <value>" patterns
    if not filters:
        for prep in ["for", "in", "of", "to"]:
            match = re.search(rf"\b{prep}\s+([a-zA-Z0-9\s.-]+)(?:\s+in\s+20\d\d|\s+for\s+20\d\d|\b|$)", question, flags=re.IGNORECASE)
            if match:
                val = match.group(1).strip()
                if val.lower() not in ["admission", "admissions", "lead", "leads", "cucet", "table", "chart", "bar", "pie", "growth", "performance"]:
                    # Exclude 4-digit years from being treated as arbitrary filters
                    if not (val.isdigit() and len(val) == 4 and val.startswith("20")):
                        val = val.rstrip("?:.!'\"").strip()
                        if val and len(val) > 1:
                            filters["unknown_dim"] = val
                            break
                        
    return filters


def parse_question(question: str) -> dict[str, Any]:
    """Convert natural-language question into a structured intent."""
    normalized = normalize_text(question)
    limit = None
    limit_match = re.search(r"\b(?:top|bottom|first|last|highest|lowest)\s+(\d+)\b", normalized)
    if limit_match:
        limit = int(limit_match.group(1))

    ref_info = detect_anaphora_references(question)
    response_type, chart_type = detect_response_format(question)
    heur_filters = extract_heuristics_filters(question)

    if ref_info["is_reference"]:
        return {
            "question": question,
            "intent_type": "followup_reference",
            "metric": "admission",
            "time_context": detect_time_context(question),
            "dimensions": [],
            "filters": heur_filters,
            "response_type": response_type,
            "chart_type": chart_type,
            "ref_info": ref_info,
            "limit": limit,
        }

    metric = detect_metric(question)
    source_intent = detect_source_intent(question)
    source_detail = detect_source_detail(question)
    time_context = detect_time_context(question)
    dimensions = detect_dimensions(question)
    funnel = detect_funnel(question) or detect_funnel_by_stages(question)

    comparison_info = extract_comparison(question)
    if comparison_info:
        return {
            "question": question,
            "intent_type": "comparison",
            "comparison_info": comparison_info,
            "metric": metric or "admission",
            "time_context": time_context,
            "dimensions": dimensions,
            "filters": heur_filters,
            "response_type": response_type,
            "chart_type": chart_type,
        }

    yoy_words = [
        "dropped", "decreased", "increased", "improved", "improving", "decline",
        "previous year", "last year", "yoy", "year over year", "rate drop", "rate dropped",
        "improvement", "improvements", "lost", "decline", "declined"
    ]
    if any(w in normalized for w in yoy_words):
        if not dimensions:
            if any(w in normalized for w in ["counsellor", "counselor", "agent", "owner"]):
                dimensions = ["owner"]
            elif any(w in normalized for w in ["course", "courses", "program", "programs"]):
                dimensions = ["program_name"]
            else:
                dimensions = []

        return {
            "question": question,
            "intent_type": "yoy",
            "metric": metric or "admission",
            "time_context": time_context,
            "dimensions": dimensions,
            "filters": heur_filters,
            "response_type": response_type,
            "chart_type": chart_type,
        }

    ranking_words = [
        "who brought", "who generated", "which generated", "which had",
        "highest number", "lowest number", "most", "fewest", "highest",
        "lowest", "top", "best", "worst"
    ]
    if any(w in normalized for w in ranking_words):
        if not dimensions:
            if any(w in normalized for w in ["who", "counsellor", "counselor"]):
                dimensions = ["owner"]
            elif any(w in normalized for w in ["course", "courses", "program", "programs"]):
                dimensions = ["program_name"]
            else:
                dimensions = []

        return {
            "question": question,
            "intent_type": "ranking",
            "metric": metric or "admission",
            "time_context": time_context,
            "dimensions": dimensions,
            "filters": heur_filters,
            "response_type": response_type,
            "chart_type": chart_type,
            "limit": limit,
        }

    if source_intent or (source_detail[0] and source_detail[1]):
        return {
            "question": question,
            "intent_type": "source",
            "metric": metric,
            "time_context": time_context,
            "dimensions": dimensions,
            "filters": heur_filters,
            "response_type": response_type,
            "chart_type": chart_type,
            "source_detail": (
                {
                    "main_source": source_detail[0],
                    "source": source_detail[1],
                }
                if source_detail[0] and source_detail[1]
                else None
            ),
        }

    if funnel:
        return {
            "question": question,
            "intent_type": "funnel",
            "metric": None,
            "time_context": time_context,
            "dimensions": dimensions,
            "filters": heur_filters,
            "response_type": response_type,
            "chart_type": chart_type,
        }

    # If no metric, dimension, source, funnel, or comparison keyword was matched:
    if not metric and not dimensions:
        if any(kw in normalized for kw in ["how many", "total", "count", "number of", "how much"]):
            metric = "admission"
        elif any(kw in normalized for kw in ["increased", "decreased", "improve", "improved", "dropped", "decline", "performance", "previous year", "last year"]):
            metric = "admission"
        else:
            return {
                "question": question,
                "intent_type": "unknown",
                "metric": None,
                "time_context": time_context,
                "dimensions": [],
                "filters": heur_filters,
                "response_type": response_type,
                "chart_type": chart_type,
            }

    return {
        "question": question,
        "intent_type": "breakdown" if dimensions else "metric",
        "metric": metric or "admission",
        "time_context": time_context,
        "dimensions": dimensions,
        "filters": heur_filters,
        "response_type": response_type,
        "chart_type": chart_type,
        "limit": limit,
    }