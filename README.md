# PIOS Core Self-Hosted

This repository contains the public PIOS Core Self-Hosted VM path. It provides
data-empty setup, packaging, validation, install, and verification materials
only.

The current signed release candidate is `v0.1.0-rc1` for `arm64` QEMU/qcow2
images, suitable for Apple Silicon and arm64 VM proof paths. An `x86_64`
release is not yet published.

Start here:

1. Read `docs/install/owner-agent-handoff.md`.
2. Review `docs/install/release-verification.md`.
3. Check provider status in `docs/install/provider-readiness-matrix.md`.
4. For local use, follow `docs/install/self-hosted-qemu-local-vm.md`.

Boundaries:

- no owner data is included;
- no private manifests are included;
- no private key material is included;
- provider support is limited to what the readiness matrix explicitly states;
- AWS owners should normally use `https://github.com/peecos/pios-core-aws-template`.
