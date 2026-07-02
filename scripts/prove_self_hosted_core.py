from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.export_core_bundle import object_output_path, sha256_file
from scripts.validate_core_bundle import load_bundle_manifest, validate_core_bundle

CORE_ZONES = ("originals", "events", "knowledge", "derived", "system")
EVENT_REF_FIELDS = (
    "detail_ref",
    "history_manifest_ref",
    "manifest_ref",
    "original_ref",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def safe_core_key(key: str) -> Path:
    path = Path(key)
    if key.startswith("/") or ".." in path.parts:
        raise ValueError(f"unsafe Core key: {key}")
    if not path.parts or path.parts[0] not in CORE_ZONES:
        raise ValueError(f"Core key must start with a known zone: {key}")
    return path


def create_empty_core_root(local_core_root: Path) -> None:
    local_core_root.mkdir(parents=True, exist_ok=False)
    for zone in CORE_ZONES:
        (local_core_root / zone).mkdir()


def hydrate_bundle_to_local_core(bundle_dir: Path, local_core_root: Path) -> dict[str, Any]:
    validation = validate_core_bundle(bundle_dir)
    manifest = load_bundle_manifest(bundle_dir)
    create_empty_core_root(local_core_root)

    for item in manifest["objects"]:
        destination = local_core_root / safe_core_key(item["key"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(object_output_path(bundle_dir, item["key"]), destination)

    return {
        "status": "hydrated",
        "bundle_id": validation["bundle_id"],
        "object_count": validation["object_count"],
        "local_core_root": str(local_core_root),
        "zones": list(CORE_ZONES),
    }


def resolve_core_ref(
    value: str,
    *,
    local_core_root: Path,
    source_bucket: str,
) -> dict[str, Any]:
    if value.startswith("s3://"):
        parsed = urlparse(value)
        if parsed.netloc != source_bucket:
            raise ValueError(
                f"cross-bucket reference is not valid for this proof: {value}"
            )
        key = parsed.path.lstrip("/")
        ref_type = "s3"
    elif "://" in value:
        raise ValueError(f"unsupported reference scheme: {value}")
    else:
        key = value
        ref_type = "core_key"

    path = local_core_root / safe_core_key(key)
    return {
        "ref": value,
        "ref_type": ref_type,
        "key": key,
        "local_path": str(path),
        "exists": path.exists(),
        "content_length": path.stat().st_size if path.exists() else None,
    }


def collect_event_refs(event: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for field in EVENT_REF_FIELDS:
        value = event.get(field)
        if isinstance(value, str):
            refs.append(value)
    for field in ("original_refs", "related_refs"):
        value = event.get(field)
        if isinstance(value, list):
            refs.extend(item for item in value if isinstance(item, str))
    event_object_key = event.get("event_object_key")
    if isinstance(event_object_key, str):
        refs.append(event_object_key)
    return refs


def collect_manifest_refs(manifest: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for field in ("inputs", "outputs"):
        value = manifest.get(field)
        if isinstance(value, list):
            refs.extend(item for item in value if isinstance(item, str))
    return refs


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def verify_local_references(
    *,
    bundle_dir: Path,
    local_core_root: Path,
    source_bucket: str,
) -> dict[str, Any]:
    bundle_manifest = load_bundle_manifest(bundle_dir)
    objects_by_key = {item["key"]: item for item in bundle_manifest["objects"]}
    missing_objects = []
    sha_mismatches = []

    for key, item in objects_by_key.items():
        path = local_core_root / safe_core_key(key)
        if not path.exists():
            missing_objects.append(key)
            continue
        actual_sha = sha256_file(path)
        if actual_sha != item["sha256"]:
            sha_mismatches.append({"key": key, "expected": item["sha256"], "actual": actual_sha})

    event_checks: list[dict[str, Any]] = []
    manifest_checks: list[dict[str, Any]] = []
    unresolved_refs: list[dict[str, Any]] = []

    event_keys = sorted(key for key in objects_by_key if key.startswith("events/"))
    for key in event_keys:
        event_path = local_core_root / safe_core_key(key)
        event = load_json(event_path)
        resolved = [
            resolve_core_ref(ref, local_core_root=local_core_root, source_bucket=source_bucket)
            for ref in collect_event_refs(event)
        ]
        missing = [item for item in resolved if not item["exists"]]
        unresolved_refs.extend({"source_key": key, **item} for item in missing)
        event_checks.append(
            {
                "event_key": key,
                "event_id": event.get("event_id"),
                "event_type": event.get("event_type"),
                "resolved_ref_count": len(resolved),
                "missing_ref_count": len(missing),
            }
        )

    manifest_keys = sorted(
        key for key in objects_by_key if key.startswith("system/processing-manifests/")
    )
    for key in manifest_keys:
        manifest_path = local_core_root / safe_core_key(key)
        processing_manifest = load_json(manifest_path)
        resolved = [
            resolve_core_ref(ref, local_core_root=local_core_root, source_bucket=source_bucket)
            for ref in collect_manifest_refs(processing_manifest)
        ]
        missing = [item for item in resolved if not item["exists"]]
        unresolved_refs.extend({"source_key": key, **item} for item in missing)
        manifest_checks.append(
            {
                "manifest_key": key,
                "manifest_id": processing_manifest.get("manifest_id"),
                "status": processing_manifest.get("status"),
                "resolved_ref_count": len(resolved),
                "missing_ref_count": len(missing),
            }
        )

    if missing_objects or sha_mismatches or unresolved_refs:
        raise ValueError(
            json.dumps(
                {
                    "missing_objects": missing_objects,
                    "sha_mismatches": sha_mismatches,
                    "unresolved_refs": unresolved_refs[:20],
                    "unresolved_ref_count": len(unresolved_refs),
                },
                indent=2,
                sort_keys=True,
            )
        )

    return {
        "status": "passed",
        "object_count": len(objects_by_key),
        "event_count": len(event_checks),
        "processing_manifest_count": len(manifest_checks),
        "event_checks": event_checks,
        "processing_manifest_checks": manifest_checks,
    }


def select_history_detail(local_core_root: Path) -> dict[str, Any]:
    html_paths = sorted((local_core_root / "derived" / "update-details").glob("**/index.html"))
    if not html_paths:
        raise ValueError("no derived update detail HTML found")
    path = html_paths[0]
    return {
        "status": "passed",
        "relative_path": str(path.relative_to(local_core_root)),
        "content_length": path.stat().st_size,
        "title_marker_present": "<title" in path.read_text(errors="replace").lower(),
    }


def rebuild_local_event_index(local_core_root: Path) -> dict[str, Any]:
    events = []
    for path in sorted((local_core_root / "events").glob("**/*.json")):
        event = load_json(path)
        events.append(
            {
                "event_key": str(path.relative_to(local_core_root)),
                "event_id": event.get("event_id"),
                "event_type": event.get("event_type"),
                "occurred_time": event.get("occurred_time"),
                "source": event.get("source"),
                "title": event.get("title"),
                "summary": event.get("summary"),
            }
        )

    index_path = local_core_root / "derived" / "indexes" / "self-hosted-proof" / "event-index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index = {
        "schema_version": "self_hosted_event_index_v1",
        "generated_at": utc_now(),
        "source": "prove_self_hosted_core.py",
        "event_count": len(events),
        "events": events,
    }
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")
    return {
        "status": "passed",
        "index_key": str(index_path.relative_to(local_core_root)),
        "event_count": len(events),
    }


def prove_self_hosted_core(
    *,
    bundle_dir: Path,
    local_core_root: Path,
    rebuild_index: bool,
) -> dict[str, Any]:
    bundle_manifest = load_bundle_manifest(bundle_dir)
    source_bucket = bundle_manifest["source"]["bucket"]
    hydration = hydrate_bundle_to_local_core(bundle_dir, local_core_root)
    reference_proof = verify_local_references(
        bundle_dir=bundle_dir,
        local_core_root=local_core_root,
        source_bucket=source_bucket,
    )
    history_detail = select_history_detail(local_core_root)
    index_result = rebuild_local_event_index(local_core_root) if rebuild_index else None
    zone_counts = {
        zone: sum(1 for path in (local_core_root / zone).glob("**/*") if path.is_file())
        for zone in CORE_ZONES
    }
    return {
        "status": "passed",
        "proof_type": "self_hosted_local_restore_retrieval_render_rebuild",
        "bundle_id": bundle_manifest["bundle_id"],
        "source_bucket": source_bucket,
        "local_core_root": str(local_core_root),
        "hydration": hydration,
        "reference_proof": reference_proof,
        "history_detail": history_detail,
        "derived_index_rebuild": index_result,
        "zone_counts": zone_counts,
        "known_limits": [
            "This proof validates local restore/retrieval/render/rebuild, not self-hosted protected ingestion.",
            "The current source bundle contains no knowledge/ objects.",
        ],
        "authorization": {
            "new_owner_data_upload": False,
            "connector_sync": False,
            "source_decommission": False,
            "broad_migration": False,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prove a Core Bundle can hydrate into a local/self-hosted Core root and resolve references locally."
    )
    parser.add_argument("--bundle-dir", required=True, type=Path)
    parser.add_argument("--local-core-root", required=True, type=Path)
    parser.add_argument("--rebuild-derived-index", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = prove_self_hosted_core(
        bundle_dir=args.bundle_dir,
        local_core_root=args.local_core_root,
        rebuild_index=args.rebuild_derived_index,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
