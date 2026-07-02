# PIOS Core Self-Hosted QEMU Local VM

Status: release-candidate install documentation for the signed public prerelease

This guide describes the local QEMU package shape proven in the repository. It
is written for an owner or owner-authorized agent that wants to inspect and boot
the self-hosted Core Template package on a local machine.

The current artifact is a data-empty Core Template. It contains Core setup
tools, not owner data.

## Current Package Shape

The local proof package contains:

```text
README.md
qemu-standalone-20260703.qcow2
qemu-standalone-20260703.qcow2.sha256
release-manifest.json
```

The package archive is:

```text
pios-core-self-hosted-qemu-arm64-v0.1.0-rc1.tar.zst
```

The image is:

```text
qemu-standalone-20260703.qcow2
```

Current architecture:

```text
arm64
```

Current image format:

```text
qcow2
```

## Verify Package

After downloading or copying the package, verify the package checksum against
the public release manifest.

For public releases, first follow:

```text
docs/install/release-verification.md
```

For the current release-candidate package:

```bash
shasum -a 256 pios-core-self-hosted-qemu-arm64-v0.1.0-rc1.tar.zst
```

Expected package digest:

```text
a0516caa3a30e3a375ae66473159953a4ff79877f77c0ceb95b20a3862ff7c4a
```

Extract:

```bash
tar --zstd -xf pios-core-self-hosted-qemu-arm64-v0.1.0-rc1.tar.zst
cd pios-core-self-hosted-qemu-arm64-v0.1.0-rc1
```

Verify the extracted image:

```bash
shasum -a 256 -c qemu-standalone-20260703.qcow2.sha256
```

Expected result:

```text
qemu-standalone-20260703.qcow2: OK
```

## Inspect Image

Confirm the image is standalone and does not depend on a backing file:

```bash
qemu-img info qemu-standalone-20260703.qcow2
```

Expected properties:

```text
file format: qcow2
virtual size: 3.5 GiB
no backing file
```

## First-Boot Manifest

First boot needs an owner-specific self-hosted provisioning manifest. The
manifest must be created by the owner or an owner-authorized agent.

Minimal shape:

```json
{
  "manifest_version": "self_hosted_provisioning_manifest_v1",
  "core_instance": {
    "env_name": "local",
    "owner_id": "owner_example",
    "owner_slug": "example"
  },
  "self_hosted": {
    "core_root": "/var/lib/pios-core/owners/example/core",
    "key_store_path": "/var/lib/pios-core/owners/example/keys",
    "key_provider": "local_dev_file_keys"
  },
  "services": {
    "start_core_api": false,
    "start_connectors": false,
    "start_scheduler": false
  },
  "authorization": {
    "hydrate_bundle": false,
    "connector_sync": false,
    "broad_migration": false,
    "source_decommission": false
  }
}
```

The current proof implementation requires all authorization gates and service
flags to remain `false` during empty first boot.

## Boot With QEMU

For the current arm64 proof image on macOS with QEMU/HVF, the tested pattern is:

```bash
qemu-system-aarch64 \
  -machine virt,accel=hvf,highmem=off \
  -cpu host \
  -m 2048 \
  -smp 2 \
  -drive if=pflash,format=raw,readonly=on,file=/opt/homebrew/share/qemu/edk2-aarch64-code.fd \
  -drive if=pflash,format=raw,file=/path/to/edk2-arm-vars-copy.fd \
  -drive if=virtio,format=qcow2,file=/path/to/proof-overlay.qcow2 \
  -drive if=virtio,format=raw,readonly=on,file=/path/to/seed.iso \
  -netdev user,id=net0 \
  -device virtio-net-pci,netdev=net0 \
  -nographic
```

Use a copy of the EDK2 vars file for each VM boot. Do not write directly to the
shared template vars file.

For ordinary use, the owner-facing flow should be wrapped by a setup script or
VM frontend. The raw QEMU command is the current proof-level interface, not the
final product experience.

## Expected First-Boot Result

`pios-core-init` should create:

```text
/var/lib/pios-core/owners/<owner-slug>/core/originals
/var/lib/pios-core/owners/<owner-slug>/core/events
/var/lib/pios-core/owners/<owner-slug>/core/knowledge
/var/lib/pios-core/owners/<owner-slug>/core/derived
/var/lib/pios-core/owners/<owner-slug>/core/system
```

Bootstrap records:

```text
system/bootstrap/core-instance.json
system/bootstrap/zone-manifest.json
system/bootstrap/key-manifest.json
system/bootstrap/health-check.json
```

Generated local development keys are stored outside the Core root at the
manifest's `key_store_path`.

## Boundaries

This local proof does not yet provide:

- production-grade key provider;
- local protected-ingestion enforcement;
- local immutability/backup policy;
- local remediation/erasure mechanism;
- service supervisor startup;
- connector sync;
- owner-data migration;
- provider support beyond separately recorded provider proofs.

No broad migration or connector sync should be started from this package.
