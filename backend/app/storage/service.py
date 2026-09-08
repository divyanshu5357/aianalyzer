"""
Storage Provider Factory Service.
Returns the configured object storage provider (S3, R2, or Local fallback).
"""
import logging
from typing import Optional, Any, Dict

from app.config.settings import settings
from app.storage.base import ObjectStorageProvider
from app.storage.local_provider import LocalStorageProvider
from app.storage.s3_r2_provider import S3R2StorageProvider

logger = logging.getLogger(__name__)

_PROVIDER_INSTANCE: Optional[ObjectStorageProvider] = None


def get_storage_provider() -> ObjectStorageProvider:
    """
    Factory returning the active ObjectStorageProvider instance.
    Defaults to S3R2StorageProvider if endpoint & credentials exist,
    otherwise falls back cleanly to LocalStorageProvider.
    """
    global _PROVIDER_INSTANCE
    if _PROVIDER_INSTANCE is not None:
        return _PROVIDER_INSTANCE

    provider_type = (settings.storage_provider or "local").lower()

    if provider_type in ("r2", "s3") or settings.storage_endpoint_url or settings.storage_access_key:
        try:
            _PROVIDER_INSTANCE = S3R2StorageProvider(
                endpoint_url=settings.storage_endpoint_url,
                bucket=settings.storage_bucket,
                access_key=settings.storage_access_key,
                secret_key=settings.storage_secret_key,
                region=settings.storage_region,
                public_url=settings.storage_public_url,
            )
            logger.info("Initialized S3/R2 storage provider for bucket=%s", settings.storage_bucket)
            return _PROVIDER_INSTANCE
        except Exception as e:
            logger.warning("Failed to initialize S3/R2 provider, falling back to LocalStorageProvider: %s", e)

    _PROVIDER_INSTANCE = LocalStorageProvider()
    logger.info("Initialized LocalStorageProvider fallback.")
    return _PROVIDER_INSTANCE


def reset_storage_provider():
    """Reset cached singleton instance (useful for unit testing)."""
    global _PROVIDER_INSTANCE
    _PROVIDER_INSTANCE = None


class StorageService:
    """
    Production Storage Service abstraction wrapping active ObjectStorageProvider.
    Supports S3, R2, and local fallback without hardcoded paths or bucket names.
    """

    def __init__(self, provider: Optional[ObjectStorageProvider] = None):
        self.provider = provider or get_storage_provider()

    def put_file(
        self,
        key: str,
        data_or_path: Any,
        content_type: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> bool:
        """Upload a file or raw bytes to storage."""
        if isinstance(data_or_path, (bytes, bytearray)):
            return self.provider.put_object(key, data_or_path, content_type=content_type, metadata=metadata)
        elif hasattr(data_or_path, "read"):
            return self.provider.put_object(key, data_or_path, content_type=content_type, metadata=metadata)
        elif isinstance(data_or_path, str):
            with open(data_or_path, "rb") as f:
                return self.provider.put_object(key, f, content_type=content_type, metadata=metadata)
        return False

    def get_file(self, key: str, target_local_path: Optional[str] = None) -> Any:
        """Download an object to target local path, or return raw bytes if no path provided."""
        if target_local_path:
            return self.provider.download_file(key, target_local_path)
        return self.provider.get_object(key)

    def delete_file(self, key: str) -> bool:
        """Delete an object from storage."""
        return self.provider.delete_object(key)

    def exists(self, key: str) -> bool:
        """Check if an object exists in storage."""
        return self.provider.exists(key)

    def get_signed_url(
        self,
        key: str,
        expires_in: int = 3600,
        operation: str = "download",
        content_type: Optional[str] = None,
    ) -> str:
        """Generate a presigned URL for upload or download."""
        if operation == "upload":
            res = self.provider.create_presigned_upload_url(
                key, expires_in=expires_in, content_type=content_type
            )
            return res.get("url", "")
        return self.provider.create_presigned_download_url(key, expires_in=expires_in)

