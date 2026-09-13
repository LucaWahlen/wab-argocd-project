terraform {
  required_version = ">= 1.12"

  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = ">= 0.113.1, < 1.0.0"
    }
  }
}

provider "proxmox" {
  endpoint  = var.proxmox_endpoint
  api_token = var.proxmox_api_token
  insecure  = var.proxmox_insecure
}
