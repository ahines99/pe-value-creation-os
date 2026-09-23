"""Evidence content store (PVC-032).

Originals are immutable: writing different bytes to an existing evidence id raises, and the file is marked
read-only. Derived text (for example, extracted document text) is stored separately and may be regenerated.
The filesystem backend is for dev and tests; production uses the S3 backend with versioning and Object Lock.
"""

from __future__ import annotations

import hashlib
import os
import stat
import time
import uuid
from pathlib import Path
from typing import Any, Protocol


class ImmutableEvidenceError(PermissionError):
    """Attempt to overwrite an evidence original with different content."""


class EvidenceNotFound(KeyError):
    pass


class EvidenceStore(Protocol):
    def put_original(self, company_id: str, evidence_id: str, content: bytes) -> str: ...

    def get_original(self, company_id: str, evidence_id: str) -> bytes: ...

    def put_derived(self, company_id: str, evidence_id: str, text: str) -> str: ...

    def get_derived(self, company_id: str, evidence_id: str) -> str | None: ...

    def delete_company(self, company_id: str) -> int: ...


def _safe(part: str) -> str:
    if not part or "/" in part or "\\" in part or part in {".", ".."}:
        raise ValueError(f"Unsafe path component {part!r}")
    return part


class FileSystemEvidenceStore:
    def __init__(self, root: Path | str):
        self.root = Path(root)

    def _dir(self, company_id: str, evidence_id: str) -> Path:
        return self.root / _safe(company_id) / _safe(evidence_id)

    def put_original(self, company_id: str, evidence_id: str, content: bytes) -> str:
        """Store an original once. Safe under concurrent writers: each writes a private temp file and publishes it
        with an atomic create-if-absent hard link, so exactly one writer wins and the others only verify."""
        d = self._dir(company_id, evidence_id)
        path = d / "original"
        rel = str(path.relative_to(self.root).as_posix())
        if path.exists():
            self._verify_same(path, content, evidence_id)
            return rel
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / f"original.{uuid.uuid4().hex}.tmp"
        tmp.write_bytes(content)
        try:
            os.link(tmp, path)  # fails if another writer published first; never overwrites
        except FileExistsError:
            tmp.unlink(missing_ok=True)
            self._verify_same(path, content, evidence_id)
            return rel
        # The temp name is a second link to the same file: drop it before making the file read-only (Windows
        # will not delete a read-only file).
        tmp.unlink(missing_ok=True)
        path.chmod(stat.S_IREAD | stat.S_IRGRP)
        return rel

    @staticmethod
    def _verify_same(path: Path, content: bytes, evidence_id: str) -> None:
        if hashlib.sha256(path.read_bytes()).digest() != hashlib.sha256(content).digest():
            raise ImmutableEvidenceError(f"Evidence {evidence_id} already stored with different content")

    def get_original(self, company_id: str, evidence_id: str) -> bytes:
        path = self._dir(company_id, evidence_id) / "original"
        if not path.exists():
            raise EvidenceNotFound(evidence_id)
        return path.read_bytes()

    def put_derived(self, company_id: str, evidence_id: str, text: str) -> str:
        d = self._dir(company_id, evidence_id)
        d.mkdir(parents=True, exist_ok=True)
        path = d / "derived.txt"
        tmp = d / f"derived.{uuid.uuid4().hex}.tmp"
        tmp.write_text(text, encoding="utf-8")
        for attempt in range(5):  # Windows refuses to replace a file another thread has open; retry briefly
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if attempt == 4:
                    tmp.unlink(missing_ok=True)
                    raise
                time.sleep(0.02 * (attempt + 1))
        return str(path.relative_to(self.root).as_posix())

    def get_derived(self, company_id: str, evidence_id: str) -> str | None:
        path = self._dir(company_id, evidence_id) / "derived.txt"
        return path.read_text(encoding="utf-8") if path.exists() else None

    def delete_company(self, company_id: str) -> int:
        """Offboarding deletion (PVC-144). Returns number of evidence items removed."""
        base = self.root / _safe(company_id)
        if not base.exists():
            return 0
        n = 0
        for d in base.iterdir():
            for f in d.iterdir():
                f.chmod(stat.S_IWRITE | stat.S_IREAD)
                f.unlink()
            d.rmdir()
            n += 1
        base.rmdir()
        return n


class S3EvidenceStore:
    """S3 backend. The bucket must have versioning and Object Lock (governance or compliance mode) enabled;
    see infra/terraform/modules/pvc/storage.tf. `client` is a boto3 S3 client (injected for testing)."""

    def __init__(self, bucket: str, client: Any = None, prefix: str = "evidence", kms_key_id: str | None = None):
        if client is None:  # pragma: no cover - requires boto3 and AWS credentials
            import boto3

            client = boto3.client("s3")
        self.bucket, self.client, self.prefix = bucket, client, prefix.strip("/")
        # With a key id, objects are encrypted with that customer-managed key; without one the bucket's default
        # encryption applies (never the AWS-managed aws/s3 key by accident).
        self._sse = {"ServerSideEncryption": "aws:kms", "SSEKMSKeyId": kms_key_id} if kms_key_id else {}

    def _key(self, company_id: str, evidence_id: str, name: str) -> str:
        return f"{self.prefix}/{_safe(company_id)}/{_safe(evidence_id)}/{name}"

    def put_original(self, company_id: str, evidence_id: str, content: bytes) -> str:
        key = self._key(company_id, evidence_id, "original")
        digest = hashlib.sha256(content).hexdigest()
        try:
            head = self.client.head_object(Bucket=self.bucket, Key=key)
        except self._client_error() as exc:
            if not self._is_missing(exc):
                raise  # access denied, throttling, KMS errors: never treat as "absent" and overwrite
        else:
            if head.get("Metadata", {}).get("sha256") != digest:
                raise ImmutableEvidenceError(f"Evidence {evidence_id} already stored with different content")
            return key
        self.client.put_object(Bucket=self.bucket, Key=key, Body=content, Metadata={"sha256": digest}, **self._sse)
        return key

    def _client_error(self) -> type[Exception]:
        exc = getattr(getattr(self.client, "exceptions", None), "ClientError", None)
        return exc if isinstance(exc, type) else KeyError

    @staticmethod
    def _is_missing(exc: Exception) -> bool:
        """True only for 'object does not exist' (HTTP 404); other client errors must propagate."""
        response = getattr(exc, "response", None)
        if not isinstance(response, dict):
            return isinstance(exc, KeyError)  # test doubles raise KeyError for a missing key
        code = str(response.get("Error", {}).get("Code", ""))
        return code in {"404", "NoSuchKey", "NotFound"}

    def get_original(self, company_id: str, evidence_id: str) -> bytes:
        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=self._key(company_id, evidence_id, "original"))
        except self._client_error() as e:
            if not self._is_missing(e):
                raise
            raise EvidenceNotFound(evidence_id) from e
        body: bytes = obj["Body"].read()
        return body

    def put_derived(self, company_id: str, evidence_id: str, text: str) -> str:
        key = self._key(company_id, evidence_id, "derived.txt")
        self.client.put_object(Bucket=self.bucket, Key=key, Body=text.encode("utf-8"), **self._sse)
        return key

    def get_derived(self, company_id: str, evidence_id: str) -> str | None:
        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=self._key(company_id, evidence_id, "derived.txt"))
        except self._client_error() as e:
            if not self._is_missing(e):
                raise
            return None
        data: bytes = obj["Body"].read()
        return data.decode("utf-8")

    def delete_company(self, company_id: str) -> int:
        prefix = f"{self.prefix}/{_safe(company_id)}/"
        n = 0
        paginator = self.client.get_paginator("list_object_versions")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for v in page.get("Versions", []) + page.get("DeleteMarkers", []):
                self.client.delete_object(
                    Bucket=self.bucket, Key=v["Key"], VersionId=v["VersionId"], BypassGovernanceRetention=True
                )
                n += 1
        return n
