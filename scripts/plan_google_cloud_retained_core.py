from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_ARTIFACT_MANIFEST = Path(
    "image-artifacts/google-cloud-import-artifact/google-cloud-import-artifact-manifest.json"
)
DEFAULT_OUTPUT_DIR = Path("image-artifacts/google-cloud-retained-core-plan")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def resolve_repo_path(path: Path) -> Path:
    return (REPO_ROOT / path).resolve() if not path.is_absolute() else path


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON file: {path}") from exc


def require_artifact(manifest: dict[str, Any]) -> None:
    if manifest.get("schema_version") != "pios_google_cloud_import_artifact_v1":
        raise ValueError("expected Google Cloud import artifact manifest")
    if manifest.get("status") != "passed" or manifest.get("cloud_calls") != 0:
        raise ValueError("artifact must be a passed local-only artifact")
    for key in ("archive", "archive_name", "archive_sha256"):
        if not manifest.get(key):
            raise ValueError(f"artifact manifest is missing {key}")


def gcloud_base(project: str, account: str) -> list[str]:
    return ["gcloud", "--project", project, "--account", account]


def build_commands(
    *,
    project: str,
    account: str,
    archive: str,
    bucket: str,
    image_name: str,
    instance_name: str,
    zone: str,
    machine_type: str,
    network: str,
    subnet: str,
    boot_disk: str,
    core_disk: str,
    key_disk: str,
    user_data: str,
) -> dict[str, list[str]]:
    base = gcloud_base(project, account)
    archive_uri = f"gs://{bucket}/{Path(archive).name}"
    return {
        "create_private_import_bucket": [
            *base, "storage", "buckets", "create", f"gs://{bucket}",
            "--location=europe-north1", "--uniform-bucket-level-access", "--public-access-prevention",
        ],
        "upload_data_empty_archive": [*base, "storage", "cp", archive, archive_uri],
        "create_arm64_golden_image": [
            *base, "compute", "images", "create", image_name, f"--source-uri={archive_uri}",
            "--architecture=ARM64", "--guest-os-features=GVNIC",
            "--labels=pios_role=self_hosted_core,owner_scope=one_owner,environment=gcp1_data_empty",
        ],
        "create_retained_core_disk": [
            *base, "compute", "disks", "create", core_disk, f"--zone={zone}",
            "--size=100GB", "--type=pd-balanced",
            "--labels=pios_role=self_hosted_core,owner_scope=one_owner,environment=gcp1_data_empty",
        ],
        "create_retained_boot_disk": [
            *base, "compute", "disks", "create", boot_disk, f"--zone={zone}",
            f"--image={image_name}", "--size=40GB", "--type=pd-balanced",
            "--labels=pios_role=self_hosted_core,owner_scope=one_owner,environment=gcp1_data_empty",
        ],
        "create_retained_key_disk": [
            *base, "compute", "disks", "create", key_disk, f"--zone={zone}",
            "--size=20GB", "--type=pd-balanced",
            "--labels=pios_role=self_hosted_core,owner_scope=one_owner,environment=gcp1_data_empty",
        ],
        "boot_retained_core_after_explicit_confirmation": [
            *base, "compute", "instances", "create", instance_name, f"--zone={zone}",
            f"--machine-type={machine_type}",
            f"--disk=name={boot_disk},boot=yes,mode=rw,auto-delete=no",
            f"--disk=name={core_disk},mode=rw,auto-delete=no",
            f"--disk=name={key_disk},mode=rw,auto-delete=no",
            f"--network-interface=network={network},subnet={subnet},no-address,nic-type=GVNIC",
            "--tags=pios-core-iap-ssh,pios-core-no-egress", "--no-service-account", "--no-scopes",
            "--shielded-secure-boot", "--shielded-vtpm", "--shielded-integrity-monitoring",
            "--deletion-protection", f"--metadata-from-file=user-data={user_data}",
            "--labels=pios_role=self_hosted_core,owner_scope=one_owner,environment=gcp1_data_empty",
        ],
    }


def build_plan(*, artifact_manifest_path: Path, **values: str) -> dict[str, Any]:
    artifact = load_json(artifact_manifest_path)
    require_artifact(artifact)
    archive = Path(artifact["archive"])
    if not archive.is_absolute():
        archive = resolve_repo_path(archive)
    if not archive.is_file():
        raise ValueError(f"archive is missing: {archive}")
    commands = build_commands(archive=str(archive), **values)
    return {
        "schema_version": "pios_google_cloud_retained_core_plan_v1",
        "created_at": utc_now(),
        "status": "planned_zero_cloud_calls",
        "cloud_calls": 0,
        "project": values["project"],
        "zone": values["zone"],
        "machine_type": values["machine_type"],
        "network": values["network"],
        "subnet": values["subnet"],
        "artifact_archive_sha256": artifact["archive_sha256"],
        "requires_confirmation_before_boot": "--confirm-gcp-retained-deploy",
        "commands": {name: " ".join(command) for name, command in commands.items()},
        "boundaries": [
            "dry-run only; this planner never calls Google Cloud",
            "no owner data or Core Bundle hydration",
            "no external IP, public listener, Cloud NAT, or service account",
            "metadata gates remain synthetic/data-empty and false",
            "legacy default-network import proof runner is prohibited",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan the retained, data-empty GCP Core deployment without cloud calls.")
    parser.add_argument("--artifact-manifest", type=Path, default=DEFAULT_ARTIFACT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--project", default="pios-core-solo")
    parser.add_argument("--account", default="valto@prifina.com")
    parser.add_argument("--bucket", default="pios-core-solo-import-staging")
    parser.add_argument("--image-name", default="pios-core-data-empty-arm64-v1")
    parser.add_argument("--instance-name", default="pios-core-solo")
    parser.add_argument("--zone", default="europe-north1-a")
    parser.add_argument("--machine-type", default="c4a-standard-2")
    parser.add_argument("--network", default="pios-core-vpc")
    parser.add_argument("--subnet", default="pios-core-en1")
    parser.add_argument("--boot-disk", default="pios-core-boot")
    parser.add_argument("--core-disk", default="pios-core-data")
    parser.add_argument("--key-disk", default="pios-core-keys")
    parser.add_argument("--user-data", default="REQUIRES_SYNTHETIC_CLOUD_INIT_USER_DATA")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = build_plan(
        artifact_manifest_path=resolve_repo_path(args.artifact_manifest),
        project=args.project, account=args.account, bucket=args.bucket, image_name=args.image_name,
        instance_name=args.instance_name, zone=args.zone, machine_type=args.machine_type,
        network=args.network, subnet=args.subnet, boot_disk=args.boot_disk, core_disk=args.core_disk, key_disk=args.key_disk,
        user_data=args.user_data,
    )
    output_dir = resolve_repo_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "retained-core-deployment-plan.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
