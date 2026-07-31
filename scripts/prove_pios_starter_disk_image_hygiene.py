from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_self_hosted_qemu_image_candidate import (
    boot_qemu,
    build_manifest,
    create_overlay,
    indent_block,
    make_seed_iso,
    qemu_paths,
)
from scripts.package_self_hosted_qemu_image_candidate import (
    assert_no_backing_file,
    qemu_img_info,
    sha256_file,
)

HYGIENE_PROOF_START = "PIOS_STARTER_HYGIENE_PROOF_START"
HYGIENE_EMPTY_STATE_OK = "PIOS_STARTER_HYGIENE_EMPTY_STATE_OK"
HYGIENE_PROOF_DONE = "PIOS_STARTER_HYGIENE_PROOF_DONE"
DEFAULT_OUTPUT_DIR = Path("image-artifacts/pios-starter-disk-image-hygiene")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def utc_now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ").lower()


def resolve_repo_path(path: Path) -> Path:
    return (REPO_ROOT / path).resolve() if not path.is_absolute() else path


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON file: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"release manifest must be a JSON object: {path}")
    return value


def release_image_from_manifest(manifest: dict[str, Any], manifest_path: Path) -> Path:
    if manifest.get("schema_version") != "self_hosted_qemu_image_release_manifest_v1":
        raise ValueError("release manifest has an unexpected schema_version")
    if manifest.get("status") != "passed":
        raise ValueError("release manifest must have status=passed")
    image_value = manifest.get("standalone_image")
    if not isinstance(image_value, str) or not image_value:
        raise ValueError("release manifest is missing standalone_image")
    image = Path(image_value)
    if not image.is_absolute():
        image = (manifest_path.parent / image).resolve()
    if not image.is_file():
        raise ValueError(f"standalone image is missing: {image}")
    return image


def validate_release_image(manifest: dict[str, Any], manifest_path: Path) -> dict[str, Any]:
    image = release_image_from_manifest(manifest, manifest_path)
    expected_sha256 = manifest.get("standalone_image_sha256")
    if not isinstance(expected_sha256, str) or not expected_sha256:
        raise ValueError("release manifest is missing standalone_image_sha256")
    actual_sha256 = sha256_file(image)
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"standalone image checksum mismatch: expected {expected_sha256}, got {actual_sha256}"
        )
    info = qemu_img_info(image)
    if info.get("format") != "qcow2":
        raise ValueError(f"standalone image must use qcow2 format, got {info.get('format')}")
    assert_no_backing_file(info)
    return {
        "image": str(image),
        "sha256": actual_sha256,
        "qemu_img_info": info,
    }


def build_hygiene_user_data(*, owner_id: str, owner_slug: str, env_name: str) -> str:
    manifest = json.dumps(
        build_manifest(owner_id=owner_id, owner_slug=owner_slug, env_name=env_name),
        indent=2,
        sort_keys=True,
    )
    health_path = f"/var/lib/pios-core/owners/{owner_slug}/core/system/bootstrap/health-check.json"
    return (
        "#cloud-config\n"
        "write_files:\n"
        "  - path: /tmp/pios-self-hosted-manifest.json\n"
        "    permissions: '0600'\n"
        "    content: |\n"
        f"{indent_block(manifest, 6)}"
        "runcmd:\n"
        "  - [bash, -lc, \"set -euo pipefail; trap 'sync; shutdown -h now' EXIT; "
        f"echo {HYGIENE_PROOF_START} | tee /dev/console; "
        "test -x /opt/pios-core/bin/pios-core-init; "
        "test ! -e /var/lib/pios-core || test -z \\\"$(find /var/lib/pios-core -mindepth 1 -print -quit)\\\"; "
        f"echo {HYGIENE_EMPTY_STATE_OK} | tee /dev/console; "
        "/opt/pios-core/bin/pios-core-init --manifest /tmp/pios-self-hosted-manifest.json | tee /tmp/pios-core-init-result.json /dev/console; "
        f"cat {health_path} | tee /tmp/pios-core-health-check.json /dev/console; "
        f"echo {HYGIENE_PROOF_DONE} | tee /dev/console\"]\n"
    )


def run_hygiene_proof(
    *,
    release_image: Path,
    output_dir: Path,
    run_id: str,
    owner_id: str,
    owner_slug: str,
    env_name: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    qemu = qemu_paths()
    output_dir.mkdir(parents=True, exist_ok=True)
    overlay = output_dir / f"{run_id}-overlay.qcow2"
    create_overlay(qemu_img=qemu["qemu_img"], backing_image=release_image, overlay=overlay)
    seed_iso = output_dir / f"{run_id}-seed.iso"
    make_seed_iso(
        seed_dir=output_dir / f"{run_id}-seed",
        seed_iso=seed_iso,
        user_data=build_hygiene_user_data(
            owner_id=owner_id,
            owner_slug=owner_slug,
            env_name=env_name,
        ),
        meta_data=f"instance-id: pios-starter-hygiene-{run_id}\nlocal-hostname: {owner_slug}\n",
    )
    serial_log_path = output_dir / f"{run_id}-serial.log"
    serial_log = boot_qemu(
        qemu=qemu["qemu"],
        code_fd=qemu["code_fd"],
        vars_template=qemu["vars_template"],
        vars_fd=output_dir / f"{run_id}-vars.fd",
        disk_image=overlay,
        seed_iso=seed_iso,
        timeout_seconds=timeout_seconds,
        live_log_path=serial_log_path,
        stop_when_seen=HYGIENE_PROOF_DONE,
    )
    serial_log_path.write_text(serial_log)
    health_schema_seen = '"schema_version": "self_hosted_core_health_check_v1"' in serial_log
    health_passed_seen = '"status": "passed"' in serial_log
    passed = (
        HYGIENE_PROOF_START in serial_log
        and HYGIENE_EMPTY_STATE_OK in serial_log
        and HYGIENE_PROOF_DONE in serial_log
        and health_schema_seen
        and health_passed_seen
    )
    return {
        "status": "passed" if passed else "failed",
        "overlay": str(overlay),
        "seed_iso": str(seed_iso),
        "serial_log": str(serial_log_path),
        "networking": "QEMU user networking with restrict=on; no outbound guest access",
        "markers": {
            "proof_start_seen": HYGIENE_PROOF_START in serial_log,
            "empty_core_state_seen": HYGIENE_EMPTY_STATE_OK in serial_log,
            "proof_done_seen": HYGIENE_PROOF_DONE in serial_log,
            "health_schema_seen": health_schema_seen,
            "health_passed_seen": health_passed_seen,
        },
        "synthetic_owner": {
            "owner_id": owner_id,
            "owner_slug": owner_slug,
            "env_name": env_name,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify a PIOS Starter Disk Image is standalone and begins with no Core state, "
            "then run a separate synthetic-owner first boot on a disposable QEMU overlay."
        )
    )
    parser.add_argument("--release-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--owner-id", default=None)
    parser.add_argument("--owner-slug", default=None)
    parser.add_argument("--env-name", default="starter-hygiene")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_id = args.run_id or f"pios-starter-hygiene-{utc_now_compact()}"
    owner_slug = args.owner_slug or f"{run_id}-owner"
    owner_id = args.owner_id or f"owner_synthetic_{owner_slug.replace('-', '_')}"
    manifest_path = resolve_repo_path(args.release_manifest)
    output_dir = resolve_repo_path(args.output_dir)
    manifest = load_json(manifest_path)
    release = validate_release_image(manifest, manifest_path)
    proof = run_hygiene_proof(
        release_image=Path(release["image"]),
        output_dir=output_dir,
        run_id=run_id,
        owner_id=owner_id,
        owner_slug=owner_slug,
        env_name=args.env_name,
        timeout_seconds=args.timeout_seconds,
    )
    result = {
        "schema_version": "self_hosted_pios_starter_hygiene_proof_v1",
        "created_at": utc_now(),
        "status": proof["status"],
        "run_id": run_id,
        "release_manifest": str(manifest_path),
        "release_image": release,
        "proof": proof,
        "boundaries": [
            "disposable local QCOW2 overlay only",
            "separate synthetic owner only",
            "no real owner data, credentials, or keys",
            "no Core Bundle hydration",
            "no connector sync, scheduler, Core API, or application networking",
        ],
    }
    result_path = output_dir / f"{run_id}-result.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    if proof["status"] != "passed":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
