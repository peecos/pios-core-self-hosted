# Local Machine VM Setup Validation Plan

Status: proof-level local setup passed; final owner-facing UX not complete
Created: 2026-07-02

This runbook defines the next validation target for running the PIOS Core
Self-Hosted golden image on an owner's own computer.

It does not authorize owner-data migration, connector sync, bundle hydration,
or public release publication.

## Purpose

The current repository has proven that the data-empty QEMU image can boot and
initialize Core locally. The next local-machine step is to validate the setup as
an owner/agent installation flow rather than as an internal proof command.

Success means an owner-authorized agent can take the packaged image, verify it,
create a synthetic first-boot manifest, boot it on a local VM runtime, confirm
health, and stop without enabling migration or connectors.

## Current Inputs

```yaml
release_package: pios-core-self-hosted-qemu-arm64-20260702.tar.zst
package_sha256: 0158d2e2999a9ca94a480015d9de1c18b0d530f2aeae2233f5edfb8751e5b205
image: qemu-standalone-20260702.qcow2
image_sha256: 92f065e3f8a5d0db87254c88db13e031a2077138cf2f8bb4c78126eadd868de4
architecture: arm64
format: qcow2
status: local_proof_not_published
```

Install guidance:

```text
docs/install/self-hosted-qemu-local-vm.md
```

## Validation Flow

1. Start from the local release package, not from build directories.
2. Verify package checksum.
3. Extract the package into a clean local validation directory.
4. Verify the extracted QCOW2 checksum.
5. Inspect the QCOW2 and confirm no backing file.
6. Create a synthetic self-hosted provisioning manifest with all service and
   authorization gates false.
7. Create a local first-boot seed or equivalent VM metadata path.
8. Boot the image in a local VM runtime.
9. Confirm `pios-core-init` runs.
10. Confirm all five Core zones exist.
11. Confirm `system/bootstrap/health-check.json` reports `status: passed`.
12. Confirm generated keys are outside the Core root.
13. Confirm no bundle hydration, connector sync, broad migration, or source
    decommission occurred.
14. Shut down the VM and record cleanup/removal steps for temporary VM state.

## Runtime Targets

The first validated local-machine target can be one of:

- QEMU directly on macOS or Linux;
- UTM on macOS using the QEMU backend;
- another local VM frontend that can boot the QCOW2 or a converted copy while
  preserving first-boot metadata behavior.

The proof should record which runtime was used. Passing on one runtime does not
automatically mark all local VM runtimes supported.

## Evidence Record

Record the proof as:

```yaml
local_machine_vm_setup:
  status: passed | failed
  proof_date: <YYYY-MM-DD>
  runtime: qemu | utm | other
  host_os: macos | linux | windows | other
  architecture: arm64 | x86_64
  package_sha256: <sha256>
  image_sha256: <sha256>
  first_boot_status: passed | failed
  health_check_status: passed | failed
  generated_keys_outside_core: true | false
  authorization_gates_false: true | false
  cleanup_status: complete | incomplete
```

## Fail Conditions

Fail the validation if:

- checksum verification fails;
- the image has a backing file;
- the first-boot manifest cannot be supplied;
- service or authorization gates are true;
- `pios-core-init` fails;
- the health check fails;
- keys are generated inside the Core root;
- cleanup is not understood;
- owner data is included.

## Current Boundary

Proof-level local-machine setup validation has passed. Detailed proof evidence
is retained in private operator records.

The remaining gap is owner-facing usability: a polished wrapper or local VM
frontend flow, production-signed package verification, hardened keys, and local
operational policies.
