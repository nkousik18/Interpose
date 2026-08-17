# EKS cluster + managed node group (docs/INTERPOSE_SCOPING.md Section 11.6). The
# cluster's own IAM role and the node group's own IAM role live here, colocated with
# what they serve -- iam.tf is reserved for IRSA (pod-level) roles specifically, see
# that file's own header comment.

resource "aws_iam_role" "cluster" {
  name = "${local.name_prefix}-eks-cluster"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "eks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "cluster_policy" {
  role       = aws_iam_role.cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}

resource "aws_eks_cluster" "this" {
  name     = local.name_prefix
  role_arn = aws_iam_role.cluster.arn
  version  = var.kubernetes_version

  vpc_config {
    # Both public and private subnets -- the control plane's own ENIs can land in
    # either; only the node group below is restricted to private subnets.
    subnet_ids = concat(aws_subnet.public[*].id, aws_subnet.private[*].id)
  }

  # Section 11.8's observability scope: API server audit/authenticator logs to
  # CloudWatch (monitoring.tf creates the matching log group).
  enabled_cluster_log_types = ["api", "audit", "authenticator"]

  dynamic "encryption_config" {
    # Only when a customer-managed KMS key exists (kms.tf, enable_custom_kms) --
    # omitting this block entirely (not pointing at some default) when
    # enable_custom_kms=false, since EKS has no "default CMK" for Kubernetes
    # Secrets envelope encryption the way RDS/S3 do for their own storage -- this is
    # a real behavior difference, not just a formality, so examples/minimal/ (which
    # sets enable_custom_kms=false) genuinely runs without this extra layer, not a
    # silently-defaulted equivalent.
    for_each = var.enable_custom_kms ? [1] : []
    content {
      provider {
        key_arn = aws_kms_key.eks[0].arn
      }
      resources = ["secrets"]
    }
  }

  depends_on = [aws_iam_role_policy_attachment.cluster_policy]

  tags = local.common_tags
}

# IRSA (IAM Roles for Service Accounts, iam.tf) needs the cluster's OIDC issuer
# registered as an IAM identity provider -- this is the one piece of plumbing that
# makes "a specific Kubernetes ServiceAccount can assume a specific IAM role" work
# at all. `tls_certificate` fetches the issuer's TLS certificate purely to read its
# root CA thumbprint, which `aws_iam_openid_connect_provider` requires.
data "tls_certificate" "eks_oidc" {
  url = aws_eks_cluster.this.identity[0].oidc[0].issuer
}

resource "aws_iam_openid_connect_provider" "eks" {
  url             = aws_eks_cluster.this.identity[0].oidc[0].issuer
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.eks_oidc.certificates[0].sha1_fingerprint]

  tags = local.common_tags
}

resource "aws_iam_role" "node_group" {
  name = "${local.name_prefix}-eks-node-group"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = local.common_tags
}

# The three policies every EKS worker node needs, regardless of what workloads it
# runs: join the cluster, run the CNI (pod networking), pull images from ECR.
resource "aws_iam_role_policy_attachment" "node_worker" {
  role       = aws_iam_role.node_group.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
}

resource "aws_iam_role_policy_attachment" "node_cni" {
  role       = aws_iam_role.node_group.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
}

resource "aws_iam_role_policy_attachment" "node_ecr" {
  role       = aws_iam_role.node_group.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

resource "aws_eks_node_group" "this" {
  cluster_name    = aws_eks_cluster.this.name
  node_group_name = "${local.name_prefix}-default"
  node_role_arn   = aws_iam_role.node_group.arn
  # Private subnets only -- worker nodes get no public IP; outbound traffic (image
  # pulls, AWS API calls) goes through the NAT Gateway(s) in vpc.tf.
  subnet_ids     = aws_subnet.private[*].id
  instance_types = [var.node_instance_type]

  scaling_config {
    desired_size = var.node_desired_size
    min_size     = var.node_min_size
    max_size     = var.node_max_size
  }

  # Ensures the worker-node policies are attached before nodes try to join --
  # otherwise node registration can fail on the very first apply.
  depends_on = [
    aws_iam_role_policy_attachment.node_worker,
    aws_iam_role_policy_attachment.node_cni,
    aws_iam_role_policy_attachment.node_ecr,
  ]

  tags = local.common_tags
}
