from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

CORE_ZONES = ("originals", "events", "knowledge", "derived", "system")
PROTECTED_ZONES = ("originals", "events")
BOOTSTRAP_DIR = Path("system/bootstrap")
CORE_INSTANCE_RECORD = BOOTSTRAP_DIR / "core-instance.json"
ZONE_MANIFEST_RECORD = BOOTSTRAP_DIR / "zone-manifest.json"
KEY_MANIFEST_RECORD = BOOTSTRAP_DIR / "key-manifest.json"
HEALTH_CHECK_RECORD = BOOTSTRAP_DIR / "health-check.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json_manifest(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(
            "self-hosted provisioning manifest must be JSON. JSON is valid YAML, "
            "so a .yaml file may be used if its contents are JSON-formatted."
        ) from exc


def nested(manifest: dict[str, Any], *keys: str) -> Any:
    current: Any = manifest
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def require_string(manifest: dict[str, Any], *keys: str) -> str:
    value = nested(manifest, *keys)
    dotted = ".".join(keys)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing required string: {dotted}")
    return value.strip()


def require_false(manifest: dict[str, Any], *keys: str) -> None:
    value = nested(manifest, *keys)
    dotted = ".".join(keys)
    if value is not False:
        raise ValueError(f"{dotted} must be false for empty first-boot init")


def validate_owner_slug(owner_slug: str) -> None:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", owner_slug):
        raise ValueError(
            "core_instance.owner_slug must be 2-63 chars of lowercase letters, "
            "digits, or hyphens, and must start with a letter or digit"
        )


def validate_env_name(env_name: str) -> None:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", env_name):
        raise ValueError(
            "core_instance.env_name must be 2-63 chars of lowercase letters, "
            "digits, or hyphens, and must start with a letter or digit"
        )


def validate_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    manifest_version = require_string(manifest, "manifest_version")
    if manifest_version != "self_hosted_provisioning_manifest_v1":
        raise ValueError(
            "manifest_version must be self_hosted_provisioning_manifest_v1"
        )

    owner_id = require_string(manifest, "core_instance", "owner_id")
    if not owner_id.startswith("owner_"):
        raise ValueError("core_instance.owner_id must start with owner_")
    owner_slug = require_string(manifest, "core_instance", "owner_slug")
    validate_owner_slug(owner_slug)
    env_name = require_string(manifest, "core_instance", "env_name")
    validate_env_name(env_name)
    core_root = Path(require_string(manifest, "self_hosted", "core_root")).expanduser()
    key_store_path = Path(
        require_string(manifest, "self_hosted", "key_store_path")
    ).expanduser()
    if not core_root.is_absolute():
        raise ValueError("self_hosted.core_root must be an absolute path")
    if not key_store_path.is_absolute():
        raise ValueError("self_hosted.key_store_path must be an absolute path")
    key_provider = require_string(manifest, "self_hosted", "key_provider")
    if key_provider != "local_dev_file_keys":
        raise ValueError(
            "only self_hosted.key_provider=local_dev_file_keys is implemented"
        )
    require_false(manifest, "authorization", "hydrate_bundle")
    require_false(manifest, "authorization", "connector_sync")
    require_false(manifest, "authorization", "broad_migration")
    require_false(manifest, "authorization", "source_decommission")
    require_false(manifest, "services", "start_core_api")
    require_false(manifest, "services", "start_connectors")
    require_false(manifest, "services", "start_scheduler")

    return {
        "manifest_version": manifest_version,
        "owner_id": owner_id,
        "owner_slug": owner_slug,
        "env_name": env_name,
        "core_root": core_root,
        "key_store_path": key_store_path,
        "key_provider": key_provider,
    }


def write_json(path: Path, body: dict[str, Any], *, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(body, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if mode is None:
        path.write_bytes(payload)
        return
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
    except Exception:
        try:
            path.unlink()
        finally:
            raise


def key_fingerprint(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def create_local_keys(key_store_path: Path) -> dict[str, Any]:
    key_store_path.mkdir(parents=True, exist_ok=False)
    key_store_path.chmod(0o700)
    generated: dict[str, Any] = {
        "provider": "local_dev_file_keys",
        "keys": {},
        "warning": (
            "local_dev_file_keys are first-boot development keys for VM proofing; "
            "production self-hosted installs need a hardened key provider."
        ),
    }

    for name in (*CORE_ZONES, "signing"):
        secret = secrets.token_hex(32)
        fingerprint = key_fingerprint(secret)
        filename = f"{name}.key"
        write_json(
            key_store_path / filename,
            {
                "schema_version": "local_dev_key_v1",
                "key_name": name,
                "secret": secret,
            },
            mode=0o600,
        )
        generated["keys"][name] = {
            "key_id": f"local-dev:{name}:{fingerprint[:16]}",
            "fingerprint": fingerprint,
            "path": str(key_store_path / filename),
        }
    return generated


def build_bootstrap_records(
    *,
    config: dict[str, Any],
    key_manifest: dict[str, Any],
    created_at: str,
) -> dict[str, dict[str, Any]]:
    key_manifest_public = {
        "schema_version": "core_key_manifest_v1",
        "created_at": created_at,
        "provider": key_manifest["provider"],
        "keys": {
            name: {
                "key_id": value["key_id"],
                "fingerprint": value["fingerprint"],
            }
            for name, value in key_manifest["keys"].items()
        },
        "key_material_stored_outside_core": True,
    }
    return {
        str(CORE_INSTANCE_RECORD): {
            "schema_version": "self_hosted_core_instance_v1",
            "created_at": created_at,
            "env_name": config["env_name"],
            "owner_id": config["owner_id"],
            "owner_slug": config["owner_slug"],
            "storage_adapter": "local_filesystem",
            "core_root": str(config["core_root"]),
            "zones": list(CORE_ZONES),
            "authorization": {
                "hydrate_bundle": False,
                "connector_sync": False,
                "broad_migration": False,
                "source_decommission": False,
            },
        },
        str(ZONE_MANIFEST_RECORD): {
            "schema_version": "core_zone_manifest_v1",
            "created_at": created_at,
            "zones": {
                zone: {
                    "path": zone,
                    "protected": zone in PROTECTED_ZONES,
                    "canonical_storage": zone in ("originals", "events", "knowledge", "system"),
                    "derived": zone == "derived",
                }
                for zone in CORE_ZONES
            },
        },
        str(KEY_MANIFEST_RECORD): key_manifest_public,
    }


def health_check_core_root(core_root: Path, key_store_path: Path) -> dict[str, Any]:
    zone_results = {
        zone: {
            "exists": (core_root / zone).is_dir(),
            "file_count": sum(1 for path in (core_root / zone).glob("**/*") if path.is_file())
            if (core_root / zone).is_dir()
            else None,
        }
        for zone in CORE_ZONES
    }
    bootstrap_results = {
        str(record): (core_root / record).is_file()
        for record in (
            CORE_INSTANCE_RECORD,
            ZONE_MANIFEST_RECORD,
            KEY_MANIFEST_RECORD,
            HEALTH_CHECK_RECORD,
        )
    }
    key_results = {
        name: (key_store_path / f"{name}.key").is_file()
        for name in (*CORE_ZONES, "signing")
    }
    passed = (
        all(result["exists"] for result in zone_results.values())
        and all(bootstrap_results.values())
        and all(key_results.values())
    )
    return {
        "schema_version": "self_hosted_core_health_check_v1",
        "checked_at": utc_now(),
        "status": "passed" if passed else "failed",
        "zones": zone_results,
        "bootstrap_records": bootstrap_results,
        "keys": key_results,
    }


def ensure_not_initialized(core_root: Path, key_store_path: Path) -> None:
    if (core_root / CORE_INSTANCE_RECORD).exists():
        raise ValueError(f"Core root is already initialized: {core_root}")
    if core_root.exists():
        if any(core_root.iterdir()):
            raise ValueError(f"Core root exists and is not empty: {core_root}")
    if key_store_path.exists():
        if any(key_store_path.iterdir()):
            raise ValueError(f"key store path exists and is not empty: {key_store_path}")


def init_self_hosted_core(manifest: dict[str, Any]) -> dict[str, Any]:
    config = validate_manifest(manifest)
    core_root: Path = config["core_root"]
    key_store_path: Path = config["key_store_path"]
    ensure_not_initialized(core_root, key_store_path)
    created_at = utc_now()

    core_root.mkdir(parents=True, exist_ok=True)
    for zone in CORE_ZONES:
        (core_root / zone).mkdir()

    key_manifest = create_local_keys(key_store_path)
    for relative, body in build_bootstrap_records(
        config=config,
        key_manifest=key_manifest,
        created_at=created_at,
    ).items():
        write_json(core_root / relative, body)

    initial_health = {
        "schema_version": "self_hosted_core_health_check_v1",
        "checked_at": utc_now(),
        "status": "pending",
    }
    write_json(core_root / HEALTH_CHECK_RECORD, initial_health)
    health = health_check_core_root(core_root, key_store_path)
    write_json(core_root / HEALTH_CHECK_RECORD, health)
    if health["status"] != "passed":
        raise ValueError("self-hosted Core health check failed")

    return {
        "status": "initialized",
        "schema_version": "self_hosted_core_init_result_v1",
        "created_at": created_at,
        "owner_id": config["owner_id"],
        "owner_slug": config["owner_slug"],
        "core_root": str(core_root),
        "key_store_path": str(key_store_path),
        "zones": list(CORE_ZONES),
        "bootstrap_records": [
            str(CORE_INSTANCE_RECORD),
            str(ZONE_MANIFEST_RECORD),
            str(KEY_MANIFEST_RECORD),
            str(HEALTH_CHECK_RECORD),
        ],
        "health_check": health,
        "authorization": {
            "hydrate_bundle": False,
            "connector_sync": False,
            "broad_migration": False,
            "source_decommission": False,
        },
    }


def build_init_plan(manifest: dict[str, Any]) -> dict[str, Any]:
    config = validate_manifest(manifest)
    return {
        "status": "preview_only",
        "aws_calls": 0,
        "network_calls": 0,
        "owner_id": config["owner_id"],
        "owner_slug": config["owner_slug"],
        "core_root": str(config["core_root"]),
        "key_store_path": str(config["key_store_path"]),
        "zones": list(CORE_ZONES),
        "will_write_owner_data": False,
        "will_hydrate_bundle": False,
        "will_start_connectors": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Initialize an empty self-hosted PIOS Core root from a provisioning manifest."
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--preview", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = load_json_manifest(args.manifest)
    result = build_init_plan(manifest) if args.preview else init_self_hosted_core(manifest)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
