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
