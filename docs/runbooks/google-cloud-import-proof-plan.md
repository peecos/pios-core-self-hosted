# Google Cloud Import Proof Plan

Status: successful proof complete; Google Cloud experimental
Created: 2026-07-02

This runbook defines the first planned cloud-provider import proof for the PIOS
Core Self-Hosted golden image path.

It does not authorize Google Cloud resource creation, billing exposure, image
upload, VM launch, or provider support claims.

Use the general provider proof template:

```text
docs/install/provider-import-proof-template.md
```

Read the provider readiness matrix first:

```text
docs/install/provider-readiness-matrix.md
```

## Why Google Cloud First

The current proven artifact is an arm64 qcow2 QEMU image. Google Cloud has a
documented custom-image import path based on raw disk images compressed as
`tar.gz` and uploaded to Cloud Storage.

That makes Google Cloud a reasonable first cloud-provider proof candidate, but
not automatically supported.

The first owner-approved attempt is recorded in private operator evidence.

That attempt proved archive upload, custom image creation, ARM64 VM boot, and
cleanup. It failed before Core initialization because the imported image did not
consume the Google Cloud metadata/user-data path; cloud-init reported
`Datasource DataSourceNone`.

The gVNIC follow-up attempt is recorded in private operator evidence.

That attempt added a PIOS Google metadata first-boot adapter, explicit
`GVNIC` image and VM flags, and a generic DHCP baseline. The VM booted and the
metadata-init service started, but the guest still had no non-loopback network
interface. Serial output showed the Google NIC as PCI device `[1ae0:0042]`, and
local build inspection showed the generic Ubuntu arm64 image lacks the `gve`
kernel module.

The first successful proof is recorded in private operator evidence.

That proof used a Google-compatible image variant with offline gVNIC driver
package injection. The VM imported, booted, fetched the synthetic provisioning
manifest through the Google metadata path, ran `pios-core-init`, passed the
five-zone health check, and cleaned up all temporary Google resources.

## Required Owner Approval

Before running this proof, the owner must approve:

- Google Cloud project;
- billing exposure;
- region/zone;
- temporary Cloud Storage bucket or staging path;
- image name;
- VM machine type;
- firewall/network posture;
- cleanup plan;
- maximum expected cost;
- synthetic owner identity;
- no owner-data upload.

## Planned Artifact Conversion

The first proof should not mutate the canonical package. It should create a
temporary provider-specific import artifact:

```text
standalone qcow2
  -> disk.raw
  -> oldgnu tar.gz archive for Google Cloud custom image import
```

The zero-cloud-call planning script is:

```text
scripts/plan_google_cloud_import_proof.py
```

It emits planned local conversion commands and planned Google Cloud command
shapes without contacting Google Cloud or creating resources.

The local provider-artifact builder is:

```text
scripts/build_google_cloud_import_artifact.py
```

It converts the standalone qcow2 proof image into the Google Cloud import
shape, verifies that the archive contains only `disk.raw`, writes checksums,
and records `cloud_calls: 0`.

The first local artifact proof is recorded in private operator evidence.

The guarded import proof runner is:

```text
scripts/run_google_cloud_import_proof.py
```

Without `--confirm-gcp-resource-creation`, it must emit a preview with
`cloud_calls: 0`. With confirmation, it creates the temporary bucket, uploads
the archive, creates the custom image, boots one synthetic proof VM, reads the
serial output, and then attempts cleanup of the VM, image, object, and bucket.

The conversion proof must record:

```yaml
source_qcow2: <path>
source_qcow2_sha256: <sha256>
raw_image: <path>
raw_image_sha256: <sha256>
tar_gz_archive: <path>
tar_gz_sha256: <sha256>
conversion_tool: <tool-and-version>
```

## Planned Google Cloud Flow

The first proof should follow this shape:

1. Run the zero-cloud-call planner.
2. Review owner approvals, cost ceiling, region, zone, machine type, staging
   bucket, and cleanup plan.
3. Verify the release package and image checksums locally.
4. Run the local provider-artifact builder.
5. Run the guarded proof runner in preview mode.
6. Upload the archive to an owner-approved Cloud Storage staging path.
7. Create a Compute Engine custom image from the uploaded archive with
   `--architecture arm64` and `GVNIC` guest OS feature.
8. Launch one VM from the custom image with synthetic provisioning metadata,
   no external IP, and a `GVNIC` network interface.
9. Confirm the guest exposes a non-loopback network interface and can reach the
   Google metadata endpoint.
10. Run or trigger `pios-core-init` through the Google metadata first-boot path.
11. Confirm all five Core zones exist.
12. Confirm `system/bootstrap/health-check.json` reports `status: passed`.
13. Confirm authorization gates remain false:
    - `hydrate_bundle`;
    - `connector_sync`;
    - `broad_migration`;
    - `source_decommission`.
14. Capture serial console or boot logs needed for proof.
15. Delete the VM, custom image, and staging object unless owner explicitly
    approves keeping them for repeat proof.

## Evidence Record

Record the proof as:

```yaml
provider: google_cloud
provider_region: <region-zone>
proof_date: <YYYY-MM-DD>
release_id: <release-id>
package_sha256: <sha256>
source_image_sha256: <sha256>
provider_archive_sha256: <sha256>
cloud_storage_staging_uri: <redacted-or-synthetic-proof-uri>
custom_image_id: <id>
vm_instance_id: <id>
network_exposure: none | ssh_restricted | other
first_boot_status: passed | failed
health_check_status: passed | failed
cleanup_status: complete | incomplete
supported_status_after_proof: unsupported | experimental
```

The public repo should not retain private project IDs, billing IDs, or sensitive
operator identifiers. Store private evidence in operator records when needed.

## Fail Conditions

Fail the proof if:

- checksum verification fails;
- conversion changes image semantics unexpectedly;
- Google Cloud import fails;
- VM does not boot;
- guest network interface is missing;
- metadata endpoint is unreachable;
- first-boot manifest is not applied;
- `pios-core-init` fails;
- health check fails;
- any authorization gate is true unexpectedly;
- network exposure is broader than approved;
- cleanup fails;
- any owner data is included.

## Current Boundary

Google Cloud provider status is now `experimental`, not `supported`.

The successful proof closes the first gVNIC driver/bootstrap gap. Before Google
Cloud can be marked `supported`, the path still needs repeatability, cost and
security review, documentation review, production release signing, and public
release publication.
