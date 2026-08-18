from sqlalchemy import text
from sqlalchemy.orm import Session


def save_column_mappings(
    db: Session,
    dataset_id,
    analysis: dict,
) -> int:

    saved_count = 0

    for column in analysis.get(
        "columns",
        [],
    ):

        canonical_column = column.get(
            "canonical_column"
        )

        if not canonical_column:
            continue

        business_meaning = column.get(
            "business_meaning"
        )

        confidence = column.get(
            "confidence",
            0.0,
        )

        data_type = column.get(
            "data_type"
        )

        query = text(
            """
            INSERT INTO intelligence.column_mappings
            (
                dataset_id,
                original_column,
                canonical_column,
                business_meaning,
                data_type,
                confidence,
                verified
            )
            VALUES
            (
                :dataset_id,
                :original_column,
                :canonical_column,
                :business_meaning,
                :data_type,
                :confidence,
                false
            )
            ON CONFLICT (
                dataset_id,
                original_column
            )
            DO UPDATE SET
                canonical_column = EXCLUDED.canonical_column,
                business_meaning = EXCLUDED.business_meaning,
                data_type = EXCLUDED.data_type,
                confidence = EXCLUDED.confidence,
                updated_at = CURRENT_TIMESTAMP
            """
        )

        db.execute(
            query,
            {
                "dataset_id": dataset_id,

                "original_column": column[
                    "column"
                ],

                "canonical_column": (
                    canonical_column
                ),

                "business_meaning": (
                    business_meaning
                ),

                "data_type": data_type,

                "confidence": confidence,
            },
        )

        saved_count += 1

    db.commit()

    return saved_count