"""Owner-neutral, zero-network adapter templates for generated source fixtures.

The templates model two generic source shapes only: original-byte capture and
structured evidence.  They deliberately create harmless generated fixtures;
they do not connect to a provider, read a local folder, configure a service,
or accept owner content.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from scripts import pios_canonical_source_primitives as primitives
from scripts import pios_generic_source_lifecycle as lifecycle

OUTBOX_SCHEMA = "pios_generic_source_adapter_outbox_v1"
LEDGER_SCHEMA = "pios_generic_source_adapter_receipt_ledger_v1"
SYNTHETIC_OWNER_ID = "owner_synthetic_b3"
TEMPLATE_NAMES = frozenset({"original_byte_capture", "structured_evidence"})


class AdapterTemplateError(ValueError):
    """Raised when an adapter template or its local harness is invalid."""


@dataclass(frozen=True)
class PreparedSyntheticCandidate:
    """A locally generated candidate awaiting local lifecycle submission."""

    template_name: str
    candidate: dict[str, Any]
    original_bytes: bytes


class GenericSourceAdapter(Protocol):
    """The local-only interface implemented by reusable source-shape templates."""

    template_name: str

    def prepare_generated(
        self,
        *,
        source_native_record_id: str,
        extensions: Mapping[str, Any] | None = None,
    ) -> PreparedSyntheticCandidate:
        """Create and locally validate one harmless generated candidate."""


def _extensions(extensions: Mapping[str, Any] | None) -> dict[str, Any]:
    return primitives.preserve_extensions({} if extensions is None else extensions)


def _prepare(
    *,
    template_name: str,
    integration_id: str,
    source_native_record_id: str,
    payload: Mapping[str, Any],
    original_bytes: bytes,
    processing_manifest: Mapping[str, Any],
    extensions: Mapping[str, Any] | None,
) -> PreparedSyntheticCandidate:
    if template_name not in TEMPLATE_NAMES:
        raise AdapterTemplateError("template_name must be a supported generic source shape")
    candidate = lifecycle.build_source_candidate(
        owner_id=SYNTHETIC_OWNER_ID,
        integration_id=integration_id,
        source_native_record_id=source_native_record_id,
        payload=payload,
        original_bytes=original_bytes,
        processing_manifest=processing_manifest,
        source_provenance={
            "fixture_class": "generated_harmless",
            "source_shape": template_name,
            "transport": "local_only",
        },
        extensions=_extensions(extensions),
    )
    lifecycle.validate_source_candidate(candidate, original_bytes)
    return PreparedSyntheticCandidate(template_name, candidate, original_bytes)


class OriginalByteCaptureTemplate:
    """Template for a generic item represented first by original bytes."""

    template_name = "original_byte_capture"

    def prepare_generated(
        self,
        *,
        source_native_record_id: str,
        extensions: Mapping[str, Any] | None = None,
    ) -> PreparedSyntheticCandidate:
        original_bytes = (
            b"PIOS Starter harmless generated original-byte capture fixture.\n"
        )
        return _prepare(
            template_name=self.template_name,
            integration_id="original-byte-capture",
            source_native_record_id=source_native_record_id,
            payload={
                "fixture": "generated_harmless",
                "source_shape": self.template_name,
                "version": 1,
            },
            original_bytes=original_bytes,
            processing_manifest={
                "adapter_template": self.template_name,
                "fixture": "generated_harmless",
                "input_representation": "original_bytes",
                "version": 1,
            },
            extensions=extensions,
        )


class StructuredEvidenceTemplate:
    """Template for a generic structured-evidence source record."""

    template_name = "structured_evidence"

    def prepare_generated(
        self,
        *,
        source_native_record_id: str,
        extensions: Mapping[str, Any] | None = None,
    ) -> PreparedSyntheticCandidate:
        original_value = {
            "fixture": "generated_harmless",
            "record_kind": "structured_evidence",
            "version": 1,
        }
        original_bytes = primitives.canonical_json_bytes(original_value)
        return _prepare(
            template_name=self.template_name,
            integration_id="structured-evidence",
            source_native_record_id=source_native_record_id,
            payload={
                "fixture": "generated_harmless",
                "record_fields": sorted(original_value),
                "source_shape": self.template_name,
            },
            original_bytes=original_bytes,
            processing_manifest={
                "adapter_template": self.template_name,
                "fixture": "generated_harmless",
                "input_representation": "canonical_json_bytes",
                "version": 1,
            },
            extensions=extensions,
        )


def _write_immutable(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if path.read_bytes() != content:
            raise AdapterTemplateError(f"immutable local content differs: {path.name}")
        return
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content)


class LocalSyntheticAdapterHarness:
    """A local outbox and receipt-ledger façade over the B2 lifecycle contract."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.lifecycle = lifecycle.LocalSyntheticSourceLifecycle(root / "lifecycle")

    def _outbox_path(self, stable_source_record_id: str) -> Path:
        if not primitives.STABLE_SOURCE_ID_RE.fullmatch(stable_source_record_id):
            raise AdapterTemplateError("stable_source_record_id must be a canonical src_ identifier")
        return self.root / "outbox" / f"{stable_source_record_id}.json"

    def _outbox_original_path(self, digest: str) -> Path:
        integrity = primitives.validate_integrity({"sha256": digest, "byte_count": 0})
        return self.root / "outbox-originals" / f"{integrity['sha256']}.bin"

    def _ledger_path(self, receipt_id: str) -> Path:
        if not isinstance(receipt_id, str) or not receipt_id.startswith("rcpt_") or not primitives.SHA256_RE.fullmatch(receipt_id[5:]):
            raise AdapterTemplateError("receipt_id must be a canonical receipt identifier")
        return self.root / "receipt-ledger" / f"{receipt_id}.json"

    @staticmethod
    def _validate_template_binding(record: Mapping[str, Any], candidate: Mapping[str, Any]) -> str:
        template_name = record.get("template_name")
        if template_name not in TEMPLATE_NAMES:
            raise AdapterTemplateError("outbox template_name is not a supported generic source shape")
        evidence = candidate["evidence"]
        manifest = candidate["processing_manifest"]
        if (
            evidence["payload"].get("source_shape") != template_name
            or evidence["source_provenance"].get("source_shape") != template_name
            or manifest.get("adapter_template") != template_name
        ):
            raise AdapterTemplateError("outbox template name is not bound to its candidate")
        return template_name

    def enqueue(self, prepared: PreparedSyntheticCandidate) -> dict[str, Any]:
        """Persist a prepared generated fixture in an immutable local outbox."""
        if not isinstance(prepared, PreparedSyntheticCandidate):
            raise AdapterTemplateError("prepared candidate must be produced by a template")
        candidate = lifecycle.validate_source_candidate(prepared.candidate, prepared.original_bytes)
        evidence = candidate["evidence"]
        original_integrity = primitives.verify_bytes(
            prepared.original_bytes, evidence["original_integrity"]
        )
        stable_id = evidence["stable_source_record_id"]
        record = {
            "schema_version": OUTBOX_SCHEMA,
            "template_name": prepared.template_name,
            "candidate": candidate,
            "original_integrity": original_integrity,
        }
        self._validate_template_binding(record, candidate)
        _write_immutable(
            self._outbox_path(stable_id), primitives.canonical_json_bytes(record)
        )
        _write_immutable(
            self._outbox_original_path(original_integrity["sha256"]), prepared.original_bytes
        )
        return record

    def read_outbox(self, stable_source_record_id: str) -> dict[str, Any]:
        path = self._outbox_path(stable_source_record_id)
        if not path.is_file():
            raise AdapterTemplateError("local outbox record does not exist")
        try:
            record = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise AdapterTemplateError("local outbox record is not valid JSON") from exc
        if record.get("schema_version") != OUTBOX_SCHEMA:
            raise AdapterTemplateError(f"outbox.schema_version must be {OUTBOX_SCHEMA}")
        candidate = record.get("candidate")
        integrity = primitives.validate_integrity(record.get("original_integrity"))
        original = self._outbox_original_path(integrity["sha256"]).read_bytes()
        primitives.verify_bytes(original, integrity)
        normalized = lifecycle.validate_source_candidate(candidate, original)
        if normalized["evidence"]["stable_source_record_id"] != stable_source_record_id:
            raise AdapterTemplateError("outbox path and candidate stable identity do not match")
        template_name = self._validate_template_binding(record, normalized)
        return {
            "schema_version": OUTBOX_SCHEMA,
            "template_name": template_name,
            "candidate": normalized,
            "original_integrity": integrity,
        }

    def submit_enqueued(
        self, stable_source_record_id: str, *, test_outcome: str = "accept"
    ) -> dict[str, Any]:
        """Submit one local outbox record using only B2 synthetic outcomes."""
        record = self.read_outbox(stable_source_record_id)
        integrity = record["original_integrity"]
        original = self._outbox_original_path(integrity["sha256"]).read_bytes()
        result = self.lifecycle.submit(
            record["candidate"], original, test_outcome=test_outcome
        )
        if result["status"] not in {"accepted", "duplicate"}:
            return result
        receipt = lifecycle.verify_receipt(record["candidate"], original, result["receipt"])
        ledger_record = {
            "schema_version": LEDGER_SCHEMA,
            "template_name": record["template_name"],
            "candidate_integrity": record["candidate"]["candidate_integrity"],
            "receipt": receipt,
        }
        _write_immutable(
            self._ledger_path(receipt["receipt_id"]),
            primitives.canonical_json_bytes(ledger_record),
        )
        return {"status": result["status"], "receipt": receipt}

    def read_receipt_ledger(self, receipt_id: str) -> dict[str, Any]:
        path = self._ledger_path(receipt_id)
        if not path.is_file():
            raise AdapterTemplateError("local receipt-ledger record does not exist")
        try:
            record = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise AdapterTemplateError("local receipt-ledger record is not valid JSON") from exc
        if record.get("schema_version") != LEDGER_SCHEMA:
            raise AdapterTemplateError(f"ledger.schema_version must be {LEDGER_SCHEMA}")
        return primitives.canonical_json_value(record)
