import re
from typing import Any

from app.semantic.business_resolver import (
    resolve_business_metric,
)
from app.semantic.concepts import CONCEPTS
from app.semantic.time_parser import (
    detect_time_context,
)


def normalize_text(value: str) -> str:
    """
    Normalize text for semantic comparison.

    Examples:
        "Program_Name" -> "program name"
        "CY Admission" -> "cy admission"
        "Lead-Admission%" -> "lead admission%"
    """

    value = str(value).lower().strip()

    value = value.replace("_", " ")
    value = value.replace("-", " ")

    value = re.sub(
        r"[^a-z0-9% ]+",
        " ",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def get_tokens(value: str) -> set[str]:
    """
    Convert text into meaningful tokens.
    """

    normalized = normalize_text(value)

    return {
        token
        for token in normalized.split()
        if len(token) > 1
    }


def token_score(
    column_name: str,
    synonyms: list[str],
) -> float:
    """
    Calculate semantic similarity between
    a column name and a list of synonyms.
    """

    normalized_column = normalize_text(
        column_name
    )

    column_tokens = get_tokens(
        column_name
    )

    best_score = 0.0

    for synonym in synonyms:

        normalized_synonym = normalize_text(
            synonym
        )

        synonym_tokens = get_tokens(
            synonym
        )

        # -----------------------------------------
        # Exact full-column match
        # -----------------------------------------

        if normalized_column == normalized_synonym:

            best_score = max(
                best_score,
                1.0,
            )

            continue

        # -----------------------------------------
        # Exact token-set match
        # -----------------------------------------

        if (
            synonym_tokens
            and synonym_tokens.issubset(
                column_tokens
            )
        ):

            if len(synonym_tokens) > 1:

                best_score = max(
                    best_score,
                    0.95,
                )

            else:

                best_score = max(
                    best_score,
                    0.90,
                )

            continue

        # -----------------------------------------
        # Partial token overlap
        # -----------------------------------------

        if (
            column_tokens
            and synonym_tokens
        ):

            overlap = (
                len(
                    column_tokens
                    & synonym_tokens
                )
                / len(synonym_tokens)
            )

            # Ignore weak matches
            if overlap >= 0.5:

                score = overlap * 0.70

                best_score = max(
                    best_score,
                    score,
                )

    return best_score


def determine_data_role(
    category: str,
) -> str:
    """
    Convert semantic category into a
    business data role.
    """

    # Metrics
    if category in (
        "metric",
        "funnel",
    ):
        return "metric"

    # Dates
    if category == "date":
        return "date"

    # Dimensions
    if category in (
        "time_dimension",
        "geography",
        "academic",
        "organization",
        "marketing",
        "identity",
    ):
        return "dimension"

    return "unknown"


def build_candidate(
    concept_key: str,
    concept: dict,
    score: float,
    time_context: str | None,
    sample_values: list[Any],
    data_type: str,
    data_role: str | None = None,
) -> dict:
    """
    Build a consistent semantic candidate.
    """

    if data_role is None:

        data_role = determine_data_role(
            concept["category"]
        )

    return {
        "concept_key": concept_key,

        "display_name": concept[
            "display_name"
        ],

        "score": round(
            score,
            4,
        ),

        "time_context": time_context,

        "category": concept[
            "category"
        ],

        "sample_values": (
            sample_values[:5]
        ),

        "data_type": data_type,

        "data_role": data_role,
    }


def infer_column(
    column_name: str,
    sample_values: list[Any],
    data_type: str,
) -> list[dict]:
    """
    Infer the business meaning of a column.

    Priority:

    1. Client-specific business rules
    2. Exact semantic concept match
    3. Strong token-based semantic match
    """

    candidates = []

    # =================================================
    # STEP 1
    # Client-specific business resolver
    # =================================================

    business_match = resolve_business_metric(
        column_name
    )

    if business_match:

        concept_key = business_match[
            "concept_key"
        ]

        concept = CONCEPTS.get(
            concept_key
        )

        if concept:

            return [
                build_candidate(
                    concept_key=concept_key,
                    concept=concept,
                    score=1.0,
                    time_context=(
                        business_match[
                            "time_context"
                        ]
                    ),
                    sample_values=sample_values,
                    data_type=data_type,
                    data_role=(
                        business_match[
                            "data_role"
                        ]
                    ),
                )
            ]

    # =================================================
    # STEP 2
    # Generic semantic inference
    # =================================================

    detected_time_context = (
        detect_time_context(
            column_name
        )
    )

    for concept_key, concept in CONCEPTS.items():

        score = token_score(
            column_name,
            concept["synonyms"],
        )

        # Ignore weak matches
        if score < 0.70:
            continue

        candidates.append(
            build_candidate(
                concept_key=concept_key,
                concept=concept,
                score=score,
                time_context=(
                    detected_time_context
                ),
                sample_values=sample_values,
                data_type=data_type,
            )
        )

    # =================================================
    # STEP 3
    # Sort strongest candidate first
    # =================================================

    candidates.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    # =================================================
    # STEP 4
    # Exact-match protection
    #
    # Example:
    #
    # Admission Year
    #
    # We want:
    # admission_year = 1.0
    #
    # Not:
    # admission_year = 1.0
    # admission = 0.9
    # year = 0.9
    # =================================================

    exact_matches = [
        candidate
        for candidate in candidates
        if candidate["score"] == 1.0
    ]

    if exact_matches:

        return exact_matches[:1]

    # =================================================
    # STEP 5
    # Return strongest candidates
    # =================================================

    return candidates[:5]