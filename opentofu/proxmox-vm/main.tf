resource "proxmox_download_file" "cloud_image" {
  content_type = "import"
  datastore_id = var.image_datastore_id
  node_name    = var.proxmox_node
  url          = var.cloud_image_url
  file_name    = var.cloud_image_file_name
}

resource "proxmox_virtual_environment_vm" "wab_node" {
  name          = var.vm_name
  node_name     = var.proxmox_node
  vm_id         = var.vm_id
  tags          = ["kind", "opentofu"]
  scsi_hardware = "virtio-scsi-single"

  cpu {
    cores = var.vm_cores
    type  = "host"
  }

  memory {
    dedicated = var.vm_memory
  }

  disk {
    datastore_id = var.storage_pool
    import_from  = proxmox_download_file.cloud_image.id
    interface    = "scsi0"
    size         = var.vm_disk_size
    file_format  = "raw"
    iothread     = true
    discard      = "on"
  }

  network_device {
    bridge = var.network_bridge
  }

  operating_system {
    type = "l26"
  }

  initialization {
    datastore_id = var.storage_pool

    ip_config {
      ipv4 {
        address = "${var.vm_ip_address}/${var.vm_subnet_mask}"
        gateway = var.vm_gateway
      }
    }

    dns {
      servers = var.dns_servers
    }

    user_account {
      username = var.vm_user
      keys     = [var.ssh_public_key]
    }
  }
}
