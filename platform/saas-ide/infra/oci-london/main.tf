terraform {
  required_version = ">= 1.6.0"
  required_providers {
    oci = { source = "oracle/oci", version = "~> 6.0" }
  }
}
provider "oci" { region = "uk-london-1" }
variable "compartment_ocid" { type = string }
variable "name_prefix" {
  type = string
  default = "aepx-staging"
}
variable "vcn_cidr" {
  type = string
  default = "10.74.0.0/16"
}
resource "oci_core_vcn" "aepx" {
  compartment_id = var.compartment_ocid
  cidr_blocks = [var.vcn_cidr]
  display_name = "${var.name_prefix}-vcn"
  dns_label = "aepx"
}
resource "oci_core_subnet" "private" {
  compartment_id = var.compartment_ocid
  vcn_id = oci_core_vcn.aepx.id
  cidr_block = "10.74.10.0/24"
  display_name = "${var.name_prefix}-private"
  prohibit_public_ip_on_vnic = true
}
resource "oci_core_network_security_group" "api" {
  compartment_id = var.compartment_ocid
  vcn_id = oci_core_vcn.aepx.id
  display_name = "${var.name_prefix}-api-nsg"
}
resource "oci_objectstorage_bucket" "draft_artifacts" {
  compartment_id = var.compartment_ocid
  namespace = var.object_storage_namespace
  name = "${var.name_prefix}-draft-artifacts"
  access_type = "NoPublicAccess"
  versioning = "Enabled"
}
variable "object_storage_namespace" { type = string }
output "private_subnet_ocid" { value = oci_core_subnet.private.id }
output "api_nsg_ocid" { value = oci_core_network_security_group.api.id }
output "draft_bucket_name" { value = oci_objectstorage_bucket.draft_artifacts.name }
