# PIOS Solo C1: Generic Synthetic Source-Ingress Contract

Status: local-only C1 preparation. No endpoint, transport, enrollment,
credential, Owner Bind, app networking, or personal data is authorized.

## Scope

`scripts/pios_synthetic_source_ingress.py` is the generic Solo-side contract
layer needed for C1 review. It projects a validated B2 candidate into a strict
synthetic-only envelope, then exercises the existing local B2 lifecycle in a
temporary directory. It is not a Corebox adapter or a service.

The input B2 candidate remains unchanged. In particular, its local diagnostic
provenance is not rewritten. The projection has separate canonical bytes and a
separate `candidate_integrity` / `envelope_integrity` binding.

## Agreed Generic Decisions

| C1 topic | Generic C1 decision |
| --- | --- |
| Profile | Exact profile is `pios_synthetic_source_ingress_v1`. It accepts only `synthetic_normal`, `synthetic_allowed`, and `synthetic_prepared`; any other profile/state is refused. |
| Projection | B2 candidate payload, original integrity, processing manifest, extensions, stable source ID, and idempotency key are projected. Local provenance is replaced by a strict three-field synthetic projection; raw local candidate remains intact. |
| Canonicalization | B1 strict canonical UTF-8 JSON, lower-case SHA-256, and exact byte counts are used for payload, manifest, B2 transport candidate, and outer envelope. |
| Identity | Owner, integration/version, platform, synthetic origin-device, capture, item, source-native record, stable source record, and idempotency key are all receipt-bound tokens. None is a credential or enrollment record. |
| Original integrity | Original SHA-256/byte count and processing-manifest SHA-256/byte count are recomputed before submission and receipt validation. The processing-manifest object is explicitly carried so its digest is independently recomputable. |
| Receipt | Accepted and duplicate receipts contain all identity/integrity bindings plus canonical `core://` event/original/processing-manifest references. Receipt IDs are deterministic B2 bindings. The local synthetic issuance time is an explicit test-clock input and the accepted receipt is retained immutably; a duplicate returns the same binding with duplicate status. |
| Outcomes | Accepted, duplicate, denied, retry, revoked, and export/readback remain local synthetic results. Retry stores the exact envelope/candidate/idempotency binding; changed retry input fails closed. |
| Readback | An independent caller supplies envelope, original bytes, and receipt; it validates the receipt then recomputes original integrity from local retained synthetic bytes. |
| Retention | Callers provide a temporary local root. Synthetic originals, manifests, receipts, and retry state are local-only and should be removed after the reviewed fixture proof. |

## Path-Free Transport Projection

Synthetic provenance has exactly these values:

```json
{
  "fixture_class": "generated_harmless",
  "source_shape": "<synthetic-safe-token>",
  "transport": "synthetic_local_projection"
}
```

The envelope rejects filesystem paths, bookmarks, endpoints, URLs, provider
references, logical references before a receipt exists, credentials, tokens,
passwords, and owner-comment fields anywhere in payload, manifest, extensions,
or transport provenance. Canonical receipt fields accept only their exact
expected `core://` values; `s3://` cannot enter them.

## Verification

Focused tests cover:

- deterministic projection while preserving the raw local candidate outside the
  projection;
- altered original bytes, candidate/payload/manifest integrity, and envelope
  integrity rejection;
- path, endpoint, and non-synthetic-profile rejection;
- accepted and duplicate receipts bound to owner, device, capture, item,
  source-native/stable record, idempotency, digests, and `core://` references;
- retry refusal when canonical bytes or idempotency change;
- revocation blocking a new synthetic attempt; and
- local export plus independent original-byte readback.

Run:

```sh
python3 -m unittest tests/test_pios_synthetic_source_ingress.py
python3 -m unittest discover -s tests
```

## C1 Review Gaps Outside This Repository

The generic Solo contract is ready for C1 review, but C1 is not yet a complete
Corebox implementation:

1. Corebox must implement a pure Swift transport projection that maps its
   local candidate fields to this envelope while excluding `manifest_path` and
   `item_manifest_path`.
2. Corebox must implement local receipt validation with the same bindings and
   use it before changing local state to `synthetic_accepted`.
3. Corebox must select its exact synthetic integration-version and token mapping
   for origin device/capture/item identifiers, then prove deterministic bytes
   with harmless generated text only.
4. C2 still requires a separately approved generated fixture and a reviewed
   execution boundary. This local contract does not create a transport path or
   real device authorization.

The current Starter image and O4 maintenance boundary are unchanged. If this
module is carried into a future capability-bearing image, re-run image hygiene,
residue, local boot, and provider evidence against that exact artifact.
