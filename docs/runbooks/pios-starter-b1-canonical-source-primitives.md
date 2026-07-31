# PIOS Starter B1: Generic Canonical Source-Primitives Library

## Scope

`scripts/pios_canonical_source_primitives.py` is the B1 reusable, local-only
library for future synthetic source adapters. It contains no adapter,
transport, credentials, owner identity, application integration, service
activation, endpoint, or provider-specific storage code.

It is included in future data-empty image roots through the existing explicit
image-root allowlist. The current r3 image artifact is unchanged; a later B6
capability-bearing image build must re-run the existing image hygiene and
residue proofs.

## Generic API

- `canonical_json_bytes(value)`: strict deterministic UTF-8 JSON. Object keys
  are strings, keys are sorted, separators are fixed, non-finite/float values
  are rejected, and decimal-like values must be represented as strings.
- `derive_stable_source_record_id(integration_id, source_native_record_id)`:
  produces an opaque `src_...` identity from the generic integration/native
  pair.
- `derive_idempotency_key(stable_source_record_id, payload_integrity)`:
  produces a deterministic `idem_...` key bound to the canonical payload
  digest and byte count.
- `integrity_for_bytes`, `validate_integrity`, and `verify_bytes`: strict
  lowercase SHA-256 plus byte-count binding.
- `build_core_ref` and `validate_core_ref`: construct and validate canonical
  `core://events/...`, `core://originals/...`, and other defined Core logical
  collections only. Provider references are rejected from logical fields.
- `validate_source_provenance`: preserves opaque provider/storage metadata but
  rejects embedded `core://` logical references; those belong only in
  `logical_references`.
- `preserve_extensions`: canonical JSON round-trip preservation for unknown
  extension objects.
- `LocalSyntheticEvidenceStore`: atomic create-only retention of harmless
  synthetic original bytes and canonical evidence. Repeating identical bytes
  is a duplicate; changing content under the same stable source identity is an
  immutable conflict.

## B1 Boundaries

- Tests use generated harmless strings in temporary directories only.
- No Corebox, Ally, History, Dash, LifeStory, personal identity, endpoint,
  credential, app binary, cloud resource, network transport, or service is
  involved.
- `core://` is logical identity only. The temporary local store is an
  implementation detail for synthetic tests, not canonical provenance.
- B1 does not implement B2 receipts, retry/refusal/revocation lifecycle, or a
  source adapter. Those are separately reviewed work.

## B2 Implication

B2 receipts can use the B1 stable identity, idempotency key, byte-integrity,
extension, immutable-evidence, and `core://` primitives without selecting an
owner, device, app, or storage provider. Receipt/lifecycle semantics remain
out of scope until the B1 checkpoint is reviewed.
