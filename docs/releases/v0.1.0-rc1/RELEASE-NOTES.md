# PIOS Core Self-Hosted QEMU arm64 v0.1.0-rc1

Status: signed release candidate; not published

## Summary

This release candidate packages the data-empty PIOS Core Self-Hosted QEMU arm64
image as a Core Template. It is intended for local QEMU validation and early
provider-import proof work. It contains Core setup tooling and empty structure,
not owner data.

## Artifact

```text
pios-core-self-hosted-qemu-arm64-v0.1.0-rc1.tar.zst
```

Package SHA-256:

```text
a0516caa3a30e3a375ae66473159953a4ff79877f77c0ceb95b20a3862ff7c4a
```

Standalone image SHA-256:

```text
1eea6f9a752454addeb0143ff88e7357c4a41c018d721059b0bb72aa03ce647e
```

## Verification

Verify the public key, `SHA256SUMS.sig`, `SHA256SUMS`, package checksum,
extracted image checksum, and qcow2 backing-file status before booting or
importing the image.

Use:

```text
docs/install/release-verification.md
```

Production public key fingerprint:

```text
0c33f7ed09c2dcf37399cdca72096c076156689d9a636f37730a3ea139891d0f
```

## Provider Status

```text
local_qemu: local_proof_passed
google_cloud: experimental
azure: unsupported
aws_ec2_self_hosted: unsupported
generic_vm_providers: unverified
```

AWS EC2 self-hosted is intentionally not a validation target for this release
candidate because the AWS-native owner path is Core Managed AWS.

## Boundaries

- No owner data is included.
- No private manifests are included.
- No private key material is included.
- This is not a backup.
- This does not authorize connector sync, bundle hydration, broad migration, or
  source decommissioning.
- The release candidate is not published until the public repository/site
  publication gate passes.

