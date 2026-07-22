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

## Open by Design

Use this path, study it, adapt it, operate it independently, or fork it. Code,
release tooling, and install materials use Apache-2.0. Independent
implementations and compatible services are welcome. Names and official
endorsement claims are handled separately only to prevent confusion.

See [OPENNESS.md](OPENNESS.md) for the plain-language guide and
[LICENSE](LICENSE) for the formal terms.

## License and Attribution

Code, schemas, scripts, release tooling, and install documentation in this
repository are licensed under the Apache License 2.0.

Copyright (c) 2026 Valto Loikkanen / peecos.

The broader PIOS 2.0 framework documentation is published separately under
CC BY 4.0 in `https://github.com/peecos/pios`.

The names `peecos`, `PIOS`, `PIOS Core`, `Cotton`, and associated logos or
marks are not licensed under Apache-2.0. See `TRADEMARKS.md`.
