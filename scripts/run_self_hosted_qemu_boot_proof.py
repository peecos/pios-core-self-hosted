from __future__ import annotations

import argparse
import base64
import json
import shutil
import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_self_hosted_image_root import build_self_hosted_image_root

DEFAULT_BASE_IMAGE = Path("image-build/qemu-cloud/noble-server-cloudimg-arm64.img")
DEFAULT_OUTPUT_DIR = Path("image-build/qemu-repeat-proof")
DEFAULT_IMAGE_ROOT = Path("image-build/qemu-repeat-proof/image-root")
PROOF_START = "PIOS_QEMU_PROOF_START"
PROOF_DONE = "PIOS_QEMU_PROOF_DONE"


def utc_now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def run(
    command: list[str],
    *,
    cwd: Path = REPO_ROOT,
    timeout: int | None = None,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=capture,
        text=True,
        timeout=timeout,
    )


def find_first_existing(candidates: tuple[Path, ...], label: str) -> Path:
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise ValueError(f"could not find {label}; checked: {', '.join(str(path) for path in candidates)}")


def qemu_share_candidates(filename: str) -> tuple[Path, ...]:
    return (
        Path("/opt/homebrew/share/qemu") / filename,
        Path("/opt/homebrew/Cellar/qemu/11.0.2/share/qemu") / filename,
        Path("/usr/local/share/qemu") / filename,
        Path("/usr/share/qemu") / filename,
    )


def ensure_base_image(path: Path) -> Path:
    resolved = (REPO_ROOT / path).resolve() if not path.is_absolute() else path
    if not resolved.is_file():
        raise ValueError(
            "base cloud image is missing. Download and checksum-verify an arm64 "
            f"Ubuntu Noble cloud image first: {resolved}"
        )
    return resolved


def make_payload_archive(image_root: Path, output_dir: Path) -> Path:
    archive = output_dir / f"{image_root.name}.tar.gz"
    if archive.exists():
        archive.unlink()
    run(
        [
            "tar",
            "-czf",
            str(archive),
            "-C",
            str(image_root.parent),
            image_root.name,
        ]
    )
    return archive


def build_manifest(owner_id: str, owner_slug: str, env_name: str) -> dict[str, Any]:
    return {
        "manifest_version": "self_hosted_provisioning_manifest_v1",
        "core_instance": {
            "env_name": env_name,
            "owner_id": owner_id,
            "owner_slug": owner_slug,
        },
        "self_hosted": {
            "core_root": f"/var/lib/pios-core/owners/{owner_slug}/core",
            "key_store_path": f"/var/lib/pios-core/owners/{owner_slug}/keys",
            "key_provider": "local_dev_file_keys",
        },
        "services": {
            "start_core_api": False,
            "start_connectors": False,
            "start_scheduler": False,
        },
        "authorization": {
            "hydrate_bundle": False,
            "connector_sync": False,
            "broad_migration": False,
            "source_decommission": False,
        },
    }


def indent_block(value: str, spaces: int) -> str:
    return textwrap.indent(value.rstrip() + "\n", " " * spaces)


def write_seed(
    *,
    seed_dir: Path,
    seed_iso: Path,
    payload_archive: Path,
    owner_id: str,
    owner_slug: str,
    env_name: str,
) -> None:
    if seed_dir.exists():
        shutil.rmtree(seed_dir)
    seed_dir.mkdir(parents=True)
    manifest = json.dumps(
        build_manifest(owner_id=owner_id, owner_slug=owner_slug, env_name=env_name),
        indent=2,
        sort_keys=True,
    )
    payload_b64 = base64.b64encode(payload_archive.read_bytes()).decode("ascii")
    payload_b64_wrapped = "\n".join(textwrap.wrap(payload_b64, width=76))
    health_path = f"/var/lib/pios-core/owners/{owner_slug}/core/system/bootstrap/health-check.json"
    user_data = (
        "#cloud-config\n"
        "write_files:\n"
        "  - path: /tmp/pios-core-root.tar.gz\n"
        "    permissions: '0600'\n"
        "    encoding: b64\n"
        "    content: |\n"
        f"{indent_block(payload_b64_wrapped, 6)}"
        "  - path: /tmp/pios-self-hosted-manifest.json\n"
        "    permissions: '0600'\n"
        "    content: |\n"
        f"{indent_block(manifest, 6)}"
        "runcmd:\n"
        "  - [bash, -lc, \"set -euo pipefail; "
        f"echo {PROOF_START} | tee /dev/console; "
        "mkdir -p /opt/pios-core; "
        "tar -xzf /tmp/pios-core-root.tar.gz -C /opt/pios-core --strip-components=1; "
        "/opt/pios-core/bin/pios-core-init --manifest /tmp/pios-self-hosted-manifest.json | tee /tmp/pios-core-init-result.json /dev/console; "
        f"cat {health_path} | tee /tmp/pios-core-health-check.json /dev/console; "
        f"echo {PROOF_DONE} | tee /dev/console; "
        "sync; shutdown -h now\"]\n"
    )
    (seed_dir / "user-data").write_text(user_data)
    (seed_dir / "meta-data").write_text(
        f"instance-id: pios-qemu-{owner_slug}\nlocal-hostname: {owner_slug}\n"
    )
    if seed_iso.exists():
        seed_iso.unlink()
    run(
        [
            "hdiutil",
            "makehybrid",
            "-quiet",
            "-iso",
            "-joliet",
            "-default-volume-name",
            "cidata",
            "-o",
            str(seed_iso),
            str(seed_dir),
        ]
    )


def run_qemu_proof(
    *,
    base_image: Path,
    output_dir: Path,
    run_id: str,
    timeout_seconds: int,
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    qemu = shutil.which("qemu-system-aarch64")
    qemu_img = shutil.which("qemu-img")
    if not qemu:
        raise ValueError("qemu-system-aarch64 is not available on PATH")
    if not qemu_img:
        raise ValueError("qemu-img is not available on PATH")

    code_fd = find_first_existing(qemu_share_candidates("edk2-aarch64-code.fd"), "aarch64 EDK2 code fd")
    vars_template = find_first_existing(qemu_share_candidates("edk2-arm-vars.fd"), "aarch64 EDK2 vars fd")
    vars_fd = output_dir / f"{run_id}-edk2-arm-vars.fd"
    shutil.copy2(vars_template, vars_fd)

    overlay = output_dir / f"{run_id}.qcow2"
    if overlay.exists():
        overlay.unlink()
    run(
        [
            qemu_img,
            "create",
            "-f",
            "qcow2",
            "-F",
            "qcow2",
            "-b",
            str(base_image),
            str(overlay),
        ]
    )

    seed_iso = output_dir / f"{run_id}-seed.iso"
    command = [
        qemu,
        "-machine",
        "virt,accel=hvf,highmem=off",
        "-cpu",
        "host",
        "-m",
        "2048",
        "-smp",
        "2",
        "-drive",
        f"if=pflash,format=raw,readonly=on,file={code_fd}",
        "-drive",
        f"if=pflash,format=raw,file={vars_fd}",
        "-drive",
        f"if=virtio,format=qcow2,file={overlay}",
        "-drive",
        f"if=virtio,format=raw,readonly=on,file={seed_iso}",
        "-netdev",
        "user,id=net0",
        "-device",
        "virtio-net-pci,netdev=net0",
        "-nographic",
    ]
    completed = run(command, timeout=timeout_seconds)
    return completed, {
        "qemu_binary": qemu,
        "qemu_img_binary": qemu_img,
        "firmware_code_fd": str(code_fd),
        "firmware_vars_fd": str(vars_fd),
        "overlay": str(overlay),
        "seed_iso": str(seed_iso),
        "command": command,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a direct QEMU proof that a data-empty self-hosted Core initializes inside a fresh VM."
    )
    parser.add_argument("--base-image", type=Path, default=DEFAULT_BASE_IMAGE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--image-root", type=Path, default=DEFAULT_IMAGE_ROOT)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--owner-id", default=None)
    parser.add_argument("--owner-slug", default=None)
    parser.add_argument("--env-name", default="proof")
    parser.add_argument("--timeout-seconds", type=int, default=600)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_id = args.run_id or f"qemu-proof-{utc_now_compact().lower()}"
    owner_slug = args.owner_slug or run_id.replace("_", "-")
    owner_id = args.owner_id or f"owner_{owner_slug.replace('-', '_')}"
    output_dir = (REPO_ROOT / args.output_dir).resolve() if not args.output_dir.is_absolute() else args.output_dir
    image_root = (REPO_ROOT / args.image_root).resolve() if not args.image_root.is_absolute() else args.image_root
    output_dir.mkdir(parents=True, exist_ok=True)
    base_image = ensure_base_image(args.base_image)

    build_result = build_self_hosted_image_root(
        output_dir=image_root,
        force=True,
        run_hygiene=True,
    )
    payload_archive = make_payload_archive(image_root, output_dir)
    seed_dir = output_dir / f"{run_id}-seed"
    seed_iso = output_dir / f"{run_id}-seed.iso"
    write_seed(
        seed_dir=seed_dir,
        seed_iso=seed_iso,
        payload_archive=payload_archive,
        owner_id=owner_id,
        owner_slug=owner_slug,
        env_name=args.env_name,
    )
    completed, qemu_metadata = run_qemu_proof(
        base_image=base_image,
        output_dir=output_dir,
        run_id=run_id,
        timeout_seconds=args.timeout_seconds,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    log_path = output_dir / f"{run_id}-serial.log"
    log_path.write_text(output)
    passed = (
        completed.returncode == 0
        and PROOF_START in output
        and PROOF_DONE in output
        and '"schema_version": "self_hosted_core_init_result_v1"' in output
        and '"schema_version": "self_hosted_core_health_check_v1"' in output
        and '"status": "passed"' in output
    )
    result = {
        "schema_version": "self_hosted_qemu_boot_proof_result_v1",
        "status": "passed" if passed else "failed",
        "run_id": run_id,
        "owner_id": owner_id,
        "owner_slug": owner_slug,
        "env_name": args.env_name,
        "base_image": str(base_image),
        "output_dir": str(output_dir),
        "image_root_build": build_result,
        "payload_archive": str(payload_archive),
        "serial_log": str(log_path),
        "qemu": qemu_metadata,
        "markers": {
            "start_seen": PROOF_START in output,
            "done_seen": PROOF_DONE in output,
        },
        "notes": [
            "synthetic owner only",
            "no real owner data",
            "no bundle hydration",
            "not a publishable golden image artifact",
        ],
    }
    result_path = output_dir / f"{run_id}-result.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
