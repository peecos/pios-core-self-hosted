# PIOS Starter Offline Documentation

This directory is copied into every PIOS Starter image at
`/opt/pios-core/docs/starter/`. It is a compact, release-bound orientation
bundle for a data-empty installation.

Read in this order:

1. `runtime-profile.md` for the neutral runtime model.
2. `owner-bind.md` before creating any owner-specific state.
3. `corebox-companion.md` before installing or connecting the optional Inbox
   companion.

The image's `IMAGE_MANIFEST.json` names every included file and its source
revision. Verify that manifest and the release artifact checksum before relying
on this material.

This is not a copy of the full PIOS 2.0 master. The canonical framework source
is maintained separately by peecos. This bundle intentionally contains no
owner identity, endpoint, credential, device record, recovery material, policy,
or personal data.

