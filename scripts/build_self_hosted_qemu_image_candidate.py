from __future__ import annotations

import argparse
import base64
import json
import shutil
import subprocess
import sys
import textwrap
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_self_hosted_image_root import build_self_hosted_image_root
from scripts.run_self_hosted_qemu_boot_proof import (
    DEFAULT_BASE_IMAGE,
    find_first_existing,
    make_payload_archive,
    qemu_share_candidates,
    run,
)

DEFAULT_OUTPUT_DIR = Path("image-build/qemu-image-candidate")
DEFAULT_GOOGLE_GVNIC_DEB_DIR = Path("image-build/google-gvnic-debs")
CANDIDATE_BUILD_START = "PIOS_QEMU_CANDIDATE_BUILD_START"
CANDIDATE_BUILD_DONE = "PIOS_QEMU_CANDIDATE_BUILD_DONE"
CANDIDATE_PROOF_START = "PIOS_QEMU_CANDIDATE_PROOF_START"
CANDIDATE_PROOF_DONE = "PIOS_QEMU_CANDIDATE_PROOF_DONE"


def utc_now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ").lower()


def resolve_repo_path(path: Path) -> Path:
    return (REPO_ROOT / path).resolve() if not path.is_absolute() else path


def ensure_base_image(path: Path) -> Path:
    resolved = resolve_repo_path(path)
    if not resolved.is_file():
        raise ValueError(f"base image is missing: {resolved}")
    return resolved


def indent_block(value: str, spaces: int) -> str:
    return textwrap.indent(value.rstrip() + "\n", " " * spaces)


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


def make_seed_iso(seed_dir: Path, seed_iso: Path, user_data: str, meta_data: str) -> None:
    if seed_dir.exists():
        shutil.rmtree(seed_dir)
    seed_dir.mkdir(parents=True)
    (seed_dir / "user-data").write_text(user_data)
    (seed_dir / "meta-data").write_text(meta_data)
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


def write_candidate_build_seed(
    *,
    seed_dir: Path,
    seed_iso: Path,
    payload_archive: Path,
    run_id: str,
    install_google_gvnic_modules: bool,
    google_gvnic_deb_dir: Path,
) -> None:
    payload_b64 = base64.b64encode(payload_archive.read_bytes()).decode("ascii")
    payload_b64_wrapped = "\n".join(textwrap.wrap(payload_b64, width=76))
    google_gvnic_setup = ""
    if install_google_gvnic_modules:
        debs = sorted(google_gvnic_deb_dir.glob("*.deb"))
        if not debs:
            raise ValueError(f"no .deb files found in Google gVNIC deb directory: {google_gvnic_deb_dir}")
        google_gvnic_setup = (
            "printf '%s\\n' gve > /etc/modules-load.d/pios-google-gvnic.conf; "
            "mkdir -p /mnt/pios-seed; "
            "mount -o ro LABEL=cidata /mnt/pios-seed || mount -o ro /dev/disk/by-label/cidata /mnt/pios-seed; "
            "ls -l /mnt/pios-seed/google-gvnic-debs | tee /dev/console; "
            "dpkg -i /mnt/pios-seed/google-gvnic-debs/*.deb; "
            "modinfo gve | tee /dev/console || true; "
            "modprobe gve || true; "
            "umount /mnt/pios-seed || true; "
        )
    user_data = (
        "#cloud-config\n"
        "write_files:\n"
        "  - path: /tmp/pios-core-root.tar.gz\n"
        "    permissions: '0600'\n"
        "    encoding: b64\n"
        "    content: |\n"
        f"{indent_block(payload_b64_wrapped, 6)}"
        "runcmd:\n"
        "  - [bash, -lc, \"set -euo pipefail; trap 'sync; shutdown -h now' EXIT; "
        f"echo {CANDIDATE_BUILD_START} | tee /dev/console; "
        "mkdir -p /opt/pios-core; "
        "tar -xzf /tmp/pios-core-root.tar.gz -C /opt/pios-core --strip-components=1; "
        "ln -sf /opt/pios-core/bin/pios-core-init /usr/local/bin/pios-core-init; "
        "test -x /usr/local/bin/pios-core-init; "
        "mkdir -p /etc/netplan /etc/cloud/cloud.cfg.d /etc/systemd/network; "
        "printf '%s\\n' 'network: {config: disabled}' > /etc/cloud/cloud.cfg.d/99-pios-disable-cloud-network-config.cfg; "
        "printf '%s\\n' "
        "'network:' "
        "'  version: 2' "
        "'  renderer: networkd' "
        "'  ethernets:' "
        "'    pios-any:' "
        "'      match:' "
        "'        name: e*' "
        "'      dhcp4: true' "
        "'      dhcp6: false' "
        "'      optional: true' "
        "> /etc/netplan/99-pios-dhcp.yaml; "
        "chmod 0600 /etc/netplan/99-pios-dhcp.yaml; "
        "netplan generate || true; "
        "printf '%s\\n' "
        "'[Match]' "
        "'Type=ether' "
        "'' "
        "'[Network]' "
        "'DHCP=ipv4' "
        "'IPv6AcceptRA=no' "
        "'LinkLocalAddressing=ipv4' "
        "'' "
        "'[DHCPv4]' "
        "'RouteMetric=100' "
        "'UseDNS=true' "
        "> /etc/systemd/network/10-pios-provider-dhcp.network; "
        "netplan generate || true; "
        f"{google_gvnic_setup}"
        "printf '%s\\n' "
        "'[Unit]' "
        "'Description=PIOS Google metadata first-boot init' "
        "'After=systemd-networkd.service network-online.target' "
        "'Wants=systemd-networkd.service network-online.target' "
        "'ConditionPathExists=/opt/pios-core/scripts/pios_google_metadata_init.py' "
        "'' "
        "'[Service]' "
        "'Type=oneshot' "
        "'Environment=PYTHONUNBUFFERED=1' "
        "'ExecStart=/usr/bin/python3 /opt/pios-core/scripts/pios_google_metadata_init.py --optional --retry-seconds 10' "
        "'StandardOutput=journal+console' "
        "'StandardError=journal+console' "
        "'RemainAfterExit=yes' "
        "'' "
        "'[Install]' "
        "'WantedBy=multi-user.target' "
        "> /etc/systemd/system/pios-google-metadata-init.service; "
        "systemctl enable systemd-networkd.service systemd-networkd-wait-online.service || true; "
        "systemctl enable pios-google-metadata-init.service; "
        "apt-get clean; "
        "rm -rf /var/lib/apt/lists/*; "
        "rm -f /tmp/pios-core-root.tar.gz; "
        "find /opt/pios-core -type d -name __pycache__ -prune -exec rm -rf {} +; "
        "cloud-init clean --logs --machine-id || true; "
        "truncate -s 0 /etc/machine-id || true; "
        "rm -f /var/lib/dbus/machine-id || true; "
        f"echo {CANDIDATE_BUILD_DONE} | tee /dev/console\"]\n"
    )
    make_seed_iso(
        seed_dir=seed_dir,
        seed_iso=seed_iso,
        user_data=user_data,
        meta_data=f"instance-id: pios-candidate-build-{run_id}\nlocal-hostname: pios-candidate-build\n",
    )
    if install_google_gvnic_modules:
        deb_target = seed_dir / "google-gvnic-debs"
        deb_target.mkdir(parents=True, exist_ok=True)
        for deb in sorted(google_gvnic_deb_dir.glob("*.deb")):
            shutil.copy2(deb, deb_target / deb.name)
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


def write_candidate_proof_seed(
    *,
    seed_dir: Path,
    seed_iso: Path,
    run_id: str,
    owner_id: str,
    owner_slug: str,
    env_name: str,
) -> None:
    manifest = json.dumps(
        build_manifest(owner_id=owner_id, owner_slug=owner_slug, env_name=env_name),
        indent=2,
        sort_keys=True,
    )
    health_path = f"/var/lib/pios-core/owners/{owner_slug}/core/system/bootstrap/health-check.json"
    user_data = (
        "#cloud-config\n"
        "write_files:\n"
        "  - path: /tmp/pios-self-hosted-manifest.json\n"
        "    permissions: '0600'\n"
        "    content: |\n"
        f"{indent_block(manifest, 6)}"
        "runcmd:\n"
        "  - [bash, -lc, \"set -euo pipefail; trap 'sync; shutdown -h now' EXIT; "
        f"echo {CANDIDATE_PROOF_START} | tee /dev/console; "
        "test -x /opt/pios-core/bin/pios-core-init; "
        "/opt/pios-core/bin/pios-core-init --manifest /tmp/pios-self-hosted-manifest.json | tee /tmp/pios-core-init-result.json /dev/console; "
        f"cat {health_path} | tee /tmp/pios-core-health-check.json /dev/console; "
        f"echo {CANDIDATE_PROOF_DONE} | tee /dev/console\"]\n"
    )
    make_seed_iso(
        seed_dir=seed_dir,
        seed_iso=seed_iso,
        user_data=user_data,
        meta_data=f"instance-id: pios-candidate-proof-{run_id}\nlocal-hostname: {owner_slug}\n",
    )


def qemu_paths() -> dict[str, str]:
    qemu = shutil.which("qemu-system-aarch64")
    qemu_img = shutil.which("qemu-img")
    if not qemu:
        raise ValueError("qemu-system-aarch64 is not available on PATH")
    if not qemu_img:
        raise ValueError("qemu-img is not available on PATH")
    return {
        "qemu": qemu,
        "qemu_img": qemu_img,
        "code_fd": str(find_first_existing(qemu_share_candidates("edk2-aarch64-code.fd"), "aarch64 EDK2 code fd")),
        "vars_template": str(find_first_existing(qemu_share_candidates("edk2-arm-vars.fd"), "aarch64 EDK2 vars fd")),
    }


def create_overlay(*, qemu_img: str, backing_image: Path, overlay: Path) -> None:
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
            str(backing_image),
            str(overlay),
        ]
    )


def boot_qemu(
    *,
    qemu: str,
    code_fd: str,
    vars_template: str,
    vars_fd: Path,
    disk_image: Path,
    seed_iso: Path,
    timeout_seconds: int,
    live_log_path: Path | None = None,
) -> str:
    shutil.copy2(vars_template, vars_fd)
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
        f"if=virtio,format=qcow2,file={disk_image}",
        "-drive",
        f"if=virtio,format=raw,readonly=on,file={seed_iso}",
        "-netdev",
        "user,id=net0",
        "-device",
        "virtio-net-pci,netdev=net0",
        "-nographic",
    ]
    process = subprocess.Popen(
        command,
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    output: list[str] = []

    def collect_output() -> None:
        if process.stdout is None:
            return
        log_handle = live_log_path.open("w") if live_log_path else None
        for line in process.stdout:
            output.append(line)
            if log_handle:
                log_handle.write(line)
                log_handle.flush()
        if log_handle:
            log_handle.close()

    reader = threading.Thread(target=collect_output, daemon=True)
    reader.start()
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if process.poll() is not None:
            reader.join(timeout=2)
            return "".join(output)
        recent = "".join(output[-200:])
        if "reboot: Power down" in recent or "Reached target \x1b[0;1;39mpoweroff.target" in recent:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
            reader.join(timeout=2)
            return "".join(output)
        time.sleep(0.5)
    process.kill()
    process.wait(timeout=10)
    reader.join(timeout=2)
    raise subprocess.TimeoutExpired(command, timeout_seconds, output="".join(output))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build and prove a local QEMU/cloud-image self-hosted Core image candidate."
    )
    parser.add_argument("--base-image", type=Path, default=DEFAULT_BASE_IMAGE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--owner-id", default=None)
    parser.add_argument("--owner-slug", default=None)
    parser.add_argument("--env-name", default="proof")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument(
        "--install-google-gvnic-modules",
        action="store_true",
        help="Install the matching linux-modules-extra package so Google gVNIC can bind on T2A imports.",
    )
    parser.add_argument("--google-gvnic-deb-dir", type=Path, default=DEFAULT_GOOGLE_GVNIC_DEB_DIR)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_id = args.run_id or f"qemu-candidate-{utc_now_compact()}"
    owner_slug = args.owner_slug or f"{run_id}-owner"
    owner_id = args.owner_id or f"owner_{owner_slug.replace('-', '_')}"
    output_dir = resolve_repo_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    base_image = ensure_base_image(args.base_image)
    qemu = qemu_paths()

    image_root = output_dir / "image-root"
    build_result = build_self_hosted_image_root(
        output_dir=image_root,
        force=True,
        run_hygiene=True,
    )
    payload_archive = make_payload_archive(image_root, output_dir)

    candidate_image = output_dir / f"{run_id}-candidate.qcow2"
    create_overlay(qemu_img=qemu["qemu_img"], backing_image=base_image, overlay=candidate_image)
    build_seed = output_dir / f"{run_id}-build-seed.iso"
    write_candidate_build_seed(
        seed_dir=output_dir / f"{run_id}-build-seed",
        seed_iso=build_seed,
        payload_archive=payload_archive,
        run_id=run_id,
        install_google_gvnic_modules=args.install_google_gvnic_modules,
        google_gvnic_deb_dir=resolve_repo_path(args.google_gvnic_deb_dir),
    )
    build_log = boot_qemu(
        qemu=qemu["qemu"],
        code_fd=qemu["code_fd"],
        vars_template=qemu["vars_template"],
        vars_fd=output_dir / f"{run_id}-build-vars.fd",
        disk_image=candidate_image,
        seed_iso=build_seed,
        timeout_seconds=args.timeout_seconds,
        live_log_path=output_dir / f"{run_id}-build-serial-live.log",
    )
    build_log_path = output_dir / f"{run_id}-build-serial.log"
    build_log_path.write_text(build_log)
    build_passed = CANDIDATE_BUILD_START in build_log and CANDIDATE_BUILD_DONE in build_log

    proof_overlay = output_dir / f"{run_id}-proof-overlay.qcow2"
    create_overlay(qemu_img=qemu["qemu_img"], backing_image=candidate_image, overlay=proof_overlay)
    proof_seed = output_dir / f"{run_id}-proof-seed.iso"
    write_candidate_proof_seed(
        seed_dir=output_dir / f"{run_id}-proof-seed",
        seed_iso=proof_seed,
        run_id=run_id,
        owner_id=owner_id,
        owner_slug=owner_slug,
        env_name=args.env_name,
    )
    proof_log = boot_qemu(
        qemu=qemu["qemu"],
        code_fd=qemu["code_fd"],
        vars_template=qemu["vars_template"],
        vars_fd=output_dir / f"{run_id}-proof-vars.fd",
        disk_image=proof_overlay,
        seed_iso=proof_seed,
        timeout_seconds=args.timeout_seconds,
        live_log_path=output_dir / f"{run_id}-proof-serial-live.log",
    )
    proof_log_path = output_dir / f"{run_id}-proof-serial.log"
    proof_log_path.write_text(proof_log)
    proof_passed = (
        CANDIDATE_PROOF_START in proof_log
        and CANDIDATE_PROOF_DONE in proof_log
        and '"schema_version": "self_hosted_core_init_result_v1"' in proof_log
        and '"schema_version": "self_hosted_core_health_check_v1"' in proof_log
        and '"status": "passed"' in proof_log
    )
    result = {
        "schema_version": "self_hosted_qemu_image_candidate_result_v1",
        "status": "passed" if build_passed and proof_passed else "failed",
        "run_id": run_id,
        "owner_id": owner_id,
        "owner_slug": owner_slug,
        "base_image": str(base_image),
        "candidate_image": str(candidate_image),
        "proof_overlay": str(proof_overlay),
        "image_root_build": build_result,
        "install_google_gvnic_modules": args.install_google_gvnic_modules,
        "google_gvnic_deb_dir": str(resolve_repo_path(args.google_gvnic_deb_dir))
        if args.install_google_gvnic_modules
        else None,
        "payload_archive": str(payload_archive),
        "build_serial_log": str(build_log_path),
        "proof_serial_log": str(proof_log_path),
        "markers": {
            "candidate_build_start_seen": CANDIDATE_BUILD_START in build_log,
            "candidate_build_done_seen": CANDIDATE_BUILD_DONE in build_log,
            "candidate_proof_start_seen": CANDIDATE_PROOF_START in proof_log,
            "candidate_proof_done_seen": CANDIDATE_PROOF_DONE in proof_log,
        },
        "boundaries": [
            "synthetic owner only",
            "candidate image contains installed Core payload but no owner Core",
            "proof init runs on throwaway overlay, not candidate image directly",
            "not yet published as a golden image",
        ],
    }
    result_path = output_dir / f"{run_id}-result.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
