import re


# ============================================================
# BUSINESS PHYSICAL PROFILES
# ============================================================

PHYSICAL_PROFILES = {
    "leads": {
        "table_aliases": [
            "enquiries",
            "enquiry",
            "leads",
            "lead",
            "prospects",
            "prospect",
        ],
        "entity_columns": [
            "enquiry_id",
            "lead_id",
            "prospect_id",
            "user_id",
        ],
        "date_columns": [
            "enquiry_date",
            "lead_date",
            "created_date",
            "created_at",
        ],
    },

    "cucet": {
        "table_aliases": [
            "cucet_registrations",
            "cucet_registration",
            "cucet",
            "registrations",
            "registration",
        ],
        "entity_columns": [
            "registration_id",
            "cucet_id",
        ],
        "date_columns": [
            "registration_date",
            "cucet_date",
            "created_at",
        ],
    },

    "admission": {
        "table_aliases": [
            "admissions",
            "admission",
            "enrollments",
            "enrolments",
            "students",
        ],
        "entity_columns": [
            "admission_id",
            "enrollment_id",
            "enrolment_id",
        ],
        "date_columns": [
            "admission_date",
            "enrollment_date",
            "enrolment_date",
            "joining_date",
            "created_at",
        ],
        "status_columns": [
            "admission_status",
            "enrollment_status",
            "enrolment_status",
            "status",
        ],
    },

    "program": {
        "table_aliases": [
            "admissions",
            "admission",
            "enquiries",
            "enquiry",
            "cucet_registrations",
            "cucet_registration",
        ],
        "columns": [
            "program_name",
            "program",
            "program_code",
        ],
    },

    "campus": {
        "table_aliases": [
            "admissions",
            "admission",
            "enquiries",
            "enquiry",
            "cucet_registrations",
            "cucet_registration",
        ],
        "columns": [
            "campus_name",
            "campus",
        ],
    },

    "state": {
        "table_aliases": [
            "admissions",
            "admission",
            "enquiries",
            "enquiry",
            "cucet_registrations",
            "cucet_registration",
        ],
        "columns": [
            "state",
            "state_name",
        ],
    },
}


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_name(value: str) -> str:
    """
    Normalize a database or business name.
    """

    value = str(value).lower().strip()

    value = value.replace("_", " ")
    value = value.replace("-", " ")

    value = re.sub(
        r"[^a-z0-9 ]+",
        " ",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


# ============================================================
# COLUMN ROLE
# ============================================================

def infer_column_role(
    column_name: str,
    data_type: str,
) -> str:

    name = normalize_name(
        column_name
    )

    # -----------------------------------------
    # Date
    # -----------------------------------------

    if (
        "date" in name
        or "time" in name
    ):
        return "date"

    # -----------------------------------------
    # Status
    # -----------------------------------------

    if (
        "status" in name
        or name in (
            "exam status",
            "admission status",
            "lead status",
        )
    ):
        return "status"

    # -----------------------------------------
    # Technical ID
    # -----------------------------------------

    if name == "id":
        return "technical_identifier"

    # -----------------------------------------
    # Business identifiers
    # -----------------------------------------

    if (
        name.endswith(" id")
        or name.endswith(" code")
    ):
        return "identifier"

    # -----------------------------------------
    # Dimensions
    # -----------------------------------------

    if name in (
        "program",
        "program name",
        "campus",
        "campus name",
        "cluster",
        "state",
        "state name",
        "city",
        "district",
        "country",
        "source",
        "main source",
        "lead type",
        "owner",
    ):
        return "dimension"

    # -----------------------------------------
    # Numeric
    # -----------------------------------------

    if data_type in (
        "smallint",
        "integer",
        "bigint",
        "numeric",
        "real",
        "double precision",
    ):
        return "numeric"

    return "attribute"


# ============================================================
# TABLE MATCHING
# ============================================================

def table_matches_profile(
    table_name: str,
    concept_key: str,
) -> bool:

    profile = PHYSICAL_PROFILES.get(
        concept_key
    )

    if not profile:
        return False

    normalized_table = normalize_name(
        table_name
    )

    aliases = {
        normalize_name(alias)
        for alias in profile.get(
            "table_aliases",
            [],
        )
    }

    return normalized_table in aliases


# ============================================================
# COLUMN MATCHING
# ============================================================

def column_matches_profile(
    column_name: str,
    concept_key: str,
    role: str | None = None,
) -> bool:

    profile = PHYSICAL_PROFILES.get(
        concept_key
    )

    if not profile:
        return False

    normalized_column = normalize_name(
        column_name
    )

    # Metric entity columns
    if role == "entity":

        columns = profile.get(
            "entity_columns",
            [],
        )

        return normalized_column in {
            normalize_name(column)
            for column in columns
        }

    # Date columns
    if role == "date":

        columns = profile.get(
            "date_columns",
            [],
        )

        return normalized_column in {
            normalize_name(column)
            for column in columns
        }

    # Status columns
    if role == "status":

        columns = profile.get(
            "status_columns",
            [],
        )

        return normalized_column in {
            normalize_name(column)
            for column in columns
        }

    # Dimension columns
    columns = profile.get(
        "columns",
        [],
    )

    return normalized_column in {
        normalize_name(column)
        for column in columns
    }


# ============================================================
# SCORE PHYSICAL MAPPING
# ============================================================

def score_physical_column(
    concept_key: str,
    table_name: str,
    column_name: str,
    data_type: str,
    role: str | None = None,
) -> float:

    # -----------------------------------------
    # Unknown concept
    # -----------------------------------------

    if concept_key not in PHYSICAL_PROFILES:
        return 0.0

    score = 0.0

    table_match = table_matches_profile(
        table_name,
        concept_key,
    )

    column_match = column_matches_profile(
        column_name,
        concept_key,
        role,
    )

    # -----------------------------------------
    # Strong table match
    # -----------------------------------------

    if table_match:
        score += 0.50

    # -----------------------------------------
    # Strong column match
    # -----------------------------------------

    if column_match:
        score += 0.50

    return min(
        score,
        1.0,
    )


# ============================================================
# DISCOVER PHYSICAL CANDIDATES
# ============================================================

def discover_physical_candidates(
    schema_info: dict,
    concepts: list[str],
) -> list[dict]:

    results = []

    for concept_key in concepts:

        concept_candidates = []

        # ====================================================
        # METRIC CONCEPTS
        # ====================================================

        if concept_key in (
            "leads",
            "cucet",
            "admission",
        ):

            roles = [
                "entity",
                "date",
                "status",
            ]

        else:

            roles = [
                None,
            ]

        # ====================================================
        # TABLES
        # ====================================================

        for table in schema_info.get(
            "tables",
            [],
        ):

            table_name = table[
                "table"
            ]

            # Don't inspect unrelated tables
            # for metric concepts.
            if (
                concept_key in (
                    "leads",
                    "cucet",
                    "admission",
                )
                and not table_matches_profile(
                    table_name,
                    concept_key,
                )
            ):
                continue

            # =================================================
            # COLUMNS
            # =================================================

            for column in table.get(
                "columns",
                [],
            ):

                column_name = column[
                    "column"
                ]

                data_type = column[
                    "data_type"
                ]

                for role in roles:

                    actual_role = role

                    # Dimension role inference
                    if actual_role is None:

                        actual_role = infer_column_role(
                            column_name,
                            data_type,
                        )

                    score = score_physical_column(
                        concept_key,
                        table_name,
                        column_name,
                        data_type,
                        actual_role,
                    )

                    # Ignore weak candidates
                    if score < 0.50:
                        continue

                    concept_candidates.append(
                        {
                            "concept_key": (
                                concept_key
                            ),
                            "table_schema": (
                                table["schema"]
                            ),
                            "table_name": (
                                table_name
                            ),
                            "column_name": (
                                column_name
                            ),
                            "column_role": (
                                actual_role
                            ),
                            "data_type": (
                                data_type
                            ),
                            "confidence": round(
                                score,
                                4,
                            ),
                        }
                    )

        # =================================================
        # REMOVE DUPLICATES
        # =================================================

        unique = {}

        for candidate in concept_candidates:

            key = (
                candidate["table_schema"],
                candidate["table_name"],
                candidate["column_name"],
                candidate["column_role"],
            )

            unique[key] = candidate

        concept_candidates = list(
            unique.values()
        )

        # =================================================
        # SORT
        # =================================================

        concept_candidates.sort(
            key=lambda item: (
                item["confidence"],
                item["column_role"] == "entity",
                item["column_role"] == "date",
                item["column_role"] == "status",
            ),
            reverse=True,
        )

        # Keep all meaningful mappings for
        # dimensions, but limit metric candidates.
        if concept_key in (
            "leads",
            "cucet",
            "admission",
        ):

            results.extend(
                concept_candidates[:10]
            )

        else:

            results.extend(
                concept_candidates[:10]
            )

    return results