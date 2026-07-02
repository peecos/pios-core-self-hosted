# PIOS Core Release Verification

Status: draft public verification guide; production public key available in repo; no public release published

This guide explains how an owner or owner-authorized agent should verify a
PIOS/Core release package before booting or importing it.

## Required Files

A public release should provide:

```text
release-manifest.json
package.tar.zst
SHA256SUMS
SHA256SUMS.sig
peecos-release-signing-key.pub
```

The exact file names may include version, architecture, or channel.

Current production public key material in this repository:

```text
docs/release-keys/peecos-release-signing-key.pub
docs/release-keys/peecos-release-signing-key-fingerprint.txt
```

## Tool Requirements

For the current OpenSSL Ed25519 proof style, signature verification requires
OpenSSL 3.x.

On macOS, the system `openssl` is usually LibreSSL and may not support
`pkeyutl -rawin`. Install OpenSSL 3, for example with Homebrew `openssl@3`, and
invoke that binary explicitly if needed.

Checksum commands differ by platform:

```text
macOS: shasum -a 256 -c SHA256SUMS
Linux: sha256sum -c SHA256SUMS
```

## Verification Order

1. Verify the release-signing public key came from an official peecos source.
2. Verify `SHA256SUMS.sig` against `SHA256SUMS`.
3. Verify package checksums with `SHA256SUMS`.
4. Extract the package.
5. Verify the image checksum inside the package.
6. Inspect the image format and backing-file status.
7. Only then boot or import the image.

## Signature Verification

For the current OpenSSL Ed25519 proof style:

```bash
openssl pkeyutl \
  -verify \
  -rawin \
  -pubin \
  -inkey peecos-release-signing-key.pub \
  -in SHA256SUMS \
  -sigfile SHA256SUMS.sig
```

Expected successful output:

```text
Signature Verified Successfully
```

If signature verification fails, stop.

## Package Checksum Verification

```bash
shasum -a 256 -c SHA256SUMS
```

On Linux:

```bash
sha256sum -c SHA256SUMS
```

If any checksum fails, stop.

## Extract Package

```bash
tar --zstd -xf <package>.tar.zst
```

Then verify the image checksum file inside the extracted package:

```bash
shasum -a 256 -c <image>.qcow2.sha256
```

On Linux:

```bash
sha256sum -c <image>.qcow2.sha256
```

If verification fails, stop.

## Inspect Image

For QEMU/qcow2 images:

```bash
qemu-img info <image>.qcow2
```

Expected:

```text
file format: qcow2
no backing file
```

If the image unexpectedly depends on a backing file, stop.

## Check Release Manifest

Open `release-manifest.json` and confirm:

- release id and version are expected;
- architecture matches the target host or provider;
- package checksum matches `SHA256SUMS`;
- image checksum matches the extracted image checksum;
- provider support status does not overclaim;
- known limitations are acceptable.

## Fail-Closed Rules

Stop if:

- public key source is unclear;
- signature does not verify;
- checksum does not verify;
- image has unexpected backing-file metadata;
- architecture is wrong;
- provider import is not marked supported or experimental for your target;
- the owner has not approved setup on this host/provider.

## Current Boundary

The current repository contains a production public verification key and a
signed local release-candidate proof. The release candidate is not published
yet. The production key setup proof is recorded in:

```text
docs/runbooks/production-release-key-setup-proof-2026-07-03.md
```
