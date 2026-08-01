# PIOS Starter v0.1.0 Release Readiness

Status: published stable release on 2026-08-01

## Release Promise

`PIOS Starter v0.1.0` will be the first stable public release of the
data-empty, self-hosted PIOS Starter for arm64 QEMU. It lets an independent
owner or owner-authorized agent verify and boot a neutral Core template before
the separately governed Owner Bind transition.

It will not claim a hosted service, an owner-bound Core, a default endpoint,
device enrollment, app networking, Corebox synchronization, personal-data
intake, broad migration, connector operation, or support for unverified
providers.

## Scope

Included:

- signed data-empty arm64 QCOW2/release package;
- embedded offline `docs/starter/` orientation bundle;
- local QEMU installation and verification path;
- generic Core health, portability, source, projection, and safe-disabled
  owner-control primitives; and
- optional Corebox companion documentation with no embedded Corebox binary or
  automatic connection.

Excluded:

- Owner Bind implementation or any owner-specific material;
- Corebox transport, device credentials, or synchronization;
- a public Core API, hosted account flow, or managed service; and
- any Google Cloud support claim beyond the explicit provider-readiness status.

C3 local companion transport is useful follow-on work but is not a release
prerequisite for this neutral Starter scope.

The image-root allowlist and its regression coverage exclude all C3 socket,
transport, orchestration, and execution tooling. C3 source may remain in the
development repository as dormant conformance work, but it is not a runtime
capability or public availability claim of `v0.1.0`.

## Stable Release Gate

The release operator must complete and record each item against the same
immutable source tag and generated artifact set:

1. Freeze the release revision and create the intended `v0.1.0` source tag.
2. Rebuild the image from that revision so the embedded Starter documentation
   bundle and runtime have one source identity.
3. Pass the full repository suite, image-root hygiene scan, package boot proof,
   fresh-image hygiene proof, residue inspection, B6 capability lifecycle
   proof, and evidence-readiness binding.
4. Create the public package, public release manifest, release notes, and
   `SHA256SUMS` from that exact artifact set.
5. Run an independent clean-machine verification: signature, package checksum,
   extracted-image checksum, standalone QCOW2 inspection, and local boot.
6. Run the production signing ceremony using the protected production release
   key, then verify the resulting signature with the public key before upload.
7. Run the curated-public-tree hygiene scan and review the GitHub release and
   peecos.org availability copy for private identifiers and scope overclaims.
8. Publish the GitHub stable release and the peecos.org availability page,
   linking the release notes and verification guide. Record the release proof.

Any failure or source/artifact mismatch stops the release. Rebuild rather than
patching a candidate artifact in place.

## Availability Copy

After publication, public pages may say:

> PIOS Starter v0.1.0 is available as a signed, data-empty self-hosted Starter
> for arm64 QEMU. Verify the release before booting it. Owner Bind, app
> connections, and personal-data use remain separate owner decisions.

Before publication, public pages must say only that `v0.1.0` is planned. Do
not pre-announce a download URL, provider support level, or compatibility claim
that the release evidence does not establish.

## Release Files

```text
pios-starter-v0.1.0-arm64.tar.zst
pios-starter-v0.1.0-release-manifest.json
SHA256SUMS
SHA256SUMS.sig
RELEASE-NOTES.md
peecos-release-signing-key.pub
```

The exact final names may preserve the established self-hosted naming scheme,
but all files must be mutually bound by the signed checksum manifest.
