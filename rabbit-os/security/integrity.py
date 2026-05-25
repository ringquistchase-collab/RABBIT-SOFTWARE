"""
Integrity verification — chain-of-custody checks for ingested events.
"""
import hashlib
import hmac
from typing import Any, Dict

from core.config import cfg


def sign_payload(payload: Dict[str, Any]) -> str:
    import json
    body = json.dumps(payload, sort_keys=True, default=str).encode()
    return hmac.new(cfg.SECRET_KEY.encode(), body, hashlib.sha256).hexdigest()


def verify_signature(payload: Dict[str, Any], signature: str) -> bool:
    expected = sign_payload(payload)
    return hmac.compare_digest(expected, signature)


def integrity_check(record: Dict[str, Any]) -> bool:
    """Re-hash event data and compare to stored hash."""
    import json
    data   = record.get("data", {})
    stored = record.get("hash", "")
    actual = hashlib.sha256(
        json.dumps(data, sort_keys=True, default=str).encode()
    ).hexdigest()
    return hmac.compare_digest(stored, actual) if stored else False
