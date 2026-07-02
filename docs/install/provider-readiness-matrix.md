# Self-Hosted Provider Readiness Matrix

Status: planning matrix; Google Cloud experimental; no cloud provider marked supported
Checked: 2026-07-02

This matrix records how close the current self-hosted QEMU image artifact is to
each target provider.

It does not authorize provider resource creation. Each provider still needs an
owner-approved proof run using:

```text
docs/install/provider-import-proof-template.md
```

## Current Artifact

```yaml
format: qcow2
architecture: arm64
role: data-empty Core Template
state: signed public prerelease
```

The artifact has been locally package-verified and boot-proven. A
Google-compatible arm64 variant has also passed one owner-approved Google Cloud
import, boot, first-init, health-check, and cleanup proof.

## Matrix

| Provider | Current status | Artifact gap | First proof path |
| --- | --- | --- | --- |
| Local QEMU | Proof-level local setup passed; signed prerelease exists | Repeatability and support documentation still needed before supported status | Use local VM install guide and release verification flow |
| Google Cloud | Experimental: one owner-approved import, boot, metadata init, health check, and cleanup proof passed | Requires repeatability, cost/security review, and documentation review before support | Follow `docs/runbooks/google-cloud-import-proof-plan.md`; detailed proof evidence is retained privately |
| Azure | Planned after provider-artifact conversion plan | Convert to fixed VHD; confirm Azure Linux requirements, cloud-init/agent behavior, Hyper-V generation, and 1 MB alignment | Follow `docs/runbooks/azure-import-proof-plan.md` after owner approval |
| AWS EC2 self-hosted | Intentionally not a validation target for now | AWS is covered by the separate Core Managed AWS path, which is already the mature AWS-native option | Use Core Managed AWS for AWS owners; revisit self-hosted EC2 only if a concrete owner need appears |
| External VM providers | Planned for owner/community validation, not this immediate proof run | Varies by accepted image format, cloud-init support, console access, cleanup model; examples include regional providers such as UpCloud, Hetzner, and similar VM hosts | Use the provider proof template per provider; record evidence before claiming experimental support |

## Source Notes

Google Cloud manual import documentation describes creating a raw disk image,
compressing it as `tar.gz`, uploading it to Cloud Storage, creating a custom
image, then booting a VM from that imported image.

Azure documentation describes fixed VHD requirements, Azure Linux preparation
requirements, direct upload to a managed disk, writeable SAS access, and AzCopy
upload.

AWS self-hosted VM import is intentionally out of scope for the current
validation track because Core Managed AWS is the AWS-native deployment option.
If a future owner specifically needs self-hosted EC2, treat it as a new proof
path rather than a blocker for the generic self-hosted VM track.

Official source URLs are intentionally included here because provider import
rules change:

```text
https://cloud.google.com/compute/docs/import/import-existing-image
https://learn.microsoft.com/en-us/azure/virtual-machines/linux/create-upload-generic
https://learn.microsoft.com/en-us/azure/virtual-machines/linux/disks-upload-vhd-to-managed-disk-cli
https://docs.aws.amazon.com/vm-import/latest/userguide/prerequisites.html
```

## Provider Plans

```text
docs/runbooks/google-cloud-import-proof-plan.md
docs/runbooks/azure-import-proof-plan.md
docs/runbooks/external-vm-provider-proof-plan.md
```

## Provider Support Rule

Do not mark a provider `experimental` or `supported` from this matrix alone.

`experimental` requires at least one owner-approved provider proof with:

- package verification;
- image import;
- VM boot;
- synthetic first-boot init;
- Core zone health check;
- no owner data;
- cleanup proof.

`supported` requires repeatability, cost/security review, documentation review,
and a public release package signed with the production release key.
