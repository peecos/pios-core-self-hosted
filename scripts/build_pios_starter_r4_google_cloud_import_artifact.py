"""Build the isolated local Google Cloud import artifact for exact PIOS Starter r4."""
from __future__ import annotations

import argparse
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

from scripts.plan_pios_starter_r4_google_cloud_proof import (
    ARTIFACT_SCHEMA,
    PLAN_SCHEMA,
    R4_QCOW2,
    R4_QCOW2_SHA256,
    load_json,
    resolve_repo_path,
    sha256_file,
    validate_r4_release,
)

DEFAULT_PLAN = Path("image-artifacts/pios-starter-r4-gcp-proof-plan/r4-20260731-preview-plan.json")
DEFAULT_OUTPUT_DIR = Path("image-artifacts/pios-starter-r4-google-cloud-import-artifact-20260731")


class R4ImportArtifactError(ValueError):
    """Raised for an invalid local r4 import artifact input or output."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run_command(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True)


def oldgnu_tar_tool() -> str:
    gtar = shutil.which("gtar")
    if gtar:
        return gtar
    tar = shutil.which("tar")
    if tar:
        probe = subprocess.run([tar, "--format=oldgnu", "--help"], check=False, capture_output=True, text=True)
        if probe.returncode == 0:
            return tar
    raise R4ImportArtifactError("GNU tar with oldgnu support is required for an r4 Google import artifact")


def qemu_img_info(path: Path) -> dict[str, Any]:
    qemu_img = shutil.which("qemu-img")
    if not qemu_img:
        raise R4ImportArtifactError("qemu-img is not available on PATH")
    return json.loads(run_command([qemu_img, "info", "--output=json", str(path)]).stdout)


def ensure_empty_output(output_dir: Path) -> None:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise R4ImportArtifactError("r4 import-artifact output directory must be empty")
    output_dir.mkdir(parents=True, exist_ok=True)


def build_import_artifact(*, plan_path: Path, output_dir: Path) -> dict[str, Any]:
    plan = load_json(plan_path)
    if plan.get("schema_version") != PLAN_SCHEMA or plan.get("status") != "planned_zero_cloud_calls":
        raise R4ImportArtifactError("a passed zero-cloud-call r4 proof plan is required")
    if plan.get("cloud_calls") != 0 or plan.get("provider") != "google_cloud":
        raise R4ImportArtifactError("r4 plan must be local-only Google Cloud planning")
    source = plan.get("source_artifact")
    if not isinstance(source, dict) or source.get("qcow2_sha256") != R4_QCOW2_SHA256:
        raise R4ImportArtifactError("r4 plan is not bound to the required QCOW2 checksum")
    qcow2 = resolve_repo_path(R4_QCOW2)
    if not qcow2.is_file() or sha256_file(qcow2) != R4_QCOW2_SHA256:
        raise R4ImportArtifactError("the exact local r4 QCOW2 is unavailable or has changed")
    validate_r4_release(
        release_manifest_path=Path(source["release_manifest"]),
        evidence_readiness_path=Path(source["evidence_readiness"]),
    )
    ensure_empty_output(output_dir)
    qemu_info = qemu_img_info(qcow2)
    if qemu_info.get("format") != "qcow2":
        raise R4ImportArtifactError("r4 import source must be QCOW2")
    raw_name = "disk.raw"
    archive_name = plan["temporary_resources"]["object"]
    if not isinstance(archive_name, str) or not archive_name.endswith(".tar.gz"):
        raise R4ImportArtifactError("r4 plan must supply a temporary oldgnu tar.gz object name")
    raw_path = output_dir / raw_name
    archive_path = output_dir / archive_name
    qemu_img = shutil.which("qemu-img")
    if not qemu_img:
        raise R4ImportArtifactError("qemu-img is not available on PATH")
    tar_tool = oldgnu_tar_tool()
    run_command([qemu_img, "convert", "-p", "-f", "qcow2", "-O", "raw", str(qcow2), str(raw_path)])
    raw_sha256 = sha256_file(raw_path)
    (output_dir / f"{raw_name}.sha256").write_text(f"{raw_sha256}  {raw_name}\n")
    run_command([tar_tool, "--format=oldgnu", "-Sczf", str(archive_path), raw_name], cwd=output_dir)
    archive_sha256 = sha256_file(archive_path)
    (output_dir / f"{archive_name}.sha256").write_text(f"{archive_sha256}  {archive_name}\n")
    listing = run_command([tar_tool, "-tzf", str(archive_path)]).stdout.splitlines()
    if listing != [raw_name]:
        raise R4ImportArtifactError("r4 import archive must contain only disk.raw")
    manifest = {
        "schema_version": ARTIFACT_SCHEMA,
        "created_at": utc_now(),
        "status": "passed",
        "cloud_calls": 0,
        "provider": "google_cloud",
        "r4_qcow2": str(qcow2),
        "r4_qcow2_sha256": R4_QCOW2_SHA256,
        "source_plan": str(plan_path),
        "source_release_manifest": source["release_manifest"],
        "source_evidence_readiness": source["evidence_readiness"],
        "source_qcow2_info": qemu_info,
        "raw_image": str(raw_path),
        "raw_image_name": raw_name,
        "raw_image_sha256": raw_sha256,
        "raw_image_size_bytes": raw_path.stat().st_size,
        "archive": str(archive_path),
        "archive_name": archive_name,
        "archive_sha256": archive_sha256,
        "archive_size_bytes": archive_path.stat().st_size,
        "archive_listing": listing,
        "tar_tool": tar_tool,
        "temporary_resources": plan["temporary_resources"],
        "boundaries": [
            "exact r4 QCOW2 checksum bound before conversion",
            "disk.raw is the sole oldgnu archive member",
            "local artifact only; no Google Cloud call or resource",
            "artifact is for isolated temporary r4 proof only, never persistent pios-core-solo deployment",
        ],
    }
    manifest_path = output_dir / "r4-google-cloud-import-artifact-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a local oldgnu Google import artifact from exact PIOS Starter r4.")
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = build_import_artifact(
        plan_path=resolve_repo_path(args.plan), output_dir=resolve_repo_path(args.output_dir)
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
