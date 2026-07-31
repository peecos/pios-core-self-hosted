"""Prove B1-B5 PIOS Starter capabilities on a fresh disposable local VM overlay."""
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
from scripts.prove_pios_starter_disk_image_hygiene import (
    load_json,
    resolve_repo_path,
    validate_release_image,
)

CAPABILITY_PROOF_START = "PIOS_STARTER_CAPABILITY_PROOF_START"
CAPABILITY_EMPTY_STATE_OK = "PIOS_STARTER_CAPABILITY_EMPTY_STATE_OK"
CAPABILITY_LIFECYCLE_PASSED = "PIOS_STARTER_CAPABILITY_LIFECYCLE_PASSED"
CAPABILITY_PROOF_DONE = "PIOS_STARTER_CAPABILITY_PROOF_DONE"
DEFAULT_OUTPUT_DIR = Path("image-artifacts/pios-starter-capability-lifecycle")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def utc_now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ").lower()


def capability_fixture_script() -> str:
    """Return the generated-only B1-B5 exercise run inside the disposable guest."""
    return """from datetime import datetime, timezone
import json
from pathlib import Path

from scripts import pios_projection_approval_primitives as approvals
from scripts import pios_source_adapter_templates as adapters
from scripts import pios_owner_control_boundary as owner_control

root = Path('/tmp/pios-starter-capability-fixture')
adapter_harness = adapters.LocalSyntheticAdapterHarness(root / 'source')
prepared = adapters.OriginalByteCaptureTemplate().prepare_generated(
    source_native_record_id='generated-capability-item-1',
    extensions={'future_extension': {'preserved': True}},
)
outbox = adapter_harness.enqueue(prepared)
stable_id = outbox['candidate']['evidence']['stable_source_record_id']
accepted = adapter_harness.submit_enqueued(stable_id)
if accepted['status'] != 'accepted':
    raise RuntimeError('generated source candidate was not accepted')
if adapter_harness.lifecycle.readback_original(accepted['receipt']) != prepared.original_bytes:
    raise RuntimeError('generated source original readback mismatch')
exported = adapter_harness.lifecycle.export()
if exported['status'] != 'passed' or len(exported['receipts']) != 1:
    raise RuntimeError('generated source export did not retain one receipt')

projection = approvals.build_projection_record(
    source_receipt=accepted['receipt'],
    projection_fields={'label': 'harmless generated projection'},
    extensions={'future_projection_extension': {'preserved': True}},
)
approvals.validate_projection_record(projection)
now = datetime(2026, 7, 31, 16, 0, 0, tzinfo=timezone.utc)
challenge = approvals.begin_sensitive_action(
    owner_id='owner_synthetic_b6',
    action_type='export_projection',
    parameters={'fixture': 'generated_harmless'},
    session_binding='binding_synthetic_session',
    csrf_binding='binding_synthetic_csrf',
    issued_at=now,
)
proof = approvals.build_synthetic_approval_proof(challenge=challenge, approved_at=now)
approval = approvals.LocalSyntheticApprovalHarness(
    approvals.LocalImmutableAuditStore(root / 'audit')
).approve(challenge=challenge, proof=proof, now=now)
if approval['status'] != 'approved':
    raise RuntimeError('generated local approval did not pass')

health = owner_control.boundary_health()
if health['capability_state'] != owner_control.DISABLED_STATUS:
    raise RuntimeError('owner-control boundary was not safe-disabled')
rejected_owner_bind = False
invalid = owner_control.neutral_configuration()
invalid['service']['enabled'] = True
try:
    owner_control.validate_neutral_configuration(invalid)
except owner_control.OwnerControlConfigurationError:
    rejected_owner_bind = True
if not rejected_owner_bind:
    raise RuntimeError('owner-control boundary accepted an enabled service')

print(json.dumps({
    'schema_version': 'pios_starter_capability_lifecycle_fixture_v1',
    'status': 'passed',
    'source_receipt_id': accepted['receipt']['receipt_id'],
    'export_cursor': exported['cursor'],
    'projection_ref': projection['projection_ref'],
    'approval_ref': approval['approval_ref'],
    'audit_ref': approval['audit_ref'],
    'owner_control_state': health['capability_state'],
    'owner_bind_rejection_confirmed': rejected_owner_bind,
}, sort_keys=True))
"""


def build_capability_user_data(*, owner_id: str, owner_slug: str, env_name: str) -> str:
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
        "  - path: /tmp/pios-starter-capability-fixture.py\n"
        "    permissions: '0600'\n"
        "    content: |\n"
        f"{indent_block(capability_fixture_script(), 6)}"
        "runcmd:\n"
        "  - [bash, -lc, \"set -euo pipefail; trap 'sync; shutdown -h now' EXIT; "
        f"echo {CAPABILITY_PROOF_START} | tee /dev/console; "
        "test -x /opt/pios-core/bin/pios-core-init; "
        "test ! -e /var/lib/pios-core || test -z \\\"$(find /var/lib/pios-core -mindepth 1 -print -quit)\\\"; "
        f"echo {CAPABILITY_EMPTY_STATE_OK} | tee /dev/console; "
        "/opt/pios-core/bin/pios-core-init --manifest /tmp/pios-self-hosted-manifest.json | tee /tmp/pios-core-init-result.json /dev/console; "
        f"cat {health_path} | tee /tmp/pios-core-health-check.json /dev/console; "
        "PYTHONPATH=/opt/pios-core python3 /tmp/pios-starter-capability-fixture.py | tee /tmp/pios-starter-capability-result.json /dev/console; "
        f"echo {CAPABILITY_LIFECYCLE_PASSED} | tee /dev/console; "
        f"echo {CAPABILITY_PROOF_DONE} | tee /dev/console\"]\n"
    )


def run_capability_proof(
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
        user_data=build_capability_user_data(
            owner_id=owner_id, owner_slug=owner_slug, env_name=env_name
        ),
        meta_data=f"instance-id: pios-starter-capability-{run_id}\nlocal-hostname: {owner_slug}\n",
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
        stop_when_seen=CAPABILITY_PROOF_DONE,
    )
    serial_log_path.write_text(serial_log)
    markers = {
        "proof_start_seen": CAPABILITY_PROOF_START in serial_log,
        "empty_core_state_seen": CAPABILITY_EMPTY_STATE_OK in serial_log,
        "lifecycle_passed_seen": CAPABILITY_LIFECYCLE_PASSED in serial_log,
        "proof_done_seen": CAPABILITY_PROOF_DONE in serial_log,
        "core_health_passed_seen": '"schema_version": "self_hosted_core_health_check_v1"' in serial_log
        and '"status": "passed"' in serial_log,
        "source_lifecycle_fixture_seen": '"schema_version": "pios_starter_capability_lifecycle_fixture_v1"' in serial_log
        and '"owner_control_state": "disabled_unconfigured"' in serial_log
        and '"owner_bind_rejection_confirmed": true' in serial_log,
    }
    return {
        "status": "passed" if all(markers.values()) else "failed",
        "overlay": str(overlay),
        "seed_iso": str(seed_iso),
        "serial_log": str(serial_log_path),
        "networking": "QEMU user networking with restrict=on; no outbound guest access configured",
        "synthetic_owner": {
            "owner_id": owner_id,
            "owner_slug": owner_slug,
            "env_name": env_name,
        },
        "markers": markers,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Boot a fresh disposable PIOS Starter overlay and prove B1-B5 generic "
            "capabilities with generated local-only data."
        )
    )
    parser.add_argument("--release-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--owner-id", default=None)
    parser.add_argument("--owner-slug", default=None)
    parser.add_argument("--env-name", default="starter-capability-proof")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_id = args.run_id or f"pios-starter-capability-{utc_now_compact()}"
    owner_slug = args.owner_slug or f"{run_id}-owner"
    owner_id = args.owner_id or f"owner_synthetic_{owner_slug.replace('-', '_')}"
    manifest_path = resolve_repo_path(args.release_manifest)
    output_dir = resolve_repo_path(args.output_dir)
    manifest = load_json(manifest_path)
    release = validate_release_image(manifest, manifest_path)
    proof = run_capability_proof(
        release_image=Path(release["image"]),
        output_dir=output_dir,
        run_id=run_id,
        owner_id=owner_id,
        owner_slug=owner_slug,
        env_name=args.env_name,
        timeout_seconds=args.timeout_seconds,
    )
    result = {
        "schema_version": "self_hosted_pios_starter_capability_lifecycle_proof_v1",
        "created_at": utc_now(),
        "status": proof["status"],
        "run_id": run_id,
        "release_manifest": str(manifest_path),
        "release_image": release,
        "proof": proof,
        "boundaries": [
            "disposable local QCOW2 overlay only",
            "separate synthetic owner only",
            "generated local source/approval fixtures only",
            "no owner Bind values, credentials, or personal data",
            "no Core Bundle hydration, connector sync, scheduler, Core API, or application networking",
        ],
    }
    result_path = output_dir / f"{run_id}-result.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if proof["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
