import pytest
from unittest.mock import MagicMock
from app.ingestion.job_tracker import (
    create_job,
    update_job_progress,
    mark_job_completed,
    mark_job_failed,
    get_job_status,
)


def test_job_tracker_lifecycle():
    job_id = "test_job_12345"

    # 1. Create job
    created = create_job(job_id, filename="test_dataset.csv", total_rows=1000)
    assert created["job_id"] == job_id
    assert created["stage"] == "parsing"
    assert created["status"] == "processing"
    assert created["total_rows"] == 1000

    # 2. Update progress: Staging
    staged = update_job_progress(job_id, "staging", processed_rows=500, total_rows=1000)
    assert staged["stage"] == "staging"
    assert staged["processed_rows"] == 500
    assert staged["progress_percent"] == 27.5  # 10 + 0.5 * 35

    # 3. Update progress: Normalization
    normed = update_job_progress(job_id, "normalization", processed_rows=800, total_rows=1000)
    assert normed["stage"] == "normalization"
    assert normed["processed_rows"] == 800
    assert normed["progress_percent"] == 86.0  # 50 + 0.8 * 45

    # 4. Fetch job status
    status = get_job_status(job_id)
    assert status is not None
    assert status["job_id"] == job_id
    assert status["stage"] == "normalization"

    # 5. Complete job
    completed = mark_job_completed(job_id, message="Completed successfully")
    assert completed["status"] == "completed"
    assert completed["stage"] == "completed"
    assert completed["progress_percent"] == 100.0

    # 6. Check status again
    final_status = get_job_status(job_id)
    assert final_status["status"] == "completed"


def test_job_tracker_failure():
    job_id = "test_job_fail_999"
    create_job(job_id, filename="bad_dataset.csv", total_rows=500)

    failed = mark_job_failed(job_id, error="Invalid column schema")
    assert failed["status"] == "failed"
    assert failed["error"] == "Invalid column schema"

    status = get_job_status(job_id)
    assert status["status"] == "failed"
    assert status["error"] == "Invalid column schema"
