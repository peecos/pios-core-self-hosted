#!/usr/bin/env python3
"""Fail-closed, zero-write C2 synthetic-fixture preview.

This command validates the immutable Corebox C2 fixture using only the
existing B1/C1 Python validators. It deliberately does not create a local
lifecycle root, submit an envelope, issue a receipt, write evidence, or make a
network/cloud/VM call. Supplying the future execution confirmation flag exits
with an error until separately authorized execution work is implemented.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import pios_canonical_source_primitives as primitives
from scripts import pios_synthetic_source_ingress as ingress

FIXTURE_SCHEMA = "corebox_c2_synthetic_fixture_manifest_v1"
PREVIEW_SCHEMA = "corebox_c2_synthetic_zero_write_preview_v1"
RUNNER_PREVIEW_SCHEMA = "pios_solo_c2_zero_write_preview_v1"
FIXTURE_STATUS = "prepared_not_authorized"
FIXTURE_ID = "corebox_c2_harmless_text_v1"
FIXTURE_SOURCE = "CoreboxC2SyntheticFixtureBuilder"
PROFILE = "pios_synthetic_source_ingress_v1"
ARTIFACT_NAMES = frozenset(
    {"original.bin", "envelope.json", "corebox-c2-zero-write-preview.json"}
)
REQUIRED_FILES = ARTIFACT_NAMES | {"fixture-manifest.json"}
EXPECTED_AUTHORIZATION = {
    "app_networking": False,
    "c2_execution": False,
    "credentials": False,
    "device_enrollment": False,
    "endpoint": False,
    "local_fixture_export": True,
    "personal_data": False,
}
EXPECTED_LIFECYCLE_CHECKS = [
    "accepted",
    "duplicate",
    "denied",
    "retry",
    "revoked",
    "readback",
    "export",
]
SHA256_RE = re.compile(r"[0-9a-f]{64}")
PROOF_ID_RE = re.compile(r"c2-[a-z0-9-]{1,100}")
UTC_SECONDS_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


class C2PreviewError(ValueError):
    """Raised when the immutable C2 fixture cannot be previewed safely."""


class C2ExecutionNotAuthorized(C2PreviewError):
    """Raised when a caller tries to run a lifecycle through this preview tool."""


def _integrity(value: bytes) -> dict[str, Any]:
    return {"sha256": hashlib.sha256(value).hexdigest(), "byte_count": len(value)}


def _read_json(path: Path) -> tuple[bytes, dict[str, Any]]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise C2PreviewError(f"cannot read canonical JSON artifact: {path.name}") from exc
    if not isinstance(value, dict):
        raise C2PreviewError(f"JSON artifact must be an object: {path.name}")
    if primitives.canonical_json_bytes(value) != raw:
        raise C2PreviewError(f"JSON artifact is not exact B1 canonical bytes: {path.name}")
    return raw, value


def _expected_sha256(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise C2PreviewError(f"{field} must be a lowercase SHA-256 value")
    return value


def _assert_integrity(name: str, raw: bytes, expected: Mapping[str, Any], supplied_sha256: str) -> None:
    if not isinstance(expected, Mapping) or set(expected) != {"sha256", "byte_count"}:
        raise C2PreviewError(f"fixture manifest integrity shape is invalid: {name}")
    actual = _integrity(raw)
    if expected != actual:
        raise C2PreviewError(f"fixture artifact integrity mismatch: {name}")
    if supplied_sha256 != actual["sha256"]:
        raise C2PreviewError(f"approved SHA-256 does not match fixture artifact: {name}")


def _validate_optional_decision_inputs(proof_id: str | None, receipt_recorded_at: str | None) -> None:
    if proof_id is not None and (not isinstance(proof_id, str) or not PROOF_ID_RE.fullmatch(proof_id)):
        raise C2PreviewError("proof_id must use c2- plus lowercase safe tokens")
    if receipt_recorded_at is not None:
        if not isinstance(receipt_recorded_at, str) or not UTC_SECONDS_RE.fullmatch(receipt_recorded_at):
            raise C2PreviewError("receipt_recorded_at must be a UTC whole-second timestamp")
        try:
            datetime.fromisoformat(receipt_recorded_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise C2PreviewError("receipt_recorded_at is invalid") from exc


def _validate_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "artifacts",
        "authorization",
        "expected_lifecycle_checks",
        "fixture_id",
        "profile",
        "schema_version",
        "source",
        "status",
    }
    if set(manifest) != required:
        raise C2PreviewError("fixture manifest fields are not the reviewed contract shape")
    if manifest["schema_version"] != FIXTURE_SCHEMA:
        raise C2PreviewError("fixture manifest schema is not supported")
    if manifest["fixture_id"] != FIXTURE_ID or manifest["source"] != FIXTURE_SOURCE:
        raise C2PreviewError("fixture identity/source is not the reviewed harmless fixture")
    if manifest["profile"] != PROFILE or manifest["status"] != FIXTURE_STATUS:
        raise C2PreviewError("fixture is not the prepared C2 synthetic profile")
    if manifest["authorization"] != EXPECTED_AUTHORIZATION:
        raise C2PreviewError("fixture authorization gates are not all in the reviewed state")
    if manifest["expected_lifecycle_checks"] != EXPECTED_LIFECYCLE_CHECKS:
        raise C2PreviewError("fixture lifecycle checks are not the reviewed C2 plan")
    artifacts = manifest["artifacts"]
    if not isinstance(artifacts, Mapping) or set(artifacts) != ARTIFACT_NAMES:
        raise C2PreviewError("fixture artifacts are not the reviewed C2 input set")
    return dict(manifest)


def _validate_zero_write_preview(
    preview: Mapping[str, Any], manifest: Mapping[str, Any], envelope: Mapping[str, Any]
) -> None:
    required = {
        "app_networking",
        "c2_execution",
        "client_capture_id",
        "client_item_id",
        "cloud_calls",
        "device_enrollment",
        "envelope_integrity",
        "fixture_id",
        "integration_id",
        "network_calls",
        "origin_device_id",
        "original_integrity",
        "owner_id",
        "profile",
        "real_personal_file_intake",
        "schema_version",
        "status",
    }
    if set(preview) != required:
        raise C2PreviewError("zero-write preview fields are not the reviewed contract shape")
    expected_false = {
        "app_networking",
        "c2_execution",
        "device_enrollment",
        "real_personal_file_intake",
    }
    if any(preview[name] is not False for name in expected_false):
        raise C2PreviewError("zero-write preview contains an enabled operation")
    if preview["network_calls"] != 0 or preview["cloud_calls"] != 0:
        raise C2PreviewError("zero-write preview reports network or cloud activity")
    if (
        preview["schema_version"] != PREVIEW_SCHEMA
        or preview["fixture_id"] != manifest["fixture_id"]
        or preview["profile"] != PROFILE
        or preview["status"] != FIXTURE_STATUS
    ):
        raise C2PreviewError("zero-write preview identity does not match fixture manifest")
    for field in ("owner_id", "integration_id", "origin_device_id", "client_capture_id", "client_item_id"):
        if preview[field] != envelope[field]:
            raise C2PreviewError(f"zero-write preview does not bind envelope {field}")
    for field, artifact in (("envelope_integrity", "envelope.json"), ("original_integrity", "original.bin")):
        if preview[field] != manifest["artifacts"][artifact]:
            raise C2PreviewError(f"zero-write preview integrity does not bind {artifact}")


def run_zero_write_preview(
    *,
    input_dir: Path,
    expected_original_sha256: str,
    expected_envelope_sha256: str,
    expected_zero_write_preview_sha256: str,
    expected_fixture_manifest_sha256: str,
    proof_id: str | None = None,
    receipt_recorded_at: str | None = None,
) -> dict[str, Any]:
    """Verify one immutable C2 input without creating any lifecycle state."""
    expected_hashes = {
        "original.bin": _expected_sha256(expected_original_sha256, field="expected_original_sha256"),
        "envelope.json": _expected_sha256(expected_envelope_sha256, field="expected_envelope_sha256"),
        "corebox-c2-zero-write-preview.json": _expected_sha256(
            expected_zero_write_preview_sha256,
            field="expected_zero_write_preview_sha256",
        ),
    }
    expected_fixture_manifest_sha256 = _expected_sha256(
        expected_fixture_manifest_sha256,
        field="expected_fixture_manifest_sha256",
    )
    _validate_optional_decision_inputs(proof_id, receipt_recorded_at)
    if not input_dir.is_dir():
        raise C2PreviewError("input_dir must be an existing fixture directory")
    entries = {path.name for path in input_dir.iterdir()}
    if entries != REQUIRED_FILES:
        raise C2PreviewError("fixture directory contains missing or unreviewed files")

    manifest_raw, manifest = _read_json(input_dir / "fixture-manifest.json")
    if _integrity(manifest_raw)["sha256"] != expected_fixture_manifest_sha256:
        raise C2PreviewError("approved SHA-256 does not match fixture-manifest.json")
    manifest = _validate_manifest(manifest)

    artifact_bytes = {name: (input_dir / name).read_bytes() for name in ARTIFACT_NAMES}
    for name in ARTIFACT_NAMES:
        _assert_integrity(name, artifact_bytes[name], manifest["artifacts"][name], expected_hashes[name])

    envelope_raw, envelope = _read_json(input_dir / "envelope.json")
    if envelope_raw != artifact_bytes["envelope.json"]:
        raise C2PreviewError("fixture envelope read is inconsistent")
    normalized = ingress.validate_synthetic_envelope(envelope, artifact_bytes["original.bin"])
    preview_raw, preview = _read_json(input_dir / "corebox-c2-zero-write-preview.json")
    if preview_raw != artifact_bytes["corebox-c2-zero-write-preview.json"]:
        raise C2PreviewError("fixture zero-write preview read is inconsistent")
    _validate_zero_write_preview(preview, manifest, normalized)

    return {
        "schema_version": RUNNER_PREVIEW_SCHEMA,
        "mode": "zero_write_preview",
        "status": FIXTURE_STATUS,
        "fixture": {
            "fixture_id": manifest["fixture_id"],
            "source": manifest["source"],
            "profile": manifest["profile"],
            "fixture_manifest_integrity": _integrity(manifest_raw),
            "artifacts": {name: _integrity(artifact_bytes[name]) for name in sorted(ARTIFACT_NAMES)},
        },
        "decision_inputs": {
            "proof_id": proof_id,
            "receipt_recorded_at": receipt_recorded_at,
        },
        "checks": {
            "manifest_artifacts": "passed",
            "authorization_gates": "passed",
            "zero_write_preview": "passed",
            "canonical_envelope": "passed",
            "c1_envelope_validation": "passed",
            "network_guard": "installed",
        },
        "execution_authorized": False,
        "lifecycle_submission_performed": False,
        "writes_performed": False,
    }


def install_no_network_audit_guard() -> None:
    """Deny future socket or subprocess audit events in this CLI process."""
    forbidden_prefixes = ("socket.", "subprocess.")

    def deny(event: str, _args: tuple[Any, ...]) -> None:
        if event.startswith(forbidden_prefixes):
            raise C2PreviewError(f"zero-write preview blocked forbidden process event: {event}")

    sys.addaudithook(deny)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preview one immutable C2 synthetic fixture without writes")
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--expected-original-sha256", required=True)
    parser.add_argument("--expected-envelope-sha256", required=True)
    parser.add_argument("--expected-zero-write-preview-sha256", required=True)
    parser.add_argument("--expected-fixture-manifest-sha256", required=True)
    parser.add_argument("--proof-id")
    parser.add_argument("--receipt-recorded-at")
    parser.add_argument("--confirm-c2-local-synthetic-proof", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.confirm_c2_local_synthetic_proof:
        print(
            "C2 lifecycle execution is not implemented in this preview-only runner; "
            "a separate owner authorization and execution patch are required.",
            file=sys.stderr,
        )
        return 2
    try:
        install_no_network_audit_guard()
        preview = run_zero_write_preview(
            input_dir=args.input_dir,
            expected_original_sha256=args.expected_original_sha256,
            expected_envelope_sha256=args.expected_envelope_sha256,
            expected_zero_write_preview_sha256=args.expected_zero_write_preview_sha256,
            expected_fixture_manifest_sha256=args.expected_fixture_manifest_sha256,
            proof_id=args.proof_id,
            receipt_recorded_at=args.receipt_recorded_at,
        )
    except C2PreviewError as exc:
        print(f"C2 zero-write preview refused: {exc}", file=sys.stderr)
        return 2
    print(primitives.canonical_json_bytes(preview).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
