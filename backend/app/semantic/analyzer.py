from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.semantic.inference import infer_column


def analyze_dataset(
    db: Session,
    dataset_id,
) -> dict:

    query = text(
        """
        SELECT
            r.row_number,
            c.cleaned_data
        FROM staging.cleaned_records c
        JOIN staging.records r
            ON c.staging_record_id = r.id
        WHERE c.dataset_id = :dataset_id
        ORDER BY r.row_number
        LIMIT 1000
        """
    )

    result = db.execute(
        query,
        {
            "dataset_id": dataset_id,
        },
    )

    rows = result.fetchall()

    if not rows:
        return {
            "dataset_id": str(dataset_id),
            "columns": [],
            "message": "No cleaned records found.",
        }

    column_values = defaultdict(list)

    for row in rows:

        data = row.cleaned_data

        if not isinstance(data, dict):
            continue

        for column, value in data.items():

            if len(column_values[column]) < 20:

                column_values[column].append(value)

    analysis = []

    for column_name, values in column_values.items():

        non_null_values = [
            value
            for value in values
            if value is not None
        ]

        if non_null_values:

            first_value = non_null_values[0]

            data_type = type(
                first_value
            ).__name__

        else:

            data_type = "unknown"

        candidates = infer_column(
            column_name=column_name,
            sample_values=values,
            data_type=data_type,
        )

        best_candidate = (
            candidates[0]
            if candidates
            else None
        )

        analysis.append(
            {
                "column": column_name,
                "data_type": data_type,
                "sample_values": values[:5],
                "candidates": candidates,

                "canonical_column": (
                    best_candidate["concept_key"]
                    if best_candidate
                    else None
                ),

                "business_meaning": (
                    best_candidate[
                        "display_name"
                    ]
                    if best_candidate
                    else None
                ),

                "confidence": (
                    best_candidate["score"]
                    if best_candidate
                    else 0.0
                ),
            }
        )

    return {
        "dataset_id": str(dataset_id),
        "columns": analysis,
    }