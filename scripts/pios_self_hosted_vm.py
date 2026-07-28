"""Safely operate a data-empty local ARM64 QEMU PIOS Core image.

This is a host-side developer wrapper. It never creates provisioning data,
mounts a host directory, or enables VM networking. A real boot is opt-in.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WORKSPACE_MARKER = ".pios-self-hosted-vm-workspace.json"
RUN_RECORD = "run.json"
HEALTH_SCHEMA = "self_hosted_core_health_check_v1"
HEALTH_STATUS_PATTERN = re.compile(
    rf'"schema_version"\s*:\s*"{HEALTH_SCHEMA}".{{0,4096}}?"status"\s*:\s*"(?P<status>[^"]+)"',
    re.DOTALL,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_firmware(filename: str) -> Path:
    for directory in (
        Path("/opt/homebrew/share/qemu"),
        Path("/usr/local/share/qemu"),
        Path("/usr/share/qemu"),
    ):
        candidate = directory / filename
        if candidate.is_file():
            return candidate
    raise ValueError(f"could not find QEMU firmware {filename}")


def qemu_binary(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise ValueError(f"required executable is not available on PATH: {name}")
    return found


def run_checked(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, capture_output=True, text=True)


def inspect_image(image: Path, qemu_img: str) -> dict[str, Any]:
    if not image.is_file():
        raise ValueError(f"image is missing: {image}")
    result = run_checked([qemu_img, "info", "--output=json", str(image)])
    info = json.loads(result.stdout)
    if info.get("format") != "qcow2":
        raise ValueError(f"image must be qcow2, found: {info.get('format')}")
    for field in ("backing-filename", "full-backing-filename", "backing-filename-format"):
        if info.get(field):
            raise ValueError(f"base image must have no backing file ({field} is present)")
    return info


def workspace_marker(workspace: Path) -> Path:
    return workspace / WORKSPACE_MARKER


def ensure_workspace(workspace: Path) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    marker = workspace_marker(workspace)
    if marker.exists():
        try:
            existing = json.loads(marker.read_text())
        except json.JSONDecodeError as exc:
            raise ValueError(f"workspace marker is invalid: {marker}") from exc
        if existing.get("schema_version") != "pios_self_hosted_vm_workspace_v1":
            raise ValueError(f"workspace marker is unrecognized: {marker}")
        return
    if any(workspace.iterdir()):
        raise ValueError(f"refusing non-empty directory without wrapper marker: {workspace}")
    marker.write_text(json.dumps({
        "schema_version": "pios_self_hosted_vm_workspace_v1",
        "created_at": utc_now(),
        "purpose": "local data-empty QEMU wrapper state only",
    }, indent=2, sort_keys=True) + "\n")


def read_record(workspace: Path, run_id: str) -> tuple[Path, dict[str, Any]]:
    path = workspace / "runs" / run_id / RUN_RECORD
    if not path.is_file():
        raise ValueError(f"run record is missing: {path}")
    try:
        record = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"run record is invalid: {path}") from exc
    if record.get("schema_version") != "pios_self_hosted_vm_run_v1":
        raise ValueError(f"run record is unrecognized: {path}")
    return path, record


def write_record(path: Path, record: dict[str, Any]) -> None:
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")


def process_is_qemu(pid: int, expected_binary: str) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return False
    result = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True)
    return result.returncode == 0 and Path(expected_binary).name in result.stdout


def health_from_log(log_path: Path) -> dict[str, Any]:
    if not log_path.is_file():
        return {"status": "not_available", "reason": "serial log is not available"}
    content = log_path.read_text(errors="replace")
    statuses = [match.group("status") for match in HEALTH_STATUS_PATTERN.finditer(content)]
    return {
        "status": "passed" if "passed" in statuses else "pending_or_failed",
        "health_schema_seen": HEALTH_SCHEMA in content,
        "health_record_statuses": statuses,
        "passed_status_seen": "passed" in statuses,
    }


def status(workspace: Path, run_id: str) -> dict[str, Any]:
    _, record = read_record(workspace, run_id)
    pid = record.get("pid")
    running = isinstance(pid, int) and process_is_qemu(pid, record["qemu_binary"])
    return {
        "schema_version": "pios_self_hosted_vm_status_v1",
        "checked_at": utc_now(),
        "run_id": run_id,
        "run_state": "running" if running else "stopped_or_exited",
        "pid": pid,
        "health": health_from_log(Path(record["serial_log"])),
        "record": str(workspace / "runs" / run_id / RUN_RECORD),
        "serial_log": record["serial_log"],
        "boundaries": record["boundaries"],
    }


def command_disables_network(command: list[str]) -> bool:
    return any(command[index:index + 2] == ["-nic", "none"] for index in range(len(command) - 1))


def diagnostics(workspace: Path, run_id: str) -> dict[str, Any]:
    _, record = read_record(workspace, run_id)
    serial_log = Path(record["serial_log"])
    content = serial_log.read_text(errors="replace") if serial_log.is_file() else ""
    metadata_attempt = (
        "pios_google_metadata_init_result_v1" in content
        and ("metadata_unavailable" in content or "Network is unreachable" in content)
    )
    warnings = []
    if not command_disables_network(record["command"]):
        warnings.append("QEMU command does not contain -nic none")
    if metadata_attempt:
        warnings.append("guest metadata-init attempted an unreachable metadata lookup")
    return {
        "schema_version": "pios_self_hosted_vm_diagnostics_v1",
        "checked_at": utc_now(),
        "run_id": run_id,
        "networking": {
            "qemu_nic_none": command_disables_network(record["command"]),
            "host_directory_mounts": False,
            "guest_metadata_attempt_detected": metadata_attempt,
        },
        "inputs": {
            "base_image": record["image"],
            "base_image_sha256": record["image_sha256"],
            "seed_iso": record["seed_iso"],
        },
        "artifacts": {
            name: {"path": record[name], "exists": Path(record[name]).is_file()}
            for name in ("overlay", "edk2_vars", "serial_log")
        },
        "health": health_from_log(serial_log),
        "warnings": warnings,
    }


def plan_start(args: argparse.Namespace) -> dict[str, Any]:
    image = args.image.expanduser().resolve()
    seed_iso = args.seed_iso.expanduser().resolve()
    if not seed_iso.is_file():
        raise ValueError(f"seed ISO is missing: {seed_iso}")
    qemu = qemu_binary(args.qemu_system)
    qemu_img = qemu_binary(args.qemu_img)
    code_fd = find_firmware("edk2-aarch64-code.fd")
    vars_template = find_firmware("edk2-arm-vars.fd")
    image_info = inspect_image(image, qemu_img)
    if args.expected_image_sha256 and sha256_file(image) != args.expected_image_sha256.lower():
        raise ValueError("base image SHA-256 does not match --expected-image-sha256")
    workspace = args.workspace.expanduser().resolve()
    run_id = args.run_id or datetime.now(timezone.utc).strftime("vm-%Y%m%dT%H%M%SZ")
    run_dir = workspace / "runs" / run_id
    if run_dir.exists():
        raise ValueError(f"run id already exists: {run_dir}")
    command = [
        qemu, "-machine", "virt,accel=hvf,highmem=off", "-cpu", "host",
        "-m", str(args.memory_mib), "-smp", str(args.cpus),
        "-drive", f"if=pflash,format=raw,readonly=on,file={code_fd}",
        "-drive", f"if=pflash,format=raw,file={run_dir / 'edk2-arm-vars.fd'}",
        "-drive", f"if=virtio,format=qcow2,file={run_dir / 'overlay.qcow2'}",
        "-drive", f"if=virtio,format=raw,readonly=on,file={seed_iso}",
        "-nic", "none", "-nographic",
    ]
    return {
        "schema_version": "pios_self_hosted_vm_start_plan_v1",
        "status": "ready_to_boot" if args.confirm_boot else "dry_run",
        "run_id": run_id,
        "workspace": str(workspace),
        "run_dir": str(run_dir),
        "image": str(image),
        "image_sha256": sha256_file(image),
        "image_info": image_info,
        "seed_iso": str(seed_iso),
        "qemu_binary": qemu,
        "qemu_img_binary": qemu_img,
        "firmware": {"code": str(code_fd), "vars_template": str(vars_template)},
        "command": command,
        "boundaries": [
            "data-empty image required", "no owner data or Core Bundle hydration",
            "no host directory mounts", "VM networking disabled with -nic none",
            "no Core API, connector, or scheduler is enabled by this wrapper",
        ],
    }


def start(args: argparse.Namespace) -> dict[str, Any]:
    plan = plan_start(args)
    if not args.confirm_boot:
        return plan
    workspace = Path(plan["workspace"])
    run_dir = Path(plan["run_dir"])
    ensure_workspace(workspace)
    run_dir.mkdir(parents=True)
    shutil.copy2(plan["firmware"]["vars_template"], run_dir / "edk2-arm-vars.fd")
    run_checked([plan["qemu_img_binary"], "create", "-f", "qcow2", "-F", "qcow2", "-b", plan["image"], str(run_dir / "overlay.qcow2")])
    serial_log = run_dir / "serial.log"
    with serial_log.open("w") as log_handle:
        process = subprocess.Popen(plan["command"], stdout=log_handle, stderr=subprocess.STDOUT, start_new_session=True)
    record = {
        "schema_version": "pios_self_hosted_vm_run_v1", "started_at": utc_now(),
        "run_id": plan["run_id"], "pid": process.pid, "qemu_binary": plan["qemu_binary"],
        "image": plan["image"], "image_sha256": plan["image_sha256"], "seed_iso": plan["seed_iso"],
        "overlay": str(run_dir / "overlay.qcow2"), "edk2_vars": str(run_dir / "edk2-arm-vars.fd"),
        "serial_log": str(serial_log), "command": plan["command"], "boundaries": plan["boundaries"],
    }
    write_record(run_dir / RUN_RECORD, record)
    return {**plan, "status": "boot_started", "pid": process.pid, "record": str(run_dir / RUN_RECORD), "serial_log": str(serial_log)}


def stop(workspace: Path, run_id: str, timeout_seconds: int) -> dict[str, Any]:
    path, record = read_record(workspace, run_id)
    pid = record.get("pid")
    if not isinstance(pid, int) or not process_is_qemu(pid, record["qemu_binary"]):
        state = "already_stopped_or_exited"
    else:
        os.killpg(pid, signal.SIGTERM)
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline and process_is_qemu(pid, record["qemu_binary"]):
            time.sleep(0.2)
        state = "stopped" if not process_is_qemu(pid, record["qemu_binary"]) else "stop_timeout"
    record["stopped_at"] = utc_now()
    record["stop_state"] = state
    write_record(path, record)
    evidence = {"schema_version": "pios_self_hosted_vm_stop_evidence_v1", "recorded_at": utc_now(), "run_id": run_id, "status": state, "health": health_from_log(Path(record["serial_log"]))}
    evidence_path = path.parent / "stop-evidence.json"
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    return {**evidence, "evidence": str(evidence_path)}


def delete_workspace(workspace: Path, confirmation: bool, action: str) -> dict[str, Any]:
    if not confirmation:
        raise ValueError(f"{action} requires its explicit confirmation flag")
    marker = workspace_marker(workspace)
    if not marker.is_file():
        raise ValueError(f"refusing to delete workspace without wrapper marker: {workspace}")
    try:
        marker_data = json.loads(marker.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"workspace marker is invalid: {marker}") from exc
    if marker_data.get("schema_version") != "pios_self_hosted_vm_workspace_v1":
        raise ValueError(f"refusing to delete workspace with unrecognized marker: {workspace}")
    shutil.rmtree(workspace)
    return {"schema_version": "pios_self_hosted_vm_cleanup_v1", "status": "removed", "action": action, "workspace": str(workspace), "recorded_at": utc_now()}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Operate a data-empty local ARM64 QEMU PIOS Core image safely.")
    parser.add_argument("operation", nargs="?", choices=("start", "status", "diagnostics", "stop", "cleanup", "reset"), default="start")
    parser.add_argument("--workspace", type=Path, default=Path(".pios-self-hosted-vm"))
    parser.add_argument("--run-id")
    parser.add_argument("--image", type=Path)
    parser.add_argument("--seed-iso", type=Path)
    parser.add_argument("--expected-image-sha256")
    parser.add_argument("--confirm-boot", action="store_true")
    parser.add_argument("--confirm-cleanup", action="store_true")
    parser.add_argument("--confirm-reset", action="store_true")
    parser.add_argument("--qemu-system", default="qemu-system-aarch64")
    parser.add_argument("--qemu-img", default="qemu-img")
    parser.add_argument("--memory-mib", type=int, default=2048)
    parser.add_argument("--cpus", type=int, default=2)
    parser.add_argument("--stop-timeout-seconds", type=int, default=20)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        workspace = args.workspace.expanduser().resolve()
        if args.operation == "start":
            if not args.image or not args.seed_iso:
                raise ValueError("start requires --image and --seed-iso; without --confirm-boot it is a non-mutating dry-run")
            result = start(args)
        elif args.operation == "status":
            if not args.run_id:
                raise ValueError("status requires --run-id")
            result = status(workspace, args.run_id)
        elif args.operation == "diagnostics":
            if not args.run_id:
                raise ValueError("diagnostics requires --run-id")
            result = diagnostics(workspace, args.run_id)
        elif args.operation == "stop":
            if not args.run_id:
                raise ValueError("stop requires --run-id")
            result = stop(workspace, args.run_id, args.stop_timeout_seconds)
        else:
            result = delete_workspace(workspace, args.confirm_cleanup if args.operation == "cleanup" else args.confirm_reset, args.operation)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("status") not in {"stop_timeout"} else 1
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, indent=2, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
