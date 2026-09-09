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
        clean_endpoint = endpoint_url.strip() if endpoint_url and endpoint_url.strip() else None
        effective_region = None if (region in ("auto", "", None) and not clean_endpoint) else (region or "auto")

        client_kwargs: Dict[str, Any] = {
            "service_name": "s3",
            "config": Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
        }
        if clean_endpoint:
            client_kwargs["endpoint_url"] = clean_endpoint
        if access_key and secret_key:
            client_kwargs["aws_access_key_id"] = access_key
            client_kwargs["aws_secret_access_key"] = secret_key
        if effective_region:
            client_kwargs["region_name"] = effective_region

        self.client = session.client(**client_kwargs)

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

    def initiate_multipart_upload(self, key: str, content_type: Optional[str] = None) -> str:
        params: Dict[str, Any] = {"Bucket": self.bucket, "Key": key}
        if content_type:
            params["ContentType"] = content_type
        res = self.client.create_multipart_upload(**params)
        return res["UploadId"]

    def create_presigned_part_url(
        self, key: str, upload_id: str, part_number: int, expires_in: int = 3600
    ) -> str:
        return self.client.generate_presigned_url(
            "upload_part",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "UploadId": upload_id,
                "PartNumber": part_number,
            },
            ExpiresIn=expires_in,
        )

    def complete_multipart_upload(self, key: str, upload_id: str, parts: list[dict]) -> dict:
        formatted_parts = []
        for p in parts:
            part_num = p.get("PartNumber") if p.get("PartNumber") is not None else p.get("part_number")
            raw_etag = p.get("ETag") or p.get("etag") or ""
            if part_num is not None:
                # AWS S3 requires ETag to be quoted if not already
                etag = str(raw_etag).strip()
                if not etag.startswith('"'):
                    etag = f'"{etag}"'
                formatted_parts.append({"PartNumber": int(part_num), "ETag": etag})
        formatted_parts.sort(key=lambda x: x["PartNumber"])
        return self.client.complete_multipart_upload(
            Bucket=self.bucket,
            Key=key,
            UploadId=upload_id,
            MultipartUpload={"Parts": formatted_parts},
        )

    def abort_multipart_upload(self, key: str, upload_id: str) -> bool:
        try:
            self.client.abort_multipart_upload(
                Bucket=self.bucket,
                Key=key,
                UploadId=upload_id,
            )
            return True
        except Exception as e:
            logger.warning("Failed to abort multipart upload for key=%s upload_id=%s: %s", key, upload_id, e)
            return False
