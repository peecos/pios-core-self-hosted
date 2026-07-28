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
  -nic none \
  -nographic
```

Use a copy of the EDK2 vars file for each VM boot. Do not write directly to the
shared template vars file.

For ordinary use, the owner-facing flow should be wrapped by a setup script or
VM frontend. The raw QEMU command is the current proof-level interface, not the
final product experience.

## Local Developer Wrapper (VM-0 / VM-1)

For a repeatable data-empty local workflow, use the repository wrapper. It is a
host-side tool: it does not build or download an image, create a provisioning
seed, mount host directories, or enable VM networking. Supply an already
verified, standalone data-empty QCOW2 image and an owner-authorized seed ISO.

The default `start` invocation is a non-mutating dry-run. It checks the image
format, backing-file safety, QEMU/HVF firmware, and exact command it would run;
it creates no overlay, firmware copy, log, or workspace.

```bash
python3 scripts/pios_self_hosted_vm.py \
  --image /safe/local/path/qemu-standalone-20260703.qcow2 \
  --seed-iso /safe/local/path/data-empty-first-boot-seed.iso \
  --expected-image-sha256 <verified-image-sha256>
```

To boot, add an explicit confirmation and choose a run workspace outside the
image and Core root. The wrapper creates a fresh QCOW2 overlay and EDK2 vars
copy under that workspace, captures the serial log there, and starts QEMU with
`-nic none`.

```bash
python3 scripts/pios_self_hosted_vm.py \
  --workspace /safe/local/path/pios-vm-runs \
  --run-id local-empty-001 \
  --image /safe/local/path/qemu-standalone-20260703.qcow2 \
  --seed-iso /safe/local/path/data-empty-first-boot-seed.iso \
  --expected-image-sha256 <verified-image-sha256> \
  --confirm-boot
```

The seed ISO must itself keep all service flags and authorization gates false.
The wrapper does not inspect or alter it; do not use an owner-data seed.

Check the recorded process state and serial-log health evidence:

```bash
python3 scripts/pios_self_hosted_vm.py status \
  --workspace /safe/local/path/pios-vm-runs --run-id local-empty-001
```

For a read-only diagnostic report, including the recorded input hashes, wrapper
artifact presence, QEMU `-nic none` posture, health-record result, and any
guest metadata-init attempt detected in the serial log:

```bash
python3 scripts/pios_self_hosted_vm.py diagnostics \
  --workspace /safe/local/path/pios-vm-runs --run-id local-empty-001
```

Diagnostics never starts, stops, writes to, or cleans up a VM run. A detected
metadata-init attempt is a local-image/profile issue to resolve before a repeat
boot; it does not mean the wrapper enabled networking.

Stop a run (records stop evidence without changing the base image):

```bash
python3 scripts/pios_self_hosted_vm.py stop \
  --workspace /safe/local/path/pios-vm-runs --run-id local-empty-001
```

After stopping every run, remove only the wrapper-created workspace with an
explicit confirmation. `reset` is the same deliberately destructive operation
under a name suitable for a fresh developer retry. Both refuse any directory
that lacks the wrapper marker.

```bash
python3 scripts/pios_self_hosted_vm.py cleanup \
  --workspace /safe/local/path/pios-vm-runs --confirm-cleanup

python3 scripts/pios_self_hosted_vm.py reset \
  --workspace /safe/local/path/pios-vm-runs --confirm-reset
```

The wrapper is deliberately local-only. It does not enable Core API,
connectors, scheduler, bundle hydration, or networking, and it must not be
pointed at iCloud, Storage-wiki, or personal-data paths.

The data-empty image root retains a Google metadata adapter for provider
portability, but it is fail-closed: on local QEMU it identifies a non-Google
DMI environment and exits without attempting a metadata request. A provider
metadata request is possible only after the guest identifies itself as Google
Compute Engine.

The image-candidate builder is separate from the ordinary local wrapper. Its
default uses QEMU user networking with `restrict=on` only because a pristine
cloud base image waits for an interface before cloud-init can install the
data-empty payload. This mode disables guest outbound connections by default;
unrestricted user networking requires the builder's explicit
`--allow-user-network` option. The ordinary local wrapper remains `-nic none`.

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
