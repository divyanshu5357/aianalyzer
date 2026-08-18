from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def validate_relationship(
    db: Session,
    relationship: dict[str, Any],
) -> dict[str, Any]:
    """
    Validate a candidate relationship by checking
    actual value overlap between two columns.
    """

    left_schema = relationship["left_schema"]
    left_table = relationship["left_table"]
    left_column = relationship["left_column"]

    right_schema = relationship["right_schema"]
    right_table = relationship["right_table"]
    right_column = relationship["right_column"]

    # --------------------------------------------------
    # 1. Validate identifiers
    # --------------------------------------------------

    identifiers = [
        left_schema,
        left_table,
        left_column,
        right_schema,
        right_table,
        right_column,
    ]

    for identifier in identifiers:
        if not identifier.replace("_", "").isalnum():
            raise ValueError(
                f"Unsafe SQL identifier: {identifier}"
            )

    # --------------------------------------------------
    # 2. Count rows on both sides
    # --------------------------------------------------

    left_count_query = text(
        f"""
        SELECT COUNT(*)
        FROM "{left_schema}"."{left_table}"
        """
    )

    right_count_query = text(
        f"""
        SELECT COUNT(*)
        FROM "{right_schema}"."{right_table}"
        """
    )

    left_row_count = db.execute(
        left_count_query
    ).scalar_one()

    right_row_count = db.execute(
        right_count_query
    ).scalar_one()

    # --------------------------------------------------
    # 3. Count matching values
    # --------------------------------------------------

    matching_query = text(
        f"""
        SELECT COUNT(*)
        FROM (
            SELECT DISTINCT "{left_column}" AS value
            FROM "{left_schema}"."{left_table}"
            WHERE "{left_column}" IS NOT NULL
        ) l
        INNER JOIN (
            SELECT DISTINCT "{right_column}" AS value
            FROM "{right_schema}"."{right_table}"
            WHERE "{right_column}" IS NOT NULL
        ) r
        ON l.value = r.value
        """
    )

    matching_rows = db.execute(
        matching_query
    ).scalar_one()

    # --------------------------------------------------
    # 4. Count distinct values
    # --------------------------------------------------

    left_distinct_query = text(
        f"""
        SELECT COUNT(DISTINCT "{left_column}")
        FROM "{left_schema}"."{left_table}"
        WHERE "{left_column}" IS NOT NULL
        """
    )

    right_distinct_query = text(
        f"""
        SELECT COUNT(DISTINCT "{right_column}")
        FROM "{right_schema}"."{right_table}"
        WHERE "{right_column}" IS NOT NULL
        """
    )

    left_distinct = db.execute(
        left_distinct_query
    ).scalar_one()

    right_distinct = db.execute(
        right_distinct_query
    ).scalar_one()

    # --------------------------------------------------
    # 5. Calculate overlap
    # --------------------------------------------------

    if left_distinct == 0 or right_distinct == 0:
        validation_score = 0.0

    else:
        smaller_distinct = min(
            left_distinct,
            right_distinct,
        )

        validation_score = (
            matching_rows / smaller_distinct
        )

        validation_score = min(
            validation_score,
            1.0,
        )

    # --------------------------------------------------
    # 6. Determine status
    # --------------------------------------------------

    if validation_score >= 0.80:
        status = "verified"

    elif validation_score >= 0.50:
        status = "possible"

    else:
        status = "rejected"

    # --------------------------------------------------
    # 7. Return validation result
    # --------------------------------------------------

    return {
        **relationship,

        "candidate_confidence": relationship.get(
            "confidence",
            0.0,
        ),

        "validation_score": round(
            validation_score,
            4,
        ),

        "left_row_count": left_row_count,

        "right_row_count": right_row_count,

        "matching_rows": matching_rows,

        "left_distinct_values": left_distinct,

        "right_distinct_values": right_distinct,

        "status": status,
    }