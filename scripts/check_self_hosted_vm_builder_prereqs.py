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

REQUIRED_TO_PACKAGE = ("python3", "tar", "zstd")
VM_BUILDERS = ("packer", "qemu-system-x86_64", "qemu-system-aarch64", "tart")


def tool_status(name: str) -> dict[str, Any]:
    path = shutil.which(name)
    return {
        "name": name,
        "available": path is not None,
        "path": path,
    }


def check_prereqs(*, require_vm_builder: bool) -> dict[str, Any]:
    packaging = [tool_status(name) for name in REQUIRED_TO_PACKAGE]
    builders = [tool_status(name) for name in VM_BUILDERS]
    packaging_ready = all(item["available"] for item in packaging)
    vm_builder_ready = any(item["available"] for item in builders)
    status = "ready" if packaging_ready and (vm_builder_ready or not require_vm_builder) else "blocked"
    return {
        "status": status,
        "packaging_ready": packaging_ready,
        "vm_builder_ready": vm_builder_ready,
        "require_vm_builder": require_vm_builder,
        "packaging_tools": packaging,
        "vm_builders": builders,
        "next_action": (
            "build and boot a VM image"
            if vm_builder_ready
            else "install Packer, QEMU, Tart, or run the scaffold on a VM-capable machine"
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check local prerequisites for self-hosted image packaging and VM building."
    )
    parser.add_argument("--require-vm-builder", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = check_prereqs(require_vm_builder=args.require_vm_builder)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
