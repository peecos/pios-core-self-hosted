# Production Release-Key Setup Checklist

Status: passed for first key; production release not yet published

This checklist defines the remaining work after choosing the first public
release custody model.

Decision record:

```text
docs/decisions/production-release-key-custody.md
```

Signing ceremony:

```text
docs/runbooks/production-release-signing-ceremony.md
```

## Goal

Create a protected production release-signing key and publish its public
verification material without turning local proof keys, owner data, or private
operator records into public release artifacts.

This checklist does not create the key by itself. It is the gate that must be
completed before the first public release package can be signed.

## Required Decisions

Before creating the key, record:

- release-key owner or owners;
- exact key mechanism;
- where the private key is generated;
- where the private key is stored;
- how signing access is authorized;
- backup/recovery policy;
- rotation policy;
- compromise/revocation notice process;
- canonical public-key publication location.

## Acceptable First Mechanisms

For first public releases, the key mechanism should be one of:

- hardware-backed local release key;
- encrypted offline software key on a controlled release machine;
- repository/release service key only after repository governance is mature.

The current local development signing key under `image-artifacts/` is not an
acceptable production mechanism.

## Prepared First Mechanism

The first setup plan has been prepared as an encrypted offline software-key
path controlled by the peecos release maintainer:

```text
docs/runbooks/production-release-key-setup-preparation-2026-07-03.md
```

That preparation made zero cloud calls and wrote no private key material. It is
not a production-key setup proof.

The setup proof passed on 2026-07-03:

```text
docs/runbooks/production-release-key-setup-proof-2026-07-03.md
```

## Setup Steps

1. Confirm the release-key owner or owners.
2. Choose the key mechanism.
3. Generate the production key in the chosen protected environment.
4. Record the public key fingerprint.
5. Store the private key according to the custody decision.
6. Create backup/recovery material, if the chosen mechanism supports it.
7. Publish the public verification key or fingerprint in the chosen canonical
   public location.
8. Add the same public key or fingerprint to release verification docs.
9. Run a dry-run signing ceremony on a synthetic `SHA256SUMS` file.
10. Verify the signature with the public key from the public location.
11. Record the setup proof.

## Must Not Do

- Do not reuse a local development proof key.
- Do not commit private key material.
- Do not include private key material in a VM image, release package, Core
  Bundle, owner manifest, or public repo.
- Do not publish a release until signature verification works from the public
  key location.
- Do not let provider support claims depend on an unsigned package.

## Public Verification Material

The first public release should make these available:

```text
peecos-release-signing-key.pub
peecos-release-signing-key-fingerprint.txt
SHA256SUMS
SHA256SUMS.sig
release-manifest.json
docs/install/release-verification.md
```

The public key may live on peecos.org, GitHub, or both. If both are used, one
location must be declared canonical and the other must match it.

## Setup Proof Record

Record the setup as:

```yaml
release_key_setup:
  status: passed
  setup_time: <timestamp>
  key_mechanism: <hardware_token | encrypted_offline_software_key | release_service>
  key_owner: <name-or-role>
  public_key_location: <url-or-path>
  public_key_fingerprint: <fingerprint>
  private_key_stored_in_public_repo: false
  private_key_stored_in_image: false
  synthetic_signature_verified: true
  recovery_policy_recorded: true
  rotation_policy_recorded: true
  revocation_policy_recorded: true
```

## Current Boundary

The first production release key exists and the synthetic setup ceremony
passed. Public release remains blocked until the release package is regenerated
from the intended source state, signed in the production signing ceremony,
verified, and published through the public release gate.
