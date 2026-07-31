"""Generic, local-only synthetic source-ingress contract for C1 review.

This module intentionally provides no listener, endpoint, credential, device
enrollment, application transport, or personal-data handling. It projects a
validated B2 candidate into a strict path-free synthetic envelope, then uses
the existing local B2 lifecycle only for generated harmless fixtures.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from scripts import pios_canonical_source_primitives as primitives
from scripts import pios_generic_source_lifecycle as lifecycle

ENVELOPE_SCHEMA = "pios_synthetic_source_ingress_envelope_v1"
RECEIPT_SCHEMA = "pios_synthetic_source_ingress_receipt_v1"
PROFILE = "pios_synthetic_source_ingress_v1"
SYNTHETIC_DATA_CLASS = "synthetic_normal"
SYNTHETIC_PERMISSION = "synthetic_allowed"
SYNTHETIC_LIFECYCLE = "synthetic_prepared"
SYNTHETIC_TRANSPORT = "synthetic_local_projection"
INGRESS_INDEX_SCHEMA = "pios_synthetic_source_ingress_index_v1"

TOKEN_RE = re.compile(r"[a-z][a-z0-9_-]{0,127}")
VERSION_RE = re.compile(r"[0-9A-Za-z][0-9A-Za-z._+-]{0,127}")
EVENT_TYPE_RE = re.compile(r"[a-z][a-z0-9_.-]{0,127}")
UTC_TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
FORBIDDEN_TRANSPORT_KEYS = frozenset(
    {
        "path",
        "manifest_path",
        "item_manifest_path",
        "bookmark",
        "endpoint",
        "url",
        "credential",
        "api_key",
        "token",
        "password",
        "owner_comment",
        "comment",
    }
)


class SyntheticIngressError(ValueError):
    """Raised when a synthetic-only envelope or receipt violates C1 bindings."""


class SyntheticReceiptMismatch(SyntheticIngressError):
    """Raised when a receipt is not fully bound to its synthetic envelope."""


class RetryBindingMismatch(SyntheticIngressError):
    """Raised when a retry changes its canonical envelope or idempotency key."""


def _canonical_timestamp(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not UTC_TIMESTAMP_RE.fullmatch(value):
        raise SyntheticIngressError(f"{field} must be RFC3339 UTC seconds ending in Z")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SyntheticIngressError(f"{field} is not a valid UTC timestamp") from exc
    return value


def _token(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not TOKEN_RE.fullmatch(value):
        raise SyntheticIngressError(f"{field} must be a synthetic-safe lowercase token")
    return value


def _version(value: Any) -> str:
    if not isinstance(value, str) or not VERSION_RE.fullmatch(value):
        raise SyntheticIngressError("integration_version must be a bounded version token")
    return value


def _event_type(value: Any) -> str:
    if not isinstance(value, str) or not EVENT_TYPE_RE.fullmatch(value) or not value.endswith(".prepared"):
        raise SyntheticIngressError("event_type must be a canonical synthetic *.prepared event")
    return value


def _reject_transport_unsafe(value: Any, *, field: str = "envelope") -> None:
    if isinstance(value, str):
        lowered = value.lower()
        if (
            value.startswith(("/", "~", "\\"))
            or "\\" in value
            or "://" in value
            or lowered.startswith(("file:", "s3:", "core:"))
        ):
            raise SyntheticIngressError(f"{field} contains a forbidden path, provider, or logical reference")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _reject_transport_unsafe(item, field=f"{field}[{index}]")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise SyntheticIngressError(f"{field} keys must be strings")
            if key.lower() in FORBIDDEN_TRANSPORT_KEYS:
                raise SyntheticIngressError(f"{field} contains forbidden local or credential field: {key}")
            _reject_transport_unsafe(item, field=f"{field}.{key}")


def validate_synthetic_provenance(value: Mapping[str, Any]) -> dict[str, str]:
    """Accept only a small, path-free provenance projection for synthetic ingress."""
    if not isinstance(value, Mapping) or set(value) != {"fixture_class", "source_shape", "transport"}:
        raise SyntheticIngressError("synthetic provenance must contain only fixture_class, source_shape, and transport")
    normalized = {
        "fixture_class": value.get("fixture_class"),
        "source_shape": value.get("source_shape"),
        "transport": value.get("transport"),
    }
    if normalized["fixture_class"] != "generated_harmless":
        raise SyntheticIngressError("synthetic provenance fixture_class must be generated_harmless")
    normalized["source_shape"] = _token(normalized["source_shape"], field="source_provenance.source_shape")
    if normalized["transport"] != SYNTHETIC_TRANSPORT:
        raise SyntheticIngressError("synthetic provenance transport must be synthetic_local_projection")
    _reject_transport_unsafe(normalized, field="source_provenance")
    return normalized


def _envelope_binding(envelope: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in envelope.items() if key != "envelope_integrity"}


def _envelope_integrity(envelope: Mapping[str, Any]) -> dict[str, Any]:
    return primitives.integrity_for_bytes(primitives.canonical_json_bytes(_envelope_binding(envelope)))


def _project_candidate(
    source_candidate: Mapping[str, Any],
    original_bytes: bytes,
    *,
    source_provenance: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the distinct, path-free B2 candidate used by the transport projection."""
    source = lifecycle.validate_source_candidate(source_candidate, original_bytes)
    safe_provenance = validate_synthetic_provenance(source_provenance)
    _reject_transport_unsafe(source["evidence"]["payload"], field="payload")
    _reject_transport_unsafe(source["processing_manifest"], field="processing_manifest")
    _reject_transport_unsafe(source["evidence"]["extensions"], field="extensions")
    return lifecycle.build_source_candidate(
        owner_id=source["owner_id"],
        integration_id=source["evidence"]["integration_id"],
        source_native_record_id=source["evidence"]["source_native_record_id"],
        payload=source["evidence"]["payload"],
        original_bytes=original_bytes,
        processing_manifest=source["processing_manifest"],
        source_provenance=safe_provenance,
        extensions=source["evidence"]["extensions"],
    )


def build_synthetic_envelope(
    source_candidate: Mapping[str, Any],
    original_bytes: bytes,
    *,
    integration_version: str,
    source_platform: str,
    origin_device_id: str,
    client_capture_id: str,
    client_item_id: str,
    event_type: str,
    observed_at: str,
    recorded_at_local: str,
    source_provenance: Mapping[str, Any],
) -> dict[str, Any]:
    """Project one local B2 candidate into a synthetic-only transport envelope.

    The source candidate remains untouched. The returned envelope has a new
    path-free transport candidate integrity and canonical envelope integrity.
    """
    projected = _project_candidate(
        source_candidate, original_bytes, source_provenance=source_provenance
    )
    evidence = projected["evidence"]
    envelope: dict[str, Any] = {
        "schema_version": ENVELOPE_SCHEMA,
        "profile": PROFILE,
        "owner_id": projected["owner_id"],
        "integration_id": evidence["integration_id"],
        "integration_version": _version(integration_version),
        "source_platform": _token(source_platform, field="source_platform"),
        "origin_device_id": _token(origin_device_id, field="origin_device_id"),
        "client_capture_id": _token(client_capture_id, field="client_capture_id"),
        "client_item_id": _token(client_item_id, field="client_item_id"),
        "source_native_record_id": evidence["source_native_record_id"],
        "stable_source_record_id": evidence["stable_source_record_id"],
        "idempotency_key": evidence["idempotency_key"],
        "event_type": _event_type(event_type),
        "observed_at": _canonical_timestamp(observed_at, field="observed_at"),
        "recorded_at_local": _canonical_timestamp(recorded_at_local, field="recorded_at_local"),
        "data_class": SYNTHETIC_DATA_CLASS,
        "evidence_tier": "raw",
        "permission_state": SYNTHETIC_PERMISSION,
        "local_lifecycle_state": SYNTHETIC_LIFECYCLE,
        "candidate_integrity": projected["candidate_integrity"],
        "candidate_payload_integrity": evidence["payload_integrity"],
        "original_integrity": evidence["original_integrity"],
        "processing_manifest": projected["processing_manifest"],
        "processing_manifest_integrity": projected["processing_manifest_integrity"],
        "payload": evidence["payload"],
        "source_provenance": evidence["source_provenance"],
        "extensions": evidence["extensions"],
    }
    _reject_transport_unsafe(envelope["payload"], field="payload")
    _reject_transport_unsafe(envelope["processing_manifest"], field="processing_manifest")
    _reject_transport_unsafe(envelope["extensions"], field="extensions")
    envelope["envelope_integrity"] = _envelope_integrity(envelope)
    return envelope


def validate_synthetic_envelope(
    envelope: Mapping[str, Any], original_bytes: bytes
) -> dict[str, Any]:
    if not isinstance(envelope, Mapping) or envelope.get("schema_version") != ENVELOPE_SCHEMA:
        raise SyntheticIngressError(f"envelope.schema_version must be {ENVELOPE_SCHEMA}")
    required = {
        "schema_version", "profile", "owner_id", "integration_id", "integration_version",
        "source_platform", "origin_device_id", "client_capture_id", "client_item_id",
        "source_native_record_id", "stable_source_record_id", "idempotency_key", "event_type",
        "observed_at", "recorded_at_local", "data_class", "evidence_tier", "permission_state",
        "local_lifecycle_state", "candidate_integrity", "candidate_payload_integrity",
        "original_integrity", "processing_manifest", "processing_manifest_integrity", "payload",
        "source_provenance", "extensions", "envelope_integrity",
    }
    if set(envelope) != required:
        raise SyntheticIngressError("synthetic envelope fields are not the canonical contract shape")
    if envelope.get("profile") != PROFILE:
        raise SyntheticIngressError("only the synthetic-only ingress profile is accepted")
    if envelope.get("data_class") != SYNTHETIC_DATA_CLASS or envelope.get("permission_state") != SYNTHETIC_PERMISSION:
        raise SyntheticIngressError("envelope is not explicitly synthetic-only")
    if envelope.get("evidence_tier") != "raw" or envelope.get("local_lifecycle_state") != SYNTHETIC_LIFECYCLE:
        raise SyntheticIngressError("envelope lifecycle/evidence tier is not synthetic prepared raw evidence")
    _version(envelope.get("integration_version"))
    for field in ("source_platform", "origin_device_id", "client_capture_id", "client_item_id"):
        _token(envelope.get(field), field=field)
    _event_type(envelope.get("event_type"))
    _canonical_timestamp(envelope.get("observed_at"), field="observed_at")
    _canonical_timestamp(envelope.get("recorded_at_local"), field="recorded_at_local")
    safe_provenance = validate_synthetic_provenance(envelope.get("source_provenance"))
    _reject_transport_unsafe(envelope.get("payload"), field="payload")
    _reject_transport_unsafe(envelope.get("processing_manifest"), field="processing_manifest")
    _reject_transport_unsafe(envelope.get("extensions"), field="extensions")
    projected = lifecycle.build_source_candidate(
        owner_id=envelope.get("owner_id"),
        integration_id=envelope.get("integration_id"),
        source_native_record_id=envelope.get("source_native_record_id"),
        payload=envelope.get("payload"),
        original_bytes=original_bytes,
        processing_manifest=envelope.get("processing_manifest"),
        source_provenance=safe_provenance,
        extensions=envelope.get("extensions"),
    )
    evidence = projected["evidence"]
    for field, expected in {
        "stable_source_record_id": evidence["stable_source_record_id"],
        "idempotency_key": evidence["idempotency_key"],
        "candidate_integrity": projected["candidate_integrity"],
        "candidate_payload_integrity": evidence["payload_integrity"],
        "original_integrity": evidence["original_integrity"],
        "processing_manifest_integrity": projected["processing_manifest_integrity"],
        "source_provenance": evidence["source_provenance"],
        "extensions": evidence["extensions"],
    }.items():
        if envelope.get(field) != expected:
            raise SyntheticIngressError(f"envelope field is not bound to projected candidate: {field}")
    expected_integrity = _envelope_integrity(envelope)
    if envelope.get("envelope_integrity") != expected_integrity:
        raise SyntheticIngressError("envelope integrity does not match canonical transport bytes")
    return primitives.canonical_json_value(envelope)


def _receipt_for_envelope(
    envelope: Mapping[str, Any],
    original_bytes: bytes,
    *,
    status: str,
    recorded_at: str,
) -> dict[str, Any]:
    if status not in {"accepted", "duplicate"}:
        raise SyntheticReceiptMismatch("synthetic ingress receipt status must be accepted or duplicate")
    normalized = validate_synthetic_envelope(envelope, original_bytes)
    projected = lifecycle.build_source_candidate(
        owner_id=normalized["owner_id"],
        integration_id=normalized["integration_id"],
        source_native_record_id=normalized["source_native_record_id"],
        payload=normalized["payload"],
        original_bytes=original_bytes,
        processing_manifest=normalized["processing_manifest"],
        source_provenance=normalized["source_provenance"],
        extensions=normalized["extensions"],
    )
    base = lifecycle.expected_receipt_for_candidate(projected, original_bytes)
    return {
        "schema_version": RECEIPT_SCHEMA,
        "profile": PROFILE,
        "status": status,
        "receipt_id": base["receipt_id"],
        "recorded_at": _canonical_timestamp(recorded_at, field="recorded_at"),
        "owner_id": normalized["owner_id"],
        "integration_id": normalized["integration_id"],
        "integration_version": normalized["integration_version"],
        "source_platform": normalized["source_platform"],
        "origin_device_id": normalized["origin_device_id"],
        "client_capture_id": normalized["client_capture_id"],
        "client_item_id": normalized["client_item_id"],
        "source_native_record_id": normalized["source_native_record_id"],
        "stable_source_record_id": normalized["stable_source_record_id"],
        "idempotency_key": normalized["idempotency_key"],
        "candidate_integrity": normalized["candidate_integrity"],
        "candidate_payload_integrity": normalized["candidate_payload_integrity"],
        "original_integrity": normalized["original_integrity"],
        "processing_manifest_integrity": normalized["processing_manifest_integrity"],
        "event_ref": base["event_ref"],
        "original_ref": base["original_ref"],
        "processing_manifest_ref": base["processing_manifest_ref"],
    }


def verify_synthetic_receipt(
    envelope: Mapping[str, Any], original_bytes: bytes, receipt: Mapping[str, Any]
) -> dict[str, Any]:
    if not isinstance(receipt, Mapping) or receipt.get("schema_version") != RECEIPT_SCHEMA:
        raise SyntheticReceiptMismatch(f"receipt.schema_version must be {RECEIPT_SCHEMA}")
    if receipt.get("profile") != PROFILE:
        raise SyntheticReceiptMismatch("receipt is not issued under the synthetic-only profile")
    status = receipt.get("status")
    recorded_at = _canonical_timestamp(receipt.get("recorded_at"), field="receipt.recorded_at")
    expected = _receipt_for_envelope(envelope, original_bytes, status=status, recorded_at=recorded_at)
    if set(receipt) != set(expected):
        raise SyntheticReceiptMismatch("receipt fields are not the canonical synthetic contract shape")
    for field, expected_value in expected.items():
        if receipt.get(field) != expected_value:
            raise SyntheticReceiptMismatch(f"receipt field is not bound to envelope: {field}")
    for field in ("event_ref", "original_ref", "processing_manifest_ref"):
        primitives.validate_core_ref(receipt[field])
        if receipt[field].startswith("s3://"):
            raise SyntheticReceiptMismatch("provider reference is forbidden in canonical receipt fields")
    return expected


def _write_immutable(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if path.read_bytes() != content:
            raise SyntheticIngressError(f"immutable ingress content differs: {path.name}")
        return
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content)


class LocalSyntheticSourceIngress:
    """Local C1 harness; synthetic profile only and never a network transport."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.lifecycle = lifecycle.LocalSyntheticSourceLifecycle(root / "lifecycle")
        self.index_path = root / "ingress-index.json"

    def _receipt_path(self, receipt_id: str) -> Path:
        if not isinstance(receipt_id, str) or not receipt_id.startswith("rcpt_"):
            raise SyntheticIngressError("receipt_id must be a canonical receipt identifier")
        return self.root / "receipts" / f"{receipt_id}.json"

    def _load_index(self) -> dict[str, Any]:
        if not self.index_path.exists():
            return {"schema_version": INGRESS_INDEX_SCHEMA, "retry_pending": {}}
        return json.loads(self.index_path.read_text())

    def _save_index(self, index: Mapping[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.index_path.with_suffix(".tmp")
        temporary.write_bytes(primitives.canonical_json_bytes(index))
        os.replace(temporary, self.index_path)

    @staticmethod
    def _projected_candidate(envelope: Mapping[str, Any], original_bytes: bytes) -> dict[str, Any]:
        normalized = validate_synthetic_envelope(envelope, original_bytes)
        return lifecycle.build_source_candidate(
            owner_id=normalized["owner_id"],
            integration_id=normalized["integration_id"],
            source_native_record_id=normalized["source_native_record_id"],
            payload=normalized["payload"],
            original_bytes=original_bytes,
            processing_manifest=normalized["processing_manifest"],
            source_provenance=normalized["source_provenance"],
            extensions=normalized["extensions"],
        )

    def submit(
        self,
        envelope: Mapping[str, Any],
        original_bytes: bytes,
        *,
        test_outcome: str = "accept",
        receipt_recorded_at: str = "2026-01-01T00:00:00Z",
    ) -> dict[str, Any]:
        normalized = validate_synthetic_envelope(envelope, original_bytes)
        candidate = self._projected_candidate(normalized, original_bytes)
        stable_id = normalized["stable_source_record_id"]
        index = self._load_index()
        pending = index["retry_pending"].get(stable_id)
        retry_binding = {
            "envelope_integrity": normalized["envelope_integrity"],
            "idempotency_key": normalized["idempotency_key"],
            "candidate_integrity": normalized["candidate_integrity"],
        }
        if pending and pending != retry_binding:
            raise RetryBindingMismatch("retry must preserve envelope bytes, candidate integrity, and idempotency key")
        result = self.lifecycle.submit(candidate, original_bytes, test_outcome=test_outcome)
        if result["status"] == "retry":
            index["retry_pending"][stable_id] = retry_binding
            self._save_index(index)
            return {"profile": PROFILE, **result}
        if result["status"] == "denied":
            return {"profile": PROFILE, **result}
        if result["status"] not in {"accepted", "duplicate"}:
            raise SyntheticIngressError("local lifecycle returned an unsupported synthetic outcome")
        if result["status"] == "accepted":
            receipt = _receipt_for_envelope(
                normalized,
                original_bytes,
                status="accepted",
                recorded_at=receipt_recorded_at,
            )
            _write_immutable(self._receipt_path(receipt["receipt_id"]), primitives.canonical_json_bytes(receipt))
            if stable_id in index["retry_pending"]:
                del index["retry_pending"][stable_id]
                self._save_index(index)
            verify_synthetic_receipt(normalized, original_bytes, receipt)
            return {"status": "accepted", "receipt": receipt}
        stored = json.loads(self._receipt_path(result["receipt"]["receipt_id"]).read_text())
        duplicate = dict(stored)
        duplicate["status"] = "duplicate"
        verify_synthetic_receipt(normalized, original_bytes, duplicate)
        return {"status": "duplicate", "receipt": duplicate}

    def revoke(self) -> dict[str, Any]:
        self.lifecycle.revoke()
        return {"profile": PROFILE, "status": "revoked", "code": "grant_revoked"}

    def readback_original(self, envelope: Mapping[str, Any], original_bytes: bytes, receipt: Mapping[str, Any]) -> bytes:
        verified = verify_synthetic_receipt(envelope, original_bytes, receipt)
        original = self.lifecycle.readback_original(verified)
        primitives.verify_bytes(original, verified["original_integrity"])
        return original

    def export(self) -> dict[str, Any]:
        exported = self.lifecycle.export()
        receipts = []
        for base_receipt in exported["receipts"]:
            stored = json.loads(self._receipt_path(base_receipt["receipt_id"]).read_text())
            receipts.append(stored)
        return {"profile": PROFILE, "status": exported["status"], "cursor": exported["cursor"], "receipts": receipts}
