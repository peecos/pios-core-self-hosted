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

from scripts.plan_google_cloud_retained_core import (
    build_commands,
    load_json,
    require_artifact,
    resolve_repo_path,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def require_data_empty_manifest(path: Path) -> None:
    manifest = load_json(path)
    services = manifest.get("services", {})
    authorization = manifest.get("authorization", {})
    required = {
        "start_core_api": services.get("start_core_api"),
        "start_connectors": services.get("start_connectors"),
        "start_scheduler": services.get("start_scheduler"),
        "hydrate_bundle": authorization.get("hydrate_bundle"),
        "connector_sync": authorization.get("connector_sync"),
        "broad_migration": authorization.get("broad_migration"),
        "source_decommission": authorization.get("source_decommission"),
    }
    unsafe = [name for name, value in required.items() if value is not False]
    if unsafe:
        raise ValueError(f"metadata manifest is not data-empty: {', '.join(unsafe)}")


def write_gce_user_data(manifest_path: Path, output_dir: Path) -> Path:
    manifest = load_json(manifest_path)
    owner_slug = manifest["core_instance"]["owner_slug"]
    health_path = f"/var/lib/pios-core/owners/{owner_slug}/core/system/bootstrap/health-check.json"
    content = json.dumps(manifest, indent=2, sort_keys=True)
    user_data = (
        "#cloud-config\nwrite_files:\n  - path: /tmp/pios-self-hosted-manifest.json\n"
        "    permissions: '0600'\n    content: |\n"
        + "\n".join(f"      {line}" for line in content.splitlines())
        + "\nruncmd:\n  - [bash, -lc, \"set -euo pipefail; "
        "echo PIOS_GCP1_FIRST_BOOT_START | tee /dev/console; "
        "/opt/pios-core/bin/pios-core-init --manifest /tmp/pios-self-hosted-manifest.json | tee /tmp/pios-core-init-result.json /dev/console; "
        f"cat {health_path} | tee /tmp/pios-core-health-check.json /dev/console; "
        "echo PIOS_GCP1_FIRST_BOOT_DONE | tee /dev/console\"]\n"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "gce-data-empty-user-data.yaml"
    path.write_text(user_data)
    return path


def preview_or_run(*, artifact_manifest: Path, metadata_manifest: Path, output_dir: Path, confirm: bool, values: dict[str, str]) -> dict[str, Any]:
    artifact = load_json(artifact_manifest)
    require_artifact(artifact)
    if not metadata_manifest.is_file():
        raise ValueError(f"metadata manifest is missing: {metadata_manifest}")
    require_data_empty_manifest(metadata_manifest)
    archive = Path(artifact["archive"])
    if not archive.is_absolute():
        archive = resolve_repo_path(archive)
    if not archive.is_file():
        raise ValueError(f"archive is missing: {archive}")
    user_data = write_gce_user_data(metadata_manifest, output_dir)
    commands = build_commands(archive=str(archive), user_data=str(user_data), **values)
    result: dict[str, Any] = {
        "schema_version": "pios_google_cloud_retained_core_execution_v1",
        "created_at": utc_now(), "project": values["project"],
        "status": "preview_only", "cloud_calls": 0,
        "requires_confirmation": "--confirm-gcp-retained-deploy",
        "commands": {name: " ".join(command) for name, command in commands.items()},
    }
    if confirm:
        executed = []
        for name in ("create_private_import_bucket", "upload_data_empty_archive", "create_arm64_golden_image", "create_retained_boot_disk", "create_retained_core_disk", "create_retained_key_disk", "boot_retained_core_after_explicit_confirmation"):
            completed = subprocess.run(commands[name], check=True, capture_output=True, text=True)
            executed.append({"step": name, "stdout": completed.stdout[-2000:], "stderr": completed.stderr[-2000:]})
        result.update(status="submitted", cloud_calls=len(executed), executed=executed)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "retained-core-execution-result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preview or explicitly submit the retained data-empty GCP Core deployment.")
    parser.add_argument("--artifact-manifest", type=Path, required=True)
    parser.add_argument("--metadata-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--project", default="pios-core-solo"); parser.add_argument("--account", required=True)
    parser.add_argument("--bucket", default="pios-core-solo-import-staging"); parser.add_argument("--image-name", default="pios-core-data-empty-arm64-v1")
    parser.add_argument("--instance-name", default="pios-core-solo"); parser.add_argument("--zone", default="europe-north1-a")
    parser.add_argument("--machine-type", default="c4a-standard-2"); parser.add_argument("--network", default="pios-core-vpc")
    parser.add_argument("--subnet", default="pios-core-en1"); parser.add_argument("--boot-disk", default="pios-core-boot"); parser.add_argument("--core-disk", default="pios-core-data"); parser.add_argument("--key-disk", default="pios-core-keys")
    parser.add_argument("--confirm-gcp-retained-deploy", action="store_true")
    args = parser.parse_args(argv)
    values = {key: getattr(args, key) for key in ("project", "account", "bucket", "image_name", "instance_name", "zone", "machine_type", "network", "subnet", "boot_disk", "core_disk", "key_disk")}
    result = preview_or_run(artifact_manifest=resolve_repo_path(args.artifact_manifest), metadata_manifest=resolve_repo_path(args.metadata_manifest), output_dir=resolve_repo_path(args.output_dir), confirm=args.confirm_gcp_retained_deploy, values=values)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
