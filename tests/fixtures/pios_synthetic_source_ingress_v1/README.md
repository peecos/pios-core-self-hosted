# PIOS C1 canonical harmless golden fixture

This fixture is a fixed, owner-neutral, local-only regression vector for the
Python B1/B2/C1 source primitives. It contains generated harmless text only.
It is not a Corebox transport fixture, an endpoint contract, a credential,
device enrollment, owner bind, or a claim of cross-language byte parity.

`original.bin` is the exact 37-byte original input. Its SHA-256 and byte count
are in `golden-manifest.json`.

Every `*.json` artifact is stored as readable, sorted-key UTF-8 JSON. Its
canonical fixture bytes are exactly:

```python
canonical_json_bytes(json.loads(path.read_text(encoding="utf-8")))
```

The checked-in text files end in one LF for repository text-file handling; that
LF is deliberately *not* part of the canonical JSON byte stream. The manifest
pins the SHA-256 and byte count of those B1 canonical bytes, not a platform
text-file representation.

The fixed artifacts cover the B2 input/candidates, C1 envelope/bindings,
accepted and duplicate receipts, and fail-closed negative vectors. The Python
regression test reconstructs each value using the implementation and compares
the canonical bytes, SHA-256 values, and byte counts directly.

Do not substitute owner content, device identifiers, paths, endpoints,
credentials, or a provider reference into this fixture. Any future Swift or
Corebox byte-parity vector requires a separately reviewed C1 contract update.
