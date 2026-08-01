#!/usr/bin/env python3
"""Disabled-by-default command coordination for one future C3 local proof.

This module may validate and describe the exact two-process handoff, but its
CLI never creates a listener, starts a Corebox child, or writes evidence. The
internal execution function remains hard-disabled pending a separate decision
and review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import pios_canonical_source_primitives as primitives
from scripts import run_pios_solo_c3_named_session as session

ORCHESTRATOR_SCHEMA = "pios_solo_c3_command_orchestration_plan_v1"
SOLO_SERVER_REVISION = session.SOLO_EXECUTION_REVISION
COREBOX_CLIENT_REVISION = session.COREBOX_EXECUTION_REVISION
ORCHESTRATION_EXECUTION_ENABLED = False
PRIOR_PROOF_IDS = frozenset({session.REVIEW_PROOF_ID})
MAX_CHILD_OUTPUT_BYTES = 64 * 1024


class C3CommandOrchestrationError(ValueError):
    """Raised when the command coordinator cannot safely prepare a C3 proof."""


class C3CommandOrchestrationNotAuthorized(C3CommandOrchestrationError):
    """Raised for every execution attempt while the orchestrator is disabled."""


@dataclass(frozen=True)
class CoreboxToolIdentity:
    device: int
    inode: int
    size: int
    modified_ns: int
    sha256: str


@dataclass(frozen=True)
class NamedSessionPlan:
    input_dir: Path
    proof_id: str
    receipt_recorded_at: str
    runtime_parent: Path
    evidence_dir: Path
    corebox_tool: Path
    corebox_tool_identity: CoreboxToolIdentity
    solo_revision: str
    corebox_revision: str
    fixture: dict[str, Any]


def _open_corebox_tool(path: Path) -> tuple[int, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise C3CommandOrchestrationError("Corebox C3 tool cannot be opened safely") from exc
    details = os.fstat(descriptor)
    if not stat.S_ISREG(details.st_mode) or details.st_uid != os.geteuid() or details.st_mode & 0o111 == 0:
        os.close(descriptor)
        raise C3CommandOrchestrationError("Corebox C3 tool owner, type, or executable mode is unsafe")
    return descriptor, details


def _hash_descriptor(descriptor: int) -> str:
    digest = hashlib.sha256()
    os.lseek(descriptor, 0, os.SEEK_SET)
    while chunk := os.read(descriptor, 1024 * 1024):
        digest.update(chunk)
    os.lseek(descriptor, 0, os.SEEK_SET)
    return digest.hexdigest()


def _require_corebox_tool(path: Path) -> tuple[Path, CoreboxToolIdentity]:
    path = Path(path)
    if not path.is_absolute():
        raise C3CommandOrchestrationError("Corebox C3 tool path must be absolute")
    descriptor, details = _open_corebox_tool(path)
    try:
        identity = CoreboxToolIdentity(
            device=details.st_dev,
            inode=details.st_ino,
            size=details.st_size,
            modified_ns=details.st_mtime_ns,
            sha256=_hash_descriptor(descriptor),
        )
    finally:
        os.close(descriptor)
    return path, identity


def build_named_session_plan(
    *,
    input_dir: Path,
    proof_id: str,
    receipt_recorded_at: str,
    runtime_parent: Path,
    evidence_dir: Path,
    corebox_tool: Path,
    solo_revision: str,
    corebox_revision: str,
) -> NamedSessionPlan:
    if session._require_revision(solo_revision, field="solo_revision") != SOLO_SERVER_REVISION:
        raise C3CommandOrchestrationError("C3 orchestration requires the reviewed Solo server revision")
    if session._require_revision(corebox_revision, field="corebox_revision") != COREBOX_CLIENT_REVISION:
        raise C3CommandOrchestrationError("C3 orchestration requires the reviewed Corebox client revision")
    try:
        session._require_named_proof_and_receipt(proof_id, receipt_recorded_at)
        session._require_fresh_evidence_destination(evidence_dir)
    except session.C3NamedSessionPreviewError as exc:
        raise C3CommandOrchestrationError("C3 named input binding is invalid") from exc
    if proof_id in PRIOR_PROOF_IDS:
        raise C3CommandOrchestrationError("C3 orchestration requires a new proof ID")
    if not runtime_parent.is_absolute() or not runtime_parent.is_dir() or runtime_parent.is_symlink():
        raise C3CommandOrchestrationError("C3 runtime parent must be an existing absolute non-symlink directory")
    tool, tool_identity = _require_corebox_tool(corebox_tool)
    fixture = session.run_zero_write_preview(input_dir=input_dir)
    return NamedSessionPlan(
        input_dir=Path(input_dir),
        proof_id=proof_id,
        receipt_recorded_at=receipt_recorded_at,
        runtime_parent=Path(runtime_parent),
        evidence_dir=Path(evidence_dir),
        corebox_tool=tool,
        corebox_tool_identity=tool_identity,
        solo_revision=solo_revision,
        corebox_revision=corebox_revision,
        fixture=fixture["fixture"],
    )


def preview(plan: NamedSessionPlan) -> dict[str, Any]:
    """Return sanitized plan facts without exposing local paths or commands."""
    return {
        "schema_version": ORCHESTRATOR_SCHEMA,
        "status": "prepared_not_authorized",
        "proof_id": plan.proof_id,
        "receipt_recorded_at": plan.receipt_recorded_at,
        "revisions": {
            "solo_server_revision": plan.solo_revision,
            "corebox_client_revision": plan.corebox_revision,
            "command_orchestration_revision": "must_be_named_in_a_future_execution_decision",
            "corebox_command_interface_revision": "must_be_named_in_a_future_execution_decision",
        },
        "fixture": plan.fixture,
        "planned_processes": ["one_solo_server", "one_corebox_developer_tool"],
        "planned_transport": "AF_UNIX/SOCK_STREAM only",
        "planned_sequence": [
            "validate_named_bindings",
            "create_private_runtime",
            "bind_listener",
            "start_corebox_developer_tool",
            "accept_same_euid_peer",
            "accepted_and_exact_duplicate",
            "validate_receipts",
            "cleanup_runtime_and_write_sanitized_evidence",
        ],
        "socket_session_executed": False,
        "child_process_started": False,
        "fixture_submission_performed": False,
        "lifecycle_execution_performed": False,
        "network_or_cloud_calls": 0,
        "execution_authorized": False,
    }


def _snapshot_corebox_tool(plan: NamedSessionPlan, *, runtime: Path) -> Path:
    """Copy the exact reviewed executable bytes into the private runtime."""
    source, details = _open_corebox_tool(plan.corebox_tool)
    destination = runtime / "corebox-c3-client"
    destination_fd = -1
    try:
        current = CoreboxToolIdentity(
            device=details.st_dev,
            inode=details.st_ino,
            size=details.st_size,
            modified_ns=details.st_mtime_ns,
            sha256=_hash_descriptor(source),
        )
        if current != plan.corebox_tool_identity:
            raise C3CommandOrchestrationError("Corebox C3 tool changed after planning")
        destination_fd = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o700,
        )
        digest = hashlib.sha256()
        while chunk := os.read(source, 1024 * 1024):
            digest.update(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(destination_fd, view)
                view = view[written:]
        os.fsync(destination_fd)
        if digest.hexdigest() != plan.corebox_tool_identity.sha256:
            raise C3CommandOrchestrationError("Corebox C3 tool snapshot digest differs")
    except Exception:
        try:
            os.unlink(destination)
        except FileNotFoundError:
            pass
        raise
    finally:
        os.close(source)
        if destination_fd >= 0:
            os.close(destination_fd)
    return destination


def _corebox_command(plan: NamedSessionPlan, *, executable: Path, runtime: Path, socket_path: Path) -> list[str]:
    """Build the private child command only after the server bound its socket."""
    return [
        str(executable),
        "--execute-c3-named-session",
        "--fixture", str(plan.input_dir),
        "--runtime-dir", str(runtime),
        "--socket", str(socket_path),
        "--proof-id", plan.proof_id,
        "--receipt-recorded-at", plan.receipt_recorded_at,
        "--confirm-c3-local-transport-orchestration",
    ]


def _stop_child(child: subprocess.Popen[bytes]) -> None:
    if child.poll() is not None:
        return
    child.terminate()
    try:
        child.wait(timeout=5)
    except subprocess.TimeoutExpired:
        child.kill()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired as exc:
            raise C3CommandOrchestrationError("Corebox child could not be terminated") from exc


def _wait_for_child(child: subprocess.Popen[bytes]) -> None:
    try:
        child.wait(timeout=45)
    except subprocess.TimeoutExpired as exc:
        _stop_child(child)
        raise C3CommandOrchestrationError("Corebox child exceeded the C3 timeout") from exc


def _read_bounded_output(handle: Any, *, field: str) -> bytes:
    handle.seek(0)
    value = handle.read(MAX_CHILD_OUTPUT_BYTES + 1)
    if len(value) > MAX_CHILD_OUTPUT_BYTES:
        raise C3CommandOrchestrationError(f"Corebox child {field} exceeded the output limit")
    return value


def _validate_corebox_result(stdout: bytes, result: dict[str, Any]) -> dict[str, str]:
    if not stdout.endswith(b"\n") or stdout.endswith(b"\n\n"):
        raise C3CommandOrchestrationError("Corebox child result must be one canonical JSON line")
    body = stdout[:-1]
    try:
        client_result = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise C3CommandOrchestrationError("Corebox child did not return canonical session JSON") from exc
    required = {
        "proof_id", "semantic_request_id", "connection_binding_hash", "receipt_id",
        "accepted_status", "duplicate_status",
    }
    if not isinstance(client_result, dict) or set(client_result) != required:
        raise C3CommandOrchestrationError("Corebox child result schema is incomplete")
    if primitives.canonical_json_bytes(client_result) != body:
        raise C3CommandOrchestrationError("Corebox child result JSON is not canonical")
    expected = {
        "proof_id": result["proof_id"],
        "semantic_request_id": result["semantic_request_id"],
        "connection_binding_hash": result["connection_binding_hash"],
        "receipt_id": result["receipt_id"],
        "accepted_status": result["accepted_status"],
        "duplicate_status": result["duplicate_status"],
    }
    if client_result != expected:
        raise C3CommandOrchestrationError("Corebox and Solo C3 result bindings differ")
    return client_result


def execute_named_session(plan: NamedSessionPlan, *, execution_authorized: bool) -> dict[str, Any]:
    """Run the future bounded server/client pair; hard-disabled in this revision."""
    if execution_authorized is not True or not ORCHESTRATION_EXECUTION_ENABLED:
        raise C3CommandOrchestrationNotAuthorized(
            "C3 command orchestration is disabled pending separate owner authorization and review"
        )
    child: subprocess.Popen[bytes] | None = None
    stdout_file = tempfile.TemporaryFile(mode="w+b")
    stderr_file = tempfile.TemporaryFile(mode="w+b")

    def start_corebox(runtime: Path, socket_path: Path) -> None:
        nonlocal child
        snapshot = _snapshot_corebox_tool(plan, runtime=runtime)
        try:
            child = subprocess.Popen(
                _corebox_command(plan, executable=snapshot, runtime=runtime, socket_path=socket_path),
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
            )
        finally:
            os.unlink(snapshot)

    try:
        result = session.execute_one_shot_session(
            input_dir=plan.input_dir,
            proof_id=plan.proof_id,
            receipt_recorded_at=plan.receipt_recorded_at,
            runtime_parent=plan.runtime_parent,
            evidence_dir=plan.evidence_dir,
            solo_revision=plan.solo_revision,
            corebox_revision=plan.corebox_revision,
            execution_authorized=True,
            on_listener_ready=start_corebox,
            retain_evidence=False,
        )
        if child is None:
            raise C3CommandOrchestrationError("Corebox child was not started")
        _wait_for_child(child)
        if child.returncode != 0:
            raise C3CommandOrchestrationError("Corebox child refused the named C3 session")
        stdout = _read_bounded_output(stdout_file, field="stdout")
        stderr = _read_bounded_output(stderr_file, field="stderr")
        if stderr:
            raise C3CommandOrchestrationError("Corebox child emitted unexpected stderr")
        _validate_corebox_result(stdout, result)
        session.retain_session_evidence(result=result, evidence_dir=plan.evidence_dir)
        return result
    finally:
        try:
            if child is not None:
                _stop_child(child)
        finally:
            stdout_file.close()
            stderr_file.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare/refuse one bounded C3 command orchestration")
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--proof-id", required=True)
    parser.add_argument("--receipt-recorded-at", required=True)
    parser.add_argument("--runtime-parent", required=True, type=Path)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--corebox-tool", required=True, type=Path)
    parser.add_argument("--solo-revision", required=True)
    parser.add_argument("--corebox-revision", required=True)
    parser.add_argument("--confirm-c3-local-transport-orchestration", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        plan = build_named_session_plan(
            input_dir=args.input_dir,
            proof_id=args.proof_id,
            receipt_recorded_at=args.receipt_recorded_at,
            runtime_parent=args.runtime_parent,
            evidence_dir=args.evidence_dir,
            corebox_tool=args.corebox_tool,
            solo_revision=args.solo_revision,
            corebox_revision=args.corebox_revision,
        )
        if args.confirm_c3_local_transport_orchestration:
            execute_named_session(plan, execution_authorized=False)
        print(primitives.canonical_json_bytes(preview(plan)).decode("utf-8"))
        return 0
    except (C3CommandOrchestrationError, session.C3NamedSessionPreviewError) as exc:
        print(f"C3 command orchestration refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
