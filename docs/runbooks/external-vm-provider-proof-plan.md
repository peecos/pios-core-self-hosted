# External VM Provider Proof Plan

Status: generic plan; no external-provider resources created
Created: 2026-07-02

This runbook defines the generic proof shape for non-big-cloud VM providers
such as UpCloud, Hetzner, and similar regional or independent VM hosts.

It does not authorize provider account creation, billing exposure, image upload,
VM launch, owner-data upload, or provider support claims.

Use the general provider proof template:

```text
docs/install/provider-import-proof-template.md
```

Read the provider readiness matrix first:

```text
docs/install/provider-readiness-matrix.md
```

## Purpose

The self-hosted golden image should be portable beyond the major clouds. This
plan keeps that validation path explicit without requiring this project to test
every provider internally.

An external provider should only become `experimental` after an
owner-approved or community-reviewed proof shows that the provider can import
or boot the data-empty Core Template, run first initialization, pass the
five-zone health check, and clean up temporary resources.

## Provider Intake Questions

Before attempting a proof, record:

- provider name;
- account owner;
- region/data-center;
- supported CPU architectures;
- accepted image formats;
- whether custom image upload/import is available;
- whether cloud-init, NoCloud, metadata, or an equivalent first-boot mechanism
  is available;
- serial console or boot-log access;
- networking defaults and firewall posture;
- cost ceiling;
- cleanup process;
- whether the proof uses a provider-native image import, local VM upload, or
  manual attached-disk workflow.

## Minimum Technical Requirements

The first proof should require:

- no owner data in the image;
- package checksum verification before upload/import;
- VM boot from the imported or attached image;
- synthetic provisioning manifest only;
- `pios-core-init` executed during first boot or immediately after boot;
- all five Core zones created;
- `system/bootstrap/health-check.json` reports `status: passed`;
- all authorization gates remain false:
  - `hydrate_bundle`;
  - `connector_sync`;
  - `broad_migration`;
  - `source_decommission`;
- cleanup proof for VM, image, disk, bucket/object, or other temporary
  resources.

## Evidence Record

Record each external-provider proof as:

```yaml
provider: <provider-name>
provider_category: external_vm
provider_region: <region-or-datacenter>
proof_date: <YYYY-MM-DD>
release_id: <release-id>
package_sha256: <sha256>
source_image_sha256: <sha256>
provider_artifact_sha256: <sha256-or-null>
image_import_method: custom_image_import | uploaded_disk | local_vm | other
vm_instance_id: <id-or-redacted>
network_exposure: none | ssh_restricted | other
first_boot_status: passed | failed
health_check_status: passed | failed
cleanup_status: complete | incomplete
supported_status_after_proof: unsupported | experimental
```

The public repo should not retain private account IDs, billing IDs, operator
identifiers, credentials, or provider tokens. Store sensitive evidence in
operator records when needed.

## Fail Conditions

Fail the proof if:

- checksum verification fails;
- provider import/upload changes image semantics unexpectedly;
- the VM does not boot;
- first-boot manifest cannot be supplied;
- `pios-core-init` fails;
- health check fails;
- any authorization gate is true unexpectedly;
- network exposure is broader than approved;
- cleanup fails;
- owner data is included.

## Current Boundary

No external VM provider proof has been run from this plan. External providers
remain unverified until a provider-specific proof record exists.

The first public self-hosted package track can continue without internally
validating every external provider, as long as provider support claims remain
explicit and evidence-based.

