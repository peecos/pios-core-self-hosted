# PIOS Solo C3 Named-Session Preview/Refusal Runner

Status: preview/refusal implementation only. It never creates or accepts a
Unix socket session in this revision.

## Purpose

`scripts/run_pios_solo_c3_named_session.py` validates the exact fixed Corebox
C2 fixture and its C1 envelope through the existing Solo C2/C1 validators. It
then rebuilds the reviewed C3 request vector in memory using the Solo
foundation, but retains only the challenge integrity and request/frame facts.

The preview is pinned to:

- Solo foundation `45c5bac`;
- Corebox preview contract `1db18d5` and execution client `1566817`;
- proof-vector ID `c3-corebox-local-20260801-r1`;
- receipt timestamp `2026-08-01T00:00:03Z`; and
- the fixed review-vector request SHA-256
  `2fd9cdcdeeeb9d179d4bdab4c4f03ff2b88983bdd9597c9a753175ef02675518`,
  1090 request bytes / 1094 framed bytes,
  semantic ID `req_1cb56356f0dc0ed30c6d88cdc38a5f110b2f7728cf6a1f368b762ca0b1bec81c`,
  and connection binding
  `c7270e2f9596324db521fa9a548ed87f67fc50890f70e4ed41d173bb8eec6752`.

This is a deterministic cross-language contract vector, not an approved C3
proof ID or session authorization.

## Preview

```sh
python3 scripts/run_pios_solo_c3_named_session.py \
  --input-dir <fixed-corebox-c2-fixture-directory>
```

The command requires exactly the four regular, non-symlink fixed fixture
files. It verifies their approved hashes, byte counts, manifest posture, and
C1 envelope before building the in-memory review vector. It emits canonical
JSON with no raw nonce, socket path, UID, fixture body, or evidence directory.

Its planned future session contract is fixed as:

- `AF_UNIX` stream only, no loopback or other network transport;
- same effective UID immediately after `accept()` and before challenge issue;
- ordinary bounded `recv`/`send` frames only, 16 KiB maximum, no ancillary data;
- one exact request plus one byte-identical duplicate on the same connection;
- fixed fixture and C1 validation before any lifecycle operation; and
- sanitized-only evidence plus connection/listener/socket/runtime/lifecycle
  cleanup on every outcome.

## Explicit Refusal

`--confirm-c3-local-transport-proof` is intentionally a refusal in this
revision. It stops before preview, runtime creation, socket API use, fixture
submission, or lifecycle work. It is not an execution path.

## Bounded Execution Path (Implemented but Inactive)

The runner now also contains an internal one-shot server state machine for a
future named proof. It is not reachable from the CLI and requires an explicit
`execution_authorized=True` argument supplied only by a future reviewed proof
entry point. The current CLI still refuses every confirmation attempt.

When later authorized, the state machine will create a fresh private runtime,
bind one `AF_UNIX` stream listener, call same-EUID verification immediately
after `accept()`, issue one challenge, validate one fixed request before
lifecycle work, return one accepted response, require one byte-identical
duplicate request, return one duplicate response, then clean the connection,
listener, socket, runtime, and disposable lifecycle root. It uses ordinary
bounded `recv`/`sendall` framing only; no ancillary descriptor APIs are used.

Before any future named execution, the runner requires explicit proof ID,
receipt timestamp, absolute runtime parent, fresh evidence destination, Solo
revision `ef40daf`, and Corebox execution revision `1566817`. Both revision
values, the proof ID, and the receipt timestamp are rejected before any runtime
directory can be made. It records only those revisions and sanitized
lifecycle/root counts in the future result. The accepted connection also
receives a 30-second timeout before peer verification.

The implementation was validated only through mocked listener/channel and
lifecycle seams. No actual listener, `accept()`, connection, fixture
submission, receipt exchange, or lifecycle proof was run.

## Still Not Authorized

No Unix-socket session, Corebox client connection, fixture submission,
accepted/duplicate receipt exchange, lifecycle execution, endpoint, loopback,
network, credential, persistent configuration, device enrollment, Owner Bind,
personal data, or VM/cloud change is authorized. A later named owner decision
must authorize both implementation of the actual session path and one bounded
execution.
