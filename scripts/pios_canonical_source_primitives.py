"""Owner-neutral, local-only source primitives for future synthetic adapters.

This module deliberately has no network client, credential, owner identity,
application adapter, service activation, or provider-specific storage code.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

SOURCE_EVIDENCE_SCHEMA = "pios_canonical_source_evidence_v1"
SOURCE_IDENTITY_SCHEMA = "pios_canonical_source_identity_v1"
IDEMPOTENCY_SCHEMA = "pios_canonical_source_idempotency_v1"
CORE_COLLECTIONS = frozenset({"events", "originals", "knowledge", "derived", "system"})
IDENTIFIER_RE = re.compile(r"[a-z][a-z0-9-]{0,62}")
STABLE_SOURCE_ID_RE = re.compile(r"src_[0-9a-f]{64}")
LOGICAL_REFERENCE_NAME_RE = re.compile(r"[a-z][a-z0-9_]{0,62}")
CORE_SEGMENT_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")


class SourcePrimitiveError(ValueError):
    """Base error for invalid generic source data."""


class IntegrityError(SourcePrimitiveError):
    """Raised when a digest or byte-count binding does not verify."""


class LogicalReferenceError(SourcePrimitiveError):
    """Raised for malformed or non-canonical logical references."""


class ImmutableEvidenceConflict(SourcePrimitiveError):
    """Raised when a stable source identity attempts to change retained content."""


def _canonical_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        raise SourcePrimitiveError("canonical JSON does not accept float values; encode decimals as strings")
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise SourcePrimitiveError("canonical JSON object keys must be strings")
            normalized[key] = _canonical_value(item)
        return normalized
    raise SourcePrimitiveError(f"canonical JSON does not accept {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    """Return strict, repeatable UTF-8 JSON bytes for supported JSON values."""
    return json.dumps(
        _canonical_value(value),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_json_value(value: Any) -> Any:
    """Return a JSON-round-tripped immutable-by-convention copy of a value."""
    return json.loads(canonical_json_bytes(value).decode("utf-8"))


def sha256_bytes(value: bytes) -> str:
    if not isinstance(value, bytes):
        raise SourcePrimitiveError("SHA-256 input must be bytes")
    return hashlib.sha256(value).hexdigest()


def integrity_for_bytes(value: bytes) -> dict[str, Any]:
    return {"sha256": sha256_bytes(value), "byte_count": len(value)}


def validate_integrity(integrity: Mapping[str, Any]) -> dict[str, Any]:
    digest = integrity.get("sha256")
    byte_count = integrity.get("byte_count")
    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        raise IntegrityError("sha256 must be exactly 64 lowercase hexadecimal characters")
    if not isinstance(byte_count, int) or isinstance(byte_count, bool) or byte_count < 0:
        raise IntegrityError("byte_count must be a non-negative integer")
    return {"sha256": digest, "byte_count": byte_count}


def verify_bytes(value: bytes, integrity: Mapping[str, Any]) -> dict[str, Any]:
    expected = validate_integrity(integrity)
    actual = integrity_for_bytes(value)
    if actual != expected:
        raise IntegrityError(
            f"integrity mismatch: expected sha256={expected['sha256']} byte_count={expected['byte_count']}, "
            f"got sha256={actual['sha256']} byte_count={actual['byte_count']}"
        )
    return actual


def _validate_identifier(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER_RE.fullmatch(value):
        raise SourcePrimitiveError(f"{field} must be 1-63 lowercase letters, digits, or hyphens")
    return value


def _validate_native_record_id(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 512:
        raise SourcePrimitiveError("source_native_record_id must be a non-empty string of at most 512 characters")
    if any(ord(character) < 32 for character in value):
        raise SourcePrimitiveError("source_native_record_id must not contain control characters")
    return value


def derive_stable_source_record_id(integration_id: str, source_native_record_id: str) -> str:
    """Derive an opaque stable identity without exposing a native source ID in paths."""
    identity = {
        "schema_version": SOURCE_IDENTITY_SCHEMA,
        "integration_id": _validate_identifier(integration_id, field="integration_id"),
        "source_native_record_id": _validate_native_record_id(source_native_record_id),
    }
    return f"src_{sha256_bytes(canonical_json_bytes(identity))}"


def derive_idempotency_key(
    stable_source_record_id: str, payload_integrity: Mapping[str, Any]
) -> str:
    if not isinstance(stable_source_record_id, str) or not STABLE_SOURCE_ID_RE.fullmatch(
        stable_source_record_id
    ):
        raise SourcePrimitiveError("stable_source_record_id must be a canonical src_ SHA-256 identifier")
    identity = {
        "schema_version": IDEMPOTENCY_SCHEMA,
        "stable_source_record_id": stable_source_record_id,
        "payload_integrity": validate_integrity(payload_integrity),
    }
    return f"idem_{sha256_bytes(canonical_json_bytes(identity))}"


def build_core_ref(collection: str, *segments: str) -> str:
    collection = _validate_identifier(collection, field="core collection")
    if collection not in CORE_COLLECTIONS:
        raise LogicalReferenceError(f"unsupported core collection: {collection}")
    if not segments:
        raise LogicalReferenceError("core reference requires at least one path segment")
    checked_segments: list[str] = []
    for segment in segments:
        if not isinstance(segment, str) or not CORE_SEGMENT_RE.fullmatch(segment):
            raise LogicalReferenceError("core reference segments must be canonical lowercase path tokens")
        checked_segments.append(segment)
    return f"core://{collection}/{'/'.join(checked_segments)}"


def validate_core_ref(reference: str) -> str:
    if not isinstance(reference, str):
        raise LogicalReferenceError("core reference must be a string")
    parsed = urlsplit(reference)
    if parsed.scheme != "core" or not parsed.netloc:
        raise LogicalReferenceError("logical references must use core://")
    if parsed.query or parsed.fragment or parsed.username or parsed.password or ":" in parsed.netloc:
        raise LogicalReferenceError("core references must not contain query, fragment, user, or port components")
    collection = parsed.netloc
    if collection not in CORE_COLLECTIONS:
        raise LogicalReferenceError(f"unsupported core collection: {collection}")
    segments = parsed.path.split("/")[1:]
    if not segments or any(not CORE_SEGMENT_RE.fullmatch(segment) for segment in segments):
        raise LogicalReferenceError("core references must have canonical lowercase path segments")
    canonical = build_core_ref(collection, *segments)
    if reference != canonical:
        raise LogicalReferenceError("core reference is not in canonical form")
    return canonical


def validate_logical_references(references: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(references, Mapping):
        raise LogicalReferenceError("logical_references must be an object")
    validated: dict[str, str] = {}
    for name, reference in references.items():
        if not isinstance(name, str) or not LOGICAL_REFERENCE_NAME_RE.fullmatch(name):
            raise LogicalReferenceError("logical reference names must use lowercase letters, digits, or underscores")
        validated[name] = validate_core_ref(reference)
    return dict(sorted(validated.items()))


def _contains_core_reference(value: Any) -> bool:
    if isinstance(value, str):
        return value.startswith("core://")
    if isinstance(value, list):
        return any(_contains_core_reference(item) for item in value)
    if isinstance(value, Mapping):
        return any(_contains_core_reference(item) for item in value.values())
    return False


def preserve_extensions(extensions: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(extensions, Mapping):
        raise SourcePrimitiveError("extensions must be an object")
    return canonical_json_value(extensions)


def validate_source_provenance(provenance: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(provenance, Mapping):
        raise SourcePrimitiveError("source_provenance must be an object")
    preserved = canonical_json_value(provenance)
    if _contains_core_reference(preserved):
        raise LogicalReferenceError(
            "core:// references belong in logical_references, not source_provenance"
        )
    return preserved


def build_source_evidence(
    *,
    integration_id: str,
    source_native_record_id: str,
    payload: Mapping[str, Any],
    original_bytes: bytes,
    logical_references: Mapping[str, Any],
    source_provenance: Mapping[str, Any],
    extensions: Mapping[str, Any],
) -> dict[str, Any]:
    integration_id = _validate_identifier(integration_id, field="integration_id")
    source_native_record_id = _validate_native_record_id(source_native_record_id)
    if not isinstance(payload, Mapping):
        raise SourcePrimitiveError("payload must be an object")
    payload_value = canonical_json_value(payload)
    payload_integrity = integrity_for_bytes(canonical_json_bytes(payload_value))
    stable_source_record_id = derive_stable_source_record_id(
        integration_id, source_native_record_id
    )
    return {
        "schema_version": SOURCE_EVIDENCE_SCHEMA,
        "integration_id": integration_id,
        "source_native_record_id": source_native_record_id,
        "stable_source_record_id": stable_source_record_id,
        "idempotency_key": derive_idempotency_key(stable_source_record_id, payload_integrity),
        "payload": payload_value,
        "payload_integrity": payload_integrity,
        "original_integrity": integrity_for_bytes(original_bytes),
        "logical_references": validate_logical_references(logical_references),
        "source_provenance": validate_source_provenance(source_provenance),
        "extensions": preserve_extensions(extensions),
    }


def validate_source_evidence(record: Mapping[str, Any], original_bytes: bytes) -> dict[str, Any]:
    if not isinstance(record, Mapping) or record.get("schema_version") != SOURCE_EVIDENCE_SCHEMA:
        raise SourcePrimitiveError(f"record.schema_version must be {SOURCE_EVIDENCE_SCHEMA}")
    expected = build_source_evidence(
        integration_id=record.get("integration_id"),
        source_native_record_id=record.get("source_native_record_id"),
        payload=record.get("payload"),
        original_bytes=original_bytes,
        logical_references=record.get("logical_references"),
        source_provenance=record.get("source_provenance"),
        extensions=record.get("extensions"),
    )
    for field in (
        "stable_source_record_id",
        "idempotency_key",
        "payload_integrity",
        "original_integrity",
        "logical_references",
        "source_provenance",
        "extensions",
    ):
        if record.get(field) != expected[field]:
            raise IntegrityError(f"source evidence field does not match canonical binding: {field}")
    return expected


def _write_immutable(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if path.read_bytes() != content:
            raise ImmutableEvidenceConflict(f"immutable content already differs: {path.name}")
        return
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content)


class LocalSyntheticEvidenceStore:
    """A temporary local immutable store for harmless generated source fixtures."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _original_path(self, digest: str) -> Path:
        return self.root / "originals" / f"{digest}.bin"

    def _evidence_path(self, stable_source_record_id: str) -> Path:
        return self.root / "evidence" / f"{stable_source_record_id}.json"

    def retain(self, record: Mapping[str, Any], original_bytes: bytes) -> dict[str, Any]:
        canonical_record = validate_source_evidence(record, original_bytes)
        original_digest = canonical_record["original_integrity"]["sha256"]
        stable_id = canonical_record["stable_source_record_id"]
        evidence_bytes = canonical_json_bytes(canonical_record)
        evidence_path = self._evidence_path(stable_id)
        if evidence_path.exists():
            if evidence_path.read_bytes() != evidence_bytes:
                raise ImmutableEvidenceConflict(
                    "stable source identity already has different immutable evidence"
                )
            verify_bytes(self._original_path(original_digest).read_bytes(), canonical_record["original_integrity"])
            status = "duplicate"
        else:
            _write_immutable(self._original_path(original_digest), original_bytes)
            _write_immutable(evidence_path, evidence_bytes)
            status = "accepted"
        return {
            "status": status,
            "stable_source_record_id": stable_id,
            "idempotency_key": canonical_record["idempotency_key"],
            "original_ref": build_core_ref("originals", original_digest),
            "evidence_ref": build_core_ref("system", "synthetic-evidence", stable_id),
        }

    def read_evidence(self, stable_source_record_id: str) -> dict[str, Any]:
        if not isinstance(stable_source_record_id, str) or not STABLE_SOURCE_ID_RE.fullmatch(
            stable_source_record_id
        ):
            raise SourcePrimitiveError("stable_source_record_id must be a canonical src_ SHA-256 identifier")
        return json.loads(self._evidence_path(stable_source_record_id).read_text())
