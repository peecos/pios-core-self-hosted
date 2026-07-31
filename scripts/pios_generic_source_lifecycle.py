"""Owner-neutral local synthetic lifecycle and receipt primitives for B2.

No network transport, source adapter, credential, service activation, or real
owner configuration is implemented here. The owner identifier is a generic
receipt-binding input; tests use harmless synthetic values only.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Mapping

from scripts import pios_canonical_source_primitives as primitives

CANDIDATE_SCHEMA = "pios_generic_source_candidate_v1"
RECEIPT_SCHEMA = "pios_generic_source_receipt_v1"
OWNER_ID_RE = re.compile(r"owner_[a-z0-9_]{1,126}")
TEST_OUTCOMES = frozenset({"accept", "deny", "retry_once"})


class LifecycleError(ValueError):
    """Raised for an invalid B2 candidate, receipt, or lifecycle operation."""


class ReceiptMismatch(LifecycleError):
    """Raised when a receipt is not bound to the candidate being verified."""


def _validate_owner_id(owner_id: str) -> str:
    if not isinstance(owner_id, str) or not OWNER_ID_RE.fullmatch(owner_id):
        raise LifecycleError("owner_id must be a generic owner_ identifier")
    return owner_id


def _canonical_manifest(manifest: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(manifest, Mapping):
        raise LifecycleError("processing_manifest must be an object")
    canonical = primitives.canonical_json_value(manifest)
    return canonical, primitives.integrity_for_bytes(primitives.canonical_json_bytes(canonical))


def _candidate_binding(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": CANDIDATE_SCHEMA,
        "owner_id": candidate["owner_id"],
        "evidence": candidate["evidence"],
        "processing_manifest_integrity": candidate["processing_manifest_integrity"],
    }


def _candidate_integrity(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return primitives.integrity_for_bytes(primitives.canonical_json_bytes(_candidate_binding(candidate)))


def build_source_candidate(
    *,
    owner_id: str,
    integration_id: str,
    source_native_record_id: str,
    payload: Mapping[str, Any],
    original_bytes: bytes,
    processing_manifest: Mapping[str, Any],
    source_provenance: Mapping[str, Any],
    extensions: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a local-only generic candidate with complete integrity bindings."""
    owner_id = _validate_owner_id(owner_id)
    manifest, manifest_integrity = _canonical_manifest(processing_manifest)
    evidence = primitives.build_source_evidence(
        integration_id=integration_id,
        source_native_record_id=source_native_record_id,
        payload=payload,
        original_bytes=original_bytes,
        logical_references={},
        source_provenance=source_provenance,
        extensions=extensions,
    )
    candidate: dict[str, Any] = {
        "schema_version": CANDIDATE_SCHEMA,
        "owner_id": owner_id,
        "evidence": evidence,
        "processing_manifest": manifest,
        "processing_manifest_integrity": manifest_integrity,
    }
    candidate["candidate_integrity"] = _candidate_integrity(candidate)
    return candidate


def validate_source_candidate(candidate: Mapping[str, Any], original_bytes: bytes) -> dict[str, Any]:
    if not isinstance(candidate, Mapping) or candidate.get("schema_version") != CANDIDATE_SCHEMA:
        raise LifecycleError(f"candidate.schema_version must be {CANDIDATE_SCHEMA}")
    owner_id = _validate_owner_id(candidate.get("owner_id"))
    evidence = primitives.validate_source_evidence(candidate.get("evidence"), original_bytes)
    manifest, manifest_integrity = _canonical_manifest(candidate.get("processing_manifest"))
    if candidate.get("processing_manifest_integrity") != manifest_integrity:
        raise LifecycleError("processing manifest integrity does not match canonical manifest bytes")
    normalized: dict[str, Any] = {
        "schema_version": CANDIDATE_SCHEMA,
        "owner_id": owner_id,
        "evidence": evidence,
        "processing_manifest": manifest,
        "processing_manifest_integrity": manifest_integrity,
    }
    candidate_integrity = _candidate_integrity(normalized)
    if candidate.get("candidate_integrity") != candidate_integrity:
        raise LifecycleError("candidate integrity does not match canonical identity and digest bindings")
    normalized["candidate_integrity"] = candidate_integrity
    return normalized


def _derive_receipt_id_from_validated(candidate: Mapping[str, Any]) -> str:
    evidence = candidate["evidence"]
    binding = {
        "schema_version": RECEIPT_SCHEMA,
        "owner_id": candidate["owner_id"],
        "integration_id": evidence["integration_id"],
        "stable_source_record_id": evidence["stable_source_record_id"],
        "idempotency_key": evidence["idempotency_key"],
        "candidate_integrity": candidate["candidate_integrity"],
        "original_integrity": evidence["original_integrity"],
        "processing_manifest_integrity": candidate["processing_manifest_integrity"],
    }
    return f"rcpt_{primitives.sha256_bytes(primitives.canonical_json_bytes(binding))}"


def _receipt_for_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    evidence = candidate["evidence"]
    original_digest = evidence["original_integrity"]["sha256"]
    manifest_digest = candidate["processing_manifest_integrity"]["sha256"]
    receipt_id = _derive_receipt_id_from_validated(candidate)
    return {
        "schema_version": RECEIPT_SCHEMA,
        "status": "accepted",
        "receipt_id": receipt_id,
        "owner_id": candidate["owner_id"],
        "integration_id": evidence["integration_id"],
        "source_native_record_id": evidence["source_native_record_id"],
        "stable_source_record_id": evidence["stable_source_record_id"],
        "idempotency_key": evidence["idempotency_key"],
        "candidate_integrity": candidate["candidate_integrity"],
        "payload_integrity": evidence["payload_integrity"],
        "original_integrity": evidence["original_integrity"],
        "processing_manifest_integrity": candidate["processing_manifest_integrity"],
        "event_ref": primitives.build_core_ref("events", receipt_id),
        "original_ref": primitives.build_core_ref("originals", original_digest),
        "processing_manifest_ref": primitives.build_core_ref(
            "system", "processing-manifests", manifest_digest
        ),
    }


def verify_receipt(candidate: Mapping[str, Any], original_bytes: bytes, receipt: Mapping[str, Any]) -> dict[str, Any]:
    normalized = validate_source_candidate(candidate, original_bytes)
    if not isinstance(receipt, Mapping) or receipt.get("schema_version") != RECEIPT_SCHEMA:
        raise ReceiptMismatch(f"receipt.schema_version must be {RECEIPT_SCHEMA}")
    expected = _receipt_for_candidate(normalized)
    for field, expected_value in expected.items():
        if receipt.get(field) != expected_value:
            raise ReceiptMismatch(f"receipt field is not bound to candidate: {field}")
    return expected


def _write_immutable(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if path.read_bytes() != content:
            raise LifecycleError(f"immutable retained content differs: {path.name}")
        return
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content)


class LocalSyntheticSourceLifecycle:
    """A zero-network local lifecycle harness for generated harmless fixtures."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.evidence_store = primitives.LocalSyntheticEvidenceStore(root / "content")
        self.index_path = root / "lifecycle-index.json"

    def _load_index(self) -> dict[str, Any]:
        if not self.index_path.exists():
            return {"accepted": {}, "retry_once": [], "revoked": False}
        return json.loads(self.index_path.read_text())

    def _save_index(self, value: Mapping[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.index_path.with_suffix(".tmp")
        temporary.write_bytes(primitives.canonical_json_bytes(value))
        os.replace(temporary, self.index_path)

    def _manifest_path(self, digest: str) -> Path:
        return self.root / "processing-manifests" / f"{digest}.json"

    def _receipt_path(self, receipt_id: str) -> Path:
        return self.root / "receipts" / f"{receipt_id}.json"

    def submit(
        self,
        candidate: Mapping[str, Any],
        original_bytes: bytes,
        *,
        test_outcome: str = "accept",
    ) -> dict[str, Any]:
        if test_outcome not in TEST_OUTCOMES:
            raise LifecycleError("test_outcome must be accept, deny, or retry_once")
        normalized = validate_source_candidate(candidate, original_bytes)
        index = self._load_index()
        evidence = normalized["evidence"]
        stable_id = evidence["stable_source_record_id"]
        if index["revoked"]:
            return {"status": "denied", "code": "grant_revoked", "retryable": False}
        existing = index["accepted"].get(stable_id)
        if existing:
            if existing["candidate_integrity"] != normalized["candidate_integrity"]:
                return {"status": "denied", "code": "source_identity_conflict", "retryable": False}
            receipt = json.loads(self._receipt_path(existing["receipt_id"]).read_text())
            verify_receipt(normalized, original_bytes, receipt)
            return {"status": "duplicate", "receipt": receipt}
        if test_outcome == "deny":
            return {"status": "denied", "code": "synthetic_denied", "retryable": False}
        if test_outcome == "retry_once" and evidence["idempotency_key"] not in index["retry_once"]:
            index["retry_once"].append(evidence["idempotency_key"])
            self._save_index(index)
            return {"status": "retry", "code": "synthetic_transient", "retryable": True}

        self.evidence_store.retain(evidence, original_bytes)
        manifest_bytes = primitives.canonical_json_bytes(normalized["processing_manifest"])
        manifest_digest = normalized["processing_manifest_integrity"]["sha256"]
        _write_immutable(self._manifest_path(manifest_digest), manifest_bytes)
        receipt = _receipt_for_candidate(normalized)
        _write_immutable(self._receipt_path(receipt["receipt_id"]), primitives.canonical_json_bytes(receipt))
        index["accepted"][stable_id] = {
            "candidate_integrity": normalized["candidate_integrity"],
            "receipt_id": receipt["receipt_id"],
        }
        self._save_index(index)
        verify_receipt(normalized, original_bytes, receipt)
        return {"status": "accepted", "receipt": receipt}

    def revoke(self) -> dict[str, Any]:
        index = self._load_index()
        index["revoked"] = True
        self._save_index(index)
        return {"status": "revoked", "code": "grant_revoked"}

    def readback_original(self, receipt: Mapping[str, Any]) -> bytes:
        if not isinstance(receipt, Mapping):
            raise LifecycleError("receipt must be an object")
        integrity = primitives.validate_integrity(receipt.get("original_integrity"))
        original = (self.root / "content" / "originals" / f"{integrity['sha256']}.bin").read_bytes()
        primitives.verify_bytes(original, integrity)
        return original

    def export(self, cursor: int = 0) -> dict[str, Any]:
        if not isinstance(cursor, int) or cursor < 0:
            raise LifecycleError("cursor must be a non-negative integer")
        receipts = []
        for entry in self._load_index()["accepted"].values():
            receipts.append(json.loads(self._receipt_path(entry["receipt_id"]).read_text()))
        receipts.sort(key=lambda receipt: receipt["receipt_id"])
        return {"status": "passed", "cursor": len(receipts), "receipts": receipts[cursor:]}
