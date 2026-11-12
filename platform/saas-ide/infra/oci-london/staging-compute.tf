# Dedicated private staging VM; creation is opt-in after approved cost/security plan.
variable "enable_staging_compute" {
  type    = bool
  default = false
}
variable "availability_domain" {
  type = string
  description = "Verified availability domain in uk-london-1"
  default = ""
}
variable "image_ocid" {
  type = string
  description = "Verified compatible OCI image OCID for London"
  default = ""
}
variable "ssh_public_key" {
  type = string
  description = "Operator-managed SSH public key; never supply a private key"
  default = ""
  sensitive = true
}
variable "instance_shape" {
  type    = string
  default = "VM.Standard.A1.Flex"
  validation {
    condition     = var.instance_shape == "VM.Standard.A1.Flex"
    error_message = "Only OCI Always Free Ampere A1 shape is allowed."
  }
}
variable "instance_ocpus" {
  type    = number
  default = 1
  validation {
    condition = var.instance_ocpus >= 1 && var.instance_ocpus <= 2
    error_message = "Staging CPU budget guardrail: 1 to 2 OCPUs."
  }
}
variable "instance_memory_gb" {
  type    = number
  default = 6
  validation {
    condition = var.instance_memory_gb >= 4 && var.instance_memory_gb <= 12
    error_message = "Staging memory guardrail: 4 to 12 GB."
  }
}
resource "oci_core_instance" "staging" {
  count               = var.enable_staging_compute ? 1 : 0
  availability_domain = var.availability_domain
  compartment_id      = var.compartment_ocid
  display_name        = "${var.name_prefix}-api"
  shape               = var.instance_shape
  shape_config {
    ocpus         = var.instance_ocpus
    memory_in_gbs = var.instance_memory_gb
  }
  source_details {
    source_type = "image"
    source_id   = var.image_ocid
    boot_volume_size_in_gbs = 50
  }
  create_vnic_details {
    subnet_id        = oci_core_subnet.private.id
    assign_public_ip = false
    nsg_ids          = [oci_core_network_security_group.api.id]
  }
  metadata = {
    ssh_authorized_keys = var.ssh_public_key
  }
  lifecycle {
    precondition {
      condition = !var.enable_staging_compute || (
        startswith(var.image_ocid, "ocid1.image.") &&
        var.instance_memory_gb <= var.instance_ocpus * 6 &&
        length(var.availability_domain) > 5 &&
        startswith(var.ssh_public_key, "ssh-")
      )
      error_message = "Supply verified London image, AD and SSH public key before enabling compute."
    }
  }
}
output "staging_instance_id" {
  value = var.enable_staging_compute ? oci_core_instance.staging[0].id : null
}
