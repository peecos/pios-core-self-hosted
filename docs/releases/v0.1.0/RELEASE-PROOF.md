# PIOS Starter v0.1.0 Release Proof

Status: published and verified

## Release Identity

- Source tag: `v0.1.0`
- Source commit: `b8fa6beb649f7cfd5c30f827432621f285ec849f`
- Release: `https://github.com/peecos/pios-core-self-hosted/releases/tag/v0.1.0`
- Published: 2026-08-01
- Channel: stable
- Architecture: arm64
- Format: standalone QCOW2 package for local QEMU

## Artifact Identity

- Package: `pios-starter-v0.1.0-arm64.tar.zst`
- Package SHA-256: `be414ea8098a91aba4b12785368045c4acd742e9f8fad279affc546fc65cedae`
- Image SHA-256: `621499be6b737cebaa72496ddab48b9ef9029cdef6d00913796a83292f91f3e8`
- Public key SHA-256: `0c33f7ed09c2dcf37399cdca72096c076156689d9a636f37730a3ea139891d0f`

## Passed Gates

- 117 repository tests;
- tracked-source private-identifier and public-document scans;
- image-root allowlist and hygiene scan;
- candidate and standalone boot proofs;
- extracted-package boot proof;
- fresh empty-state hygiene proof;
- B1-B5 capability lifecycle proof;
- residue and prior synthetic-token inspection;
- evidence binding to one QCOW2 checksum;
- focused independent read-only release review;
- protected production-key signing and independent local signature verification;
- final release-directory checksum verification; and
- GitHub release asset upload verification.

The image manifest explicitly excludes C3 transport, socket, orchestration,
and execution tooling. Corebox is represented only by offline companion
boundary documentation; no Corebox binary, state, credential, endpoint, or
enabled connection is present.

## Boundary

This release does not authorize or provide Owner Bind, a hosted service,
public endpoint, device enrollment, app networking, background sync, Corebox
personal intake, credentials, broad migration, connector operation, or
personal data. Google Cloud remains experimental; x86_64, Azure, AWS EC2
self-hosted, and generic provider support are not claimed by this release.
