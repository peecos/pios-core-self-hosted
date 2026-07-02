# Production Release Signing Ceremony

Status: draft procedure; production key setup passed; no release published

This runbook defines the human-controlled signing step for public PIOS/Core
release artifacts.

Decision record:

```text
docs/decisions/production-release-key-custody.md
```

Production key setup gate:

```text
docs/runbooks/production-release-key-setup-checklist.md
```

Prepared setup plan:

```text
docs/runbooks/production-release-key-setup-preparation-2026-07-03.md
```

Production key setup proof:

```text
docs/runbooks/production-release-key-setup-proof-2026-07-03.md
```

## Purpose

Public release artifacts must be verifiable by owners and owner-authorized
agents. The release package may be built and validated by scripts, but final
public checksum signing is a separate release ceremony.

## Required Inputs

Before signing, the release operator must have:

- clean source checkout;
- source tag;
- passed public split hygiene scan, if artifacts are being published from a
  public repository split;
- package archive;
- package manifest;
- validation result;
- public release manifest;
- successful extracted-package boot proof;
- `SHA256SUMS` generated for all public artifacts;
- production private signing key available through the chosen protected custody
  mechanism;
- public verification key ready for publication.

## Must Not Sign

Do not sign if:

- source is untagged;
- working tree is dirty;
- package validation failed;
- extracted-image boot proof failed;
- release manifest is missing or stale;
- checksums were generated from a different artifact set;
- private key is a development proof key;
- release notes omit known limitations;
- provider support is overstated;
- artifacts include owner data, private manifests, generated keys, or local
  proof-only state.

## Ceremony Steps

1. Confirm source tag and commit.
2. Confirm release package and manifest are from that tag.
3. Run package validation.
4. Confirm the extracted-image boot proof passed.
5. Generate `SHA256SUMS`.
6. Review `SHA256SUMS`.
7. Sign `SHA256SUMS` with the protected production release key.
8. Verify the signature locally with the public key.
9. Publish:
   - package archive;
   - public release manifest;
   - `SHA256SUMS`;
   - `SHA256SUMS.sig`;
   - public verification key or key fingerprint;
   - release notes;
   - verification instructions.
10. Record the release proof.

## Expected Public Verification Files

```text
SHA256SUMS
SHA256SUMS.sig
peecos-release-signing-key.pub
release-manifest.json
```

## Verification Command Shape

The exact commands depend on the final key format. For the current OpenSSL
Ed25519 proof style, verification shape is:

```bash
openssl pkeyutl \
  -verify \
  -rawin \
  -pubin \
  -inkey peecos-release-signing-key.pub \
  -in SHA256SUMS \
  -sigfile SHA256SUMS.sig
```

This command requires OpenSSL 3.x. On macOS, the system `openssl` is usually
LibreSSL and may not support `-rawin`; use an OpenSSL 3 installation such as
Homebrew `openssl@3` if the final release key keeps this verification format.

Then verify the package:

```bash
shasum -a 256 -c SHA256SUMS
```

On Linux, `sha256sum -c SHA256SUMS` is the usual equivalent.

## Release Proof Record

Each public release should record:

```yaml
release_id: <release-id>
version: <version>
source_tag: <tag>
source_commit: <commit>
package_archive: <name>
release_manifest: <name>
checksums_file: SHA256SUMS
signature_file: SHA256SUMS.sig
public_key_fingerprint: <fingerprint>
signature_verified_before_publish: true
package_validation_status: passed
boot_proof_status: passed
provider_support:
  local_qemu: supported | experimental
  google_cloud: unsupported | experimental | supported
  azure: unsupported | experimental | supported
  aws: unsupported | experimental | supported
known_boundaries:
  - <item>
```

## Current Boundary

The production release key exists and the synthetic setup ceremony passed. The
local proof key under `image-artifacts/` remains a development key and must not
be published as the production peecos release key. No public release has been
published yet; this ceremony is still required for each release artifact set.
