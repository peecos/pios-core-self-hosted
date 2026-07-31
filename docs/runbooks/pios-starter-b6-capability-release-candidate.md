# PIOS Starter B6: Capability-Bearing Local Release Candidate

## Purpose

This runbook builds and proves a new local PIOS Starter Disk Image after
reviewed B1-B5 capabilities have changed the future image payload. It creates
only a data-empty, unsigned, unpublished local QCOW2 candidate. It does not
perform Owner Bind, cloud import, signing, publication, or a source connection.

## Required Local Inputs

- ARM64 cloud base image at `image-build/qemu-cloud/`.
- Staged offline gVNIC packages at `image-build/google-gvnic-debs/`.
- Staged offline Google guest-agent/OS Login packages at
  `image-build/google-guest-agent-debs/`.
- Apple Silicon QEMU/HVF and ARM64 EDK2 firmware.

Do not download inputs during this workflow. The candidate builder uses
restricted QEMU user networking and no outbound guest access. During offline
package installation it temporarily uses Debian `policy-rc.d` so guest-agent
services cannot start inside the local image-build VM; the guard is removed
before the image is finalized.

## B6 Workflow

1. Run the full local suite.
2. Build a candidate using the staged offline dependency directories.
3. Flatten and checksum the candidate into a standalone QCOW2; require its
   package boot proof to pass.
4. Run fresh-image hygiene against a separate disposable overlay.
5. Run `prove_pios_starter_capability_lifecycle.py` against another disposable
   overlay. It must prove empty state, Core health, generated B3 source
   receipt/export, B4 projection/approval/audit, and B5 safe-disabled health.
6. Run the residue inspection against another disposable overlay, rejecting
   the candidate build's synthetic token and known temporary paths.
7. Run `validate_pios_starter_disk_image_evidence.py` to bind package health,
   hygiene, and residue evidence to the same checksum. Record the lifecycle
   proof alongside it in the B6 evidence note.

All proof overlays, seed ISOs, EDK2 vars copies, serial logs, and result JSON
records remain outside the QCOW2/Core root. A failed proof never mutates the
source candidate or standalone image.

## B1-B5 Capability Inventory

- B1 canonical JSON, source IDs/idempotency, integrity, extension, logical
  reference, provenance, and immutable evidence primitives.
- B2 local candidate lifecycle, receipt, refusal/retry/revocation, export, and
  original readback contract.
- B3 harmless original-byte and structured-evidence templates with local
  outbox and receipt-ledger semantics.
- B4 receipt-separated projection, immutable audit, classification, action
  challenge, expiry/replay/CSRF binding, and approval interface primitives.
- B5 strict safe-disabled owner-control schema, authentication/WebAuthn/
  recovery interfaces, and private-Core/public-edge non-deployment template.

## Required Release Record

The B6 evidence must state the exact QCOW2 SHA-256, release manifest, payload
source revision, included file inventory, local test count, package proof,
fresh hygiene proof, capability lifecycle proof, residue inspection, evidence
readiness result, known limitations, and Owner Bind prerequisites.

The existing local provider path is evidence only: inclusion of the staged
gVNIC and guest-agent/OS Login packages does not prove a new candidate has
been imported or booted on Google Cloud. A separate, owner-approved provider
proof is required before any new cloud image use.

## Boundary

The local candidate must remain data-empty, unsigned, unpublished, and without
an owner identity, domain, passkey, credential, key, policy, service account,
endpoint, public ingress, app networking, Core Bundle hydration, connector,
scheduler, Core API, or personal data.
