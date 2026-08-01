#!/usr/bin/env python3
"""Disabled-by-default command coordination for one future C3 local proof.

This module may validate and describe the exact two-process handoff, but its
CLI never creates a listener, starts a Corebox child, or writes evidence. The
internal execution function remains hard-disabled pending a separate decision
and review.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import pios_canonical_source_primitives as primitives
from scripts import run_pios_solo_c3_named_session as session

ORCHESTRATOR_SCHEMA = "pios_solo_c3_command_orchestration_plan_v1"
SOLO_SERVER_REVISION = "2ccfa0c"
COREBOX_CLIENT_REVISION = "1566817"
ORCHESTRATION_EXECUTION_ENABLED = False


class C3CommandOrchestrationError(ValueError):
    """Raised when the command coordinator cannot safely prepare a C3 proof."""


class C3CommandOrchestrationNotAuthorized(C3CommandOrchestrationError):
    """Raised for every execution attempt while the orchestrator is disabled."""


@dataclass(frozen=True)
class NamedSessionPlan:
    input_dir: Path
    proof_id: str
    receipt_recorded_at: str
    runtime_parent: Path
    evidence_dir: Path
    corebox_tool: Path
    solo_revision: str
    corebox_revision: str
    fixture: dict[str, Any]


def _require_corebox_tool(path: Path) -> Path:
    path = Path(path)
    if not path.is_absolute():
        raise C3CommandOrchestrationError("Corebox C3 tool path must be absolute")
    try:
        details = os.lstat(path)
    except FileNotFoundError as exc:
        raise C3CommandOrchestrationError("Corebox C3 tool is missing") from exc
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
        raise C3CommandOrchestrationError("Corebox C3 tool must be a regular non-symlink file")
    if not os.access(path, os.X_OK):
        raise C3CommandOrchestrationError("Corebox C3 tool must be executable")
    return path


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
    if not runtime_parent.is_absolute() or not runtime_parent.is_dir() or runtime_parent.is_symlink():
        raise C3CommandOrchestrationError("C3 runtime parent must be an existing absolute non-symlink directory")
    tool = _require_corebox_tool(corebox_tool)
    fixture = session.run_zero_write_preview(input_dir=input_dir)
    return NamedSessionPlan(
        input_dir=Path(input_dir),
        proof_id=proof_id,
        receipt_recorded_at=receipt_recorded_at,
        runtime_parent=Path(runtime_parent),
        evidence_dir=Path(evidence_dir),
        corebox_tool=tool,
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


def _corebox_command(plan: NamedSessionPlan, *, runtime: Path, socket_path: Path) -> list[str]:
    """Build the private child command only after the server bound its socket."""
    return [
        str(plan.corebox_tool),
        "--execute-c3-named-session",
        "--fixture", str(plan.input_dir),
        "--runtime-dir", str(runtime),
        "--socket", str(socket_path),
        "--proof-id", plan.proof_id,
        "--receipt-recorded-at", plan.receipt_recorded_at,
        "--confirm-c3-local-transport-orchestration",
    ]


def execute_named_session(plan: NamedSessionPlan, *, execution_authorized: bool) -> dict[str, Any]:
    """Run the future bounded server/client pair; hard-disabled in this revision."""
    if execution_authorized is not True or not ORCHESTRATION_EXECUTION_ENABLED:
        raise C3CommandOrchestrationNotAuthorized(
            "C3 command orchestration is disabled pending separate owner authorization and review"
        )
    child: subprocess.Popen[str] | None = None

    def start_corebox(runtime: Path, socket_path: Path) -> None:
        nonlocal child
        child = subprocess.Popen(
            _corebox_command(plan, runtime=runtime, socket_path=socket_path),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

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
        )
        if child is None:
            raise C3CommandOrchestrationError("Corebox child was not started")
        stdout, stderr = child.communicate(timeout=45)
        if child.returncode != 0:
            raise C3CommandOrchestrationError("Corebox child refused the named C3 session")
        try:
            client_result = json.loads(stdout)
        except ValueError as exc:
            raise C3CommandOrchestrationError("Corebox child did not return canonical session JSON") from exc
        if not isinstance(client_result, dict) or client_result.get("receipt_id") != result["receipt_id"]:
            raise C3CommandOrchestrationError("Corebox and Solo C3 receipt bindings differ")
        return result
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            child.wait(timeout=5)


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
