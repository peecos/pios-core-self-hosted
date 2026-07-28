"""Local-only synthetic connected-source fixture loop for VM-2.

No network, API server, application, or owner data is involved. The script
creates a disposable synthetic Core only after explicit confirmation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.pios_core_init import init_self_hosted_core


INTEGRATION_ID = "synthetic_local_source"
ENVELOPE_SCHEMA = "pios_local_synthetic_source_envelope_v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def write_new_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(payload)


class LocalSyntheticSourceAdapter:
    def __init__(self, *, core_root: Path, state_dir: Path, owner_id: str) -> None:
        self.core_root = core_root
        self.state_dir = state_dir
        self.owner_id = owner_id
        self.state_path = state_dir / "adapter-state.json"

    def load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"accepted": {}, "transient_attempted": [], "revoked": False}
        return json.loads(self.state_path.read_text())

    def save_state(self, state: dict[str, Any]) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")

    def deny(self, code: str, *, retryable: bool = False) -> dict[str, Any]:
        return {"status": "denied", "code": code, "retryable": retryable}

    def commit(self, envelope: dict[str, Any], *, allow_test_controls: bool = False) -> dict[str, Any]:
        state = self.load_state()
        if state["revoked"]:
            return self.deny("grant_revoked")
        required = ("schema_version", "owner_id", "integration_id", "source_native_record_id", "idempotency_key", "data_class", "evidence_tier", "payload")
        if any(not envelope.get(key) for key in required):
            return self.deny("invalid_envelope")
        if envelope["schema_version"] != ENVELOPE_SCHEMA or envelope["owner_id"] != self.owner_id:
            return self.deny("invalid_envelope")
        if envelope["integration_id"] != INTEGRATION_ID or envelope["data_class"] != "synthetic_normal":
            return self.deny("grant_denied")
        if envelope["evidence_tier"] not in {"raw", "processed", "projection"} or not isinstance(envelope["payload"], dict):
            return self.deny("invalid_envelope")

        idempotency_key = envelope["idempotency_key"]
        content_digest = digest(envelope)
        if allow_test_controls and envelope.get("test_control") == "transient_once" and idempotency_key not in state["transient_attempted"]:
            state["transient_attempted"].append(idempotency_key)
            self.save_state(state)
            return {"status": "retry", "code": "synthetic_transient_failure", "retryable": True}
        existing = state["accepted"].get(idempotency_key)
        if existing:
            if existing["content_digest"] != content_digest:
                return self.deny("idempotency_conflict")
            return {"status": "duplicate", "event_ref": existing["event_ref"], "original_ref": existing["original_ref"]}

        object_id = digest({"owner_id": self.owner_id, "source_native_record_id": envelope["source_native_record_id"], "idempotency_key": idempotency_key})[:32]
        event_id = f"synthetic-{object_id}"
        original_key = f"originals/source={INTEGRATION_ID}/{object_id}.json"
        event_key = f"events/source={INTEGRATION_ID}/{event_id}.json"
        original_ref = f"core://{original_key}"
        event_ref = f"core://{event_key}"
        now = utc_now()
        write_new_json(self.core_root / original_key, {"schema_version": "pios_synthetic_original_v1", "recorded_at": now, "envelope": envelope})
        write_new_json(self.core_root / event_key, {
            "schema_version": "pios_synthetic_source_event_v1", "event_id": event_id,
            "event_type": "source_record_accepted", "recorded_at": now, "owner_id": self.owner_id,
            "integration_id": INTEGRATION_ID, "source_native_record_id": envelope["source_native_record_id"],
            "idempotency_key": idempotency_key, "evidence_tier": envelope["evidence_tier"],
            "original_ref": original_ref, "event_object_key": event_key,
        })
        state["accepted"][idempotency_key] = {"content_digest": content_digest, "event_ref": event_ref, "original_ref": original_ref, "event_id": event_id}
        self.save_state(state)
        return {"status": "accepted", "event_ref": event_ref, "original_ref": original_ref, "event_id": event_id}

    def revoke(self) -> dict[str, Any]:
        state = self.load_state()
        state["revoked"] = True
        self.save_state(state)
        audit_path = self.core_root / "system" / "source-audit" / f"{INTEGRATION_ID}-revocation.json"
        write_new_json(audit_path, {"schema_version": "pios_synthetic_source_revocation_v1", "recorded_at": utc_now(), "integration_id": INTEGRATION_ID, "owner_id": self.owner_id, "status": "revoked"})
        return {"status": "revoked", "audit_ref": f"core://{audit_path.relative_to(self.core_root)}"}

    def export(self, cursor: int = 0) -> dict[str, Any]:
        entries = list(self.load_state()["accepted"].values())
        page = entries[cursor:]
        return {"status": "passed", "cursor": len(entries), "event_refs": [entry["event_ref"] for entry in page], "count": len(page)}


def synthetic_envelope(record_id: str, idempotency_key: str, **extra: Any) -> dict[str, Any]:
    return {"schema_version": ENVELOPE_SCHEMA, "owner_id": "owner_synthetic_vm2", "integration_id": INTEGRATION_ID, "source_native_record_id": record_id, "idempotency_key": idempotency_key, "data_class": "synthetic_normal", "evidence_tier": "raw", "payload": {"kind": "harmless_fixture", "value": record_id}, **extra}


def run_fixture_suite(workspace: Path) -> dict[str, Any]:
    if workspace.exists() and any(workspace.iterdir()):
        raise ValueError(f"synthetic fixture workspace must be empty: {workspace}")
    workspace.mkdir(parents=True, exist_ok=True)
    core_root = workspace / "core"
    key_store = workspace / "keys"
    init_self_hosted_core({"manifest_version": "self_hosted_provisioning_manifest_v1", "core_instance": {"env_name": "synthetic", "owner_id": "owner_synthetic_vm2", "owner_slug": "synthetic-vm2"}, "self_hosted": {"core_root": str(core_root), "key_store_path": str(key_store), "key_provider": "local_dev_file_keys"}, "services": {"start_core_api": False, "start_connectors": False, "start_scheduler": False}, "authorization": {"hydrate_bundle": False, "connector_sync": False, "broad_migration": False, "source_decommission": False}})
    adapter = LocalSyntheticSourceAdapter(core_root=core_root, state_dir=workspace / "adapter-state", owner_id="owner_synthetic_vm2")
    accepted = adapter.commit(synthetic_envelope("accepted-1", "idem-accepted"), allow_test_controls=True)
    duplicate = adapter.commit(synthetic_envelope("accepted-1", "idem-accepted"), allow_test_controls=True)
    denied = adapter.commit(synthetic_envelope("denied-1", "idem-denied", data_class="guarded"), allow_test_controls=True)
    retry_first = adapter.commit(synthetic_envelope("retry-1", "idem-retry", test_control="transient_once"), allow_test_controls=True)
    retry_second = adapter.commit(synthetic_envelope("retry-1", "idem-retry", test_control="transient_once"), allow_test_controls=True)
    revoked = adapter.revoke()
    revoked_attempt = adapter.commit(synthetic_envelope("revoked-1", "idem-revoked"), allow_test_controls=True)
    export = adapter.export()
    result = {"schema_version": "pios_local_synthetic_source_fixture_result_v1", "status": "passed", "created_at": utc_now(), "workspace": str(workspace), "boundaries": ["synthetic data only", "no network", "no Core API", "no app integration", "no owner data"], "fixtures": {"accepted": accepted, "duplicate": duplicate, "denied": denied, "retry_first": retry_first, "retry_second": retry_second, "revoked": revoked, "revoked_attempt": revoked_attempt, "export": export}}
    (workspace / "fixture-result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a local synthetic connected-source fixture loop.")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--confirm-synthetic-write", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    workspace = args.workspace.expanduser().resolve()
    if not args.confirm_synthetic_write:
        print(json.dumps({"status": "dry_run", "workspace": str(workspace), "will_write_synthetic_data": True, "boundaries": ["no network", "no Core API", "no owner data"]}, indent=2, sort_keys=True))
        return 0
    print(json.dumps(run_fixture_suite(workspace), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
