# IRSA (IAM Roles for Service Accounts) for pod service accounts
# (docs/INTERPOSE_SCOPING.md Section 11.6). The EKS cluster's own IAM role and node
# group role live in eks.tf instead -- this file is specifically the mechanism that
# lets one Kubernetes ServiceAccount (the gateway's) assume one narrowly-scoped IAM
# role, rather than every pod on a node inheriting whatever permissions the node's
# own EC2 instance profile has (which eks.tf's node-group role deliberately doesn't
# carry any of this -- see its own comment: only the three baseline EKS worker
# policies, nothing more).
#
# What the gateway actually needs AWS access for in production: reading its own
# DB/Redis credentials from Secrets Manager (rds.tf, elasticache.tf) instead of a
# Helm values file baking them in, and reading/writing the audit archive bucket
# (s3.tf) for the warm-tier archival Section 10.7 describes.

data "aws_iam_policy_document" "gateway_irsa_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.eks.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${replace(aws_iam_openid_connect_provider.eks.url, "https://", "")}:sub"
      values   = ["system:serviceaccount:${var.gateway_namespace}:${var.gateway_service_account_name}"]
    }
    condition {
      test     = "StringEquals"
      variable = "${replace(aws_iam_openid_connect_provider.eks.url, "https://", "")}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "gateway" {
  name               = "${local.name_prefix}-gateway-irsa"
  assume_role_policy = data.aws_iam_policy_document.gateway_irsa_assume.json

  tags = local.common_tags
}

data "aws_iam_policy_document" "gateway_secrets" {
  statement {
    sid     = "ReadDbAndRedisCredentials"
    effect  = "Allow"
    actions = ["secretsmanager:GetSecretValue"]
    resources = compact([
      aws_secretsmanager_secret.db.arn,
      var.enable_elasticache ? aws_secretsmanager_secret.redis[0].arn : "",
    ])
  }
}

data "aws_iam_policy_document" "gateway_audit_archive" {
  statement {
    sid       = "ListAuditArchiveBucket"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.audit_archive.arn]
  }
  statement {
    sid       = "ReadWriteAuditArchiveObjects"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.audit_archive.arn}/*"]
  }
}

resource "aws_iam_role_policy" "gateway_secrets" {
  name   = "${local.name_prefix}-gateway-secrets"
  role   = aws_iam_role.gateway.id
  policy = data.aws_iam_policy_document.gateway_secrets.json
}

resource "aws_iam_role_policy" "gateway_audit_archive" {
  name   = "${local.name_prefix}-gateway-audit-archive"
  role   = aws_iam_role.gateway.id
  policy = data.aws_iam_policy_document.gateway_audit_archive.json
}
