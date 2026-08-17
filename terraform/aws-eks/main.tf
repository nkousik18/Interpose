# Shared data sources every other file in this module reads from. No `provider`
# block here, deliberately -- this file is a *reusable module* (instantiated via
# `module "..." { source = "..." }`), not a root module. Terraform provider
# configuration is the root module's job (see examples/minimal/main.tf); a reusable
# module declaring its own provider block would either conflict with the root's
# configuration or force every caller to use "provider passing," both of which
# defeat the point of this module being reusable across more than one root
# (Section 11.6: "given AWS creds and a bucket for state, `terraform apply` from
# `examples/minimal/` provisions a working environment" -- implying other root
# modules could exist too).
data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}
