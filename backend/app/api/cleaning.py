from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.cleaning.service import clean_dataset


router = APIRouter(
    prefix="/api/data",
    tags=["Data Cleaning"],
)


@router.post("/clean/{dataset_id}")
def clean_dataset_endpoint(
    dataset_id: UUID,
    db: Session = Depends(get_db),
):

    try:

        result = clean_dataset(
            db=db,
            dataset_id=dataset_id,
        )

        return result

    except Exception as error:

        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=(
                f"Cleaning failed: {error}"
            ),
        )