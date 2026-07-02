# PIOS Core Self-Hosted Packer Scaffold

Status: scaffold only; not yet executed

This directory is the VM-builder handoff for the data-empty self-hosted Core
image path.

The local Primary Mac currently does not have `packer`, `qemu-system-x86_64`,
or `tart` installed, so the scaffold is intentionally not marked as a booted VM
proof. Use `scripts/check_self_hosted_vm_builder_prereqs.py` before attempting
to build.

## Intended Flow

1. Build and hygiene-check the image root:

   ```bash
   .venv/bin/python scripts/build_self_hosted_image_root.py \
     --output-dir image-build/self-hosted-root \
     --force \
     --run-hygiene
   ```

   `--force` is only valid when the output directory already contains a prior
   `IMAGE_MANIFEST.json` with the expected image-root schema. The builder
   refuses to force-delete arbitrary non-image directories.

2. Package it as a data-empty install payload:

   ```bash
   .venv/bin/python scripts/package_self_hosted_image_root.py \
     --image-root image-build/self-hosted-root \
     --output-dir image-artifacts \
     --package-id pios-core-self-hosted-root
   ```

3. Prepare local unattended-install seed files.

   Copy the example seed into an untracked build directory and replace the
   password hash with a local build-only value:

   ```bash
   mkdir -p image-build/packer-http
   cp image/packer/http/meta-data image-build/packer-http/meta-data
   cp image/packer/http/user-data.example image-build/packer-http/user-data
   ```

   Do not commit the generated `user-data` file. The temporary `piosbuilder`
   account exists only to let Packer provision the image. A golden candidate
   must not be published if it still contains build credentials, known
   passwords, or builder-only sudoers files.

4. Use a VM builder to install the payload into `/opt/pios-core`.

   Before the Packer scaffold can run, choose a concrete base image and provide:

   - `iso_url` and `iso_checksum`;
   - a local `image_payload_archive`;
   - temporary communicator values such as `ssh_username`, `ssh_password`, and
     `ssh_timeout`;
   - distro-specific unattended install input. The included `boot_command` and
     `http_directory` are an Ubuntu Server live ISO starting point and may need
     adjustment for the chosen ISO;
   - `accelerator=hvf` on macOS or `accelerator=kvm` on Linux;
   - `qemu_binary=qemu-system-x86_64` for amd64 images or
     `qemu_binary=qemu-system-aarch64` for arm64 images;
   - guest dependencies: `python3`, `tar`, and `zstd`.

   The scaffold installs `python3`, `tar`, and `zstd` automatically on
   apt-based guests, but non-Debian/Ubuntu guests need equivalent commands.

5. In the VM, run:

   ```bash
   /opt/pios-core/bin/pios-core-init \
     --manifest /path/to/self-hosted-provisioning-manifest.json
   ```

6. Run image-level hygiene and repeatability checks before calling the result a
   golden image candidate.

## Boundary

The Packer scaffold must not embed:

- owner data;
- hydrated Core Bundles;
- generated keys;
- AWS account ids, ARNs, bucket names, or profiles;
- local manifests;
- pilot evidence.
