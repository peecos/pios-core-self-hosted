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
import os
import stat
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import pios_canonical_source_primitives as primitives
from scripts import pios_c3_local_transport as transport
from scripts import run_pios_solo_c2_synthetic_proof as c2

RUNNER_PREVIEW_SCHEMA = "pios_solo_c3_named_session_zero_write_preview_v1"
SOLO_FOUNDATION_REVISION = "45c5bac"
COREBOX_CONTRACT_REVISION = "1db18d5"
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
            "corebox_contract_commit": COREBOX_CONTRACT_REVISION,
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
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        install_no_session_audit_guard()
        if args.confirm_c3_local_transport_proof:
            refuse_named_session_execution()
        preview = run_zero_write_preview(input_dir=args.input_dir)
    except C3NamedSessionPreviewError as exc:
        print(f"C3 named-session preview refused: {exc}", file=sys.stderr)
        return 2
    print(primitives.canonical_json_bytes(preview).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
