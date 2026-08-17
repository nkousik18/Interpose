# Audit archive bucket -- the warm/cold tier of the audit log (docs/INTERPOSE_SCOPING.md
# Section 10.7): entries older than 30 days archived to Parquet here by a Spark job
# (out of this module's scope -- it only provisions the bucket the job writes to),
# transitioning to Glacier after `var.audit_archive_glacier_transition_days` (90,
# matching Section 10.7's own number) for the cold tier.
#
# Bucket names are globally unique across all of AWS, not just this account -- the
# account ID suffix is what keeps two different AWS accounts from ever colliding on
# the same `cluster_name`/`environment` combination.
resource "aws_s3_bucket" "audit_archive" {
  bucket = "${local.name_prefix}-audit-archive-${data.aws_caller_identity.current.account_id}"

  tags = local.common_tags
}

resource "aws_s3_bucket_public_access_block" "audit_archive" {
  bucket = aws_s3_bucket.audit_archive.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "audit_archive" {
  bucket = aws_s3_bucket.audit_archive.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "audit_archive" {
  bucket = aws_s3_bucket.audit_archive.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = var.enable_custom_kms ? "aws:kms" : "AES256"
      kms_master_key_id = var.enable_custom_kms ? aws_kms_key.s3[0].arn : null
    }
    bucket_key_enabled = var.enable_custom_kms
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "audit_archive" {
  bucket = aws_s3_bucket.audit_archive.id

  rule {
    id     = "warm-to-cold"
    status = "Enabled"

    filter {}

    transition {
      days          = var.audit_archive_glacier_transition_days
      storage_class = "GLACIER"
    }
  }
}
