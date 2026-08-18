import json

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.cleaning.engine import clean_record


def clean_dataset(
    db: Session,
    dataset_id,
) -> dict:

    # ----------------------------------
    # Get staging records
    # ----------------------------------

    select_query = text(
        """
        SELECT
            id,
            row_number,
            raw_data
        FROM staging.records
        WHERE dataset_id = :dataset_id
        ORDER BY row_number
        """
    )

    result = db.execute(
        select_query,
        {
            "dataset_id": dataset_id,
        },
    )

    records = result.fetchall()

    cleaned_count = 0
    issue_count = 0

    # ----------------------------------
    # Process each record
    # ----------------------------------

    for record in records:

        staging_id = record.id

        raw_data = record.raw_data

        cleaned_data, issues = clean_record(
            raw_data
        )

        insert_query = text(
            """
            INSERT INTO staging.cleaned_records
            (
                dataset_id,
                staging_record_id,
                cleaned_data,
                issues,
                issue_count,
                cleaning_status
            )
            VALUES
            (
                :dataset_id,
                :staging_record_id,
                CAST(:cleaned_data AS JSONB),
                CAST(:issues AS JSONB),
                :issue_count,
                :cleaning_status
            )
            """
        )

        db.execute(
            insert_query,
            {
                "dataset_id": dataset_id,
                "staging_record_id": staging_id,
                "cleaned_data": json.dumps(
                    cleaned_data
                ),
                "issues": json.dumps(
                    issues
                ),
                "issue_count": len(issues),
                "cleaning_status": (
                    "issues_found"
                    if issues
                    else "clean"
                ),
            },
        )

        cleaned_count += 1
        issue_count += len(issues)

    db.commit()

    return {
        "dataset_id": str(dataset_id),
        "records_processed": cleaned_count,
        "issues_found": issue_count,
    }