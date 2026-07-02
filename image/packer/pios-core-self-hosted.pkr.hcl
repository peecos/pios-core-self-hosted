packer {
  required_version = ">= 1.10.0"
  required_plugins {
    qemu = {
      version = ">= 1.1.0"
      source  = "github.com/hashicorp/qemu"
    }
  }
}

variable "iso_url" {
  type        = string
  description = "Path or URL to a minimal Linux installer ISO. Not pinned in repo."
}

variable "iso_checksum" {
  type        = string
  description = "Checksum for iso_url, for example sha256:<digest>."
}

variable "image_payload_archive" {
  type        = string
  description = "Data-empty PIOS Core self-hosted image-root tar.zst payload."
}

variable "http_directory" {
  type        = string
  description = "Directory served by Packer for unattended installer seed files."
  default     = "image/packer/http"
}

variable "vm_name" {
  type    = string
  default = "pios-core-self-hosted"
}

variable "cpus" {
  type    = number
  default = 2
}

variable "memory" {
  type        = number
  description = "Guest memory in MiB."
  default     = 4096
}

variable "accelerator" {
  type        = string
  description = "QEMU accelerator for the build host, e.g. hvf on macOS or kvm on Linux."
  default     = "hvf"
}

variable "qemu_binary" {
  type        = string
  description = "QEMU binary to use. Use qemu-system-x86_64 for amd64 images or qemu-system-aarch64 for arm64 images."
  default     = "qemu-system-x86_64"
}

variable "ssh_username" {
  type        = string
  description = "Temporary installer user created by local cloud-init/autoinstall seed."
  default     = "piosbuilder"
}

variable "ssh_password" {
  type        = string
  description = "Temporary installer password. Must match the local seed file. Do not commit real values."
  sensitive   = true
}

variable "ssh_timeout" {
  type    = string
  default = "30m"
}

variable "boot_wait" {
  type    = string
  default = "5s"
}

variable "boot_command" {
  type        = list(string)
  description = "Ubuntu Server live ISO autoinstall boot command. Adjust per distro/ISO."
  default = [
    "e<wait>",
    "<down><down><down><end>",
    " autoinstall ds=nocloud-net\\;s=http://{{ .HTTPIP }}:{{ .HTTPPort }}/ ---",
    "<f10>"
  ]
}

source "qemu" "pios_core_self_hosted" {
  vm_name          = var.vm_name
  iso_url          = var.iso_url
  iso_checksum     = var.iso_checksum
  disk_size        = "20000M"
  format           = "qcow2"
  cpus             = var.cpus
  memory           = var.memory
  headless         = true
  accelerator      = var.accelerator
  qemu_binary      = var.qemu_binary
  http_directory   = var.http_directory
  boot_wait        = var.boot_wait
  boot_command     = var.boot_command
  ssh_username     = var.ssh_username
  ssh_password     = var.ssh_password
  ssh_timeout      = var.ssh_timeout
  shutdown_command = "echo '${var.ssh_password}' | sudo -S shutdown -P now"
}

build {
  name    = "pios-core-self-hosted"
  sources = ["source.qemu.pios_core_self_hosted"]

  provisioner "file" {
    source      = var.image_payload_archive
    destination = "/tmp/pios-core-self-hosted-root.tar.zst"
  }

  provisioner "shell" {
    inline = [
      "if command -v apt-get >/dev/null 2>&1; then sudo apt-get update && sudo apt-get install -y python3 zstd tar; fi",
      "sudo mkdir -p /opt/pios-core",
      "sudo tar --zstd -xf /tmp/pios-core-self-hosted-root.tar.zst -C /opt/pios-core --strip-components=1",
      "sudo ln -sf /opt/pios-core/bin/pios-core-init /usr/local/bin/pios-core-init",
      "test -x /usr/local/bin/pios-core-init",
      "sudo rm -f /tmp/pios-core-self-hosted-root.tar.zst"
    ]
  }
}
