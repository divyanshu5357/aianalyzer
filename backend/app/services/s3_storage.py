"""
Storage service adapter delegating to ObjectStorageProvider.
Ensures provider-agnostic execution for R2, S3, MinIO, and Local storage fallback.
"""
import logging
from typing import Optional
from app.storage.service import get_storage_provider

logger = logging.getLogger(__name__)


def generate_upload_url(
    object_key: str,
    content_type: str,
    expires_in: int = 3600,
) -> str:
    provider = get_storage_provider()
    res = provider.create_presigned_upload_url(object_key, expires_in=expires_in, content_type=content_type)
    return res.get("url", "")


def download_file(object_key: str, local_path: str) -> None:
    provider = get_storage_provider()
    ok = provider.download_file(object_key, local_path)
    if not ok:
        raise ValueError(f"Failed to download object storage key: {object_key}")


def delete_file(object_key: str) -> None:
    provider = get_storage_provider()
    provider.delete_object(object_key)


def check_object_exists(object_key: str) -> bool:
    provider = get_storage_provider()
    return provider.exists(object_key)


def initiate_multipart_upload(object_key: str, content_type: Optional[str] = None) -> str:
    provider = get_storage_provider()
    return provider.initiate_multipart_upload(object_key, content_type=content_type)


def create_presigned_part_url(
    object_key: str, upload_id: str, part_number: int, expires_in: int = 3600
) -> str:
    provider = get_storage_provider()
    return provider.create_presigned_part_url(object_key, upload_id, part_number, expires_in=expires_in)


def complete_multipart_upload(object_key: str, upload_id: str, parts: list[dict]) -> dict:
    provider = get_storage_provider()
    return provider.complete_multipart_upload(object_key, upload_id, parts)


def abort_multipart_upload(object_key: str, upload_id: str) -> bool:
    provider = get_storage_provider()
    return provider.abort_multipart_upload(object_key, upload_id)