# VPC, subnets, NAT, route tables (docs/INTERPOSE_SCOPING.md Section 11.6). Hand-rolled
# rather than the community `terraform-aws-modules/vpc` module -- same reasoning
# this project already applied to Postgres/Redis Helm charts (values.yaml's
# `postgres.embedded` comment): an external module dependency buys nothing a dozen
# resources here don't already cover plainly, for a module whose whole purpose is
# demonstrating real understanding of what an EKS-ready VPC actually needs.
#
# Standard 2-tier layout: public subnets (NAT Gateways, load balancers) and private
# subnets (EKS nodes -- no public IP, outbound-only via NAT) across
# `var.availability_zone_count` AZs. `cidrsubnet` carves /24s out of the /16 VPC CIDR:
# public subnets start at network index 0, private at index 100, so the two ranges
# can never collide regardless of how many AZs this module is asked to span.

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(local.common_tags, {
    Name = local.name_prefix
  })
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-igw"
  })
}

resource "aws_subnet" "public" {
  count                   = var.availability_zone_count
  vpc_id                  = aws_vpc.this.id
  availability_zone       = local.azs[count.index]
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index)
  map_public_ip_on_launch = true

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-public-${local.azs[count.index]}"
    Tier = "public"
    # EKS auto-discovers subnets for internet-facing load balancers via this tag.
    "kubernetes.io/role/elb" = "1"
    # Required so EKS's own subnet-discovery logic recognizes this VPC's subnets as
    # belonging to this cluster once it exists -- "shared" (not "owned") since this
    # VPC isn't exclusively owned by one EKS cluster's lifecycle.
    "kubernetes.io/cluster/${local.name_prefix}" = "shared"
  })
}

resource "aws_subnet" "private" {
  count             = var.availability_zone_count
  vpc_id            = aws_vpc.this.id
  availability_zone = local.azs[count.index]
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, count.index + 100)

  tags = merge(local.common_tags, {
    Name                                         = "${local.name_prefix}-private-${local.azs[count.index]}"
    Tier                                         = "private"
    "kubernetes.io/role/internal-elb"            = "1"
    "kubernetes.io/cluster/${local.name_prefix}" = "shared"
  })
}

# NAT Gateway(s) -- see variables.tf's single_nat_gateway comment for the cost/HA
# tradeoff. Each NAT Gateway needs its own Elastic IP.
resource "aws_eip" "nat" {
  count  = var.single_nat_gateway ? 1 : var.availability_zone_count
  domain = "vpc"

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-nat-eip-${count.index}"
  })
}

resource "aws_nat_gateway" "this" {
  count         = var.single_nat_gateway ? 1 : var.availability_zone_count
  allocation_id = aws_eip.nat[count.index].id
  # Single-NAT mode still needs exactly one public subnet to live in -- the first one.
  subnet_id = aws_subnet.public[count.index].id

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-nat-${count.index}"
  })

  depends_on = [aws_internet_gateway.this]
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-public"
  })
}

resource "aws_route_table_association" "public" {
  count          = var.availability_zone_count
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# One route table per AZ for private subnets, even in single-NAT mode -- every AZ's
# table just ends up routing to the same shared NAT Gateway in that case. Keeping
# the resource shape identical between single- and multi-NAT modes (rather than a
# single shared table in one case, per-AZ in the other) avoids conditional
# complexity elsewhere that would need to know which mode is active.
resource "aws_route_table" "private" {
  count  = var.availability_zone_count
  vpc_id = aws_vpc.this.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = var.single_nat_gateway ? aws_nat_gateway.this[0].id : aws_nat_gateway.this[count.index].id
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-private-${local.azs[count.index]}"
  })
}

resource "aws_route_table_association" "private" {
  count          = var.availability_zone_count
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[count.index].id
}
