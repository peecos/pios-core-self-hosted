#!/usr/bin/env python3
"""Preview/refusal-only preparation for one future C3 named Unix-socket session.

This runner validates the exact immutable Corebox C2 fixture and C1 envelope,
then rebuilds the reviewed cross-language C3 challenge/request vector in memory.
It never creates a runtime directory, binds/accepts/connects a socket, submits
the fixture, calls the lifecycle, or writes evidence. A confirmation flag is
present only to refuse clearly until a separate named execution approval.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import pios_canonical_source_primitives as primitives
from scripts import pios_c3_local_transport as transport
from scripts import pios_synthetic_source_ingress as ingress
from scripts import run_pios_solo_c2_synthetic_proof as c2

RUNNER_PREVIEW_SCHEMA = "pios_solo_c3_named_session_zero_write_preview_v1"
SESSION_RESULT_SCHEMA = "pios_solo_c3_named_session_result_v1"
SOLO_FOUNDATION_REVISION = "45c5bac"
SOLO_EXECUTION_REVISION = "ef40daf"
COREBOX_PREVIEW_CONTRACT_REVISION = "1db18d5"
COREBOX_EXECUTION_REVISION = "1566817"
REVIEW_PROOF_ID = "c3-corebox-local-20260801-r1"
REVIEW_RECEIPT_RECORDED_AT = "2026-08-01T00:00:03Z"
REVIEW_CHALLENGE_NONCE_HEX = "6161616161616161616161616161616161616161616161616161616161616161"
REVIEW_REQUEST_SHA256 = "2fd9cdcdeeeb9d179d4bdab4c4f03ff2b88983bdd9597c9a753175ef02675518"
REVIEW_FRAME_BYTE_COUNT = 1094
REVIEW_SEMANTIC_REQUEST_ID = "req_1cb56356f0dc0ed30c6d88cdc38a5f110b2f7728cf6a1f368b762ca0b1bec81c"
REVIEW_CONNECTION_BINDING_HASH = "c7270e2f9596324db521fa9a548ed87f67fc50890f70e4ed41d173bb8eec6752"
FIXTURE_FILE_NAMES = frozenset(
    {
        "original.bin",
        "envelope.json",
        "corebox-c2-zero-write-preview.json",
        "fixture-manifest.json",
    }
)


class C3NamedSessionPreviewError(ValueError):
    """Raised when a C3 preview cannot be proven safe and exact."""


class C3NamedSessionExecutionNotAuthorized(C3NamedSessionPreviewError):
    """Raised for every execution attempt in this preview/refusal revision."""


class C3NamedSessionProtocolError(C3NamedSessionPreviewError):
    """Raised when an enabled future one-shot session breaks its strict contract."""


def _require_revision(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{7,40}", value):
        raise C3NamedSessionProtocolError(f"{field} must be an explicit git revision")
    return value


def _require_fresh_evidence_destination(path: Path) -> Path:
    path = Path(path)
    if path.exists():
        raise C3NamedSessionProtocolError("C3 evidence destination must not already exist")
    if not path.parent.is_dir():
        raise C3NamedSessionProtocolError("C3 evidence parent must already exist")
    return path


def _require_named_proof_and_receipt(proof_id: str, receipt_recorded_at: str) -> None:
    """Convert transport validation failures into the C3 protocol boundary."""
    try:
        transport._proof_id(proof_id)
        transport._receipt_time(receipt_recorded_at)
    except transport.C3TransportError as exc:
        raise C3NamedSessionProtocolError("C3 named proof identifier or receipt timestamp is invalid") from exc


def _validate_fixed_fixture_path_safety(input_dir: Path) -> None:
    """Require exactly four local regular files before C1 fixture validation."""
    try:
        directory = os.lstat(input_dir)
    except FileNotFoundError as exc:
        raise C3NamedSessionPreviewError("fixture directory is missing") from exc
    if stat.S_ISLNK(directory.st_mode) or not stat.S_ISDIR(directory.st_mode):
        raise C3NamedSessionPreviewError("fixture directory must be a real local directory")
    try:
        entries = {entry.name for entry in input_dir.iterdir()}
    except OSError as exc:
        raise C3NamedSessionPreviewError("fixture directory cannot be read") from exc
    if entries != FIXTURE_FILE_NAMES:
        raise C3NamedSessionPreviewError("fixture directory contains missing or unreviewed files")
    for name in FIXTURE_FILE_NAMES:
        try:
            details = os.lstat(input_dir / name)
        except FileNotFoundError as exc:
            raise C3NamedSessionPreviewError(f"fixture artifact is missing: {name}") from exc
        if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
            raise C3NamedSessionPreviewError(f"fixture artifact must be a regular non-symlink file: {name}")


def _fixture_preview(input_dir: Path) -> dict[str, Any]:
    fixed = transport.fixed_c2_fixture_integrities()
    try:
        return c2.run_zero_write_preview(
            input_dir=input_dir,
            expected_original_sha256=fixed["original"]["sha256"],
            expected_envelope_sha256=fixed["envelope"]["sha256"],
            expected_zero_write_preview_sha256=fixed["zero_write_preview"]["sha256"],
            expected_fixture_manifest_sha256=fixed["fixture_manifest"]["sha256"],
        )
    except c2.C2PreviewError as exc:
        raise C3NamedSessionPreviewError("fixed fixture/C1 validation refused") from exc


def _review_vector() -> tuple[dict[str, Any], dict[str, Any], bytes]:
    fixed = transport.fixed_c2_fixture_integrities()
    challenge = transport.build_challenge(
        proof_id=REVIEW_PROOF_ID,
        fixture_manifest_sha256=fixed["fixture_manifest"]["sha256"],
        nonce=bytes.fromhex(REVIEW_CHALLENGE_NONCE_HEX),
    )
    request = transport.build_fixed_fixture_request(
        challenge=challenge,
        fixture_integrities=fixed,
        receipt_recorded_at=REVIEW_RECEIPT_RECORDED_AT,
    )
    transport.validate_fixed_fixture_request(
        request,
        challenge=challenge,
        fixture_integrities=fixed,
        receipt_recorded_at=REVIEW_RECEIPT_RECORDED_AT,
    )
    frame = transport.encode_canonical_frame(request)
    if transport.validate_canonical_frame(frame) != request:
        raise C3NamedSessionPreviewError("C3 frame does not round-trip canonically")
    body = frame[4:]
    if (
        primitives.sha256_bytes(body) != REVIEW_REQUEST_SHA256
        or len(frame) != REVIEW_FRAME_BYTE_COUNT
        or request["semantic_request_id"] != REVIEW_SEMANTIC_REQUEST_ID
        or request["connection_binding_hash"] != REVIEW_CONNECTION_BINDING_HASH
    ):
        raise C3NamedSessionPreviewError("C3 review vector does not match the approved Corebox contract")
    return challenge, request, frame


def run_zero_write_preview(*, input_dir: Path) -> dict[str, Any]:
    """Validate fixed input and session ordering without any socket or write."""
    _validate_fixed_fixture_path_safety(input_dir)
    fixture = _fixture_preview(input_dir)
    challenge, request, frame = _review_vector()
    return {
        "schema_version": RUNNER_PREVIEW_SCHEMA,
        "status": "preview_refusal_only",
        "revisions": {
            "solo_foundation_commit": SOLO_FOUNDATION_REVISION,
            "corebox_preview_contract_commit": COREBOX_PREVIEW_CONTRACT_REVISION,
            "corebox_execution_commit": COREBOX_EXECUTION_REVISION,
        },
        "fixture": fixture["fixture"],
        "c1_validation": fixture["checks"]["c1_envelope_validation"],
        "review_vector": {
            "proof_id": request["proof_id"],
            "receipt_recorded_at": REVIEW_RECEIPT_RECORDED_AT,
            "challenge_integrity": primitives.integrity_for_bytes(primitives.canonical_json_bytes(challenge)),
            "request_integrity": primitives.integrity_for_bytes(frame[4:]),
            "frame_byte_count": len(frame),
            "semantic_request_id": request["semantic_request_id"],
            "connection_binding_hash": request["connection_binding_hash"],
        },
        "planned_session": {
            "transport": "AF_UNIX/SOCK_STREAM only",
            "peer_verification": "same_effective_uid_immediately_after_accept",
            "framing": {"mode": "ordinary_recv_send", "max_frame_bytes": transport.MAX_FRAME_BYTES, "ancillary_data": False},
            "request_sequence": ["one_accepted_exact_request", "one_exact_duplicate_same_connection"],
            "validation_order": ["fixed_fixture", "C1_envelope", "request_binding", "local_lifecycle"],
            "cleanup": ["close_connection", "close_listener", "unlink_socket", "remove_runtime", "remove_lifecycle_roots"],
            "evidence": "sanitized_only_no_uid_path_or_nonce",
        },
        "socket_session_executed": False,
        "fixture_submission_performed": False,
        "lifecycle_execution_performed": False,
        "writes_performed": False,
        "network_or_cloud_calls": 0,
        "execution_authorized": False,
    }


def refuse_named_session_execution() -> None:
    """Refuse before creating runtime state or touching a socket API."""
    raise C3NamedSessionExecutionNotAuthorized(
        "C3 named-session execution requires a separate owner-approved proof decision"
    )


def _load_validated_lifecycle_input(input_dir: Path) -> tuple[dict[str, Any], bytes]:
    """Read the already C1-validated harmless envelope/original for future use."""
    try:
        envelope_raw = (input_dir / "envelope.json").read_bytes()
        envelope = primitives.canonical_json_value(json.loads(envelope_raw))
        original = (input_dir / "original.bin").read_bytes()
    except (OSError, ValueError) as exc:
        raise C3NamedSessionProtocolError("fixed fixture lifecycle input cannot be read") from exc
    if primitives.canonical_json_bytes(envelope) != envelope_raw:
        raise C3NamedSessionProtocolError("fixed envelope is not canonical")
    try:
        return ingress.validate_synthetic_envelope(envelope, original), original
    except ingress.SyntheticIngressError as exc:
        raise C3NamedSessionProtocolError("fixed fixture C1 envelope validation failed") from exc


def _require_lifecycle_result(result: Mapping[str, Any], expected_status: str) -> dict[str, Any]:
    if not isinstance(result, Mapping) or result.get("status") != expected_status:
        raise C3NamedSessionProtocolError(f"local lifecycle did not return {expected_status}")
    receipt = result.get("receipt")
    if not isinstance(receipt, Mapping):
        raise C3NamedSessionProtocolError(f"local lifecycle {expected_status} result has no receipt")
    return dict(receipt)


def _start_one_fixture_lifecycle(
    *, lifecycle_root: Path, envelope: Mapping[str, Any], original: bytes, receipt_recorded_at: str
) -> tuple[ingress.LocalSyntheticSourceIngress, dict[str, Any]]:
    """Start future local lifecycle only after the first bound request validates."""
    local = ingress.LocalSyntheticSourceIngress(lifecycle_root)
    accepted = _require_lifecycle_result(
        local.submit(envelope, original, receipt_recorded_at=receipt_recorded_at), "accepted"
    )
    accepted = ingress.verify_synthetic_receipt(envelope, original, accepted)
    return local, accepted


def _finish_one_fixture_lifecycle(
    *, local: ingress.LocalSyntheticSourceIngress, envelope: Mapping[str, Any], original: bytes, accepted: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Finish future lifecycle only after the exact duplicate request validates."""
    duplicate = _require_lifecycle_result(local.submit(envelope, original), "duplicate")
    duplicate = ingress.verify_synthetic_receipt(envelope, original, duplicate)
    if duplicate["receipt_id"] != accepted["receipt_id"]:
        raise C3NamedSessionProtocolError("accepted and duplicate lifecycle receipts differ")
    readback = local.readback_original(envelope, original, accepted)
    if primitives.integrity_for_bytes(readback) != primitives.integrity_for_bytes(original):
        raise C3NamedSessionProtocolError("local lifecycle original readback differs")
    exported = local.export()
    if exported.get("status") != "passed" or exported.get("cursor") != 1:
        raise C3NamedSessionProtocolError("local lifecycle export is not one-receipt passed state")
    return duplicate, exported


def execute_one_shot_session(
    *,
    input_dir: Path,
    proof_id: str,
    receipt_recorded_at: str,
    runtime_parent: Path,
    evidence_dir: Path,
    solo_revision: str,
    corebox_revision: str,
    execution_authorized: bool,
    on_listener_ready: Callable[[Path, Path], None] | None = None,
) -> dict[str, Any]:
    """Execute one future owner-confirmed session; never used by this revision's CLI.

    The authorization argument is deliberately explicit so a future named proof
    path cannot accidentally reuse the preview default. Tests mock every socket
    primitive; this implementation is not invoked in the current checkpoint.
    """
    if execution_authorized is not True:
        refuse_named_session_execution()
    if _require_revision(solo_revision, field="solo_revision") != SOLO_EXECUTION_REVISION:
        raise C3NamedSessionProtocolError("C3 execution requires the reviewed Solo server revision")
    if _require_revision(corebox_revision, field="corebox_revision") != COREBOX_EXECUTION_REVISION:
        raise C3NamedSessionProtocolError("C3 execution requires the reviewed Corebox client revision")
    _require_named_proof_and_receipt(proof_id, receipt_recorded_at)
    _require_fresh_evidence_destination(evidence_dir)
    _validate_fixed_fixture_path_safety(input_dir)
    _fixture_preview(input_dir)
    envelope, original = _load_validated_lifecycle_input(input_dir)
    if not runtime_parent.is_absolute() or not runtime_parent.is_dir():
        raise C3NamedSessionProtocolError("C3 runtime parent must be an existing absolute directory")
    runtime: Path | None = None
    listener = None
    connection = None
    socket_path: Path | None = None
    result: dict[str, Any] | None = None
    try:
        runtime = transport.create_private_runtime_directory(runtime_parent)
        listener, socket_path = transport.bind_private_unix_listener(runtime)
        if on_listener_ready is not None:
            on_listener_ready(runtime, socket_path)
        listener.settimeout(30)
        connection, _unused_peer_address = listener.accept()
        connection.settimeout(30)
        # This must remain the first action after accept; do not retain peer data.
        transport.require_same_effective_uid(connection)
        challenge = transport.build_challenge(
            proof_id=proof_id,
            fixture_manifest_sha256=transport.fixed_c2_fixture_integrities()["fixture_manifest"]["sha256"],
        )
        transport.send_canonical_frame(connection, challenge)
        request = transport.receive_canonical_frame(connection)
        request = transport.validate_fixed_fixture_request(
            request,
            challenge=challenge,
            fixture_integrities=transport.fixed_c2_fixture_integrities(),
            receipt_recorded_at=receipt_recorded_at,
        )
        with tempfile.TemporaryDirectory(prefix="lifecycle-", dir=runtime) as lifecycle_directory:
            local, accepted = _start_one_fixture_lifecycle(
                lifecycle_root=Path(lifecycle_directory),
                envelope=envelope,
                original=original,
                receipt_recorded_at=receipt_recorded_at,
            )
            accepted_response = transport.build_receipt_response(
                semantic_request_id=request["semantic_request_id"], status="accepted", receipt=accepted
            )
            transport.send_canonical_frame(connection, accepted_response)
            duplicate_request = transport.receive_canonical_frame(connection)
            transport.require_exact_duplicate(request, duplicate_request)
            _duplicate_from_lifecycle, exported = _finish_one_fixture_lifecycle(
                local=local, envelope=envelope, original=original, accepted=accepted
            )
            duplicate_response = transport.build_receipt_response(
                semantic_request_id=request["semantic_request_id"], status="duplicate", receipt=accepted
            )
            transport.send_canonical_frame(connection, duplicate_response)
            result = {
                "schema_version": SESSION_RESULT_SCHEMA,
                "status": "passed",
                "proof_id": proof_id,
                "receipt_recorded_at": receipt_recorded_at,
                "same_local_uid": True,
                "semantic_request_id": request["semantic_request_id"],
                "connection_binding_hash": request["connection_binding_hash"],
                "receipt_id": accepted["receipt_id"],
                "export_cursor": exported["cursor"],
                "ephemeral_lifecycle_roots_created": 1,
                "ephemeral_lifecycle_roots_removed": 1,
                "revisions": {
                    "solo_revision": solo_revision,
                    "corebox_revision": corebox_revision,
                },
                "network_or_cloud_calls": 0,
                "vm_or_core_runtime_changes": 0,
            }
    finally:
        if connection is not None:
            connection.close()
        if listener is not None and runtime is not None and socket_path is not None:
            transport.cleanup_private_unix_listener(listener, runtime, socket_path)
            if result is not None:
                result["cleanup"] = "passed"
        elif runtime is not None:
            transport.cleanup_private_runtime_directory(runtime)
    if result is None:
        raise C3NamedSessionProtocolError("C3 session completed without a result")
    evidence = _require_fresh_evidence_destination(evidence_dir)
    evidence.mkdir()
    (evidence / "c3-session-result.json").write_bytes(primitives.canonical_json_bytes(result))
    return result


def install_no_session_audit_guard() -> None:
    """Prevent accidental socket/process use while this preview runner executes."""
    forbidden_prefixes = ("socket.", "subprocess.")

    def deny(event: str, _args: tuple[Any, ...]) -> None:
        if event.startswith(forbidden_prefixes):
            raise C3NamedSessionPreviewError(f"preview blocked forbidden process event: {event}")

    sys.addaudithook(deny)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preview/refuse one future C3 named Unix-socket session")
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--confirm-c3-local-transport-proof", action="store_true")
    parser.add_argument("--proof-id")
    parser.add_argument("--receipt-recorded-at")
    parser.add_argument("--runtime-parent", type=Path)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--solo-revision")
    parser.add_argument("--corebox-revision")
    return parser.parse_args(argv)


def require_named_execution_arguments(args: argparse.Namespace) -> None:
    required = {
        "proof_id": args.proof_id,
        "receipt_recorded_at": args.receipt_recorded_at,
        "runtime_parent": args.runtime_parent,
        "evidence_dir": args.evidence_dir,
        "solo_revision": args.solo_revision,
        "corebox_revision": args.corebox_revision,
    }
    missing = sorted(name for name, value in required.items() if value is None)
    if missing:
        raise C3NamedSessionExecutionNotAuthorized(
            "C3 named execution requires explicit " + ", ".join(missing)
        )
    try:
        _require_named_proof_and_receipt(args.proof_id, args.receipt_recorded_at)
    except C3NamedSessionProtocolError as exc:
        raise C3NamedSessionExecutionNotAuthorized(str(exc)) from exc
    if _require_revision(args.solo_revision, field="solo_revision") != SOLO_EXECUTION_REVISION:
        raise C3NamedSessionExecutionNotAuthorized("C3 named execution requires the reviewed Solo server revision")
    if _require_revision(args.corebox_revision, field="corebox_revision") != COREBOX_EXECUTION_REVISION:
        raise C3NamedSessionExecutionNotAuthorized("C3 named execution requires the reviewed Corebox client revision")
    if not args.runtime_parent.is_absolute() or not args.evidence_dir.is_absolute():
        raise C3NamedSessionExecutionNotAuthorized("C3 runtime and evidence paths must be absolute")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        install_no_session_audit_guard()
        if args.confirm_c3_local_transport_proof:
            require_named_execution_arguments(args)
            refuse_named_session_execution()
        preview = run_zero_write_preview(input_dir=args.input_dir)
    except C3NamedSessionPreviewError as exc:
        print(f"C3 named-session preview refused: {exc}", file=sys.stderr)
        return 2
    print(primitives.canonical_json_bytes(preview).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
