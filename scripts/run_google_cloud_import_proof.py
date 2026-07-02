from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_self_hosted_qemu_image_candidate import build_manifest

DEFAULT_ARTIFACT_MANIFEST = Path(
    "image-artifacts/google-cloud-import-artifact/google-cloud-import-artifact-manifest.json"
)
DEFAULT_OUTPUT_DIR = Path("image-artifacts/google-cloud-import-proof")
PROOF_START = "PIOS_GOOGLE_METADATA_INIT_START"
PROOF_DONE = "PIOS_GOOGLE_METADATA_INIT_DONE"
METADATA_MANIFEST_KEY = "pios-self-hosted-manifest"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def resolve_repo_path(path: Path) -> Path:
    return (REPO_ROOT / path).resolve() if not path.is_absolute() else path


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON file: {path}") from exc


def run_command(command: list[str], *, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def gcloud_base(project: str, account: str) -> list[str]:
    return ["gcloud", "--project", project, "--account", account]


def build_metadata_manifest(*, owner_id: str, owner_slug: str, env_name: str) -> str:
    return json.dumps(
        build_manifest(owner_id=owner_id, owner_slug=owner_slug, env_name=env_name),
        indent=2,
        sort_keys=True,
    )


def build_commands(
    *,
    artifact_manifest: dict[str, Any],
    project: str,
    account: str,
    bucket: str,
    bucket_location: str,
    zone: str,
    image_name: str,
    instance_name: str,
    machine_type: str,
    metadata_manifest_path: Path,
) -> dict[str, list[str]]:
    archive = Path(artifact_manifest["archive"])
    if not archive.is_absolute():
        archive = resolve_repo_path(archive)
    if not archive.is_file():
        raise ValueError(f"Google Cloud import archive is missing: {archive}")
    archive_uri = f"gs://{bucket}/{archive.name}"
    base = gcloud_base(project, account)
    return {
        "create_bucket": [
            *base,
            "storage",
            "buckets",
            "create",
            f"gs://{bucket}",
            f"--location={bucket_location}",
            "--uniform-bucket-level-access",
            "--public-access-prevention",
        ],
        "upload_archive": [
            *base,
            "storage",
            "cp",
            str(archive),
            archive_uri,
        ],
        "create_image": [
            *base,
            "compute",
            "images",
            "create",
            image_name,
            f"--source-uri={archive_uri}",
            "--architecture=ARM64",
            "--guest-os-features=GVNIC",
        ],
        "create_instance": [
            *base,
            "compute",
            "instances",
            "create",
            instance_name,
            f"--zone={zone}",
            f"--machine-type={machine_type}",
            f"--image={image_name}",
            "--network-interface=network=default,no-address,nic-type=GVNIC",
            "--no-restart-on-failure",
            f"--metadata-from-file={METADATA_MANIFEST_KEY}={metadata_manifest_path}",
        ],
        "serial_output": [
            *base,
            "compute",
            "instances",
            "get-serial-port-output",
            instance_name,
            f"--zone={zone}",
        ],
        "delete_instance": [
            *base,
            "compute",
            "instances",
            "delete",
            instance_name,
            f"--zone={zone}",
            "--quiet",
        ],
        "delete_image": [
            *base,
            "compute",
            "images",
            "delete",
            image_name,
            "--quiet",
        ],
        "delete_archive": [
            *base,
            "storage",
            "rm",
            archive_uri,
        ],
        "delete_bucket": [
            *base,
            "storage",
            "buckets",
            "delete",
            f"gs://{bucket}",
            "--quiet",
        ],
    }


def command_preview(commands: dict[str, list[str]]) -> dict[str, str]:
    return {name: " ".join(command) for name, command in commands.items()}


def cleanup(commands: dict[str, list[str]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for name in ("delete_instance", "delete_image", "delete_archive", "delete_bucket"):
        command = commands[name]
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
        results.append(
            {
                "step": name,
                "returncode": completed.returncode,
                "stdout": completed.stdout[-4000:],
                "stderr": completed.stderr[-4000:],
            }
        )
    return results


def classify_serial_failure(serial_output: str) -> str:
    if '"status": "metadata_unavailable"' in serial_output:
        return "google_metadata_endpoint_unavailable"
    if "Datasource DataSourceNone" in serial_output:
        return "google_metadata_datasource_not_available"
    if "Used fallback datasource" in serial_output:
        return "cloud_init_fallback_datasource"
    if "No such file or directory" in serial_output and "pios-core-init" in serial_output:
        return "pios_core_init_missing"
    if "Permission denied" in serial_output and "pios-core-init" in serial_output:
        return "pios_core_init_not_executable"
    return "proof_markers_not_seen"


def wait_for_serial_success(
    *,
    command: list[str],
    timeout_seconds: int,
    poll_seconds: int,
) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_output = ""
    attempts = 0
    while time.time() < deadline:
        attempts += 1
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
        last_output = (completed.stdout or "") + (completed.stderr or "")
        if PROOF_DONE in last_output:
            passed = (
                PROOF_START in last_output
                and '"schema_version": "self_hosted_core_init_result_v1"' in last_output
                and '"schema_version": "self_hosted_core_health_check_v1"' in last_output
                and '"status": "passed"' in last_output
            )
            return {
                "status": "passed" if passed else "failed",
                "attempts": attempts,
                "failure_reason": None if passed else classify_serial_failure(last_output),
                "proof_start_seen": PROOF_START in last_output,
                "proof_done_seen": True,
                "serial_output_tail": last_output[-12000:],
            }
        time.sleep(poll_seconds)
    return {
        "status": "failed",
        "attempts": attempts,
        "failure_reason": classify_serial_failure(last_output),
        "proof_start_seen": PROOF_START in last_output,
        "proof_done_seen": False,
        "serial_output_tail": last_output[-12000:],
    }


def run_google_cloud_import_proof(
    *,
    artifact_manifest_path: Path,
    output_dir: Path,
    project: str,
    account: str,
    bucket: str,
    bucket_location: str,
    zone: str,
    image_name: str,
    instance_name: str,
    machine_type: str,
    owner_id: str,
    owner_slug: str,
    env_name: str,
    confirm: bool,
    timeout_seconds: int,
    poll_seconds: int,
) -> dict[str, Any]:
    artifact_manifest = load_json(artifact_manifest_path)
    if artifact_manifest.get("status") != "passed":
        raise ValueError("artifact manifest must have status=passed")
    if artifact_manifest.get("cloud_calls") != 0:
        raise ValueError("artifact manifest must have cloud_calls=0")
    if artifact_manifest.get("provider") != "google_cloud":
        raise ValueError("artifact manifest must have provider=google_cloud")
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pios-gcp-proof-") as tmp:
        metadata_manifest_path = Path(tmp) / "pios-self-hosted-manifest.json"
        metadata_manifest_path.write_text(
            build_metadata_manifest(owner_id=owner_id, owner_slug=owner_slug, env_name=env_name)
        )
        commands = build_commands(
            artifact_manifest=artifact_manifest,
            project=project,
            account=account,
            bucket=bucket,
            bucket_location=bucket_location,
            zone=zone,
            image_name=image_name,
            instance_name=instance_name,
            machine_type=machine_type,
            metadata_manifest_path=metadata_manifest_path,
        )
        common = {
            "schema_version": "pios_google_cloud_import_proof_v1",
            "created_at": utc_now(),
            "provider": "google_cloud",
            "project": project,
            "account": account,
            "bucket": bucket,
            "bucket_location": bucket_location,
            "zone": zone,
            "image_name": image_name,
            "instance_name": instance_name,
            "machine_type": machine_type,
            "artifact_manifest": str(artifact_manifest_path),
            "archive_sha256": artifact_manifest["archive_sha256"],
            "commands": command_preview(commands),
            "boundaries": [
                "synthetic owner identity only",
                "no owner data",
                "cleanup expected",
            ],
        }
        if not confirm:
            result = {
                **common,
                "status": "preview_only",
                "cloud_calls": 0,
                "resource_creation_authorized": False,
            }
            (output_dir / "google-cloud-import-proof-preview.json").write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n"
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return result

        executed: list[dict[str, Any]] = []
        cleanup_results: list[dict[str, Any]] = []
        status = "failed"
        serial_result: dict[str, Any] | None = None
        try:
            for name in ("create_bucket", "upload_archive", "create_image", "create_instance"):
                completed = run_command(commands[name], timeout=timeout_seconds)
                executed.append(
                    {
                        "step": name,
                        "returncode": completed.returncode,
                        "stdout": completed.stdout[-4000:],
                        "stderr": completed.stderr[-4000:],
                    }
                )
            serial_result = wait_for_serial_success(
                command=commands["serial_output"],
                timeout_seconds=timeout_seconds,
                poll_seconds=poll_seconds,
            )
            status = "passed" if serial_result["status"] == "passed" else "failed"
        finally:
            cleanup_results = cleanup(commands)
        cleanup_complete = all(item["returncode"] == 0 for item in cleanup_results)
        if not cleanup_complete:
            status = "failed"
        result = {
            **common,
            "status": status,
            "resource_creation_authorized": True,
            "executed": executed,
            "serial_result": serial_result,
            "cleanup": cleanup_results,
            "cleanup_status": "complete" if cleanup_complete else "incomplete",
            "supported_status_after_proof": "experimental" if status == "passed" else "unsupported",
        }
        output = output_dir / "google-cloud-import-proof-result.json"
        output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(json.dumps(result, indent=2, sort_keys=True))
        return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run or preview the Google Cloud self-hosted import proof.")
    parser.add_argument("--artifact-manifest", type=Path, default=DEFAULT_ARTIFACT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--project", required=True)
    parser.add_argument("--account", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--bucket-location", default="europe-west4")
    parser.add_argument("--zone", default="europe-west4-a")
    parser.add_argument("--image-name", default="pios-core-self-hosted-qemu-arm64-proof-20260702")
    parser.add_argument("--instance-name", default="pios-core-gcp-proof-20260702")
    parser.add_argument("--machine-type", default="t2a-standard-1")
    parser.add_argument("--owner-id", default="owner_google_cloud_proof")
    parser.add_argument("--owner-slug", default="google-cloud-proof")
    parser.add_argument("--env-name", default="proof")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--poll-seconds", type=int, default=10)
    parser.add_argument("--confirm-gcp-resource-creation", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_google_cloud_import_proof(
        artifact_manifest_path=resolve_repo_path(args.artifact_manifest),
        output_dir=resolve_repo_path(args.output_dir),
        project=args.project,
        account=args.account,
        bucket=args.bucket,
        bucket_location=args.bucket_location,
        zone=args.zone,
        image_name=args.image_name,
        instance_name=args.instance_name,
        machine_type=args.machine_type,
        owner_id=args.owner_id,
        owner_slug=args.owner_slug,
        env_name=args.env_name,
        confirm=args.confirm_gcp_resource_creation,
        timeout_seconds=args.timeout_seconds,
        poll_seconds=args.poll_seconds,
    )
    return 0 if result["status"] in {"preview_only", "passed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
