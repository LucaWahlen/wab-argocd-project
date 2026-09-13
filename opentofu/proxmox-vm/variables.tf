variable "proxmox_endpoint" {
  description = "Proxmox API endpoint, e.g. https://proxmox.example.lan:8006/"
  type        = string
}

variable "proxmox_api_token" {
  description = "Proxmox API token in the form 'user@realm!tokenid=uuid'"
  type        = string
  sensitive   = true
}

variable "proxmox_insecure" {
  description = "Skip TLS verification for the Proxmox API (needed for self-signed certs)"
  type        = bool
  default     = true
}

variable "proxmox_node" {
  description = "Name of the Proxmox node to deploy the VM on"
  type        = string
}

variable "cloud_image_url" {
  description = "URL of the cloud-init-ready disk image OpenTofu downloads onto the Proxmox node and boots the VM from"
  type        = string
  default     = "https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img"
}

variable "cloud_image_file_name" {
  description = "Name to save the downloaded image as on Proxmox - must end in a real disk-image extension (.qcow2/.raw/...) for content_type = \"import\" to accept it, since Ubuntu's URL misleadingly ends in .img despite being qcow2"
  type        = string
  default     = "wab-noble-server-cloudimg-amd64.qcow2"
}

variable "image_datastore_id" {
  description = "Proxmox datastore to download the cloud image onto (needs the 'Import' content type enabled, e.g. the default 'local')"
  type        = string
  default     = "local"
}

variable "vm_id" {
  description = "VM ID to assign to the new VM"
  type        = number
  default     = 111
}

variable "vm_name" {
  description = "Name/hostname of the VM"
  type        = string
  default     = "wab"
}

variable "vm_cores" {
  description = "Number of vCPUs for the VM"
  type        = number
  default     = 4
}

variable "vm_memory" {
  description = "RAM for the VM, in MB"
  type        = number
  default     = 8192
}

variable "vm_disk_size" {
  description = "Disk size for the VM, in GB"
  type        = number
  default     = 50
}

variable "storage_pool" {
  description = "Proxmox storage pool to use for the VM disk and cloud-init drive"
  type        = string
}

variable "network_bridge" {
  description = "Proxmox network bridge to attach the VM to"
  type        = string
  default     = "vmbr0"
}

variable "vm_ip_address" {
  description = "Static IPv4 address for the VM, e.g. 192.168.1.50"
  type        = string
}

variable "vm_subnet_mask" {
  description = "Subnet mask in CIDR bits, e.g. 24"
  type        = number
  default     = 24
}

variable "vm_gateway" {
  description = "Default gateway for the VM's network, e.g. 192.168.1.1"
  type        = string
}

variable "dns_servers" {
  description = "DNS servers for the VM"
  type        = list(string)
  default     = ["1.1.1.1", "8.8.8.8"]
}

variable "vm_user" {
  description = "Default user account created on the VM via cloud-init"
  type        = string
  default     = "ubuntu"
}

variable "ssh_public_key" {
  description = "Your SSH public key contents, e.g. file(\"~/.ssh/id_ed25519.pub\")"
  type        = string
}
