"""Plan an isolated, temporary Google Cloud proof for the local PIOS Starter r4 image.

This module makes no cloud calls.  It deliberately does not reuse persistent
deployment names or the legacy default-network import-proof model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

R4_RELEASE_MANIFEST = Path(
    "image-artifacts/pios-starter-disk-image-20260731-r4/"
    "pios-starter-disk-image-20260731-r4-release-manifest.json"
)
R4_EVIDENCE_READINESS = Path(
    "image-artifacts/pios-starter-disk-image-20260731-r4/"
    "pios-starter-disk-image-20260731-r4-evidence-readiness.json"
)
R4_QCOW2 = Path(
    "image-artifacts/pios-starter-disk-image-20260731-r4/"
    "pios-starter-disk-image-20260731-r4.qcow2"
)
R4_QCOW2_SHA256 = "f04ae641e213d14aa802f5a2c06907616d4642f69836bc133a30059b55470c19"
PLAN_SCHEMA = "pios_starter_r4_google_cloud_proof_plan_v1"
ARTIFACT_SCHEMA = "pios_starter_r4_google_cloud_import_artifact_v1"
CONFIRMATION_FLAG = "--confirm-r4-gcp-proof-execution"
TEMPORARY_PREFIX = "pios-r4proof-"
DEFAULT_OUTPUT_DIR = Path("image-artifacts/pios-starter-r4-gcp-proof-plan")
DEFAULT_PROOF_ID = "r4-20260731-preview"
DEFAULT_ZONE = "europe-north1-a"
DEFAULT_REGION = "europe-north1"
DEFAULT_MACHINE_TYPE = "c4a-standard-2"
DEFAULT_NETWORK = "pios-core-vpc"
DEFAULT_SUBNET = "pios-core-en1"
DEFAULT_PROJECT = "pios-core-solo"
DEFAULT_ACCOUNT = "valto@prifina.com"
DEFAULT_BUDGET_DISPLAY_NAME = "<owner-approved-r4-proof-budget-name>"
DISK_TYPE = "hyperdisk-balanced"
DISK_SPECS = {"boot": "40GB", "core": "100GB", "keys": "20GB"}
IAP_TCP_SOURCE_RANGE = "35.235.240.0/20"
PROOF_ID_RE = re.compile(r"r4-[a-z0-9](?:[a-z0-9-]{0,34}[a-z0-9])?")


class R4ProofPlanError(ValueError):
    """Raised for an unsafe or mismatched r4 proof planning input."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def resolve_repo_path(path: Path) -> Path:
    return (REPO_ROOT / path).resolve() if not path.is_absolute() else path


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise R4ProofPlanError(f"invalid JSON file: {path}") from exc
    if not isinstance(value, dict):
        raise R4ProofPlanError(f"JSON object required: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_r4_release(
    *, release_manifest_path: Path, evidence_readiness_path: Path
) -> dict[str, Any]:
    manifest = load_json(release_manifest_path)
    if manifest.get("schema_version") != "self_hosted_qemu_image_release_manifest_v1":
        raise R4ProofPlanError("r4 release manifest has an unexpected schema")
    if manifest.get("status") != "passed":
        raise R4ProofPlanError("r4 release manifest must be passed")
    if manifest.get("standalone_image_name") != R4_QCOW2.name:
        raise R4ProofPlanError("r4 release manifest names an unexpected standalone image")
    if manifest.get("standalone_image_sha256") != R4_QCOW2_SHA256:
        raise R4ProofPlanError("r4 release manifest has an unexpected QCOW2 checksum")
    inspection = manifest.get("inspection")
    if not isinstance(inspection, Mapping) or inspection.get("format") != "qcow2":
        raise R4ProofPlanError("r4 release manifest must describe QCOW2")
    if inspection.get("backing_file_present") is not False:
        raise R4ProofPlanError("r4 release manifest must prove no backing file")
    image = Path(manifest.get("standalone_image", ""))
    if not image.is_absolute():
        image = (release_manifest_path.parent / image).resolve()
    if image.resolve() != resolve_repo_path(R4_QCOW2):
        raise R4ProofPlanError("r4 release manifest must reference exactly the approved r4 QCOW2")
    if not image.is_file() or sha256_file(image) != R4_QCOW2_SHA256:
        raise R4ProofPlanError("local r4 QCOW2 does not match the required checksum")

    readiness = load_json(evidence_readiness_path)
    if readiness.get("schema_version") != "pios_starter_disk_image_evidence_readiness_v1":
        raise R4ProofPlanError("r4 readiness record has an unexpected schema")
    if readiness.get("status") != "passed" or readiness.get("readiness") != "local_image_evidence_complete":
        raise R4ProofPlanError("r4 local evidence readiness must be complete")
    summary = readiness.get("summary")
    if not isinstance(summary, Mapping) or summary.get("release_image_sha256") != R4_QCOW2_SHA256:
        raise R4ProofPlanError("r4 readiness record is not bound to the required checksum")
    return {
        "release_manifest": str(release_manifest_path),
        "evidence_readiness": str(evidence_readiness_path),
        "qcow2": str(image),
        "qcow2_sha256": R4_QCOW2_SHA256,
    }


def validate_proof_id(proof_id: str, *, executable: bool = False) -> str:
    if not isinstance(proof_id, str) or not PROOF_ID_RE.fullmatch(proof_id):
        raise R4ProofPlanError("proof_id must be a canonical r4- lowercase temporary identifier")
    if executable and proof_id.endswith("-preview"):
        raise R4ProofPlanError("a non-preview unique proof_id is required for cloud execution")
    return proof_id


def temporary_names(proof_id: str) -> dict[str, str]:
    proof_id = validate_proof_id(proof_id)
    prefix = f"{TEMPORARY_PREFIX}{proof_id}"
    names = {
        "bucket": f"{prefix}-stage",
        "object": f"{prefix}-disk-raw.tar.gz",
        "image": f"{prefix}-image",
        "boot_disk": f"{prefix}-boot",
        "core_disk": f"{prefix}-core",
        "key_disk": f"{prefix}-keys",
        "instance": f"{prefix}-vm",
        "output_directory": f"image-artifacts/{prefix}",
    }
    for name, value in names.items():
        if name == "output_directory":
            continue
        if not value.startswith(TEMPORARY_PREFIX) or "pios-core-solo" in value:
            raise R4ProofPlanError("temporary r4 proof names must not overlap persistent resources")
    return names


def build_synthetic_first_boot_manifest(proof_id: str) -> dict[str, Any]:
    proof_id = validate_proof_id(proof_id)
    slug = f"gcp-{proof_id}"
    return {
        "manifest_version": "self_hosted_provisioning_manifest_v1",
        "core_instance": {
            "env_name": "gcp-r4-proof",
            "owner_id": f"owner_synthetic_{proof_id.replace('-', '_')}",
            "owner_slug": slug,
        },
        "self_hosted": {
            "core_root": f"/var/lib/pios-core/owners/{slug}/core",
            "key_store_path": f"/var/lib/pios-core/owners/{slug}/keys",
            "key_provider": "local_dev_file_keys",
        },
        "services": {
            "start_core_api": False,
            "start_connectors": False,
            "start_scheduler": False,
        },
        "authorization": {
            "hydrate_bundle": False,
            "connector_sync": False,
            "broad_migration": False,
            "source_decommission": False,
        },
    }


def assert_all_gates_false(manifest: Mapping[str, Any]) -> None:
    values = {
        **manifest.get("services", {}),
        **manifest.get("authorization", {}),
    }
    expected = (
        "start_core_api",
        "start_connectors",
        "start_scheduler",
        "hydrate_bundle",
        "connector_sync",
        "broad_migration",
        "source_decommission",
    )
    unsafe = [name for name in expected if values.get(name) is not False]
    if unsafe:
        raise R4ProofPlanError(f"r4 first-boot manifest has unsafe gates: {', '.join(unsafe)}")


def build_cloud_init_user_data(proof_id: str) -> str:
    manifest = build_synthetic_first_boot_manifest(proof_id)
    assert_all_gates_false(manifest)
    serialized = json.dumps(manifest, indent=2, sort_keys=True)
    owner_slug = manifest["core_instance"]["owner_slug"]
    health_path = f"/var/lib/pios-core/owners/{owner_slug}/core/system/bootstrap/health-check.json"
    return (
        "#cloud-config\n"
        "write_files:\n"
        "  - path: /tmp/pios-self-hosted-manifest.json\n"
        "    permissions: '0600'\n"
        "    content: |\n"
        + "\n".join(f"      {line}" for line in serialized.splitlines())
        + "\nruncmd:\n"
        "  - [bash, -lc, \"set -euo pipefail; "
        "echo PIOS_R4_GCP_PROOF_START | tee /dev/console; "
        "/opt/pios-core/bin/pios-core-init --manifest /tmp/pios-self-hosted-manifest.json | tee /tmp/pios-core-init-result.json /dev/console; "
        f"cat {health_path} | tee /tmp/pios-core-health-check.json /dev/console; "
        "echo PIOS_R4_GCP_PROOF_HEALTH_PASSED | tee /dev/console; "
        "echo PIOS_R4_GCP_PROOF_DONE | tee /dev/console\"]\n"
    )


def gcloud_base(project: str, account: str) -> list[str]:
    return ["gcloud", "--project", project, "--account", account]


def build_execution_commands(
    *,
    project: str,
    account: str,
    billing_account: str,
    network: str,
    subnet: str,
    proof_id: str,
    artifact_manifest: Mapping[str, Any],
    user_data_path: Path,
) -> dict[str, list[str]]:
    names = temporary_names(proof_id)
    archive = Path(str(artifact_manifest["archive"])).resolve()
    base = gcloud_base(project, account)
    archive_uri = f"gs://{names['bucket']}/{names['object']}"
    owner_slug = build_synthetic_first_boot_manifest(proof_id)["core_instance"]["owner_slug"]
    labels = "pios_role=self_hosted_core_proof,environment=r4_temporary_proof,cleanup=required"
    return {
        "verify_active_account": [*base, "auth", "list", "--filter", f"account={account}", "--format=json"],
        "verify_project": [*base, "projects", "describe", project, "--format=json"],
        "verify_billing": [*base, "billing", "projects", "describe", project, "--format=json"],
        "verify_budget_visibility": [*base, "billing", "budgets", "list", f"--billing-account={billing_account}", "--format=json"],
        "verify_machine_type": [*base, "compute", "machine-types", "describe", DEFAULT_MACHINE_TYPE, f"--zone={DEFAULT_ZONE}", "--format=json"],
        "verify_regional_quota": [*base, "compute", "regions", "describe", DEFAULT_REGION, "--format=json"],
        "verify_network": [*base, "compute", "networks", "describe", network, "--format=json"],
        "verify_subnet": [*base, "compute", "networks", "subnets", "describe", subnet, f"--region={DEFAULT_REGION}", "--format=json"],
        "verify_iap_firewall": [*base, "compute", "firewall-rules", "list", f"--filter=network={network} AND direction=INGRESS", "--format=json"],
        "check_bucket_absent": [*base, "storage", "buckets", "describe", f"gs://{names['bucket']}"],
        "check_image_absent": [*base, "compute", "images", "describe", names["image"]],
        "check_boot_disk_absent": [*base, "compute", "disks", "describe", names["boot_disk"], f"--zone={DEFAULT_ZONE}"],
        "check_core_disk_absent": [*base, "compute", "disks", "describe", names["core_disk"], f"--zone={DEFAULT_ZONE}"],
        "check_key_disk_absent": [*base, "compute", "disks", "describe", names["key_disk"], f"--zone={DEFAULT_ZONE}"],
        "check_instance_absent": [*base, "compute", "instances", "describe", names["instance"], f"--zone={DEFAULT_ZONE}"],
        "create_bucket": [
            *base, "storage", "buckets", "create", f"gs://{names['bucket']}", f"--location={DEFAULT_REGION}",
            "--uniform-bucket-level-access", "--public-access-prevention",
        ],
        "upload_archive": [*base, "storage", "cp", str(archive), archive_uri],
        "create_image": [
            *base, "compute", "images", "create", names["image"], f"--source-uri={archive_uri}",
            "--architecture=ARM64", "--guest-os-features=GVNIC,UEFI_COMPATIBLE", f"--labels={labels}",
        ],
        "create_boot_disk": [
            *base, "compute", "disks", "create", names["boot_disk"], f"--zone={DEFAULT_ZONE}",
            f"--image={names['image']}", f"--size={DISK_SPECS['boot']}", f"--type={DISK_TYPE}", f"--labels={labels}",
        ],
        "create_core_disk": [
            *base, "compute", "disks", "create", names["core_disk"], f"--zone={DEFAULT_ZONE}",
            f"--size={DISK_SPECS['core']}", f"--type={DISK_TYPE}", f"--labels={labels}",
        ],
        "create_key_disk": [
            *base, "compute", "disks", "create", names["key_disk"], f"--zone={DEFAULT_ZONE}",
            f"--size={DISK_SPECS['keys']}", f"--type={DISK_TYPE}", f"--labels={labels}",
        ],
        "create_instance": [
            *base, "compute", "instances", "create", names["instance"], f"--zone={DEFAULT_ZONE}",
            f"--machine-type={DEFAULT_MACHINE_TYPE}",
            f"--network-interface=network={network},subnet={subnet},no-address,nic-type=GVNIC",
            f"--disk=name={names['boot_disk']},boot=yes,auto-delete=no",
            f"--disk=name={names['core_disk']},boot=no,auto-delete=no",
            f"--disk=name={names['key_disk']},boot=no,auto-delete=no",
            "--shielded-secure-boot", "--shielded-vtpm", "--shielded-integrity-monitoring",
            "--no-service-account", "--no-scopes", "--no-restart-on-failure",
            f"--metadata-from-file=user-data={user_data_path}", f"--labels={labels}",
        ],
        "serial_output": [*base, "compute", "instances", "get-serial-port-output", names["instance"], f"--zone={DEFAULT_ZONE}", "--port=1"],
        "iap_oslogin_health_readback": [
            *base, "compute", "ssh", names["instance"], f"--zone={DEFAULT_ZONE}", "--tunnel-through-iap", "--quiet",
            "--command", f"sudo cat /var/lib/pios-core/owners/{owner_slug}/core/system/bootstrap/health-check.json",
        ],
        "delete_instance": [*base, "compute", "instances", "delete", names["instance"], f"--zone={DEFAULT_ZONE}", "--quiet"],
        "delete_boot_disk": [*base, "compute", "disks", "delete", names["boot_disk"], f"--zone={DEFAULT_ZONE}", "--quiet"],
        "delete_core_disk": [*base, "compute", "disks", "delete", names["core_disk"], f"--zone={DEFAULT_ZONE}", "--quiet"],
        "delete_key_disk": [*base, "compute", "disks", "delete", names["key_disk"], f"--zone={DEFAULT_ZONE}", "--quiet"],
        "delete_image": [*base, "compute", "images", "delete", names["image"], "--quiet"],
        "delete_object": [*base, "storage", "rm", archive_uri],
        "delete_bucket": [*base, "storage", "buckets", "delete", f"gs://{names['bucket']}", "--quiet"],
    }


def command_preview(commands: Mapping[str, list[str]]) -> dict[str, str]:
    return {name: shlex.join(command) for name, command in commands.items()}


def build_plan(
    *,
    release_manifest_path: Path,
    evidence_readiness_path: Path,
    proof_id: str,
    project: str,
    account: str,
    billing_account: str,
    network: str,
    subnet: str,
    monthly_cost_ceiling_usd: float,
    proof_cost_ceiling_usd: float,
    budget_display_name: str,
) -> dict[str, Any]:
    source = validate_r4_release(
        release_manifest_path=release_manifest_path,
        evidence_readiness_path=evidence_readiness_path,
    )
    names = temporary_names(proof_id)
    manifest = build_synthetic_first_boot_manifest(proof_id)
    assert_all_gates_false(manifest)
    user_data_placeholder = Path(names["output_directory"]) / "r4-gcp-user-data.yaml"
    artifact_placeholder = {
        "archive": Path(names["output_directory"]) / names["object"],
    }
    commands = build_execution_commands(
        project=project,
        account=account,
        billing_account=billing_account,
        network=network,
        subnet=subnet,
        proof_id=proof_id,
        artifact_manifest=artifact_placeholder,
        user_data_path=user_data_placeholder,
    )
    return {
        "schema_version": PLAN_SCHEMA,
        "created_at": utc_now(),
        "status": "planned_zero_cloud_calls",
        "cloud_calls": 0,
        "provider": "google_cloud",
        "proof_id": proof_id,
        "source_artifact": source,
        "temporary_resources": names,
        "provider_baseline": {
            "region": DEFAULT_REGION,
            "zone": DEFAULT_ZONE,
            "machine_type": DEFAULT_MACHINE_TYPE,
            "architecture": "arm64",
            "disk_type": DISK_TYPE,
            "disk_sizes": DISK_SPECS,
            "guest_os_features": ["GVNIC", "UEFI_COMPATIBLE"],
            "shielded_vm": {"secure_boot": True, "vtpm": True, "integrity_monitoring": True},
            "network": network,
            "subnet": subnet,
            "external_ip": False,
            "service_account": False,
            "scopes": False,
            "operator_access": "IAP/OS Login only",
            "cloud_init_metadata_key": "user-data",
        },
        "synthetic_first_boot_manifest": manifest,
        "budget_cost_limits": {
            "billing_account": billing_account,
            "budget_display_name": budget_display_name,
            "monthly_cost_ceiling_usd": monthly_cost_ceiling_usd,
            "proof_cost_ceiling_usd": proof_cost_ceiling_usd,
            "owner_authorization_required_before_cloud_call": True,
        },
        "preflight_requirements": {
            "exact_project_and_account": True,
            "quota_and_machine_availability": True,
            "temporary_name_collisions": True,
            "private_vpc_subnet_and_iap_firewall": {"source_range": IAP_TCP_SOURCE_RANGE},
            "billing_budget_and_cost_limits": {
                "exact_project_billing_account_link": True,
                "named_project_scoped_usd_budget": budget_display_name,
                "required_thresholds": [0.5, 0.8, 1.0],
                "enabled_alert_delivery": True,
            },
            "permissions": "validated by the isolated full lifecycle and cleanup evidence; no IAM introspection API or reviewer role is required",
        },
        "requires_confirmation": CONFIRMATION_FLAG,
        "commands": command_preview(commands),
        "boundaries": [
            "planner makes zero Google Cloud calls",
            "temporary names must use pios-r4proof- and never persistent pios-core-solo names",
            "no owner data, credentials, Core Bundle hydration, app networking, or Owner Bind",
            "no endpoint, external IP, service account, or service scopes",
            "old retained deployment and legacy default-network import runners are not used",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan an isolated r4 Google Cloud proof without cloud calls.")
    parser.add_argument("--release-manifest", type=Path, default=R4_RELEASE_MANIFEST)
    parser.add_argument("--evidence-readiness", type=Path, default=R4_EVIDENCE_READINESS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--proof-id", default=DEFAULT_PROOF_ID)
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--account", default=DEFAULT_ACCOUNT)
    parser.add_argument("--billing-account", default="<owner-approved-billing-account>")
    parser.add_argument("--budget-display-name", default=DEFAULT_BUDGET_DISPLAY_NAME)
    parser.add_argument("--network", default=DEFAULT_NETWORK)
    parser.add_argument("--subnet", default=DEFAULT_SUBNET)
    parser.add_argument("--monthly-cost-ceiling-usd", type=float, default=0.0)
    parser.add_argument("--proof-cost-ceiling-usd", type=float, default=0.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_dir = resolve_repo_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    plan = build_plan(
        release_manifest_path=resolve_repo_path(args.release_manifest),
        evidence_readiness_path=resolve_repo_path(args.evidence_readiness),
        proof_id=args.proof_id,
        project=args.project,
        account=args.account,
        billing_account=args.billing_account,
        network=args.network,
        subnet=args.subnet,
        monthly_cost_ceiling_usd=args.monthly_cost_ceiling_usd,
        proof_cost_ceiling_usd=args.proof_cost_ceiling_usd,
        budget_display_name=args.budget_display_name,
    )
    output = output_dir / f"{args.proof_id}-plan.json"
    output.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
