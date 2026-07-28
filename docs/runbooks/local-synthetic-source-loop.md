# Local Synthetic Source Loop

Status: VM-2 local fixture proof. This is not a Core API or app integration.

`scripts/pios_local_synthetic_source.py` creates a disposable, data-empty
synthetic Core only after explicit confirmation. It has no network calls, API
server, credentials, mounts, app access, or owner data.

Dry-run is the default:

```bash
python3 scripts/pios_local_synthetic_source.py \
  --workspace /safe/local/path/pios-vm2-synthetic
```

Run the fixture loop only in an empty disposable workspace:

```bash
python3 scripts/pios_local_synthetic_source.py \
  --workspace /safe/local/path/pios-vm2-synthetic \
  --confirm-synthetic-write
```

The result proves accepted, duplicate, denied, retry, revoked, and export
outcomes. Accepted records receive deterministic `core://originals/...` and
`core://events/...` references. Revocation preserves audit evidence and blocks
future submissions; it does not delete accepted Core evidence.

Do not use this tool with a real Core root, app payload, owner data, or a
networked service. VM-2 remains a local synthetic contract fixture only.
