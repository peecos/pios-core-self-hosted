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

### O3: Recovery Reconfirmation

Review the existing recovery snapshots and schedule any new snapshot or
isolated restore test as a distinct owner-confirmed action. A restored clone is
recovery state, never a new independent Core.

**Exit evidence:** documented snapshot readers, retention, encryption posture,
isolated restore cleanup, and private health readback.

### O4: Patching And Maintenance Proposal

Prepare—not execute—a package inventory, maintenance window, rollback point,
restart check, and local evidence plan. Any patch that downloads packages,
changes the image, or changes disk/VM state needs a new owner approval and an
egress/privacy review.

**Exit evidence:** a reviewable proposed maintenance record only. No automatic
patching, guest telemetry, Cloud Ops agent, or log-export sink is enabled.

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
