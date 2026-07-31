# PIOS Solo GCP-2 O4: Zero-Change Maintenance Proposal

Status: preparation only. It does not authorize a package refresh, package
installation, egress, snapshot, restart, or any persistent-resource change.

## Current Readiness

The retained data-empty baseline has passed O1 private inventory/cost planning,
O2 restart, and O3 isolated snapshot restore. A read-only guest inventory on
August 1, 2026 reports Ubuntu 24.04.4 LTS, kernel `6.8.0-136-generic`, no
failed systemd units, 36 GiB free on the root filesystem, active Google guest
agent, and working IAP/OS Login integration.

The VM has no approved package-download path: it is private, has no external
IP, uses deny-all egress, and has no approved Cloud NAT or mirror. Do not use
an update check as a pretext to weaken that boundary.

## Future Patch Gate

Before any patch operation, the owner must approve an exact package objective,
signed dependency/checksum manifest, package transport, pre-change snapshot
set, maintenance window/operator, stop/rollback rules, and post-patch private
health evidence.

The preferred transport is a small, offline verified package bundle through
the existing private IAP/OS Login path. It remains a future mutation and needs
its own named decision. A temporary egress design, Cloud NAT, public IP,
unbounded APT update/upgrade, automatic patching, monitoring agent, or guest
telemetry is not authorized by this proposal.

## Stop Rules

Do not start a patch cycle if package provenance, checksums/signatures,
dependency closure, recovery snapshot, private health, target configuration,
or the maintenance window is missing. Any mismatch or failure stops the run;
do not automatically retry, broaden egress, change configuration, or recover
without another owner decision.

## Boundary

This is owner-neutral operations planning. It does not authorize Owner Bind,
Corebox connectivity, Core/API activation, app networking, credentials,
personal data, public ingress, release, or publication.
