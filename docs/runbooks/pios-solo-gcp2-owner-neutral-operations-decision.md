# PIOS Solo: Next Owner Decision After The r4 GCP Proof

Status: decision package only. It creates no cloud resource, makes no cloud
call, and does not authorize Owner Bind.

## Decision Required

The next decision is **GCP-2 owner-neutral operations and retention approval**
for the already-proven, data-empty `pios-core-solo` GCP-1 baseline. It is not a
new persistent deployment and it is not an approval to bind the instance to an
owner or an application.

The owner must choose one of these outcomes:

1. retain the private, data-empty baseline for a named review period and begin
   only its owner-neutral operations-baseline planning; or
2. retire the retained baseline through a separately reviewed deletion plan.

The r4 isolated proof does not select either outcome. It proved that the r4
Starter artifact can be imported, privately booted, read through IAP/OS Login,
and fully cleaned up without changing retained resources.

## Recorded Retention Direction

On **July 31, 2026**, the owner directed this lane to continue with the
recommended retention path. For planning purposes, retain the existing
data-empty baseline through a review on **August 31, 2026**. This direction
authorizes only the zero-cloud-call GCP-2 operations plan; it does not itself
authorize a VM restart, snapshot, patch, IAM change, network change, or any
other cloud operation.

Before a cloud-changing operation, the owner must still record the current
provider cost estimate, the permitted operator identity, the specific action,
and its rollback/deletion behavior.

## What Retention Covers

If approved, the retained baseline is limited to the existing data-empty
private GCP-1 environment:

- the `pios-core-solo` private Shielded ARM64 C4A VM in `europe-north1-a`;
- its 40 GiB boot, 100 GiB Core, and 20 GiB key Hyperdisk Balanced disks;
- the current data-empty golden-image and recovery snapshot evidence;
- the private VPC/subnet, IAP/OS Login access posture, no-egress tags, and
  no-public-IP configuration; and
- bounded operational documentation for restart, private access, snapshot /
  restore, patch planning, evidence review, and eventual deletion.

It creates no new owner identity, Core identity, owner key, app identity,
endpoint, credential, source record, or user data. It does not convert a
snapshot into a fresh Core; snapshots remain recovery state only.

## Cost Boundary

Retention continues the actual Google Cloud charge for the existing C4A
instance, 160 GiB of Hyperdisk Balanced storage with its configured minimum
performance, retained image/snapshot storage, and any approved platform usage.
The project has an owner-approved **USD 200 monthly budget** with 50%, 80%, and
100% alerts. That budget is an alerting ceiling, not a price guarantee or an
automatic shutdown control.

Before the owner selects a retention period, record a current provider price
estimate for the existing region and resource inventory, the intended review
date, and the deletion approver. Do not infer a cost estimate from the budget
alone or enable new billing products to obtain it.

## Explicitly Not Authorized

This decision does **not** authorize:

- Owner Bind, Core initialization for an owner, owner policy, owner keys, or
  credentials;
- a Corebox bind, device enrollment, endpoint, Core API, connector, scheduler,
  app networking, background synchronization, or personal capture;
- any personal data, Core Bundle hydration, source migration, or source
  decommissioning;
- a public IP, public listener, DNS, TLS, Dash, passkeys, or public ingress;
- a service account, broad egress, telemetry agent, or external log export;
- a new provider image/import, a replacement VM, a new project, or a cloud
  resource change beyond the separately named operation the owner later
  approves; or
- release signing, publication, tagging, or a support-status change.

## Required Owner Record

The approval must name:

1. retain or retire outcome and, if retained, a review/expiry date;
2. billing owner and confirmation that the USD 200 monthly alert posture stays
   acceptable;
3. deployment/runtime/auditor/break-glass identities permitted to review the
   private baseline; and
4. whether the next bounded work is only GCP-2 operations evidence or a
   separate Owner Bind proposal.

Only after that record may a follow-up plan describe a specific retained
operation. Any operation that changes owner-specific state, exposes an
application, or connects Corebox requires its own named decision.

## Architecture Confirmation

The current PIOS Starter architecture preserves the companion boundary:

- the r4 artifact was proven data-empty and imports with all Core/API,
  connector, scheduler, hydration, migration, and source-decommission gates
  false;
- the generic source-primitives and adapter-template layers are local-only and
  do not include a Corebox binary, Inbox path, app identifier, endpoint, or
  transport; and
- Corebox remains an independently distributed unbound companion. Its later
  synthetic adapter must conform to the generic contract rather than make the
  image or retained Core depend on Corebox-specific state.

This confirmation does not certify a Corebox release or authorize the next
synthetic loop.
