# Azure Import Proof Plan

Status: planned; no Azure resources created
Created: 2026-07-02

This runbook defines the planned Azure proof path for the PIOS Core
Self-Hosted golden image.

It does not authorize Azure resource creation, billing exposure, image upload,
VM launch, or provider support claims.

Use the general provider proof template:

```text
docs/install/provider-import-proof-template.md
```

Read the provider readiness matrix first:

```text
docs/install/provider-readiness-matrix.md
```

## Current Artifact Gap

The current proven artifact is:

```yaml
format: qcow2
architecture: arm64
```

Azure upload/import flows require a prepared VHD path. The Azure proof should
therefore begin with an explicit provider-artifact conversion plan rather than
trying to upload the current qcow2 directly.

## Required Owner Approval

Before running this proof, the owner must approve:

- Azure subscription;
- resource group;
- region;
- temporary storage account/container or managed-disk upload flow;
- VM size;
- network posture;
- cost ceiling;
- cleanup plan;
- synthetic owner identity;
- no owner-data upload.

## Planned Artifact Conversion

The first Azure proof should not mutate the canonical package. It should create
a temporary provider-specific import artifact:

```text
standalone qcow2
  -> fixed VHD
  -> Azure managed disk or image
```

The conversion proof must record:

```yaml
source_qcow2: <path>
source_qcow2_sha256: <sha256>
fixed_vhd: <path>
fixed_vhd_sha256: <sha256>
conversion_tool: <tool-and-version>
vhd_size_alignment_checked: true
azure_linux_preparation_checked: true
```

## Planned Azure Flow

The first proof should follow this shape:

1. Verify the release package and image checksums locally.
2. Convert the standalone qcow2 image to fixed VHD.
3. Confirm Azure Linux image preparation requirements are satisfied.
4. Confirm VHD size/alignment requirements.
5. Upload the VHD through an owner-approved Azure upload path.
6. Create a managed disk, managed image, or gallery image according to the
   selected Azure flow.
7. Launch one VM from the imported image with synthetic provisioning metadata.
8. Run or trigger `pios-core-init`.
9. Confirm all five Core zones exist.
10. Confirm `system/bootstrap/health-check.json` reports `status: passed`.
11. Confirm authorization gates remain false:
    - `hydrate_bundle`;
    - `connector_sync`;
    - `broad_migration`;
    - `source_decommission`.
12. Capture boot diagnostics or serial console logs needed for proof.
13. Delete the VM, disk/image, storage objects, and temporary resources unless
    owner explicitly approves keeping them for repeat proof.

## Evidence Record

Record the proof as:

```yaml
provider: azure
provider_region: <region>
proof_date: <YYYY-MM-DD>
release_id: <release-id>
package_sha256: <sha256>
source_image_sha256: <sha256>
fixed_vhd_sha256: <sha256>
resource_group: <redacted-or-synthetic-proof-name>
managed_disk_or_image_id: <id>
vm_instance_id: <id>
network_exposure: none | ssh_restricted | other
first_boot_status: passed | failed
health_check_status: passed | failed
cleanup_status: complete | incomplete
supported_status_after_proof: unsupported | experimental
```

The public repo should not retain private subscription IDs, tenant IDs, billing
IDs, or sensitive operator identifiers. Store private evidence in operator
records when needed.

## Fail Conditions

Fail the proof if:

- checksum verification fails;
- conversion changes image semantics unexpectedly;
- VHD requirements are not satisfied;
- Azure import/upload fails;
- VM does not boot;
- first-boot manifest is not applied;
- `pios-core-init` fails;
- health check fails;
- any authorization gate is true unexpectedly;
- network exposure is broader than approved;
- cleanup fails;
- any owner data is included.

## Current Boundary

No Azure commands have been run from this plan. Provider status remains
`unsupported` until an owner-approved proof is completed and reviewed.
