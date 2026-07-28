# Google Cloud Persistent One-Owner Core: GCP-0 Deployment Review

Status: review-only; zero Google Cloud calls; no deployment authorization.

The Primary Mac QEMU path is the local build, regression, diagnostics, and
portability-test environment. This runbook prepares—not deploys—a retained,
data-empty, one-owner Google Compute Engine Core.

## Decision Gate

Every value marked owner decision must be recorded before GCP-1. A missing
value blocks deployment; do not substitute another project, billing account,
identity, region, or credential.

## Source And Image Gate

- Source commit: `d05ece7` or a later owner-reviewed successor.
- Re-run local data-empty candidate build, first-boot proof, and package/image
  checksum verification before import.
- Record QCOW2, raw-import archive, and custom-image SHA-256 values.
- Import only a new data-empty artifact. Do not repurpose a proof image as a
  retained Core image without fresh local proof and review.
- Delete the staging import object after custom-image verification unless the
  owner explicitly approves retention.

## Proposed GCP-1 Shape

| Area | Review baseline | Owner decision |
| --- | --- | --- |
| Project/billing | Dedicated one-owner project and named billing account | Project ID, billing owner, charge approval |
| Region/zone | ARM-capable zone; all zonal disks co-located | Region, zone, residency rationale |
| Machine | ARM64 T2A; review begins at `t2a-standard-2` | Exact machine type and quota |
| Boot disk | 30–50 GiB persistent boot disk, no owner data | Disk type and size |
| Core disk | Separate 100 GiB persistent balanced disk | Disk type, size, mount path |
| Keys | Separate persistent key disk or hardened provider | Key custody design |
| Encryption | GCP-1 data-empty proof may use Google-managed encryption only if accepted; CMEK is preferred before owner data | CMEK owner, recovery, rotation |
| Labels | `pios_role=self_hosted_core`, `owner_scope=one_owner`, `environment=gcp1_data_empty` | Cost/owner label values |

Current machine availability and quota are deployment-time checks after owner
authorization, not assumptions made by this review.

## Proposed Owner-Reviewed Baseline (2026-07-28)

The owner selected `pios-core-solo` as the intended project ID for a dedicated
one-owner Core. It is a proposed identifier only: do not create or reserve it
until GCP-1 is explicitly authorized and availability is confirmed.

| Decision | Proposed baseline |
| --- | --- |
| Project | ID `pios-core-solo`; display name `PIOS Core Solo`; dedicated one-owner project |
| Billing | Valto owner approval; planning ceiling EUR 200/month in the billing-account currency; alerts at 50%, 80%, and 100% |
| Location | Primary `europe-north1-a`; `europe-west4` is the import-proof fallback only if ARM quota/availability blocks the primary |
| Compute | `t2a-standard-2`, ARM64, standard VM, automatic restart and host-maintenance migration |
| VM protection | Shielded VM: Secure Boot, vTPM, integrity monitoring; deletion protection enabled |
| Storage | 40 GiB `pd-balanced` boot disk; 100 GiB `pd-balanced` Core-data disk; 20 GiB separate key-custody disk; Core/key disks retained on instance deletion |
| Access | No external IP; OS Login plus IAP TCP forwarding for the named owner operator; no default public SSH rule |
| Service identity | No broad default service account; attach only a later purpose-scoped identity after review |
| Encryption | Google-managed encryption for data-empty GCP-1 only; CMEK/key-custody design is mandatory before owner data or GCP-2 |
| Backup | One manual post-health snapshot, then an isolated restore test; no automatic owner-data backup policy until GCP-2 |
| Monitoring | Platform status and bounded serial evidence only; no guest telemetry/export agent until a reviewed egress/privacy decision |

## Which Decisions Can Change Later

- **Do not treat as changeable:** the project ID is a lifetime identifier. The
  project can be deleted and recreated, but the desired identifier must be
  correct before creation.
- **Change with migration/review:** region/zone, ARM architecture, image
  lineage, and encryption/CMEK posture. Plan a replacement VM/disk and
  restore/export path rather than an in-place switch.
- **Change with downtime or compatibility checks:** machine type. Do not assume
  a T2A change is a routine in-place resize; use a planned stop/restart or
  replacement path.
- **Grow, not shrink:** Persistent Disk capacity can be increased, but disk
  reduction requires a migration/rebuild approach.
- **Configurable later:** budgets/alerts, snapshots, firewall rules, IAP/OS
  Login policy, and external IP assignment. A public IP remains absent in
  GCP-1; if needed later, use a separately authorized application-edge design.

## Network And Access

- No external IP, public Core/API endpoint, load balancer, DNS record, app
  listener, or public firewall rule.
- Dedicated VPC/subnet or owner-approved private network; ingress and egress
  deny by default.
- Do not grant broad VM outbound access. Package, monitoring, and backup egress
  require separate reviewed allowlists.
- Leading operator-access option: IAP TCP forwarding to the internal IP with
  OS Login and MFA/SSO, enabled only after owner approval of identities and the
  required private firewall rule.
- Serial console is break-glass evidence only, controlled by a separately named
  MFA identity; it is never a data plane.

This is a **GCP-1 stage rule**, not a permanent claim that a public address can
never be relevant. The Joensuu Susicorn MVP is a separate public application
runtime and demonstrates a legitimate later need for web ingress. If a PIOS
application or owner-approved public surface later needs inbound Internet
traffic, design a separate application/edge ingress path with its own identity,
authorization, firewall, TLS, logging, and incident controls. Do not attach a
public IP or public listener directly to the Core VM merely for convenience.

Name before GCP-1: billing owner, deployment operator, runtime operator,
auditor, and break-glass recovery identity. Do not use AWS identities, generic
keys, app credentials, or shared human accounts.

## First Boot: Data-Empty Only

The GCP metadata manifest must be synthetic/data-empty and set all of these to
`false`: `hydrate_bundle`, `connector_sync`, `broad_migration`,
`source_decommission`, `start_core_api`, `start_connectors`, and
`start_scheduler`.

Success evidence is five empty zones, keys outside the Core root, passed health,
and no public endpoint. The metadata adapter may use GCP metadata only after
guest Google Compute Engine identity detection; it must not create app network
access.

## Backup, Operations, Recovery, And Cost

- Approve snapshot location, encryption, retention, and readers before a
  post-initialization snapshot. First restore is an isolated no-public-IP test
  VM, then deletion.
- GCP-1 uses platform status and bounded serial evidence. Guest log export,
  Cloud Ops agents, or external alerts require a later GCP-2 egress/privacy
  decision.
- Patching is manual and owner-approved in GCP-1; define maintenance window,
  rollback snapshot, restart test, and audit record before GCP-2.
- Set a billing budget and alert thresholds before retained resources. Owner
  supplies the numeric monthly ceiling; evaluate eligible spend-cap controls
  separately if automatic pausing is desired.
- Pre-approve actions for boot failure, access loss, disk/key recovery, cost
  breach, and owner exit/deletion. Never delete data automatically merely from
  a cost alert.

## Duplication And Recovery Model

Complete this while the Core is still data-empty, before any owner-data
migration.

1. **Golden data-empty template:** retain the reviewed ARM64 custom image and
   synthetic first-boot manifest. Create a new VM from this path when an
   independent Core is needed; it receives a fresh instance identity and fresh
   Core/key initialization.
2. **Snapshot/restore clone:** snapshot the boot, Core-data, and key-custody
   disks after a successful health check. Restore the disks into an isolated
   no-public-IP replacement VM when the goal is recovery or an exact clone.
   This intentionally carries the existing Core state and keys.
3. **Post-health proof:** immediately after GCP-1 health passes, retain the
   golden image and create one snapshot set. Run one isolated restore test,
   verify health, then delete the test VM/disks.

New instances do not automatically inherit instance name, internal/external IP,
IAM/service identity, firewall attachment, or operator-access settings. Apply
those from the approved deployment configuration. Do not use a snapshot clone
as an independent owner Core without fresh identity and key initialization.

## GCP-1 Preflight Checklist

- [ ] Project ID and organization/folder boundary
- [ ] Billing owner, charge approval, monthly ceiling, alerts
- [ ] Region/zone, ARM machine, quota, residency rationale
- [ ] Named MFA/SSO deployment, runtime, auditor, and break-glass identities
- [ ] Private VPC/subnet, no-public-IP, IAP/OS Login decision
- [ ] Image/import checksums, image name, retention/deletion plan
- [ ] Disk, encryption/CMEK, key-custody, snapshot/restore design
- [ ] Monitoring, patching, incident, recovery, and deletion plan
- [ ] Synthetic first-boot manifest with all gates false
- [ ] Explicit owner authorization for GCP-1 billing and resources

## Related Material

- `docs/runbooks/google-cloud-import-proof-plan.md`: experimental cleanup proof
- `docs/install/provider-readiness-matrix.md`: Google Cloud remains experimental
- `scripts/plan_google_cloud_import_proof.py`: legacy proof preview only
