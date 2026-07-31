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

## Provider Preparation

The provider-specific import path may create only data-empty staging/import
resources before Owner Bind. For the Google path, retain the private VPC,
no-public-IP, IAP/OS Login, no-service-account, Shielded VM, and no-egress
baseline. Import commands, disk type, and guest-driver requirements are in the
Google persistent-Core runbook.

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
