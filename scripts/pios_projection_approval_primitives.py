"""Owner-neutral local projection, audit, and action-approval primitives.

This module contains no listener, identity provider, browser integration,
credential, or source mutation capability.  Its only executable flow uses
generated synthetic bindings and local immutable audit files.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from scripts import pios_canonical_source_primitives as primitives
from scripts import pios_generic_source_lifecycle as lifecycle

PROJECTION_SCHEMA = "pios_generic_projection_v1"
ACTION_CHALLENGE_SCHEMA = "pios_generic_action_challenge_v1"
APPROVAL_PROOF_SCHEMA = "pios_generic_approval_proof_v1"
AUDIT_RECORD_SCHEMA = "pios_generic_audit_record_v1"
READ_ONLY = "read_only"
SENSITIVE = "sensitive"
DEFAULT_ACTION_CLASSIFICATIONS = {
    "view_projection": READ_ONLY,
    "export_projection": SENSITIVE,
    "change_projection_policy": SENSITIVE,
}
OWNER_ID_RE = re.compile(r"owner_[a-z0-9_]{1,126}")
ACTION_NAME_RE = re.compile(r"[a-z][a-z0-9_]{0,62}")
BINDING_RE = re.compile(r"binding_[a-z0-9_-]{1,126}")
RECEIPT_ID_RE = re.compile(r"rcpt_[0-9a-f]{64}")
ACTION_ID_RE = re.compile(r"action_[0-9a-f]{64}")
PROOF_ID_RE = re.compile(r"proof_[0-9a-f]{64}")
AUDIT_ID_RE = re.compile(r"audit_[0-9a-f]{64}")
APPROVAL_ID_RE = re.compile(r"approval_[0-9a-f]{64}")
UTC_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class ProjectionApprovalError(ValueError):
    """Base error for invalid local projection or approval data."""


class ApprovalRejected(ProjectionApprovalError):
    """Raised when an approval proof is invalid, expired, or already used."""


class AuditPersistenceError(ProjectionApprovalError):
    """Raised when a required immutable audit record cannot be persisted."""


def _canonical(value: Any) -> Any:
    return primitives.canonical_json_value(value)


def _integrity(value: Mapping[str, Any]) -> dict[str, Any]:
    return primitives.integrity_for_bytes(primitives.canonical_json_bytes(value))


def _validate_owner_id(owner_id: str) -> str:
    if not isinstance(owner_id, str) or not OWNER_ID_RE.fullmatch(owner_id):
        raise ProjectionApprovalError("owner_id must be a generic owner_ identifier")
    return owner_id


def _validate_binding(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not BINDING_RE.fullmatch(value):
        raise ProjectionApprovalError(f"{field} must be a generic binding_ identifier")
    return value


def _parse_timestamp(value: str, *, field: str) -> datetime:
    if not isinstance(value, str):
        raise ProjectionApprovalError(f"{field} must be a UTC timestamp string")
    try:
        parsed = datetime.strptime(value, UTC_TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ProjectionApprovalError(
            f"{field} must use canonical UTC format YYYY-MM-DDTHH:MM:SSZ"
        ) from exc
    return parsed


def _timestamp(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ProjectionApprovalError("timestamps must be timezone-aware datetimes")
    return value.astimezone(timezone.utc).strftime(UTC_TIMESTAMP_FORMAT)


def _validate_action_type(action_type: str) -> str:
    if not isinstance(action_type, str) or not ACTION_NAME_RE.fullmatch(action_type):
        raise ProjectionApprovalError("action_type must be a canonical generic action name")
    return action_type


def classify_action(
    action_type: str, classifications: Mapping[str, str] | None = None
) -> str:
    """Classify a named generic action without enabling that action."""
    action_type = _validate_action_type(action_type)
    policy = DEFAULT_ACTION_CLASSIFICATIONS if classifications is None else classifications
    classification = policy.get(action_type) if isinstance(policy, Mapping) else None
    if classification not in {READ_ONLY, SENSITIVE}:
        raise ProjectionApprovalError("action type must have an explicit read_only or sensitive classification")
    return classification


def _receipt_binding(receipt: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(receipt, Mapping) or receipt.get("schema_version") != lifecycle.RECEIPT_SCHEMA:
        raise ProjectionApprovalError("projection source must be a B2 receipt")
    receipt_id = receipt.get("receipt_id")
    if not isinstance(receipt_id, str) or not RECEIPT_ID_RE.fullmatch(receipt_id):
        raise ProjectionApprovalError("receipt_id must be a canonical receipt identifier")
    candidate_integrity = primitives.validate_integrity(receipt.get("candidate_integrity"))
    return {
        "receipt_id": receipt_id,
        "candidate_integrity": candidate_integrity,
        "event_ref": primitives.validate_core_ref(receipt.get("event_ref")),
        "original_ref": primitives.validate_core_ref(receipt.get("original_ref")),
        "processing_manifest_ref": primitives.validate_core_ref(
            receipt.get("processing_manifest_ref")
        ),
    }


def _projection_binding(
    source_receipt_binding: Mapping[str, Any],
    projection_fields: Mapping[str, Any],
    extensions: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": PROJECTION_SCHEMA,
        "source_receipt_binding": _canonical(source_receipt_binding),
        "projection_fields": _canonical(projection_fields),
        "extensions": primitives.preserve_extensions(extensions),
    }


def build_projection_record(
    *,
    source_receipt: Mapping[str, Any],
    projection_fields: Mapping[str, Any],
    extensions: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a projection that references source truth but cannot mutate it."""
    if not isinstance(projection_fields, Mapping):
        raise ProjectionApprovalError("projection_fields must be an object")
    source_binding = _receipt_binding(source_receipt)
    binding = _projection_binding(source_binding, projection_fields, extensions)
    projection_id = f"projection_{primitives.sha256_bytes(primitives.canonical_json_bytes(binding))}"
    record = {
        **binding,
        "projection_id": projection_id,
        "projection_ref": primitives.build_core_ref("derived", "projections", projection_id),
    }
    record["projection_integrity"] = _integrity(record)
    return record


def validate_projection_record(record: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(record, Mapping) or record.get("schema_version") != PROJECTION_SCHEMA:
        raise ProjectionApprovalError(f"projection.schema_version must be {PROJECTION_SCHEMA}")
    raw_source_binding = record.get("source_receipt_binding")
    if not isinstance(raw_source_binding, Mapping):
        raise ProjectionApprovalError("projection source_receipt_binding must be an object")
    source_binding = _receipt_binding(
        {
            "schema_version": lifecycle.RECEIPT_SCHEMA,
            "receipt_id": raw_source_binding.get("receipt_id"),
            "candidate_integrity": raw_source_binding.get("candidate_integrity"),
            "event_ref": raw_source_binding.get("event_ref"),
            "original_ref": raw_source_binding.get("original_ref"),
            "processing_manifest_ref": raw_source_binding.get("processing_manifest_ref"),
        }
    )
    fields = record.get("projection_fields")
    extensions = record.get("extensions")
    if not isinstance(fields, Mapping) or not isinstance(extensions, Mapping):
        raise ProjectionApprovalError("projection fields and extensions must be objects")
    binding = _projection_binding(source_binding, fields, extensions)
    projection_id = f"projection_{primitives.sha256_bytes(primitives.canonical_json_bytes(binding))}"
    expected = {
        **binding,
        "projection_id": projection_id,
        "projection_ref": primitives.build_core_ref("derived", "projections", projection_id),
    }
    expected["projection_integrity"] = _integrity(expected)
    if _canonical(record) != expected:
        raise ProjectionApprovalError("projection fields or integrity are not bound to source receipt")
    return expected


def _action_binding(
    *,
    owner_id: str,
    action_type: str,
    classification: str,
    parameters: Mapping[str, Any],
    session_binding: str,
    csrf_binding: str,
    issued_at: str,
    expires_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": ACTION_CHALLENGE_SCHEMA,
        "owner_id": owner_id,
        "action_type": action_type,
        "classification": classification,
        "parameters": _canonical(parameters),
        "session_binding": session_binding,
        "csrf_binding": csrf_binding,
        "issued_at": issued_at,
        "expires_at": expires_at,
    }


def begin_sensitive_action(
    *,
    owner_id: str,
    action_type: str,
    parameters: Mapping[str, Any],
    session_binding: str,
    csrf_binding: str,
    issued_at: datetime,
    ttl_seconds: int = 300,
) -> dict[str, Any]:
    """Create an unapproved, short-lived local action challenge."""
    owner_id = _validate_owner_id(owner_id)
    action_type = _validate_action_type(action_type)
    if classify_action(action_type) != SENSITIVE:
        raise ProjectionApprovalError("read_only actions do not accept an approval proof")
    if not isinstance(parameters, Mapping):
        raise ProjectionApprovalError("action parameters must be an object")
    if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool) or not 1 <= ttl_seconds <= 300:
        raise ProjectionApprovalError("ttl_seconds must be an integer from 1 through 300")
    issued_at_text = _timestamp(issued_at)
    expires_at_text = _timestamp(issued_at + timedelta(seconds=ttl_seconds))
    binding = _action_binding(
        owner_id=owner_id,
        action_type=action_type,
        classification=SENSITIVE,
        parameters=parameters,
        session_binding=_validate_binding(session_binding, field="session_binding"),
        csrf_binding=_validate_binding(csrf_binding, field="csrf_binding"),
        issued_at=issued_at_text,
        expires_at=expires_at_text,
    )
    action_id = f"action_{primitives.sha256_bytes(primitives.canonical_json_bytes(binding))}"
    challenge = {**binding, "action_id": action_id}
    challenge["action_integrity"] = _integrity(challenge)
    return challenge


def validate_action_challenge(challenge: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(challenge, Mapping) or challenge.get("schema_version") != ACTION_CHALLENGE_SCHEMA:
        raise ProjectionApprovalError(f"challenge.schema_version must be {ACTION_CHALLENGE_SCHEMA}")
    owner_id = _validate_owner_id(challenge.get("owner_id"))
    action_type = _validate_action_type(challenge.get("action_type"))
    classification = classify_action(action_type)
    if classification != SENSITIVE or challenge.get("classification") != SENSITIVE:
        raise ProjectionApprovalError("challenge must be for an explicitly sensitive action")
    parameters = challenge.get("parameters")
    if not isinstance(parameters, Mapping):
        raise ProjectionApprovalError("challenge parameters must be an object")
    issued_at = _parse_timestamp(challenge.get("issued_at"), field="issued_at")
    expires_at = _parse_timestamp(challenge.get("expires_at"), field="expires_at")
    if expires_at <= issued_at or expires_at - issued_at > timedelta(seconds=300):
        raise ProjectionApprovalError("challenge expiry must be after issue and no more than five minutes")
    binding = _action_binding(
        owner_id=owner_id,
        action_type=action_type,
        classification=SENSITIVE,
        parameters=parameters,
        session_binding=_validate_binding(challenge.get("session_binding"), field="session_binding"),
        csrf_binding=_validate_binding(challenge.get("csrf_binding"), field="csrf_binding"),
        issued_at=_timestamp(issued_at),
        expires_at=_timestamp(expires_at),
    )
    action_id = f"action_{primitives.sha256_bytes(primitives.canonical_json_bytes(binding))}"
    expected = {**binding, "action_id": action_id}
    expected["action_integrity"] = _integrity(expected)
    if _canonical(challenge) != expected:
        raise ProjectionApprovalError("challenge action binding or integrity is invalid")
    return expected


def build_synthetic_approval_proof(
    *, challenge: Mapping[str, Any], approved_at: datetime
) -> dict[str, Any]:
    """Build a generated local approval proof; it is not an authentication method."""
    normalized = validate_action_challenge(challenge)
    approved_at_text = _timestamp(approved_at)
    proof_binding = {
        "schema_version": APPROVAL_PROOF_SCHEMA,
        "proof_kind": "synthetic_step_up",
        "action_id": normalized["action_id"],
        "action_integrity": normalized["action_integrity"],
        "owner_id": normalized["owner_id"],
        "session_binding": normalized["session_binding"],
        "csrf_binding": normalized["csrf_binding"],
        "approved_at": approved_at_text,
    }
    proof_id = f"proof_{primitives.sha256_bytes(primitives.canonical_json_bytes(proof_binding))}"
    return {**proof_binding, "proof_id": proof_id}


def validate_approval_proof(
    *, challenge: Mapping[str, Any], proof: Mapping[str, Any], now: datetime
) -> dict[str, Any]:
    normalized_challenge = validate_action_challenge(challenge)
    if not isinstance(proof, Mapping) or proof.get("schema_version") != APPROVAL_PROOF_SCHEMA:
        raise ApprovalRejected(f"proof.schema_version must be {APPROVAL_PROOF_SCHEMA}")
    approved_at = _parse_timestamp(proof.get("approved_at"), field="proof.approved_at")
    now_utc = _parse_timestamp(_timestamp(now), field="now")
    issued_at = _parse_timestamp(normalized_challenge["issued_at"], field="issued_at")
    expires_at = _parse_timestamp(normalized_challenge["expires_at"], field="expires_at")
    if now_utc > expires_at or approved_at > expires_at or approved_at < issued_at:
        raise ApprovalRejected("approval_expired")
    expected = build_synthetic_approval_proof(
        challenge=normalized_challenge, approved_at=approved_at
    )
    if _canonical(proof) != expected:
        raise ApprovalRejected("approval proof is not bound to the exact action, owner, session, and CSRF binding")
    return expected


def _audit_binding(
    challenge: Mapping[str, Any], proof: Mapping[str, Any]
) -> dict[str, Any]:
    approval_id = _derive_approval_id(challenge["action_id"], proof["proof_id"])
    return {
        "schema_version": AUDIT_RECORD_SCHEMA,
        "outcome": "approved",
        "approval_id": approval_id,
        "owner_id": challenge["owner_id"],
        "action_id": challenge["action_id"],
        "action_type": challenge["action_type"],
        "classification": challenge["classification"],
        "action_integrity": challenge["action_integrity"],
        "proof_id": proof["proof_id"],
        "approved_at": proof["approved_at"],
    }


def _derive_approval_id(action_id: str, proof_id: str) -> str:
    return f"approval_{primitives.sha256_bytes(primitives.canonical_json_bytes({"action_id": action_id, "proof_id": proof_id}))}"


def build_audit_record(challenge: Mapping[str, Any], proof: Mapping[str, Any]) -> dict[str, Any]:
    normalized_challenge = validate_action_challenge(challenge)
    if not isinstance(proof, Mapping):
        raise ProjectionApprovalError("audit record requires an approval proof object")
    approved_at = _parse_timestamp(proof.get("approved_at"), field="proof.approved_at")
    normalized_proof = validate_approval_proof(
        challenge=normalized_challenge, proof=proof, now=approved_at
    )
    binding = _audit_binding(normalized_challenge, normalized_proof)
    audit_id = f"audit_{primitives.sha256_bytes(primitives.canonical_json_bytes(binding))}"
    record = {
        **binding,
        "audit_id": audit_id,
        "approval_ref": primitives.build_core_ref("system", "approvals", binding["approval_id"]),
        "audit_ref": primitives.build_core_ref("system", "audit", audit_id),
    }
    record["audit_integrity"] = _integrity(record)
    return record


def validate_audit_record(record: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(record, Mapping) or record.get("schema_version") != AUDIT_RECORD_SCHEMA:
        raise ProjectionApprovalError(f"audit.schema_version must be {AUDIT_RECORD_SCHEMA}")
    if record.get("outcome") != "approved":
        raise ProjectionApprovalError("audit outcome must be approved")
    owner_id = _validate_owner_id(record.get("owner_id"))
    action_id = record.get("action_id")
    proof_id = record.get("proof_id")
    approval_id = record.get("approval_id")
    if not isinstance(action_id, str) or not ACTION_ID_RE.fullmatch(action_id):
        raise ProjectionApprovalError("audit action_id must be canonical")
    if not isinstance(proof_id, str) or not PROOF_ID_RE.fullmatch(proof_id):
        raise ProjectionApprovalError("audit proof_id must be canonical")
    if not isinstance(approval_id, str) or not APPROVAL_ID_RE.fullmatch(approval_id):
        raise ProjectionApprovalError("audit approval_id must be canonical")
    if approval_id != _derive_approval_id(action_id, proof_id):
        raise ProjectionApprovalError("audit approval_id is not bound to the action and proof")
    action_type = _validate_action_type(record.get("action_type"))
    if classify_action(action_type) != SENSITIVE or record.get("classification") != SENSITIVE:
        raise ProjectionApprovalError("audit must record a sensitive action")
    action_integrity = primitives.validate_integrity(record.get("action_integrity"))
    approved_at = _timestamp(_parse_timestamp(record.get("approved_at"), field="approved_at"))
    binding = {
        "schema_version": AUDIT_RECORD_SCHEMA,
        "outcome": "approved",
        "approval_id": approval_id,
        "owner_id": owner_id,
        "action_id": action_id,
        "action_type": action_type,
        "classification": SENSITIVE,
        "action_integrity": action_integrity,
        "proof_id": proof_id,
        "approved_at": approved_at,
    }
    audit_id = f"audit_{primitives.sha256_bytes(primitives.canonical_json_bytes(binding))}"
    expected = {
        **binding,
        "audit_id": audit_id,
        "approval_ref": primitives.build_core_ref("system", "approvals", approval_id),
        "audit_ref": primitives.build_core_ref("system", "audit", audit_id),
    }
    expected["audit_integrity"] = _integrity(expected)
    if _canonical(record) != expected:
        raise ProjectionApprovalError("audit record integrity or approval binding is invalid")
    return expected


def _write_immutable(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if path.read_bytes() != content:
            raise AuditPersistenceError(f"immutable audit content differs: {path.name}")
        return
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content)


class LocalImmutableAuditStore:
    """Create-only local audit storage with an explicit synthetic failure hook."""

    def __init__(self, root: Path, *, fail_writes: bool = False) -> None:
        self.root = root
        self.fail_writes = fail_writes

    def _path(self, audit_id: str) -> Path:
        if not isinstance(audit_id, str) or not AUDIT_ID_RE.fullmatch(audit_id):
            raise AuditPersistenceError("audit_id must be a canonical audit identifier")
        return self.root / "audit" / f"{audit_id}.json"

    def write(self, record: Mapping[str, Any]) -> dict[str, Any]:
        normalized = validate_audit_record(record)
        if self.fail_writes:
            raise AuditPersistenceError("synthetic_audit_write_failure")
        _write_immutable(self._path(normalized["audit_id"]), primitives.canonical_json_bytes(normalized))
        return normalized

    def has_audit(self, audit_id: str) -> bool:
        return self._path(audit_id).is_file()

    def has_action(self, action_id: str) -> bool:
        if not isinstance(action_id, str) or not ACTION_ID_RE.fullmatch(action_id):
            raise AuditPersistenceError("action_id must be a canonical action identifier")
        audit_root = self.root / "audit"
        if not audit_root.exists():
            return False
        for path in audit_root.glob("*.json"):
            try:
                record = validate_audit_record(json.loads(path.read_text()))
            except (json.JSONDecodeError, ProjectionApprovalError) as exc:
                raise AuditPersistenceError("stored audit record is invalid") from exc
            if record["action_id"] == action_id:
                return True
        return False


class LocalSyntheticApprovalHarness:
    """Local-only approval outcome coordinator with no action executor."""

    def __init__(self, audit_store: LocalImmutableAuditStore) -> None:
        self.audit_store = audit_store

    def approve(
        self, *, challenge: Mapping[str, Any], proof: Mapping[str, Any], now: datetime
    ) -> dict[str, Any]:
        normalized_challenge = validate_action_challenge(challenge)
        normalized_proof = validate_approval_proof(
            challenge=normalized_challenge, proof=proof, now=now
        )
        record = build_audit_record(normalized_challenge, normalized_proof)
        if self.audit_store.has_action(record["action_id"]) or self.audit_store.has_audit(
            record["audit_id"]
        ):
            raise ApprovalRejected("approval_replayed")
        persisted = self.audit_store.write(record)
        return {
            "status": "approved",
            "approval_ref": persisted["approval_ref"],
            "audit_ref": persisted["audit_ref"],
            "audit_id": persisted["audit_id"],
        }
