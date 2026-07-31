# PIOS Starter r4 Isolated Google Cloud Proof Package

## Purpose

This package prepares a later, named owner-approved **temporary** Google Cloud
proof for the local PIOS Starter r4 artifact. It is not the persistent
`pios-core-solo` deployment path and must never mutate its retained VM, disks,
images, snapshots, VPC, or subnet.

The package has three scripts:

- `plan_pios_starter_r4_google_cloud_proof.py`: local zero-cloud-call plan.
- `build_pios_starter_r4_google_cloud_import_artifact.py`: local QCOW2 to
  `disk.raw` plus oldgnu `tar.gz` artifact conversion.
- `run_pios_starter_r4_google_cloud_proof.py`: preview by default; future
  execution only with `--confirm-r4-gcp-proof-execution`.

## Exact Local Artifact Contract

The package accepts only:

```text
image-artifacts/pios-starter-disk-image-20260731-r4/
  pios-starter-disk-image-20260731-r4.qcow2

SHA-256
f04ae641e213d14aa802f5a2c06907616d4642f69836bc133a30059b55470c19
```

It validates the r4 release manifest and local evidence-readiness record before
converting. The generated oldgnu archive must contain only `disk.raw`; raw and
archive SHA-256 files and a manifest bind both back to the exact r4 QCOW2
digest.

## Temporary Resource Model

All eventual cloud resources derive from a required `r4-*` proof ID and begin
with `pios-r4proof-`:

- staging bucket and archive object;
- imported image;
- temporary 40 GiB boot, 100 GiB Core, and 20 GiB key disks;
- isolated proof VM; and
- local result/evidence directory.

The preview ID ends in `-preview` and is rejected for execution. This prevents
a preview resource name from becoming a live proof name. Persistent
`pios-core-solo` names are neither accepted nor generated.

## Planned Private Baseline

The runner’s generated commands use:

- `europe-north1-a`, ARM64 `c4a-standard-2`;
- `hyperdisk-balanced` for all three temporary disks;
- imported image guest OS features `GVNIC,UEFI_COMPATIBLE`;
- Shielded Secure Boot, vTPM, and integrity monitoring;
- existing private VPC/subnet with gVNIC and no external IP;
- no service account and no scopes;
- cloud-init `user-data`, not a custom metadata-manifest key; and
- a generated synthetic first-boot manifest with Core API, connector,
  scheduler, hydration, migration, and source-decommission gates all false.

No command creates, changes, or exposes a public endpoint.

## Execution Gate

The runner is preview-only unless the owner later supplies one explicit
confirmation flag:

```text
--confirm-r4-gcp-proof-execution
```

Execution also requires a non-preview unique proof ID, a named billing account
and budget, positive owner-approved monthly and proof cost ceilings, refreshed
authentication, a separately verified operator-permission record, and
successful preflight. The runner does **not** treat readable IAM policy as
evidence of effective access: inherited, conditional, group, and custom-role
permissions can differ from visible project bindings.

The operator record must conform to
`schemas/manifests/pios_starter_r4_gcp_operator_permission_record.schema.json`,
bind the exact project and gcloud account, be unexpired, identify independent
verification evidence, and prove the effective create/delete/read permissions
for the temporary bucket, object, image, disks, and VM, plus IAP tunnel and OS
Login access. A missing, mismatched, expired, or incomplete record blocks
execution before any cloud command.

Preflight then parses—not merely lists—the active account, exact project,
project-to-billing-account linkage, and named budget. The budget must scope to
the exact project (project ID or number), use USD, have a positive amount no
greater than the approved monthly ceiling, contain 50%, 80%, and 100% threshold
alerts, and have an enabled alert-delivery path. It also checks C4A availability
and regional quota, private VPC/subnet, IAP TCP/22 firewall readiness,
IAM-policy visibility as supporting owner-review evidence only, and
temporary-resource name absence.

After boot, a future execution requires both serial markers and IAP/OS Login
readback of a passed five-zone health JSON. Cleanup always attempts deletion of
the temporary VM, three disks, image, archive object, and staging bucket—even
if creation, boot, serial evidence, or readback fails. If preflight fails
before all temporary names have been proved absent, no temporary resource can
have been created and the runner deliberately makes no guessed-name deletion
attempt; it records `not_required_preflight_failed` instead. Its result records
failure and cleanup evidence rather than silently stopping.

## Local Validation

```sh
python3 scripts/plan_pios_starter_r4_google_cloud_proof.py \
  --output-dir image-artifacts/pios-starter-r4-gcp-proof-plan \
  --proof-id r4-20260731-preview

python3 scripts/build_pios_starter_r4_google_cloud_import_artifact.py \
  --plan image-artifacts/pios-starter-r4-gcp-proof-plan/r4-20260731-preview-plan.json \
  --output-dir image-artifacts/pios-starter-r4-google-cloud-import-artifact-20260731

python3 scripts/run_pios_starter_r4_google_cloud_proof.py \
  --artifact-manifest image-artifacts/pios-starter-r4-google-cloud-import-artifact-20260731/r4-google-cloud-import-artifact-manifest.json \
  --output-dir image-artifacts/pios-starter-r4-gcp-proof-preview-20260731 \
  --proof-id r4-20260731-preview
```

The last command must report `preview_only` and `cloud_calls: 0`.

For a later, separately authorized execution, the owner must supply the exact
budget display name and an independently produced permission record with
`--operator-permission-record`. This runbook intentionally provides no command
that creates a passed record or performs a cloud proof.

## Boundary

Do not execute the confirmation flag without a later named owner approval.
This package does not authorize a GCP import, VM boot, deployment, Owner Bind,
public release, signing, tagging, endpoint, app networking, or personal data.
