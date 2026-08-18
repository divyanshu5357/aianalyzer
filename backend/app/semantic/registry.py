import json

from sqlalchemy import text
from sqlalchemy.orm import Session


def save_semantic_mappings(
    db: Session,
    dataset_id,
    analysis: dict,
) -> int:

    saved_count = 0

    for column in analysis.get(
        "columns",
        [],
    ):

        candidates = column.get(
            "candidates",
            [],
        )

        if not candidates:
            continue

        # Best semantic candidate
        best = candidates[0]

        concept_key = best["concept_key"]

        confidence = best["score"]

        time_context = best.get(
            "time_context"
        )

        # Use role already determined
        # by the semantic inference layer.
        data_role = best.get(
            "data_role"
        )

        evidence = {
            "column": column["column"],
            "data_type": column["data_type"],
            "sample_values": column[
                "sample_values"
            ],
            "candidate": best,
        }

        query = text(
            """
            INSERT INTO intelligence.semantic_mappings
            (
                dataset_id,
                source_column,
                concept_key,
                time_context,
                data_role,
                confidence,
                evidence,
                inference_method,
                status
            )
            VALUES
            (
                :dataset_id,
                :source_column,
                :concept_key,
                :time_context,
                :data_role,
                :confidence,
                CAST(:evidence AS jsonb),
                :inference_method,
                :status
            )
            ON CONFLICT (
                dataset_id,
                source_column,
                concept_key
            )
            DO UPDATE SET
                time_context = EXCLUDED.time_context,
                data_role = EXCLUDED.data_role,
                confidence = EXCLUDED.confidence,
                evidence = EXCLUDED.evidence,
                inference_method = EXCLUDED.inference_method,
                status = EXCLUDED.status,
                updated_at = CURRENT_TIMESTAMP
            """
        )

        db.execute(
            query,
            {
                "dataset_id": dataset_id,

                "source_column": column[
                    "column"
                ],

                "concept_key": concept_key,

                "time_context": time_context,

                "data_role": data_role,

                "confidence": confidence,

                "evidence": json.dumps(
                    evidence,
                    default=str,
                ),

                "inference_method": (
                    "rule_based_semantic_inference"
                ),

                "status": "suggested",
            },
        )

        saved_count += 1

    db.commit()

    return saved_count