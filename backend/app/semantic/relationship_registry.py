from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.semantic.relationship_validator import (
    validate_relationship,
)


def save_relationships(
    db: Session,
    relationships: list[dict[str, Any]],
) -> int:

    saved_count = 0

    for relationship in relationships:

        result = validate_relationship(
            db,
            relationship,
        )

        query = text(
            """
            INSERT INTO intelligence.relationships
            (
                left_schema,
                left_table,
                left_column,
                right_schema,
                right_table,
                right_column,
                relationship_key,
                relationship_type,
                candidate_confidence,
                validation_score,
                left_row_count,
                right_row_count,
                matching_rows,
                unmatched_left_rows,
                unmatched_right_rows,
                status,
                validation_details
            )
            VALUES
            (
                :left_schema,
                :left_table,
                :left_column,
                :right_schema,
                :right_table,
                :right_column,
                :relationship_key,
                :relationship_type,
                :candidate_confidence,
                :validation_score,
                :left_row_count,
                :right_row_count,
                :matching_rows,
                :unmatched_left_rows,
                :unmatched_right_rows,
                :status,
                CAST(:validation_details AS jsonb)
            )
            """
        )

        unmatched_left = max(
            result["left_distinct_values"]
            - result["matching_rows"],
            0,
        )

        unmatched_right = max(
            result["right_distinct_values"]
            - result["matching_rows"],
            0,
        )

        import json

        validation_details = {
            "reason": result.get(
                "reason"
            ),
            "relationship_key": result.get(
                "relationship_key"
            ),
            "left_distinct_values": result[
                "left_distinct_values"
            ],
            "right_distinct_values": result[
                "right_distinct_values"
            ],
        }

        db.execute(
            query,
            {
                "left_schema": result[
                    "left_schema"
                ],

                "left_table": result[
                    "left_table"
                ],

                "left_column": result[
                    "left_column"
                ],

                "right_schema": result[
                    "right_schema"
                ],

                "right_table": result[
                    "right_table"
                ],

                "right_column": result[
                    "right_column"
                ],

                "relationship_key": result[
                    "relationship_key"
                ],

                "relationship_type": result[
                    "relationship_type"
                ],

                "candidate_confidence": result[
                    "candidate_confidence"
                ],

                "validation_score": result[
                    "validation_score"
                ],

                "left_row_count": result[
                    "left_row_count"
                ],

                "right_row_count": result[
                    "right_row_count"
                ],

                "matching_rows": result[
                    "matching_rows"
                ],

                "unmatched_left_rows": unmatched_left,

                "unmatched_right_rows": unmatched_right,

                "status": result[
                    "status"
                ],

                "validation_details": json.dumps(
                    validation_details,
                    default=str,
                ),
            },
        )

        saved_count += 1

    db.commit()

    return saved_count