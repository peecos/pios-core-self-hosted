from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.prove_pios_starter_disk_image_hygiene import load_json, resolve_repo_path
from scripts.validate_pios_starter_disk_image_evidence import EVIDENCE_SCHEMA


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def git_output(args: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip()


def current_source_state() -> dict[str, Any]:
    commit = git_output(["rev-parse", "HEAD"])
    tag_output = git_output(["tag", "--points-at", "HEAD"])
    tracked_status = git_output(["status", "--porcelain", "--untracked-files=no"])
    return {
        "commit": commit,
        "tags_at_head": tag_output.splitlines() if tag_output else [],
        "tracked_worktree_clean": tracked_status == "",
        "untracked_artifacts_intentionally_not_evaluated": True,
    }


def build_signing_review_plan(
    *, evidence_readiness: dict[str, Any], source_state: dict[str, Any]
) -> dict[str, Any]:
    if evidence_readiness.get("schema_version") != EVIDENCE_SCHEMA:
        raise ValueError("evidence readiness has an unexpected schema_version")
    if evidence_readiness.get("status") != "passed":
        raise ValueError("evidence readiness must have status=passed")
    if evidence_readiness.get("readiness") != "local_image_evidence_complete":
        raise ValueError("evidence readiness does not represent a complete local image evidence set")
    summary = evidence_readiness.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("evidence readiness is missing summary")
    image = summary.get("release_image")
    digest = summary.get("release_image_sha256")
    if not isinstance(image, str) or not isinstance(digest, str):
        raise ValueError("evidence readiness is missing release image identity")

    missing_inputs: list[str] = []
    if not source_state.get("commit"):
        missing_inputs.append("verified source commit")
    if not source_state.get("tags_at_head"):
        missing_inputs.append("owner-approved immutable source tag")
    if source_state.get("tracked_worktree_clean") is not True:
        missing_inputs.append("clean tracked source checkout")
    missing_inputs.extend(
        [
            "owner-approved release ID/version and release notes",
            "staged public artifact set and public release manifest",
            "passed public-split/package validation for that exact artifact set",
            "authorized production signing operator and protected-key access",
            "explicit publication target and owner approval",
        ]
    )
    return {
        "schema_version": "pios_starter_signing_review_plan_v1",
        "created_at": utc_now(),
        "status": "blocked_pending_owner_release_decision",
        "mode": "plan_only_no_signing",
        "source_state": source_state,
        "local_image_evidence": {
            "readiness_result": evidence_readiness.get("release_manifest"),
            "image": image,
            "sha256": digest,
            "package_health_proof": summary.get("package_health_proof"),
            "fresh_vm_hygiene": summary.get("fresh_vm_hygiene"),
            "residue_inspection": summary.get("residue_inspection"),
        },
        "missing_inputs": missing_inputs,
        "owner_decision_required": [
            "whether to promote this local candidate into a named public release process",
            "release ID/version, source tag, notes, and publication target",
            "production signing operator/key-custody authorization",
        ],
        "later_operator_sequence": [
            "create/confirm an immutable source tag in a clean release checkout",
            "stage the public artifact set and public release manifest",
            "run public-split and extracted-package validation for that exact set",
            "generate and review SHA256SUMS",
            "sign only after explicit owner approval through the production ceremony",
            "verify the signature before any approved publication",
        ],
        "boundaries": [
            "no source tag created",
            "no production or development key accessed",
            "no checksum signature created",
            "no artifact published",
            "no cloud/provider resource created or changed",
            "no Owner Bind or owner-specific state",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create a zero-signing, zero-publication review plan from a passed PIOS Starter "
            "local evidence-readiness record."
        )
    )
    parser.add_argument("--evidence-readiness", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    readiness_path = resolve_repo_path(args.evidence_readiness)
    output_path = resolve_repo_path(args.output)
    plan = build_signing_review_plan(
        evidence_readiness=load_json(readiness_path),
        source_state=current_source_state(),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
