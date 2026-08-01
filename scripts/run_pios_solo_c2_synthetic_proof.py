#!/usr/bin/env python3
"""Fail-closed C2 synthetic-fixture runner.

This command validates the immutable Corebox C2 fixture using only the
existing B1/C1 Python validators. The default mode is a zero-write preview.
The explicitly confirmed local execution mode creates only disposable local
lifecycle state and a reviewed harmless evidence package; it has no transport,
network/cloud/VM, credential, or Core-runtime path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
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
RUNNER_RESULT_SCHEMA = "pios_solo_c2_synthetic_proof_result_v1"
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
SOLO_REVISION_RE = re.compile(r"[0-9a-f]{7,64}")
UTC_SECONDS_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


class C2PreviewError(ValueError):
    """Raised when the immutable C2 fixture cannot be previewed safely."""


class C2ExecutionNotAuthorized(C2PreviewError):
    """Raised when a caller tries to run without all execution gates."""


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


def _validate_execution_inputs(
    *,
    proof_id: str | None,
    receipt_recorded_at: str | None,
    solo_revision: str | None,
    evidence_dir: Path | None,
    work_root: Path | None,
) -> tuple[str, str, str, Path, Path]:
    _validate_optional_decision_inputs(proof_id, receipt_recorded_at)
    if proof_id is None or receipt_recorded_at is None:
        raise C2ExecutionNotAuthorized("confirmed execution requires proof_id and receipt_recorded_at")
    if not isinstance(solo_revision, str) or not SOLO_REVISION_RE.fullmatch(solo_revision):
        raise C2ExecutionNotAuthorized("confirmed execution requires a lowercase Solo revision")
    if evidence_dir is None or not evidence_dir.is_absolute():
        raise C2ExecutionNotAuthorized("confirmed execution requires an absolute evidence_dir")
    if work_root is None or not work_root.is_absolute() or not work_root.is_dir():
        raise C2ExecutionNotAuthorized("confirmed execution requires an existing absolute work_root")
    if evidence_dir.exists():
        raise C2ExecutionNotAuthorized("evidence_dir must not already exist")
    return proof_id, receipt_recorded_at, solo_revision, evidence_dir, work_root


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


def _require_outcome(result: Mapping[str, Any], *, status: str, code: str | None = None) -> dict[str, Any]:
    if not isinstance(result, Mapping) or result.get("status") != status:
        raise C2PreviewError(f"unexpected local lifecycle status: expected {status}")
    if code is not None and result.get("code") != code:
        raise C2PreviewError(f"unexpected local lifecycle code: expected {code}")
    return dict(result)


def _write_canonical(path: Path, value: Mapping[str, Any]) -> bytes:
    content = primitives.canonical_json_bytes(value)
    path.write_bytes(content)
    return content


def _copy_fixture_inputs(input_dir: Path, destination: Path) -> dict[str, dict[str, Any]]:
    destination.mkdir(parents=True, exist_ok=False)
    copied: dict[str, dict[str, Any]] = {}
    for name in sorted(REQUIRED_FILES):
        source = input_dir / name
        target = destination / name
        shutil.copyfile(source, target)
        source_bytes = source.read_bytes()
        if target.read_bytes() != source_bytes:
            raise C2PreviewError(f"evidence input copy differs: {name}")
        copied[name] = _integrity(source_bytes)
    return copied


def _write_sanitized_failure_marker(evidence_dir: Path, proof_id: str, error: Exception) -> None:
    marker = evidence_dir.with_name(f"{evidence_dir.name}.failed.json")
    if marker.exists():
        return
    _write_canonical(
        marker,
        {
            "schema_version": "pios_solo_c2_synthetic_proof_failure_v1",
            "status": "failed",
            "proof_id": proof_id,
            "failure_class": type(error).__name__,
            "raw_fixture_retained": False,
            "temporary_lifecycle_state_retained": False,
        },
    )


def _run_main_lifecycle(
    root: Path, envelope: Mapping[str, Any], original: bytes, receipt_recorded_at: str
) -> dict[str, Any]:
    local = ingress.LocalSyntheticSourceIngress(root)
    accepted = _require_outcome(
        local.submit(envelope, original, receipt_recorded_at=receipt_recorded_at), status="accepted"
    )
    accepted_receipt = accepted.get("receipt")
    if not isinstance(accepted_receipt, Mapping):
        raise C2PreviewError("accepted lifecycle result has no receipt")
    verified_accepted = ingress.verify_synthetic_receipt(envelope, original, accepted_receipt)
    duplicate = _require_outcome(local.submit(envelope, original), status="duplicate")
    duplicate_receipt = duplicate.get("receipt")
    if not isinstance(duplicate_receipt, Mapping):
        raise C2PreviewError("duplicate lifecycle result has no receipt")
    verified_duplicate = ingress.verify_synthetic_receipt(envelope, original, duplicate_receipt)
    if verified_accepted["receipt_id"] != verified_duplicate["receipt_id"]:
        raise C2PreviewError("accepted and duplicate receipts do not share one receipt ID")
    readback = local.readback_original(envelope, original, verified_accepted)
    if _integrity(readback) != _integrity(original):
        raise C2PreviewError("readback original does not match fixture original")
    exported = local.export()
    if exported.get("profile") != PROFILE or exported.get("status") != "passed" or exported.get("cursor") != 1:
        raise C2PreviewError("local export is not the expected one-receipt result")
    receipts = exported.get("receipts")
    if not isinstance(receipts, list) or len(receipts) != 1:
        raise C2PreviewError("local export did not retain exactly one accepted receipt")
    ingress.verify_synthetic_receipt(envelope, original, receipts[0])
    return {
        "accepted_receipt": verified_accepted,
        "duplicate_receipt": verified_duplicate,
        "export": exported,
        "readback_integrity": _integrity(readback),
    }


def _run_denied_lifecycle(root: Path, envelope: Mapping[str, Any], original: bytes) -> dict[str, Any]:
    local = ingress.LocalSyntheticSourceIngress(root)
    denied = _require_outcome(local.submit(envelope, original, test_outcome="deny"), status="denied", code="synthetic_denied")
    if denied.get("retryable") is not False or "receipt" in denied:
        raise C2PreviewError("denied lifecycle result is not fail-closed")
    return denied


def _run_revoked_lifecycle(root: Path, envelope: Mapping[str, Any], original: bytes) -> dict[str, Any]:
    local = ingress.LocalSyntheticSourceIngress(root)
    revoked = local.revoke()
    if revoked != {"profile": PROFILE, "status": "revoked", "code": "grant_revoked"}:
        raise C2PreviewError("synthetic revocation result is not canonical")
    blocked = _require_outcome(local.submit(envelope, original), status="denied", code="grant_revoked")
    if blocked.get("retryable") is not False:
        raise C2PreviewError("revoked lifecycle result is unexpectedly retryable")
    return {"revoke": revoked, "blocked_submit": blocked}


def _run_retry_lifecycle(
    root: Path, envelope: Mapping[str, Any], original: bytes, receipt_recorded_at: str
) -> dict[str, Any]:
    local = ingress.LocalSyntheticSourceIngress(root)
    retry = _require_outcome(local.submit(envelope, original, test_outcome="retry_once"), status="retry", code="synthetic_transient")
    if retry.get("retryable") is not True:
        raise C2PreviewError("retry lifecycle result is not retryable")
    accepted = _require_outcome(
        local.submit(
            envelope,
            original,
            test_outcome="retry_once",
            receipt_recorded_at=receipt_recorded_at,
        ),
        status="accepted",
    )
    receipt = accepted.get("receipt")
    if not isinstance(receipt, Mapping):
        raise C2PreviewError("retried lifecycle result has no accepted receipt")
    return {"retry": retry, "accepted_receipt": ingress.verify_synthetic_receipt(envelope, original, receipt)}


def execute_local_synthetic_proof(
    *,
    input_dir: Path,
    expected_original_sha256: str,
    expected_envelope_sha256: str,
    expected_zero_write_preview_sha256: str,
    expected_fixture_manifest_sha256: str,
    proof_id: str | None,
    receipt_recorded_at: str | None,
    solo_revision: str | None,
    evidence_dir: Path | None,
    work_root: Path | None,
    confirmed: bool,
) -> dict[str, Any]:
    """Run the local-only C2 lifecycle with explicit gates and cleanup.

    This function is intentionally not called for the fixed owner fixture until
    a separate named execution decision supplies every argument.
    """
    if confirmed is not True:
        raise C2ExecutionNotAuthorized("local lifecycle execution requires explicit confirmation")
    proof_id, receipt_recorded_at, solo_revision, evidence_dir, work_root = _validate_execution_inputs(
        proof_id=proof_id,
        receipt_recorded_at=receipt_recorded_at,
        solo_revision=solo_revision,
        evidence_dir=evidence_dir,
        work_root=work_root,
    )
    if evidence_dir == input_dir or input_dir in evidence_dir.parents or evidence_dir in input_dir.parents:
        raise C2ExecutionNotAuthorized("evidence_dir must be separate from immutable fixture input")
    preview = run_zero_write_preview(
        input_dir=input_dir,
        expected_original_sha256=expected_original_sha256,
        expected_envelope_sha256=expected_envelope_sha256,
        expected_zero_write_preview_sha256=expected_zero_write_preview_sha256,
        expected_fixture_manifest_sha256=expected_fixture_manifest_sha256,
        proof_id=proof_id,
        receipt_recorded_at=receipt_recorded_at,
    )
    original = (input_dir / "original.bin").read_bytes()
    _, envelope = _read_json(input_dir / "envelope.json")
    evidence_parent = evidence_dir.parent
    if not evidence_parent.is_dir():
        raise C2ExecutionNotAuthorized("evidence_dir parent must already exist")
    stage: Path | None = None
    work_directory: Path | None = None
    try:
        stage = Path(tempfile.mkdtemp(prefix=f".{proof_id}-", dir=evidence_parent))
        copied_inputs = _copy_fixture_inputs(input_dir, stage / "input")
        with tempfile.TemporaryDirectory(prefix=f"{proof_id}-", dir=work_root) as temporary:
            work_directory = Path(temporary)
            main = _run_main_lifecycle(work_directory / "main", envelope, original, receipt_recorded_at)
            denied = _run_denied_lifecycle(work_directory / "denied", envelope, original)
            revoked = _run_revoked_lifecycle(work_directory / "revoked", envelope, original)
            retry = _run_retry_lifecycle(work_directory / "retry", envelope, original, receipt_recorded_at)
            _write_canonical(stage / "accepted-receipt.json", main["accepted_receipt"])
            _write_canonical(stage / "duplicate-receipt.json", main["duplicate_receipt"])
            _write_canonical(stage / "export.json", main["export"])
            _write_canonical(
                stage / "outcomes.json",
                {"denied": denied, "revoked": revoked, "retry": retry, "readback_integrity": main["readback_integrity"]},
            )
        if work_directory.exists():
            raise C2PreviewError("temporary lifecycle root was not removed")
        result = {
            "schema_version": RUNNER_RESULT_SCHEMA,
            "status": "passed",
            "proof_id": proof_id,
            "receipt_recorded_at": receipt_recorded_at,
            "solo_revision": solo_revision,
            "runner_source_integrity": _integrity(Path(__file__).read_bytes()),
            "preview": preview,
            "input_artifacts": copied_inputs,
            "receipt_id": main["accepted_receipt"]["receipt_id"],
            "accepted_receipt_integrity": _integrity(primitives.canonical_json_bytes(main["accepted_receipt"])),
            "duplicate_receipt_integrity": _integrity(primitives.canonical_json_bytes(main["duplicate_receipt"])),
            "cleanup": {"temporary_lifecycle_roots": 4, "status": "passed"},
            "network_or_cloud_calls": 0,
            "vm_or_core_runtime_changes": 0,
        }
        result_bytes = _write_canonical(stage / "result-manifest.json", result)
        if primitives.canonical_json_bytes(json.loads(result_bytes)) != result_bytes:
            raise C2PreviewError("result manifest is not canonical")
        os.replace(stage, evidence_dir)
        return result
    except Exception as exc:
        if stage is not None and stage.exists():
            shutil.rmtree(stage)
        _write_sanitized_failure_marker(evidence_dir, proof_id, exc)
        raise
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
    parser.add_argument("--solo-revision")
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--confirm-c2-local-synthetic-proof", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        install_no_network_audit_guard()
        if args.confirm_c2_local_synthetic_proof:
            result = execute_local_synthetic_proof(
                input_dir=args.input_dir,
                expected_original_sha256=args.expected_original_sha256,
                expected_envelope_sha256=args.expected_envelope_sha256,
                expected_zero_write_preview_sha256=args.expected_zero_write_preview_sha256,
                expected_fixture_manifest_sha256=args.expected_fixture_manifest_sha256,
                proof_id=args.proof_id,
                receipt_recorded_at=args.receipt_recorded_at,
                solo_revision=args.solo_revision,
                evidence_dir=args.evidence_dir,
                work_root=Path("/private/tmp"),
                confirmed=True,
            )
            print(primitives.canonical_json_bytes(result).decode("utf-8"))
            return 0
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
