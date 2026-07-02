from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.package_self_hosted_qemu_image_candidate import (
    assert_no_backing_file,
    qemu_img_info,
    run_standalone_boot_proof,
)
from scripts.run_self_hosted_qemu_boot_proof import run

DEFAULT_RELEASE_MANIFEST = Path(
    "image-artifacts/qemu-image-candidate/qemu-standalone-20260702-release-manifest.json"
)
DEFAULT_OUTPUT_DIR = Path("image-artifacts/qemu-release-package")
DEFAULT_VALIDATION_DIR = Path("image-build/qemu-release-package-validation")


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


def clean_dir(path: Path) -> None:
    if path.exists():
        if not path.is_dir():
            raise ValueError(f"path exists and is not a directory: {path}")
        shutil.rmtree(path)
    path.mkdir(parents=True)


def write_release_readme(
    *,
    package_root: Path,
    manifest: dict[str, Any],
) -> None:
    (package_root / "README.md").write_text(
        "# PIOS Core Self-Hosted QEMU Image Candidate\n\n"
        "This package is a local proof artifact for a data-empty PIOS Core "
        "Self-Hosted QEMU image. It is not a signed public release yet.\n\n"
        "Contents:\n\n"
        f"- `{manifest['standalone_image_name']}`: standalone qcow2 image\n"
        f"- `{manifest['standalone_image_name']}.sha256`: SHA-256 checksum\n"
        "- `release-manifest.json`: release-style manifest\n\n"
        "Boundaries:\n\n"
        "- no real owner data;\n"
        "- synthetic owner proof only;\n"
        "- not signed;\n"
        "- provider support is tracked by separate provider proof records.\n"
    )


def build_package(
    *,
    release_manifest_path: Path,
    output_dir: Path,
    package_id: str,
) -> tuple[Path, dict[str, Any]]:
    manifest = load_json(release_manifest_path)
    if manifest.get("status") != "passed":
        raise ValueError("release manifest must have status=passed")
    standalone_image = Path(manifest["standalone_image"])
    checksum_file = Path(manifest["standalone_image_checksum_file"])
    if not standalone_image.is_absolute():
        standalone_image = resolve_repo_path(standalone_image)
    if not checksum_file.is_absolute():
        checksum_file = resolve_repo_path(checksum_file)
    if not standalone_image.is_file():
        raise ValueError(f"standalone image is missing: {standalone_image}")
    if not checksum_file.is_file():
        raise ValueError(f"checksum file is missing: {checksum_file}")

    package_root = output_dir / package_id
    clean_dir(package_root)
    shutil.copy2(standalone_image, package_root / standalone_image.name)
    shutil.copy2(checksum_file, package_root / checksum_file.name)
    shutil.copy2(release_manifest_path, package_root / "release-manifest.json")
    write_release_readme(package_root=package_root, manifest=manifest)

    archive = output_dir / f"{package_id}.tar.zst"
    if archive.exists():
        archive.unlink()
    run(
        [
            "tar",
            "--zstd",
            "-cf",
            str(archive),
            "-C",
            str(output_dir),
            package_id,
        ]
    )
    package_manifest = {
        "schema_version": "self_hosted_qemu_release_package_manifest_v1",
        "created_at": utc_now(),
        "status": "packaged",
        "package_id": package_id,
        "package_archive": str(archive),
        "package_archive_sha256": sha256_file(archive),
        "source_release_manifest": str(release_manifest_path),
        "included_files": sorted(
            str(path.relative_to(package_root))
            for path in package_root.rglob("*")
            if path.is_file()
        ),
        "boundaries": [
            "local proof package",
            "not signed",
            "not published",
            "no real owner data",
        ],
    }
    package_manifest_path = output_dir / f"{package_id}-package-manifest.json"
    package_manifest_path.write_text(json.dumps(package_manifest, indent=2, sort_keys=True) + "\n")
    return archive, package_manifest


def extract_package(*, archive: Path, validation_dir: Path) -> Path:
    clean_dir(validation_dir)
    run(["tar", "--zstd", "-xf", str(archive), "-C", str(validation_dir)])
    roots = [path for path in validation_dir.iterdir() if path.is_dir()]
    if len(roots) != 1:
        raise ValueError(f"expected exactly one extracted package root, found {len(roots)}")
    return roots[0]


def validate_extracted_package(
    *,
    extracted_root: Path,
    run_id: str,
    owner_id: str,
    owner_slug: str,
    env_name: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    manifest_path = extracted_root / "release-manifest.json"
    manifest = load_json(manifest_path)
    image = extracted_root / manifest["standalone_image_name"]
    checksum = extracted_root / f"{manifest['standalone_image_name']}.sha256"
    if not image.is_file():
        raise ValueError(f"extracted image is missing: {image}")
    if not checksum.is_file():
        raise ValueError(f"extracted checksum is missing: {checksum}")
    expected_digest = manifest["standalone_image_sha256"]
    actual_digest = sha256_file(image)
    if actual_digest != expected_digest:
        raise ValueError("extracted image checksum does not match release manifest")
    checksum_text = checksum.read_text().strip()
    if expected_digest not in checksum_text:
        raise ValueError("extracted checksum file does not contain expected digest")
    info = qemu_img_info(image)
    assert_no_backing_file(info)
    boot_proof = run_standalone_boot_proof(
        standalone_image=image,
        proof_dir=extracted_root / "proof",
        run_id=run_id,
        owner_id=owner_id,
        owner_slug=owner_slug,
        env_name=env_name,
        timeout_seconds=timeout_seconds,
    )
    if boot_proof["status"] != "passed":
        raise ValueError("extracted package boot proof failed")
    return {
        "status": "passed",
        "release_manifest": str(manifest_path),
        "image": str(image),
        "image_sha256": actual_digest,
        "qemu_img_info": info,
        "inspection": {
            "format": info.get("format"),
            "virtual_size": info.get("virtual-size"),
            "actual_size": info.get("actual-size"),
            "backing_file_present": False,
        },
        "boot_proof": boot_proof,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Package and validate a self-hosted QEMU release candidate by extracting and boot-proving it."
    )
    parser.add_argument("--release-manifest", type=Path, default=DEFAULT_RELEASE_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--validation-dir", type=Path, default=DEFAULT_VALIDATION_DIR)
    parser.add_argument("--package-id", default="pios-core-self-hosted-qemu-arm64-20260702")
    parser.add_argument("--run-id", default="qemu-release-package-20260702")
    parser.add_argument("--owner-id", default="owner_qemu_release_package_proof")
    parser.add_argument("--owner-slug", default="qemu-release-package-proof")
    parser.add_argument("--env-name", default="proof")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    release_manifest = resolve_repo_path(args.release_manifest)
    output_dir = resolve_repo_path(args.output_dir)
    validation_dir = resolve_repo_path(args.validation_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    archive, package_manifest = build_package(
        release_manifest_path=release_manifest,
        output_dir=output_dir,
        package_id=args.package_id,
    )
    extracted_root = extract_package(archive=archive, validation_dir=validation_dir)
    validation = validate_extracted_package(
        extracted_root=extracted_root,
        run_id=args.run_id,
        owner_id=args.owner_id,
        owner_slug=args.owner_slug,
        env_name=args.env_name,
        timeout_seconds=args.timeout_seconds,
    )
    result = {
        "schema_version": "self_hosted_qemu_release_package_validation_v1",
        "created_at": utc_now(),
        "status": "passed",
        "package": package_manifest,
        "validation": validation,
        "boundaries": [
            "simulated local download/extraction proof",
            "not signed",
            "not published",
            "no real owner data",
            "provider support is tracked by separate provider proof records",
        ],
    }
    result_path = output_dir / f"{args.package_id}-validation-result.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
