# PIOS Core Start

Status: source text for `https://peecos.org/pios/start`

This page is designed for an owner to give to their own AI agent.

Agent: your job is to help the owner create or plan a PIOS Core setup. Ask the
owner only the questions needed for their chosen path. Stop at all approval
gates. Do not migrate owner data, start connector sync, deploy infrastructure,
or publish anything without explicit owner approval.

## Short Summary

PIOS Core is personal information infrastructure for one owner.

It gives the owner and their agents a durable place to preserve source material,
record canonical events, maintain structured knowledge, build retrieval
surfaces, and move between tools without losing context or ownership.

The owner owns the Core. Services and agents are delegated helpers.

## Choose One Deployment Option

Ask the owner:

```text
Do you want Core Managed AWS or Core Self-Hosted VM?
```

### Option A: Core Managed AWS

Use this if the owner wants to deploy an AWS-native Core into the owner's own
AWS environment using templates, manifests, and gated runbooks.

This is a template/self-setup path. It is not a hosted peecos account service.
A fully hosted account-and-use product is outside the open peecos framework
release and may be offered separately by a service provider.

Start from:

```text
docs/runbooks/new-owner-provisioning-template.md
docs/runbooks/aws-template-gate-sequence.md
docs/runbooks/aws-account-preflight.md
https://github.com/peecos/pios-core-aws-template
```

Do not deploy until the owner has approved:

- AWS account;
- AWS region;
- IAM operator/auditor principals;
- cost posture;
- provisioning manifest;
- synthesized deployment plan.

### Option B: Core Self-Hosted VM

Use this if the owner wants a VM-based Core that can run locally or on a
VM-capable cloud provider.

Start from:

```text
docs/install/self-hosted-qemu-local-vm.md
docs/install/self-hosted-cloud-provider-imports.md
docs/install/provider-import-proof-template.md
docs/install/provider-readiness-matrix.md
docs/runbooks/google-cloud-import-proof-plan.md
docs/runbooks/azure-import-proof-plan.md
docs/runbooks/external-vm-provider-proof-plan.md
docs/runbooks/local-machine-vm-setup-validation-plan.md
docs/runbooks/self-hosted-golden-vm-image-plan.md
```

Current status:

- local QEMU image path has proof artifacts;
- release package extraction and boot proof passed;
- first production release-key setup passed;
- a signed v0.1.0-rc1 prerelease is published at
  `https://github.com/peecos/pios-core-self-hosted/releases/tag/v0.1.0-rc1`;
- provider-specific imports are not yet marked supported;
- Google Cloud has an experimental proof, not a supported production path;
- Azure needs a fixed-VHD proof path;
- AWS owners should use the AWS template setup path unless they have a specific
  reason to request a separate self-hosted EC2 proof.

## Choose One Adoption Track

Ask the owner:

```text
Are you starting fresh, or transitioning an existing personal system?
```

### Track 1: New Owner Gradual Start

Use this if the owner does not already have a substantial custom personal
information system.

Start from:

```text
docs/runbooks/track-1-new-owner-gradual-start.md
```

Keep first intake narrow and owner-approved.

### Track 2: Existing Personal System Transition

Use this if the owner already has custom wikis, app folders, automation, agents,
dashboards, logs, data takeouts, or other personal information infrastructure.

Start from:

```text
docs/runbooks/track-2-existing-system-transition-template.md
```

Do not migrate by folder glob. First create a system map, classify source
disposition, then plan bounded functional-area batches.

## Required Owner Questions

Ask:

1. Which deployment option: AWS Managed or Self-Hosted VM?
2. Which adoption track: Track 1 clean start or Track 2 existing system?
3. What should the owner id and owner slug be?
4. What environment name should be used first?
5. What data sensitivity is allowed for the first proof?
6. Who can approve infrastructure, upload, migration, and decommissioning?
7. For AWS: account id, region, operator principal, auditor principal, cost
   guardrail, and MFA posture.
8. For self-hosted: local machine, VM host, or cloud VM provider; who controls
   the host; and whether provider import is already proven.

## Fail-Closed Rules

Stop if:

- sensitivity is unknown;
- credentials, secrets, private keys, health, finance, legal, or other guarded
  data may be involved;
- a command would deploy infrastructure;
- a command would upload owner data;
- a command would start connector sync;
- a command would start broad migration;
- a command would delete or decommission sources;
- a manifest sets authorization gates to true;
- a checksum or signature does not verify;
- an image has unexpected backing-file metadata;
- the chosen provider import path has not been tested or is only experimental.

Unknown sensitivity means exclude.

Unresolved blocking question means fail.

## What Not To Do

Do not:

- reuse another owner's account, manifests, bucket names, keys, or proof
  artifacts;
- import broad folders recursively;
- start email, chat, drive, photo, or calendar sync;
- migrate guarded data;
- delete existing sources;
- treat derived projections as source of truth;
- treat an unpublished local proof artifact as a public production release.

## Expected Outputs

For any setup attempt, produce:

```text
path decision
track decision
private owner manifest
preflight/verification record
owner approval record before action
post-action validation record
explicit list of what remains blocked
```

## Success Criteria

AWS Managed first setup succeeds when:

- preflight passes;
- synth/diff is reviewed;
- deploy is owner-approved;
- post-deploy validation passes;
- synthetic write/replay proof passes;
- no owner migration starts without separate approval.

Self-Hosted VM first setup succeeds when:

- package checksum verifies;
- signature verifies;
- image has no unexpected backing-file dependency;
- first boot initializes an owner-specific Core;
- all five zones exist;
- health check passes;
- connector sync, bundle hydration, broad migration, and source
  decommissioning remain false.

Track 2 first transition succeeds when:

- system map exists;
- source dispositions are explicit;
- batch is count-bounded and individually listed;
- sensitivity is explicit;
- peer technical screen, checklist result, and owner approval are distinct;
- retrieval proof passes;
- broad migration remains blocked.

## Documentation Boundary

peecos.org is the public orientation layer. It should explain what PIOS is, who
it is for, how to start, and where the approval gates are.

Full technical documentation, release verification instructions, runbooks,
proof records, and master-level specifications belong in the peecos GitHub
repositories.

Current references:

```text
docs/install/owner-agent-handoff.md
https://github.com/peecos/
https://github.com/peecos/pios-core-self-hosted
docs/runbooks/public-repository-and-release-layout.md
docs/runbooks/pios-2-public-productization-target.md
docs/decisions/production-release-key-custody.md
docs/runbooks/production-release-key-setup-checklist.md
docs/runbooks/production-release-signing-ceremony.md
docs/install/release-verification.md
docs/install/provider-readiness-matrix.md
docs/runbooks/google-cloud-import-proof-plan.md
docs/runbooks/azure-import-proof-plan.md
docs/runbooks/external-vm-provider-proof-plan.md
docs/runbooks/local-machine-vm-setup-validation-plan.md
```
