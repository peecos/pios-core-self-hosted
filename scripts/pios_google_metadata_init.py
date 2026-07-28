"""Initialize provider metadata only when the guest identifies as Google Compute.

Local QEMU images may include this adapter for provider portability, but they
must never probe a metadata endpoint merely because the service is installed.
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path
from typing import Callable


DEFAULT_DMI_ROOT = Path("/sys/class/dmi/id")
METADATA_URL = "http://metadata.google.internal/computeMetadata/v1/instance/id"


def read_dmi_value(dmi_root: Path, name: str) -> str:
    path = dmi_root / name
    try:
        return path.read_text(errors="replace").strip()
    except OSError:
        return ""


def is_google_compute_environment(dmi_root: Path = DEFAULT_DMI_ROOT) -> bool:
    vendor = read_dmi_value(dmi_root, "sys_vendor").casefold()
    product = read_dmi_value(dmi_root, "product_name").casefold()
    return "google" in vendor and "compute engine" in product


def fetch_instance_id(retry_seconds: int) -> None:
    request = urllib.request.Request(METADATA_URL, headers={"Metadata-Flavor": "Google"})
    deadline = time.monotonic() + retry_seconds
    while True:
        try:
            with urllib.request.urlopen(request, timeout=2) as response:
                if response.headers.get("Metadata-Flavor") != "Google":
                    raise ValueError("metadata response did not include Metadata-Flavor: Google")
                response.read(128)
                return
        except Exception:
            if time.monotonic() >= deadline:
                raise
            time.sleep(1)


def metadata_init_result(
    *,
    dmi_root: Path = DEFAULT_DMI_ROOT,
    retry_seconds: int = 10,
    fetcher: Callable[[int], None] = fetch_instance_id,
) -> dict[str, object]:
    if not is_google_compute_environment(dmi_root):
        return {
            "schema_version": "pios_google_metadata_init_result_v1",
            "status": "skipped_not_google_compute",
            "network_attempted": False,
        }
    try:
        fetcher(retry_seconds)
    except Exception as exc:
        return {
            "schema_version": "pios_google_metadata_init_result_v1",
            "status": "metadata_unavailable",
            "network_attempted": True,
            "error": str(exc),
        }
    return {
        "schema_version": "pios_google_metadata_init_result_v1",
        "status": "metadata_reachable",
        "network_attempted": True,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Google metadata initialization only on Google Compute Engine.")
    parser.add_argument("--optional", action="store_true")
    parser.add_argument("--retry-seconds", type=int, default=10)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.retry_seconds < 0:
        raise ValueError("--retry-seconds must be non-negative")
    result = metadata_init_result(retry_seconds=args.retry_seconds)
    print(json.dumps(result, sort_keys=True))
    if result["status"] in {"metadata_reachable", "skipped_not_google_compute"}:
        return 0
    return 0 if args.optional else 1


if __name__ == "__main__":
    raise SystemExit(main())
