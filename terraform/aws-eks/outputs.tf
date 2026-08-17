# Module outputs (docs/INTERPOSE_SCOPING.md Section 11.6): "everything a downstream
# Helm install needs." None of these are the raw RDS password or Redis auth token --
# both stay in Secrets Manager (rds.tf, elasticache.tf); these outputs are the ARNs
# a deployer points `external-secrets-operator` at (charts/interpose/values.yaml's
# own `secrets.existingSecretName` comment already names this as the production
# pattern), never the secret values themselves in `terraform output` or state-viewer
# tooling any wider than strictly necessary.

output "cluster_name" {
  description = "EKS cluster name -- pass to `aws eks update-kubeconfig --name <this>`."
  value       = aws_eks_cluster.this.name
}

output "cluster_endpoint" {
  description = "EKS API server endpoint."
  value       = aws_eks_cluster.this.endpoint
}

output "cluster_certificate_authority_data" {
  description = "Base64-encoded cluster CA certificate, for kubeconfig generation."
  value       = aws_eks_cluster.this.certificate_authority[0].data
}

output "cluster_oidc_issuer_url" {
  description = "The cluster's OIDC issuer URL (iam.tf's IRSA trust policy is built from this)."
  value       = aws_eks_cluster.this.identity[0].oidc[0].issuer
}

output "gateway_irsa_role_arn" {
  description = "IAM role the gateway's ServiceAccount assumes -- set as the `eks.amazonaws.com/role-arn` annotation on that ServiceAccount (charts/interpose/templates/serviceaccount.yaml doesn't set this today; a production values overlay needs to add it)."
  value       = aws_iam_role.gateway.arn
}

output "rds_address" {
  description = "RDS instance hostname (no port)."
  value       = aws_db_instance.this.address
}

output "rds_port" {
  description = "RDS instance port."
  value       = aws_db_instance.this.port
}

output "rds_database_name" {
  description = "Database name Interpose's gateway connects to."
  value       = aws_db_instance.this.db_name
}

output "rds_secret_arn" {
  description = "Secrets Manager ARN holding the RDS master password."
  value       = aws_secretsmanager_secret.db.arn
}

output "redis_endpoint" {
  description = "ElastiCache primary endpoint address, or null when enable_elasticache=false (an in-cluster Redis is used instead -- see that variable's comment)."
  value       = var.enable_elasticache ? aws_elasticache_replication_group.this[0].primary_endpoint_address : null
}

output "redis_secret_arn" {
  description = "Secrets Manager ARN holding the Redis AUTH token, or null when enable_elasticache=false."
  value       = var.enable_elasticache ? aws_secretsmanager_secret.redis[0].arn : null
}

output "audit_archive_bucket_name" {
  description = "S3 bucket name for the audit log's warm/cold archive tier."
  value       = aws_s3_bucket.audit_archive.bucket
}

output "audit_archive_bucket_arn" {
  description = "S3 bucket ARN for the audit log's warm/cold archive tier."
  value       = aws_s3_bucket.audit_archive.arn
}

output "vpc_id" {
  description = "VPC ID."
  value       = aws_vpc.this.id
}

output "private_subnet_ids" {
  description = "Private subnet IDs (EKS nodes, RDS, ElastiCache)."
  value       = aws_subnet.private[*].id
}

output "public_subnet_ids" {
  description = "Public subnet IDs (NAT Gateways, internet-facing load balancers)."
  value       = aws_subnet.public[*].id
}
