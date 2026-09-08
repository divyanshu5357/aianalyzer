"""
Cloudflare R2 / AWS S3 Compatible Object Storage Provider.
Uses boto3 to interact with any S3-compatible API.
Credentials are server-side only and never exposed to the frontend.
"""
import io
import logging
from typing import Any, BinaryIO, Dict, Iterator, Optional

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.storage.base import ObjectStorageProvider

logger = logging.getLogger(__name__)


class S3R2StorageProvider(ObjectStorageProvider):
    def __init__(
        self,
        endpoint_url: Optional[str],
        bucket: str,
        access_key: Optional[str],
        secret_key: Optional[str],
        region: str = "auto",
        public_url: Optional[str] = None,
    ):
        self.bucket = bucket
        self.public_url = public_url

        session = boto3.session.Session()
        self.client = session.client(
            service_name="s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region or "auto",
            config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
        )

    def put_object(
        self,
        key: str,
        data: bytes | BinaryIO,
        content_type: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> bool:
        try:
            extra_args: Dict[str, Any] = {}
            if content_type:
                extra_args["ContentType"] = content_type
            if metadata:
                extra_args["Metadata"] = metadata

            if isinstance(data, bytes):
                self.client.put_object(Bucket=self.bucket, Key=key, Body=data, **extra_args)
            else:
                self.client.upload_fileobj(Fileobj=data, Bucket=self.bucket, Key=key, ExtraArgs=extra_args)
            return True
        except ClientError as e:
            logger.error("Failed to put_object key=%s: %s", key, e)
            return False

    def get_object(self, key: str) -> bytes:
        try:
            res = self.client.get_object(Bucket=self.bucket, Key=key)
            return res["Body"].read()
        except ClientError as e:
            logger.error("Failed to get_object key=%s: %s", key, e)
            raise FileNotFoundError(f"Object {key} not found in storage.") from e

    def stream_object(self, key: str, chunk_size: int = 65536) -> Iterator[bytes]:
        try:
            res = self.client.get_object(Bucket=self.bucket, Key=key)
            stream = res["Body"]
            while True:
                chunk = stream.read(chunk_size)
                if not chunk:
                    break
                yield chunk
        except ClientError as e:
            logger.error("Failed to stream_object key=%s: %s", key, e)
            raise FileNotFoundError(f"Object {key} not found in storage.") from e

    def download_file(self, key: str, local_path: str) -> bool:
        try:
            self.client.download_file(self.bucket, key, local_path)
            return True
        except ClientError as e:
            logger.error("Failed to download_file key=%s to %s: %s", key, local_path, e)
            return False

    def delete_object(self, key: str) -> bool:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as e:
            logger.error("Failed to delete_object key=%s: %s", key, e)
            return False

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False

    def get_metadata(self, key: str) -> Dict[str, Any]:
        try:
            res = self.client.head_object(Bucket=self.bucket, Key=key)
            return {
                "size": res.get("ContentLength", 0),
                "content_type": res.get("ContentType"),
                "last_modified": res.get("LastModified").isoformat() if res.get("LastModified") else None,
                "metadata": res.get("Metadata", {}),
            }
        except ClientError as e:
            logger.error("Failed to get_metadata key=%s: %s", key, e)
            return {"size": 0, "metadata": {}}

    def create_presigned_upload_url(
        self, key: str, expires_in: int = 3600, content_type: Optional[str] = None
    ) -> Dict[str, Any]:
        try:
            params = {"Bucket": self.bucket, "Key": key}
            if content_type:
                params["ContentType"] = content_type

            url = self.client.generate_presigned_url(
                "put_object",
                Params=params,
                ExpiresIn=expires_in,
            )
            return {
                "url": url,
                "method": "PUT",
                "headers": {"Content-Type": content_type} if content_type else {},
                "key": key,
            }
        except ClientError as e:
            logger.error("Failed to generate presigned upload URL for key=%s: %s", key, e)
            raise

    def create_presigned_download_url(self, key: str, expires_in: int = 3600) -> str:
        try:
            return self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expires_in,
            )
        except ClientError as e:
            logger.error("Failed to generate presigned download URL for key=%s: %s", key, e)
            raise
