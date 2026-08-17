# The shortest real spin-up path (docs/INTERPOSE_SCOPING.md Section 11.6): EKS + RDS
# + S3, skipping ElastiCache (an in-cluster Redis instead -- the Helm chart's own
# `redis.embedded` toggle, same as local kind dev) and custom KMS (each service's own
# default encryption instead of a dedicated customer-managed key). This is a real
# ROOT module (has its own `provider` block, unlike `../..` -- see that module's
# `main.tf` comment for why a reusable module never declares one itself).

terraform {
  required_version = ">= 1.7"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Section 11.6: "the module doesn't dictate a state backend (users choose S3,
  # Terraform Cloud, local)... examples/minimal/ shows S3 backend usage." Left
  # commented -- an un-configured backend here means `terraform init` uses local
  # state by default, so a first-time reader can actually run this without first
  # having to go create a state bucket + lock table. Uncomment and fill in real,
  # already-existing resources to switch to remote state.
  # backend "s3" {
  #   bucket         = "your-terraform-state-bucket"
  #   key            = "interpose/minimal/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "your-terraform-locks"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.region
}

variable "region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "us-east-1"
}

module "interpose_eks" {
  source = "../.."

  region       = var.region
  cluster_name = "interpose"
  environment  = "demo"

  enable_elasticache = false
  enable_custom_kms  = false
}

output "cluster_name" {
  value = module.interpose_eks.cluster_name
}

output "cluster_endpoint" {
  value = module.interpose_eks.cluster_endpoint
}

output "configure_kubectl" {
  description = "Run this after apply to point kubectl at the new cluster."
  value       = "aws eks update-kubeconfig --name ${module.interpose_eks.cluster_name} --region ${var.region}"
}

output "rds_address" {
  value = module.interpose_eks.rds_address
}

output "rds_secret_arn" {
  description = "Fetch the RDS master password with: aws secretsmanager get-secret-value --secret-id <this>"
  value       = module.interpose_eks.rds_secret_arn
}

output "audit_archive_bucket_name" {
  value = module.interpose_eks.audit_archive_bucket_name
}

output "gateway_irsa_role_arn" {
  value = module.interpose_eks.gateway_irsa_role_arn
}
