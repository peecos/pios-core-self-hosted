from __future__ import annotations

import argparse
import json
import shutil
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.validate_self_hosted_image_root import scan_image_root

INCLUDED_FILES = (
    "self-hosted-provisioning-manifest.example.json",
    "image/self-hosted/README.md",
    "scripts/pios_core_init.py",
    "scripts/pios_google_metadata_init.py",
    "scripts/prove_self_hosted_core.py",
    "scripts/validate_core_bundle.py",
    "scripts/export_core_bundle.py",
)

INCLUDED_DIRS = (
    "schemas",
)

GENERATED_WRAPPER = "bin/pios-core-init"
IMAGE_MANIFEST = "IMAGE_MANIFEST.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def copy_tree(source: Path, destination: Path) -> None:
    if destination.exists():
        raise ValueError(f"destination already exists: {destination}")
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
    )


def ensure_empty_destination(output_dir: Path, *, force: bool) -> None:
    if output_dir.exists():
        if not output_dir.is_dir():
            raise ValueError(f"output path exists and is not a directory: {output_dir}")
        if any(output_dir.iterdir()):
            if not force:
                raise ValueError(f"output directory exists and is not empty: {output_dir}")
            manifest_path = output_dir / IMAGE_MANIFEST
            if not manifest_path.is_file():
                raise ValueError(
                    "refusing to --force a directory that is not a prior "
                    "self-hosted image root"
                )
            try:
                manifest = json.loads(manifest_path.read_text())
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "refusing to --force a directory with an invalid image manifest"
                ) from exc
            if manifest.get("schema_version") != "self_hosted_image_root_manifest_v1":
                raise ValueError(
                    "refusing to --force a directory with an unrecognized image manifest"
                )
            shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


def write_wrapper(output_dir: Path) -> None:
    wrapper = output_dir / GENERATED_WRAPPER
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    wrapper.write_text(
        "#!/usr/bin/env sh\n"
        "set -eu\n"
        'SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"\n'
        'exec python3 "$SCRIPT_DIR/../scripts/pios_core_init.py" "$@"\n'
    )
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


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


def build_image_manifest(output_dir: Path) -> dict[str, Any]:
    files = sorted(
        str(path.relative_to(output_dir))
        for path in output_dir.rglob("*")
        if path.is_file()
    )
    return {
        "schema_version": "self_hosted_image_root_manifest_v1",
        "created_at": utc_now(),
        "source_commit": git_commit(),
        "image_root_type": "data_empty_self_hosted_core_template",
        "included_files": files,
        "excluded_from_image": [
            "bundles/",
            "restore-proofs/",
            "cdk.out/",
            ".venv/",
            "provisioning-manifest.*.local.json",
            "docs/runbooks/*pilot*",
            "owner data",
            "generated key material",
            "AWS account ids, ARNs, bucket names, or profile names",
        ],
        "authorization": {
            "hydrate_bundle": False,
            "connector_sync": False,
            "broad_migration": False,
            "source_decommission": False,
        },
    }


def build_self_hosted_image_root(
    *,
    output_dir: Path,
    force: bool,
    run_hygiene: bool,
) -> dict[str, Any]:
    ensure_empty_destination(output_dir, force=force)
    copied: list[str] = []

    for relative in INCLUDED_FILES:
        source = REPO_ROOT / relative
        if not source.is_file():
            raise ValueError(f"included file is missing: {relative}")
        destination_relative = (
            "README.md" if relative == "image/self-hosted/README.md" else relative
        )
        copy_file(source, output_dir / destination_relative)
        copied.append(destination_relative)

    for relative in INCLUDED_DIRS:
        source = REPO_ROOT / relative
        if not source.is_dir():
            raise ValueError(f"included directory is missing: {relative}")
        copy_tree(source, output_dir / relative)
        copied.append(relative)

    write_wrapper(output_dir)
    copied.append(GENERATED_WRAPPER)

    manifest_path = output_dir / IMAGE_MANIFEST
    manifest_path.write_text(
        json.dumps(build_image_manifest(output_dir), indent=2, sort_keys=True) + "\n"
    )
    copied.append(IMAGE_MANIFEST)

    hygiene = scan_image_root(output_dir) if run_hygiene else None
    if hygiene and hygiene["status"] != "passed":
        raise ValueError(json.dumps(hygiene, indent=2, sort_keys=True))

    return {
        "status": "built",
        "image_root": str(output_dir),
        "copied": copied,
        "hygiene": hygiene,
        "next_step": "copy this image root into a VM image and run pios-core-init on first boot",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a data-empty self-hosted Core image-root directory from an explicit allowlist."
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--run-hygiene", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = build_self_hosted_image_root(
        output_dir=args.output_dir,
        force=args.force,
        run_hygiene=args.run_hygiene,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
