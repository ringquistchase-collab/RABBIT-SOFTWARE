"""
Cold storage — S3 interface for long-term archival of sessions and artifacts.
Also bridges to Supabase Storage for existing RabbitOS bucket assets.
"""
import os
import json
import gzip
import hashlib
import logging
from datetime import datetime
from typing import Optional

log = logging.getLogger("memory.cold_storage")

S3_BUCKET     = os.getenv("S3_BUCKET",  "rabbitos-cold-storage")
S3_REGION     = os.getenv("S3_REGION",  "us-east-1")
S3_PREFIX     = os.getenv("S3_PREFIX",  "sessions")
SUPABASE_URL  = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY  = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

try:
    import boto3
    from botocore.exceptions import ClientError
    S3_AVAILABLE = True
except ImportError:
    S3_AVAILABLE = False
    log.warning("boto3 not installed — ColdStorage in mock mode")


class ColdStorage:
    """
    Archives sessions, task results, and artifacts to S3.
    Compresses with gzip; stores SHA3-256 manifest for integrity.
    """

    def __init__(self):
        if S3_AVAILABLE:
            self._s3 = boto3.client("s3", region_name=S3_REGION)
        else:
            self._s3      = None
            self._mock_store: dict[str, bytes] = {}

    # ── Write ──────────────────────────────────────────────────────────────────

    def archive_session(self, session_id: str, user_id: str,
                        tasks: list[dict], metadata: Optional[dict] = None) -> str:
        payload = {
            "session_id":  session_id,
            "user_id":     user_id,
            "archived_at": datetime.utcnow().isoformat() + "Z",
            "tasks":       tasks,
            "metadata":    metadata or {},
        }
        return self._put(f"{S3_PREFIX}/{user_id}/{session_id}/session.json.gz", payload)

    def archive_artifact(self, user_id: str, artifact_type: str,
                         artifact_id: str, data: dict) -> str:
        key = f"artifacts/{user_id}/{artifact_type}/{artifact_id}.json.gz"
        return self._put(key, data)

    def put_raw(self, key: str, content: bytes, content_type: str = "application/octet-stream") -> str:
        checksum = hashlib.sha3_256(content).hexdigest()
        if self._s3:
            self._s3.put_object(
                Bucket=S3_BUCKET,
                Key=key,
                Body=content,
                ContentType=content_type,
                Metadata={"sha3-256": checksum},
            )
        else:
            self._mock_store[key] = content
        log.debug("Stored %s (%d bytes) checksum=%s", key, len(content), checksum[:12])
        return checksum

    # ── Read ───────────────────────────────────────────────────────────────────

    def get_session(self, user_id: str, session_id: str) -> Optional[dict]:
        key = f"{S3_PREFIX}/{user_id}/{session_id}/session.json.gz"
        return self._get(key)

    def get_artifact(self, user_id: str, artifact_type: str,
                     artifact_id: str) -> Optional[dict]:
        key = f"artifacts/{user_id}/{artifact_type}/{artifact_id}.json.gz"
        return self._get(key)

    def list_sessions(self, user_id: str) -> list[str]:
        prefix = f"{S3_PREFIX}/{user_id}/"
        if self._s3:
            try:
                resp = self._s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=prefix, Delimiter="/")
                return [cp["Prefix"].replace(prefix, "").rstrip("/")
                        for cp in resp.get("CommonPrefixes", [])]
            except Exception as e:
                log.error("list_sessions failed: %s", e)
                return []
        return [k.replace(prefix, "").split("/")[0]
                for k in self._mock_store if k.startswith(prefix)]

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _put(self, key: str, data: dict) -> str:
        raw       = json.dumps(data, default=str).encode()
        compressed = gzip.compress(raw)
        return self.put_raw(key, compressed, "application/gzip")

    def _get(self, key: str) -> Optional[dict]:
        if self._s3:
            try:
                obj = self._s3.get_object(Bucket=S3_BUCKET, Key=key)
                return json.loads(gzip.decompress(obj["Body"].read()))
            except Exception:
                return None
        raw = self._mock_store.get(key)
        if raw:
            return json.loads(gzip.decompress(raw))
        return None

    def stats(self) -> dict:
        if self._s3:
            return {"backend": "s3", "bucket": S3_BUCKET, "region": S3_REGION}
        return {"backend": "mock", "objects": len(self._mock_store)}
