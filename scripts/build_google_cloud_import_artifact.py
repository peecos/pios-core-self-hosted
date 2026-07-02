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

DEFAULT_PLAN = Path(
    "image-artifacts/google-cloud-import-plan/"
    "pios-core-self-hosted-qemu-arm64-proof-plan.json"
)
DEFAULT_QCOW2 = Path("image-artifacts/qemu-image-candidate/qemu-standalone-20260702.qcow2")
DEFAULT_OUTPUT_DIR = Path("image-artifacts/google-cloud-import-artifact")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def resolve_repo_path(path: Path) -> Path:
    return (REPO_ROOT / path).resolve() if not path.is_absolute() else path


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON file: {path}") from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_command(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def oldgnu_tar_tool() -> str:
    gtar = shutil.which("gtar")
    if gtar:
        return gtar
    tar = shutil.which("tar")
    if tar:
        probe = subprocess.run(
            [tar, "--format=oldgnu", "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        if probe.returncode == 0:
            return tar
    raise ValueError(
        "GNU tar with oldgnu format support is required for Google Cloud import artifacts. "
        "On macOS, install it with: brew install gnu-tar"
    )


def qemu_img_info(path: Path) -> dict[str, Any]:
    qemu_img = shutil.which("qemu-img")
    if not qemu_img:
        raise ValueError("qemu-img is not available on PATH")
    completed = run_command([qemu_img, "info", "--output=json", str(path)])
    return json.loads(completed.stdout)


def ensure_output_dir(output_dir: Path, *, force: bool) -> None:
    manifest = output_dir / "google-cloud-import-artifact-manifest.json"
    if output_dir.exists() and any(output_dir.iterdir()):
        if not force:
            raise ValueError(f"output directory is not empty: {output_dir}")
        if not manifest.exists():
            raise ValueError(
                "refusing to --force an output directory that is not a prior Google Cloud import artifact"
            )
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


def build_google_cloud_import_artifact(
    *,
    plan_path: Path,
    qcow2_path: Path,
    output_dir: Path,
    force: bool,
) -> dict[str, Any]:
    plan = load_json(plan_path)
    if plan.get("status") != "planned_zero_cloud_calls":
        raise ValueError("Google Cloud import plan must have status=planned_zero_cloud_calls")
    if plan.get("cloud_calls") != 0:
        raise ValueError("Google Cloud import plan must have cloud_calls=0")
    if plan.get("provider") != "google_cloud":
        raise ValueError("Google Cloud import plan must have provider=google_cloud")

    qemu_img = shutil.which("qemu-img")
    if not qemu_img:
        raise ValueError("qemu-img is not available on PATH")
    tar_tool = oldgnu_tar_tool()
    qcow2 = resolve_repo_path(qcow2_path)
    if not qcow2.is_file():
        raise ValueError(f"qcow2 image is missing: {qcow2}")
    output = resolve_repo_path(output_dir)
    ensure_output_dir(output, force=force)

    expected = plan["temporary_provider_artifacts"]
    raw_name = expected["raw_image"]
    archive_name = expected["raw_archive"]
    if raw_name != "disk.raw":
        raise ValueError("Google Cloud import artifact must use disk.raw inside the archive")
    raw_path = output / raw_name
    archive_path = output / archive_name

    source_info = qemu_img_info(qcow2)
    if source_info.get("format") != "qcow2":
        raise ValueError(f"expected qcow2 source image, got {source_info.get('format')!r}")

    run_command([qemu_img, "convert", "-p", "-f", "qcow2", "-O", "raw", str(qcow2), str(raw_path)])
    raw_sha256 = sha256_file(raw_path)
    (output / f"{raw_name}.sha256").write_text(f"{raw_sha256}  {raw_name}\n")

    run_command([tar_tool, "--format=oldgnu", "-Sczf", str(archive_path), raw_name], cwd=output)
    archive_sha256 = sha256_file(archive_path)
    (output / f"{archive_name}.sha256").write_text(f"{archive_sha256}  {archive_name}\n")

    tar_listing = run_command([tar_tool, "-tzf", str(archive_path)]).stdout.splitlines()
    if tar_listing != [raw_name]:
        raise ValueError(f"Google Cloud archive must contain only disk.raw, got: {tar_listing}")

    manifest = {
        "schema_version": "pios_google_cloud_import_artifact_v1",
        "created_at": utc_now(),
        "status": "passed",
        "cloud_calls": 0,
        "provider": "google_cloud",
        "source_plan": str(plan_path),
        "source_qcow2": str(qcow2),
        "source_qcow2_sha256": sha256_file(qcow2),
        "source_qcow2_info": source_info,
        "raw_image": str(raw_path),
        "raw_image_name": raw_name,
        "raw_image_sha256": raw_sha256,
        "raw_image_size_bytes": raw_path.stat().st_size,
        "archive": str(archive_path),
        "archive_name": archive_name,
        "archive_sha256": archive_sha256,
        "archive_size_bytes": archive_path.stat().st_size,
        "archive_listing": tar_listing,
        "tar_tool": tar_tool,
        "planned_cloud_storage_uri": expected["cloud_storage_uri"],
        "planned_custom_image_name": expected["custom_image_name"],
        "planned_proof_instance_name": expected["proof_instance_name"],
        "boundaries": [
            "local artifact only",
            "no Google Cloud calls",
            "no resource creation",
            "no owner data",
            "provider remains unsupported until proof completes",
        ],
    }
    manifest_path = output / "google-cloud-import-artifact-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the local Google Cloud import artifact from the standalone qcow2 proof image."
    )
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--qcow2", type=Path, default=DEFAULT_QCOW2)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    build_google_cloud_import_artifact(
        plan_path=resolve_repo_path(args.plan),
        qcow2_path=resolve_repo_path(args.qcow2),
        output_dir=resolve_repo_path(args.output_dir),
        force=args.force,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
