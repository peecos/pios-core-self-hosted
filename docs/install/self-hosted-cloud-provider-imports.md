# PIOS Core Self-Hosted Cloud Provider Imports

Status: planning guidance; Google Cloud experimental

This document defines the expected shape of future cloud-provider import
guidance for the PIOS Core Self-Hosted golden image.

Use this proof template for each provider:

```text
docs/install/provider-import-proof-template.md
```

Use this matrix to decide the next provider proof:

```text
docs/install/provider-readiness-matrix.md
```

The current proven artifact is:

```text
format: qcow2
architecture: arm64
role: data-empty Core Template
```

It has been locally packaged, extracted, checksum-verified, inspected for no
backing file, and boot-proven with QEMU. A Google-compatible variant has also
passed one owner-approved Google Cloud import, ARM64 VM boot, metadata-provided
first initialization, five-zone health check, and cleanup proof. Azure and
external VM providers have not yet been tested. AWS self-hosted VM import is
intentionally not a current validation target because Core Managed AWS is the
AWS-native path.

## Common Provider Requirements

Each provider import path should document:

- supported CPU architecture;
- supported disk image format;
- whether conversion is required;
- where the image is uploaded before import;
- how checksums are verified before import;
- how the imported image is named and versioned;
- whether cloud-init or equivalent first-boot metadata is supported;
- required network/firewall defaults;
- expected VM size for first boot;
- how the owner supplies the provisioning manifest;
- how first-boot logs are inspected;
- how to delete failed test imports.

## Required PIOS Validation After Import

For each provider, the first proof should:

1. Import the image without owner data.
2. Launch one VM from the imported image.
3. Supply a synthetic self-hosted provisioning manifest.
4. Run `pios-core-init`.
5. Confirm all five Core zones exist.
6. Confirm `system/bootstrap/health-check.json` reports `status: passed`.
7. Confirm no connector sync, bundle hydration, broad migration, or source
   decommission action occurred.
8. Destroy the test VM and any temporary import resources.

## Provider Sections To Add

The following sections are placeholders until each provider path is tested.

### Google Cloud

Status: experimental; one owner-approved proof passed.

Proof plan:

```text
docs/runbooks/google-cloud-import-proof-plan.md
```

Detailed Google Cloud proof evidence is retained in private operator records.

Completed:

- convert standalone qcow2 to raw and compress as `tar.gz`;
- create a temporary Cloud Storage staging path;
- create a custom image with `ARM64`;
- boot one `t2a-standard-1` VM with no external IP;
- create the custom image and VM with explicit `GVNIC` configuration;
- install and start the PIOS Google metadata first-boot service;
- inject the required Google `gve` driver path for the proof image variant;
- fetch the synthetic provisioning manifest through the Google metadata path;
- run `pios-core-init`;
- pass the five-zone Core health check;
- clean up the VM, custom image, staged archive, and bucket.

Remaining work:

- repeat the proof enough times to treat it as a supported path;
- complete cost/security and documentation review;
- publish a production-signed release artifact before owner-facing public use.

### Azure

Status: planned after fixed-VHD conversion planning; not tested.

Proof plan:

```text
docs/runbooks/azure-import-proof-plan.md
```

Expected work:

- convert to fixed VHD;
- confirm Azure Linux preparation requirements;
- define storage account/container staging path;
- define managed image or gallery image flow;
- define test VM boot command;
- record a provider-specific proof runbook.

### AWS

Status: intentionally out of current self-hosted validation scope.

For AWS, the preferred path is Core Managed AWS, not the self-hosted VM image.
Do not spend validation effort on EC2 VM import unless a future owner has a
specific reason to run the self-hosted image on AWS instead of using Core
Managed AWS.

The self-hosted AWS path is retained as an out-of-scope decision. Use the AWS
template repository for AWS owners unless a future owner has a specific reason
to validate self-hosted EC2.

### External VM Providers

Status: planned for owner/community validation, not current internal proof.

Expected work:

- define minimum VM features: arm64 or x86_64 support, cloud-init support,
  attached disk support, console log access;
- document provider-specific image upload/import constraints;
- record a proof runbook for each provider before marking it experimental or
  supported.

Examples include regional VM providers such as UpCloud, Hetzner, and similar
hosts. These should use the same proof template and evidence standard, but they
do not need to be validated internally before the first public package track can
continue.

## Boundary

No provider should be listed as supported until an import, boot, init, health
check, and cleanup proof has been recorded.

After a first successful proof, mark the provider `experimental` unless
repeatability, cost/security review, and documentation review have also passed.
