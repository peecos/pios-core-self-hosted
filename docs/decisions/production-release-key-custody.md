# Production Release-Key Custody

Status: decided for first public release; production key setup passed; first prerelease published
Created: 2026-07-02
Decided: 2026-07-02

This decision record defines the release-key custody model for signing the
self-hosted QEMU image as a public peecos release.

The local signing mechanics proof is complete. That proof used a local
development Ed25519 key under ignored `image-artifacts/`. It proves the signing
flow works, but it is not production release-key custody.

The first production release-key setup proof is complete. Detailed setup
evidence is retained in private operator records; the public repository contains
only the public verification key, fingerprint, and verification instructions.

## Decision

Use **Option C: Two-Step Release** for the first public PIOS/Core releases.

Build and validation may be automated or scripted, but final public checksum
signing must be a separate human-controlled signing step using a protected
production release key.

The local development signing key from proof work must not be reused as the
production release key.

## Required Properties

The production release-signing key must support:

- signing `SHA256SUMS` or equivalent release checksum files;
- publishing the public verification key;
- documenting owner/agent verification commands;
- key rotation;
- key compromise response;
- separation between development proof keys and production release keys;
- no private key material in public repositories, VM images, release packages,
  Core Bundles, or owner manifests.

## Candidate Models

### Option A: Hardware-Backed Local Release Key

The release maintainer signs releases from a controlled machine using a
hardware-backed key or token.

Pros:

- strong custody boundary;
- private key is not stored in CI;
- easy to reason about for early releases.

Cons:

- release depends on a human-controlled signing ceremony;
- harder to automate;
- requires hardware-token procedure documentation.

### Option B: Repository/CI Release Signing

The release process signs artifacts in a controlled CI or release service.

Pros:

- repeatable;
- fits GitHub release automation;
- easier for multi-maintainer projects later.

Cons:

- requires careful secret storage and access control;
- CI compromise can affect signing;
- needs stronger repository governance before public use.

### Option C: Two-Step Release

Build and validate artifacts in automation, then sign final checksums manually
with a hardware-backed release key.

Pros:

- automation handles reproducible packaging and validation;
- final signing remains human-controlled;
- good fit for early public releases.

Cons:

- still requires a manual release step;
- release runbook must prevent signing unvalidated artifacts.

## First Public Posture

Use Option C for the first public release:

1. Build package artifacts from a clean tagged source state.
2. Run package validation and boot proof.
3. Generate `SHA256SUMS`.
4. Review the release manifest and proof records.
5. Sign `SHA256SUMS` with a hardware-backed or otherwise separately protected
   production key.
6. Publish artifact, manifest, checksums, signature, public verification key,
   and verification commands.

Do not reuse the local development key from the proof as a public release key.

## Production Release Gate

A release is not public until all are true:

- source tag exists;
- artifact package exists;
- package validation passed;
- boot proof from extracted package passed;
- release manifest generated for the tag/version;
- `SHA256SUMS` generated;
- `SHA256SUMS` signed with the production release key;
- signature verified before upload;
- public verification key and commands are documented;
- release notes include boundaries and unsupported provider statuses.

## Canonical Public Key Location

The canonical release-key fingerprint publication location is:

```text
https://www.peecos.org/pios/docs
```

The public repository also carries the public verification key and fingerprint
for convenience.

## Open Items

- continue release signing from clean source tags.
- add key-compromise and revocation contact instructions.

## Related Runbooks

```text
docs/runbooks/production-release-signing-ceremony.md
docs/runbooks/production-release-key-setup-checklist.md
docs/install/release-verification.md
```
