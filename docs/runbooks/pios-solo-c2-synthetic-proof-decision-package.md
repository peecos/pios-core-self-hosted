# PIOS Solo C2: Synthetic-Proof Decision Package And Local Runner Plan

Status: local execution implementation is ready and tested only with disposable
harmless fixtures. The fixed Corebox fixture has **not** been submitted. C2
remains one separately named, local-only, harmless lifecycle proof.

## Purpose

C2 proves one Corebox-shaped synthetic item through the already validated
local Solo lifecycle. It is not a Core API call, VM operation, endpoint,
connector, device enrollment, app synchronization, Owner Bind, or personal
capture.

The future Solo-side runner may use only:

- `scripts/pios_synthetic_source_ingress.py`;
- its `LocalSyntheticSourceIngress`, which uses the B2
  `LocalSyntheticSourceLifecycle`; and
- B1 canonical JSON/integrity helpers already covered by the C1 fixtures.

It must not import an app SDK, access a Corebox folder, invoke Corebox, open a
listener, use credentials, call a network API, read the Core root, mutate a VM,
or write inside a disk image.

## C2 Owner Decision Required Before Execution

The owner must approve all of the following in one named decision after a
zero-write preview has printed the exact input hashes:

| Required decision field | Required value or rule |
| --- | --- |
| Proof ID | One new collision-free ID, for example `c2-corebox-harmless-YYYYMMDD-r1`. |
| Fixture | One newly generated, generated-harmless Corebox transport fixture, not the earlier C1 evidence item, an app folder item, or an owner capture. |
| Fixture source | A named Corebox commit and local fixture-export command/harness that calls `CoreboxSyntheticTransport`; no installed app connection is required. |
| Exact input bindings | Previewed envelope, original, zero-write-preview, and fixture-manifest SHA-256/byte counts, plus a fixed owner-approved receipt time. |
| Solo revision | The committed Solo revision containing the C1 contract to be exercised. |
| Evidence destination | `Storage-wiki/Storage/Other/pios-core/self-hosted-vm/c2-synthetic-proof/<proof-id>/`. The directory must not already exist. |
| Retention | Retain only the verified harmless input, receipts, export/readback evidence, result manifest, and sanitised diagnostics in that evidence directory. |
| Cleanup | Remove all temporary lifecycle roots after evidence is atomically written and verified. |
| Stop authority | Any preflight, binding, result, cleanup, or evidence mismatch stops the proof with no retry, fallback, or configuration change. |

The decision must explicitly say that it does **not** authorize C2 follow-on
work, a personal capture, endpoint, app networking, device enrollment,
credential, Owner Bind, VM/GCP operation, Core hydration, connector/scheduler,
or Core API activation.

## Required Fixture Contract

The Corebox side supplies a new local input directory containing only:

```text
fixture-manifest.json
original.bin
envelope.json
corebox-c2-zero-write-preview.json
```

`fixture-manifest.json` must bind:

- the fixture ID, `prepared_not_authorized` status, and
  `generated_harmless` classification;
- the Corebox commit and the fact that `CoreboxSyntheticTransport` generated
  the envelope;
- the C1 profile `pios_synthetic_source_ingress_v1`;
- SHA-256 and byte counts for `original.bin` and canonical `envelope.json`;
- all-false assertions for endpoint, transport, credentials, enrollment,
  personal data, app networking, Owner Bind, Core API, connector, scheduler,
  hydration, migration, and source-decommission activity.

The fixture must use only synthetic-safe generic IDs and a new harmless text
original. It must not include a path, bookmark, URL, endpoint, `core://` or
provider reference in payload/provenance/extensions, a real device identifier,
or any owner content. The C1 envelope validator is the authoritative
path-free/integrity gate.

The fixture exporter is outside the Solo runner. The runner consumes these
four artifacts exactly and does not read Corebox state or invoke an app. The
fixture need not contain a proof ID or receipt clock: those are separately
supplied by the named owner decision and bound as exact runner arguments,
without changing the fixture.

## Preview Runner Interface

`scripts/run_pios_solo_c2_synthetic_proof.py` implements the zero-write
preview and the separately confirmed local lifecycle path. Both install a
CLI-process audit guard that rejects socket/subprocess events. The confirmed
path uses only disposable local lifecycle roots and an atomic harmless evidence
directory; it has no transport or Core-runtime integration.

```sh
python3 scripts/run_pios_solo_c2_synthetic_proof.py \
  --input-dir <approved-local-fixture-directory> \
  --expected-envelope-sha256 <previewed-sha256> \
  --expected-original-sha256 <previewed-sha256> \
  --expected-zero-write-preview-sha256 <previewed-sha256> \
  --expected-fixture-manifest-sha256 <previewed-sha256>

# Do not run this command until a named owner decision authorizes this exact
# fixture, proof ID, receipt time, Solo revision, and empty evidence directory:
python3 scripts/run_pios_solo_c2_synthetic_proof.py \
  --proof-id <approved-proof-id> \
  --input-dir <approved-local-fixture-directory> \
  --evidence-dir '<Storage-wiki>/Storage/Other/pios-core/self-hosted-vm/c2-synthetic-proof/<approved-proof-id>' \
  --expected-envelope-sha256 <approved-sha256> \
  --expected-original-sha256 <approved-sha256> \
  --expected-zero-write-preview-sha256 <approved-sha256> \
  --expected-fixture-manifest-sha256 <approved-sha256> \
  --receipt-recorded-at <approved-UTC-whole-second> \
  --solo-revision <approved-committed-solo-revision> \
  --confirm-c2-local-synthetic-proof
```

The preview is the default and creates no state. The confirmation flag enables
the local lifecycle only when every execution input is present. The runner
rejects a missing/changed hash, proof ID, receipt time, Solo revision, existing
evidence directory, unsafe fixture, or cleanup/evidence failure. The current
implementation must not be used against the fixed fixture until the named
owner decision supplies those values.

The confirmation flag alone is insufficient: the runner must require exact
approved hashes and a new evidence destination. It must reject a changed input
after preview rather than silently recomputing approval scope.

## Planned Execution Checks

After confirmed preflight, the runner uses isolated temporary directories under
`/private/tmp` with restrictive permissions. It performs these local checks in
order:

1. Verify every manifest-listed artifact and its fixed hash binding. Require
   `prepared_not_authorized` fixture status, `local_fixture_export: true`, all
   other authorization gates false, and a zero-write preview with zero network
   and cloud calls. Validate safe identifiers and absence of forbidden
   transport values.
2. Parse `envelope.json`; require that its raw bytes equal B1 canonical JSON
   bytes and that `validate_synthetic_envelope(envelope, original)` passes.
3. In a fresh main lifecycle root, submit once with the fixed receipt time;
   require `accepted`, verify the receipt, and retain only the local synthetic
   evidence generated by the existing lifecycle.
4. Submit the unchanged envelope/original again; require `duplicate`, verify
   the duplicate receipt, and require the same receipt ID and complete binding.
5. Use the receipt-bound local `readback_original` and `export`; recompute the
   original SHA-256/byte count and independently verify the exported accepted
   receipt. This is local `core://` receipt-reference verification only, not a
   Core API lookup.
6. In separate fresh temporary roots, prove the already-defined refused and
   revocation outcomes: `synthetic_denied` with no receipt, and a synthetic
   grant revocation followed by `grant_revoked`. This models no real device
   revocation or enrollment.
7. Optionally exercise the existing `retry_once` path in another fresh root;
   only the byte-identical retry may proceed. A changed envelope/original must
   fail with `RetryBindingMismatch`.
8. Write an evidence manifest containing every input/output hash, status,
   receipt ID, test-clock value, source revision, and cleanup result. Verify it
   before declaring success.

The runner must install a local no-network guard for its own process and have
tests proving that its imports and execution path do not call sockets,
subprocesses, cloud CLIs, or app binaries. A guard failure is a stop condition.

## Retention, Cleanup, And Diagnostics

The evidence destination is outside the VM image and Core root. On success it
retains only harmless generated data:

- the exact four input artifacts;
- accepted and duplicate receipt artifacts;
- exported receipt/readback result and synthetic outcome summaries;
- the canonical hash manifest, runner version/revision, and sanitised log; and
- a cleanup record listing only temporary directory labels and their successful
  removal, never a personal filesystem path.

Temporary lifecycle roots, local retained originals, manifests, receipts,
retry state, and indexes are removed in a `finally` cleanup after the evidence
manifest is written and verified. The runner must not offer a `--keep-workdir`
option. If evidence cannot be written or verified, it records a sanitised
failure marker outside the lifecycle root, removes temporary state, exits
non-zero, and requires a new owner decision before another attempt.

## Hard Stop Conditions

Stop immediately, write only sanitised diagnostics, clean temporary state, and
do not retry automatically if any of these occurs:

- missing confirmation, hash, fixture-manifest, or collision-free proof ID;
- evidence destination already exists;
- a non-harmless field, forbidden path/URL/provider/logical reference, real
  owner/device content, or any non-false gate assertion;
- C1 envelope, candidate, original, manifest, receipt, duplicate, export, or
  readback integrity mismatch;
- any unexpected outcome code, receipt ID, or retry mutation;
- any attempted network/app/VM/Core/cloud operation or no-network guard hit;
- incomplete cleanup; or
- evidence-manifest write/verification failure.

No fallback may enable networking, create a local account, re-run against a
different fixture, use C1 evidence as a substitute fixture, or touch the
retained Solo VM.

## Acceptance And Review

A C2 result is passed only if every planned check succeeds, all hashes and
receipt bindings are recorded, cleanup is proven, and an independent reviewer
can read the retained harmless artifacts without a Corebox app, endpoint, or
Core runtime. Passing C2 does not authorize any named personal capture. Stop
for owner review before proposing a later personal-capture decision.
