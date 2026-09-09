import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.main import app
from app.storage.local_provider import LocalStorageProvider
from app.storage.s3_r2_provider import S3R2StorageProvider

client = TestClient(app)

def test_local_storage_multipart_flow(tmp_path):
    storage = LocalStorageProvider(base_dir=str(tmp_path))
    s3_key = "uploads/raw/test_multipart.csv"
    
    upload_id = storage.initiate_multipart_upload(s3_key)
    assert upload_id is not None
    assert isinstance(upload_id, str)
    
    part1_data = b"ProspectID,Name\nP001,Alice\n"
    part2_data = b"P002,Bob\n"
    
    etag1 = storage.upload_part(s3_key, upload_id, 1, part1_data)
    etag2 = storage.upload_part(s3_key, upload_id, 2, part2_data)
    
    assert etag1 is not None
    assert etag2 is not None
    
    parts = [
        {"PartNumber": 1, "ETag": etag1},
        {"PartNumber": 2, "ETag": etag2}
    ]
    complete_res = storage.complete_multipart_upload(s3_key, upload_id, parts)
    assert complete_res["key"] == s3_key
    assert storage.exists(s3_key) is True
    
    stored_bytes = storage.get_object(s3_key)
    assert stored_bytes == part1_data + part2_data

def test_local_storage_multipart_abort(tmp_path):
    storage = LocalStorageProvider(base_dir=str(tmp_path))
    s3_key = "uploads/raw/test_abort.csv"
    
    upload_id = storage.initiate_multipart_upload(s3_key)
    
    part1_data = b"ProspectID,Name\nP001,Alice\n"
    storage.upload_part(s3_key, upload_id, 1, part1_data)
    
    abort_res = storage.abort_multipart_upload(s3_key, upload_id)
    assert abort_res is True
    assert storage.exists(s3_key) is False

def test_api_multipart_initiate_and_abort():
    with patch("app.services.s3_storage.initiate_multipart_upload") as mock_init, \
         patch("app.services.s3_storage.create_presigned_part_url") as mock_part_url, \
         patch("app.services.s3_storage.abort_multipart_upload") as mock_abort, \
         patch("app.api.upload.get_db") as mock_get_db:
        
        mock_init.return_value = "test-upload-123"
        mock_part_url.side_effect = lambda key, upload_id, part_number, expires_in=7200: f"https://s3.amazonaws.com/test-bucket/{key}?partNumber={part_number}&uploadId={upload_id}"
        mock_abort.return_value = True

        mock_db = MagicMock()
        mock_dataset = MagicMock()
        mock_dataset.id = "ds-123"
        mock_dataset.storage_key = "uploads/ds-123/crm_large.csv"
        mock_db.query().filter().first.return_value = mock_dataset
        mock_get_db.return_value = iter([mock_db])

        # 350 MB file test
        payload = {
            "filename": "crm_large.csv",
            "file_size": 350 * 1024 * 1024,
            "file_type": "raw_data",
            "academic_year": "2024-25",
            "campus_name": "Main Campus"
        }
        res = client.post("/api/data/upload/multipart/initiate", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["upload_id"] == "test-upload-123"
        assert data["total_parts"] == 35  # 350MB / 10MB
        assert len(data["parts"]) == 35
        assert data["parts"][0]["part_number"] == 1
        assert "uploadId=test-upload-123" in data["parts"][0]["url"]

        # Abort test
        abort_payload = {
            "job_id": data["job_id"],
            "dataset_id": data["dataset_id"],
            "s3_key": data["s3_key"],
            "upload_id": data["upload_id"],
            "reason": "Cancelled by user"
        }
        abort_res = client.post("/api/data/upload/multipart/abort", json=abort_payload)
        assert abort_res.status_code == 200
        assert abort_res.json()["status"] == "aborted"

def test_s3_storage_provider_multipart_methods():
    mock_boto3_client = MagicMock()
    mock_boto3_client.create_multipart_upload.return_value = {"UploadId": "s3-mock-upload-id"}
    mock_boto3_client.generate_presigned_url.return_value = "https://s3.amazonaws.com/test-url"
    mock_boto3_client.complete_multipart_upload.return_value = {"Location": "s3://bucket/key"}
    mock_boto3_client.abort_multipart_upload.return_value = {}

    with patch("boto3.session.Session.client", return_value=mock_boto3_client):
        provider = S3R2StorageProvider(
            endpoint_url=None,
            bucket="test-bucket",
            access_key="test-key",
            secret_key="test-secret",
            region="us-east-1"
        )
        provider.client = mock_boto3_client

        upload_id = provider.initiate_multipart_upload("test.csv")
        assert upload_id == "s3-mock-upload-id"

        url = provider.create_presigned_part_url("test.csv", "s3-mock-upload-id", 1)
        assert url == "https://s3.amazonaws.com/test-url"

        comp = provider.complete_multipart_upload("test.csv", "s3-mock-upload-id", [{"PartNumber": 1, "ETag": "etag1"}])
        assert comp.get("Key") == "test.csv" or comp.get("key") == "test.csv" or "Location" in comp

        abort = provider.abort_multipart_upload("test.csv", "s3-mock-upload-id")
        assert abort is True
