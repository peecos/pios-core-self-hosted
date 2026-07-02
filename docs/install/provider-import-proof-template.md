# Self-Hosted Provider Import Proof Template

Status: reusable template; no provider marked supported by this template alone

Use this template for each VM provider import proof.

Provider support is not granted until the provider-specific proof is completed,
reviewed, and recorded.

## Proof Metadata

```yaml
provider: <google_cloud | azure | aws | hetzner | upcloud | local_vm | other>
provider_region: <region-or-location>
proof_date: <YYYY-MM-DD>
reviewer: <agent-or-human>
release_id: <release-id>
release_manifest: <path-or-url>
package_archive: <path-or-url>
package_sha256: <sha256>
image_name: <image-name>
image_sha256: <sha256>
architecture: <arm64 | x86_64>
image_format: <qcow2 | raw | vhd | vmdk | provider-native>
status: planned | passed | failed
```

## Preconditions

- Owner approved a provider import proof.
- Proof uses synthetic owner identity only.
- No real owner data is present in the image.
- Provider readiness matrix has been reviewed:
  `docs/install/provider-readiness-matrix.md`.
- Public split hygiene scan has passed if this proof uses artifacts from a
  curated public repository split.
- Package checksum has been verified.
- Signature has been verified if a signature exists.
- Provider account/project/subscription is confirmed.
- Cost exposure is understood.
- Cleanup commands are known before creating resources.
- Provider-specific format and architecture constraints are understood.
- Any provider-specific converted artifact is temporary, checksummed, and
  traceable back to the source package.

## Provider Import Details

Record:

```yaml
staging_location: <bucket/container/path>
source_image_format: <qcow2 | raw | vhd | vmdk | provider-native>
provider_import_format: <qcow2 | raw-tar-gz | vhd | vmdk | provider-native>
conversion_required: true | false
conversion_command_or_flow: <command-or-summary>
converted_artifact_sha256: <sha256-or-none>
import_command_or_flow: <command or manual flow summary>
imported_image_id: <provider image id>
vm_instance_id: <provider VM id>
vm_size: <machine type>
boot_metadata_method: <cloud-init | serial console | startup script | other>
network_exposure: <none | ssh restricted | other>
temporary_resources:
  - <resource id>
```

## Required Validation

The proof passes only if all are true:

1. Image import succeeds.
2. VM boots from imported image.
3. Synthetic self-hosted provisioning manifest is supplied.
4. `pios-core-init` runs.
5. Five Core zones are created:
   - `originals`
   - `events`
   - `knowledge`
   - `derived`
   - `system`
6. `system/bootstrap/health-check.json` reports `status: passed`.
7. Authorization gates remain false:
   - `hydrate_bundle`
   - `connector_sync`
   - `broad_migration`
   - `source_decommission`
8. Service flags remain false unless a service-supervisor proof is explicitly
   in scope:
   - `start_core_api`
   - `start_connectors`
   - `start_scheduler`
9. No owner data is uploaded.
10. Cleanup succeeds or residual resources are explicitly listed.

## Evidence To Capture

Capture:

```text
package checksum verification output
signature verification output
provider import command/result
imported image id
VM boot proof
pios-core-init output
health-check JSON
authorization gate state
cleanup command/result
cost notes
known limitations
```

## Fail Conditions

Fail if:

- checksum mismatch;
- signature mismatch;
- import requires changing the image in an undocumented way;
- VM does not boot;
- first-boot manifest is not applied;
- health check does not pass;
- any authorization gate becomes true unexpectedly;
- provider exposes network services unexpectedly;
- cleanup cannot be completed;
- proof accidentally includes owner data.

## Proof Result

```yaml
result: passed | failed
supported_status_after_proof: unsupported | experimental | supported
remaining_limitations:
  - <item>
cleanup_status: complete | incomplete
next_review_needed: true | false
```

`supported_status_after_proof` should normally be `experimental` after the
first successful proof and move to `supported` only after repeatability,
cost/security review, and documentation review.
