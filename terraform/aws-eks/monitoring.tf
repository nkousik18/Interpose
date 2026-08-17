# CloudWatch log groups + alarms (docs/INTERPOSE_SCOPING.md Section 11.6).
# Deliberately scoped to AWS-infrastructure-level monitoring only -- application-level
# golden-signal metrics/alerting (Section 11.8's Prometheus/AlertManager rules) are
# the Helm chart's own concern (`charts/interpose/templates/otel-collector/`,
# `.../prometheus/`, `concepts/34-metrics-and-prometheus.md`), not something this
# Terraform module reaches into the cluster to configure.

resource "aws_cloudwatch_log_group" "eks_cluster" {
  # EKS's own naming convention for cluster control-plane logs -- must match exactly
  # for the log group `aws_eks_cluster.this`'s `enabled_cluster_log_types` writes to
  # (eks.tf) to actually land here instead of an auto-created, unmanaged group with
  # AWS's own default (never-expire) retention.
  name              = "/aws/eks/${local.name_prefix}/cluster"
  retention_in_days = 30

  tags = local.common_tags
}

resource "aws_sns_topic" "alarms" {
  name = "${local.name_prefix}-alarms"

  tags = local.common_tags
}

# One representative pair of RDS alarms, not an exhaustive production alerting
# suite -- this module proves the AWS-infra-level monitoring pattern (a CloudWatch
# alarm publishing to an SNS topic an operator subscribes to however they prefer:
# email, PagerDuty, a Lambda), not a claim of covering every metric a real
# production deploy would want watched.
resource "aws_cloudwatch_metric_alarm" "rds_cpu" {
  alarm_name          = "${local.name_prefix}-rds-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "RDS CPU utilization above 80% for 15 minutes."
  alarm_actions       = [aws_sns_topic.alarms.arn]
  ok_actions          = [aws_sns_topic.alarms.arn]

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.this.id
  }

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "rds_free_storage" {
  alarm_name          = "${local.name_prefix}-rds-storage-low"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 1
  metric_name         = "FreeStorageSpace"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  # 2 GiB, in bytes -- a fixed floor rather than a percentage of
  # `var.db_allocated_storage`, since RDS storage autoscaling (not enabled by this
  # module) can change the denominator out from under a percentage-based threshold.
  threshold         = 2147483648
  alarm_description = "RDS free storage below 2 GiB."
  alarm_actions     = [aws_sns_topic.alarms.arn]
  ok_actions        = [aws_sns_topic.alarms.arn]

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.this.id
  }

  tags = local.common_tags
}
