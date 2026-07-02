from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.validate_self_hosted_image_root import scan_image_root


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip()


def package_tar_zst(source_dir: Path, archive_path: Path) -> None:
    if shutil.which("tar") is None or shutil.which("zstd") is None:
        raise RuntimeError("tar and zstd are required to package the image root")
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    tar_command = [
        "tar",
        "-C",
        str(source_dir.parent),
        "-cf",
        "-",
        source_dir.name,
    ]
    zstd_command = ["zstd", "-q", "-T0", "-o", str(archive_path)]
    tar_process = subprocess.Popen(tar_command, stdout=subprocess.PIPE)
    try:
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
            raise RuntimeError(
                f"tar failed with exit code {tar_return}: {zstd_process.stderr}"
            )
    except Exception:
        if tar_process.stdout is not None:
            tar_process.stdout.close()
        tar_process.wait()
        if archive_path.exists():
            archive_path.unlink()
        raise


def package_self_hosted_image_root(
    *,
    image_root: Path,
    output_dir: Path,
    package_id: str,
) -> dict[str, Any]:
    hygiene = scan_image_root(image_root)
    if hygiene["status"] != "passed":
        raise ValueError(json.dumps(hygiene, indent=2, sort_keys=True))

    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / f"{package_id}.tar.zst"
    if archive_path.exists():
        raise ValueError(f"archive already exists: {archive_path}")
    package_tar_zst(image_root, archive_path)
    archive_sha256 = sha256_file(archive_path)
    manifest = {
        "schema_version": "self_hosted_image_package_manifest_v1",
        "created_at": utc_now(),
        "package_id": package_id,
        "source_commit": git_commit(),
        "image_root": str(image_root),
        "archive_path": str(archive_path),
        "archive_sha256": archive_sha256,
        "archive_size": archive_path.stat().st_size,
        "hygiene": hygiene,
        "authorization": {
            "hydrate_bundle": False,
            "connector_sync": False,
            "broad_migration": False,
            "source_decommission": False,
        },
        "boundary": (
            "This package is a data-empty install payload, not a booted VM image "
            "and not a Core Bundle."
        ),
    }
    manifest_path = output_dir / f"{package_id}.manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    checksum_path = output_dir / f"{package_id}.sha256"
    checksum_path.write_text(f"{archive_sha256}  {archive_path.name}\n")
    return {
        "status": "packaged",
        "package_id": package_id,
        "archive_path": str(archive_path),
        "manifest_path": str(manifest_path),
        "checksum_path": str(checksum_path),
        "archive_sha256": archive_sha256,
        "archive_size": archive_path.stat().st_size,
        "hygiene_status": hygiene["status"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Package a hygiene-passed self-hosted image root as a data-empty install payload."
    )
    parser.add_argument("--image-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--package-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = package_self_hosted_image_root(
        image_root=args.image_root,
        output_dir=args.output_dir,
        package_id=args.package_id,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
