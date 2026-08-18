from pydantic import BaseModel
from typing import Any


class DatasetProfile(BaseModel):
    dataset_id: str
    filename: str
    rows: int
    columns: int
    column_names: list[str]
    missing_values: int
    duplicate_rows: int
    quality_score: float
    sample_rows: list[dict[str, Any]]