# PIOS Solo C3: Local-Transport Decision Package

Status: **the narrow Solo-side Unix-socket foundation and named-session
preview/refusal runner are implemented and locally tested; no C3 listener
session, Corebox socket client, fixture handoff, or C3 proof is authorized or
implemented.**

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

The Solo listener must obtain platform local-peer credentials and require the
connecting peer to have the same local UID. Evidence records only
`same_local_uid: true`; it must not retain the UID, socket path, or other
personal machine identifier.

On the current macOS/Python baseline, `getpeereid(3)` and `LOCAL_PEERCRED` are
available at the operating-system layer, but Python does not expose
`socket.getpeereid` or Linux `SO_PEERCRED`. The approved foundation is the
small macOS-only `ctypes` `getpeereid(3)` adapter in
`scripts/pios_c3_local_transport.py`. It defines the BSD ABI explicitly as
`getpeereid(int, uid_t *, gid_t *)`, reads only effective UID/GID, has no
fallback, and is tested on a connected local `AF_UNIX` socket pair. A later
session runner must compare the connected peer effective UID to the listener
effective UID immediately after `accept()` and before a challenge. Failure to
obtain or compare credentials is a refusal, never a best-effort fallback.

Same-UID verification is an owner-account trust boundary, not proof that the
peer is a particular signed Corebox process. C3 must state that any process
running under that same local UID is inside its limited test trust domain. A
stronger process/application identity claim would need a separately reviewed
mechanism and is out of scope.

### Loopback Is Not Selected

Plain `127.0.0.1` or `::1` TCP cannot establish equivalent local-user binding
without a credential or bearer secret. Both conflict with the current boundary.
There is no Unix-socket-to-loopback fallback. A future loopback option needs a
new owner decision and a reviewed non-credential local-peer binding design.

## Future Owner Decision Required Before C3 Handoff Execution

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

Corebox may send exactly one `submit_fixed_fixture` request followed only by
one exact duplicate request in the same connection. It canonically binds
protocol/schema versions, proof ID, fixture ID, challenge nonce, fixed receipt
time, and SHA-256/byte counts of every fixed input. Solo recomputes all
bindings and runs the existing C1 validator before calling the local lifecycle.

The design has two distinct IDs:

- `semantic_request_id`: deterministic hash of proof ID, protocol version,
  fixture ID, four fixture integrity records, and receipt time; and
- `connection_binding_hash`: hash of `semantic_request_id` plus the current
  one-connection challenge nonce.

The receipt response returns both. The second request must preserve both values
and every fixture byte exactly. This makes the duplicate proof deterministic
without allowing a request from an old connection to become valid.

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
- One exact repeat in the same connection returns `duplicate` with the same
  receipt ID.
- Changed envelope/original/hash under the same request ID is refused before
  lifecycle submission and never replaces local state.
- Any request bearing a challenge from a previous connection is stale and
  refused before lifecycle submission. The C3 proof allows no reconnect after
  challenge issuance.
- Changed proof ID, fixture ID, receipt time, protocol version, or connection
  binding is refused. Cross-proof replay is forbidden.
- The listener accepts no second fixture, no ancillary data, and no request
  after the required duplicate response.

## Foundation Implementation — 2026-08-01

`scripts/pios_c3_local_transport.py` implements only the reviewed,
non-lifecycle building blocks:

- macOS `getpeereid(3)` effective-peer credentials and fail-closed same-EUID
  verification for connected `AF_UNIX` stream sockets;
- creation of a fresh absolute-path runtime directory, verified with `lstat`
  as owner-owned `0700`, plus a fixed `handoff.sock` verified as an owner-owned
  `0600` Unix socket; and
- restrictive cleanup that refuses a symlink, non-socket replacement, wrong
  mode/owner, unexpected path, or a runtime directory that cannot be proven
  empty after unlink.

It also provides canonical 16 KiB length-prefixed frame validation and exact
challenge/request binding. The request shape is hard-pinned to exactly the
prepared C2 fixture ID and these four integrity records:

| Input | SHA-256 | Bytes |
| --- | --- | ---: |
| `envelope.json` | `d1c0f4c1d41872f85e5c23331b593413615577524a0fa12ed81086b497370d5d` | 3185 |
| `original.bin` | `557dcfaa13fcd79c59a61a0dc7d292aedf96ca4bf9aa41908b0ade40726be679` | 42 |
| `corebox-c2-zero-write-preview.json` | `0a6cc21d9dd0a616558a2e47995fd9c6ad32ebe1e7d38946a8ebe96e6285b732` | 776 |
| `fixture-manifest.json` | `19e7cc9c57df09cbdea8711e5684257279578a18c39fcde8a92851a26a2245a7` | 870 |

The foundation contains no `accept()` session loop, Corebox client,
fixture-file reader, lifecycle call, receipt handler, or confirmation flag.
Its unit tests use an empty local listener and metadata bindings only; they do
not read, transmit, or submit the prepared fixture. The module has no
`AF_INET`, `AF_INET6`, `connect`, `sendmsg`, `recvmsg`, or lifecycle import.

## Planned Execution and Cleanup

`scripts/run_pios_solo_c3_named_session.py` now provides the zero-write,
preview/refusal runner. It reads only the fixed four-artifact fixture, invokes
the existing C1 validation, rebuilds the reviewed Corebox/Solo request vector
in memory, verifies the exact request/frame hashes, and emits sanitized plan
facts. It creates no runtime directory, listener, connection, evidence
directory, lifecycle state, or socket API event. Its confirmation flag refuses
before preview or socket activity; this is not an execution switch.

A later separately authorized session implementation must validate exact
inputs, no TCP listener, socket directory safety, peer-binding capability, no
endpoint/credential fields, and evidence freshness before binding a socket.

Only named confirmation may create the private Unix socket and perform one
accepted plus one duplicate handoff, receipt validation, and local
export/readback. The installed Corebox app may remain disconnected; a pure
local Corebox test harness is preferred.

The implementation must create the socket under a restrictive umask, verify
the new directory/socket ownership and actual `0700`/`0600` modes with
`lstat`, and refuse a non-socket, symlink, unexpected path replacement, or
wrong owner. Unix stream sockets can carry file descriptors through ancillary
data; C3 must use ordinary `recv` framing only and reject any ancillary data or
descriptor transfer. It must never call `recvmsg`/`sendmsg` for C3 frames.

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
  mutation; any reconnect after challenge issuance; or any ancillary data/file
  descriptor transfer;
- unexpected receipt/status or receipt verification failure;
- endpoint, credential, network, app configuration, VM/Core/cloud, or
  personal-data action; or
- evidence write, socket unlink, connection close, or runtime cleanup failure.

## Required Evidence

Retain only harmless review material: fixed fixture copies/hashes, protocol and
implementation revisions, frame limit, `same_local_uid: true`, challenge hash,
semantic request ID, connection-binding hash, accepted/duplicate responses and
validation, replay refusal, export/readback, zero network/cloud/VM/Core
assertions, and cleanup result. Do not retain UID, socket path, nonce,
endpoint, credential, app folder, or personal data.

## Narrow Design Review — 2026-08-01

Local macOS documentation confirms that binding a Unix-domain socket creates a
filesystem socket file which must be explicitly unlinked, that ordinary
filesystem access controls apply to `connect`, and that effective peer
credentials on connected Unix stream sockets are reliable at connect/listen
time. The C3 amendments above turn those facts into explicit gates. No socket
or platform credential call was made during this review.

## C3 Acceptance Boundary

C3 passes only if the fixed fixture completes accepted and exact duplicate
handoffs over the private Unix socket; both sides validate the same receipt;
replay mutation fails closed; evidence is complete; and listener/socket/
lifecycle roots are cleaned. A passed C3 proof would still not authorize
persistent transport, background synchronization, Owner Bind, or personal
capture.
