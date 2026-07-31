# PIOS Starter B4: Projection, Audit, And Approval Primitives

## Purpose

This runbook verifies the owner-neutral B4 primitives carried by a future PIOS
Starter Disk Image. They establish the local data-model discipline for a later
owner-control surface without creating that surface, configuring an account,
or enabling any action against Core data.

The implementation is `scripts/pios_projection_approval_primitives.py`. It
uses B1 canonical integrity helpers and consumes B2 receipt shapes only as
read-only source references.

## Projection Boundary

`build_projection_record()` accepts a B2 receipt and separate projection
fields. It copies only a bounded source receipt binding:

- receipt ID and candidate digest;
- canonical event, original, and processing-manifest logical references; and
- a derived `core://derived/projections/...` reference.

It does not accept, retain, or modify source original bytes, source payload,
or source evidence. Projection fields and unknown extensions are independently
canonicalized and integrity-bound. A projection cannot modify the receipt from
which it was built; an edited projection fails validation.

## Generic Approval Boundary

`classify_action()` requires each generic action type to be explicitly
classified as `read_only` or `sensitive`. The included policy names only the
generic actions `view_projection`, `export_projection`, and
`change_projection_policy`; it enables none of them.

For an explicitly sensitive action, `begin_sensitive_action()` creates a
maximum five-minute challenge bound to:

- an exact action name and canonical parameters;
- a synthetic owner receipt-binding value;
- opaque session and CSRF binding identifiers; and
- exact issue and expiry timestamps.

`build_synthetic_approval_proof()` is a generated local test proof, not an
authentication method. The local harness verifies exact action, owner,
session, CSRF, and expiry bindings. It rejects expired or replayed proofs.
There is no browser flow, passkey, credential, identity-provider integration,
or action executor in this capability.

## Audit Boundary

`LocalImmutableAuditStore` writes a create-only canonical audit record before
the local harness returns an approved outcome. Audit records include derived
`core://system/approvals/...` and `core://system/audit/...` references, and
bind the approval to the exact action and proof. A synthetic audit-write
failure returns no approval and leaves the proof/action usable for a later
successful local retry.

The records are immutable and digest-bound, but not signed: a reusable image
cannot carry an owner signing key or signing authority. The selection of an
owner signing boundary, key custody, retention, and external audit destination
is deferred to Owner Bind and must remain absent from the image.

## Verification

Run from the repository root:

```sh
python3 -m unittest tests/test_pios_projection_approval_primitives.py
python3 -m unittest discover -s tests
python3 scripts/build_self_hosted_image_root.py \
  --output-dir /private/tmp/pios-starter-b4-image-root --run-hygiene
python3 scripts/validate_self_hosted_image_root.py \
  --image-root /private/tmp/pios-starter-b4-image-root
```

The focused tests prove that:

- a projection is separate from its B2 receipt source and cannot validate if
  its view fields are changed;
- actions require an explicit classification;
- a sensitive approval produces an immutable audit record before its outcome;
- expired and replayed proofs fail closed;
- a changed CSRF binding fails closed;
- audit-write failure does not consume an action/proof; and
- the module has no transport-client imports.

## Boundary

B4 does not create a Dash account, service, public/private listener, domain,
TLS certificate, WebAuthn relying-party identifier, passkey, recovery factor,
identity-provider client, session secret, endpoint, app credential, Core write
capability, cloud resource, owner configuration, or personal data.

B5 may define unconfigured service/authentication/recovery interfaces, but it
must retain the safe-disabled state until an explicit Owner Bind and later
edge/identity decision.
