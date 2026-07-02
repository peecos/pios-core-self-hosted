# Example only. Copy to an untracked local pkrvars file and fill real values.
# Do not commit local ISO paths, checksums, passwords, or build credentials.

iso_url               = "file:///path/to/ubuntu-24.04-live-server.iso"
iso_checksum          = "sha256:REPLACE_WITH_ISO_SHA256"
image_payload_archive = "image-artifacts/pios-core-self-hosted-root.tar.zst"

accelerator = "hvf" # macOS host. Use "kvm" on Linux.
qemu_binary = "qemu-system-x86_64" # Use qemu-system-aarch64 for arm64 images.
cpus        = 2
memory      = 4096

http_directory = "image-build/packer-http"
ssh_username   = "piosbuilder"
ssh_password   = "REPLACE_WITH_LOCAL_BUILD_ONLY_PASSWORD"
