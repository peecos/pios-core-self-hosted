# PIOS Starter v0.1.0 Release Notes

Status: published stable release

## Overview

PIOS Starter v0.1.0 is the first stable release of the signed,
data-empty PIOS Core Starter for arm64 QEMU. It provides a neutral Core
template that an owner or owner-authorized agent can verify and boot before a
separately governed Owner Bind.

## Included

- standalone arm64 QCOW2 release package with no backing file;
- generic five-zone Core initialization and health primitives;
- portability, canonical source, generic lifecycle, projection, and
  safe-disabled owner-control primitives;
- embedded release-bound orientation under `/opt/pios-core/docs/starter/`; and
- local verification, checksum, signature, extraction, and boot instructions.

## Deliberately Not Included

- owner identity, data, keys, credentials, policy, or recovery material;
- a hosted account, public endpoint, Core API, or managed service;
- device enrollment, app networking, background synchronization, or personal
  intake;
- Corebox binaries, local Corebox state, or an enabled Corebox connection;
- C3 socket, transport, orchestration, or execution tooling; and
- broad migration, connector operation, or an unverified provider claim.

Corebox is an optional separately distributed companion. C3 remains dormant
development and conformance work and is not a runtime capability of this
release.

## Verification Boundary

The stable release was published only after the frozen source, generated image,
package, manifest, checksums, production signature, clean-machine boot proof,
and public-tree hygiene evidence all agreed. A successful Starter boot does not
authorize Owner Bind, app connection, or personal-data transfer.

## Provider Status

Local arm64 QEMU is the stable release target. Provider-specific import or
runtime claims remain governed by the provider-readiness matrix and separate
proof records.
