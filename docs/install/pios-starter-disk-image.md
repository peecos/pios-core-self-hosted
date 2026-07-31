# PIOS Starter Disk Image

## Purpose

The **PIOS Starter Disk Image** is the neutral, data-empty disk image from
which a new owner can start a fresh PIOS Core. It contains reusable runtime,
empty Core schemas, health/recovery tooling, and provider guest capabilities.
It does not contain owner identity, data, keys, credentials, policy, access
principals, domains, or endpoints.

The current local release-candidate naming convention is:

```text
pios-starter-disk-image-YYYYMMDD.qcow2
pios-starter-disk-image-YYYYMMDD-release-manifest.json
pios-starter-disk-image-YYYYMMDD.qcow2.sha256
```

## Neutral Golden Starter Boundary

Before **Owner Bind**, work may:

- build, package, checksum, sign, retain, import, and prove the image;
- add generic runtime, health, recovery, portability, and provider support;
- use synthetic fixtures and all-false provisioning manifests; and
- run isolated, data-empty first-boot and restore proofs.

Before Owner Bind, work must not create or choose owner identity, Core data,
keys, credentials, authorization grants, owner policy, project/VPC/IAM
principals, DNS/TLS/passkey settings, public endpoint, source records, or
application networking.

## Verify A Release Candidate Locally

1. Verify the release-manifest reports `status: passed`.
2. Verify the standalone QCOW2 checksum against its `.sha256` file.
3. Inspect the QCOW2 with `qemu-img info`; it must have no backing file.
4. Run the packaged local proof. It must report all five zones and a passed
   `self_hosted_core_health_check_v1` record.
5. Keep proof logs, manifests, and checksums outside the image and Core root.

For a second independent fresh-VM hygiene proof, run the packaged disk through
the disposable local overlay workflow below. It verifies the release manifest,
checksum, and absence of a QCOW2 backing file. Before Core initialization, the
guest refuses to continue unless `/var/lib/pios-core` is absent or empty; this
rules out a carried-over Core root, owner state, or prior synthetic-owner token.
It then initializes a distinct synthetic owner with all services disabled and
requires a passed five-zone health record.

```bash
python3 scripts/prove_pios_starter_disk_image_hygiene.py \
  --release-manifest image-artifacts/pios-starter-disk-image-YYYYMMDD/pios-starter-disk-image-YYYYMMDD-release-manifest.json \
  --output-dir image-artifacts/pios-starter-disk-image-hygiene/YYYYMMDD \
  --run-id pios-starter-hygiene-YYYYMMDD
```

This is a local-only proof. It creates only a disposable QCOW2 overlay, EDK2
vars copy, NoCloud seed, serial log, and result manifest outside the Starter
image. QEMU networking remains restricted (`user,restrict=on`), and the
workflow does not hydrate a bundle or enable the Core API, connectors,
scheduler, or application networking.

For a deeper package-residue check that does not initialize a Core, run:

```bash
python3 scripts/inspect_pios_starter_disk_image_residue.py \
  --release-manifest image-artifacts/pios-starter-disk-image-YYYYMMDD/pios-starter-disk-image-YYYYMMDD-release-manifest.json \
  --output-dir image-artifacts/pios-starter-disk-image-residue-inspection/YYYYMMDD \
  --run-id pios-starter-residue-YYYYMMDD
```

The inspection validates the same standalone/checksum contract, requires an
empty Core state path, rejects known temporary build and proof paths, and
searches persistent Core, cloud-init, log, configuration, home, and temporary
paths for the prior synthetic-owner token recorded by the source candidate.
The token is supplied to the guest in encoded form so the inspection seed does
not create the text it is checking for. It does not run `pios-core-init`.

If this gate finds only the known empty `/mnt/pios-seed` temporary mount
directory from an older offline-package build, create a replacement package
locally rather than modifying the source image. The cleanup command removes
only that empty directory on a disposable overlay, flattens a new standalone
QCOW2, then runs the synthetic five-zone boot proof:

```bash
python3 scripts/clean_pios_starter_disk_image_residue.py \
  --release-manifest image-artifacts/pios-starter-disk-image-YYYYMMDD/pios-starter-disk-image-YYYYMMDD-release-manifest.json \
  --output-dir image-artifacts/pios-starter-disk-image-clean/YYYYMMDD \
  --run-id pios-starter-disk-image-YYYYMMDD-r2
```

Run the fresh-image hygiene proof and package-residue inspection again against
that replacement manifest. Any other residue requires a reviewed rebuild from
the fixed source builder; do not use this narrow cleanup tool for broader
changes.

If a local runner stops after the cleanup serial log has recorded both cleanup
markers and the standalone QCOW2 exists, resume only the synthetic health proof
and manifest creation with:

```bash
python3 scripts/finalize_pios_starter_disk_image_cleanup.py \
  --source-release-manifest image-artifacts/pios-starter-disk-image-YYYYMMDD/pios-starter-disk-image-YYYYMMDD-release-manifest.json \
  --cleaned-image image-artifacts/pios-starter-disk-image-clean/YYYYMMDD/pios-starter-disk-image-YYYYMMDD-r2.qcow2 \
  --cleanup-serial-log image-artifacts/pios-starter-disk-image-clean/YYYYMMDD/pios-starter-disk-image-YYYYMMDD-r2-cleanup-serial.log \
  --output-dir image-artifacts/pios-starter-disk-image-clean/YYYYMMDD \
  --run-id pios-starter-disk-image-YYYYMMDD-r2
```

The finalizer refuses missing cleanup markers and rechecks the QCOW2 format and
backing-file contract before it runs the synthetic health proof.

## Validate Local Candidate Evidence

Before bringing a local candidate to a separately approved signing or
publication review, bind its package-health proof, fresh-VM hygiene proof, and
residue inspection to the exact same QCOW2 and checksum:

```bash
python3 scripts/validate_pios_starter_disk_image_evidence.py \
  --release-manifest image-artifacts/pios-starter-disk-image-YYYYMMDD/pios-starter-disk-image-YYYYMMDD-release-manifest.json \
  --fresh-hygiene-result image-artifacts/pios-starter-disk-image-YYYYMMDD/fresh-hygiene/pios-starter-hygiene-YYYYMMDD-result.json \
  --residue-inspection-result image-artifacts/pios-starter-disk-image-YYYYMMDD/residue-inspection/pios-starter-residue-YYYYMMDD-result.json \
  --output image-artifacts/pios-starter-disk-image-YYYYMMDD/pios-starter-disk-image-YYYYMMDD-evidence-readiness.json
```

A passed result means only that the local image evidence is complete. It does
not sign, publish, import, deploy, create an owner-specific Core, or change
provider-support status.

To prepare an owner decision for the separately governed production signing
ceremony without creating a tag, signature, or public release, run:

```bash
python3 scripts/plan_pios_starter_signing_review.py \
  --evidence-readiness image-artifacts/pios-starter-disk-image-YYYYMMDD/pios-starter-disk-image-YYYYMMDD-evidence-readiness.json \
  --output image-artifacts/pios-starter-disk-image-YYYYMMDD/pios-starter-disk-image-YYYYMMDD-signing-review-plan.json
```

The plan is expected to remain blocked until the owner supplies a release ID,
immutable source tag, artifact/release-note set, protected production-key
authorization, and explicit publication decision.

## Provider Preparation

The provider-specific import path may create only data-empty staging/import
resources before Owner Bind. For the Google path, retain the private VPC,
no-public-IP, IAP/OS Login, no-service-account, Shielded VM, and no-egress
baseline. Import commands, disk type, and guest-driver requirements are in the
Google persistent-Core runbook.

## Optional Corebox Companion

Corebox is an optional, local-first Inbox companion distributed alongside PIOS
Starter for any Starter user to install. It is not part of this disk image and
is not a Core runtime dependency.

The Starter therefore contains no Corebox binary, app-group state, Inbox
folder, capture, manifest, local receipt history, endpoint, device identifier
or key, credential, sync setting, or enabled app transport. The generic source
primitives in the Starter deliberately preserve this separation: they support
future synthetic adapters without choosing Corebox storage, UI, identity, or
network behavior.

A separately released unbound companion may provide local macOS/iOS capture,
Share extensions, local manifests and ledgers, candidate construction, and
archive/move/delete behavior. Its compatible-Core configuration must remain
disabled and unbound until a later owner explicitly selects their own Solo
target, confirms device enrollment, completes a synthetic-only proof, and
passes independent review. That later bind is not authorized by image import,
data-empty Core boot, or this documentation.

## Owner Bind

**Owner Bind** is a separately approved action. It turns a Neutral Golden
Starter into an owner-specific Core by creating or selecting fresh owner
identity, keys, access principals, owner policy, and eventually owner data.

Never use a disk snapshot as the starting point for a different owner: a
snapshot is recovery state and carries existing Core identity and keys. Use the
PIOS Starter Disk Image for an independent fresh Core instead.

## Post-Bind Requirements

After Owner Bind, verify fresh identity/key initialization, owner-approved
policy, access recovery, backup/retention, and the bounded health check before
any owner-data migration. Public HTTPS, Dash, passkeys, Corebox, connectors,
scheduler, Core API, and application networking require their own approved
stages.
