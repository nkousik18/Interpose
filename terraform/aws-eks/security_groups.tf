# Security group definitions (docs/INTERPOSE_SCOPING.md Section 11.6). EKS itself
# manages a default cluster security group automatically (the control plane <-> node
# ENI traffic); this file only adds what that default doesn't cover -- node-to-node
# traffic, and narrow inbound access from nodes to RDS/ElastiCache.

resource "aws_security_group" "nodes" {
  name_prefix = "${local.name_prefix}-nodes-"
  description = "EKS worker nodes -- node-to-node traffic and all outbound."
  vpc_id      = aws_vpc.this.id

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-nodes"
  })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_security_group_rule" "nodes_self" {
  description              = "Allow nodes to reach each other on any port (pod-to-pod, kubelet, etc.)."
  type                     = "ingress"
  from_port                = 0
  to_port                  = 0
  protocol                 = "-1"
  security_group_id        = aws_security_group.nodes.id
  source_security_group_id = aws_security_group.nodes.id
}

resource "aws_security_group_rule" "nodes_egress" {
  description       = "Nodes need outbound for image pulls, AWS API calls (via NAT), DNS, etc."
  type              = "egress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  security_group_id = aws_security_group.nodes.id
  cidr_blocks       = ["0.0.0.0/0"]
}

resource "aws_security_group" "rds" {
  name_prefix = "${local.name_prefix}-rds-"
  description = "RDS Postgres -- inbound only from EKS worker nodes, on 5432."
  vpc_id      = aws_vpc.this.id

  ingress {
    description     = "Postgres from EKS nodes"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.nodes.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-rds"
  })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_security_group" "redis" {
  count       = var.enable_elasticache ? 1 : 0
  name_prefix = "${local.name_prefix}-redis-"
  description = "ElastiCache Redis -- inbound only from EKS worker nodes, on 6379."
  vpc_id      = aws_vpc.this.id

  ingress {
    description     = "Redis from EKS nodes"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.nodes.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-redis"
  })

  lifecycle {
    create_before_destroy = true
  }
}
