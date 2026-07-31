from __future__ import annotations

import argparse
import base64
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
    make_seed_iso,
    qemu_paths,
)
from scripts.prove_pios_starter_disk_image_hygiene import (
    load_json,
    release_image_from_manifest,
    resolve_repo_path,
    validate_release_image,
)
from scripts.build_self_hosted_qemu_image_candidate import create_overlay

DEFAULT_OUTPUT_DIR = Path("image-artifacts/pios-starter-disk-image-residue-inspection")
RESIDUE_INSPECTION_START = "PIOS_STARTER_RESIDUE_INSPECTION_START"
RESIDUE_INSPECTION_PASSED = "PIOS_STARTER_RESIDUE_INSPECTION_PASSED"
RESIDUE_INSPECTION_FAILED = "PIOS_STARTER_RESIDUE_INSPECTION_FAILED"

SEARCH_ROOTS = (
    "/var/lib/pios-core",
    "/var/lib/cloud",
    "/var/log",
    "/opt/pios-core",
    "/etc",
    "/home",
    "/root",
    "/tmp",
)

TEMPORARY_RESIDUE_PATHS = (
    "/tmp/pios-core-root.tar.gz",
    "/tmp/pios-self-hosted-manifest.json",
    "/tmp/pios-core-init-result.json",
    "/tmp/pios-core-health-check.json",
    "/mnt/pios-seed",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def utc_now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ").lower()


def resolve_manifest_relative_path(value: str, manifest_path: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (manifest_path.parent / path).resolve()


def derive_forbidden_token(
    manifest: dict[str, Any], manifest_path: Path, explicit_token: str | None
) -> tuple[str, str]:
    if explicit_token:
        return explicit_token, "explicit --forbidden-token"
    candidate_result_value = manifest.get("source_candidate_result")
    if not isinstance(candidate_result_value, str) or not candidate_result_value:
        raise ValueError(
            "release manifest has no source_candidate_result; provide --forbidden-token explicitly"
        )
    candidate_result_path = resolve_manifest_relative_path(candidate_result_value, manifest_path)
    if not candidate_result_path.is_file():
        raise ValueError(
            f"source candidate result is missing: {candidate_result_path}; provide --forbidden-token explicitly"
        )
    candidate_result = load_json(candidate_result_path)
    owner_slug = candidate_result.get("owner_slug")
    if not isinstance(owner_slug, str) or not owner_slug:
        raise ValueError(
            f"source candidate result has no owner_slug: {candidate_result_path}; provide --forbidden-token explicitly"
        )
    return owner_slug, f"source candidate result {candidate_result_path} owner_slug"


def build_residue_inspection_user_data(forbidden_token: str) -> str:
    token_b64 = base64.b64encode(forbidden_token.encode("utf-8")).decode("ascii")
    search_roots = " ".join(SEARCH_ROOTS)
    temporary_paths = " ".join(TEMPORARY_RESIDUE_PATHS)
    return (
        "#cloud-boothook\n"
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        "trap 'sync; shutdown -h now' EXIT\n"
        f"echo {RESIDUE_INSPECTION_START} | tee /dev/console\n"
        "test -x /opt/pios-core/bin/pios-core-init\n"
        "test ! -e /var/lib/pios-core || test -z \"$(find /var/lib/pios-core -mindepth 1 -print -quit)\"\n"
        f"for residue_path in {temporary_paths}; do test ! -e \"$residue_path\"; done\n"
        f"forbidden_token=\"$(printf %s {token_b64} | base64 -d)\"\n"
        f"for search_root in {search_roots}; do\n"
        "  test -e \"$search_root\" || continue\n"
        "  set +e\n"
        "  grep -R -a -F -- \"$forbidden_token\" \"$search_root\" >/dev/null 2>&1\n"
        "  grep_status=$?\n"
        "  set -e\n"
        f"  if [ \"$grep_status\" -ne 1 ]; then echo {RESIDUE_INSPECTION_FAILED}:$search_root | tee /dev/console; exit 1; fi\n"
        "done\n"
        f"echo {RESIDUE_INSPECTION_PASSED} | tee /dev/console\n"
    )


def run_residue_inspection(
    *,
    release_image: Path,
    output_dir: Path,
    run_id: str,
    forbidden_token: str,
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
        user_data=build_residue_inspection_user_data(forbidden_token),
        meta_data=f"instance-id: pios-starter-residue-{run_id}\nlocal-hostname: pios-starter-residue\n",
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
        stop_when_seen=(RESIDUE_INSPECTION_PASSED, RESIDUE_INSPECTION_FAILED),
    )
    serial_log_path.write_text(serial_log)
    passed = (
        RESIDUE_INSPECTION_START in serial_log
        and RESIDUE_INSPECTION_PASSED in serial_log
        and RESIDUE_INSPECTION_FAILED not in serial_log
    )
    return {
        "status": "passed" if passed else "failed",
        "overlay": str(overlay),
        "seed_iso": str(seed_iso),
        "serial_log": str(serial_log_path),
        "networking": "QEMU user networking with restrict=on; no outbound guest access configured",
        "checked_core_state_path": "/var/lib/pios-core",
        "checked_temporary_paths": list(TEMPORARY_RESIDUE_PATHS),
        "checked_token_search_roots": list(SEARCH_ROOTS),
        "markers": {
            "inspection_start_seen": RESIDUE_INSPECTION_START in serial_log,
            "inspection_passed_seen": RESIDUE_INSPECTION_PASSED in serial_log,
            "inspection_failed_seen": RESIDUE_INSPECTION_FAILED in serial_log,
        },
        "failure_lines": [
            line for line in serial_log.splitlines() if RESIDUE_INSPECTION_FAILED in line
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect a packaged PIOS Starter Disk Image for known temporary build/proof residue "
            "and a prior synthetic-owner token, using a disposable local QEMU overlay."
        )
    )
    parser.add_argument("--release-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--run-id", default=None)
    parser.add_argument(
        "--forbidden-token",
        default=None,
        help="Known synthetic owner/build token to reject; defaults to owner_slug from source_candidate_result.",
    )
    parser.add_argument("--timeout-seconds", type=int, default=900)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_id = args.run_id or f"pios-starter-residue-{utc_now_compact()}"
    manifest_path = resolve_repo_path(args.release_manifest)
    output_dir = resolve_repo_path(args.output_dir)
    manifest = load_json(manifest_path)
    release = validate_release_image(manifest, manifest_path)
    forbidden_token, forbidden_token_source = derive_forbidden_token(
        manifest, manifest_path, args.forbidden_token
    )
    inspection = run_residue_inspection(
        release_image=Path(release["image"]),
        output_dir=output_dir,
        run_id=run_id,
        forbidden_token=forbidden_token,
        timeout_seconds=args.timeout_seconds,
    )
    result = {
        "schema_version": "self_hosted_pios_starter_residue_inspection_v1",
        "created_at": utc_now(),
        "status": inspection["status"],
        "run_id": run_id,
        "release_manifest": str(manifest_path),
        "release_image": release,
        "forbidden_token": forbidden_token,
        "forbidden_token_source": forbidden_token_source,
        "inspection": inspection,
        "boundaries": [
            "disposable local QCOW2 overlay only",
            "no Core initialization or Owner Bind",
            "no real owner data, credentials, or keys",
            "no Core Bundle hydration",
            "no connector sync, scheduler, Core API, or application networking",
        ],
    }
    result_path = output_dir / f"{run_id}-result.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if inspection["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
