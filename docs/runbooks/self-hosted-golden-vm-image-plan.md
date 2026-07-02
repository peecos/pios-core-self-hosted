# Self-Hosted Golden VM Image Plan

Status: signed v0.1.0-rc1 local release candidate exists; Google Cloud experimental; provider support not complete

This runbook defines the target for a data-empty Core Self-Hosted VM image that
can be installed by a new owner and later hydrated with an optional Core Bundle.
It supports the broader public productization target in
`docs/runbooks/pios-2-public-productization-target.md`.

## Goal

Produce a reusable golden VM image that is ready to start PIOS Core setup
without containing any owner data. The image should be usable on an owner's own
computer through a local VM runtime and on common VM-capable cloud providers
such as Google Cloud, Azure, AWS, Hetzner, UpCloud, or similar services.

The image is a Core Template artifact, not a Core Bundle.

## Artifact Boundary

### Included In The Golden Image

- OS baseline and runtime dependencies;
- Core service code and scripts;
- event schemas and validators;
- local storage adapter;
- local reference-resolution adapter;
- first-boot provisioning command;
- empty Core-zone initialization logic;
- export/import/checksum tools;
- local retrieval proof tools;
- optional service unit files;
- documentation needed for first boot.

### Excluded From The Golden Image

- owner data;
- hydrated Core Bundles;
- AWS account ids, bucket names, ARNs, or profile names;
- owner id / owner slug;
- owner profile;
- Circle runtime/messages;
- live Dash state;
- raw logs;
- credentials, OAuth files, API keys, tokens, MFA details, private keys;
- generated local keys.

## First-Boot Setup Model

On first boot, the owner runs or the VM starts:

```bash
pios-core-init --manifest /path/to/provisioning-manifest.yaml
```

The init flow should:

1. validate that the image has not already been owner-provisioned;
2. read a provisioning manifest;
3. create the owner-specific Core root;
4. create empty zone directories:
   - `originals/`
   - `events/`
   - `knowledge/`
   - `derived/`
   - `system/`
5. generate local encryption/signing keys or bind to the configured key
   provider;
6. write bootstrap system records;
7. start local services;
8. run an empty-Core health check.

## Validation Gates

Before calling an image "golden," validate:

1. Image hygiene:
   - no owner data;
  - no owner-specific identifiers;
   - no AWS identifiers;
   - no credentials or generated keys.
2. Empty first boot:
   - first-boot setup succeeds from a clean manifest;
   - five zones exist;
   - zones are empty except owner-specific bootstrap system records;
   - services start.
3. Synthetic local protected-write proof:
   - create one synthetic original and one synthetic event;
   - enforce atomic create/no-overwrite;
   - replay fails.
4. Core Bundle hydration proof:
   - hydrate a test bundle;
   - validate checksums;
   - resolve provider-specific refs locally;
   - verify event/manifest/original/detail traversal.
5. Derived rebuild proof:
   - rebuild at least one local index;
   - render/open at least one History/update detail artifact.
6. Export proof:
   - export the local Core into a Core Bundle;
   - validate checksums;
   - confirm host-specific paths do not leak into canonical records.
7. Repeatability:
   - boot a second fresh VM from the same image;
   - repeat first boot and proof steps.

## Current Proof Foundation

The first local proof passed on 2026-07-01:

`docs/runbooks/self-hosted-local-validation-proof-2026-07-01.md`

That proof validated local hydration, checksum validation, S3-style reference
resolution, event/manifest/original/detail traversal, History detail
renderability, and derived event-index rebuild against the refreshed 108-object
Core Bundle.

The first empty-init proof also passed on 2026-07-01:

`docs/runbooks/self-hosted-empty-init-proof-2026-07-01.md`

That proof validated `scripts/pios_core_init.py`: preview mode makes zero AWS
or network calls, first boot creates an empty five-zone Core root, writes
bootstrap records under `system/bootstrap/`, generates local development key
material outside the Core root, and fails closed when replayed against an
already initialized root.

The first data-empty image-root scaffold proof passed on 2026-07-01:

`docs/runbooks/self-hosted-image-root-scaffold-proof-2026-07-01.md`

That proof validated an allowlist-based image root with 11 files, zero hygiene
findings, no bundled owner data, no restore proofs, no generated keys, no real
AWS identifiers, and a generated `bin/pios-core-init` wrapper that successfully
initialized an empty Core root and failed closed on replay.

The first VM packaging scaffold proof also passed on 2026-07-01:

`docs/runbooks/self-hosted-vm-packaging-scaffold-proof-2026-07-01.md`

That proof produced a hygiene-passed data-empty install payload and Packer
scaffold. It also confirmed this machine does not currently have `packer`,
  QEMU, or `tart`, so the booted VM proof is blocked until a VM builder is
  installed or the scaffold is run on a VM-capable machine.

The VM-builder handoff scaffold was expanded on 2026-07-02:

`docs/runbooks/self-hosted-vm-builder-handoff-2026-07-02.md`

That handoff adds concrete Packer variables, example NoCloud/autoinstall seed
files, and an example local variable file. It is still not a booted VM proof.

The first direct QEMU boot proof also passed on 2026-07-02:

`docs/runbooks/self-hosted-qemu-boot-proof-2026-07-02.md`

That proof used an Ubuntu Noble arm64 cloud image, QEMU/HVF, a NoCloud seed, and
the data-empty image root. It booted a throwaway VM, ran `pios-core-init`, wrote
the empty five-zone Core structure, generated local development keys outside
the Core root, and produced a passed health-check record. It is not yet a
repeatable golden image candidate.

The QEMU repeat proof also passed on 2026-07-02:

`docs/runbooks/self-hosted-qemu-repeat-proof-2026-07-02.md`

That proof used `scripts/run_self_hosted_qemu_boot_proof.py` to rebuild the
data-empty image root, pass image hygiene, create a fresh NoCloud seed and
qcow2 overlay, boot QEMU again, and confirm the expected init and health-check
markers for a second synthetic owner identity. This validates repeatable
empty-Core VM initialization at the narrow QEMU/cloud-image level. It is still
not a cleaned distributable golden image.

The first QEMU/cloud-image candidate proof passed on 2026-07-02:

`docs/runbooks/self-hosted-qemu-image-candidate-proof-2026-07-02.md`

That proof used `scripts/build_self_hosted_qemu_image_candidate.py` to install
the data-empty Core payload into an Ubuntu Noble arm64 cloud-image overlay,
then booted a separate proof overlay from that candidate and ran
`pios-core-init` with a synthetic owner identity. This proves the candidate
image path can carry the Core Template payload and still support first-boot
owner initialization. The current candidate is a local qcow2 overlay with a
backing file, so it is not yet a standalone publishable artifact.

The first standalone QEMU image artifact proof passed on 2026-07-02:

`docs/runbooks/self-hosted-qemu-standalone-image-proof-2026-07-02.md`

That proof used `scripts/package_self_hosted_qemu_image_candidate.py` to convert
the backed candidate overlay into a standalone qcow2 artifact, verify that no
backing-file metadata remained, write a SHA-256 checksum and release-style
manifest, and boot a fresh proof overlay from the standalone image. First-boot
init passed from the standalone image. This is still a local proof artifact,
not a signed public release.

The current standalone artifact was refreshed after the Google gVNIC work. The
current standalone image checksum is:

```text
92f065e3f8a5d0db87254c88db13e031a2077138cf2f8bb4c78126eadd868de4
```

The first QEMU release package proof passed on 2026-07-02:

`docs/runbooks/self-hosted-qemu-release-package-proof-2026-07-02.md`

That proof used `scripts/validate_self_hosted_qemu_release_package.py` to
package the standalone qcow2, checksum, release manifest, and README into a
`.tar.zst`, extract it into a clean validation directory, recheck checksums,
confirm no backing-file metadata, and boot-prove the extracted image. This is
still local and unsigned, not a public GitHub release.

The first QEMU release signing proof passed on 2026-07-02:

`docs/runbooks/self-hosted-qemu-release-signing-proof-2026-07-02.md`

That proof used `scripts/sign_self_hosted_qemu_release_package.py` to write
`SHA256SUMS` for the package archive, package manifest, and validation result,
sign it with a local development Ed25519 release key, and verify the signature.
The production signing path was then proven for the v0.1.0-rc1 release
candidate on 2026-07-03:

`docs/runbooks/self-hosted-qemu-v0.1.0-rc1-release-candidate-proof-2026-07-03.md`

That proof rebuilt the image/package chain from the tagged source state,
validated package extraction and boot, signed `SHA256SUMS` with the production
release key, verified the signature, and generated a public release manifest.
It remains a local signed release candidate, not a published public release.
This proves signing mechanics only. The first public release-key custody model
is now decided as a two-step release, but production key creation and
publication remain open.

The first public release manifest proof passed on 2026-07-02:

`docs/runbooks/self-hosted-qemu-public-release-manifest-proof-2026-07-02.md`

That proof used `scripts/build_self_hosted_public_release_manifest.py` to
generate a machine-readable local-proof release manifest from the package
validation and signing proofs. The manifest records artifact names, checksums,
format, architecture, verification files, proof status, and install entrypoints.
Local QEMU usage documentation and provider-import planning guidance now exist
under `docs/install/`.

The first successful Google Cloud provider proof passed on 2026-07-02:

`docs/runbooks/google-cloud-import-proof-success-2026-07-02.md`

That proof used a Google-compatible image variant with offline `gve` driver
package injection. It imported the artifact into Google Cloud, booted an ARM64
`t2a-standard-1` VM with `GVNIC`, fetched the synthetic provisioning manifest
through Google metadata, ran `pios-core-init`, passed the five-zone health
check, and cleaned up all temporary Google resources. Google Cloud is now
experimental, not supported.

The current public handoff and release layout drafts are:

```text
docs/install/owner-agent-handoff.md
docs/runbooks/public-repository-and-release-layout.md
docs/decisions/production-release-key-custody.md
docs/runbooks/production-release-key-setup-checklist.md
docs/runbooks/production-release-signing-ceremony.md
docs/install/release-verification.md
docs/install/provider-readiness-matrix.md
docs/runbooks/local-machine-vm-setup-validation-plan.md
docs/runbooks/local-machine-vm-setup-validation-proof-2026-07-02.md
docs/runbooks/google-cloud-import-proof-plan.md
docs/runbooks/google-cloud-import-proof-success-2026-07-02.md
docs/runbooks/azure-import-proof-plan.md
docs/runbooks/external-vm-provider-proof-plan.md
```

## Recommended Build Path

1. Keep the self-hosted logic in this repo until the VM image boundary is clear.
2. Use `scripts/pios_core_init.py` as the current `pios-core-init` reference
   command for creating an empty local Core root from a provisioning manifest.
3. Use `scripts/build_self_hosted_image_root.py` to create the current
   data-empty image root.
4. Use `scripts/package_self_hosted_image_root.py` to package the image root as
   a data-empty install payload.
5. Use `image/packer/pios-core-self-hosted.pkr.hcl`, or an equivalent builder,
   on a VM-capable machine.
6. Add the concrete base-image wiring:
   - communicator settings such as SSH user/key/password and timeout;
   - unattended install input such as cloud-init/autoinstall seed files;
   - host accelerator choice (`hvf` on macOS, `kvm` on Linux);
   - QEMU binary choice (`qemu-system-x86_64` for amd64 or
     `qemu-system-aarch64` for arm64);
   - guest runtime dependencies: `python3`, `tar`, and `zstd`.
7. Build a minimal Ubuntu/Debian image first.
8. Run image hygiene checks.
9. Boot the image locally and run empty first boot.
10. Run the local proof tool against a non-production test bundle.
11. Treat direct QEMU/cloud-image customization as the first proven local
   candidate path while Packer remains blocked locally.
12. Use `scripts/package_self_hosted_qemu_image_candidate.py` to flatten/rebase
   the candidate and prove the standalone artifact.
13. Produce a cleaned candidate image with no temporary cloud-init seed traces,
   temporary builder user, generated proof keys, proof manifests, or proof owner
   identity.
14. Add release hardening:
   - signed checksums through `scripts/sign_self_hosted_qemu_release_package.py`;
   - public release manifest naming/versioning through
     `scripts/build_self_hosted_public_release_manifest.py`;
   - base-image provenance;
   - provider-specific import guidance.
15. Use `scripts/validate_self_hosted_qemu_release_package.py` to validate the
   package after extraction.
16. Boot the cleaned release candidate and rerun empty first boot plus repeatability
   proof before publishing it as a golden image.

## Not Yet Implemented

- production peecos release-signing key creation/publication;
- owner-facing local-machine VM wrapper/UX beyond the proof-level setup path;
- provider repeatability tests and non-Google provider import tests;
- deeper disk-image hygiene/inspection gate;
- hardened local key hierarchy;
- local protected-ingestion enforcement;
- local immutability/backup policy;
- self-hosted remediation/erasure mechanism;
- service supervisor configuration;
- repeat proof from the cleaned candidate image.
