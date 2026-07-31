"""Preview or explicitly execute the isolated temporary PIOS Starter r4 GCP proof.

No cloud call occurs unless the sole explicit execution confirmation flag is
provided.  This runner refuses persistent names and always attempts cleanup of
the temporary r4 proof resources after an execution attempt.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.plan_pios_starter_r4_google_cloud_proof import (
    ARTIFACT_SCHEMA,
    CONFIRMATION_FLAG,
    DEFAULT_ACCOUNT,
    DEFAULT_NETWORK,
    DEFAULT_PROJECT,
    DEFAULT_SUBNET,
    IAP_TCP_SOURCE_RANGE,
    R4_QCOW2_SHA256,
    R4ProofPlanError,
    assert_all_gates_false,
    build_cloud_init_user_data,
    build_execution_commands,
    command_preview,
    load_json,
    resolve_repo_path,
    sha256_file,
    temporary_names,
    validate_proof_id,
)

DEFAULT_ARTIFACT_MANIFEST = Path(
    "image-artifacts/pios-starter-r4-google-cloud-import-artifact-20260731/"
    "r4-google-cloud-import-artifact-manifest.json"
)
DEFAULT_OUTPUT_DIR = Path("image-artifacts/pios-starter-r4-gcp-proof-execution")
PROOF_START = "PIOS_R4_GCP_PROOF_START"
PROOF_HEALTH = "PIOS_R4_GCP_PROOF_HEALTH_PASSED"
PROOF_DONE = "PIOS_R4_GCP_PROOF_DONE"
HEALTH_SCHEMA = "self_hosted_core_health_check_v1"
REQUIRED_PERMISSIONS = frozenset(
    {
        "compute.images.create",
        "compute.images.delete",
        "compute.disks.create",
        "compute.disks.delete",
        "compute.instances.create",
        "compute.instances.delete",
        "compute.instances.getSerialPortOutput",
        "storage.buckets.create",
        "storage.buckets.delete",
        "storage.objects.create",
        "storage.objects.delete",
    }
)


class R4ProofExecutionError(ValueError):
    """Raised when the r4 execution preflight or proof fails closed."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run_command(command: list[str], *, check: bool, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=check, capture_output=True, text=True, timeout=timeout)


def load_r4_artifact(path: Path) -> dict[str, Any]:
    artifact = load_json(path)
    if artifact.get("schema_version") != ARTIFACT_SCHEMA:
        raise R4ProofExecutionError("expected an r4-specific Google import artifact manifest")
    if artifact.get("status") != "passed" or artifact.get("cloud_calls") != 0:
        raise R4ProofExecutionError("r4 import artifact must be passed and local-only")
    if artifact.get("r4_qcow2_sha256") != R4_QCOW2_SHA256:
        raise R4ProofExecutionError("r4 import artifact is not bound to the exact r4 QCOW2")
    archive = Path(str(artifact.get("archive", "")))
    if not archive.is_absolute():
        archive = resolve_repo_path(archive)
    if not archive.is_file():
        raise R4ProofExecutionError("r4 Google import archive is missing")
    archive_sha256 = artifact.get("archive_sha256")
    if not isinstance(archive_sha256, str) or sha256_file(archive) != archive_sha256:
        raise R4ProofExecutionError("r4 Google import archive checksum does not match its manifest")
    if not isinstance(artifact.get("raw_image_sha256"), str):
        raise R4ProofExecutionError("r4 Google import artifact is missing raw-image checksum evidence")
    if artifact.get("archive_listing") != ["disk.raw"]:
        raise R4ProofExecutionError("r4 Google import archive must contain only disk.raw")
    return artifact


def write_user_data(*, proof_id: str, output_dir: Path) -> Path:
    user_data = build_cloud_init_user_data(proof_id)
    if not user_data.startswith("#cloud-config\n"):
        raise R4ProofExecutionError("r4 first-boot payload must be cloud-init user-data")
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "r4-proof-user-data.yaml"
    path.write_text(user_data)
    return path


def require_execution_inputs(
    *, proof_id: str,
    billing_account: str,
    monthly_cost_ceiling_usd: float,
    proof_cost_ceiling_usd: float,
) -> None:
    try:
        validate_proof_id(proof_id, executable=True)
    except R4ProofPlanError as exc:
        raise R4ProofExecutionError(str(exc)) from exc
    if not isinstance(billing_account, str) or not billing_account or billing_account.startswith("<"):
        raise R4ProofExecutionError("an explicit owner-approved billing account is required")
    if monthly_cost_ceiling_usd <= 0 or proof_cost_ceiling_usd <= 0:
        raise R4ProofExecutionError("positive owner-approved monthly and proof cost ceilings are required")
    if proof_cost_ceiling_usd > monthly_cost_ceiling_usd:
        raise R4ProofExecutionError("proof cost ceiling must not exceed the monthly cost ceiling")


def command_result(name: str, completed: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    return {
        "step": name,
        "returncode": completed.returncode,
        "stdout": (completed.stdout or "")[-4000:],
        "stderr": (completed.stderr or "")[-4000:],
    }


def assert_absent(name: str, completed: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    text = f"{completed.stdout}\n{completed.stderr}".lower()
    not_found = any(marker in text for marker in ("not found", "not_found", "was not found", "does not exist"))
    if completed.returncode == 0 or not not_found:
        raise R4ProofExecutionError(f"temporary resource collision or unverified absence: {name}")
    return command_result(name, completed)


def firewall_allows_iap_ssh(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    for rule in value:
        if not isinstance(rule, Mapping):
            continue
        sources = rule.get("sourceRanges", [])
        allowed = rule.get("allowed", [])
        if IAP_TCP_SOURCE_RANGE not in sources or not isinstance(allowed, list):
            continue
        for item in allowed:
            if isinstance(item, Mapping) and item.get("IPProtocol") == "tcp":
                ports = item.get("ports", [])
                if not ports or "22" in ports:
                    return True
    return False


def run_preflight(commands: Mapping[str, list[str]]) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for name in (
        "verify_active_account",
        "verify_project",
        "verify_billing",
        "verify_budget_visibility",
        "verify_machine_type",
        "verify_regional_quota",
        "verify_network",
        "verify_subnet",
    ):
        completed = run_command(commands[name], check=True)
        results[name] = command_result(name, completed)
    permission_completed = run_command(commands["verify_permissions"], check=True)
    results["verify_permissions"] = command_result("verify_permissions", permission_completed)
    try:
        permissions_payload = json.loads(permission_completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise R4ProofExecutionError("project IAM policy preflight did not return JSON") from exc
    if not isinstance(permissions_payload, Mapping) or not isinstance(permissions_payload.get("bindings"), list):
        raise R4ProofExecutionError("project IAM policy preflight did not return policy bindings")
    results["required_permissions_for_owner_review"] = sorted(REQUIRED_PERMISSIONS)
    firewall = run_command(commands["verify_iap_firewall"], check=True)
    results["verify_iap_firewall"] = command_result("verify_iap_firewall", firewall)
    try:
        firewall_payload = json.loads(firewall.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise R4ProofExecutionError("IAP firewall preflight did not return JSON") from exc
    if not firewall_allows_iap_ssh(firewall_payload):
        raise R4ProofExecutionError("private network lacks an IAP TCP/22 firewall path")
    for name in (
        "check_bucket_absent",
        "check_image_absent",
        "check_boot_disk_absent",
        "check_core_disk_absent",
        "check_key_disk_absent",
        "check_instance_absent",
    ):
        results[name] = assert_absent(name, run_command(commands[name], check=False))
    return results


def serial_proof_passed(value: str) -> bool:
    return (
        PROOF_START in value
        and PROOF_HEALTH in value
        and PROOF_DONE in value
        and f'"schema_version": "{HEALTH_SCHEMA}"' in value
        and '"status": "passed"' in value
    )


def wait_for_serial_proof(*, command: list[str], timeout_seconds: int, poll_seconds: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    attempts = 0
    output = ""
    while time.monotonic() < deadline:
        attempts += 1
        completed = run_command(command, check=False)
        output = f"{completed.stdout or ''}\n{completed.stderr or ''}"
        if PROOF_DONE in output:
            return {
                "status": "passed" if serial_proof_passed(output) else "failed",
                "attempts": attempts,
                "serial_output_tail": output[-12000:],
            }
        time.sleep(poll_seconds)
    return {"status": "failed", "attempts": attempts, "serial_output_tail": output[-12000:]}


def validate_iap_health_readback(value: str) -> dict[str, Any]:
    try:
        health = json.loads(value)
    except json.JSONDecodeError as exc:
        raise R4ProofExecutionError("IAP/OS Login health readback is not JSON") from exc
    if health.get("schema_version") != HEALTH_SCHEMA or health.get("status") != "passed":
        raise R4ProofExecutionError("IAP/OS Login did not read a passed five-zone health record")
    zones = health.get("zones")
    if not isinstance(zones, Mapping) or len(zones) != 5:
        raise R4ProofExecutionError("IAP/OS Login health readback does not contain five zones")
    if not all(isinstance(value, Mapping) and value.get("exists") is True for value in zones.values()):
        raise R4ProofExecutionError("IAP/OS Login health readback has an unhealthy zone")
    return health


def cleanup(commands: Mapping[str, list[str]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for name in (
        "delete_instance",
        "delete_key_disk",
        "delete_core_disk",
        "delete_boot_disk",
        "delete_image",
        "delete_object",
        "delete_bucket",
    ):
        results.append(command_result(name, run_command(commands[name], check=False)))
    return results


def preview_or_run(
    *,
    artifact_manifest_path: Path,
    output_dir: Path,
    proof_id: str,
    project: str,
    account: str,
    billing_account: str,
    network: str,
    subnet: str,
    monthly_cost_ceiling_usd: float,
    proof_cost_ceiling_usd: float,
    confirm: bool,
    timeout_seconds: int,
    poll_seconds: int,
) -> dict[str, Any]:
    artifact = load_r4_artifact(artifact_manifest_path)
    names = temporary_names(proof_id)
    user_data_path = write_user_data(proof_id=proof_id, output_dir=output_dir)
    commands = build_execution_commands(
        project=project,
        account=account,
        billing_account=billing_account,
        network=network,
        subnet=subnet,
        proof_id=proof_id,
        artifact_manifest=artifact,
        user_data_path=user_data_path,
    )
    common = {
        "schema_version": "pios_starter_r4_google_cloud_proof_execution_v1",
        "created_at": utc_now(),
        "status": "preview_only",
        "cloud_calls": 0,
        "proof_id": proof_id,
        "project": project,
        "account": account,
        "artifact_manifest": str(artifact_manifest_path),
        "r4_qcow2_sha256": R4_QCOW2_SHA256,
        "temporary_resources": names,
        "requires_confirmation": CONFIRMATION_FLAG,
        "user_data": str(user_data_path),
        "commands": command_preview(commands),
        "boundaries": [
            "preview makes no Google Cloud calls",
            "proof resources are temporary pios-r4proof-* names only",
            "persistent pios-core-solo VM, disks, images, snapshots, VPC, and subnet are never mutation targets",
            "no external IP, service account, scopes, endpoint, app networking, Owner Bind, or owner data",
        ],
    }
    if not confirm:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "r4-gcp-proof-preview.json").write_text(json.dumps(common, indent=2, sort_keys=True) + "\n")
        return common
    require_execution_inputs(
        proof_id=proof_id,
        billing_account=billing_account,
        monthly_cost_ceiling_usd=monthly_cost_ceiling_usd,
        proof_cost_ceiling_usd=proof_cost_ceiling_usd,
    )
    preflight: dict[str, Any] | None = None
    executed: list[dict[str, Any]] = []
    serial: dict[str, Any] | None = None
    readback: dict[str, Any] | None = None
    cleanup_results: list[dict[str, Any]] = []
    status = "failed"
    failure: str | None = None
    try:
        preflight = run_preflight(commands)
        for name in (
            "create_bucket",
            "upload_archive",
            "create_image",
            "create_boot_disk",
            "create_core_disk",
            "create_key_disk",
            "create_instance",
        ):
            executed.append(command_result(name, run_command(commands[name], check=True, timeout=timeout_seconds)))
        serial = wait_for_serial_proof(
            command=commands["serial_output"], timeout_seconds=timeout_seconds, poll_seconds=poll_seconds
        )
        if serial["status"] != "passed":
            raise R4ProofExecutionError("serial output did not prove a passed r4 first boot")
        health_command = run_command(commands["iap_oslogin_health_readback"], check=True, timeout=timeout_seconds)
        readback = validate_iap_health_readback(health_command.stdout or "")
        status = "passed"
    except Exception as exc:  # Failure evidence and cleanup are both mandatory for this runner.
        failure = f"{type(exc).__name__}: {exc}"
    finally:
        cleanup_results = cleanup(commands)
    cleanup_complete = all(item["returncode"] == 0 for item in cleanup_results)
    if not cleanup_complete:
        status = "failed"
    result = {
        **common,
        "status": status,
        "cloud_calls": len(executed) + (len(preflight) if preflight else 0) + len(cleanup_results),
        "preflight": preflight,
        "executed": executed,
        "serial_proof": serial,
        "iap_oslogin_health": readback,
        "cleanup": cleanup_results,
        "cleanup_status": "complete" if cleanup_complete else "incomplete",
        "failure": failure,
        "budget_cost_limits": {
            "billing_account": billing_account,
            "monthly_cost_ceiling_usd": monthly_cost_ceiling_usd,
            "proof_cost_ceiling_usd": proof_cost_ceiling_usd,
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "r4-gcp-proof-result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Preview or explicitly run an isolated temporary r4 GCP proof.")
    parser.add_argument("--artifact-manifest", type=Path, default=DEFAULT_ARTIFACT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--proof-id", default="r4-20260731-preview")
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--account", default=DEFAULT_ACCOUNT)
    parser.add_argument("--billing-account", default="<owner-approved-billing-account>")
    parser.add_argument("--network", default=DEFAULT_NETWORK)
    parser.add_argument("--subnet", default=DEFAULT_SUBNET)
    parser.add_argument("--monthly-cost-ceiling-usd", type=float, default=0.0)
    parser.add_argument("--proof-cost-ceiling-usd", type=float, default=0.0)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--poll-seconds", type=int, default=10)
    parser.add_argument(CONFIRMATION_FLAG, action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = preview_or_run(
        artifact_manifest_path=resolve_repo_path(args.artifact_manifest),
        output_dir=resolve_repo_path(args.output_dir),
        proof_id=args.proof_id,
        project=args.project,
        account=args.account,
        billing_account=args.billing_account,
        network=args.network,
        subnet=args.subnet,
        monthly_cost_ceiling_usd=args.monthly_cost_ceiling_usd,
        proof_cost_ceiling_usd=args.proof_cost_ceiling_usd,
        confirm=getattr(args, CONFIRMATION_FLAG.removeprefix("--").replace("-", "_")),
        timeout_seconds=args.timeout_seconds,
        poll_seconds=args.poll_seconds,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in {"preview_only", "passed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
