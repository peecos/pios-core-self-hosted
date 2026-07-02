from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.export_core_bundle import object_output_path

PROTECTED_ZONES = {"originals", "events"}
CORE_ZONES = {"originals", "events", "knowledge", "derived", "system"}


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


def aws_base(profile: str | None, region: str | None) -> list[str]:
    command = ["aws"]
    if profile:
        command += ["--profile", profile]
    if region:
        command += ["--region", region]
    return command


def parse_zone_key(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise ValueError("zone key mapping must be zone=key-id")
    zone, key_id = value.split("=", 1)
    if zone not in CORE_ZONES:
        raise ValueError(f"invalid zone: {zone}")
    if not key_id:
        raise ValueError(f"missing key id for zone: {zone}")
    return zone, key_id


def load_bundle_manifest(bundle_dir: Path) -> dict[str, Any]:
    return json.loads((bundle_dir / "manifest.json").read_text())


def object_metadata(bundle_id: str, item: dict[str, Any]) -> str:
    metadata = {
        "source-bundle-id": bundle_id,
        "source-zone": item["zone"],
        "source-sha256": item["sha256"],
    }
    return json.dumps(metadata, sort_keys=True)


def build_put_object_command(
    *,
    bucket: str,
    key: str,
    body_path: Path,
    zone: str,
    kms_key_id: str,
    retain_until: datetime | None,
    metadata: str,
    profile: str | None,
    region: str | None,
) -> list[str]:
    command = aws_base(profile, region) + [
        "s3api",
        "put-object",
        "--bucket",
        bucket,
        "--key",
        key,
        "--body",
        str(body_path),
        "--server-side-encryption",
        "aws:kms",
        "--ssekms-key-id",
        kms_key_id,
        "--checksum-algorithm",
        "SHA256",
        "--if-none-match",
        "*",
        "--metadata",
        metadata,
    ]
    if zone in PROTECTED_ZONES:
        if retain_until is None:
            raise ValueError("protected writes require retain_until")
        command += [
            "--object-lock-mode",
            "GOVERNANCE",
            "--object-lock-retain-until-date",
            retain_until.isoformat(),
        ]
    return command


def build_hydration_plan(
    *,
    bundle_dir: Path,
    destination_bucket: str,
    zone_kms_keys: dict[str, str],
    retention_days: int,
    retention_buffer_days: int,
    profile: str | None,
    region: str | None,
) -> dict[str, Any]:
    manifest = load_bundle_manifest(bundle_dir)
    retain_until = datetime.now(timezone.utc) + timedelta(
        days=retention_days + retention_buffer_days
    )
    planned_objects = []
    for item in manifest["objects"]:
        zone = item["zone"]
        if zone not in zone_kms_keys:
            raise ValueError(f"missing destination KMS key for zone: {zone}")
        source_path = object_output_path(bundle_dir, item["key"])
        planned_objects.append(
            {
                "zone": zone,
                "destination_bucket": destination_bucket,
                "destination_key": item["key"],
                "source_path": str(source_path),
                "source_sha256": item["sha256"],
                "protected": zone in PROTECTED_ZONES,
                "destination_kms_key_id": zone_kms_keys[zone],
                "retain_until": retain_until.isoformat()
                if zone in PROTECTED_ZONES
                else None,
                "command": build_put_object_command(
                    bucket=destination_bucket,
                    key=item["key"],
                    body_path=source_path,
                    zone=zone,
                    kms_key_id=zone_kms_keys[zone],
                    retain_until=retain_until if zone in PROTECTED_ZONES else None,
                    metadata=object_metadata(manifest["bundle_id"], item),
                    profile=profile,
                    region=region,
                ),
            }
        )
    return {
        "status": "preview_only",
        "aws_calls": 0,
        "bundle_id": manifest["bundle_id"],
        "source_bucket": manifest["source"]["bucket"],
        "destination_bucket": destination_bucket,
        "object_count": len(planned_objects),
        "authorization_required": "confirm_destination_hydration",
        "planned_objects": planned_objects,
    }


def hydrate_core_bundle(
    *,
    bundle_dir: Path,
    destination_bucket: str,
    zone_kms_keys: dict[str, str],
    retention_days: int,
    retention_buffer_days: int,
    profile: str | None,
    region: str | None,
    allow_same_bucket_test: bool,
) -> dict[str, Any]:
    plan = build_hydration_plan(
        bundle_dir=bundle_dir,
        destination_bucket=destination_bucket,
        zone_kms_keys=zone_kms_keys,
        retention_days=retention_days,
        retention_buffer_days=retention_buffer_days,
        profile=profile,
        region=region,
    )
    if (
        plan["source_bucket"] == destination_bucket
        and not allow_same_bucket_test
    ):
        raise ValueError(
            "destination bucket equals source bucket; pass --allow-same-bucket-test "
            "only for explicit non-production test hydration"
        )
    results = []
    for item in plan["planned_objects"]:
        results.append(
            {
                "destination_key": item["destination_key"],
                "result": run_command(item["command"]),
            }
        )
    return {
        "status": "hydrated",
        "bundle_id": plan["bundle_id"],
        "destination_bucket": destination_bucket,
        "object_count": len(results),
        "results": results,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Preview or hydrate a local Core Bundle into a destination AWS Core."
    )
    parser.add_argument("--bundle-dir", required=True, type=Path)
    parser.add_argument("--destination-bucket", required=True)
    parser.add_argument(
        "--zone-kms-key",
        action="append",
        default=[],
        help="Destination zone key mapping as zone=key-id. Required for each zone in the bundle.",
    )
    parser.add_argument("--retention-days", type=int, default=90)
    parser.add_argument("--retention-buffer-days", type=int, default=1)
    parser.add_argument("--profile")
    parser.add_argument("--region")
    parser.add_argument("--allow-same-bucket-test", action="store_true")
    parser.add_argument("--confirm-destination-hydration", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    zone_kms_keys = dict(parse_zone_key(value) for value in args.zone_kms_key)
    if not args.confirm_destination_hydration:
        result = build_hydration_plan(
            bundle_dir=args.bundle_dir,
            destination_bucket=args.destination_bucket,
            zone_kms_keys=zone_kms_keys,
            retention_days=args.retention_days,
            retention_buffer_days=args.retention_buffer_days,
            profile=args.profile,
            region=args.region,
        )
    else:
        result = hydrate_core_bundle(
            bundle_dir=args.bundle_dir,
            destination_bucket=args.destination_bucket,
            zone_kms_keys=zone_kms_keys,
            retention_days=args.retention_days,
            retention_buffer_days=args.retention_buffer_days,
            profile=args.profile,
            region=args.region,
            allow_same_bucket_test=args.allow_same_bucket_test,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
