from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def object_output_path(bundle_dir: Path, key: str) -> Path:
    if key.startswith("/") or ".." in Path(key).parts:
        raise ValueError(f"unsafe object key: {key}")
    return bundle_dir / "objects" / key


def build_get_object_command(
    *,
    bucket: str,
    key: str,
    version_id: str,
    output_path: Path,
    profile: str | None,
    region: str | None,
) -> list[str]:
    command = ["aws"]
    if profile:
        command += ["--profile", profile]
    if region:
        command += ["--region", region]
    command += [
        "s3api",
        "get-object",
        "--bucket",
        bucket,
        "--key",
        key,
        "--version-id",
        version_id,
        str(output_path),
    ]
    return command


def run_command(command: list[str]) -> dict[str, Any]:
    env = os.environ.copy()
    env.setdefault("DYLD_LIBRARY_PATH", "/opt/homebrew/opt/expat/lib")
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return json.loads(completed.stdout) if completed.stdout.strip() else {}


def write_checksums(bundle_dir: Path, exported_objects: list[dict[str, Any]]) -> Path:
    checksum_path = bundle_dir / "checksums.sha256"
    lines = [
        f"{item['sha256']}  objects/{item['key']}"
        for item in sorted(exported_objects, key=lambda value: value["key"])
    ]
    checksum_path.write_text("\n".join(lines) + "\n")
    return checksum_path


def package_tar_zst(bundle_dir: Path) -> Path:
    if shutil.which("tar") is None or shutil.which("zstd") is None:
        raise RuntimeError("tar and zstd are required to create .tar.zst bundles")
    archive_path = bundle_dir.with_suffix(".tar.zst")
    command = [
        "tar",
        "-C",
        str(bundle_dir.parent),
        "-cf",
        "-",
        bundle_dir.name,
    ]
    zstd_command = ["zstd", "-q", "-T0", "-o", str(archive_path)]
    tar_process = subprocess.Popen(command, stdout=subprocess.PIPE)
    zstd_process = subprocess.run(
        zstd_command,
        stdin=tar_process.stdout,
        check=True,
        capture_output=True,
        text=True,
    )
    if tar_process.stdout is not None:
        tar_process.stdout.close()
    tar_return = tar_process.wait()
    if tar_return != 0:
        raise RuntimeError(f"tar failed with exit code {tar_return}: {zstd_process.stderr}")
    return archive_path


def export_core_bundle(
    *,
    manifest: dict[str, Any],
    output_dir: Path,
    profile: str | None,
    region: str | None,
    package: bool,
) -> dict[str, Any]:
    bundle_dir = output_dir / manifest["bundle_id"]
    bundle_dir.mkdir(parents=True, exist_ok=False)
    (bundle_dir / "objects").mkdir()
    (bundle_dir / "provenance").mkdir()

    source_bucket = manifest["source"]["bucket"]
    exported_objects: list[dict[str, Any]] = []
    for item in manifest["objects"]:
        destination = object_output_path(bundle_dir, item["key"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        metadata = run_command(
            build_get_object_command(
                bucket=source_bucket,
                key=item["key"],
                version_id=item["version_id"],
                output_path=destination,
                profile=profile,
                region=region,
            )
        )
        actual_sha = sha256_file(destination)
        expected_sha = item.get("sha256")
        if expected_sha and actual_sha != expected_sha:
            raise ValueError(
                f"sha256 mismatch for {item['key']}: expected {expected_sha}, got {actual_sha}"
            )
        exported_objects.append(
            {
                **item,
                "sha256": actual_sha,
                "content_length": destination.stat().st_size,
                "aws_get_object": {
                    "version_id": metadata.get("VersionId"),
                    "ssekms_key_id_present": bool(metadata.get("SSEKMSKeyId")),
                    "object_lock_mode": metadata.get("ObjectLockMode"),
                },
            }
        )

    bundle_manifest = {
        **manifest,
        "exported_at": datetime.now(timezone.utc)
        .astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "objects": exported_objects,
    }
    manifest_path = bundle_dir / "manifest.json"
    manifest_path.write_text(json.dumps(bundle_manifest, indent=2, sort_keys=True) + "\n")
    checksum_path = write_checksums(bundle_dir, exported_objects)
    export_log = {
        "status": "exported",
        "bundle_id": manifest["bundle_id"],
        "object_count": len(exported_objects),
        "manifest_path": str(manifest_path),
        "checksums_path": str(checksum_path),
        "archive_path": None,
    }
    if package:
        export_log["archive_path"] = str(package_tar_zst(bundle_dir))
    (bundle_dir / "provenance" / "export-log.json").write_text(
        json.dumps(export_log, indent=2, sort_keys=True) + "\n"
    )
    return export_log


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export a Core Bundle from a manifest by copying listed S3 object versions."
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--profile")
    parser.add_argument("--region")
    parser.add_argument("--package", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = json.loads(args.manifest.read_text())
    result = export_core_bundle(
        manifest=manifest,
        output_dir=args.output_dir,
        profile=args.profile,
        region=args.region,
        package=args.package,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
