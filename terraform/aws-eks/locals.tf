# Computed values, naming conventions (docs/INTERPOSE_SCOPING.md Section 11.6).
locals {
  # e.g. "interpose-dev" -- the prefix every resource this module creates uses, so
  # two installs of this module (a real dev + a real prod) never collide on name.
  name_prefix = "${var.cluster_name}-${var.environment}"

  common_tags = merge(
    {
      Project     = "interpose"
      Environment = var.environment
      ManagedBy   = "terraform"
    },
    var.tags
  )

  azs = slice(data.aws_availability_zones.available.names, 0, var.availability_zone_count)
}
