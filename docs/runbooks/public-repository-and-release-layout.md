# Public Repository And Release Layout

Status: draft layout; public split preview passed; not yet published under peecos
Created: 2026-07-02

This document defines the target public layout for PIOS/Core implementation
artifacts and documentation.

It supports the broader target in:

```text
docs/runbooks/pios-2-public-productization-target.md
```

## Goals

The public layout should let an owner or owner-authorized agent:

- understand the two deployment options;
- choose AWS Managed or Self-Hosted VM;
- find the correct runbooks;
- verify release artifacts;
- start setup without any private pilot context;
- avoid unsafe migration or connector actions.

The public split must be a curated copy, not a direct fork of the private pilot
repository. Private evidence records, pilot identifiers, local manifests, and
owner-specific migration scripts must stay out of public repositories.

## Candidate GitHub Repositories

Recommended first split:

```text
peecos/pios-core-aws
peecos/pios-core-self-hosted
peecos/pios-docs
```

### peecos/pios-core-aws

Purpose:

- CDK/CloudFormation source for Core Managed AWS;
- AWS runbooks;
- provisioning manifest example;
- guardrail tests;
- export/import/hydration tooling that is AWS-specific.

Do not include:

- real owner manifests;
- AWS account ids or principal ARNs;
- private evidence records;
- owner data;
- generated keys.

### peecos/pios-core-self-hosted

Purpose:

- self-hosted image-root builder;
- QEMU/Packer/provider image builders;
- first-boot init;
- local storage adapter;
- self-hosted release packaging and validation scripts;
- install docs;
- release manifests and checksums for public image releases.

Do not include:

- hydrated Core Bundles;
- generated VM artifacts unless attached as releases;
- local proof keys;
- owner data;
- private manifests.

### peecos/pios-docs

Purpose:

- peecos.org documentation source;
- owner/agent handoff page;
- decision guide between AWS and Self-Hosted;
- security, privacy, migration, and verification explanations;
- public links to release artifacts.

## Dedicated Agent Handoff URL

Target future URL:

```text
https://peecos.org/pios/start
```

Purpose:

An owner can give this one URL to their own agent. The agent should be able to:

1. explain the choices;
2. ask the owner which path and track to use;
3. create the needed private manifest;
4. run preflight checks;
5. stop at owner approval gates;
6. validate setup;
7. avoid broad migration or connector sync without explicit approval.

Current source draft:

```text
docs/install/owner-agent-handoff.md
```

## Release Artifact Layout

For a self-hosted QEMU release:

```text
releases/<version>/
  pios-core-self-hosted-qemu-arm64-<version>.tar.zst
  pios-core-self-hosted-qemu-arm64-<version>-release-manifest.json
  SHA256SUMS
  SHA256SUMS.sig
  RELEASE-NOTES.md
```

The public release manifest should include:

- release id;
- version;
- channel;
- source tag/commit;
- artifact names;
- package checksum;
- image checksum;
- architecture;
- image format;
- backing-file status;
- verification key;
- install docs URL;
- supported and untested providers;
- known boundaries.

Provider import proofs should use:

```text
docs/install/provider-readiness-matrix.md
docs/install/provider-import-proof-template.md
docs/runbooks/google-cloud-import-proof-plan.md
docs/runbooks/azure-import-proof-plan.md
docs/runbooks/external-vm-provider-proof-plan.md
docs/runbooks/local-machine-vm-setup-validation-plan.md
```

## Publication Gate

Do not publish a release until:

- source tag is created;
- public split hygiene scan passes;
- package validation passes;
- extracted-image boot proof passes;
- release manifest is generated;
- checksums are signed with production key;
- public verification key is published;
- install docs and verification commands are published;
- provider support matrix is explicit;
- no private identifiers or local proof keys are included.

Run the public split hygiene scanner against the curated public tree before
publishing:

```text
scripts/validate_public_split_hygiene.py --public-root <curated-public-root>
```

## Current Status

Local proofs exist for:

- QEMU boot;
- repeat QEMU boot;
- QEMU image candidate;
- standalone qcow2 artifact;
- release package extraction and boot;
- local development signing;
- public release manifest shape.

Still open:

- public repository split execution;
- public peecos.org page;
- owner-facing local-machine VM setup validation;
- Google Cloud repeatability and non-Google provider proof records;
- final public release publication process.

Current release-candidate proof:

```text
docs/runbooks/self-hosted-qemu-v0.1.0-rc1-release-candidate-proof-2026-07-03.md
```

Current public split preview:

```text
scripts/build_public_split_preview.py --force
```

The preview passed with zero hygiene findings, but it is not a published
repository.

Release signing and verification procedure drafts:

```text
docs/decisions/production-release-key-custody.md
docs/runbooks/production-release-key-setup-checklist.md
docs/runbooks/production-release-signing-ceremony.md
docs/install/release-verification.md
```
