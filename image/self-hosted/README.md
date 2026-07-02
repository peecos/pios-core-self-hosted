# PIOS Core Self-Hosted Image Root

This directory documents the data-empty self-hosted image root. It is a
packaging scaffold, not a built VM image.

The image root should contain only:

- self-hosted Core runtime scripts;
- schemas needed by the runtime;
- a first-boot `pios-core-init` wrapper;
- a generic self-hosted provisioning manifest example;
- image metadata and local setup instructions.

It must not contain:

- hydrated Core Bundles;
- `bundles/` or `restore-proofs/`;
- owner-specific data or identifiers;
- AWS account ids, ARNs, bucket names, profiles, or deployment evidence;
- generated local key material;
- owner profile, Circle runtime, Dash state, raw logs, or takeout data.

Build a candidate image root with:

```bash
.venv/bin/python scripts/build_self_hosted_image_root.py \
  --output-dir image-build/self-hosted-root \
  --run-hygiene
```

The resulting directory is the input for a future VM image builder such as
Packer. The builder should copy it into `/opt/pios-core` inside the VM and make
`/opt/pios-core/bin/pios-core-init` available on the path.
