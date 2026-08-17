# Terraform + provider version pinning (docs/INTERPOSE_SCOPING.md Section 11.6).
# Pinned with `~>` (allow patch/minor upgrades, never a breaking major) rather than
# an exact version -- this module is meant to stay usable as AWS/Kubernetes provider
# releases roll forward, not frozen to whatever was current the day it was written.
terraform {
  required_version = ">= 1.7"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.30"
    }
    # Generates the RDS master password and the Redis auth token -- neither is a
    # plain `variable` with a default (a secret checked into a `.tfvars` file
    # defeats the point), and neither needs to be memorable, just random and
    # rotatable. See rds.tf / elasticache.tf.
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
    # Fetches the EKS cluster's OIDC issuer certificate thumbprint -- the one piece
    # IRSA needs that the `aws` provider itself doesn't expose (registering an EKS
    # cluster's OIDC issuer as an IAM identity provider requires that thumbprint).
    # See eks.tf.
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }
}
