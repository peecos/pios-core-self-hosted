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
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.plan_pios_starter_r4_google_cloud_proof import (
    ARTIFACT_SCHEMA,
    CONFIRMATION_FLAG,
    DEFAULT_ACCOUNT,
    DEFAULT_BUDGET_DISPLAY_NAME,
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


class R4ProofExecutionError(ValueError):
    """Raised when the r4 execution preflight or proof fails closed."""


class R4ProofPreflightError(R4ProofExecutionError):
    """Preserves partial read-only preflight evidence after a failure."""

    def __init__(self, message: str, results: Mapping[str, Any]):
        super().__init__(message)
        self.results = dict(results)


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


def canonical_billing_account_name(billing_account: str) -> str:
    if not isinstance(billing_account, str) or not billing_account or billing_account.startswith("<"):
        raise R4ProofExecutionError("an explicit owner-approved billing account is required")
    account_id = billing_account.removeprefix("billingAccounts/")
    if not account_id or "/" in account_id:
        raise R4ProofExecutionError("billing account must be an account ID or billingAccounts/<account-id>")
    return f"billingAccounts/{account_id}"


def validate_active_account(value: Any, *, account: str) -> dict[str, str]:
    if not isinstance(value, list):
        raise R4ProofExecutionError("active-account preflight did not return a JSON list")
    for item in value:
        if isinstance(item, Mapping) and item.get("account") == account and item.get("status") == "ACTIVE":
            return {"account": account, "status": "ACTIVE"}
    raise R4ProofExecutionError("requested operator account is not the active gcloud account")


def validate_project_identity(value: Any, *, project: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or value.get("projectId") != project:
        raise R4ProofExecutionError("project preflight did not return the requested project")
    number = str(value.get("projectNumber", ""))
    if not number.isdigit():
        raise R4ProofExecutionError("project preflight did not return a numeric project number")
    lifecycle = value.get("lifecycleState")
    if lifecycle not in (None, "ACTIVE"):
        raise R4ProofExecutionError("target project is not active")
    return {"project": project, "project_number": number}


def validate_billing_linkage(value: Any, *, billing_account: str) -> dict[str, str]:
    expected = canonical_billing_account_name(billing_account)
    if not isinstance(value, Mapping) or value.get("billingAccountName") != expected:
        raise R4ProofExecutionError("target project is not linked to the supplied billing account")
    return {"billing_account_name": expected, "billing_enabled": True}


def decimal_value(value: Any, *, field: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise R4ProofExecutionError(f"budget has an invalid {field}") from exc


def budget_amount_usd(budget: Mapping[str, Any]) -> Decimal:
    amount = budget.get("amount")
    if not isinstance(amount, Mapping) or not isinstance(amount.get("specifiedAmount"), Mapping):
        raise R4ProofExecutionError("required budget must specify an amount")
    specified = amount["specifiedAmount"]
    if specified.get("currencyCode") != "USD":
        raise R4ProofExecutionError("required budget must use USD")
    units = decimal_value(specified.get("units", 0), field="budget amount units")
    nanos = decimal_value(specified.get("nanos", 0), field="budget amount nanos")
    return units + nanos / Decimal("1000000000")


def validate_budget_posture(
    value: Any,
    *,
    project: str,
    project_number: str,
    budget_display_name: str,
    monthly_cost_ceiling_usd: float,
) -> dict[str, Any]:
    if isinstance(value, Mapping):
        budgets = value.get("budgets")
    else:
        budgets = value
    if not isinstance(budgets, list):
        raise R4ProofExecutionError("budget preflight did not return a JSON budget list")
    expected_projects = {f"projects/{project}", f"projects/{project_number}"}
    for budget in budgets:
        if not isinstance(budget, Mapping) or budget.get("displayName") != budget_display_name:
            continue
        budget_filter = budget.get("budgetFilter")
        projects = budget_filter.get("projects") if isinstance(budget_filter, Mapping) else None
        if not isinstance(projects, list) or not expected_projects.intersection(projects):
            continue
        amount = budget_amount_usd(budget)
        ceiling = Decimal(str(monthly_cost_ceiling_usd))
        if amount <= 0 or amount > ceiling:
            raise R4ProofExecutionError("required budget amount must be positive and no greater than the monthly cost ceiling")
        rules = budget.get("thresholdRules")
        if not isinstance(rules, list):
            raise R4ProofExecutionError("required budget does not define threshold alerts")
        thresholds: list[float] = []
        for rule in rules:
            if isinstance(rule, Mapping) and "thresholdPercent" in rule:
                try:
                    thresholds.append(float(rule["thresholdPercent"]))
                except (TypeError, ValueError) as exc:
                    raise R4ProofExecutionError("required budget has an invalid threshold alert") from exc
        for required in (0.5, 0.8, 1.0):
            if not any(abs(actual - required) < 0.000001 for actual in thresholds):
                raise R4ProofExecutionError("required budget threshold alerts must include 50%, 80%, and 100%")
        notifications = budget.get("notificationsRule", budget.get("allUpdatesRule", {}))
        if not isinstance(notifications, Mapping):
            raise R4ProofExecutionError("required budget has an invalid alert delivery rule")
        channels = notifications.get("monitoringNotificationChannels", [])
        alert_delivery = (
            notifications.get("disableDefaultIamRecipients") is not True
            or isinstance(channels, list) and any(isinstance(channel, str) and channel for channel in channels)
            or isinstance(notifications.get("pubsubTopic"), str) and bool(notifications["pubsubTopic"])
        )
        if not alert_delivery:
            raise R4ProofExecutionError("required budget has no enabled alert delivery")
        return {
            "display_name": budget_display_name,
            "project_scope": sorted(expected_projects.intersection(projects))[0],
            "amount_usd": str(amount),
            "threshold_percentages": sorted(set(thresholds)),
            "alert_delivery_verified": True,
            "alert_delivery_mode": (
                "default_iam_recipients"
                if notifications.get("disableDefaultIamRecipients") is not True
                else "monitoring_channel_or_pubsub"
            ),
        }
    raise R4ProofExecutionError("required named project-scoped budget is absent")


def require_execution_inputs(
    *, proof_id: str,
    billing_account: str,
    budget_display_name: str,
    monthly_cost_ceiling_usd: float,
    proof_cost_ceiling_usd: float,
) -> None:
    try:
        validate_proof_id(proof_id, executable=True)
    except R4ProofPlanError as exc:
        raise R4ProofExecutionError(str(exc)) from exc
    canonical_billing_account_name(billing_account)
    if not isinstance(budget_display_name, str) or not budget_display_name.strip() or budget_display_name.startswith("<"):
        raise R4ProofExecutionError("an explicit owner-approved budget display name is required")
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


def load_command_json(completed: subprocess.CompletedProcess[str], *, message: str) -> Any:
    try:
        return json.loads(completed.stdout or "")
    except json.JSONDecodeError as exc:
        raise R4ProofExecutionError(message) from exc


def run_preflight(
    commands: Mapping[str, list[str]],
    *,
    project: str,
    account: str,
    billing_account: str,
    budget_display_name: str,
    monthly_cost_ceiling_usd: float,
) -> dict[str, Any]:
    results: dict[str, Any] = {}
    cloud_call_count = 0

    def execute(name: str, *, check: bool) -> subprocess.CompletedProcess[str]:
        nonlocal cloud_call_count
        cloud_call_count += 1
        return run_command(commands[name], check=check)

    try:
        active = execute("verify_active_account", check=True)
        results["verify_active_account"] = command_result("verify_active_account", active)
        results["active_account"] = validate_active_account(
            load_command_json(active, message="active-account preflight did not return JSON"), account=account
        )

        project_completed = execute("verify_project", check=True)
        results["verify_project"] = command_result("verify_project", project_completed)
        project_identity = validate_project_identity(
            load_command_json(project_completed, message="project preflight did not return JSON"), project=project
        )
        results["project_identity"] = project_identity

        billing = execute("verify_billing", check=True)
        results["verify_billing"] = command_result("verify_billing", billing)
        results["billing_linkage"] = validate_billing_linkage(
            load_command_json(billing, message="billing preflight did not return JSON"), billing_account=billing_account
        )

        budget = execute("verify_budget_visibility", check=True)
        results["verify_budget_visibility"] = command_result("verify_budget_visibility", budget)
        results["budget_posture"] = validate_budget_posture(
            load_command_json(budget, message="budget preflight did not return JSON"),
            project=project,
            project_number=project_identity["project_number"],
            budget_display_name=budget_display_name,
            monthly_cost_ceiling_usd=monthly_cost_ceiling_usd,
        )

        for name in ("verify_machine_type", "verify_regional_quota", "verify_network", "verify_subnet"):
            completed = execute(name, check=True)
            results[name] = command_result(name, completed)
        firewall = execute("verify_iap_firewall", check=True)
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
            results[name] = assert_absent(name, execute(name, check=False))
    except Exception as exc:
        results["cloud_call_count"] = cloud_call_count
        raise R4ProofPreflightError(str(exc), results) from exc
    results["cloud_call_count"] = cloud_call_count
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
    budget_display_name: str,
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
        "execution_requirements": {
            "effective_permission_validation": "the isolated full lifecycle must create, boot, read health through IAP/OS Login, and delete every temporary proof resource",
            "no_iam_introspection_or_reviewer_role": True,
            "billing_account": billing_account,
            "budget_display_name": budget_display_name,
            "budget_scope": "exact target project",
            "budget_alert_thresholds": [0.5, 0.8, 1.0],
        },
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
        budget_display_name=budget_display_name,
        monthly_cost_ceiling_usd=monthly_cost_ceiling_usd,
        proof_cost_ceiling_usd=proof_cost_ceiling_usd,
    )
    preflight: dict[str, Any] | None = None
    executed: list[dict[str, Any]] = []
    serial: dict[str, Any] | None = None
    readback: dict[str, Any] | None = None
    cleanup_results: list[dict[str, Any]] = []
    cleanup_eligible = False
    status = "failed"
    failure: str | None = None
    try:
        preflight = run_preflight(
            commands,
            project=project,
            account=account,
            billing_account=billing_account,
            budget_display_name=budget_display_name,
            monthly_cost_ceiling_usd=monthly_cost_ceiling_usd,
        )
        # Only delete names after a complete preflight has verified every one is
        # absent.  Earlier preflight failure has created nothing and must not
        # turn a guessed name into a deletion target.
        cleanup_eligible = True
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
    except R4ProofPreflightError as exc:
        preflight = exc.results
        failure = f"R4ProofExecutionError: {exc}"
    except Exception as exc:  # Failure evidence and cleanup are both mandatory for this runner.
        failure = f"{type(exc).__name__}: {exc}"
    finally:
        if cleanup_eligible:
            cleanup_results = cleanup(commands)
    cleanup_complete = cleanup_eligible and all(item["returncode"] == 0 for item in cleanup_results)
    if not cleanup_complete:
        status = "failed"
    result = {
        **common,
        "status": status,
        "cloud_calls": len(executed) + (preflight.get("cloud_call_count", 0) if preflight else 0) + len(cleanup_results),
        "preflight": preflight,
        "executed": executed,
        "serial_proof": serial,
        "iap_oslogin_health": readback,
        "cleanup": cleanup_results,
        "cleanup_status": (
            "complete"
            if cleanup_complete
            else "not_required_preflight_failed"
            if not cleanup_eligible
            else "incomplete"
        ),
        "failure": failure,
        "effective_permission_validation": {
            "mode": "isolated_full_lifecycle",
            "status": "passed" if status == "passed" else "failed",
            "validated_operations": [item["step"] for item in executed],
            "cleanup_complete": cleanup_complete,
            "iap_oslogin_health_passed": readback is not None,
        },
        "budget_cost_limits": {
            "billing_account": billing_account,
            "budget_display_name": budget_display_name,
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
    parser.add_argument("--budget-display-name", default=DEFAULT_BUDGET_DISPLAY_NAME)
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
        budget_display_name=args.budget_display_name,
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
