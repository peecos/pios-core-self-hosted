# Self-Hosted Golden VM Image Plan

Status: signed v0.1.0-rc1 local release candidate exists; Google Cloud experimental; provider support not complete

This runbook defines the target for a data-empty Core Self-Hosted VM image that
can be installed by a new owner and later hydrated with an optional Core Bundle.
It supports the public peecos goal of providing a data-empty VM setup path that
can be validated locally and adapted to VM-capable providers.

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

Detailed proof evidence is retained in private operator records. The public
repository keeps the reusable plan, scripts, install docs, release package, and
public verification material.

The current proof foundation includes:

- local hydration and reference-resolution proof;
- empty first-boot initialization proof;
- data-empty image-root hygiene proof;
- VM packaging scaffold proof;
- direct QEMU boot proof;
- QEMU repeatability proof;
- QEMU image-candidate and standalone-image proof;
- release package extraction and boot proof;
- development signing proof;
- production signing proof for `v0.1.0-rc1`;
- Google Cloud experimental import, boot, init, health-check, and cleanup
  proof.

The current standalone artifact was refreshed after the Google gVNIC work. The
current standalone image checksum is:

```text
92f065e3f8a5d0db87254c88db13e031a2077138cf2f8bb4c78126eadd868de4
```

The published `v0.1.0-rc1` prerelease is a signed public prerelease, not a
supported production release. Google Cloud is experimental, not supported.

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
docs/runbooks/google-cloud-import-proof-plan.md
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
