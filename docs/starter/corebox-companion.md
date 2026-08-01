# Corebox Companion Boundary

Corebox is an optional local-first Inbox companion released alongside PIOS
Starter. It is not embedded in this image and is not required by the Core
runtime.

Corebox may provide local macOS or iOS capture, Share extensions, local folder
management, manifests, receipts, preview, archive, move, and delete behavior.
Installing Corebox does not bind it to this Core.

This Starter image contains no Corebox binary, app-group state, Inbox folder,
capture, receipt history, endpoint, device identifier or key, credential, sync
setting, or enabled app transport.

Any future Corebox connection requires its own owner-approved stages: compatible
Core selection, device enrollment, a scoped synthetic proof, independent review,
and a named decision before personal capture. A local image boot or Owner Bind
does not authorize those stages automatically.
