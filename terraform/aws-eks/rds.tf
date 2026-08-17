# RDS Postgres -- the audit log's hot tier (docs/INTERPOSE_SCOPING.md Section 10.7,
# Section 11.6). `storage_encrypted = true` unconditionally (RDS's own default
# AWS-managed key when `enable_custom_kms = false`, the dedicated key from kms.tf
# otherwise) -- unlike EKS, RDS always has *some* encryption-at-rest default to fall
# back to, so there's no "unencrypted" mode to accidentally leave this in.

resource "random_password" "db" {
  length  = 32
  special = false # RDS master passwords reject several special characters; simpler to avoid the set entirely than enumerate which ones are safe.
}

resource "aws_secretsmanager_secret" "db" {
  name        = "${local.name_prefix}-rds-master-password"
  description = "RDS master password for ${local.name_prefix} -- read by the gateway's IRSA role (iam.tf), never baked into a Helm values file."

  tags = local.common_tags
}

resource "aws_secretsmanager_secret_version" "db" {
  secret_id     = aws_secretsmanager_secret.db.id
  secret_string = random_password.db.result
}

resource "aws_db_subnet_group" "this" {
  name       = "${local.name_prefix}-rds"
  subnet_ids = aws_subnet.private[*].id

  tags = local.common_tags
}

resource "aws_db_instance" "this" {
  identifier     = "${local.name_prefix}-audit-log"
  engine         = "postgres"
  engine_version = "16"
  instance_class = var.db_instance_class

  allocated_storage = var.db_allocated_storage
  storage_type      = "gp3"
  storage_encrypted = true
  kms_key_id        = var.enable_custom_kms ? aws_kms_key.rds[0].arn : null

  db_name  = var.db_name
  username = var.db_username
  password = random_password.db.result

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  # Section 10.7: "RDS automated snapshots daily (production). Point-in-time
  # recovery to any second within the last 7 days."
  backup_retention_period = 7
  backup_window           = "03:00-04:00"

  # A demo/reference deploy default -- a real production install should set this
  # true via `-var skip_final_snapshot=false` (not exposed as a variable here on
  # purpose: this module's own defaults target "cheap to tear down while learning
  # it," not a production data-retention policy this module can't actually enforce
  # from outside anyway).
  skip_final_snapshot = true

  tags = local.common_tags
}
