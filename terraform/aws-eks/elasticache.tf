# ElastiCache Redis -- session state, rate-limit counters, HITL ticket queue
# (docs/INTERPOSE_SCOPING.md Section 6.8, Section 11.6). Entirely gated by
# `var.enable_elasticache`; see that variable's own comment for what "false" means
# (an in-cluster Redis instead, the Helm chart's existing `redis.embedded` toggle).
#
# Single node (`num_cache_clusters = 1`, no read replica) -- this module's reference
# deploy targets the doc's own ~$150-200/month estimate, not HA. A real production
# install would bump this via `-var` overrides this module doesn't currently expose
# as a dedicated variable (deliberately -- see rds.tf's `skip_final_snapshot`
# comment for the same "don't pretend to enforce a production posture from a demo
# module's defaults" reasoning).

resource "random_password" "redis_auth" {
  count   = var.enable_elasticache ? 1 : 0
  length  = 32
  special = false # ElastiCache AUTH tokens reject several special characters too.
}

resource "aws_secretsmanager_secret" "redis" {
  count       = var.enable_elasticache ? 1 : 0
  name        = "${local.name_prefix}-redis-auth-token"
  description = "ElastiCache AUTH token for ${local.name_prefix} -- read by the gateway's IRSA role (iam.tf)."

  tags = local.common_tags
}

resource "aws_secretsmanager_secret_version" "redis" {
  count         = var.enable_elasticache ? 1 : 0
  secret_id     = aws_secretsmanager_secret.redis[0].id
  secret_string = random_password.redis_auth[0].result
}

resource "aws_elasticache_subnet_group" "this" {
  count      = var.enable_elasticache ? 1 : 0
  name       = "${local.name_prefix}-redis"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_elasticache_replication_group" "this" {
  count = var.enable_elasticache ? 1 : 0

  replication_group_id = "${local.name_prefix}-redis"
  description          = "Redis for ${local.name_prefix} (session state, rate limiting, HITL queue)"
  engine               = "redis"
  engine_version       = "7.1"
  node_type            = var.redis_node_type
  num_cache_clusters   = 1
  port                 = 6379

  subnet_group_name  = aws_elasticache_subnet_group.this[0].name
  security_group_ids = [aws_security_group.redis[0].id]

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  auth_token                 = random_password.redis_auth[0].result

  tags = local.common_tags
}
