# Self-Hosted Portability Contract

Status: local restore, empty-init, image-root, and packaging scaffold proofs passed; golden VM image not yet built

The AWS Core Managed implementation is the current reference build. Core
Self-Hosted remains the portability target. This repo should keep AWS decisions
compatible with a future local/VM implementation instead of treating AWS service
behavior as the PIOS model.

The full owner-facing contract is maintained in Storage-wiki:

```text
Storage-wiki/Storage/Other/PIOS-2.0-Core-Self-Hosted-Implementation-Contract.md
```

## Required Equivalences

| Core contract | AWS reference | Self-hosted equivalent |
|---|---|---|
| Core zones | S3 prefixes | directories or object-store namespaces |
| Protected canonical writes | deterministic key + `If-None-Match:*` | atomic create/no-overwrite write |
| Originals | S3 object versions + KMS + retention | retained files/objects + checksums + immutable/backup policy |
| Events | one JSON object per event | one deterministic JSON/NDJSON event object |
| KMS | per-zone AWS KMS keys | local key hierarchy such as age/GPG/SOPS/OS keychain/HSM |
| Object Lock | Governance retention / legal hold | filesystem immutability, append-only permissions, immutable backup, or documented policy control |
| DynamoDB index | optional rebuildable projection | SQLite WAL or PostgreSQL when justified |
| Athena/DuckDB projections | Athena/Glue over JSON/Parquet | DuckDB over JSON/NDJSON/Parquet |
| CloudTrail | AWS audit trail | local audit log and file-integrity/process logs |
| Core Template | CDK/CloudFormation | VM image, install script, container composition, or config bundle |
| Core Bundle | `.tar.zst` manifest/checksum bundle | same bundle format hydrated into local storage |

## Repo Rule

When adding AWS features, ask whether the concept maps cleanly to the
self-hosted contract:

- event envelope fields should stay storage-agnostic where possible;
- S3 object keys and headers belong to writer metadata/adapters, not conceptual
  event meaning;
- DynamoDB, Athena, KMS, CloudTrail, and Object Lock are implementations of
  Core contracts, not the contracts themselves;
- Core Bundle export/import should remain provider-neutral;
- derived projections must be rebuildable from originals, events, knowledge,
  and system records.

## First VM/Local Proof

The first self-hosted proof was intentionally narrow and used the refreshed
current pilot bundle recorded in
`docs/runbooks/current-pilot-core-bundle-refresh-2026-06-29.md`.

Completed proof:

`docs/runbooks/self-hosted-local-validation-proof-2026-07-01.md`

The proof:

1. created an empty five-zone local structure;
2. hydrated the refreshed 108-object Core Bundle into it;
3. verified checksums;
4. resolved AWS-style `s3://<bucket>/<key>` references locally by key suffix;
5. verified event/manifest/original/detail reference traversal;
6. rendered one History/update detail page from local files;
7. rebuilt one generated event index.

This proof did not upload new owner data, enable connector sync, decommission
AWS source objects, prove self-hosted protected ingestion, or claim production
self-hosted readiness.

## Golden VM Image Target

The next self-hosted target is a data-empty golden VM image: a Core Template
that contains code, schemas, services, setup logic, and validation tools, but no
owner data or hydrated Core Bundle.

The first-boot initializer proof has passed:

`docs/runbooks/self-hosted-empty-init-proof-2026-07-01.md`

The data-empty image-root scaffold proof has passed:

`docs/runbooks/self-hosted-image-root-scaffold-proof-2026-07-01.md`

The VM packaging scaffold proof has passed, with boot blocked pending VM builder
availability:

`docs/runbooks/self-hosted-vm-packaging-scaffold-proof-2026-07-01.md`

Plan:

`docs/runbooks/self-hosted-golden-vm-image-plan.md`
