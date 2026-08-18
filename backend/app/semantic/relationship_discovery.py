from typing import Any


# ============================================================
# RELATIONSHIP CANDIDATES
# ============================================================

RELATIONSHIP_KEYS = {
    "user_id",
    "enquiry_id",
    "lead_id",
    "registration_id",
    "admission_id",
    "program_code",
}


def normalize(value: str) -> str:
    return str(value).lower().strip()


def is_relationship_candidate(
    column_name: str,
) -> bool:

    return normalize(
        column_name
    ) in RELATIONSHIP_KEYS


def discover_relationships(
    schema_info: dict,
) -> list[dict[str, Any]]:

    relationships = []

    tables = schema_info.get(
        "tables",
        [],
    )

    # --------------------------------------------------------
    # Compare every table against every other table
    # --------------------------------------------------------

    for i, left_table in enumerate(tables):

        for right_table in tables[i + 1:]:

            left_schema = left_table[
                "schema"
            ]

            right_schema = right_table[
                "schema"
            ]

            left_name = left_table[
                "table"
            ]

            right_name = right_table[
                "table"
            ]

            # ------------------------------------------------
            # Columns
            # ------------------------------------------------

            left_columns = {
                normalize(column["column"]): column
                for column in left_table.get(
                    "columns",
                    [],
                )
            }

            right_columns = {
                normalize(column["column"]): column
                for column in right_table.get(
                    "columns",
                    [],
                )
            }

            common_columns = (
                set(left_columns.keys())
                & set(right_columns.keys())
            )

            # ------------------------------------------------
            # Find common relationship keys
            # ------------------------------------------------

            for column_name in common_columns:

                if not is_relationship_candidate(
                    column_name
                ):
                    continue

                left_column = left_columns[
                    column_name
                ]

                right_column = right_columns[
                    column_name
                ]

                relationships.append(
                    {
                        "left_schema": left_schema,
                        "left_table": left_name,
                        "left_column": left_column[
                            "column"
                        ],
                        "right_schema": right_schema,
                        "right_table": right_name,
                        "right_column": right_column[
                            "column"
                        ],
                        "relationship_key": column_name,
                        "confidence": 0.90,
                        "relationship_type": (
                            "candidate_foreign_key"
                        ),
                        "reason": (
                            "Same business "
                            "relationship key exists "
                            "in both tables."
                        ),
                    }
                )

    return relationships