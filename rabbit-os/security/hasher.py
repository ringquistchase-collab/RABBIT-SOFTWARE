import hashlib
import json
from typing import Any, Dict


def hash_event(data: Dict[str, Any]) -> str:
    serialized = json.dumps(data, sort_keys=True, default=str).encode()
    return hashlib.sha256(serialized).hexdigest()


def hash_string(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
