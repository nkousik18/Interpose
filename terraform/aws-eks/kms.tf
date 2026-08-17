# Customer-managed KMS keys (docs/INTERPOSE_SCOPING.md Section 11.6), gated by
# `var.enable_custom_kms`. One key per service rather than one shared key -- so each
# service's key policy, rotation, and audit trail (CloudTrail records which key
# encrypted/decrypted what) stays scoped to that one service, not blurred across
# three unrelated data stores sharing a single key.
#
# When `enable_custom_kms = false` (examples/minimal/'s own setting), none of these
# exist at all -- RDS/S3 fall back to their own AWS-managed default encryption,
# which is real encryption at rest, just without a customer-managed key an operator
# can independently rotate, audit, or revoke access to. See eks.tf's
# `encryption_config` comment for why EKS specifically has no equivalent default to
# fall back to.

resource "aws_kms_key" "rds" {
  count                   = var.enable_custom_kms ? 1 : 0
  description             = "${local.name_prefix} RDS (audit log Postgres) encryption key"
  enable_key_rotation     = true
  deletion_window_in_days = 30

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-rds"
  })
}

resource "aws_kms_key" "s3" {
  count                   = var.enable_custom_kms ? 1 : 0
  description             = "${local.name_prefix} S3 (audit archive) encryption key"
  enable_key_rotation     = true
  deletion_window_in_days = 30

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-s3"
  })
}

resource "aws_kms_key" "eks" {
  count                   = var.enable_custom_kms ? 1 : 0
  description             = "${local.name_prefix} EKS Kubernetes Secrets envelope encryption key"
  enable_key_rotation     = true
  deletion_window_in_days = 30

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-eks"
  })
}
