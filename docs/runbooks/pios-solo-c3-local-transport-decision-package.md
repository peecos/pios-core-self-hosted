# PIOS Solo C3: Local-Transport Decision Package

Status: **draft only — no socket, listener, Corebox client, local transport,
or C3 proof is authorized or implemented.**

## Purpose and Fixed Input

C3 would prove one constrained local handoff of the completed C2 harmless
fixture from a Corebox-side local harness to the Solo local synthetic
lifecycle. It is not app sync, a Core API, a VM service, or an owner
connection.

Only this immutable fixture is eligible:

`Storage-wiki/Storage/Other/pios-core/self-hosted-vm/corebox-c2-synthetic-fixture-2026-08-01/`

Its fixture ID, four recorded hashes, profile, and `prepared_not_authorized`
gates must be revalidated before any future listener is created. C3 must not
replace, regenerate, reuse for another proof, or broaden the fixture.

## Transport Choice

### Unix-Domain Socket Is the Only Eligible Initial Transport

C3 selects an `AF_UNIX` stream socket as the only eligible initial mechanism.
It must live beneath a fresh proof-owned `/private/tmp` directory with a new
unpredictable name, directory mode `0700`, socket mode `0600`, no symlink
traversal, and automatic unlink/removal on every outcome. It must never listen
on TCP, UDP, any network interface, or a stable filesystem path.

The Solo listener must obtain platform local-peer credentials where supported
and require the connecting peer to have the same local UID. Evidence records
only `same_local_uid: true`; it must not retain the UID, socket path, or other
personal machine identifier.

### Loopback Is Not Selected

Plain `127.0.0.1` or `::1` TCP cannot establish equivalent local-user binding
without a credential or bearer secret. Both conflict with the current boundary.
There is no Unix-socket-to-loopback fallback. A future loopback option needs a
new owner decision and a reviewed non-credential local-peer binding design.

## Future Owner Decision Required Before Implementation or Execution

| Decision field | Required value |
| --- | --- |
| C3 proof ID | New ID such as `c3-corebox-local-YYYYMMDD-r1`. |
| Transport | Exactly `unix_socket`; loopback excluded. |
| Fixture | The fixed C2 fixture and all four approved hashes. |
| Corebox / Solo revisions | Reviewed pure-local client and listener revisions. |
| Receipt time | Fixed UTC whole-second timestamp. |
| Evidence destination | Fresh `Storage-wiki/.../self-hosted-vm/c3-local-transport-proof/<proof-id>/`. |
| Runtime location | Fresh private temporary directory; no stable socket/Core/VM path. |
| Confirmation | A future `--confirm-c3-local-transport-proof` after a zero-write preview. |

The decision must exclude public listeners, loopback TCP, network access,
VM/cloud changes, credentials, app networking, device enrollment, Owner Bind,
Core API/hydration/connector/scheduler activation, and personal data.

## Constrained Protocol

The protocol uses length-prefixed canonical UTF-8 JSON frames, maximum 16 KiB.
It accepts only the fixed harmless envelope and original bytes. It accepts no
path, bookmark, URL, endpoint, credential, app setting, batch, stream, or
arbitrary payload.

### Peer Binding and Challenge

After same-local-UID verification, Solo sends one in-memory challenge:

```json
{
  "schema_version": "pios_solo_c3_local_challenge_v1",
  "protocol": "pios_solo_c3_local_transport_v1",
  "proof_id": "<approved-proof-id>",
  "challenge_nonce": "<ephemeral-random-bytes-encoding>",
  "fixture_manifest_sha256": "<approved-hash>"
}
```

The nonce is one-connection replay binding only, not a credential, account,
device enrollment record, or reusable bearer token. It is never retained;
evidence may retain only its SHA-256.

### One Request and Receipt Response

Corebox may send exactly one `submit_fixed_fixture` request. It canonically
binds protocol/schema versions, proof ID, fixture ID, challenge nonce, fixed
receipt time, and SHA-256/byte counts of every fixed input. Solo recomputes all
bindings and runs the existing C1 validator before calling the local lifecycle.

Request authentication is the conjunction of Unix socket permissions and
same-UID peer verification, the fresh challenge, and exact proof/fixture hash
binding. It is not password, API key, bearer token, certificate, enrollment,
or owner identity authentication.

Solo returns only:

```json
{
  "schema_version": "pios_solo_c3_local_receipt_response_v1",
  "request_id": "<deterministic-request-binding-id>",
  "status": "accepted | duplicate",
  "receipt": { "...": "validated synthetic ingress receipt" }
}
```

Corebox validates the receipt against the exact sent envelope/original. A
mismatch, missing receipt, unexpected status, or non-canonical `core://`
reference stops the proof.

### Replay Rules

- First exact request may return `accepted`.
- One exact repeat returns `duplicate` with the same receipt ID.
- Changed envelope/original/hash under the same request ID is refused before
  lifecycle submission and never replaces local state.
- Changed challenge, proof ID, fixture ID, receipt time, or protocol version
  is refused. Cross-proof replay is forbidden.
- The listener accepts no second fixture or request after the duplicate.

## Planned Execution and Cleanup

No C3 runner exists. A later runner has a zero-write preview by default. It
must validate exact inputs, no TCP listener, socket directory safety, peer
binding capability, no endpoint/credential fields, and evidence freshness
before binding a socket.

Only named confirmation may create the private Unix socket and perform one
accepted plus one duplicate handoff, receipt validation, and local
export/readback. The installed Corebox app may remain disconnected; a pure
local Corebox test harness is preferred.

On pass or failure, close connections, stop the listener, unlink the socket,
remove the private runtime directory, and prove none remains. Never retain a
raw socket path, UID, challenge nonce, or arbitrary client bytes.

## Hard Stops

Stop with sanitized diagnostics, no automatic retry/fallback, if any of these
occurs:

- transport is not Unix socket; peer credentials are unavailable/mismatched;
  socket directory or permissions are unsafe; a symlink or existing path
  appears;
- any TCP/UDP/IPv6/loopback/public listener attempt;
- fixture/canonical/C1 validation mismatch or input outside the fixed fixture;
- malformed or oversized frame, wrong challenge/proof/binding, or replay
  mutation;
- unexpected receipt/status or receipt verification failure;
- endpoint, credential, network, app configuration, VM/Core/cloud, or
  personal-data action; or
- evidence write, socket unlink, connection close, or runtime cleanup failure.

## Required Evidence

Retain only harmless review material: fixed fixture copies/hashes, protocol and
implementation revisions, frame limit, `same_local_uid: true`, challenge hash,
request-binding hash, accepted/duplicate responses and validation, replay
refusal, export/readback, zero network/cloud/VM/Core assertions, and cleanup
result. Do not retain UID, socket path, nonce, endpoint, credential, app
folder, or personal data.

## C3 Acceptance Boundary

C3 passes only if the fixed fixture completes accepted and exact duplicate
handoffs over the private Unix socket; both sides validate the same receipt;
replay mutation fails closed; evidence is complete; and listener/socket/
lifecycle roots are cleaned. A passed C3 proof would still not authorize
persistent transport, background synchronization, Owner Bind, or personal
capture.
