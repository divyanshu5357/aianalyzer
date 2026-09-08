"""
Local Disk Storage Provider.
Fallback provider writing to data/storage/ for offline development and testing.
Provides the exact same ObjectStorageProvider API contract as S3/R2.
"""
import io
import os
import shutil
from pathlib import Path
from typing import Any, BinaryIO, Dict, Iterator, Optional

from app.storage.base import ObjectStorageProvider


class LocalStorageProvider(ObjectStorageProvider):
    def __init__(self, base_dir: str = "data/storage"):
        self.base_path = Path(base_dir)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, key: str) -> Path:
        if ".." in key or "\\" in key:
            raise ValueError(f"Path traversal blocked for key: {key}")
        safe_key = key.lstrip("/")
        full_path = (self.base_path / safe_key).resolve()
        if not str(full_path).startswith(str(self.base_path.resolve())):
            raise ValueError(f"Path traversal blocked for key: {key}")
        return full_path

    def put_object(
        self,
        key: str,
        data: bytes | BinaryIO,
        content_type: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> bool:
        path = self._resolve_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(data, bytes):
            with path.open("wb") as f:
                f.write(data)
        else:
            with path.open("wb") as f:
                shutil.copyfileobj(data, f)
        return True

    def get_object(self, key: str) -> bytes:
        path = self._resolve_path(key)
        if not path.exists():
            raise FileNotFoundError(f"Object {key} not found in local storage.")
        with path.open("rb") as f:
            return f.read()

    def stream_object(self, key: str, chunk_size: int = 65536) -> Iterator[bytes]:
        path = self._resolve_path(key)
        if not path.exists():
            raise FileNotFoundError(f"Object {key} not found in local storage.")
        with path.open("rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    def download_file(self, key: str, local_path: str) -> bool:
        src = self._resolve_path(key)
        if not src.exists():
            return False
        dest = Path(local_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return True

    def delete_object(self, key: str) -> bool:
        path = self._resolve_path(key)
        if path.exists():
            path.unlink()
            return True
        return False

    def exists(self, key: str) -> bool:
        path = self._resolve_path(key)
        return path.exists() and path.is_file()

    def get_metadata(self, key: str) -> Dict[str, Any]:
        path = self._resolve_path(key)
        if not path.exists():
            return {"size": 0, "metadata": {}}
        stat = path.stat()
        return {
            "size": stat.st_size,
            "content_type": "application/octet-stream",
            "last_modified": stat.st_mtime,
            "metadata": {},
        }

    def create_presigned_upload_url(
        self, key: str, expires_in: int = 3600, content_type: Optional[str] = None
    ) -> Dict[str, Any]:
        import urllib.parse
        encoded_key = urllib.parse.quote(key, safe="/")
        return {
            "url": f"/api/data/upload/storage-direct?key={encoded_key}",
            "method": "PUT",
            "headers": {"Content-Type": content_type} if content_type else {},
            "key": key,
        }

    def create_presigned_download_url(self, key: str, expires_in: int = 3600) -> str:
        import urllib.parse
        encoded_key = urllib.parse.quote(key, safe="/")
        return f"/api/data/upload/storage-direct?key={encoded_key}"
