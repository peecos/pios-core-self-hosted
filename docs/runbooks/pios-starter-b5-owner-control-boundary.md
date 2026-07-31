# PIOS Starter B5: Owner-Control Integration Boundary

## Purpose

This runbook verifies the owner-neutral B5 capability carried by a future
PIOS Starter Disk Image. It provides only an unconfigured configuration shape,
interface boundaries, and a non-deployment topology template for a later
owner-control surface.

It does not create a service, listener, account, browser flow, passkey,
recovery factor, identity-provider configuration, domain, certificate, edge
deployment, or Core action capability.

## Included Neutral Capability

`schemas/configs/pios_owner_control_boundary.schema.json` describes the only
configuration accepted within the reusable image:

- service and listener are `false`;
- authentication, WebAuthn, and recovery interfaces are `unconfigured`;
- Owner Bind is explicitly `missing`; and
- the private Core has no public IP and no public edge is deployed.

`scripts/pios_owner_control_boundary.py` exposes:

- `AuthenticationAdapter`, `WebAuthnCapabilityBoundary`, and `RecoveryFlow`
  protocol interfaces for later per-owner implementations;
- unconfigured implementations that return safe-disabled health and reject
  authorization, step-up, and recovery operations with `OwnerBindRequired`;
- `boundary_health()` to prove the data-empty safe-disabled state; and
- `private_core_public_edge_template()` to describe the later topology without
  selecting any address, domain, route, credential, or deployment.

The module is included in the image-root allowlist. The schema is included by
the existing complete `schemas/` directory allowlist.

## Owner Bind Boundary

The neutral module intentionally names only generic categories that a future
Owner Bind must supply: stable HTTPS origin, authentication adapter
configuration, relying-party binding, recovery configuration, session/CSRF
secret material, and edge-to-private-Core access policy.

It contains none of their values. `validate_neutral_configuration()` rejects
any configuration that differs from the exact all-disabled neutral shape. A
separate future Owner Bind contract must select values and lifecycle policy; it
must not alter the reusable image in place.

## Verification

Run from the repository root:

```sh
python3 -m unittest tests/test_pios_owner_control_boundary.py
python3 -m unittest discover -s tests
python3 scripts/build_self_hosted_image_root.py \
  --output-dir /private/tmp/pios-starter-b5-image-root --run-hygiene
python3 scripts/validate_self_hosted_image_root.py \
  --image-root /private/tmp/pios-starter-b5-image-root
```

The focused tests prove the default configuration is passed but
`disabled_unconfigured`, all listener/edge/public-IP flags are false, Owner
Bind values and service enablement are rejected, all three unconfigured
interfaces cannot perform their operations, the topology remains a
non-deployment template, and no transport or service-runtime imports exist.

## Boundary

B5 does not authorize a public edge, a public IP, Core API exposure,
application networking, passkey enrollment, owner account, user signup,
identity provider, recovery factor, action approval, owner data, cloud
resource, signing, or release publication.

B6 may package reviewed B1-B5 capabilities into a new data-empty release
candidate and its independent hygiene/evidence set. It must still not perform
Owner Bind or introduce any of the missing values named above.
