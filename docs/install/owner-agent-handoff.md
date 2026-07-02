# PIOS Core Owner-Agent Handoff

Status: source handoff text for peecos.org and GitHub install documentation

This page is written for an owner to give to their own AI agent.

Goal: help the agent start a PIOS Core setup for the owner, choose the correct
path, ask only necessary owner-specific questions, and avoid unsafe actions.

## What PIOS Core Is

PIOS Core is personal information infrastructure for one owner.

It preserves source material, records canonical events, maintains structured
knowledge and derived retrieval surfaces, and gives agents a governed place to
organize and retrieve the owner's information.

The owner owns the Core. Services and agents are delegated helpers.

## Choose A Deployment Path

Ask the owner to choose one:

```text
A. Core Managed AWS
B. Core Self-Hosted VM
```

### A. Core Managed AWS

Use this path if the owner wants to deploy an AWS-native Core into the owner's
own AWS environment using templates, manifests, and gated runbooks.

This is a template/self-setup path. It is not a hosted peecos account service.
A fully hosted account-and-use product is outside the open peecos framework
release and may be offered separately by a service provider.

Start with:

```text
https://github.com/peecos/pios-core-aws-template/blob/main/docs/runbooks/new-owner-provisioning-template.md
https://github.com/peecos/pios-core-aws-template/blob/main/docs/runbooks/aws-template-gate-sequence.md
https://github.com/peecos/pios-core-aws-template/blob/main/docs/runbooks/aws-account-preflight.md
https://github.com/peecos/pios-core-aws-template
```

Do not create AWS resources until the owner has approved the account, region,
cost posture, manifest, and synthesized deployment plan.

### B. Core Self-Hosted VM

Use this path if the owner wants a VM-based Core that can run locally or on a
VM-capable provider.

Start with:

```text
docs/install/self-hosted-qemu-local-vm.md
docs/install/self-hosted-cloud-provider-imports.md
docs/install/provider-readiness-matrix.md
docs/runbooks/google-cloud-import-proof-plan.md
docs/runbooks/azure-import-proof-plan.md
docs/runbooks/external-vm-provider-proof-plan.md
docs/runbooks/local-machine-vm-setup-validation-plan.md
docs/runbooks/self-hosted-golden-vm-image-plan.md
```

The current QEMU package path is available as a signed public prerelease. It is
a release-candidate setup path, not a claim that every VM provider is supported.

## Choose An Adoption Track

Ask the owner to choose one:

```text
Track 1: New owner gradual start
Track 2: Existing personal system transition
```

### Track 1: New Owner Gradual Start

Use this if the owner does not already have a substantial custom personal
information system.

Start with:

```text
https://github.com/peecos/pios-core-aws-template/blob/main/docs/runbooks/track-1-new-owner-gradual-start.md
```

The first real owner intake must remain narrow, owner-approved, and
normal-sensitivity unless separate guarded handling is explicitly approved.

### Track 2: Existing Personal System Transition

Use this if the owner already has a functioning personal information system,
custom wikis, app folders, automation, agents, dashboards, logs, or migration
targets.

Start with:

```text
https://github.com/peecos/pios-core-aws-template/blob/main/docs/runbooks/track-2-existing-system-transition-template.md
```

Do not migrate by folder glob. Build a system map first, classify source
disposition, then plan bounded functional-area batches.

## Questions To Ask The Owner

Ask these before doing setup work:

1. Which deployment path do you want: AWS Managed or Self-Hosted VM?
2. Which adoption track fits you: Track 1 clean start or Track 2 existing
   system transition?
3. What owner id and owner slug should identify this Core?
4. What environment name should be used first: local, pilot, staging, or
   production?
5. What data sensitivity is allowed for the first proof? Default:
   normal-sensitivity synthetic or narrow owner-approved data only.
6. Who is allowed to approve infrastructure, uploads, migration, and
   decommissioning?
7. For AWS: what account id, region, operator principal, auditor principal,
   and cost guardrail should be used?
8. For self-hosted: where will the VM run first, and who controls the host?

## Files To Create

For AWS Managed:

```text
private provisioning manifest
preflight record
synth/diff review record
owner approval record
post-deploy validation record
```

For Self-Hosted VM:

```text
self-hosted provisioning manifest
package verification record
first-boot init record
health-check record
```

For Track 2 migration:

```text
system map
source disposition table
functional-area plan
bounded batch manifest
peer technical screen
checklist result
owner approval record
retrieval proof
```

## Fail-Closed Rules

Stop and ask the owner if:

- identity, account, region, or host is unclear;
- sensitivity is unknown;
- a file may contain credentials, secrets, private keys, health, finance,
  legal, or other guarded material;
- the action would upload owner data;
- the action would enable connector sync;
- the action would start broad migration;
- the action would decommission or delete a source;
- a manifest asks for authorization gates to be true;
- a proof fails;
- expected checksums do not match;
- an image has unexpected backing-file metadata;
- the chosen provider import path has not been tested or is only experimental.

Unknown sensitivity means exclude.

Unresolved blocking question means fail.

## What Not To Do Without Owner Approval

Do not:

- deploy infrastructure;
- upload owner data;
- import broad folders or use recursive globs;
- start email/chat/photo/drive connector sync;
- migrate guarded data;
- create public shares;
- delete or decommission existing sources;
- treat derived projections as source of truth;
- reuse another owner's manifest, account id, bucket name, key, or signing
  material;
- treat an unpublished local proof package as a public production release.

## Success Criteria

For AWS Managed first setup:

- preflight account/region check passes;
- synth/diff reviewed;
- deploy approved and completed;
- post-deploy validation passes;
- synthetic protected write/replay proof passes;
- no owner migration starts without a separate gate.

For Self-Hosted VM first setup:

- package checksum verifies;
- image has no backing-file dependency unless documented;
- first boot runs with owner-specific manifest;
- five Core zones exist;
- `system/bootstrap/health-check.json` reports `status: passed`;
- no connector sync, bundle hydration, broad migration, or decommissioning
  occurs.

For Track 2 first migration:

- system map exists;
- source dispositions are explicit;
- batch is count-bounded and individually listed;
- normal/sensitive/guarded classification is explicit;
- peer screen, checklist result, and owner approval are distinct;
- retrieval proof passes after upload;
- broad migration remains blocked.

## Current Public-Release Boundary

The QEMU self-hosted path currently has:

- repeatable QEMU boot;
- image candidate;
- standalone qcow2 artifact;
- release package extraction and boot;
- production signature verification;
- public-facing manifest shape;
- signed public prerelease `v0.1.0-rc1` in
  `https://github.com/peecos/pios-core-self-hosted`.

Remaining before supported production release:

- provider-specific import proofs;
- broader installer hardening;
- supported-path documentation for each validated provider.

Release-key setup is governed by:

```text
docs/decisions/production-release-key-custody.md
docs/runbooks/production-release-key-setup-checklist.md
docs/runbooks/production-release-signing-ceremony.md
docs/install/release-verification.md
```

Provider import status is governed by:

```text
docs/install/provider-readiness-matrix.md
docs/install/provider-import-proof-template.md
docs/runbooks/google-cloud-import-proof-plan.md
docs/runbooks/azure-import-proof-plan.md
docs/runbooks/external-vm-provider-proof-plan.md
docs/runbooks/local-machine-vm-setup-validation-plan.md
```
