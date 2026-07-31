# PIOS Solo GCP-2: Owner-Neutral Operations Plan

Status: planning document; it authorizes no cloud mutation. The first O1
read-only result is recorded in the VM lane and is passed for retention
planning with a dated, explicitly bounded provider-rate estimate.

## Purpose

This plan prepares the operations baseline for the retained, data-empty
`pios-core-solo` GCP-1 environment. It follows the passed isolated r4 proof
and the recorded retention direction through **August 31, 2026**.

It is intentionally owner-neutral. It keeps the Core data-empty and privately
operated while documenting how later bounded operations would be reviewed. It
does not start Owner Bind or a source/application integration.

## Baseline To Preserve

- private Shielded ARM64 `c4a-standard-2` VM in `europe-north1-a`;
- no external IP, no public listener, no service account/scopes, IAP/OS Login
  access only, and no-egress network posture;
- 40 GiB boot, 100 GiB Core, and 20 GiB key Hyperdisk Balanced disks;
- data-empty golden image and snapshot/restore evidence; and
- all Core API, connector, scheduler, hydration, migration, and source
  decommission gates false.

Corebox remains a separately distributed unbound companion. No Corebox binary,
endpoint, device enrollment, credential, queue, capture, receipt, or app
transport belongs in this operations baseline.

## GCP-2 Readiness Record Before Any Cloud Call

Record these values in a dated operations-evidence file before proposing even a
read-only review or a cloud-changing operation:

1. current VM/disk/image/snapshot inventory and private-network posture;
2. current provider price estimate for the retained inventory and confirmation
   that the USD 200 monthly alert budget remains acceptable;
3. named deployment, runtime, auditor, and break-glass identities, each using
   MFA/SSO and no shared key or app credential;
4. a review date no later than August 31, 2026, deletion approver, and owner
   exit/retirement path; and
5. the exact action, expected evidence, rollback, and cleanup boundary.

The record must explicitly state that a budget alert is not a spend cap and
that no automatic deletion occurs from a cost alert.

## Bounded Operations Sequence

Each numbered operation is a separate future decision. Complete neither an
earlier nor a later operation merely because this plan exists.

### O1 Checkpoint - 2026-07-31

The read-only VM-lane review confirmed the retained C4A VM, three Hyperdisk
Balanced disks, Shielded/no-public-IP/no-service-account posture, IAP-only
firewall/no-egress rules, current image/snapshot inventory, and a passed
private IAP/OS Login health read. It did not mutate any resource.

The check includes a dated provider-rate estimate for continuous C4A runtime,
160 GiB Hyperdisk Balanced capacity, and configured excess IOPS/throughput,
plus a 10% residual-storage/rounding contingency. The USD 200 budget alert
posture was verified by the final r4 proof earlier the same day, but remains an
alert threshold rather than a spend cap. Do not advance to O2, O3, or O4
without a specific owner confirmation.

### O1: Read-Only Baseline Review

Verify the existing resource inventory, Shielded settings, disk auto-delete
posture, IAP/OS Login access policy, private firewall/no-egress configuration,
and current billing estimate. Capture only bounded configuration and health
evidence; do not export guest logs or personal data.

**Exit evidence:** inventory matches the documented baseline, a private health
read is still possible, and cost/retention owners are recorded.

### O2: Private Restart And Health Procedure

Plan one owner-confirmed restart only after O1. Before the restart, record the
all-false manifest, current health result, rollback procedure, and evidence
location. After restart, use the private IAP/OS Login path to read the passed
five-zone health record.

**Exit evidence:** no public IP, no new identity/data/service, and health
returns to the same safe-disabled state.

### O2 Checkpoint - 2026-07-31

The owner authorized exactly one reset of retained VM `pios-core-solo` in
`europe-north1-a`. Pre-reset IAP/OS Login read a passed five-zone health record
and guest boot time `2026-07-30 22:10:55`. The reset returned successfully.
Post-reset inspection confirmed the same private IP, C4A shape, three retained
NVME disks, no service account, Shielded/deletion settings, and IAP/no-egress
tags. IAP/OS Login then read the same passed health record from guest boot time
`2026-07-31 20:36:21`.

No stop condition fired; no rollback, retry, configuration change, or further
cloud operation occurred. Compute Engine's `lastStartTimestamp` did not change
for `instances reset`, so the guest boot-time read is the restart evidence.
The detailed evidence is retained in the VM lane. O3 remains a separate owner
decision.

### O3: Recovery Reconfirmation

Review the existing recovery snapshots and schedule any new snapshot or
isolated restore test as a distinct owner-confirmed action. A restored clone is
recovery state, never a new independent Core.

**Exit evidence:** documented snapshot readers, retention, encryption posture,
isolated restore cleanup, and private health readback.

### O3 Checkpoint - 2026-07-31

The owner authorized one restore from the current OS Login boot/Core/key
snapshots. It created three temporary Hyperdisk Balanced disks and private
Shielded C4A VM `pios-core-o3-restore-20260731-r1`, at internal
`10.83.0.11`, with no external IP or service account and the existing
IAP/no-egress tags. IAP/OS Login read the preserved passed five-zone health
record at a new guest boot time.

The clone is recovery state, not a fresh Core: its health record retains the
snapshot's original `checked_at` time and no initializer was run. After health
readback, the temporary VM and all three restore disks were deleted. A first
disk-delete attempt correctly waited for the VM deletion to finish; final
inventory contains only the retained baseline VM and disks. O4 remains a
separate owner decision.

### O4: Patching And Maintenance Proposal

Prepare—not execute—a package inventory, maintenance window, rollback point,
restart check, and local evidence plan. Any patch that downloads packages,
changes the image, or changes disk/VM state needs a new owner approval and an
egress/privacy review.

**Exit evidence:** a reviewable proposed maintenance record only. No automatic
patching, guest telemetry, Cloud Ops agent, or log-export sink is enabled.

### O4 Checkpoint - 2026-08-01

Read-only inventory confirms Ubuntu 24.04.4 LTS, kernel `6.8.0-136-generic`,
no failed systemd units, 36 GiB free root capacity, active guest-agent service,
and working private OS Login. No update index was refreshed and no package was
changed.

The no-egress/no-public-IP baseline has no approved package-download path, so
ordinary APT update/upgrade is intentionally blocked. The O4 proposal requires
a separate owner decision for an exact signed package set, offline transport or
separately reviewed egress, pre-change snapshot, maintenance window, stop
rules, and post-patch health proof. It does not authorize an actual patch.

### O5: Retention Review Or Retirement

On or before August 31, 2026, the owner decides to renew the data-empty
retention period or executes a separately approved retirement/deletion plan.
Retirement must identify the VM, disks, images, snapshots, import objects, and
network resources to retain or delete; it must never infer that deleting a VM
also safely disposes of retained disks or snapshots.

## Non-Authorization

This plan does not authorize any cloud call, restart, snapshot, restore, patch,
IAM change, billing change, service account, endpoint, public ingress, egress
exception, telemetry, Corebox bind, device enrollment, Core API, connector,
scheduler, hydration, source migration, personal data, Owner Bind, release, or
publication. It only makes the decisions and evidence required before those
actions explicit.

## Required Future Confirmation Format

Every cloud-changing request must name the operation (`O2`, `O3`, or `O4`),
the exact target resources, cost estimate, operator, rollback, and evidence
destination. A generic “continue” is sufficient only for this planning work;
it is not a confirmation to mutate the retained baseline.
