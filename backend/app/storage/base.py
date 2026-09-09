"""
Abstract Base Interface for Object Storage Providers.

Supports Cloudflare R2, AWS S3, MinIO, Wasabi, DigitalOcean Spaces,
and local disk fallback.
"""
from abc import ABC, abstractmethod
from typing import Any, BinaryIO, Dict, Iterator, Optional


class ObjectStorageProvider(ABC):
    """Abstract Object Storage Interface."""

    @abstractmethod
    def put_object(
        self,
        key: str,
        data: bytes | BinaryIO,
        content_type: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> bool:
        """Upload an object to storage."""
        pass

    @abstractmethod
    def get_object(self, key: str) -> bytes:
        """Retrieve an object's raw bytes."""
        pass

    @abstractmethod
    def stream_object(self, key: str, chunk_size: int = 65536) -> Iterator[bytes]:
        """Stream an object in chunks to conserve memory."""
        pass

    @abstractmethod
    def download_file(self, key: str, local_path: str) -> bool:
        """Download an object to a local file path."""
        pass

    @abstractmethod
    def delete_object(self, key: str) -> bool:
        """Delete an object from storage."""
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if an object exists in storage."""
        pass

    @abstractmethod
    def get_metadata(self, key: str) -> Dict[str, Any]:
        """Get object metadata and size."""
        pass

    @abstractmethod
    def create_presigned_upload_url(
        self, key: str, expires_in: int = 3600, content_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate presigned upload URL or upload parameters."""
        pass

    @abstractmethod
    def create_presigned_download_url(self, key: str, expires_in: int = 3600) -> str:
        """Generate presigned download URL."""
        pass

    @abstractmethod
    def initiate_multipart_upload(self, key: str, content_type: Optional[str] = None) -> str:
        """Initiate multipart upload and return upload_id."""
        pass

    @abstractmethod
    def create_presigned_part_url(
        self, key: str, upload_id: str, part_number: int, expires_in: int = 3600
    ) -> str:
        """Generate presigned upload URL for a specific part number."""
        pass

    @abstractmethod
    def complete_multipart_upload(self, key: str, upload_id: str, parts: list[dict]) -> dict:
        """Complete multipart upload with list of uploaded parts [{PartNumber, ETag}]."""
        pass

    @abstractmethod
    def abort_multipart_upload(self, key: str, upload_id: str) -> bool:
        """Abort multipart upload and discard uploaded parts."""
        pass
