from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.semantic.analyzer import analyze_dataset
from app.semantic.registry import (
    save_semantic_mappings,
)
from app.semantic.column_registry import (
    save_column_mappings,
)

router = APIRouter(
    prefix="/api/semantic",
    tags=["Semantic Understanding"],
)


@router.post(
    "/analyze/{dataset_id}"
)
def analyze_dataset_endpoint(
    dataset_id: UUID,
    db: Session = Depends(get_db),
):

    try:

        result = analyze_dataset(
            db=db,
            dataset_id=dataset_id,
        )

        saved_count = (
            save_semantic_mappings(
                db=db,
                dataset_id=dataset_id,
                analysis=result,
            )
        )
        saved_columns = save_column_mappings(
            db=db,
            dataset_id=dataset_id,
            analysis=result,
        )

        result[
            "mappings_saved"
        ] = saved_count

        return result

    except Exception as error:

        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=(
                f"Semantic analysis failed: "
                f"{error}"
            ),
        )