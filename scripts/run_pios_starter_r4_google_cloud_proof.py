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
OPERATOR_PERMISSION_RECORD_SCHEMA = "pios_starter_r4_gcp_operator_permission_record_v1"
REQUIRED_PERMISSIONS = frozenset(
    {
        "compute.images.create",
        "compute.images.delete",
        "compute.images.get",
        "compute.disks.create",
        "compute.disks.delete",
        "compute.disks.get",
        "compute.instances.create",
        "compute.instances.delete",
        "compute.instances.get",
        "compute.instances.getSerialPortOutput",
        "compute.machineTypes.get",
        "compute.regions.get",
        "compute.networks.get",
        "compute.subnetworks.get",
        "compute.firewalls.list",
        "storage.buckets.create",
        "storage.buckets.delete",
        "storage.buckets.get",
        "storage.objects.create",
        "storage.objects.delete",
        "storage.objects.get",
        "iap.tunnelInstances.accessViaIAP",
        "compute.osLogin",
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


def parse_timestamp(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise R4ProofExecutionError(f"operator permission record requires {field}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise R4ProofExecutionError(f"operator permission record has invalid {field}") from exc
    if parsed.tzinfo is None:
        raise R4ProofExecutionError(f"operator permission record {field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def validate_operator_permission_record(
    *, path: Path | None, project: str, account: str, now: datetime | None = None
) -> dict[str, Any]:
    """Require independently verified, still-valid effective-permission evidence.

    Google Cloud IAM-policy visibility cannot prove group, inherited, conditional,
    or custom-role effective permissions.  This deliberately consumes a separately
    verified record and never manufactures a passed record from policy bindings.
    """
    if path is None:
        raise R4ProofExecutionError("confirmed execution requires an operator permission record")
    if not path.is_file():
        raise R4ProofExecutionError("operator permission record is missing")
    try:
        record = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise R4ProofExecutionError("operator permission record is not valid JSON") from exc
    if not isinstance(record, Mapping):
        raise R4ProofExecutionError("operator permission record must be a JSON object")
    if record.get("schema_version") != OPERATOR_PERMISSION_RECORD_SCHEMA:
        raise R4ProofExecutionError("operator permission record has an unexpected schema")
    if record.get("status") != "passed":
        raise R4ProofExecutionError("operator permission record must have status passed")
    if record.get("project") != project or record.get("account") != account:
        raise R4ProofExecutionError("operator permission record does not bind the requested project and account")

    effective = record.get("effective_permissions")
    if not isinstance(effective, list) or not all(isinstance(item, str) for item in effective):
        raise R4ProofExecutionError("operator permission record has no effective permission list")
    missing = sorted(REQUIRED_PERMISSIONS.difference(effective))
    if missing:
        raise R4ProofExecutionError(
            "operator permission record lacks required effective permissions: " + ", ".join(missing)
        )

    iap_oslogin = record.get("iap_oslogin")
    if not isinstance(iap_oslogin, Mapping) or iap_oslogin.get("iap_tunnel_verified") is not True or iap_oslogin.get("os_login_verified") is not True:
        raise R4ProofExecutionError("operator permission record does not verify both IAP tunnel and OS Login")
    verification = record.get("verification")
    if not isinstance(verification, Mapping) or not all(
        isinstance(verification.get(field), str) and verification[field].strip()
        for field in ("method", "evidence_reference")
    ):
        raise R4ProofExecutionError("operator permission record requires verification method and evidence reference")

    verified_at = parse_timestamp(record.get("verified_at"), field="verified_at")
    expires_at = parse_timestamp(record.get("expires_at"), field="expires_at")
    current = now or datetime.now(timezone.utc)
    if expires_at <= current:
        raise R4ProofExecutionError("operator permission record is expired")
    if verified_at > expires_at:
        raise R4ProofExecutionError("operator permission record verified_at is after expires_at")
    return {
        "record_path": str(path),
        "schema_version": OPERATOR_PERMISSION_RECORD_SCHEMA,
        "status": "passed",
        "project": project,
        "account": account,
        "verified_at": verified_at.isoformat().replace("+00:00", "Z"),
        "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
        "effective_permissions": sorted(set(effective)),
        "iap_oslogin": {"iap_tunnel_verified": True, "os_login_verified": True},
        "verification": {
            "method": verification["method"].strip(),
            "evidence_reference": verification["evidence_reference"].strip(),
        },
    }


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
        all_updates = budget.get("allUpdatesRule")
        if not isinstance(all_updates, Mapping):
            raise R4ProofExecutionError("required budget does not define an alert delivery rule")
        channels = all_updates.get("monitoringNotificationChannels", [])
        alert_delivery = (
            all_updates.get("disableDefaultIamRecipients") is False
            or isinstance(channels, list) and any(isinstance(channel, str) and channel for channel in channels)
            or isinstance(all_updates.get("pubsubTopic"), str) and bool(all_updates["pubsubTopic"])
        )
        if not alert_delivery:
            raise R4ProofExecutionError("required budget has no enabled alert delivery")
        return {
            "display_name": budget_display_name,
            "project_scope": sorted(expected_projects.intersection(projects))[0],
            "amount_usd": str(amount),
            "threshold_percentages": sorted(set(thresholds)),
            "alert_delivery_verified": True,
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
    operator_permission_record: Mapping[str, Any],
) -> dict[str, Any]:
    results: dict[str, Any] = {}
    active = run_command(commands["verify_active_account"], check=True)
    results["verify_active_account"] = command_result("verify_active_account", active)
    results["active_account"] = validate_active_account(
        load_command_json(active, message="active-account preflight did not return JSON"), account=account
    )

    project_completed = run_command(commands["verify_project"], check=True)
    results["verify_project"] = command_result("verify_project", project_completed)
    project_identity = validate_project_identity(
        load_command_json(project_completed, message="project preflight did not return JSON"), project=project
    )
    results["project_identity"] = project_identity

    billing = run_command(commands["verify_billing"], check=True)
    results["verify_billing"] = command_result("verify_billing", billing)
    results["billing_linkage"] = validate_billing_linkage(
        load_command_json(billing, message="billing preflight did not return JSON"), billing_account=billing_account
    )

    budget = run_command(commands["verify_budget_visibility"], check=True)
    results["verify_budget_visibility"] = command_result("verify_budget_visibility", budget)
    results["budget_posture"] = validate_budget_posture(
        load_command_json(budget, message="budget preflight did not return JSON"),
        project=project,
        project_number=project_identity["project_number"],
        budget_display_name=budget_display_name,
        monthly_cost_ceiling_usd=monthly_cost_ceiling_usd,
    )

    for name in ("verify_machine_type", "verify_regional_quota", "verify_network", "verify_subnet"):
        completed = run_command(commands[name], check=True)
        results[name] = command_result(name, completed)
    permission_completed = run_command(commands["verify_iam_policy_visibility"], check=True)
    results["verify_iam_policy_visibility"] = command_result("verify_iam_policy_visibility", permission_completed)
    permissions_payload = load_command_json(permission_completed, message="project IAM policy preflight did not return JSON")
    if not isinstance(permissions_payload, Mapping) or not isinstance(permissions_payload.get("bindings"), list):
        raise R4ProofExecutionError("project IAM policy preflight did not return policy bindings")
    results["operator_permission_record"] = dict(operator_permission_record)
    results["iam_policy_visibility_only"] = True
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
    results["cloud_call_count"] = 16
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
    operator_permission_record_path: Path | None,
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
            "operator_permission_record_schema": OPERATOR_PERMISSION_RECORD_SCHEMA,
            "operator_permission_record": "separately verified, project/account-bound, unexpired effective-permission evidence",
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
    operator_permission_record = validate_operator_permission_record(
        path=operator_permission_record_path, project=project, account=account
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
            operator_permission_record=operator_permission_record,
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
    parser.add_argument("--operator-permission-record", type=Path)
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
        operator_permission_record_path=(
            resolve_repo_path(args.operator_permission_record) if args.operator_permission_record else None
        ),
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
