from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.export_core_bundle import object_output_path, sha256_file


def load_bundle_manifest(bundle_dir: Path) -> dict[str, Any]:
    return json.loads((bundle_dir / "manifest.json").read_text())


def validate_core_bundle(bundle_dir: Path) -> dict[str, Any]:
    manifest = load_bundle_manifest(bundle_dir)
    failures: list[str] = []
    for item in manifest["objects"]:
        path = object_output_path(bundle_dir, item["key"])
        if not path.exists():
            failures.append(f"missing object: {item['key']}")
            continue
        actual_sha = sha256_file(path)
        if actual_sha != item["sha256"]:
            failures.append(f"sha256 mismatch: {item['key']}")

    if failures:
        raise ValueError("; ".join(failures))

    return {
        "status": "passed",
        "bundle_id": manifest["bundle_id"],
        "object_count": len(manifest["objects"]),
        "derived_rebuild_required": manifest.get("derived_rebuild_required", True),
        "authorization": manifest["authorization"],
    }


def restore_bundle_to_directory(bundle_dir: Path, restore_dir: Path) -> dict[str, Any]:
    result = validate_core_bundle(bundle_dir)
    manifest = load_bundle_manifest(bundle_dir)
    restore_dir.mkdir(parents=True, exist_ok=False)
    for item in manifest["objects"]:
        source = object_output_path(bundle_dir, item["key"])
        destination = restore_dir / item["key"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    result["restore_dir"] = str(restore_dir)
    result["restore_mode"] = "local_directory_copy"
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate a local Core Export Bundle and optionally restore it to a local directory."
    )
    parser.add_argument("--bundle-dir", required=True, type=Path)
    parser.add_argument("--restore-dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.restore_dir:
        result = restore_bundle_to_directory(args.bundle_dir, args.restore_dir)
    else:
        result = validate_core_bundle(args.bundle_dir)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
